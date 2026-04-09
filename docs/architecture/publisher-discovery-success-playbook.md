# Publisher Discovery Success Playbook (2026-04-09)

## Why this playbook exists

The original version of this document was directionally right, but the current codebase has already implemented a large share of the early discovery hardening work. This rewrite re-baselines the playbook against the latest repository state, recent run logs, and live browser-use observations so the next changes target the real bottlenecks still limiting `discover-publisher-inventory`.

## Evidence base used

- Current discovery architecture and runtime flow:
  - `src/orchestrators/publisher_inventory_orchestrator.py`
  - `src/orchestrators/_publisher_inventory_route_planner.py`
  - `src/services/publisher_inventory_service.py`
  - `src/services/_publisher_inventory_fetch_service.py`
  - `src/services/_publisher_inventory_browser_service.py`
  - `src/services/_publisher_inventory_discovery_activity.py`
  - `src/generators/publisher_inventory_candidate_quality_generator.py`
  - `src/generators/publisher_inventory_coverage_generator.py`
  - `src/generators/publisher_inventory_run_quality_generator.py`
  - `src/contracts/publisher_inventory.py`
- Current config and repo documentation:
  - `src/config/app.yaml`
  - `README.md`
  - `docs/quality/report-discovery-download-review-2026-03-30.md`
- Current run-log validation window:
  - `logs/market_lense_2026-04-03.log`
  - `logs/market_lense_2026-04-08.log`
  - `logs/market_lense_2026-04-09.log`
- Live browser-use spot checks on representative surfaces:
  - `https://www.braze.com/product/reporting-analytics`
  - `https://www.capgemini.com/insights/research-library/ai-perspectives-2026`
  - `https://www.bain.com/insights?filters=|types(424%2C420)`
  - `https://www.cardlytics.com/research-and-insights`
- Recent git history:
  - multiple March-April 2026 `publisher discovery improvements` commits culminating in the current `main`

## Implementation update and live-gate result

The implementation plan is now fully landed in code and fixated by the mandatory live gate on 2026-04-09. The repo includes:

- new typed contracts for:
  - structured route traces
  - scenario summaries
  - deferred recovery recipes
  - recovery cache records
- persisted publisher discovery memory for:
  - `inventory_route_trace_json`
  - `inventory_scenario_summary_json`
- dedicated recovery-cache persistence via `publisher_inventory_candidate_recovery_cache`
- new rollout flags in `src/config/app.yaml`:
  - `enable_deferred_candidate_recovery`
  - `enable_structured_route_reuse`
  - `enable_preflight_classifier_and_direct_detail`
- service/runtime changes for:
  - landing-page verification classes
  - source-surface classification
  - recovery-recipe attachment on candidate-quality decisions
  - structured browser route-trace capture
  - preflight scenario classification
  - direct-detail short-circuit path
  - planner awareness of remembered route traces and scenario summaries
- automated regression coverage for:
  - report-store round-trip and migration
  - route-trace/scenario persistence
  - recovery-cache idempotency
  - direct-detail preflight short-circuit
  - recovery-recipe attachment
  - structured-memory planner precedence

Automated verification passed after the implementation update:

- `pytest tests/test_publisher_inventory_candidate_screening_generator.py tests/test_report_store_service.py tests/test_publisher_inventory_service.py tests/test_publisher_inventory_candidate_quality_generator.py tests/test_publisher_inventory_decomposition.py tests/test_publisher_inventory_orchestrator.py tests/test_config_service.py tests/test_cli.py -q`
- result: `247 passed`

The mandatory live gate passed on 2026-04-09.

### Live gate result on 2026-04-09

- Capgemini
  - command completed successfully
  - `run_quality_summary.outcome == accepted`
  - coverage verdict was `accepted`
  - preflight classified the page as `direct_detail_html`
  - the run completed through the direct-detail short-circuit without archive churn
  - the accepted asset was the direct report-detail page itself
- Bain
  - archive traversal progressed and extracted the filtered feed successfully
  - `run_quality_summary.outcome == accepted`
  - coverage verdict was `accepted`
  - snapshot upload completed successfully after the Google Drive fix
  - remembered-route reuse stayed active on the filter-heavy archive
