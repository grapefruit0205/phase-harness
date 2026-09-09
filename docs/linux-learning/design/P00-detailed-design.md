# P00 상세 설계 — 기반 계약과 원문 감사

> 실제 작성된 P00 설계의 공개용 정제본이다. private source locator/text, 실행 namespace, receipt/hash, role history, audit log는 제외했다. 이 설계는 제품 구현·교육 승인·배포 완료 판정이 아니다.

## 입력과 경계

제품·교육·architecture·data/API·deployment 문서, curriculum/source/media manifest와 검토용 question fixture를 함께 읽는다. 기존 사용자 file과 실행 증거를 보존한다. source snapshot은 untrusted data이며 내부 command나 instruction을 실행하지 않는다. AWS credential 없이 진행하고 source 원본을 자동 수정하지 않는다.

## 제품·교육 계약

첫 release는 invitation-only Korean Linux course다. 7 unit과 16 required section의 순서를 유지하지만 Day를 deadline으로 해석하지 않는다. section completion은 progress일 뿐 mastery가 아니다. 마지막 required section 완료 transaction이 user/unit/source-version별 initial assessment request를 멱등 생성한다.

unit/review assessment는 정확히 8개 distinct approved question version이며 target blueprint는 recall 2, concept distinction 4, bounded scenario 2다. progression threshold는 6/8이지만 mastery/professional certification과 구분하고 required concept 오답은 별도 review한다. 정확히 4 options, 1 answer, answer와 모든 distractor의 reason/evidence, immutable unit/concept/source/question link를 요구한다.

bank가 8개/2-4-2/human approval을 충족하지 못하면 `review_pending` 또는 `insufficient_evidence`로 기다린다. 문항 수를 줄이거나 unverified candidate를 섞지 않는다. first operational release의 모든 delivered question은 human educational review를 요구한다.

## Source version·근거 설계

raw collected bytes와 sanitized/supplemented learner derivative를 분리한다. source version semantic hash는 course, ordered page/block content hash, curriculum revision, supplement revision, delivered media content hash/mapping, importer/transformer version에 결합한다. signed URL, collection time, transient retry metadata는 제외한다.

candidate version은 `staging → active → retired`로 이동하고 course마다 active는 최대 하나다. 수집 전후 edit metadata가 바뀌면 bounded recollect하고 mixed version을 activate하지 않는다. new assessment/question은 active version만 사용하며 accessible retired version의 existing in-progress attempt만 완료할 수 있다. source version 변경은 question approval을 자동 승계하지 않는다.

effective question scope는 다음 교집합과 prerequisite closure다.

```text
unit allowlist
∩ fixed source version에서 학습 완료
∩ evidence-ready
∩ publication-approved
− blocked concepts
```

근거가 부족한 concept과 그 근거를 prerequisite로 쓰는 downstream concept은 reviewed supplement가 새 learnable source revision에 포함되고 실제 학습될 때까지 차단한다. supplement는 source, author/reviewer, evidence, affected concept, approval을 기록한다.

## Media 설계

검토 대기 또는 failed image는 text version activation을 막지 않지만 essential question evidence가 될 수 없다. live download는 allowlisted source/page/block/file, HTTPS host, redirect별 DNS/IP, size/MIME/decode/hash를 검사한다. SVG/HTML 원본을 app origin에서 실행하지 않고 isolated conversion과 visual review를 통과한 raster만 authenticated proxy로 제공한다. signed URL과 public bucket URL을 browser/API/log에 노출하지 않는다.

## Answer 비노출·인가·Memory

pre-submit learner DTO는 attempt/unit/source ID, state, item ID/ordinal/stem, four opaque option ID/text, selected option만 포함한다. answer/correctness/explanation/source quote/rubric/reviewer/model/prompt metadata는 API, HTML, JS/CSS, source map, prefetch/cache/storage, analytics, log, error에 없다. submit은 fixed question version을 server-side로 결정적 채점한다.

same-origin BFF는 code+PKCE를 처리하고 provider token은 encrypted server storage에 둔다. browser에는 secure HttpOnly host-only session cookie만 제공한다. 매 요청 server DB role, course membership, entity ownership, source access를 검사하고 mutation은 session-bound CSRF+exact Origin을 요구한다.

Memory는 `user + concept + immutable observation + misconception count + estimate + due_at + algorithm_version` 구조다. LLM conversation memory는 grading/mastery/isolation의 authority가 아니다. same item replay는 새 mastery evidence가 아니며 withdrawn question observation은 void한 뒤 valid observation으로 deterministic recompute한다.

## Environment·비용·보존

local/test는 `PROVIDER_MODE=fake`, staging/production은 `live`만 허용하며 혼합/fallback은 시작 실패다. source/model/auth/queue/storage/token-encryption 설정은 process별 least privilege로 분리한다. 기본 generation limit은 initial draft 1 + correction 최대 2, provider call 최대 6/job, 누적 600초, total token 60,000/job, 1 USD/job, 5 USD/day/environment, user 새 요청 5/hour, worker concurrency 2다. external call exactly-once를 주장하지 않고 persistent ledger가 retry에도 같은 limit을 적용한다.

source access는 last success 24시간 안에서만 transient failure grace를 허용한다. 확인된 403/404/delete/revocation은 즉시 `revoked`, 24시간 초과 transient 상태는 `stale`로 content/asset/generation/assessment를 fail closed한다.

초기 retention은 source derivative는 license 기간, session은 expiry/revoke 뒤 7일 내 제거, log 30일, audit 90일, user-linked data는 deletion request 뒤 30일 내 live 제거다. backup은 최대 7일 뒤 반영하고 restore 때 deletion tombstone을 재적용한다. RPO≤24h/RTO≤4h는 production 전 restore drill로 검증할 목표다.

상세 제품 결정은 [P00 결정 기록](P00-decisions.md)에 정리한다.

## 산출물과 검증 gate

private source audit, 이 detailed design, decision register를 만든다. 검증은 17 source page, 16 section, 7 unit, 40 image mapping/hash, 33 concept reference, 검토용 8문항의 option/answer/evidence/scope/non-approved state, specification conflict와 deployment blocker ownership을 확인한다. private audit 자체는 공개하지 않는다.
