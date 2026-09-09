# phase-harness

`phase-harness` is a small, Python-standard-library runner for phased software
work. Each phase has exactly two roles: one implementation attempt followed by
one independent verification attempt. A failure stops the run; there is no
automatic review/rework loop.

The runner pins implementation to `gpt-5.6-sol` with `medium` reasoning and
verification to `gpt-6-astra` with `high` reasoning. It invokes Codex with
plugins disabled for each isolated role and does not change global Codex
configuration or permissions.

## Project files

Copy `examples/orchestration.json` to a project's root, adapt its synthetic
paths and checks, and initialize progress:

Prerequisites are Python 3.11+ on Linux or macOS (for `fcntl`) and an installed,
authenticated Codex CLI. Install with `python -m pip install .`, or run the
module directly from this checkout.

```console
python -m phase_harness --project /path/to/project --init
python -m phase_harness --project /path/to/project --dry-run --through P01
python -m phase_harness --project /path/to/project --run --through P01
```

Each phase moves through `pending -> implementing -> ready_verify -> verifying
-> completed`. Exact commands, prompts, streams, structured results, and input
fingerprints are written beneath `.orchestrator/v2`. `progress.json` is replaced
atomically while an advisory `flock` prevents concurrent runners.

An interrupted or failed run is never silently replayed. One explicit targeted
attempt is available:

```console
python -m phase_harness --project /path/to/project --repair P02
python -m phase_harness --project /path/to/project --retry-role verify --phase P02
```

Verification may only change the configured phase verification report. Any
other project mutation, changed input fingerprint, missing mandatory check, or
reported blocker fails closed. Deployment phases additionally require their
project-specific deployment check; use a check that validates explicit account,
region, destination, and operator authorization before any deployment action.

## Fingerprints

Every phase declares meaningful input groups, such as product runtime, tests,
dependency locks, source, current phase instructions, and existing design.
Entries are sorted and hashed by relative path plus content. Generated caches,
dependency trees, build outputs, common secret files, and private harness state
are excluded. Selected symlinks are rejected. Markdown and JSON are ordinary
inputs and are never blanket-ignored.

Harness/config identity and the exact phase instruction hash are stored
separately in each receipt. Changes to harness documentation do not themselves
reopen completed product phases.

## Legacy migration

The public API `import_legacy_phase` and `--migrate-legacy` command can import a
passed legacy implementation as `ready_verify`, but only after validating its
receipt/result, snapshot digest, and exact current baseline including additions,
deletions, and changed content. A legacy verified phase can be imported as
`completed` from a completed, exit-zero, blocker-free verification receipt.

## Testing

```console
python -m unittest discover -s tests -v
```

There are no runtime dependencies. No license is granted by this repository.

## Documentation

See [`docs/README.md`](docs/README.md) for the harness design, its phase
workflow, and a sanitized reference design for a Korean Linux learning
service. The service documentation is published as an architecture example;
the service code and its private executable inputs are not part of this
repository.