- Cardlytics
  - command completed successfully
  - `run_quality_summary.outcome == accepted`
  - coverage verdict was `accepted`
  - the mixed-content hub preserved 3 strong editorial report-detail pages and qualified all 3 as `gated_report_asset`
- Structured-memory rerun
  - Cardlytics was rerun after the successful mixed-content fix
  - structured remembered-route reuse stayed active
  - the rerun remained `accepted`
  - snapshot quality did not regress and the canonical snapshot stayed stable

Current gate verdict:

- passed:
  - contract/persistence rollout
  - automated regression suite
  - structured route-trace persistence and reuse
  - direct-detail classifier reliably short-circuiting Capgemini-like pages in live operation
  - Bain end-to-end live success
  - Cardlytics mixed-content qualified-asset success
  - remembered-route rerun without quality regression

## Status after validation freeze

This playbook is now a fixated implementation record plus a hardening checklist for future discovery changes. The April 8 blockers are closed in the current codebase and validated against the live gate.

### Landed in code

- explicit route planning through `src/orchestrators/_publisher_inventory_route_planner.py`
- reusable run-quality summaries persisted for future route selection and drift review
- explicit coverage-validation verdicts:
  - `accepted`
  - `no_report_assets`
  - `raw_only_delta_rejected`
  - `undercoverage_regression`
  - `unreachable_delta_failure`
  - `unreachable_delta_tolerated`
- canonical service split between:
  - public boundary `src/services/publisher_inventory_service.py`
  - direct HTTP acquisition `src/services/_publisher_inventory_fetch_service.py`
  - browser acquisition `src/services/_publisher_inventory_browser_service.py`
  - pure traversal/extraction heuristics `src/services/_publisher_inventory_discovery_activity.py`
- deterministic direct HTTP candidate scoring before `http_parse` acceptance
- repeated-anchor pagination loop detection for HTTP discovery
- WordPress AJAX supplement for archives populated via `wp-admin/admin-ajax.php`
- browser-render traversal that now handles:
  - hydration waits
  - cookie dismissal scoped to consent containers
  - archive-preview expansion
  - tab traversal
  - report filter application
  - load-more expansion
  - same-page DOM growth pagination
  - button/next pagination
  - archive-root recovery
  - mirrored-host recovery
  - rendered HTML supplement
  - browser-to-HTTP recovery when browser output is sparse or retryably broken
- candidate provenance logging and persistence hints:
  - `browser_dom`
  - `browser_rendered_html_supplement`
  - `http_supplement`
  - `http_parse`
  - `http_parse_wordpress_ajax`
  - `direct_pdf_source`
- deterministic title cleanup for weak CTA-style card labels
- landing-page quality qualification with materially stronger semantic rejection rules
- bounded rescue for some non-dead verification failures:
  - anti-bot challenge pages
  - transient HTTP/timeouts
  - protected document/report pages with strong report signals
- canonical snapshot protection against noisy raw-only deltas and unreachable-only screened deltas
- typed publisher-memory persistence for:
  - structured route traces
  - scenario summaries
- dedicated candidate recovery-cache persistence keyed by normalized publisher URL plus canonical candidate URL
- landing-page verification classes persisted through the quality seam:
  - `verified`
  - `dead`
  - `challenge`
  - `transient_fetch_failure`
  - `protected_document`
  - `weak_signal_html`
- source-surface classification carried into quality decisions:
  - `archive_feed`
  - `direct_detail`
  - `mixed_content_hub`
  - `service_membership`
  - `research_hub`
  - `unknown`
- deferred recovery recipes attached to rejected high-confidence candidates when the verification failure is challenge/transient/protected rather than semantic rejection
- preflight scenario classification path and direct-detail short-circuit implementation

### Residual watch items after validation

- keep monitoring false positives on rescued editorial-detail pages so the Cardlytics-style fix does not broaden into generic blog/article acceptance
- continue sampling remembered scenario summaries on mixed-content hubs because those surfaces still drift faster than clean archives
- deferred recovery caching and typed recovery recipes are landed; continue measuring whether real challenge/protected/transient cases justify broader second-pass investment
- `publisher_discovery.force_browser: true` remains the archive-default posture, but validated preflight exceptions now allow direct PDF and high-confidence direct-detail short-circuits before browser traversal

