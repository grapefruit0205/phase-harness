# 데이터 및 API 계약

> 공개용 정제본이다. identifier는 schema 설명용이며 실제 사용자·source 값은 포함하지 않는다.

## 저장 계약

시각은 UTC, 내부 key는 UUID, 교육 concept/unit key는 curriculum의 stable string ID다. 사용자 key는 검증한 identity subject로 조회하며 client `user_id`를 사용하지 않는다. 운영 migration은 다음 unique/FK/check 제약을 포함한다.

| table | 핵심 field·제약 |
|---|---|
| `users` / `sessions` | `cognito_sub` UNIQUE, DB role, `disabled_at`; session hash, user, encrypted tokens, expiry, `revoked_at` |
| `course_memberships` | UNIQUE(user,course), role, `granted_by`, `revoked_at` |
| `sources` / `source_versions` | course, source root, access active/stale/revoked, last check; version staging/active/retired, `manifest_hash`, UNIQUE(course,manifest_hash), course당 active 최대 1 |
| `source_blocks` | version, stable page/block locator, heading path, text, hash; UNIQUE(version,block locator) |
| `media_assets` | version/block, storage key, sha256, MIME, alt, validation/access; 임시 signed URL 지속 저장 금지 |
| `units` / `sections` / `concepts` | stable ID, prerequisites, objectives, order, evidence/eligibility |
| `chunks` | source version, 실제 block refs, unit/concepts, text, embedding model/dimension/vector |
| `attempt_requests` | user,unit,source version,idempotency key,request hash,state,attempt/job; UNIQUE(user,operation,key) |
| `generation_jobs` / `job_watchers` | dedup key, blueprint/version, state, lease/fencing, call/budget/cost/failure; watcher owner |
| `outbox` | event ID UNIQUE, job, publish/retry; job과 같은 transaction |
| `question_versions` | stable question, immutable version, unit/primary concept/source version, stem, 4 options, answer, option explanations, source refs, hash, publication |
| `question_reviews` | version, reviewer type/identity, rubric, findings, decision, model/prompt 또는 human identity, time |
| `attempts` / `attempt_items` | user,unit,source version,state,score,time; UNIQUE(attempt,ordinal), fixed question version/display mapping |
| `answers` | UNIQUE(attempt,item), chosen option, graded correctness; option ownership 강제 |
| `section_progress` | UNIQUE(user,section,source version), completion time |
| `concept_observations` / `concept_memory` | UNIQUE(attempt item,concept); user/concept observation, misconception, estimate, due, algorithm version |
| `question_challenges` / `assessment_corrections` | owner/item/reason/state/admin decision; immutable correction, excluded items, original/revised score |
| `audit_events` | actor/action/entity/correlation/time; secret/source/answer/full prompt 제외 |

active source 교체는 submitted assessment를 바꾸지 않는다. 접근 가능한 retired version에 고정된 in-progress attempt는 제출할 수 있고 새 assessment는 active만 사용한다. source 또는 question 중대 오류 철회는 진행 중 attempt를 invalidated한다. 제출 점수는 덮어쓰지 않고 correction을 추가한다. source 권한 철회 시 과거 result는 숫자·최소 이력만 제공한다.

## 인증·공통 응답

browser는 same-origin session cookie를 사용한다. API는 role, course membership, entity ownership을 매 요청 검사한다. 민감 response는 `Cache-Control: private, no-store`이고 log/analytics에 답이나 source 본문을 싣지 않는다. OpenAPI/client는 learner/admin/result type을 분리하고 ORM object를 그대로 serialize하지 않는다.

오류는 `{ "error": { "code": "...", "message": "사용자용 설명", "correlation_id": "..." } }`다. 400 문법, 401 미인증, 403 role/CSRF, 타 사용자·미허용 course entity는 404, 409 상태/같은 idempotency key의 다른 입력, 422 응답 누락·option 불일치·학습자격, 429 한도, 503 dependency 장애다. 내부 exception/secret/prompt를 반환하지 않는다.

