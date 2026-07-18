---
goal: Enforce retained-artifact minimal execution beyond rendered HTML
version: 1.0
date_created: 2026-07-17
last_updated: 2026-07-17
owner: Codex
status: 'Completed'
tags: [feature, lineage, cost-control, execution]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Extend the existing lineage planner from its proven render-only enforcement path to independently gated publication, crop, targeted analysis, validation/advisory, and cross-report retained-read paths. Every enforce-mode run must persist its plan, reconcile observed work with it, and fail before an unplanned external side effect.

## 1. Requirements & Constraints

- **REQ-001**: Preserve the planner in `src/utils/minimal_execution_planner.py` as the only stage-skipping authority.
- **REQ-002**: Enable enforce-mode publication-only, render-only, crop-only, validation/advisory-only, prompt-family repair, and cross-report read-only execution in dependency order.
- **REQ-003**: Persist plan hash, intent, reusable artifact IDs, planned and actual stages/calls/side effects, duration, cost, avoided work, and divergence before returning an outcome.
- **REQ-004**: Reject incomplete lineage, hash mismatch, dependency mismatch, lease conflict, and any plan/actual divergence before an expensive unplanned side effect or at reconciliation when the side effect has completed.
- **REQ-005**: Construct only the model clients required by the planned restart stage; never construct a provider client for a skipped stage.
- **REQ-006**: Preserve idempotent publication and checkpoint contracts while reusing existing report-store, lock, checkpoint, LLM-ledger, and WordPress boundaries.
- **CON-001**: No new external-system boundary, scheduler, or artifact registry redesign.
- **CON-002**: Use existing retained fixture corpus for regression and live replay; do not synthesize production-like fixtures.
- **CON-003**: Keep `shadow`, `enforce`, and `disabled` policy modes; each newly enabled family remains independently reversible through the existing mode switch.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Make the execution-plan audit complete and fail closed on divergence.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Extend `ExecutionPlanResultRequest` and `artifact_execution_plan_runs` migration with actual side effects, duration, actual/avoided cost, reusable artifact IDs, and explicit reconciliation outcome. | Yes | 2026-07-17 |
| TASK-002 | Make `record_minimal_execution_plan_result` compare stages, calls, and side effects; mark unplanned work as `diverged` while retaining planned work not reached because a run fails. | Yes | 2026-07-17 |
| TASK-003 | Add a scoped report artifact lease using the existing lock service before enforce-mode checkpoint mutation; release it on terminal report-pipeline paths. Publication retains its pre-existing idempotency boundary. | Yes | 2026-07-17 |

### Implementation Phase 2

- GOAL-002: Enforce report-pipeline plans without unused clients or unplanned stage execution.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Map each required planner stage to an existing resume checkpoint and reject unsupported plan shapes before retry/budget/provider work. | Yes | 2026-07-17 |
| TASK-005 | Avoid all client construction for enforced render/crop plans; construct the existing non-source analysis bundle only for analysis plans. | Yes | 2026-07-17 |
| TASK-006 | Add crop-only execution from `source_prepared` that reruns selection, preview, and render while retaining analysis output and avoiding vector/analysis/validation model work. | Yes | 2026-07-17 |
| TASK-007 | Add targeted analysis/validator repair from `selection_complete` with its existing analysis clients and render; preserve source and crop artifacts. | Yes | 2026-07-17 |

### Implementation Phase 3

- GOAL-003: Enforce publication and read-only retained-artifact paths.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-008 | Keep `run_publish` publication-only enforce preflight fail-closed on rendered lineage and record WordPress-only actual work; its existing idempotency key remains the duplicate-write guard. | Yes | 2026-07-17 |
| TASK-009 | Make the public validated cross-report read boundary return projected retained artifacts only when its empty-stage plan reconciles with zero source-report calls. | Yes | 2026-07-17 |
| TASK-010 | Update lineage planner documentation with each enabled family, checkpoint source, call budget, rollback mode, and fail-closed conditions. | Yes | 2026-07-17 |

### Implementation Phase 4

- GOAL-004: Prove the rollout with real retained artifacts and provider calls.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | Add retained-artifact plan/actual cases for template, crop, prompt, validator, lease conflict, lease release, and audit divergence; preserve existing publication/read coverage. | Yes | 2026-07-17 |
| TASK-012 | Run focused tests and retained-report render, crop, and real LLM model-policy replays; a final fresh rebuild was correctly budget-stopped before provider I/O. | Yes | 2026-07-17 |
| TASK-013 | Update the backlog with the consequential prompt-family materialization successor, then commit and merge the verified change. | Yes | 2026-07-17 |

## 3. Alternatives

- **ALT-001**: Add a new DAG scheduler. Rejected because the existing checkpoint sequence already supplies the required safe restart boundaries.
- **ALT-002**: Trust checkpoint presence without lineage. Rejected because it can permit stale, missing, or mismatched retained inputs.
- **ALT-003**: Construct a full model bundle for every repair. Rejected because it undermines the cost and call-avoidance guarantee.

## 4. Dependencies

- **DEP-001**: `src/utils/minimal_execution_planner.py` and report-store execution-plan observation.
- **DEP-002**: Report-generation checkpoint/resume contracts and artifact-lineage registry.
- **DEP-003**: Existing lock service, LLM usage ledger, publication idempotency, and existing retained report corpus.

## 5. Files

- **FILE-001**: `src/contracts/minimal_execution_plan.py`
- **FILE-002**: `src/services/_report_store_service/execution_plan.py`
- **FILE-003**: reports SQLite migration modules
- **FILE-004**: `src/orchestrators/report_pipeline_orchestrator.py`
- **FILE-005**: `src/orchestrators/_report_generation_orchestrator/workflow.py`
- **FILE-006**: `src/orchestrators/_report_generation_orchestrator/resume.py`
- **FILE-007**: `src/orchestrators/publish_orchestrator.py`
- **FILE-008**: focused pipeline, planner, checkpoint, publish, and read tests
- **FILE-009**: `docs/architecture/lineage-minimum-regeneration-planner.md` and `CONSOLIDATED_TODO.md`

## 6. Testing

- **TEST-001**: Planner and report-store reconciliation tests reject every unplanned stage, call, or side effect.
- **TEST-002**: Public-boundary tests prove each enforce-mode family only invokes its planned operations and does not construct unneeded clients.
- **TEST-003**: Concurrency tests prove one artifact lease holder and a deterministic conflict outcome.
- **TEST-004**: Existing retained-artifact live replay proves qualitative HTML validity, plan/actual equality, and avoided provider work with bounded provider calls.

## 7. Risks & Assumptions

- **RISK-001**: A checkpoint may contain mixed-stage data; required lineage validation and scoped locks prevent reuse until it is fully proven.
- **RISK-002**: Provider-call categories are coarser than individual requests; audit records retain category-level accounting while the existing LLM ledger remains authoritative for tokens and cost.
- **ASSUMPTION-001**: The retained benchmark report and credentials named by the existing live-validation procedure remain locally available; if either is unavailable, the final record will explicitly distinguish that from passing evidence.

## 8. Related Specifications / Further Reading

- `AGENTS.md`
- `docs/architecture/lineage-minimum-regeneration-planner.md`
- `docs/quality/testing.md`
- `CONSOLIDATED_TODO.md` E7