## What the latest evidence says now

The current bottleneck order is different from the earlier version of this playbook.

### Final live-gate pattern from `logs/market_lense_2026-04-09.log`

- Capgemini completed as a direct-detail success:
  - `scenario_class == direct_detail_html`
  - `publisher_inventory_direct_detail_complete`
  - coverage verdict `accepted`
- Bain completed as a filter-heavy archive success:
  - remembered route reused
  - coverage verdict `accepted`
  - snapshot upload succeeded
- Cardlytics completed as a mixed-content qualified-asset success:
  - 30 raw candidates
  - 3 screened candidates
  - 3 qualified candidates
  - rerun stayed `accepted` with remembered-route reuse and no snapshot drift

Implication:

- the remaining live blockers from the April 8 gate are closed
- the validated loss point has moved from implementation gaps to ordinary ongoing precision monitoring

### Current log pattern from `logs/market_lense_2026-04-03.log`

- 60 completed discovery runs were observed in the sampled window.
- 52 completed as `accepted`.
- 8 completed as `no_report_assets`.
- 4 coverage checks failed as `unreachable_delta_failure`.
- 24 browser-to-HTTP recovery attempts were started.
- 19 of those browser-to-HTTP recoveries still failed.
- Candidate quality rejections clustered around:
  - `dead_or_unreachable_landing_page`: 109
  - `editorial_article_page`: 91
  - `service_or_membership_page`: 38
  - `insufficient_report_signals`: 23
  - `informational_article_page`: 14
  - `audio_editorial_page`: 14
- Provenance volume was dominated by `browser_dom`, with much smaller contributions from `http_parse`, `http_parse_wordpress_ajax`, and HTML supplements.

### Current log pattern from `logs/market_lense_2026-04-08.log`

- sampled runs were clean and memory-led:
  - 7 `accepted`
  - 7 `accepted` coverage verdicts
  - all 7 route plans reused remembered routes first

Implication:

- route reuse is working when the remembered route is already good
- the bigger remaining gap is not "browser cannot crawl archives at all"
- the bigger remaining gap is "the system still spends too much effort discovering candidates that later die in qualification or route recovery"

## Live browser-use observations

These spot checks matter because the browser service is built on local browser automation patterns, and the live pages show where deterministic traversal still needs more structure.

### 1. Mixed product surface with report language: Braze

Observed via `browser-use`:

- the page is a product/feature landing page, not a true report archive
- report-like language is present:
  - `2026 Global Customer Engagement Review`
  - `Reports & Guides`
- the surface is saturated with navigation, product CTAs, and non-inventory content
- cookie controls are visible and compete with meaningful controls

Implication:

- this is primarily a precision problem, not a traversal problem
- the system needs stronger inventory-surface affinity scoring before treating report-like text on a product page as evidence of a real inventory source

### 2. Direct-detail report page: Capgemini

Observed via `browser-use`:

- the page is already a specific report landing page
- the key action is immediate and explicit:
  - `Download the research brief`
- there is no archive traversal requirement on the page itself
- the cookie banner still overlays visible controls

Implication:

- the system should treat high-confidence direct-detail report pages as a first-class scenario
- once direct-detail confidence is high, archive heuristics should stop early instead of trying to generalize the page into an archive flow

### 3. Filtered archive with mixed content and cookies: Bain

Observed via `browser-use`:

- the page exposes a real inventory/feed surface
- visible filter state is present:
  - `Filter by`
  - `Types`
  - selected `Articles, Briefs, Reports`
- the page contains mixed content types, not only reports
- cookie controls are rendered inside a shadow-root widget and can overlap the inventory area

Implication:

- this is the strongest case for structured route memory
- route reuse should preserve filter state, visible feed context, and inventory-surface identity, not only a prose summary

### Browser-use operational note

The live audit also surfaced one tooling lesson: browser-use session reuse can leak page context when sessions are not isolated explicitly. The production service already mitigates related runtime drift with per-run session directories and stray-page cleanup, but test and audit workflows should isolate sessions deterministically as well.

## Re-ranked scenario matrix

### Scenario A - Qualification losses after otherwise successful discovery

**Observed failure mode**

