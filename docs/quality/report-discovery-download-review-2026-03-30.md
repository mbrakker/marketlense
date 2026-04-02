# Report Discovery + Download Pipeline Review (2026-03-30)

This review identifies logical inconsistencies and concrete improvements for quality/reliability in:

- `src/orchestrators/publisher_inventory_orchestrator.py`
- `src/services/publisher_inventory_service.py`
- `src/generators/publisher_inventory_generator.py`
- `src/orchestrators/report_download_orchestrator.py`
- `src/services/browser_report_download_service.py`

## 11 Logical Inconsistencies & Reliability Improvements

1. **Route memory is keyed by normalized URL only, which can overfit to path/query variants.**
   - Risk: a remembered route for one campaign/report URL can be reused incorrectly for a semantically different page under the same normalized form.
   - Improve: store memory keys at multiple scopes (`exact_url`, `path_prefix`, `host`) and score reuse confidence before applying route hints.

2. **Browser inventory traversal can return incomplete logical route summaries.**
   - Risk: route summaries are free text and may omit decisive interactions; memory reuse becomes brittle.
   - Improve: persist a structured route trace (`steps[]`, selectors/labels, outcomes) alongside human summary.

3. **Discovery route hints are free text with no schema guardrail.**
   - Risk: stale or ambiguous instructions degrade success and can mislead browser agent behavior.
   - Improve: use typed route-hint contracts (action type + target + optional guard conditions).

4. **Snapshot hash intentionally ignores some volatile fields, but no explicit compatibility marker exists.**
   - Risk: future hash-policy changes silently alter change detection semantics.
   - Improve: add `snapshot_hash_policy_version` into state and logs.

5. **Previous snapshot loading uses Drive listing fallback but lacks stale-version compatibility checks.**
   - Risk: older snapshot shapes can parse but semantically mismatch current diff logic.
   - Improve: enforce schema-version compatibility matrix with explicit migration adapters.

6. **Candidate screening happens after snapshot build, but approved/rejected decisions are not persisted as first-class audit rows.**
   - Risk: hard to diagnose why expected items were dropped.
   - Improve: store screening decisions (`accepted`, `reason`, model/request id, prompt hash) per candidate.

7. **`record_discovered_report_source` is retried, but there is no explicit idempotency token in call contract.**
    - Risk: retry storms can still duplicate side effects if DB uniqueness constraints drift.
    - Improve: pass deterministic idempotency key (`publisher + canonical_url + discovered_at_bucket`) and assert at storage layer.

8. **Download orchestrator records route memory before validating long-term route reliability.**
    - Risk: one-off flaky route can pollute memory and reduce next-run success.
    - Improve: add route-health counters and require N successful confirmations before promoting to primary memory route.

9. **Downloaded-file resolution includes fallback fetch from final URL, which can mask browser route defects.**
    - Risk: pipeline reports success even if browser flow failed but direct fetch happened later.
    - Improve: separate outcomes (`browser_downloaded` vs `http_recovered`) and gate memory-learning only on true browser success.

10. **Retry policy is shared for heterogeneous steps but without per-step tuning.**
    - Risk: DB writes, browser actions, and LLM calls need different retry/backoff behavior.
    - Improve: define per-step retry policies with bounded budgets and error-code mappings.

11. **Cross-run reproducibility is limited by incomplete browser execution telemetry.**
    - Risk: difficult postmortems when route regressions appear.
    - Improve: persist deterministic artifacts for each run (visited URL timeline, chosen elements, screenshots-on-failure, normalized exception taxonomy).

## 9 Simplification Options (Lower Complexity / Better Maintainability)

1. **Unify route-memory handling into one shared route-memory service** for both inventory discovery and report download.
2. **Introduce one typed `RouteHint` dataclass** and remove free-text hint branching in orchestrators/services.
3. **Collapse duplicated retry wrapper invocation patterns** into a single orchestrator helper with typed step config.
4. **Centralize URL normalization + source-domain extraction** into one utility module to eliminate repeated local helpers.
5. **Create a shared `OutcomeClassifier` utility** for download outcomes instead of distributed conditional logic.
6. **Replace scattered logging field assembly with small dataclass-to-log adapters** for stable event schemas.
7. **Encapsulate browser agent prompt assembly in a prompt service namespace** to avoid inline prompt concatenation in service code.
8. **Adopt a single `DiscoveryResultQuality` scorer** so HTTP and browser paths share acceptance criteria.
9. **Add one “pipeline quality gate” function per orchestrator** that validates contract completeness before persistence/output.

