# P00 구현 결정 기록 — 공개용

## 결정 index

| ID | 결정 | 적용 phase |
|---|---|---|
| `PROD-001` | invitation-only 7-unit Korean Linux flow | P01–P08 |
| `ASM-001` | 8 questions, 6/8 threshold, 2/4/2 blueprint | P03–P08 |
| `ASM-002` | insufficient/unapproved bank는 partial assessment 대신 safe wait | P03–P06 |
| `EDU-001` | first release의 모든 delivered question은 human review | P04–P08 |
| `SRC-001` | raw source, derivative content, immutable course version 분리 | P02–P08 |
| `SRC-002` | access active/stale/revoked와 24-hour maximum age | P02–P08 |
| `ELIG-001` | evidence/learning/prerequisite closure에 따른 eligibility | P02–P06 |
| `MEDIA-001` | unreviewed image는 text를 막지 않지만 question evidence 금지 | P02–P08 |
| `API-001` | learner attempt/result/admin DTO 분리와 pre-submit answer 비노출 | P01/P05/P06 |
| `AUTH-001` | same-origin BFF, server session, CSRF, membership/ownership | P01–P08 |
| `MEM-001` | structured per-user concept Memory와 deterministic grading | P05–P08 |
| `ENV-001` | local/test fake와 staging/production live fail-closed 분리 | P01–P08 |
| `LIMIT-001` | generation/review/retry/cost finite limit | P04/P06–P08 |
| `DATA-001` | type별 retention/deletion policy | P01–P08 |
| `DR-001` | initial RPO≤24h, RTO≤4h | P07–P08 |
| `DEP-001` | live account/source/domain/model 미정값은 deploy blocker | P07–P08 |

## 환경 설정 matrix

| 환경변수 | local/test | staging/production | 부재·불일치 처리 |
|---|---|---|---|
| `APP_ENV` | 실행 명령이 `local` 또는 `test` 명시 | manifest가 `staging` 또는 `production` 고정 | 누락/알 수 없는 값이면 시작 실패 |
| `PROVIDER_MODE` | `fake`만; UI/admin에 모의 표시 | `live`만 | production의 fake/혼합은 시작 실패 |
| `DATABASE_URL` | 격리 local Postgres | 환경별 Secrets Manager 값 | 필수, 환경 간 재사용 금지 |
| `APP_ORIGIN` | 명시된 local same origin | 정확한 HTTPS origin, wildcard 금지 | callback/Origin과 다르면 시작 실패 |
| `NOTION_TOKEN` | 없어야 동작 가능; fixture read-only | worker secret 필수 | live 부재 실패; browser/log 금지 |
| `AWS_REGION` | fake provider는 요구하지 않음 | project config region과 정확히 일치 | live 부재/불일치 실패 |
| `BEDROCK_GENERATION_MODEL_ID` | deterministic fake ID | 실제 접근 가능 config ID | live 미검증/불일치 실패 |
| `BEDROCK_VERIFICATION_MODEL_ID` | 생성 fake와 분리된 fake ID | 독립 검토용 실제 config ID | 생성 ID와 역할 분리, 무단 대체 금지 |
| `BEDROCK_EMBEDDING_MODEL_ID` | deterministic fake embedding | 실제 config ID와 dimension 확인 | 변경 시 별도 index 재색인 후 전환 |
| `COGNITO_USER_POOL_ID` | fake auth에는 사용하지 않음 | 환경별 pool 필수 | live 부재 실패 |
| `COGNITO_CLIENT_ID` | fake auth에는 사용하지 않음 | 환경별 client 필수 | live 부재 실패 |
| `SQS_GENERATION_QUEUE_URL` | 외부 접속 없는 DB queue adapter | 환경별 실제 queue URL | live 부재 실패 |
| `CONTENT_BUCKET` | private local storage mount | private S3 bucket | public/환경 불일치 실패 |
| `TOKEN_ENCRYPTION_KEY` | test 전용 key, 운영과 분리 | secret manager의 환경별 key | config/browser/log에 두지 않음 |
| `SOURCE_ACCESS_MAX_AGE_HOURS` | 기본 24, fake clock | 기본 24 | 더 긴 값은 policy revision 없이는 거부 |
| `GENERATION_MAX_DRAFT_ROUNDS` | 3 | 3 | 무제한/0/음수 거부 |
| `GENERATION_MAX_PROVIDER_CALLS` | 6/job | 6/job | 재시작으로 초기화 금지 |
| `GENERATION_JOB_TIMEOUT_SECONDS` | 600 | 600 | 첫 실행부터 누적 deadline |
| `GENERATION_MAX_TOTAL_TOKENS` | 60000/job 합성 사용량 | 60000/job input+output | 호출 전 예약, 초과 전 호출 중지 |
| `GENERATION_MAX_JOB_USD` | 1.00 합성 비용 | 1.00/job | 가격/사용량 미상 시 호출하지 않음 |
| `MODEL_DAILY_BUDGET_USD` | 5.00 합성 원장 | 5.00/UTC day/environment | 생성·검토·embedding·retry 공유 |

`.env.example`은 비밀이 아닌 이름과 안전한 local 기본값만 포함한다. 실제 secret은 example, project config, progress, artifact, log에 기록하지 않는다.

local fake는 환경에 실제 token이 우연히 있어도 Notion/AWS/Cognito/SQS network adapter를 호출하지 않는다. fake 오류를 live fallback으로, live 오류를 fake success로 바꾸지 않는다. fake identity는 서로 다른 learner 2명과 admin 1명을 제공하고 private fixture mount와 DB queue adapter를 사용한다. live adapter interface와 fake response 구현은 실제 provider 연결 증거와 구분한다.

## 실행·비용 상한

retry transport와 correction이 동일한 call/time/token/cost budget을 공유한다. 먼저 도달한 limit이 우선하며 independent review call 여유가 없으면 ready가 될 수 없다. persistent ledger는 worker restart로 초기화되지 않는다. permission/evidence/schema/educational failure는 transport retry 대상이 아니다. poll은 2초에서 exponential backoff하여 최대 30초, 화면 자동 poll은 5분 뒤 멈추고 manual check를 제공한다.

## 보존·삭제·복구

source/media/embedding은 use right가 유효한 기간에만 보유하고 confirmed revocation 즉시 delivery/generation을 막는다. session/token은 revoke 즉시 unusable, expiry 뒤 7일 내 제거한다. progress/attempt/answer/Memory/idempotency는 account 유지 중 보존하고 valid deletion request 뒤 30일 내 live user linkage를 제거한다. operational log 30일, audit 90일, backup 7일을 초기값으로 한다. legal/operational review가 이 초기값을 production 전에 확정한다.
