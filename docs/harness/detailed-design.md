# `phase-harness` detailed design

## Purpose and boundary

`phase-harness` is a Python-standard-library runner for ordered software
phases. It makes a narrow execution policy concrete: one implementation role,
then one independent verification role. It is not a general agent scheduler,
CI system, deployment engine, or automatic repair loop.

The package requires Python 3.11 or newer on Linux or macOS because it uses
`fcntl.flock`. Actual role execution also requires an installed and
authenticated Codex CLI. The runner does not change global Codex settings or
permissions.

## Fixed role contract

The configuration must contain exactly these roles:

| Role | Model | Reasoning | Mutation boundary |
|---|---|---|---|
| `implement` | `gpt-5.6-sol` | `medium` | May change project implementation files |
| `verify` | `gpt-6-astra` | `high` | May change only the phase verification report |

Each Codex subprocess runs with plugins disabled, a structured-output schema,
the project as its working directory, and a timeout from the project
configuration. There is no design role, Gemini/AGY call, review/rework loop,
or automatic retry.

The implementation and verification prompts include the phase instruction,
mandatory check names, current input fingerprint, and prior blocker. The
verifier is explicitly told that product, source, design, tests, and
dependencies are read-only.

## Project configuration

The runner reads `orchestration.json` and `progress.json` from the selected
project root. Configuration schema version 2 requires:

- a private state directory below `.orchestrator/`;
- a bounded timeout from 60 through 14,400 seconds;
- the exact fixed role/model/reasoning pairs above;
- one or more ordered phases with unique IDs;
- a project-relative instruction and verification-report path per phase;
- nonempty named fingerprint groups;
- nonempty mandatory-check lists for both roles; and
- dependencies that refer only to earlier phases.

Paths must be project-relative and may not contain `..`. The example in
`examples/orchestration.json` is synthetic and must be adapted to the target
project.

## Runtime components

`phase_harness/cli.py` parses commands, initializes progress, and selects the
normal, repair, verification-retry, or migration path. `phase_harness/core.py`
owns validation, fingerprinting, locking, execution, receipts, progress
updates, and legacy import. `agent-result.schema.json` defines the JSON shape
requested from each role.

The executor is injectable. Production use starts a Codex subprocess in a new
process session. Tests use a fake executor, which makes the state machine and
guards testable without model calls.

## Progress and locking

Initial progress records every configured phase as `pending`, with zero
attempts, no runs, no input fingerprints, and no blocker. The phase order in
progress must exactly match configuration order.

The runner takes a nonblocking advisory lock at
`.orchestrator/v2/runner.lock`. A second runner fails instead of racing.
Progress writes use a temporary file, `fsync`, atomic replacement, and a
directory `fsync`. This protects each write from partial replacement; it is
not a distributed lock or transactional database.

## Fingerprints and protected content

Each configured fingerprint group is expanded recursively. The runner hashes
every selected regular file, then hashes the sorted path-and-content-digest
manifest for each group and for the combined input. Missing selected paths and
selected symlinks fail closed.

The default exclusions cover VCS metadata, harness state, caches, dependency
trees, common build output, `.env*`, common private-key suffixes, and a small
set of generated files. Projects may add ignored directory and file names.
Markdown and JSON are ordinary inputs unless the project omits them from its
groups.

For verification, the runner also snapshots the project tree before and after
the role. The configured verification report is the only permitted changed
path. Any other addition, deletion, or content change blocks the phase. The
input fingerprint must also remain unchanged.

This is a content-integrity boundary, not a security sandbox: ignored files,
external systems, and process side effects are outside the snapshot.

## Evidence layout

Each attempt creates a unique directory below
`.orchestrator/v2/<phase>/`. It stores:

- the exact prompt;
- the grouped input manifest and hashes;
- stdout and stderr;
- the structured result;
- a receipt with exact argv, model, reasoning effort, timestamps, exit and
  timeout status, hashes, input/config/instruction identity, and final
  pass/block decision; and
- for verification, a copy of a pre-existing verification report before it is
  replaced.

`progress.json` links to each receipt. The harness state directory is excluded
from product-tree snapshots so recording evidence does not itself invalidate
verification.

A role passes only when the process exits zero, the result says `passed`, the
blocker list is empty, no reported check is failed or not run, every mandatory
check appears as passed, and no harness integrity error occurred. The runner
records what the role reports; it does not independently understand whether a
named test command was scientifically sufficient.

## Deployment guard

A phase marked `deployment: true` requires both `--allow-deploy` and at least
one configured dotted path under `deployment_config_paths`. Every configured
value must exist and be nonempty in `project.config.json` before the role is
started.

This is an operator-intent and configuration-presence guard. It does not
authenticate a cloud account, validate permissions, estimate cost, or approve
a destructive plan; phase checks must do that work.

## Failure and recovery semantics

Normal execution stops at the first blocked phase or role failure. If a prior
process left a phase as `implementing` or `verifying`, the next normal run
marks it blocked and requires explicit recovery. The runner never silently
replays an interrupted process.

`--repair PHASE` is allowed only for a blocked phase and runs one new
implementation attempt using the recorded blocker. A successful repair returns
the phase to `ready_verify`; it does not skip independent verification.

`--retry-role verify --phase PHASE` runs one new verification attempt only
when an implementation fingerprint exists and the phase is blocked or already
ready to verify. Both recovery commands are operator-selected one-attempt
actions; repeated invocation remains possible and is not an automatic loop.

## Legacy import

`--migrate-legacy` can import one legacy phase into `ready_verify` or
`completed`:

- `ready_verify` requires an exit-zero, blocker-free implementation receipt,
  a result consistent with any neighboring `result.json`, a snapshot whose
  hash matches the receipt, and exact comparison of explicitly selected
  baseline roots. Additions, deletions, and changed bytes are detected.
- `completed` requires an exit-zero, blocker-free verification receipt and
  fingerprints the current configured inputs.
- imports require a `pending` target phase and never rewrite the legacy
  receipt.

Authorized-path exclusions are an explicit migration escape hatch and should
be kept narrow. Legacy import validates the fields implemented by the adapter;
it cannot recreate missing historical execution evidence or prove that an old
check was adequate.

## Current limitations

- Configuration validation is implemented in Python, not by a published JSON
  Schema.
- The result schema is supplied to Codex, while the harness performs its own
  focused semantic checks after execution.
- Locking is local-host only.
- Tree comparison excludes configured ignored content and cannot observe
  external side effects.
- Receipt hashes provide integrity context but are not signatures or remote
  attestations.
- There is no automatic replay of interrupted or failed roles, retry budget,
  remote queue, dashboard, or deployment provider integration. A normal run
  does continue an intact `ready_verify` phase with verification.
