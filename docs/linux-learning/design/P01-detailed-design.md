# P01 상세 설계 — 애플리케이션 뼈대와 인증

> 실제 작성된 P01 설계의 공개용 정제본이다. local path, receipt/revision/hash, role 실행 기록, 과거 orchestration appendix는 제외했다. 구현·test·배포 완료를 주장하지 않는다.

## P01 완료 경계와 file 구성

P01은 login, session, course membership, 본인 data 접근, 관리자 disable이 동작하는 최소 Korean app이다. source 본문, section completion, generation, grading, Memory는 P02–P05가 소유한다. 미구현 endpoint는 fake success/temporary answer를 반환하지 않는다.

| path / 책임 | 구현 내용 |
|---|---|
| `apps/web/` | React/TypeScript/Vite login, fake account 선택, session/role, 허용 course, expiry/relogin/logout, 최소 admin disable UI, mobile/keyboard |
| `apps/api/` | FastAPI app factory, error envelope, BFF auth, authorization dependency, explicit DTO, SQLAlchemy repository, Alembic |
| `apps/worker/` | 별도 entrypoint/process, shared config/DB/domain, DB queue, heartbeat, bounded shutdown; generation은 미구현 |
| `packages/domain/` | installable Python config, Principal/role/course policy, provider protocol, DB model/common type |
| `packages/api-client/` | browser-safe TypeScript DTO/client; ORM/private fixture/server secret 제외 |
| root tooling | `pyproject.toml`/`uv.lock`, npm workspace/lock, lint/typecheck/test/build, Makefile, env example, dockerignore |
| containers | web/API/worker/Postgres+pgvector/one-shot migration/local TLS |
| tests/CI | unit, real PostgreSQL integration/migration, browser auth E2E, public artifact 검사 |

dependency와 image version/digest는 도입 시 공식 support와 실제 install을 확인하고 real package manager로 lock한다. source/answer fixture, `.env`, key, orchestration/history, artifact/log는 container context에 넣지 않는다.

## Local 실행·DB·worker

root의 one-command startup은 tool/port/config 검사 → owner-only local secret/TLS 최초 생성 → build → DB health → migration → idempotent fake seed → API/worker/web → bounded readiness 순서다. 재실행은 key/DB/account를 덮어쓰지 않는다. 기본 origin은 `https://localhost:8443`; host trust store를 자동 수정하지 않는다. Secure `__Host-session` cookie를 실제 HTTPS browser E2E로 확인한다. web/gateway만 loopback publish하고 API/worker/DB는 internal network다.

P01 migration은 `users`, `courses`, `course_memberships`, `sessions`, `auth_transactions`, `audit_events`, `local_jobs`, `worker_heartbeats`만 소유한다. UUID, UTC timestamptz, UNIQUE/FK/CHECK/index를 둔다. migration owner와 DML runtime user를 분리한다. disposable DB에서 fresh upgrade → constraint → downgrade base → re-upgrade와 pre-existing vector extension 보존을 검사한다. API/worker startup이 migration을 경쟁 실행하지 않는다.

fake seed는 learner A/B와 admin, Linux course와 격리용 synthetic course를 만들고 stable fake subject에 대해 idempotent다. revoked membership/disabled user를 되살리지 않으며 private source/question을 seed하지 않는다.

`GET /healthz`는 process life, `GET /readyz`는 config/DB/migration head/vector를 검사한다. worker도 readiness 뒤 heartbeat를 갱신한다. DB queue는 row lock, lease, increasing fencing token, owner-only ack를 사용한다. bounded polling/attempt/shutdown을 시험하며 P04의 outbox/SQS/cost ledger를 구현했다고 주장하지 않는다.

## Live BFF와 JWT

1. `GET /auth/login`은 independent CSPRNG state/nonce/PKCE verifier/browser-binding을 만들고 TTL 5-minute transaction과 `__Host-auth` cookie를 저장한다. callback과 authorization endpoint는 fixed config로 유도하고 arbitrary redirect를 받지 않는다.
2. authorization code, S256, 최소 `openid`와 explicit scope set을 사용한다.
3. callback은 duplicate/missing/empty code/state, wrong browser binding, expiry, replay/concurrency를 거절하고 transaction을 atomic consume한다. callback은 generic CSRF가 아니라 state+browser binding을 사용한다.
4. server만 exact redirect URI/verifier로 token endpoint를 호출한다. fixed HTTPS origin, no redirect, short timeout/size limit을 적용하고 query/body를 log하지 않는다.
5. ID/access token은 signature, RS256 allowlist, fixed issuer, exp/nbf/iat consistency, claim type을 각각 검증한다. ID는 `token_use=id`, `aud`, nonce; access는 `token_use=access`, `client_id`, required scopes와 optional API audience를 검사한다. subject가 같아야 한다.
6. JWKS는 fixed pool configuration에서만 유도한다. token의 `jku/x5u/iss`로 URL을 fetch하지 않는다. bounded `kid` cache와 one refresh를 사용하며 safe cache 없는 outage는 503이다.
7. verified subject로 preregistered enabled user를 찾는다. email/group/custom claim/query/body/header가 user creation/admin escalation 근거가 아니다. public signup/JIT endpoint는 없다.
8. new opaque session을 만들고 existing browser session을 revoke한다. provider token은 authenticated encryption으로 저장하고 raw cookie는 hash lookup만 한다. success 뒤 query 없는 fixed `/`로 redirect한다.

live adapter는 injected HTTP transport와 test RSA key로 실제 crypto validation을 검사한다. fake adapter 성공만으로 live login을 통과시키지 않으며 actual tenant login은 deployment gate다.

## Session·CSRF·logout

