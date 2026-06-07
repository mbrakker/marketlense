# Analytics, Reports Migration, and Publish Decomposition Review

Date: 2026-06-07

## Scope

This movement-only refactor decomposes three existing modules behind their
canonical boundaries:

- `analytics_store_service.py` remains the only analytics SQLite service
  entrypoint over connection/schema helpers, projection writes, cross-report
  reads, and signal candidate storage.
- `_sqlite_migration/reports.py` remains the ordered reports-database migration
  registry over schema, core metadata, routing/recovery, and analytics/signal
  projection migration owners.
- `publish_orchestrator.py` remains the publication control-plane entrypoint.
  Its public `run_publish`, `publish_cross_report_package`, and
  `publish_signal_projection` functions remain physically defined in the
  facade to preserve module-level external-boundary patch points.

No contract, SQL, migration order, branch order, retry policy, idempotency key,
checksum, validation policy, WordPress call, prompt, model call, log event,
artifact path, or cost behavior changed.

## Architecture Review

- Modular monolith preservation: yes. No deployable component or public
  entrypoint was added.
- Semantic boundaries: yes. Owners align with durable persistence and
  publication capabilities rather than file-size slices.
- Canonical ownership: preserved. Callers still import one analytics service,
  one reports migration registry, and one publish orchestrator.
- Indirection budget: preserved. Private owners call each other directly;
  compatibility facades are the only forwarding surfaces.
- Cognitive load: reduced. Projection writes, analytical reads, signal
  storage, migration families, publish preflight, and cross-report helpers can
  now be inspected independently.

## Dependency Direction

- Analytics `projection_write`, `cross_report_read`, and `signals` depend on
  `_analytics_store/common.py`.
- Reports migration owners depend on `_reports/schema.py` and the parent
  migration runner; `reports.py` alone owns the ordered registry.
- Publish helper dependency order is `models` -> `routing` ->
  `preflight`/`idempotency`/`cross_report` -> facade public workflows.

No reverse layer imports or duplicate external-system access path was added.

## Movement Audit

Evidence is stored outside the repository at
`C:\Users\Михаил\.codex\evidence\market-lense-analytics-publish-decomposition\ast-movement-audit.json`.

| Original module | Moved | Unchanged | Changed |
| --- | ---: | ---: | ---: |
| `analytics_store_service.py` | 58 | 58 | 0 |
| `_sqlite_migration/reports.py` | 32 | 32 | 0 |
| `publish_orchestrator.py` | 46 | 46 | 0 |

The reports registry and three public publish workflows intentionally remain
facade-owned.

## Verification

- Pre-change full suite: `2857 passed, 19 deselected, 22 warnings, 20 subtests
  passed`.
- Red-first ownership tests failed because owner modules did not exist.
- Combined affected suite after movement: `58 passed, 6 deselected`.
- Scoped mypy: passed for 19 changed source files.
- Post-change full suite with coverage: `2866 passed, 19 deselected, 35
  warnings, 20 subtests passed`; global coverage was `83.08%`.
- Critical coverage passed: orchestrators `84.06%`, generators `87.20%`, and
  services `82.93%`.
- Mutation, quality regression, prompt fixture regression, contract schema,
  formatting, forbidden patching, split symbol-linking, risk policy, quality
  ledger, remediation runbook, and WordPress subproject gates passed.
- Publishing prompt tokens and estimated cost were unchanged. Repository-wide
  prompt totals decreased by 98 tokens and estimated cost decreased by
  `$0.000024`; no changed code path invokes an LLM.
- Repository hygiene, architecture import, backlog source, and full-project
  mypy gates still report pre-existing baseline failures. Running the same
  gates at `58ca96b` reproduced the same nine oversized tracked images, the
  same generator-to-orchestrator import and UI replay cycle, the same active
  backlog pattern, and 35 existing mypy errors. The refactor has 34
  full-project mypy errors because the moved publish expression is now typed;
  all changed source files pass scoped mypy.

## Live Gate

Sanitized evidence is stored outside the repository:

- `C:\Users\Михаил\.codex\evidence\market-lense-analytics-publish-decomposition\baseline-live.json`
- `C:\Users\Михаил\.codex\evidence\market-lense-analytics-publish-decomposition\refactor-live.json`

The identical harness ran against baseline `58ca96b` and the refactor using a
copy of the real 8.4 MB reports database and a real generated report HTML
artifact. It exercised reports migration application, cross-report projected
reads, projection-failure persistence, signal candidate idempotent write/read,
publish dry-run, and a real WordPress draft publish followed by forced deletion.

Normalized outputs matched exactly:

- reports schema version `13`, with no pending migrations
- `37` projected source candidates
- `596` evidence rows
- `10` raw metrics
- identical projected payload and signal readback SHA-256 hashes
- identical projection failure state and attempt count
- identical dry-run and live publish routing results
- both WordPress draft deletions returned HTTP `200`

Observed local timings did not regress: migration was `5.621 ms` baseline vs
`4.972 ms` refactor, and projected read was `195.524 ms` baseline vs
`150.878 ms` refactor. WordPress publish latency was `10.063 s` baseline vs
`2.776 s` refactor and is recorded as external-network variance, not a code
performance claim.
