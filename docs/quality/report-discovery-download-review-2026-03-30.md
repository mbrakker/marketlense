# Report Discovery + Download Pipeline Review (2026-03-30)

This review identifies logical inconsistencies and concrete improvements for quality/reliability in:

- `src/orchestrators/publisher_inventory_orchestrator.py`
- `src/services/publisher_inventory_service.py`
- `src/generators/publisher_inventory_generator.py`
- `src/orchestrators/report_download_orchestrator.py`
- `src/services/browser_report_download_service.py`

## 14 Logical Inconsistencies & Reliability Improvements

1. **Route memory is keyed by normalized URL only, which can overfit to path/query variants.**
   - Risk: a remembered route for one campaign/report URL can be reused incorrectly for a semantically different page under the same normalized form.
   - Improve: store memory keys at multiple scopes (`exact_url`, `path_prefix`, `host`) and score reuse confidence before applying route hints.

2. **HTTP discovery treats any non-empty candidate list as success without candidate quality scoring.**
   - Risk: weak keyword matches can dominate output and produce high false positives on blog/news pages.
   - Improve: add candidate confidence scoring and minimum quality threshold before accepting `http_parse` route.

3. **Pagination traversal relies mainly on next-link heuristics and max page count, with no duplicate-content stop rule.**
   - Risk: infinite-ish loops through cosmetic URL changes or near-duplicate pages.
   - Improve: stop on repeated page fingerprint/hash, not only repeated URL.

4. **Browser inventory traversal can return incomplete logical route summaries.**
   - Risk: route summaries are free text and may omit decisive interactions; memory reuse becomes brittle.
   - Improve: persist a structured route trace (`steps[]`, selectors/labels, outcomes) alongside human summary.

5. **Discovery route hints are free text with no schema guardrail.**
   - Risk: stale or ambiguous instructions degrade success and can mislead browser agent behavior.
   - Improve: use typed route-hint contracts (action type + target + optional guard conditions).

6. **Snapshot hash intentionally ignores some volatile fields, but no explicit compatibility marker exists.**
   - Risk: future hash-policy changes silently alter change detection semantics.
   - Improve: add `snapshot_hash_policy_version` into state and logs.

7. **Previous snapshot loading uses Drive listing fallback but lacks stale-version compatibility checks.**
   - Risk: older snapshot shapes can parse but semantically mismatch current diff logic.
   - Improve: enforce schema-version compatibility matrix with explicit migration adapters.

8. **Candidate screening happens after snapshot build, but approved/rejected decisions are not persisted as first-class audit rows.**
   - Risk: hard to diagnose why expected items were dropped.
   - Improve: store screening decisions (`accepted`, `reason`, model/request id, prompt hash) per candidate.

9. **`record_discovered_report_source` is retried, but there is no explicit idempotency token in call contract.**
    - Risk: retry storms can still duplicate side effects if DB uniqueness constraints drift.
    - Improve: pass deterministic idempotency key (`publisher + canonical_url + discovered_at_bucket`) and assert at storage layer.

10. **Browser discovery supplements via HTTP candidate extraction when browser candidate set is empty.**
    - Risk: route kind says `browser_render` but effective extraction logic may be HTTP-derived, obscuring provenance.
    - Improve: annotate candidate provenance (`browser_dom`, `http_supplement`) and log proportion.

11. **Download orchestrator records route memory before validating long-term route reliability.**
    - Risk: one-off flaky route can pollute memory and reduce next-run success.
    - Improve: add route-health counters and require N successful confirmations before promoting to primary memory route.

12. **Downloaded-file resolution includes fallback fetch from final URL, which can mask browser route defects.**
    - Risk: pipeline reports success even if browser flow failed but direct fetch happened later.
    - Improve: separate outcomes (`browser_downloaded` vs `http_recovered`) and gate memory-learning only on true browser success.

13. **Retry policy is shared for heterogeneous steps but without per-step tuning.**
    - Risk: DB writes, browser actions, and LLM calls need different retry/backoff behavior.
    - Improve: define per-step retry policies with bounded budgets and error-code mappings.

14. **Cross-run reproducibility is limited by incomplete browser execution telemetry.**
    - Risk: difficult postmortems when route regressions appear.
    - Improve: persist deterministic artifacts for each run (visited URL timeline, chosen elements, screenshots-on-failure, normalized exception taxonomy).

## 10 Simplification Options (Lower Complexity / Better Maintainability)

1. **Unify route-memory handling into one shared route-memory service** for both inventory discovery and report download.
2. **Introduce one typed `RouteHint` dataclass** and remove free-text hint branching in orchestrators/services.
3. **Collapse duplicated retry wrapper invocation patterns** into a single orchestrator helper with typed step config.
4. **Centralize URL normalization + source-domain extraction** into one utility module to eliminate repeated local helpers.
5. **Create a shared `OutcomeClassifier` utility** for download outcomes instead of distributed conditional logic.
6. **Replace scattered logging field assembly with small dataclass-to-log adapters** for stable event schemas.
7. **Encapsulate browser agent prompt assembly in a prompt service namespace** to avoid inline prompt concatenation in service code.
8. **Adopt a single `DiscoveryResultQuality` scorer** so HTTP and browser paths share acceptance criteria.
9. **Standardize candidate provenance tagging at extraction time** to simplify downstream screening and debugging.
10. **Add one “pipeline quality gate” function per orchestrator** that validates contract completeness before persistence/output.

