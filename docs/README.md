# Documentation

This directory has two deliberately separate documentation sets.

## Phase harness

- [Detailed design](harness/detailed-design.md): implemented components,
  configuration, evidence, failure handling, migration, and known limits.
- [Phase workflow](harness/phase-workflow.md): state transitions, operator
  commands, recovery paths, and a reusable project prompt.

These pages describe the current `phase-harness` package. The source code is
the authority when prose and behavior differ.

## Linux learning service reference

The [Linux learning service index](linux-learning/README.md) publishes a
sanitized product and technical design that motivated the harness. It covers
the learning, assessment, data, API, security, and deployment contracts, plus
phase material for P00–P06.

Publication boundary:

- The Linux service implementation and private teaching source are not in
  this repository.
- Design and phase specifications are targets, not claims that features,
  tests, providers, or deployments are complete.
- P00 and P01 have authored detailed designs. P02–P06 have phase
  specifications only; no missing detailed design has been invented.
- Historical multi-role, Gemini/AGY, or automatic rework mechanics are
  superseded by the two-role harness documented here.
- The public documents are explanatory copies, separate from any private
  executable phase input, progress record, or orchestration evidence.
