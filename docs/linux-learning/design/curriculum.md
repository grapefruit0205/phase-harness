# Linux 7단원 학습·평가 설계

> 공개용 정제본이다. stable concept ID와 교육 계약은 보존했지만 사설 source URL/ID, exact heading, 원문 excerpt, asset은 제거했다. runtime은 각 concept을 course-scoped immutable source anchor에 연결한다.

사설 source의 7단계 순서를 7개 unit, 16개 필수 section, 33개 concept으로 유지한다. Day는 deadline이 아니다. source system은 원본이고 별도 web service가 assessment, grading, review를 담당한다.

각 section은 concept 설명 → 자기 설명 → 비채점 짧은 회상 순서다. 모든 필수 section의 current source version completion을 server가 확인하면 8문항 평가 준비를 자동 요청한다. blueprint는 recall 2, concept distinction 4, bounded application 2다. 승인 bank가 부족하면 `review_pending` 또는 `insufficient_evidence`로 대기하며 문항 수를 줄이지 않는다.

## unit-01 · 전체 구조와 시작점

선행 unit: 없음.

- `linux.u01.roles` — kernel의 resource 관리와 shell의 command 해석을 구분한다. misconception: shell이 CPU/memory를 직접 관리한다.
- `linux.u01.spaces` — 사용자 program과 kernel space를 구분한다. prerequisite: `linux.u01.roles`. misconception: system manager program 자체가 kernel이다.
- `linux.u01.boot` — systemd 기반 환경에서 kernel 뒤 PID 1이 service/login 환경을 시작하는 흐름을 설명한다. 모든 Linux에 일반화하지 않는다.
- `linux.u01.login` — console과 SSH의 인증 뒤 interactive user shell 흐름을 비교한다. forced command/SFTP는 scope 밖이다.
- `linux.u01.syscall` — file read를 user program의 kernel request 흐름으로 설명한다. 실제 syscall 전체 순서를 단정하지 않는다.
- `linux.u01.shell_env` — `SHELL` variable만으로 현재 실행 shell을 확정할 수 없음을 설명한다.
- `linux.u01.evidence` — 관찰값·해석·다음 확인을 나누어 기록한다. command 실행 자체를 원인 증명으로 보지 않는다.
- `linux.u01.views` — 실행·권한·파일·입출력·network/service 관점을 구분한다. 초급 범위 밖의 세부 수치를 묻지 않는다.

## unit-02 · 명령 실행과 입출력

선행 unit: unit-01.

- `linux.u02.terminal` — terminal I/O 환경과 shell process를 구분한다. Bash interactive context를 명시한다.
- `linux.u02.commands` — command 종류와 current shell의 working directory 변경을 설명한다. 외부 실행 파일의 존재 가능성과 부모 shell cwd 효과를 혼동하지 않는다.
- `linux.u02.environment` — `export`, child environment, `PATH` search를 연결한다. child 변경이 parent에 자동 반영된다는 misconception을 교정한다.
- `linux.u02.process` — representative external command에서 fork/exec/wait의 역할을 구분한다. exec가 새 PID를 만든다고 가르치지 않는다.
- `linux.u02.foreground` — process ancestry와 terminal foreground process group을 구분한다. job control 조건을 명시한다.
- `linux.u02.signals` — `SIGTERM`의 처리 가능성과 `SIGKILL`의 포착 불가능성을 구분한다. 검토된 보강 section 학습 전에는 출제하지 않는다.
- `linux.u02.streams` — file descriptor 0/1/2와 stdout→stdin pipe를 설명한다. 일반 `|`가 stderr도 전달한다고 가르치지 않는다.
- `linux.u02.redirect` — redirection 순서에 따른 FD destination 차이를 추적한다. 초기 stdout/stderr 연결과 Bash 문법을 제시한다.

## unit-03 · 사용자와 권한

선행 unit: unit-02.

