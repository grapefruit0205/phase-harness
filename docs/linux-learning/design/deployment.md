# 배포 및 운영

> 공개용 정제본이다. 계정·도메인·provider ID·credential·실제 plan 식별자는 포함하지 않는다.

## 환경과 완료 경계

local은 fixture/fake provider와 DB queue로 시작한다. P00–P06은 실제 source/AWS credential 없이 개발·검사한다. 사설 source snapshot을 public Git, container image, UI bundle에 포함하지 않는다. test fixture는 runtime seed와 분리하고 build context에서 private source, credential, agent log를 제외한다.

staging/production은 별도 Terraform state/DB/S3/Cognito/secret/domain을 사용한다. account 분리를 권장하며 단일 account면 IAM/name/network/state 경계를 강제한다. 두 환경 모두 invitation과 course membership을 적용하고 fake 설정은 시작 실패다.

필수 live 설정은 AWS account/region, 환경별 domain/DNS 권한, 사용 가능한 generation/review/embedding model ID, source token/allowlist permission, deploy credential이다. null은 local 완료를 막지 않고 deployment blocker로 남긴다. secret은 environment/Secrets Manager에만 저장한다. embedding model/dimension 변경은 별도 index를 재색인·검증한 뒤 전환한다.

## Infra 결정

CloudFront private S3 origin은 OAC로 제한한다. viewer certificate와 service-region ALB certificate를 provider alias로 구분한다. `/api/*`, `/auth/*`는 HTTPS ALB와 cache-disabled policy를 사용하며 Cookie/CSRF/Origin/redirect query를 보존한다. ALB direct access를 origin-facing 범위/secret으로 제한하고 app auth도 유지한다.

ECS와 RDS는 private subnet에 둔다. ALB/NAT와 최소 두 AZ subnet을 계획하고 source egress 비용을 포함한다. production RDS는 Multi-AZ, deletion protection, encryption, PITR, backup ≥7일을 기본으로 한다. staging의 축소 posture는 명시한다. 초기 RPO≤24h/RTO≤4h는 목표이며 실제 restore 결과로 판정한다.

Terraform state는 별도 bootstrap으로 만든 encrypted/versioned/public-blocked remote store와 lock을 쓴다. bootstrap을 같은 initial state와 순환 참조하지 않는다. code/image는 lockfile/digest로 고정하고 CI는 OIDC short-lived role, ECS는 least-privilege task role을 쓴다. API와 worker permission/secret을 분리하며 RDS는 public이 아니다.

## Staging gate

명시적 deploy 허용과 완전한 config 없이는 apply하지 않는다.

1. caller identity와 config account/region, DNS 통제, source 접근, 실제 소량 generation/independent-review/embedding dimension/quota를 확인한다. model을 추측·무단 대체하지 않는다.
2. `terraform fmt/validate/plan`, image scan/build, migration plan을 수행한다. resource, monthly cost, egress, multi-AZ, deletion protection, log retention, model budget, plan identity를 deployment plan에 기록한다.
3. 저장된 plan을 target account에 적용한다. plan 뒤 code/config 변경 시 재계획한다. migration은 one-shot task로 끝낸 뒤 API/worker를 배포한다.
4. DNS/TLS, admin invitation, course membership을 설정한다. 실제 source text/asset 수집, model 후보, human review UI, 승인 뒤 assessment E2E를 수행한다. local seed는 운영 승인이 아니다.
5. user isolation, CSRF, auth expiry/logout, private asset unauthorized access, revocation, media failure, worker duplicate/retry/DLQ, bank shortage→review_pending→approval→ready를 확인한다.
6. error/latency/DB/outbox/queue/DLQ/rejection/cost/media alert를 만들고 실제 test notification을 확인한다. source/answer/token/full prompt를 log하지 않는다.

## Production gate

P06 local 검증과 staging live integration이 통과해야 한다. 모든 제공 unit은 8-item blueprint의 human-approved bank를 가진다. 변경 question version은 재승인한다. fixture, model self-review, schema 검사를 교육 승인으로 취급하지 않는다. `human_review_required`, `allow_public_signup=false`를 유지한다.

release identity는 image digest/commit/migration/source version/question bank/prompt/model ID다. migration은 expand/contract로 적용한다. 실패 시 이전 image digest로 전환하며 destructive down migration을 자동 실행하지 않는다. production-equivalent migration과 old-app compatibility, snapshot/PITR restore 뒤 smoke를 staging에서 먼저 검증한다.

운영 URL/TLS, invited real-account E2E, unit별 교육 검토, model/infra 비용 제한, restore 소요와 data point, rollback, alert receiver를 evidence로 남긴다. 미충족이면 blocked이며 deploy-ready code와 실제 production 완료를 구분한다.

## 운영 인계

runbook은 incident, queue replay, 비용 초과 generation stop, model outage waiting, key rotation, rollback, admin recovery, source revocation을 포함한다. source authorization은 기본 24시간 내 성공해야 하며 명시 철회는 즉시 차단한다. detection delay와 stale fail-closed를 문서화한다.

초기 보존안은 source derivative는 license 유효 기간, expired session은 7일 이내 삭제, log 30일, audit 90일, account data는 계정 유지 중 보존 후 삭제 요청 30일 이내 live 제거다. backup 반영은 최대 backup 수명 7일 뒤이며 restore 시 deletion tombstone을 재적용한다. 실제 법률/운영 요구로 배포 전에 확정한다. export는 본인 progress/result만 포함하고 source 재배포 export는 기본 비활성이다.