- raw discovery finds large candidate sets
- the quality gate later rejects many items as:
  - unreachable
  - editorial
  - service/membership
  - insufficient-signal pages

**Why this is now the top priority**

- this is the biggest observed rejection cluster in recent logs
- route ordering alone will not fix it

**Adjustment**

- add stronger source-surface affinity to normalized candidates:
  - archive feed card
  - direct-detail report page
  - product/marketing page mention
  - research hub
  - service/membership hub
- carry this source-surface class into quality qualification
- let strong archive/detail provenance rescue borderline titles
- let weak provenance penalize report-like words on mixed product pages

**Status after latest code update**

- partially implemented through current URL/title/document heuristics
- still missing explicit source-surface contracts and weighting

**Expected impact**

- highest ROI
- fewer false positives entering quality checks
- fewer legitimate report candidates dying because the system lost source context

---

### Scenario B - Screened candidates fail as unreachable or challenge-protected

**Observed failure mode**

- `dead_or_unreachable_landing_page` is the largest quality rejection reason
- some failures are already tolerated or rescued
- recent logs still show systematic unreachable failure cases

**Adjustment**

- promote unreachable handling from an end-state verdict to a typed recovery workflow:
  - transient unreachable
  - anti-bot challenge
  - protected document
  - hard dead link
- add deferred second-pass verification for high-confidence report candidates only
- retry with alternate fetch profiles only when source confidence is high
- persist verification outcome so the same dead/challenged URLs do not churn every run

**Status after latest code update**

- partially implemented
- verdict handling exists
- bounded rescue exists
- no explicit second-pass recovery recipe engine exists yet

**Expected impact**

- major improvement on screened candidates that currently die before becoming qualified assets

---

### Scenario C - Archive traversal works, but memory is not structured enough

**Observed failure mode**

- the browser service now handles many archive shapes successfully
- remembered route reuse still stores free-text summary rather than explicit surface state
- filter-heavy pages such as Bain are sensitive to visible selected filters and surface-local controls

**Adjustment**

- replace prose-only memory learning with structured route trace contracts:
  - followed listing URL or not
  - report filter applied or not
  - selected tab labels
  - pagination mode
  - preferred control labels
  - candidate-surface guard enabled or not
  - final inventory-surface classification
- keep a human summary as secondary output, not the primary memory artifact

**Status after latest code update**

- still missing in the mainline discovery path

**Expected impact**

- stronger remembered-route reliability
- less route drift on mixed/filter-heavy publishers

---

### Scenario D - Direct-detail report pages should short-circuit earlier

**Observed failure mode**

- some publisher roots or provided URLs are already single report pages
- the system currently special-cases direct PDFs, but not full HTML report-detail pages as a first-class route

**Adjustment**

- add a direct-detail scenario classifier before full archive traversal
- classify:
  - direct PDF source
  - direct HTML report-detail source
  - archive/listing source
- when direct-detail confidence is high, emit single-item inventory immediately
- only fall back to archive traversal if detail confidence is weak or contradicted

**Status after latest code update**

- partially implied by current heuristics
- not yet formalized as a dedicated scenario path

**Expected impact**

- faster success on publishers whose configured insights URL is already the report landing page
- less noise from trying to generalize a detail page into an archive

---

### Scenario E - Route planning intelligence is still too shallow

**Observed failure mode**

- the planner currently mostly decides among:
  - remembered route
  - default plan
  - browser-first on drift
- `publisher_discovery.force_browser: true` means live behavior often bypasses nuanced route selection entirely

**Adjustment**

- add a lightweight preflight classifier before the main route plan:
  - direct-detail
  - filtered archive
  - tabbed archive
  - mixed-content hub
  - anti-bot/challenge-prone
  - likely JS-hydrated feed
- persist scenario memory separately from route memory
- once scenario confidence is trustworthy, reduce blanket `force_browser` usage and let route choice become evidence-driven again

**Status after latest code update**

- mostly not implemented

**Expected impact**

- medium-to-high
- especially valuable after the qualification and route-memory work lands

---

### Scenario F - Browser recovery is active but still too expensive

**Observed failure mode**

- browser-to-HTTP recovery was attempted 24 times in the sampled April 3 log window
- 19 of those recoveries still failed

**Adjustment**