- `linux.u03.identity` — UID/GID와 policy에 따른 다른 사용자 실행을 구분한다. `sudo`가 언제나 root 성공을 뜻하지 않는다.
- `linux.u03.rwx` — file content permission과 directory entry/traversal permission을 구분한다. ordinary user, path, ownership, capability/ACL/SELinux 조건을 명시한다.
- `linux.u03.diagnose` — 실행 사용자 → 상위 path → file mode → 추가 policy 순서로 permission denial을 진단한다. `777`을 첫 해결책으로 쓰지 않는다.

## unit-04 · 파일시스템과 검색

선행 unit: unit-03.

- `linux.u04.mount` — storage device, filesystem, mount point를 구분한다. 모든 mount가 disk나 format을 요구한다고 단정하지 않는다.
- `linux.u04.paths` — absolute path와 cwd-relative path를 판별한다. 시작 cwd를 제시한다.
- `linux.u04.links` — same inode의 다른 name과 target path string을 구분한다. filesystem/regular-file 조건을 명시한다.
- `linux.u04.search` — live tree search와 indexed location DB freshness를 구분한다. 구현 환경을 명시한다.
- `linux.u04.actions` — 조건에 맞는 대상을 먼저 출력·검토한 뒤 action한다. delete 예시는 disposable directory에 한정하고 assessment service가 실행하지 않는다.

## unit-05 · 네트워크와 SSH

선행 unit: unit-04.

- `linux.u05.layers` — address, route, TCP listener, authentication의 확인 지점을 나눈다. 예시 port를 universal default로 단정하지 않는다.
- `linux.u05.names` — name-service switch 결과와 direct DNS 검증을 구분한다. reviewed supplement 학습 뒤에만 answer condition으로 쓴다.
- `linux.u05.evidence` — ping/TCP/service 성공이 각각 증명하는 범위를 설명한다. error를 단일 cause 증명으로 사용하지 않고 client/server/address/port/time을 제시한다.

## unit-06 · 서비스와 로그

선행 unit: unit-05.

- `linux.u06.units` — service manager의 unit definition, process, unit type을 구분한다. systemd context를 명시한다.
- `linux.u06.lifecycle` — current `active`와 boot-time `enabled`를 구분한다. socket/dependency/manual start 가능성을 지우지 않는다.
- `linux.u06.logs` — unit/boot/time filter로 journal 조사 범위를 좁힌다. permission/collection 조건 없이 log 부재 원인을 단정하지 않는다.
- `linux.u06.recovery` — status/log/config/port evidence로 최소 수정 뒤 functional re-test한다. `active`만으로 접속 성공을 단정하지 않는다.

## unit-07 · 통합 장애 복구와 총복습

선행 unit: unit-06.

- `linux.u07.hypothesis` — 정상·증상·evidence·single hypothesis·minimal change·re-test를 연결한다. 1–6 unit의 learned concept만 교차한다.
- `linux.u07.review` — weak concept과 next review date를 기록하고 immutable source anchor로 돌아간다. 읽음 상태와 mastery를 구분한다.

통합 평가는 1–6 unit의 필수 section 완료를 server가 확인한 뒤 준비한다. 33개 concept allowlist 중 실제 완료·evidence-ready concept만 사용하며 보강 대기 concept의 전이 dependency도 계속 차단한다.

## 평가 범위와 복습 mapping

server는 unit allowlist, learned concept, evidence-ready concept, prerequisite closure의 교집합으로 출제한다. `evidence_status=needs_supplement` 또는 blocked concept은 검토·승인된 보강 설명과 학습 이력 전까지 차단한다. allowlist 자체는 publication approval이 아니다.

각 question concept ID는 course-scoped immutable `source_version + source_anchor`로 돌아간다. distractor misconception을 복습 이유로 표시한다. source ID나 exact heading은 public metadata가 아니라 private authorized DB record다.

초기 review interval은 1/3/7일 heuristic이며 개인 최적치라고 주장하지 않는다. 최초 평가, explanation 직후 retry, delayed reassessment를 분리한다. invalid question이 확인되면 그 observation만 void한다.
