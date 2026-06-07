# Analytics, Reports Migration, and Publish Decomposition Plan

Date: 2026-06-07

## Goal

Decompose three long modules by semantic ownership without changing behavior,
contracts, logs, request counts, retries, persistence, quality, latency-critical
ordering, or model/provider cost:

- `src/services/analytics_store_service.py`
- `src/services/_sqlite_migration/reports.py`
- `src/orchestrators/publish_orchestrator.py`

## Boundaries

### Analytics store

Keep `analytics_store_service.py` as the canonical service facade over:

- `_analytics_store/common.py`: DDL, connection setup, serialization, lineage,
  and shared SQLite helpers.
- `_analytics_store/projection_write.py`: report projection writes and failure
  recording.
- `_analytics_store/cross_report_read.py`: cross-report projected-data reads.
- `_analytics_store/signals.py`: signal candidate/group persistence and reads.

### Reports migrations

Keep `_sqlite_migration/reports.py` as the ordered reports migration registry
over:

- `_sqlite_migration/_reports/schema.py`: reports-database SQL definitions.
- `_sqlite_migration/_reports/core.py`: reports, report sources, and publisher
  normalization migrations.
- `_sqlite_migration/_reports/routing.py`: route history, recovery cache,
  inventory history, and private API ledger migrations.
- `_sqlite_migration/_reports/projections.py`: analytics projection, value
  score, vector queue, and signal projection migrations.

### Publish orchestrator

Keep `run_publish`, `publish_cross_report_package`, and
`publish_signal_projection` defined in `publish_orchestrator.py` so existing
module-level external-boundary patch points remain valid. Move stable helpers
under `_publish_orchestrator/`:

- `models.py`: internal routes, dataclasses, constants, and typed result fields.
- `routing.py`: metadata lookup, candidate resolution, and route settings.
- `preflight.py`: validation, existing-post lookups, taxonomy resolution, and
  publish preflight construction.
- `idempotency.py`: standard and cross-report checksums and outcome persistence.
- `cross_report.py`: cross-report classification, taxonomy, result adaptation,
  and signal package construction.

## Verification

1. Add ownership tests and confirm red before production movement.
2. Run affected unit and integration suites after each split.
3. Record AST movement counts against `HEAD`.
4. Run formatting, scoped typing, architecture, forbidden patching, full
   pytest/coverage, mutation, quality, and prompt-cost regression gates.
5. Capture real `HEAD` and post-refactor canaries outside the repository:
   SQLite migration/projection reads and writes, signal storage, publish dry
   run/idempotency, and a real WordPress API publish/delete canary when local
   credentials and an approved test target are available.
6. Commit and fast-forward merge only after normalized outputs match.