## Suggested Implementation Order (High ROI)

1. Typed route hints + structured route traces.
2. Route-memory health scoring and promotion thresholds.
3. Snapshot compatibility/version markers.
4. Deterministic browser telemetry and artifact capture.

## Pure Logical Analysis: What To Check and In Which Algorithmic Order

This section is implementation-agnostic. It defines the logical gates and decision sequence that should be validated to maximize output quality and reliability.

### A) Discovery Algorithm: Required Logical Checks

1. **Input Legitimacy Gate**
   - Check that source URL belongs to an allowed web domain class and is not an obvious non-content endpoint.
   - Normalize URL and verify canonical identity before any traversal.

2. **Route Selection Gate**
   - Decide route type (memory-guided, HTTP parse, browser render) by confidence, not by mere availability.
   - If memory exists, require route-confidence threshold and freshness window before using it.

3. **Traversal Safety Gate**
   - Enforce bounded exploration by:
     - max pages,
     - duplicate URL detection,
     - duplicate content fingerprint detection,
     - loop-pattern detection on query-param permutations.

4. **Candidate Extraction Gate**
   - For every extracted candidate, compute a normalized identity and dedup key.
   - Require minimum structural evidence that candidate is report-like (title/anchor/context coherence).

5. **Candidate Quality Gate**
   - Score each candidate with weighted evidence:
     - lexical signal (report/research indicators),
     - structural signal (PDF/detail page pattern),
     - contextual signal (found in insights/report container),
     - anti-signal penalties (tag/category/search/nav pages).
   - Drop candidates below threshold.

6. **Coverage Sufficiency Gate**
   - Evaluate if discovered set is plausible for the publisher (non-trivial count, non-repetitive types).
   - If sufficiency fails, escalate to stronger route (browser) before concluding.

7. **Snapshot Coherence Gate**
   - Before persisting snapshot, verify:
     - stable ordering,
     - no empty required fields,
     - deterministic canonical URLs,
     - monotonic page numbering consistency.

8. **Diff Integrity Gate**
   - Compare current vs previous snapshot using stable identity keys.
   - Ensure “new” set excludes historical duplicates and trivial URL alias variations.

9. **Meaningfulness Gate (LLM or rules engine)**
   - Screen only diff candidates for business relevance.
   - Require explicit reason for accept/reject and confidence.

10. **Persistence Gate**
    - Persist only post-screening approved candidates.
    - Require idempotency checks so reruns cannot duplicate source rows.

### B) Download Algorithm: Required Logical Checks

1. **Acquisition Preconditions Gate**
   - Confirm target URL is valid and route context is compatible with expected outcome class.

2. **Route Reuse Decision Gate**
   - Use remembered route only if historically reliable for the same route class and domain pattern.
   - Otherwise begin fresh discovery.

3. **Interaction Completion Gate**
   - Validate that route execution reached a terminal state:
     - file materialized, or
     - verified email submission/confirmation state.

4. **Artifact Authenticity Gate**
   - If file exists, verify it is a real PDF via independent checks (signature, parseability, non-zero size).

5. **Outcome Classification Gate**
   - Classify outcomes with deterministic rules:
     - `downloaded`,
     - `email_requested`,
     - `email_required`,
     - `failed_transient`,
     - `failed_permanent`.

6. **Route Learning Gate**
   - Learn/update memory only when outcome is strongly verified.
   - Penalize or quarantine route hints associated with ambiguous or weakly verified outcomes.

7. **Source Recording Gate**
   - Record report source only when download authenticity passes.
   - Enforce dedup and idempotency with deterministic natural keys.

### C) Cross-Cutting Reliability Logic

1. **Error Taxonomy Consistency**
   - Every failure must map to one class: transient I/O, permanent I/O, validation, logic.
   - Retry decisions depend only on this class.

