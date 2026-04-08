# Publisher Discovery Success Playbook

## Objective

Increase the end-to-end success rate of `discover-publisher-inventory` across heterogeneous publisher sites (static archives, JS-hydrated feeds, gated forms, anti-bot front doors, and multilingual paths) while preserving current architectural boundaries (`orchestrator -> generators -> services`).

This playbook analyzes the current flow and proposes scenario-specific adjustments prioritized by expected impact on discovery success, false-negative reduction, and retry efficiency.

## Current Flow (as implemented)

### Control-plane sequence

1. `publisher_inventory_orchestrator.run_publisher_inventory_discovery` resolves publisher state and Drive snapshot context.
2. Route order is planned by `_publisher_inventory_route_planner.plan_publisher_inventory_routes`.
3. Discovery attempts run through `publisher_inventory_service.discover_publisher_inventory`.
4. Raw candidates are screened (`publisher_inventory_candidate_screening_generator`) and then landing-page-qualified (`publisher_inventory_candidate_quality_generator`).
5. Coverage validation (`publisher_inventory_coverage_generator`) decides snapshot acceptance.
6. Run-quality (`publisher_inventory_run_quality_generator`) emits recommended route hints for next runs.

### Existing strengths

- Memory-route reuse and retry-aware fallback are already present.
- HTTP-first path supports pagination and WordPress AJAX supplement.
- Browser path has deterministic traversal behaviors (hydration, cookie dismissal, load-more handling).
- Coverage and run-quality gates prevent silent regressions and snapshot drift acceptance.

## Main Bottlenecks Limiting Success Rate

1. **Binary route ordering with limited scenario awareness.**
   Current route plan is primarily `memory -> http -> browser` (or browser-first in a narrow drift case), which under-utilizes past failure signatures and source-type patterns.
2. **Insufficient preflight classification before expensive traversal.**
   Discovery starts with full route execution before building a high-confidence site archetype (SPA, anti-bot-protected, archive-hub, direct-detail, API-backed feed, etc.).
3. **Coverage logic emphasizes regression protection, but not active recovery planning.**
   Coverage failures are detected well, yet remediation is mostly route-kind recommendation, not explicit remediation recipes.
4. **Candidate-quality phase is strong on rejection precision, but weak on acceptance rescue.**
   When many candidates fail landing-page checks, there is no targeted rescue strategy (for example, trying source-page-level alternate links only for the rejected cohort).
5. **Observability is rich per event, but missing scenario-level success KPIs.**
   There is no explicit outcome taxonomy dashboarding route failures by root-cause class, making optimization slower.

## Scenario-Specific Adjustments (Highest Impact)

## 1) JS-hydrated archive pages (cards appear only after render)

### Symptoms
- HTTP parse yields few/no anchors.
- Browser run eventually succeeds after hydration and/or tab traversal.

### Adjustments
- Add a lightweight **preflight surface classifier** in service layer that scores: static HTML density, script/app markers, deferred feed hints, and visible archive controls.
- If classifier confidence for JS-hydrated feed is high, route planner should choose `browser_render` first without waiting for prior-run drift.
- Persist classifier verdict into publisher state so subsequent runs skip low-yield HTTP attempts.

### Expected impact
- Faster success on SPA-heavy publishers.
- Lower time-budget failures caused by repeated low-value HTTP attempts.

## 2) Anti-bot/challenge interstitials (Cloudflare/Akamai/human verification)

### Symptoms
- Landing-page inspection rejects pages as unreachable/challenge.
- Browser route may stall with challenge markers.

### Adjustments
- Introduce explicit **challenge state contract** in discovery response (detected marker, page URL, stage).
- Route planner should short-circuit to a **challenge-aware strategy**:
  - reduce concurrency for the domain,
  - introduce cooldown before retry,
  - prefer remembered verified deep links over archive root,
  - cap futile pagination loops early.
- Record challenge incidence counts in run-quality summary and route history for operator review.

### Expected impact
- Lower false negatives from transient blocking.
- Reduced wasted browser runtime on unrecoverable sessions.

## 3) Multi-template publisher ecosystems (mixed blog + reports + tools)

### Symptoms
- Good recall initially, then quality stage rejects many non-report links.
- Undercoverage can co-exist with noisy candidate surfaces.

### Adjustments
- Add **source-page provenance weighting** in screening and quality:
  - boost candidates extracted from archive/report collection sections,
  - demote generic resource/blog/help sections unless title/path evidence is strong.
- Add an acceptance rescue path for borderline candidates:
  - when title confidence is medium and source page is high-confidence archive, probe `pdf_url`/download endpoint variants before rejection.

### Expected impact
- Higher qualified-candidate yield with controlled precision loss.
- Better performance on consultancies and SaaS vendors with mixed content hubs.

## 4) Pagination drift and duplicated feeds

### Symptoms
- Discovery loops over near-duplicate pages.
- Candidate count plateaus while page count increases.

### Adjustments
- Upgrade loop detection to include **candidate-set convergence** over a rolling window (not just anchor fingerprint repeat).
- Add per-domain **adaptive pagination cap** learned from prior successful runs.
- If convergence is detected, pivot once to alternative pagination mechanism (`next`, numbered page, load more), then terminate deterministically.

### Expected impact
- Better success under strict time budgets.
- Less churn and fewer incomplete runs.

## 5) Strong archive metadata but weak landing availability

### Symptoms
- Many screened candidates become `dead_or_unreachable_landing_page`.
- Coverage verdict becomes `unreachable_delta_tolerated` / failure.

