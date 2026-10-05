# Fraud Investigation Copilot

Synthetic-data build of the Fraud Investigation Copilot v2 design (see
`fraud-investigation-copilot.md` and `docs/`): an intelligence layer that turns
a raw bank fraud alert into a complete, evidence-linked, auditable case for a
human investigator. Built in phases (docs → local pipeline → AI layer →
entity graph/UI → AWS/Terraform → polish); do not start a phase until the
previous one runs end to end with passing tests.

## Scope

- `docs/` — BRS, user stories, HLD, LLD.
- `src/` (or equivalent) — Phase 1-3 local pipeline, AI layer, entity graph, UI.
- `infra/` — Phase 4 Terraform.
- Synthetic data only. No real bank data at any phase.

## Workflow

Inherit the root TBT workflow from the parent CLAUDE.md.

{{include:../CLAUDE.md}}
