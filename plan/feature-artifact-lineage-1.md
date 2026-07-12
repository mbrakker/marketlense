---
goal: Canonical artifact lineage and invalidation registry
version: 1.0
date_created: 2026-07-12
last_updated: 2026-07-12
owner: Codex
status: 'Completed'
tags: [feature, architecture, migration, lineage]
---

# Introduction

![Status: Completed](https://img.shields.io/badge/status-Completed-brightgreen)

Introduce one reports-DB-backed artifact lineage boundary, preserving existing checkpoint payload compatibility.

## 1. Requirements & Constraints

- **REQ-001**: Persist immutable content-addressed artifact records and direct dependency edges.
- **REQ-002**: Reuse must validate semantic compatibility and current content, not only a path.
- **REQ-003**: Invalidation must be transitive and selective by source, prompt, template, crop, or validator.
- **CON-001**: Keep the existing checkpoint-local `ArtifactRegistry` payload and public entrypoints compatible.
- **CON-002**: Use the reports SQLite database and canonical report-store service boundary.

## 2. Implementation Steps

### Implementation Phase 1

- GOAL-001: Add contracts, database migration, durable service, and pure invalidation policy.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | Add typed artifact-lineage contracts and deterministic identity construction. | ✅ | 2026-07-12 |
| TASK-002 | Add reports-db migration 15 and report-store lineage service operations. | ✅ | 2026-07-12 |
| TASK-003 | Add compatibility-aware reuse, lineage traversal, invalidation, and bounded dry-run backfill. | ✅ | 2026-07-12 |

### Implementation Phase 2

- GOAL-002: Integrate report checkpoints and publication, then verify real retained artifacts.

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-004 | Persist each report checkpoint artifact with canonical dependencies without changing checkpoint payload IDs. | ✅ | 2026-07-12 |
| TASK-005 | Attach the canonical rendered-HTML identity to publication idempotency records for source traceability. | ✅ | 2026-07-12 |
| TASK-006 | Add focused migration, service, invalidation, checkpoint-resume, and publish tests; run a live retained-artifact resume. | ✅ | 2026-07-12 |

## 3. Alternatives

- **ALT-001**: Store lineage only in checkpoint JSON. Rejected because it cannot support cross-report querying or durable selective invalidation.
- **ALT-002**: Create a new SQLite database. Rejected because reports.sqlite is already the canonical retained-report metadata boundary.

## 4. Dependencies

- **DEP-001**: Existing report SQLite migrations and report-store connection service.
- **DEP-002**: Existing checkpoint artifact registry and file hashing service.

## 5. Files

- **FILE-001**: `src/contracts/artifact_lineage.py`
- **FILE-002**: `src/services/_report_store_service/artifact_lineage.py`
- **FILE-003**: `src/utils/artifact_lineage_invalidation.py`
- **FILE-004**: report migration and report/publish orchestration integration files.

## 6. Testing

- **TEST-001**: identity, deduplication, dependency edges, compatibility reuse, and trace traversal.
- **TEST-002**: source/prompt/template/crop/validator invalidation and render-only non-invalidation.
- **TEST-003**: migration idempotency, checkpoint resume, publication lineage, and dry-run/idempotent backfill.

## 7. Risks & Assumptions

- **RISK-001**: Historical checkpoints lack prompt-level provenance; backfill will record only evidence that exists and label unavailable fields empty.
- **ASSUMPTION-001**: Existing report IDs are the Drive `file_id` and source IDs are source MD5 checksums where known.

## 8. Related Specifications / Further Reading

- `AGENTS.md`
- `docs/quality/architecture_policy.yaml`
- `src/contracts/report_artifacts.py`
