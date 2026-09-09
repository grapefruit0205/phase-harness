# Phase workflow

## State machine

```text
pending
  └─ implement ──pass──> ready_verify
         │                   └─ verify ──pass──> completed
         └─fail                         └─fail
             └───────────────────────────> blocked

implementing/verifying left by interruption
  └─ next normal run ──> blocked

blocked --repair PHASE──> implementing ──pass──> ready_verify
blocked/ready_verify --retry-role verify──> verifying ──pass──> completed
```

An implementation pass stores the post-implementation input fingerprint.
Verification starts only if the freshly calculated fingerprint is identical.
Dependencies must already be `completed` before any role or recovery attempt.

## Operator flow

1. Copy and adapt `examples/orchestration.json` in the target project.
2. Create the referenced phase instructions, design inputs, source fixtures,
   tests, and verification-report parent directories.
3. Initialize once:

   ```console
   python -m phase_harness --project /path/to/project --init
   ```

4. After configuring P01 through P03, for example, inspect the next actions
   without running roles (the bundled example itself declares only P01):

   ```console
   python -m phase_harness --project /path/to/project --dry-run --through P03
   ```

5. Run in order. The command stops immediately on failure:

   ```console
   python -m phase_harness --project /path/to/project --run --through P03
   ```

6. Read `progress.json`, the referenced receipt, streams, result, and
   verification report. Correct a failed implementation explicitly or repeat
   only verification when the implemented input is still valid:

   ```console
   python -m phase_harness --project /path/to/project --repair P03
   python -m phase_harness --project /path/to/project --retry-role verify --phase P03
   ```

Do not manufacture completion by editing progress or deleting the lock/state
history. A blocked phase is useful evidence, not disposable noise.

## Writing a phase instruction

A reusable phase instruction should be concrete about product scope and leave
the fixed execution mechanics to the harness. For example:

```markdown
# P03 — Feature name

Prerequisite: P02.

## Inputs

Read the product contract, current architecture, relevant existing code and
tests, the prior phase verification report, and this instruction.

## Implementation scope

- Deliver one bounded user-visible capability.
- Preserve the stated authorization and data-integrity invariants.
- Add focused regression and negative tests.

## Outputs

- Product code and tests in the project-owned paths.
- Verification report at the configured report path (verifier only).

## Required gates

- `unit-tests`: deterministic unit suite passes.
- `integration-tests`: boundary behavior and negative cases pass.
- `artifact-check`: no secret or private source appears in public output.

## Stop conditions

Stop and return a blocker if required input is absent, a mandatory check was
not run, an authorization boundary cannot be verified, or an external action
requires operator approval that has not been granted.
```

Then map the exact mandatory result names and meaningful input groups in
`orchestration.json`. A phase document should not claim tests passed; the
implementation result and independent verification receipt carry that claim.

## Recovery decision guide

| Observation | Operator action |
|---|---|
| Implementation failed or verifier found a product defect | Inspect evidence, then `--repair PHASE` once |
| Verification process/report failed but implementation is unchanged | `--retry-role verify --phase PHASE` once |
| Fingerprinted inputs changed after implementation | Re-establish the intended input, or repair and re-verify |
| A running state remains after interruption | Run normally once to record the block, inspect it, then choose repair/retry |
| Deployment settings or explicit authorization are absent | Supply them deliberately; do not bypass the deployment guard |
| Configuration/progress shape is invalid | Correct the project-owned configuration with history preserved |

The harness does not choose among these on the operator's behalf.

## 재사용 가능한 시작 prompt

```text
프로젝트의 AGENTS.md, README/START_HERE, orchestration.json,
progress.json, 현재 phase 문서와 관련 design을 먼저 읽어라. 설정된 phase를
선택한 단계까지 순서대로 실행하라. 구현은 gpt-5.6-sol medium 1회, 독립
검증은 gpt-6-astra high 1회만 사용한다. Gemini/AGY나 별도 design role,
자동 review/rework/retry loop를 추가하지 마라. 실패·중단 시 즉시 멈추고
evidence와 blocker를 보존하며, 명시적인 repair 또는 verify retry 없이는
역할을 재실행하지 마라. 필수 check를 실제 실행하지 않았으면 passed로
기록하지 마라.
```