| method/path | 동작 |
|---|---|
| `GET /auth/login`, `GET /auth/callback` | Cognito login 시작·callback state 검증 |
| `GET /api/v1/session`, `POST /auth/logout` | 본인·role·CSRF 조회, session 폐기 |
| `GET /api/v1/courses/linux/units` | 허용 course unit/objective/prerequisite/본인 progress |
| `GET /api/v1/sections/{id}` | 허용 active source; 접근 가능한 과거 `version_id` 지원 |
| `GET /api/v1/assets/{id}` | 인증·course/version 권한 뒤 safe bytes proxy |
| `PUT /api/v1/sections/{id}/completion` | `{version_id,completed}` 멱등 저장; old version은 current와 구분 |
| `POST /api/v1/units/{id}/attempts` | `Idempotency-Key` 필수; ready면 201 attempt, 아니면 202 request/job |
| `GET /api/v1/attempt-requests/{id}` | owner request의 ready/preparing/review_pending/unavailable |
| `GET /api/v1/jobs/{id}` | watcher 또는 admin; learner-safe status/retry 안내만 |
| `GET /api/v1/attempts/{id}` | owner `LearnerAttemptDTO` |
| `PUT /api/v1/attempts/{id}/answers/{item}` | `{chosen_option_id}` 저장만; submitted/invalidated는 409 |
| `POST /api/v1/attempts/{id}/submit` | body 없음; 저장한 8개 answer transaction 채점, 누락 422 |
| `GET /api/v1/attempts/{id}/result` | owner submitted만; 제출 전 409 |
| `POST /api/v1/attempts/{id}/items/{item}/challenge` | 본인 제출 item 이의; 길이/빈도 제한 |
| `POST /api/v1/admin/challenges/{id}/resolve` | decision/reason, 필요 시 quarantine/withdraw/correction outbox |
| `GET /api/v1/reviews/due` | 본인 예정 review와 허용 section link |
| `POST /api/v1/admin/sync` | allowlist source sync job |
| `GET /api/v1/admin/questions` | review/publication status별 `AdminQuestionDTO` |
| `POST /api/v1/admin/questions/{version}/review` | human reviewer audit와 immutable version 승인 |
| `POST /api/v1/admin/questions/{version}/publication` | publish/withdraw와 승인/active evidence 검사 |

assessment request body는 `{mode:"unit",new_round:false}` 또는 `{mode:"review",new_round:true}` server enum만 받는다. unit/review 대상, blueprint, source는 server가 정하고 arbitrary prompt/source/answer/item count/user ID는 거절한다.

## 준비 요청과 멱등성

마지막 필수 section completion 저장과 같은 transaction에서 automatic initial request를 만든다. server key는 user/unit/source version/initial을 결합하고 UNIQUE로 re-completion/retry를 합친다. 수동 첫 시작은 initial request를 재사용하고 명시적 새 round만 새 key를 쓴다. 모든 수동 시작도 완료 자격을 검사한다. 통합 unit은 required prior unit의 필수 section 완료까지 검사한다.

최초 요청이 user/unit/source version/blueprint를 고정한다. 같은 key로 202를 다시 요청해도 새 model job을 만들지 않는다. human approval 대기는 `review_pending`이며 job 종료만으로 attempt를 만들지 않는다. 승인 bank가 충족되면 권한/자격/source를 재검사하고 UNIQUE(request)로 정확히 한 attempt를 만든다. shared refill job을 사용해도 watcher와 request ownership은 유지한다. `unavailable`은 이유와 수동 retry 가능 여부를 담고 polling은 backoff와 종료 조건을 둔다.

## 답 누출을 막는 DTO

`LearnerAttemptDTO`는 attempt ID, `unit_id`, `source_version_id`, state와 item의 ID/ordinal/stem, 정확히 네 option의 opaque ID/text, `selected_option_id`만 허용한다. 다음은 포함하지 않는다: internal question version, answer, correctness, explanation, quotation, rubric, distractor label, reviewer/model/prompt metadata.

option ID는 A/B/C/D나 정답 위치를 encode하지 않는다. 화면 label은 attempt에 저장된 shuffle 순서로 그린다. selection 저장 response는 item/selected option/update time만 포함한다. submit은 동일 attempt row를 lock하고 정확히 8개 item/option 소속을 검사하며 duplicate/concurrent submit은 최초 한 번만 Memory observation을 만든다. client score/answer input field는 schema에서 금지한다.

`ResultDTO`는 submitted state, score, total=8, pass, item별 selected/correct option, 정답과 세 오답 이유, source version/section refs, review concept을 포함한다. source revoked면 `{redacted:true,score,total,submitted_at}`만 반환한다. answer/review data를 가진 `AdminQuestionDTO`는 별도 admin API에만 존재한다. pre-submit API/HTML/bundle/source map/cache에서 금지 field와 canary text를 검색한다.

## 문항 정정

challenge는 본인의 submitted item에만 연결하고 제한 길이 reason만 받는다. admin quarantine은 새 전달을 즉시 중단한다. 오류 확정은 observation에 `void_reason`/`correction_id`를 기록하고 유효 observation으로 Memory를 재계산하는 idempotent job을 만든다. 기존 answer와 원점수는 보존한다. correction result는 original/revised score, valid item count, reason, impact를 표시하며 유효 8개가 깨지면 `pass_status=invalidated`와 재평가 CTA를 준다. 분모를 줄여 6/8 기준을 재해석하지 않는다. source revocation redaction이 우선한다.