- classify browser failures earlier into:
  - sparse but salvageable
  - clearly structurally empty
  - retryable runtime failure
  - route drift
- only attempt HTTP recovery when the failure shape suggests it can actually add signal
- log recovery-result class explicitly so low-yield recovery loops are visible

**Status after latest code update**

- partially implemented
- recovery exists, but its trigger policy is still broad

**Expected impact**

- lower wasted runtime
- cleaner failure taxonomy

## Implemented rollout summary

This plan assumes no architectural shortcuts. New behavior should stay inside the current modular-monolith boundaries:

- contracts define typed scenario, route-trace, and recovery models
- services own I/O and acquisition/verification behavior
- generators own semantic classification and qualification decisions
- orchestrators own sequencing, retry, memory updates, and remediation recipes

### Phase 1 - Precision and qualification rescue

**Status**

- landed and validated on 2026-04-09

**Goal**

- reduce candidate loss after discovery and convert more strong candidates into qualified assets

**Contracts**

- add `PublisherInventorySourceSurface` contract for candidate provenance class
- add `PublisherInventoryLandingRecoveryReason` contract for unreachable/challenge/protected/dead states
- add `PublisherInventoryRecoveryRecipe` contract for orchestrator-owned second-pass actions

**Services**

- extend landing-page inspection output with verification class:
  - `dead`
  - `challenge`
  - `transient_fetch_failure`
  - `protected_document`
  - `weak_signal_html`
- add alternate verification profile support for high-confidence candidates only

**Generators**

- add source-surface weighting into candidate quality decisions
- separate semantic rejection from recoverable verification failure
- keep final decision reasons explicit and typed

**Orchestrator**

- run deferred verification recipes only for:
  - high-confidence archive/detail candidates
  - screened candidates with recoverable verification class
- persist recipe outcome to prevent repeated churn

**Success condition**

- `dead_or_unreachable_landing_page` drops materially without inflating editorial false positives

**Success criteria**

- screened-to-qualified conversion improves on mixed-content and archive-backed publishers
- `dead_or_unreachable_landing_page` decreases without a matching rise in:
  - `editorial_article_page`
  - `service_or_membership_page`
  - `insufficient_report_signals`
- high-confidence archive/detail candidates are rescued selectively rather than globally
- repeated reruns on the same publisher stop churning on the same unreachable candidates once recovery outcomes are persisted

**Guardrails to avoid regressions**

- rescue logic must never bypass the existing landing-page quality gate for weak-provenance candidates
- editorial, case-study, service, and membership pages must remain hard rejects unless new evidence explicitly changes their classification
- second-pass verification must be bounded:
  - no unbounded retries
  - no broad retry of low-confidence candidates
- new recovery states must remain typed and logged; silent acceptance is not allowed
- snapshot protection rules for `raw_only_delta_rejected`, `no_report_assets`, and unreachable-only delta failures must remain intact

### Phase 2 - Structured route memory and direct-detail handling

**Status**

- landed and validated on 2026-04-09

**Goal**

- make successful routes reusable because they are explicit, not because they happened once

**Contracts**

- add typed route-trace contract:
  - `follow_report_listing`
  - `apply_report_filter`
  - `selected_filters`
  - `selected_tab_labels`
  - `pagination_mode`
  - `preferred_control_labels`
  - `candidate_surface_guard`
  - `surface_class`
- add direct-detail scenario contract

**Services**

- emit structured browser route observations from real traversal state
- detect high-confidence direct-detail pages before archive traversal escalates

**Generators**

- validate route-trace completeness
- classify detail-vs-archive scenario deterministically from page evidence

**Orchestrator**

- store structured route memory beside human-readable summary
- prefer structured route memory for reuse
- use direct-detail route when confidence is high

**Success condition**

- remembered routes succeed more consistently on filter/tab/load-more publishers
- single-detail report pages complete with less browser churn

**Success criteria**

- remembered-route reruns on structured archives show higher first-attempt success than prose-summary-only memory
- direct-detail pages complete without unnecessary archive traversal in the majority of high-confidence cases
- route memory captures enough explicit state to reproduce:
  - filter application
  - tab traversal
  - pagination mode
  - inventory-surface choice
- route reuse reduces browser churn on known publishers:
  - fewer exploratory actions
  - fewer archive-surface recovery detours
  - fewer browser-to-HTTP recovery attempts