### Adjustments
- Add a **deferred verification mode**:
  - keep candidates with strong archive evidence in a pending set,
  - enqueue a lightweight follow-up check with longer timeout / alternate headers / delayed retry,
  - only hard-reject after second-pass verification.
- Persist pending-set outcomes to avoid repeated hard-fail loops on future runs.

### Expected impact
- Higher conversion from screened to qualified candidates.
- Fewer false “dead” classifications for intermittently available pages.

## 6) Direct report detail pages masquerading as discovery roots

### Symptoms
- Root URL is effectively a single report page with limited outbound links.
- Standard archive traversal adds little.

### Adjustments
- Expand direct-detail heuristic with schema/meta signals (`og:type`, downloadable asset indicators, report metadata blocks).
- If direct-detail confidence is high, emit single-item inventory immediately and skip archive traversal unless explicit override is set.

### Expected impact
- Higher first-pass success for publisher pages that use one canonical insight landing URL per report.

## Cross-Cutting Architecture Enhancements

## A) Add scenario memory to publisher state

Extend persisted publisher discovery state with:
- last successful scenario class (`js_hydrated_archive`, `anti_bot_challenge`, `mixed_content_hub`, etc.),
- per-route yield metrics (raw -> screened -> qualified conversion),
- dominant rejection reason distribution.

Use these fields in route planning, not only `inventory_route_kind` and run-quality recommendation.

## B) Introduce recovery recipe engine in orchestrator

When coverage verdict is non-accepted, generate deterministic remediation recipes:
- `undercoverage_regression` -> force browser with higher page budget + archive expansion strict mode,
- `unreachable_delta_failure` -> deferred verification recipe,
- `raw_only_delta_rejected` -> targeted quality rescue for high-confidence archive candidates.

Recipes should be typed contracts and logged as first-class decisions.

## C) Promote scenario KPIs to first-class telemetry

Track per publisher/domain and globally:
- route success rate by scenario class,
- time-to-first-qualified-candidate,
- screened->qualified conversion,
- challenge incidence rate,
- fallback frequency (`http->browser`, memory-route failures).

This converts tuning from anecdotal to data-driven.

## D) Add confidence-calibrated acceptance policies

Instead of binary accept/reject edges, use tiered confidence with explicit handling:
- high confidence: accept,
- medium confidence: rescue/probe path,
- low confidence: reject.

This is especially useful where archive cards are semantically strong but landing pages are flaky.

## E) Tighten idempotent route-history learning

Route history should store not only best step labels but also:
- failing step signatures,
- blocker types,
- effective mitigations.

Planner can avoid repeating historically low-yield subpaths under similar conditions.

## Prioritized Rollout Plan

## Phase 1 (Fast, high ROI)
1. Add preflight scenario classifier.
2. Feed scenario class into route planner for first-step selection.
3. Add scenario-level KPIs and dashboards from existing logs.

## Phase 2 (Recall improvement)
1. Add deferred verification mode for unreachable deltas.
2. Add quality rescue for high-confidence archive candidates.
3. Add adaptive pagination convergence controls.

## Phase 3 (Long-tail hardening)
1. Add challenge-aware strategy contracts and cooldown logic.
2. Expand scenario memory in publisher state.
3. Add remediation recipe engine for coverage verdicts.

## Scenario-to-Strategy Matrix

| Scenario | First Route | Secondary Route | Key Adjustment |
|---|---|---|---|
| Static archive, rich anchors | `http_parse` | `browser_render` on retryable failure | Keep current fast path; tune pagination convergence |
| JS-hydrated archive | `browser_render` | `http_parse` supplement | Preflight classifier switches route order |
| Anti-bot challenge observed | remembered deep-link/browser with cooldown | delayed retry with reduced churn | Challenge-aware planner branch |
| Mixed content hub | `http_parse` + stronger provenance weighting | browser rescue for medium-confidence | Quality rescue path for archive-backed candidates |
| Unreachable candidate deltas | current successful route + deferred verification | retry with alternate headers/time window | Prevent false dead-page rejects |
| Direct report detail URL | single-item direct-detail path | optional browser verification | Skip unnecessary archive traversal |

## External Best-Practice Anchors Applied

- Browser automation should rely on actionability/auto-wait patterns rather than fixed sleeps.
- Infinite-scroll/load-more surfaces require explicit crawl-stop signals and duplicate detection.
- Bot/challenge handling should classify blocking states explicitly and branch retry policy accordingly.

These principles align with current implementation direction and guide the adjustments above.

## Implementation Notes by Layer

- **Contracts:** introduce scenario, challenge, and remediation dataclasses with versioned schemas.
- **Service (`publisher_inventory_service` + internals):** own preflight classifier, challenge detection, deferred verification I/O.
- **Generators:** keep screening/quality logic focused on semantic decisions; add confidence-tiered rescue decisions.
- **Orchestrator:** own remediation recipes, retry/backoff sequencing, and state updates.
- **README/Docs:** keep this playbook linked as the canonical optimization map for future discovery tuning.


## Reference Material

- Playwright Auto-waiting and actionability checks: https://playwright.dev/docs/actionability
- Google guidance on JS lazy-loading/discoverability patterns: https://developers.google.com/search/docs/crawling-indexing/javascript/lazy-loading
- Current in-repo discovery architecture and flow notes: `README.md` and `src/orchestrators/publisher_inventory_orchestrator.py`