## Suggested Implementation Order (High ROI)

1. Typed route hints + structured route traces.
2. Candidate quality/provenance scoring before snapshot acceptance.
3. Route-memory health scoring and promotion thresholds.
4. Snapshot compatibility/version markers.
5. Deterministic browser telemetry and artifact capture.

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

Goal: split discovery by *activity type* so each unit has one responsibility, clearer quality gates, and easier reliability tuning.

### 1) Activity Catalog (What the workflow actually does)

1. **Input qualification activity**
   - Validate/normalize incoming URL and discovery context.
   - Output: canonical source identity + eligibility verdict.

2. **Route planning activity**
   - Choose initial path (`memory-guided`, `http_parse`, `browser_render`) from confidence and historical performance.
   - Output: route plan with fallback order and stop conditions.

3. **Page acquisition activity**
   - Obtain page material (HTTP HTML fetch or browser-rendered DOM state) with bounded traversal.
   - Output: ordered page captures with provenance and traversal metadata.

4. **Navigation control activity**
   - Determine “next page” / tab / load-more transitions.
   - Output: next-step actions and loop-prevention signals.

5. **Candidate extraction activity**
   - Parse anchors/DOM blocks into raw report candidates.
   - Output: raw candidate set + extraction evidence.

6. **Canonicalization and dedup activity**
   - Normalize URLs/titles and deduplicate by stable identity key.
   - Output: canonical candidate set.

7. **Quality scoring activity**
   - Score candidate quality/likelihood of being a true report asset.
   - Output: accepted/rejected candidates with reasoned scores.

8. **Coverage validation activity**
   - Check if discovery set is plausible and sufficient for this publisher.
   - Output: sufficiency verdict + escalation hint.

9. **Snapshot construction activity**
   - Build deterministic inventory snapshot from accepted candidates.
   - Output: stable snapshot payload + diff basis.

10. **Diff and novelty activity**
    - Compare against prior snapshot and identify new items.
    - Output: new-item candidate set for screening.

11. **Meaningfulness screening activity**
    - Apply relevance screening to new items only.
    - Output: approved/rejected novel items with auditable reasons.

12. **Persistence activity**
    - Write state, snapshot references, and discovered sources idempotently.
    - Output: persisted state transitions and record IDs.

13. **Run quality evaluation activity**
    - Compute run-level quality metrics and drift indicators.
    - Output: quality summary used for future planning.

### 2) Recommended Smaller Module Boundaries by Activity Type

Use activity boundaries, not file-size boundaries. Keep one role per module.

- **Orchestrator units (control plane):**
  - `discovery_route_planner` (route order + fallback policy)
  - `discovery_execution_orchestrator` (sequence/run lifecycle)
  - `discovery_persistence_orchestrator` (state/diff persistence choreography)

- **Service units (I/O only):**
  - `inventory_fetch_service` (HTTP acquisition)
  - `inventory_browser_service` (rendered acquisition/traversal)
  - `inventory_state_store_service` (snapshot/state reads+writes)

- **Generator units (domain logic):**
  - `inventory_candidate_generator` (extract/canonicalize/dedup)
  - `inventory_quality_generator` (score/filter/sufficiency)
  - `inventory_diff_generator` (snapshot/diff/novelty)
  - `inventory_screening_generator` (meaningfulness decisions)

- **Utility units (pure transforms):**
  - URL/title normalization, identity keying, scoring math, deterministic sorting.

### 3) Activity-to-Quality Gates Matrix

For each activity, define an explicit pass/fail gate:

1. Input qualification -> **valid canonical URL + eligible source type**.
2. Route planning -> **route confidence >= threshold** or forced fallback.
3. Page acquisition -> **bounded traversal + no loop signal**.
4. Navigation control -> **forward progress evidence**.
5. Candidate extraction -> **minimum structural evidence per candidate**.
6. Canonicalization/dedup -> **stable identity + zero malformed keys**.
7. Quality scoring -> **score >= acceptance threshold**.
8. Coverage validation -> **sufficient diversity/count** or escalate.
9. Snapshot construction -> **deterministic ordering + complete required fields**.
10. Diff/novelty -> **alias-safe novelty detection**.
11. Meaningfulness screening -> **auditable accept/reject rationale**.
12. Persistence -> **idempotent write guarantees**.
13. Run quality evaluation -> **metric emission complete**.

### 4) Execution Steps for Best Results (Activity-first)

1. Run input qualification.
2. Build route plan with explicit confidence.
3. Execute acquisition + navigation with loop controls.
4. Extract raw candidates with provenance.
5. Canonicalize and deduplicate.
6. Apply quality scoring.
7. Validate coverage; escalate route if insufficient.
8. Build deterministic snapshot.
9. Compute novelty against previous snapshot.
10. Screen novel items for meaningfulness.
11. Persist approved discoveries idempotently.
12. Emit run quality metrics and update route reliability memory.

### 5) Why this split improves reliability

- **Failure isolation:** defects localize to one activity (planning vs extraction vs scoring).
- **Targeted retries:** orchestrator retries only failing activity class, not whole pipeline.
- **Auditability:** each activity has explicit inputs, outputs, and quality gate result.
- **Determinism:** canonicalization and snapshot steps become stable reusable building blocks.
- **Simpler tuning:** thresholds and fallback policies can evolve without touching I/O code paths.