2. **Retry Budget Logic**
   - Allocate separate retry budgets per step type (fetch, browser interaction, persistence, model screening).
   - Stop retries when evidence indicates deterministically unrecoverable state.

3. **Determinism and Reproducibility Logic**
   - Same inputs + same memory state should produce equivalent candidate identities and outcome class.
   - Any non-deterministic branch must be recorded with explicit reason and confidence.

4. **Observability Completeness Logic**
   - For every major decision node, log:
     - gate name,
     - decision,
     - confidence,
     - rejecting reason(s),
     - next branch chosen.

5. **Quality Drift Detection Logic**
   - Continuously compare per-publisher metrics over time:
     - discovery yield,
     - approval ratio,
     - download success ratio,
     - route reuse success ratio,
     - false-positive signals (later invalid downloads).
   - Trigger review when drift crosses thresholds.

### D) End-to-End Decision Sequence (Algorithm Skeleton)

1. Normalize input and validate source class.
2. Select discovery route by confidence and history.
3. Traverse with safety bounds and loop prevention.
4. Extract candidates and compute canonical identities.
5. Score/filter candidates by quality rules.
6. Validate snapshot coherence and compute diff.
7. Screen diff for meaningfulness.
8. Persist approved discoveries idempotently.
9. For each queued report, select download route by reliability.
10. Execute route and verify terminal state.
11. Validate file authenticity or email confirmation.
12. Classify outcome deterministically.
13. Update route memory only on verified success.
14. Persist source metadata idempotently.
15. Emit final run quality metrics and drift checks.

### E) Success Criteria for “Best Results”

- High precision in discovered report candidates (low false positives).
- High verified-download rate (not merely agent-claimed success).
- Stable rerun behavior (idempotent persistence + deterministic classification).
- Declining fallback/retry rates over time due to improved route memory quality.
- Full auditability: every accept/reject/path decision explainable from logs.

## Activity-Based Decomposition: How Discovery Can Be Split into Smaller Units

Goal: keep this section limited to decomposition work that is still missing in the latest codebase.

Implemented since this review:
- navigation control, candidate extraction, and candidate-shape heuristics were extracted from the public service boundary into `src/services/_publisher_inventory_discovery_activity.py`
- direct HTTP discovery now scores candidate confidence and rejects low-confidence `http_parse` candidates before route acceptance
- direct HTTP pagination now stops on repeated anchor fingerprints instead of relying only on repeated URLs and page-count bounds
- discovery candidates now carry extraction provenance, and browser/HTTP completion logs record provenance proportions
- snapshot construction and diffing already live in `src/generators/publisher_inventory_generator.py`
- screening, landing-page quality, and persistence already execute as separate generator/orchestrator responsibilities

### Remaining Activity-Based Decomposition Gaps

1. **Route planning is still embedded in `src/orchestrators/publisher_inventory_orchestrator.py`.**
   - Memory-route reuse, HTTP/browser selection, and fallback ordering should still become an explicit planner unit with its own contract and logging surface.

2. **HTTP acquisition and browser acquisition still share one public service module.**
   - `src/services/publisher_inventory_service.py` remains the canonical boundary, but acquisition mechanics are still large enough to justify an internal split between HTTP fetch flow and browser traversal flow.

3. **Coverage validation remains implicit across service and orchestrator checks.**
   - Undercoverage, raw-only delta rejection, and unreachable-delta tolerance are valuable quality gates, but they are still distributed rather than represented as one explicit activity with one verdict contract.

4. **Run-level quality evaluation is still missing as a first-class output.**
   - The workflow logs rich traversal facts, but it does not yet persist a reusable run-quality summary for future route planning and drift monitoring.

### Remaining Recommended Boundaries

- **Orchestrator units:**
  - `discovery_route_planner` for route order, confidence, and stop conditions
  - `discovery_execution_orchestrator` for run sequencing and retry policy
  - `discovery_persistence_orchestrator` for state/diff persistence choreography

- **Internal service units under the canonical publisher inventory service boundary:**
  - `inventory_fetch_service` for HTTP acquisition
  - `inventory_browser_service` for rendered acquisition/traversal
  - `inventory_state_store_service` for snapshot/state reads and writes

- **Generator units still worth isolating further:**
  - explicit coverage-validation generator
  - explicit run-quality evaluation generator