session cookie는 Secure/HttpOnly/SameSite=Lax/Path=/, no Domain, entropy ≥256 bit다. browser에 JWT/refresh/key/session hash를 주지 않는다. session은 최대 1시간이고 live access expiry보다 길 수 없다. implicit refresh는 P01에 없다.

매 요청 session hash → expiry/revocation → current `users.disabled_at`/DB role → membership을 조회한다. Bearer/ID token, `X-User-Id`, `X-Role`, fake header를 browser auth로 받지 않는다. `GET /api/v1/session`은 opaque user/display/DB role/provider/expiry/session-bound CSRF만 반환한다.

모든 POST/PUT/PATCH/DELETE는 exact scheme/host/port Origin과 `X-CSRF-Token`을 검사한다. forged Host/Forwarded, suffix/wildcard, 다른 session token, cross-site form을 거절한다. logout은 local session revoke/token removal/cookie deletion을 즉시 수행한다. admin disable은 user disable과 모든 session revoke/token removal을 한 transaction에서 수행한다. auth response는 no-store이고 secret/query/body를 log하지 않는다.

## Fake identity

`APP_ENV=local|test`와 `PROVIDER_MODE=fake`에서만 fake route/factory/seed가 존재한다. preauth browser-binding cookie와 CSRF 뒤 enum `learner-a|learner-b|admin`만 받고 arbitrary subject/user/role을 금지한다. preauth는 5분/one-time이다. 모든 화면은 local fake를 표시한다. staging/production fake나 mixed provider는 startup failure다.

## Server 인가와 최소 API

인증 dependency와 course/ownership repository filter를 분리하되 route마다 함께 적용한다. 미인증 401 → mutation의 Origin/CSRF 403 → global admin role 403 → course membership/타인 entity 404 순서를 고정한다. UUID 형식 오류 등 validation은 공통 error envelope로 변환한다. 알려진 entity와 미존재 entity의 404 body는 동일하다. client `user_id` 입력은 `extra=forbid`로 거절한다.

| method/path | P01 동작 / 권한 |
|---|---|
| GET `/auth/login`, GET `/auth/callback` | 위 BFF/preauth 계약 |
| POST `/auth/local-login` | local/test fake에서만 preauth CSRF 계정 선택 |
| GET `/api/v1/session`, POST `/auth/logout` | 본인 session / 변경 시 CSRF |
| GET `/api/v1/courses` | 현재 user의 non-revoked membership을 join한 course metadata만 |
| GET `/api/v1/courses/{slug}` | 동일 membership을 확인한 단일 course metadata, `linux` alias 지원 |
| GET `/api/v1/sessions`, DELETE `/api/v1/sessions/{id}` | 본인의 public session ID/created/expiry/current 여부만. 삭제는 본인 session revoke. 타인의 관리 ID는 404 |
| GET `/api/v1/admin/users` | DB global admin만 제한된 user ID/display name/role/disabled 상태. pagination 상한 100, token/email/subject 반환 안 함 |
| POST `/api/v1/admin/users/{id}/disable` | global admin + CSRF. disable과 session revoke를 atomic 처리. P01에서 자기 자신 disable은 409 |
| DELETE `/api/v1/admin/courses/{slug}/memberships/{id}` | global admin 및 해당 course admin membership + CSRF. target membership의 course 일치 필수, `revoked_at` 갱신 |

global admin이라고 개인 session 조회나 모든 course content 읽기가 자동 허용되지 않는다. course membership의 admin만으로 `users.role`이 admin으로 바뀌지 않는다. permission을 prompt/model로 판단하지 않는다. 권한 변경 API를 추가한다면 동일 DB role/course scope·audit·CSRF를 요구하며 P01에는 임의 role escalation path를 만들지 않는다.

`GET /api/v1/sessions`와 DELETE는 P01의 실제 본인 entity isolation 증거다. P05 attempt ownership을 미리 구현하거나 빈 endpoint만 검사하지 않는다. domain은 향후 course/version/object 권한을 전달할 type을 제공하고 후속 기능은 같은 policy를 재사용한다. auth만 통과한 결과를 source access 승인으로 해석하지 않는다.

response는 DTO allowlist로 수동 mapping하며 ORM 전체 serialize를 금지한다. learner/admin type을 구분한다. P01에는 question/result data가 없고 frontend에 기준문항을 import하지 않는다. production bundle/HTML/source map/container context를 private source·answer/explanation canary와 secret canary로 검사한다. P05의 실제 pre-submit leak test를 P01 scaffold 검사로 대체하지 않는다.

## 필수 구현·검증 gate

- `make dev`/smoke: actual containers, HTTPS, API readiness, worker heartbeat, rerun idempotency와 negative readiness.
- lint/typecheck/build: Python/TypeScript 전체, frozen install, wheel/image/web build.
- unit: config matrix, provider no-network, JWT crypto, session/CSRF/DTO/clock.
- integration/migration: actual PostgreSQL+vector, FK/UNIQUE/CHECK, auth/membership/revoke/queue, fresh DB roundtrip.
- browser E2E: HTTPS cookie, A/B/admin, reload/logout/expiry, A/B session/course isolation, admin denial, keyboard/narrow viewport.
- public artifact: production bundle/map/container copy 목록에 private source/answer/secret canary 없음, auth/API error의 SPA fallback 없음.

JWT wrong signature/algorithm/issuer/expiry/nonce/subject/client/audience/token type/scope, OAuth state/binding/replay, session fixation/expiry/revoke, missing/evil Origin/CSRF, cross-user/course access, role escalation, fake/live mismatch를 positive control과 함께 검사한다. container/registry prerequisite가 없으면 skip-pass하지 않고 blocked로 남긴다.
