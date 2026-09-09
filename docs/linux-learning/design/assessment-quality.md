# 문항 정확성과 공개 기준

> 공개용 정제본이다. 실제 사설 문항·원문 인용·검토자 식별자는 포함하지 않는다.

검토용 기준문항은 설계 fixture이며 `needs_human_review` 상태다. model이 생성·검증을 마쳤다는 이유만으로 승인 상태를 만들지 않는다. 개발 preview는 검토용임을 표시하고 실제 평가·Memory 숙련도 갱신에서 제외한다.

## 평가 흐름

source section 읽기 → concept 설명·비채점 회상 → 모든 필수 section 완료를 server가 확인 → 단원 평가 준비 자동 요청 → server 범위 고정·생성 → 구조 검사 → 근거 검사 → 독립 풀이·반례 검사 → 검토 대기/승인 문항 제공 → 응답 제출 → server 채점 → 정답 및 네 보기 해설 → 오개념별 source 복습 → 새 변형 문항 재평가 순서다.

## 생성 입력 계약

- server가 `unit_id`, 완료한 `section_id`/`concept_id`, source revision/hash, 환경 scope, 문항 수, 인지수준 분포를 결정한다. client의 완료·승인값을 신뢰하지 않는다.
- RAG는 승인 source snapshot과 허용 concept 집합으로 제한한다. 관련 단어가 있다는 이유로 미학습 concept을 넣지 않는다. 미래 단원 preview·cheat sheet·학습목표만 있는 부분은 설명 근거가 아니다.
- 각 문항은 한 primary concept, 보기 4개, 정답 1개를 가진다. 각 오답은 실제 오개념 하나와 연결하고 보기별 이유와 immutable source anchor를 보관한다.
- “모두 정답”, “정답 없음”, 복수 사실을 묶은 보기, 길이·문법·반복어로 정답을 암시하는 보기는 금지한다.
- 가정이 답을 바꾸면 환경, 사용자 권한, 추가 접근제어, 현재 directory, 파일 존재, 표준 stream 초기 연결 등을 stem에 쓴다. 배우지 않은 예외를 함정으로 쓰지 않는다.
- 근거 부족은 `insufficient_evidence`, 교육 승인 부족은 `review_pending`으로 대기한다. 8문항을 줄이지 않고 model 일반지식으로 빈 source를 채우지 않는다. 검증된 보강자료를 학습 section으로 공개한 뒤에만 해당 concept을 허용한다.

## 독립 검증과 차단

1. schema, ID reference, duplicate option, answer 포함, 보기 수 4, source hash, 허용 concept 부분집합, 모든 보기 explanation, 승인 상태를 결정적으로 검사한다.
2. source anchor 존재와 정확한 근거 연결을 검사한다. 출처 존재만으로 의미 정확성이 보장되지는 않는다.
3. 별도 context reviewer에게 answer key 없이 stem·options·허용 evidence를 주고 독립 answer, 보기별 참/거짓/조건부, 두 번째 정답 가능성, 숨은 가정, 범위 초과를 structured result로 받는다.
4. 생성 answer와 독립 풀이가 다르거나 조건부로 둘 이상 참이면 quarantine한다. model 두 응답의 합의가 사람 검토를 대체하지 않는다.
5. 사람 reviewer는 근거/정답/오답/난도/미학습 concept 없음/환경조건을 확인한다. 승인은 `question_revision`, `content_hash`, `source_revision`, reviewer, 시각에 결합한다.
6. 첫 운영 release의 모든 전달 문항은 사람이 확인한다. 자동 공개는 별도 quality 평가와 운영정책 승인이 필요하다.

## 반드시 보강하거나 조건을 명시할 영역

- `fork → exec → wait`는 외부 명령의 대표 흐름이며 모든 shell 명령의 보편 순서가 아니다. `exec`는 새 PID가 아니라 process image를 바꾼다.
- 현재 shell의 working directory를 바꾸는 `cd`와 별도 child의 `chdir` 효과를 구분한다.
- `SIGTERM`은 정리 완료를 보장하지 않고 process가 처리·차단·무시할 수 있다. `SIGKILL`과 구분한다.
- load average를 CPU 사용률 또는 단독 장애 판정으로 사용하지 않는다.
- 권한 문제는 ordinary user, 경로, directory `w+x`, owner, capability/ACL/SELinux 조건을 명시한다.
- name-service 조회를 DNS-only 검사로 단정하지 않는다.
- network error는 다음 조사 방향이지 단일 root cause 증명이 아니다.
- system service의 active와 enabled를 구분하고 예외를 배제하는 보편 명제를 만들지 않는다.

외부 공식 근거로 교재 오류를 보완하더라도 자동으로 이미 배운 내용으로 취급하지 않는다.

## 채점·해설·복습

정답은 문제 화면 DOM, 초기 API payload, client bundle에 넣지 않는다. server가 저장한 immutable question version과 `answer_option_id`로 채점하며 제출 전에는 explanation을 반환하지 않는다. shuffle은 opaque ID를 유지하고 표시 순서만 저장한다. 중복 submit은 attempt ID로 멱등 처리한다.

결과 explanation에는 정답 이유, 선택한 오답의 misconception, 나머지 오답 이유, concept ID, versioned source anchor, 다음 recall prompt를 포함한다. challenge만으로 문항이나 Memory를 바꾸지 않는다. 관리자가 오류를 확정하면 그 revision을 철회하고 해당 observation만 void한 뒤 Memory를 재계산한다. 원래 answer와 correction record는 보존한다. 유효 8문항 조건이 깨지면 pass를 invalidated하고 새 승인 문항으로 재평가한다.

Memory에는 user별 concept state, attempt/question/source revision, 선택, 선택적 confidence, due date를 저장한다. LLM 대화 summary를 answer 근거나 승인 증거로 쓰지 않는다. section completion은 score/mastery 대체값이 아니다.

## 검증 목표

출시 전 전달 문항의 사람 승인 100%, evidence 연결 100%, answer 유일성 100%, 범위 초과 0, source 수정 뒤 이전 승인 제공 0을 확인한다. 이는 목표이며 현재 달성 보고가 아니다.
