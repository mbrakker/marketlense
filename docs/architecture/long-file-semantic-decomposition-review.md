# Long-File Semantic Decomposition Review

Date: 2026-06-07

## Scope

Five existing modules were decomposed behind their original compatibility
surfaces. This is a movement-only refactor:

- `sqlite_migration_service.py` retains the three public migration entrypoints;
  migration execution, reports schema, state schema, and UI-run schema ownership
  live under `_sqlite_migration/`.
- `publisher_inventory_candidate_quality_generator.py` remains the generator
  facade; classification, candidate evaluation, and workflow assembly live
  under `_publisher_inventory_candidate_quality/`.
- `_browser_report_download/cdp.py` remains the internal CDP compatibility
  surface; models, transport, session/target management, dialogs, and operations
  live under `_cdp/`.
- `_publisher_inventory_service/fetch_service.py` remains the acquisition
  compatibility surface; parsing, discovery, classification, and landing-page
  inspection live under `_fetch/`.
- `_publisher_inventory_service/browser_flow.py` remains the browser traversal
  compatibility surface; interaction probes, page collection, HTTP supplement
  recovery, and traversal coordination live under `_browser_flow/`.

No thresholds, branch ordering, candidate ordering, retry behavior, prompts,
configuration, schemas, logging events, provider calls, cache keys, artifact
paths, browser scripts, or cost behavior changed.

## Architecture Review

- Modular monolith preservation: yes. No deployable unit or public service
  entrypoint was added.
- Semantic boundaries: yes. Every owner groups a stable capability already
  present in the original module.
- Fewer modules with equivalent isolation: no. Combining these owners would
  restore mixed schema/capability ownership and the original long modules.
- Cognitive load: reduced. Callers retain one import path while maintainers can
  locate behavior by schema or browser/acquisition capability.
- Indirection budget: preserved. The only forwarding layers are the required
  compatibility facades; private owners call one another directly in one-way
  dependency order.

`_sqlite_migration/reports.py` remains above 1,000 lines because it owns one
cohesive reports-database schema and migration sequence. Further splitting
would fragment a single schema authority without improving replacement
independence or test isolation.

## Dependency Direction

- SQLite schema owners depend on the shared migration runner.
- Candidate-quality workflow depends on classification and evaluation.
- CDP operations depend on session/transport/models; callers still use `cdp.py`.
- Fetch inspection depends on classification/discovery/parsing.
- Browser traversal depends on collection, which depends on interaction probes.
  HTTP supplement recovery is independent.

No reverse architectural imports or second external-system access paths were
introduced.

## Movement Audit

The AST audit is stored outside the repository at
`C:\Users\Михаил\.codex\evidence\market-lense-long-file-decomposition\ast-movement-audit.json`.

| Original module | Moved | Unchanged | Changed |
| --- | ---: | ---: | ---: |
| `sqlite_migration_service.py` | 60 | 60 | 0 |
| `publisher_inventory_candidate_quality_generator.py` | 77 | 77 | 0 |
| `_browser_report_download/cdp.py` | 47 | 47 | 0 |
| `_publisher_inventory_service/fetch_service.py` | 43 | 43 | 0 |
| `_publisher_inventory_service/browser_flow.py` | 26 | 26 | 0 |

The SQLite facade still owns its three public entrypoints. The other facades
own compatibility exports only.

## Verification

- Pre-change full default suite: `2842 passed, 19 deselected, 22 warnings,
  20 subtests passed`.
- Red-first ownership tests failed because the new owner modules did not exist.
- Targeted publisher-inventory regression suite: `152 passed, 7 warnings`.
- Split symbol-linking gate: passed.
- Scoped mypy for all changed source families: passed, 30 files checked.
- Full default suite after final import cleanup: `2857 passed, 19 deselected,
  22 warnings, 20 subtests passed`.
- Coverage: global `83.05%`, orchestrators `83.80%`, generators `87.20%`,
  services `82.92%`; all configured thresholds passed.
- Mutation, quality regression, prompt fixture cost/performance regression,
  formatting, forbidden patching, risk, contract schema, WordPress, quality
  ledger, remediation runbook, and backlog gates passed.
- The repository-wide architecture gate still reports an existing
  `_report_generation_dependencies/signal.py` generator-to-orchestrator import
  and an existing UI-run replay cycle. The repository hygiene gate still
  reports nine pre-existing tracked oversized image artifacts. The full type
  gate still reports 35 existing errors in untouched files. Scoped checks prove
  this change adds no violations.

## Live Gate

Evidence is stored outside the repository under
`C:\Users\Михаил\.codex\evidence\market-lense-long-file-decomposition\`.

Three `HEAD`/post-refactor comparisons exercised:

- fresh reports/state/UI-run SQLite migrations plus idempotent reruns and exact
  schema/ledger snapshots;
- live Capgemini direct-detail discovery;
- live Bain filtered-archive browser traversal;
- live Cardlytics landing-page quality inspection;
- a real browser CDP `Runtime.evaluate` call against `https://example.com/`.

All normalized outputs matched exactly in every comparison. No LLM call was
made because none of the affected paths requires one; the prompt fixture gate
also confirmed zero publisher-inventory token, browser-attempt, or estimated
cost deltas.

Sequential live timings varied with the external sites. In the final comparison
against the closest sequential baseline, Capgemini was `+4.24%`, Bain
`+6.08%`, Cardlytics quality was `+5.05%`, CDP was `-1.32%`, and total elapsed
time was `+5.00%`. Function bodies and request counts are unchanged, and the
same outputs were observed across all samples, so this variation is attributed
to live network/browser conditions rather than the decomposition.

A 20-sample fresh-interpreter benchmark measured aggregate import time for all
five boundaries at `0.603s` median on `HEAD` and `0.626s` after the split. The
approximately `23ms` cold-start cost is the expected one-time module loading
overhead; steady-state feature execution adds no calls, branches, retries,
provider requests, or model cost.