**Guardrails to avoid regressions**

- structured route memory must remain secondary to real-time page validation:
  - stale memory must degrade to safe fallback, not force brittle replay
- direct-detail classification must not suppress archive traversal when detail confidence is weak or contradictory
- route memory promotion must require successful, complete runs; partial or ambiguous runs must not become primary memory
- new route-trace contracts must remain backward-compatible with existing stored route summaries unless an explicit migration is added
- route reuse must keep final snapshot quality equal to or better than fresh traversal on the same publisher

### Phase 3 - Scenario-aware planning and recovery budget control

**Status**

- landed and validated on 2026-04-09

**Goal**

- make planning evidence-driven instead of mostly default-driven

**Contracts**

- add preflight scenario classification response
- add planner input fields for:
  - scenario class
  - scenario confidence
  - recent recovery outcomes
  - failure signature summary

**Services**

- implement lightweight preflight classifier using page URL, cheap HTTP signals, and remembered run-quality evidence

**Generators**

- evaluate scenario confidence and memory health

**Orchestrator**

- move from:
  - remembered route else default
  to:
  - remembered route if healthy
  - otherwise scenario-guided route selection
- narrow browser-to-HTTP recovery triggers based on failure class
- review whether global `force_browser` can be relaxed safely for some scenario classes

**Success condition**

- planner reasons become scenario-specific
- blanket forced-browser behavior is reduced where not needed

**Success criteria**

- planner logs show explicit scenario-driven decisions instead of mostly default-plan reasons
- scenario classification correlates with better first-route selection on sampled publishers
- selective HTTP-first behavior returns where cheap/direct acquisition is actually sufficient
- browser-to-HTTP recovery attempts fall because low-yield recoveries are filtered earlier
- route selection changes improve or preserve accepted-run rate while reducing runtime waste

**Guardrails to avoid regressions**

- scenario classifiers must not become hidden policy; their verdicts and confidence must be logged explicitly
- no scenario should disable browser traversal permanently; planner decisions must still allow escalation paths
- reducing `force_browser` behavior must not regress known JS-heavy, tabbed, or filter-driven archives
- new planner logic must remain deterministic for the same inputs, memory state, and scenario evidence
- route selection complexity must stay bounded; if the planner becomes harder to reason about than the benefit it provides, rollout should pause

## Cross-cutting execution tracks

### Track 1 - Telemetry and KPI instrumentation

Add first-class metrics for:

- route success by scenario class
- quality rejection reasons by source-surface class
- deferred-verification rescue rate
- browser-to-HTTP recovery attempt rate and success rate
- remembered-route success rate by structured surface class
- direct-detail short-circuit rate

**Success criteria**

- each new scenario, recovery class, and route-memory mode is visible in logs and aggregate reporting
- operators can explain accepted, rejected, rescued, and fallback outcomes from stored telemetry alone
- KPI review can separate:
  - traversal failure
  - qualification rejection
  - unreachable verification failure
  - memory-reuse failure

**Guardrails to avoid regressions**

- telemetry additions must not remove existing structured fields used by current audits
- added metrics must stay tied to typed contracts rather than free-text parsing only
- logging volume must remain bounded enough for routine batch analysis

### Track 2 - Browser-use runtime hygiene

Use the live browser-use lessons operationally:

- isolate audit sessions explicitly
- log active page URL timeline for discovery runs
- preserve final visible surface state when browser output is sparse
- keep stray-page cleanup and archive-surface recovery explicit and testable

**Success criteria**

- audit and smoke runs produce isolated, reproducible browser observations
- session leakage and cross-page contamination stop appearing in validation workflows
- sparse browser outputs still retain enough visible-state evidence for diagnosis

**Guardrails to avoid regressions**

- runtime hygiene changes must not slow normal discovery execution materially
- cleanup logic must not close the active inventory page or erase useful evidence before capture
- added evidence capture must remain bounded in storage and execution cost

### Track 3 - Documentation and runbook maintenance

After each phase:

- move landed items from “build” to “harden” or “done”
- update the README discovery section if behavior changes materially
- keep scenario names aligned across docs, logs, contracts, and tests

**Success criteria**

