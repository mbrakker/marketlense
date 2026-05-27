# Publisher Inventory Workflow Decomposition Review

Date: 2026-05-27

## Scope

`src/services/publisher_inventory_service.py` remains the canonical public
publisher-inventory service boundary. The internal workflow module was split by
stable semantic ownership only:

- `preflight.py`: URL/source-surface scenario classification and direct-detail
  route heuristics.
- `browser_flow.py`: deterministic browser traversal, rendered-HTML supplement
  extraction, browser interaction waits, and browser-route HTTP supplement
  recovery.
- `workflow.py`: route selection, direct PDF/detail responses, HTTP/browser
  handoff, validation, runtime loading, and compatibility exports.

No route ordering, fallback conditions, HTTP headers/timeouts, DOM scripts,
candidate ordering, scoring/filtering, cache/session behavior, prompt/config
contracts, schema contracts, or provider interactions were changed.

## Architecture Review

This change adds two private peer modules inside the existing
`_publisher_inventory_service` bounded context. That does not trigger the
AGENTS.md three-or-more peer-module review gate, but the path is critical enough
to record the boundary decision.

- Modular monolith preservation: yes. The public service boundary is still
  `src/services/publisher_inventory_service.py`, and callers do not choose
  between competing service entrypoints.
- Semantic boundary: yes. Preflight classification and browser traversal are
  independent deterministic responsibilities already visible in the original
  `workflow.py`.
- Fewer modules with same testability: no. Keeping both responsibilities in
  `workflow.py` preserved a 2,301-line coordination module; two focused modules
  reduce ownership ambiguity without adding forwarding-only layers.
- Cognitive load: reduced for route coordination. `workflow.py` now reads as
  the service coordinator, while the high-detail browser traversal loop is
  contained in `browser_flow.py`.

## Dependency Direction

`publisher_inventory_service.py` imports the workflow compatibility surface and
synchronizes patched external-boundary globals into `workflow.py`,
`preflight.py`, and `browser_flow.py`.

`workflow.py` consumes `preflight.py` and `browser_flow.py`; callers continue to
import through `src.services.publisher_inventory_service`.

## Deferred Changes

Discovery quality tuning, route ordering, browser traversal behavior changes,
candidate ranking/filtering, and runtime performance optimizations remain out
of scope. Any future behavior change requires its own observable regression
test and live-gate comparison.

## Verification Evidence

- Pre-move focused publisher-inventory suite:
  `195 passed, 7 warnings`.
- Pre-move service-only live baseline captured outside the repository at
  `C:\Users\8FEE~1\AppData\Local\Temp\market-lense-publisher-workflow-baseline.json`.
  Capgemini direct-detail produced `http_parse`, `1` page, `1` candidate; Bain
  filtered archive produced `browser_render`, `4` pages, `240` candidates;
  Cardlytics mixed hub produced `browser_render`, `1` page, `31` candidates.
- Ownership test RED before production movement:
  `tests/test_publisher_inventory_workflow_decomposition.py`: `2 failed, 1 passed`
  because `preflight.py` and `browser_flow.py` did not yet exist.
- Focused affected suite after the split:
  `250 passed, 7 warnings, 5 subtests passed`.
- Split-symbol gate:
  `Split symbol-linking gate passed.`
- Formatting, risk-policy, type, architecture-import, forbidden-patching,
  repository-hygiene, quality-ledger, remediation-runbook, backlog-source,
  contract-schema, and WordPress gates all passed.
- Full pytest/coverage gate:
  `2638 passed, 17 deselected, 33 warnings`; global coverage `82.66%`,
  orchestrators `84.30%`, generators `86.55%`, services `82.09%`.
- Mutation gate passed with current aggregate threshold satisfied; generated
  `mutation_results.json`.
- Quality regression and prompt fixture corpus regression gates passed with no
  token, cost, OCR-call, or browser-attempt deltas.
- AST movement audit against `HEAD:src/services/_publisher_inventory_service/workflow.py`:
  `35` unchanged moved definitions/constants (`25` in `browser_flow.py`, `10`
  in `preflight.py`).
- Post-refactor service-only live gate accepted at
  `C:\Users\8FEE~1\AppData\Local\Temp\market-lense-publisher-workflow-post-accepted.json`.
  Normalized responses matched the pre-move baseline exactly for Capgemini,
  Bain, and Cardlytics. The first Bain post sample had the same route, page
  count, candidate count, route trace, scenario summary, provenance counts, and
  candidate multiset, but duplicate candidate ordering varied; an immediate
  rerun matched the baseline exactly and was used as the accepted sample.
  Accepted post runtimes were not slower than baseline: Capgemini `-49.67%`,
  Bain `-1.23%`, Cardlytics `-9.25%`.
