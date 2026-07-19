---
goal: Complete governed model execution, reusable corpus recovery, and bounded operational controls
version: 1.0
date_created: 2026-07-19
last_updated: 2026-07-19
owner: MarketLense engineering
status: Partially complete
tags: [feature, operations, lineage, recovery, governance]
---

# Introduction

![Status: Partially complete](https://img.shields.io/badge/status-partially_complete-orange)

Complete the seven requested operational-control outcomes through existing typed
service, orchestration, queue, and report-store boundaries. Every new command
is deterministic and read-only unless it explicitly submits an approved,
idempotent bounded batch.

## 1. Requirements & Constraints

- **REQ-001**: Reject an unregistered production provider namespace before client or provider I/O, while retaining explicit test-only overrides.
- **REQ-002**: Produce planner-safe corpus rehabilitation classifications and idempotent approved campaign execution without fabricated lineage.
- **REQ-003**: Produce read-only, cohort-compatible route-economics recommendations from fully attributed attempts only.
- **REQ-004**: Make A10 the single active deferred-acquisition recovery identifier and enforce canonical backlog consistency in CI.
- **REQ-005**: Resolve seven typed run profiles through one canonical resolver shared by CLI, UI, and plan-first execution.
- **REQ-006**: Quarantine checksum-identical deterministically malformed PDFs after existing redownload recovery, avoiding repeated expensive work.
- **REQ-007**: Register typed deferred-work and allowlisted remediation adapters through one disabled-by-default shared registry.
- **CON-001**: Preserve public contracts, publication approval, model/provider selection, deterministic direct-first acquisition, existing retry owners, and all external-boundary ownership.
- **CON-002**: Never retain prompt/report payloads in new telemetry, fabricate provenance, add a scheduler, or enable automatic recovery by default.
- **CON-003**: Use real retained project artifacts for validation; live calls are bounded, accounted, and avoid public writes.

## 2. Implementation Steps

### Implementation Phase 1

- **GOAL-001**: Complete model policy inventory, enforcement, accounting, and deterministic effectiveness reporting.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Inventory all `src` production LLM call namespaces and add exact/prefix policies in `src/config/app.yaml`. | | |
| TASK-002 | Make `src/utils/model_resolver.py` and `src/services/_llm_service/` reject missing production namespace/identity before client/provider I/O. | | |
| TASK-003 | Add a read-only execution-identity effectiveness projection over canonical usage and lineage records; test empty and attributed results. | | |

### Implementation Phase 2

- **GOAL-002**: Rehabilitate retained corpus records through the existing lineage planner and plan/actual audit boundary.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Add typed deterministic corpus classification and bounded plan contracts/service using report-store lineage evidence. | | |
| TASK-005 | Add CLI planning/submission commands that reuse `backfill_artifact_lineage`, the minimal planner, existing queues, and durable campaign reconciliation. | | |

### Implementation Phase 3

- **GOAL-003**: Make acquisition economics and backlog integrity operator-reviewable and deterministic.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-006 | Extend the existing acquisition-attempt schema/recording with canonical identity, complete resource envelope, ingest handoff, and usage reconciliation. | | |
| TASK-007 | Add a read-only compatible-policy/publisher route-economics report and configuration proposal/abstention. | | |
| TASK-008 | Correct A10/A13, extend `scripts/ci/check_backlog_source.py`, and add parser regression tests. | | |

### Implementation Phase 4

- **GOAL-004**: Compose approved typed operational controls without creating parallel policy systems.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-009 | Add run-profile contracts, parser/resolver, validation, hashes, recommendation, and canonical configuration profiles. | | |
| TASK-010 | Integrate profile resolution with plan, CLI/UI execution payloads, bounded events, generated configuration reference, and CTO evidence. | | |

### Implementation Phase 5

- **GOAL-005**: Introduce a PDF integrity service result and durable checksum-bound quarantine lifecycle.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Add PDF-integrity and source-quarantine contracts, state persistence/migration, configuration, and operator inspection/revalidation commands. | | |
| TASK-012 | Gate ingest before download/parse/OCR/LLM work; preserve existing redownload behavior and establish replacement/supersession transitions. | | |

### Implementation Phase 6

- **GOAL-006**: Share safe recovery adapters across CLI and one-shot supervisor while preserving disabled execution gates.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-013 | Create one typed adapter registry for deferred plan/resume, remediation execution, and proof validation. | | |
| TASK-014 | Register report-download, publisher-inventory, report-generation timeout, browser timeout, mail delivery, and claim-embedding adapters through public queue/orchestrator boundaries. | | |

### Implementation Phase 7

- **GOAL-007**: Verify, live-validate, document, close completed backlog work, and commit one focused change set.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-015 | Run focused and aggregate gates, inspect the final diff, and repair regressions. | | |
| TASK-016 | Run bounded existing-artifact canaries for each materially different affected mode; retain only bounded evidence. | | |
| TASK-017 | Regenerate derived documentation/evidence, move completed backlog items to Recently Closed, record material follow-up work, and commit on `main`. | | |

## Delivery Status

Completed on 2026-07-19: requirements REQ-001 through REQ-006, the associated
implementation phases 1 through 5, and the focused/lived-validation portions
of phase 7. The change set includes explicit model attribution, corpus
campaigns, route economics, backlog integrity, run profiles, and PDF
quarantine.

The recovery registry deliberately supports only the three proof-complete
deferred workflows (`report_generation`, `report_download`, and
`publisher_inventory`). The broader allowlisted remediation-executor registry
and the remaining recovery adapters are still owned by active A10; they are
not represented as complete merely because the disabled-by-default shared
registry exists. A15 also remains active for the required multi-policy
comparative effectiveness evidence.

## 3. Alternatives

- **ALT-001**: Build a new scheduler or generic recovery framework. Rejected because the durable queue and typed reapers already own this responsibility.
- **ALT-002**: Treat historical artifacts or attempts as complete from filename, error class, or route alone. Rejected because required proof must be retained and checksum/policy compatible.
- **ALT-003**: Permit global compatibility model policy in production. Rejected because it prevents complete namespace attribution and pre-I/O failure.

## 4. Dependencies

- **DEP-001**: Existing canonical configuration, model resolver, usage ledger, report store, workflow queue, state service, and minimum-execution planner.
- **DEP-002**: Existing retained reports, local SQLite state, guarded OpenAI and Drive credentials for bounded live canaries.

## 5. Files

- **FILE-001**: `src/config/app.yaml`, configuration contracts, parser, generated reference, and configuration documentation.
- **FILE-002**: LLM resolver/service, usage ledger projections, prompt contracts, and policy/effectiveness CLI surface.
- **FILE-003**: Report-store/state contracts, services, migrations, corpus/quarantine/economics orchestrators, and corresponding CLI modules.
- **FILE-004**: Deferred-work/remediation contracts, registry, CLI, supervisor, queue handlers, and recovery documentation.
- **FILE-005**: Backlog parser, tests, canonical TODO, and generated CTO evidence.

## 6. Testing

- **TEST-001**: Add focused positive, fail-closed, idempotency, attribution, zero-side-effect, and deterministic ordering tests for every new contract surface.
- **TEST-002**: Run affected test modules, documentation/configuration generators and gates, then the proportional aggregate quality suite.
- **TEST-003**: Run bounded existing-retained-artifact live canaries with explicit cost/side-effect checks; do not use synthetic fixtures for live proof.

## 7. Risks & Assumptions

- **RISK-001**: Current retained historical rows may lack required proof; classify/hold them rather than backfill invented provenance.
- **RISK-002**: Live provider and external-data calls may fail from budget, credentials, or upstream availability; run guarded tests first and repair only implementation failures.
- **RISK-003**: User-requested one commit applies to the new working-tree change set; existing main history is preserved.
- **ASSUMPTION-001**: The existing local `.env`, retained artifacts, and state databases are authorised in-scope for bounded canaries, while public WordPress writes remain forbidden without separate approval.

## 8. Related Specifications / Further Reading

[MarketLense engineering policy](../AGENTS.md)
[Minimum regeneration planner](../docs/architecture/lineage-minimum-regeneration-planner.md)
[Workflow control](../docs/architecture/workflow-control.md)
[Recovery operations](../docs/ops/recovery.md)
[Canonical backlog](../CONSOLIDATED_TODO.md)
