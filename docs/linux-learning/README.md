# Korean Linux learning service reference

This is a sanitized design reference for an invitation-only Korean learning
service built from a private Notion textbook. It is published to make the
product and engineering contracts reviewable without publishing the textbook,
provider identifiers, credentials, local paths, or execution history.

The service code is not included here. These documents do not claim that a
feature, test suite, provider integration, educational review, or deployment
is complete.

## Design set

- [Product and learning flow](design/product.md)
- [Curriculum taxonomy](design/curriculum.md)
- [Assessment quality](design/assessment-quality.md)
- [Architecture and security](design/architecture.md)
- [Data and API](design/data-api.md)
- [Deployment and operations](design/deployment.md)
- [P00 detailed design](design/P00-detailed-design.md)
- [P00 implementation decisions](design/P00-decisions.md)
- [P01 detailed design](design/P01-detailed-design.md)

## Phase set

- [P00 — foundation contracts and source audit](phases/P00.md)
- [P01 — application skeleton and authentication](phases/P01.md)
- [P02 — source sync, media, and RAG](phases/P02.md)
- [P03 — unit and section learning UI](phases/P03.md)
- [P04 — question generation and quality bank](phases/P04.md)
- [P05 — assessment, grading, explanation, and Memory](phases/P05.md)
- [P06 — integration, security, and educational evaluation](phases/P06.md)

P00 and P01 have authored detailed designs. P02–P06 are phase specifications,
not reconstructed detailed designs. Any historical role mechanics in the
private source have been removed; the current [two-role workflow](../harness/phase-workflow.md)
governs execution.