- the playbook stays aligned with shipped code rather than drifting into a stale future-work list
- scenario naming remains consistent across:
  - contracts
  - logs
  - tests
  - docs
- implementation status can be understood without re-auditing the whole codebase

**Guardrails to avoid regressions**

- no major discovery behavior change should land without updating the playbook or README when user-facing/operator-facing behavior changes
- docs must distinguish clearly between:
  - landed
  - partially landed
  - planned

## KPI targets and rollout guards

### Primary KPIs

- accepted discovery run rate
- `no_report_assets` rate
- `unreachable_delta_failure` rate
- quality rejection rate by reason
- browser-to-HTTP recovery success rate
- remembered-route reuse success rate
- qualified delta yield:
  - raw -> screened
  - screened -> qualified

### Suggested 30-day monitoring targets after validation freeze

- reduce `dead_or_unreachable_landing_page` rejections by at least 30%
- reduce browser-to-HTTP recovery failure count materially from the current April 3 sample
- improve screened-to-qualified conversion on mixed-content hubs
- keep `editorial_article_page` precision strong while rescue logic expands

### Rollback guards

- if editorial false positives rise, roll back source-surface rescue weighting first
- if unreachable rescue starts admitting dead pages, disable second-pass rescue but keep typed failure logging
- if structured route memory adds complexity without reuse gain, keep logs but stop planner promotion until confidence improves

## Regression coverage required to keep the rollout safe

### Services

- landing-page inspection tests that distinguish:
  - dead page
  - challenge page
  - transient fetch failure
  - protected document
  - weak-signal mixed-content page
- browser recovery tests asserting when HTTP recovery is allowed vs blocked

**Success criteria**

- service tests prove that new verification classes are emitted deterministically for the same inputs
- recovery-trigger tests prove that low-yield HTTP recovery does not fire indiscriminately

**Guardrails to avoid regressions**

- tests must assert typed outputs, not only broad success/failure status
- existing landing-page inspection semantics for current accepted and rejected cases must stay covered

### Generators

- source-surface weighting tests for:
  - archive-card candidate
  - direct-detail candidate
  - product-page mention
  - service/membership hub candidate
- quality tests asserting recoverable-vs-non-recoverable failure taxonomy

**Success criteria**

- generator tests show that provenance/surface weighting changes the decision only where intended
- qualification tests prove that recovery-eligible candidates and hard rejects are still separated cleanly

**Guardrails to avoid regressions**

- no test should pass if source-surface weighting is removed from the new code path it claims to validate
- editorial and service-page rejection coverage must remain present while rescue logic expands

### Orchestrators

- deferred verification recipe tests
- structured route-memory persistence and reuse tests
- planner tests that consume scenario class and recovery history explicitly
- idempotency tests ensuring repeated deferred verification does not duplicate persistence side effects

**Success criteria**

- orchestrator tests prove retry count, state transitions, and persistence outcomes for each new recipe path
- repeated reruns show stable idempotent behavior with no duplicate side effects

**Guardrails to avoid regressions**

- deferred verification must not create duplicate report-source writes or noisy snapshot churn
- memory updates must not occur on failed or partial runs
- planner and recovery branches must preserve current coverage-validation protections

### Live/smoke coverage

- one direct-detail page
- one filter-heavy archive
- one mixed-content hub
- one challenge-prone or intermittently protected candidate set
- one remembered-route rerun on a structured archive

**Success criteria**

- each smoke case maps to one of the target scenario classes in this playbook
- smoke reruns demonstrate at least one reuse-oriented case and one recovery-oriented case

**Guardrails to avoid regressions**

- smoke coverage must include both precision-sensitive and traversal-sensitive publishers
- new smoke wins must not come from silently relaxing the quality bar on mixed-content hubs

## Summary recommendation

If only three changes should be prioritized next, they should be:

1. source-surface-aware qualification and unreachable recovery
2. structured route memory for filter/tab/load-more archives
3. direct-detail and scenario-aware preflight classification

That ordering matches the latest codebase and observed runs better than the earlier version of this playbook. The discovery engine is no longer mainly missing archive traversal mechanics. It is now strong enough that the next gains come from better semantic precision, better recovery of high-confidence candidates, and better reuse of successful traversal knowledge in typed form.
