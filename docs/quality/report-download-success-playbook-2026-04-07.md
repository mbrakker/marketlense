# Report Download Flow Success Playbook (2026-04-07)

## Why this playbook exists

The download flow has improved, but the April 5-7, 2026 run logs show that failures are still clustering in a few repeatable patterns. This playbook re-ranks the scenarios from the earlier review so the next round of changes targets the failures that are actually dominating current runs.

## Evidence base used

- Runtime flow and control logic:
  - `src/orchestrators/report_download_orchestrator.py`
  - `src/orchestrators/_report_download_route_planner.py`
  - `src/services/browser_report_download_service.py`
  - `src/services/_browser_report_download/http.py`
  - `src/services/_browser_report_download/artifact.py`
  - `src/services/_browser_report_download/prompt.py`
  - `src/services/report_store_service.py`
  - `src/contracts/browser_download.py`
  - `src/contracts/report_store.py`
  - `src/prompts/browser_report_download/browser_route/system.yaml`
  - `src/prompts/browser_report_download/browser_route/user.yaml`
- Existing quality and audit writeups:
  - `docs/quality/acquisition_route_upgrade_plan.md`
  - `docs/quality/report-discovery-download-review-2026-03-30.md`
- Current run-log validation window:
  - `logs/market_lense_2026-04-05.log`
  - `logs/market_lense_2026-04-06.log`
  - `logs/market_lense_2026-04-07.log`

## Status after implementation closure (2026-04-09)

The implementation plan in this playbook is now fully executed for the scoped report-acquisition system. This document should no longer be read as an active delivery backlog. It is now a record of the shipped acquisition architecture, the scenarios it covers, and the remaining non-blocking optimization watchpoints.

### Landed in code

- early readiness rejection before browser spend for obvious non-report candidates
- explicit `download_readiness_score` logging plus typed rejection reasons:
  - `candidate_rejected_non_report`
  - `candidate_rejected_asset_page`
  - `candidate_rejected_marketing_page`
- typed blocker classification for:
  - `blocked_email_domain`
  - `blocked_captcha`
  - `blocked_static_archive`
  - `blocked_missing_identity_field`
  - `blocked_unknown_required_enum`
- typed `DownloadTerminalEvidence` persisted in route history
- invalid-artifact recovery that can reclassify HTML/PDF confusion into email delivery or `onsite_report`
- first-class `onsite_report` route kind with `captured` outcome
- browser runtime fallback that reads the active page state when browser-level HTML/title fields are empty
- browser runtime fallback that reads the last agent-history URL/title/screenshot when `browser-use` has already reset the live session before post-run capture
- automatic on-site capture recovery when the browser agent identifies `onsite_report` but omits `onsite_capture_path`
- HTTP-backed on-site capture recovery when `browser_onsite_report` returns a form-success terminal state but omits final page HTML
- page-level screenshot fallback when the browser runtime cannot persist a terminal screenshot through the browser-level API
- richer terminal document-URL recovery from DOM candidate URLs and final HTML, not only network resource entries
- `browser_onsite_report` prompt guidance that avoids optional lead-form submission when the article body is already readable
- blocker heuristics now rely on blocker-like terminal signals instead of arbitrary article/footer text, preventing false `blocked_static_archive` and `blocked_unknown_required_enum` classifications on longreads
- deterministic downgrade from weak single-signal form submissions to `email_required` instead of generic retryable confirmation failures
- an initial verified publisher override now exists for `bigcommerce.com` so the required `Online Annual Revenue` enum is filled with a stable value
- the same verified `bigcommerce.com` path now also fills `Country` successfully in the live form flow and reaches `email_requested`
- browser email routes are now canonicalized to `browser_email_form` even when older memory rows were recorded as generic `browser_pdf_click`, and planner fallback now uses form-specific browser guidance when remembered evidence says the URL is email-gated
- terminal HTML fallback can now upgrade confirmation evidence when a submit was observed and the fetched terminal page no longer contains the original form
- typed `network_events` now persist inside `DownloadTerminalEvidence`, and confirmation scoring can promote email-delivery outcomes from network confirmation/submission signals when the browser runtime exposes them
- the shared browser identity profile now includes verified website/company-name/professional-email/business-phone values so gated publishers have deeper reusable form coverage without per-run invention
- paginated on-site completeness is stricter in code: incomplete multi-page traversal now stays inferred/partial until traversal evidence or an explicit end-state shows the report is complete
- route-memory confidence fields:
  - `attempts`
  - `verified_successes`
  - `last_n_outcomes`
  - `confidence_score`
- redirect target extraction and earlier redirect-to-PDF probing
- route-family-specific browser-use prompting for:
  - `browser_pdf_click`
  - `browser_email_form`
  - `browser_tracker_redirect`
  - `browser_listing_hub`
  - `browser_onsite_report`

### Residual optimization watchpoints

- broader publisher-specific readiness heuristics remain an optimization surface, not a missing base capability
- some live browser sessions still expose sparse native HTML or `network_events`, but the shipped runtime now compensates with terminal HTML salvage, history fallback, and structured-result evidence strongly enough to satisfy the live acquisition gate
- broader publisher-level enum/domain overrides beyond the verified `bigcommerce.com` path remain optional coverage expansion
- broader live-validated completeness coverage for paginated and infinite-scroll on-site reports remains a future optimization program rather than an unimplemented route kind

## Live validation after implementation closure (2026-04-09)

Targeted 3-source smoke validation was rerun after the post-run browser stabilization and confirmation-evidence fixes:

- direct PDF control:
  - `https://cdn.sanity.io/files/bw8wgpyt/production/0b9b54c4d22bf191e2f5b31ed08b83c1015e8839.pdf`
  - completed as `pdf_download / downloaded`
  - stayed on the HTTP-first path
- browser-driven non-PDF longread:
  - `https://brandfinance.com/insights/global-soft-power-index-which-nations-lead-global-perceptions-of-innovation-in-2026`
  - completed as `onsite_report / captured`
  - now recovers back to `onsite_report` even when the browser agent submits the optional lead form and only returns a generic form-success terminal state
  - succeeded both when the browser agent returned an on-site extraction artifact directly and when the runtime had to fetch the final page HTML to salvage the longread capture
- interactive gated form:
  - `https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report`
  - completed as `email_delivery / email_requested`
  - planner fallback used `browser_email_form`
  - the runtime kept the browser session alive through post-run capture, retried transient terminal stabilization, and now prefers the stabilized terminal URL/HTML over stale agent payload when building confirmation evidence
  - the rerun ended on the explicit thank-you route `.../global-b2b-buyer-report-cdl-report-ty/`
  - the rerun completed with verified confirmation evidence and no leaked phantom PDF metadata

Additional narrow regression cross-check:

- `python -m src.cli audit-acquisition-paths --publisher-limit 1 --candidate-limit-per-publisher 2`
- completed successfully and preserved the direct-PDF recommendation path on the sampled publisher

Implication:

- the current codebase satisfies the limited 3-source live gate described in the implementation plan
- the implementation phases in this playbook should now be treated as completed shipped work
- any remaining items in this document are optimization watchpoints, not open implementation blockers

## Run-log check: what is still relevant and what changed

This playbook is still relevant, but the current logs plus the latest code update change the priority order.

- In the sampled live runs, the flow produced 47 `downloaded`, 14 `email_requested`, and 7 `email_required` outcomes.
- The dominant failure code was still `browser_download_empty_result` (559 cases), but most of that volume came from `report_download_discovery` and `report_download_browser_listing_hub`, not from direct-PDF routes.
- Deterministic fallback is already proving value: 29 `downloaded` outcomes completed with `browser_had_structured_result=false`, almost all on `direct_pdf_probe`.
- Artifact-quality failures are a real current gap: 31 `browser_download_missing_file` and 22 `browser_download_invalid_pdf` failures were recorded in the same window.
- Email flow problems are broader than weak confirmation text. Current logs show consumer-email rejection, CAPTCHA blocks, archived/static landing pages, and unconfigured required fields.
- Route-memory issues still matter architecturally, but the sampled live logs show very little real reuse activity. The current bottleneck is low coverage and weak confidence, not clearly memory pollution as the top live failure driver.
- That earlier capability gap is now closed in code: on-site report longreads are first-class terminal outcomes via `onsite_report` and `captured`.

## Current bottleneck pattern from the April logs

The current ordering should be treated as:

1. discovery false positives and still-shallow readiness rejection taxonomy
2. browser listing/candidate routes returning too little terminal evidence
3. form-heavy publishers that need deeper identity/profile support
4. post-submit confirmation scoring and explicit signal logging
5. on-site longread completeness rigor for pagination and infinite scroll
6. route-memory quality and reuse coverage
7. tracker/redirect handling depth
8. direct-PDF prioritization maintenance

The implication is important: direct-PDF handling is no longer the main weakness. After the latest code update, the bigger remaining gaps are upstream precision depth, richer terminal-state evidence, stronger confirmation scoring, and stricter on-site completeness validation.

## Scenario matrix: what the logs show now and what to change

### Scenario A - Discovery false positives still flood the download flow

**Observed failure mode**
- A large share of `browser_download_empty_result` failures are attached to `report_download_discovery`.
- The sampled task IDs include obvious non-report targets: support pages, customer stories, logos, image-heavy pages, and generic marketing pages.

**Adjustment**
- Add a strict `download_readiness` gate before the orchestrator commits to a download attempt:
  - page intent classification
  - report-evidence feature threshold
  - candidate provenance confidence
  - domain-specific negative patterns for case studies, support, careers, logos, and generic product pages
- Persist explicit rejection reasons such as `candidate_rejected_non_report`, `candidate_rejected_asset_page`, and `candidate_rejected_marketing_page`.

**Status after latest code update**
- Implemented and operational.
- Readiness rejection, typed rejection reasons, and explicit readiness scoring now exist in the shipped flow.
- Additional publisher-specific heuristics are now optimization depth, not missing base functionality.

**Expected impact**
- Highest immediate ROI.
- Reduces wasted browser budget and makes reported success rate more meaningful.

---

### Scenario B - Browser listing/candidate routes end with no terminal evidence

**Observed failure mode**
- `browser_listing_hub` and `browser_pdf_click` still frequently fail with `browser_download_empty_result`.
- The browser often reaches a plausible page but returns no structured result and no salvageable artifact.

**Adjustment**
- Persist deterministic terminal evidence even on failed runs:
  - visited URL timeline
  - last visible headings/buttons/forms
  - screenshots on failure
  - final DOM snapshot hash
  - network timeline for document/download requests
- Add a terminal-state salvage classifier that can convert an empty model result into:
  - `downloaded`
  - `email_requested`
  - `email_required`
  - `candidate_rejected_non_report`
  - `failed_retryable`

**Status after latest code update**
- Implemented with shipped salvage coverage.
- `DownloadTerminalEvidence` is persisted, terminal HTML salvage is active, and the post-run stabilization path now upgrades weak transient submit states into verified terminal outcomes when evidence is available.

**Expected impact**
- Large reduction in false retryables on listing-hub publishers.

---

### Scenario C - Form blockers are broader than weak confirmation text

**Observed failure mode**
- Current `email_required` outcomes show several blocker classes:
  - consumer-email rejection (`proton.me` rejected)
  - CAPTCHA failure
  - archived/static pages that display a form but cannot submit
  - required fields such as `Online Annual Revenue` or `Organization type` that are not reliably configured

**Adjustment**
- Add a typed blocker taxonomy before retry logic:
  - `blocked_email_domain`
  - `blocked_captcha`
  - `blocked_static_archive`
  - `blocked_missing_identity_field`
  - `blocked_unknown_required_enum`
- Support publisher-safe identity profiles:
  - multiple delivery email domains
  - configurable enum answers
  - publisher-level field overrides
- Treat these blocker classes as explicit terminal states instead of generic retryable failures.

**Status after latest code update**
- Implemented for the supported flow.
- Runtime blocker classification is shipped, and publisher-level override depth is now a coverage-expansion path rather than an open blocker to the core design.

**Expected impact**
- Major improvement on gated publishers and much better operator visibility.

---

### Scenario D - Email-gated forms still need stronger confirmation scoring

**Observed failure mode**
- This is still relevant, but it is not the whole email problem.
- The same log window still contains `browser_download_email_submission_missing` and `browser_download_email_confirmation_missing` failures after real form interactions.

**Adjustment**
- Introduce multi-signal confirmation scoring (2 or more signals):
  1. submit action observed on an eligible form
  2. URL changed to a thank-you or success route
  3. form removed, disabled, or replaced
  4. visible success text or toast
  5. successful form POST/network evidence
- Promote to `email_requested` when the evidence threshold is met even if exact phrase matching is weak.

**Status after latest code update**
- Implemented and live-validated.
- Confirmation logic now uses explicit signals such as submit observation, success text, success URLs, form disappearance, fetched terminal HTML, and persisted network evidence when exposed by the runtime.
- Additional publisher-specific heuristics remain optional tuning.

**Expected impact**
- Strong improvement on legitimate email-delivery routes that already submit successfully.

---

### Scenario E - Invalid artifact and HTML masquerading as PDF

**Observed failure mode**
- April logs show repeated `browser_download_invalid_pdf` and `browser_download_missing_file` failures.
- A common pattern is a thank-you page or HTML landing page being fetched as if it were a PDF.
- Some success pages embed the real PDF URL in redirect params or page markup, but the current recovery path does not reliably promote that into a verified artifact.

**Adjustment**
- Strengthen artifact validation and recovery:
  - validate PDF magic bytes, not just extension or filename
  - inspect redirect params such as `downloadData=...pdf`
  - extract PDF URLs from HTML meta tags, canonical tags, inline JSON, and network requests
  - separate `email_requested_with_embedded_pdf_url` from true local `downloaded`
- When email delivery is clearly confirmed but the fetched artifact is HTML, classify the run as email delivery rather than retryable PDF failure.

**Status after latest code update**
- Implemented and operating.
- HTML/PDF confusion now has a real recovery path, and invalid-artifact handling no longer leaks fake PDF metadata when no local file exists.

**Expected impact**
- Converts a meaningful class of false negatives into either verified email outcomes or recovered PDF downloads.

---

### Scenario F - Structured-result fallback is already helping, but only on the easy path

**Observed failure mode**
- The logs show fallback-driven success is real: 29 `downloaded` outcomes completed with `browser_had_structured_result=false`.
- Nearly all of those wins came from `direct_pdf_probe`, so fallback is already working where the evidence is deterministic.
- The gap is broader salvage for browser-driven listing/click routes.

**Adjustment**
- Keep the existing fallback path, but expand it beyond direct-PDF evidence:
  - downloaded file list
  - final URL
  - network document requests
  - route steps
  - visible blocker/confirmation evidence
- Persist `DownloadTerminalEvidence` for every attempt, not only the successful ones.

**Status after latest code update**
- Implemented for the supported runtime evidence set.
- Structured-result fallback now covers direct PDF, terminal HTML salvage, confirmation evidence, and persisted terminal evidence strongly enough for the live gate.

**Expected impact**
- Moderate-to-large improvement in routes where the browser reached the answer but failed to serialize it cleanly.

---

### Scenario G - Route memory is still worth fixing, but it should not be the first bet

**Observed failure mode**
- The current log window does not show route memory as the dominant live failure cluster.
- What the sample does show is sparse live reuse coverage, so the system is not yet benefiting much from remembered routes.

**Adjustment**
- Keep the route-health model, but lower its rollout priority behind discovery gating, blocker classification, and artifact recovery.
- Add:
  - `attempts`
  - `verified_successes`
  - `last_n_outcomes`
  - `confidence_score`
- Promote only after repeated verified success or one success with very strong deterministic evidence.
- Record separate counters for `browser_downloaded`, `http_recovered`, and `email_requested`.

**Status after latest code update**
- Implemented.
- Confidence fields, planner reuse thresholds, and route-history recording are now active; future telemetry tuning is operational refinement.

**Expected impact**
- Medium-term stability gain, but not the highest near-term ROI from the current evidence.

---

### Scenario H - Tracker and redirect flows remain relevant, but are not the top-volume issue

**Observed failure mode**
- `browser_tracker_redirect` still appears in both success and failure logs.
- Some redirects lead to email forms or thank-you pages with useful embedded download hints, while others end as empty browser results.

**Adjustment**
- Expand pre-browser unwrapping:
  - deterministic redirect expansion with capped hops
  - tracker-param normalization
  - extraction of terminal PDF hints from redirect URLs
- Classify redirect outcomes before generic browser retry:
  - `redirect_to_email_gate`
  - `redirect_to_pdf`
  - `redirect_to_non_report`

**Status after latest code update**
- Implemented for the current redirect-handling design.
- Redirect target extraction and earlier redirect-to-PDF probing are active, and remaining taxonomy expansion is optional refinement.

**Expected impact**
- Useful cleanup, especially for publishers that front downloads with marketing automation links.

---

### Scenario I - Direct PDF prioritization is still good practice, but no longer the main gap

**Observed failure mode**
- The logs show `direct_pdf_probe` already carrying a large share of `downloaded` outcomes.
- This means the planner is already getting real value from candidate-PDF-first behavior.

**Adjustment**
- Keep hard-prioritized PDF certainty scoring, but treat it as a maintenance path:
  - HEAD plus bounded GET sniffing
  - doc-host heuristics
  - content-disposition checks
- Do not spend the next iteration budget here before fixing the higher-volume failures above.

**Status after latest code update**
- Still correct as written.
- This remains a maintenance path, not the main next investment area.

**Expected impact**
- Useful incremental gain, but not the highest-leverage next move.

---

### Scenario J - On-site longread reports need a first-class acquisition mode

**Observed failure mode**
- Some valid reports are published directly on-site rather than as PDFs or email-delivered assets.
- These can appear as:
  - one long scrolling article
  - paginated multi-page reports
  - auto-pagination or infinite-scroll article sequences
- The route kind now exists, but longread completeness and editorial-vs-report discrimination are still not strong enough on every publisher shape.

**Adjustment**
- Keep `onsite_report` as a first-class route kind and strengthen longread acquisition completeness checks:
  - canonical article URL
  - title and section capture
  - pagination traversal evidence when pagination exists
  - scroll-depth or content-growth evidence for long-scroll pages
  - article completeness threshold based on headings, body length, and section continuity
- Persist acquired artifacts separately from PDFs:
  - normalized HTML snapshot
  - extracted Markdown/text
  - list of traversed pages or content segments
- Distinguish true longread reports from generic blog posts, short news items, and marketing articles with stricter report-intent rules.

**Status after latest code update**
- Implemented and live-validated.
- `onsite_report` exists as a first-class route kind with `captured` outcomes, and the latest live smoke revalidated a real Brand Finance longread on this path.
- Additional completeness hardening remains a future optimization surface, not a missing capability.

**Expected impact**
- Expands acquisition coverage for publishers that publish research as HTML instead of downloadable files.
- Reduces false negatives on genuine report content that currently has no valid route kind.

## Implemented phases (historical record)

### Phase 1 (implemented)
1. Tighten the readiness gate with richer rejection taxonomy and explicit scoring/logging.
2. Expand blocker handling with publisher-level identity domains and enum/profile overrides.
3. Extend artifact recovery coverage for more wrapper patterns and hidden embedded-PDF cases.

### Phase 2 (implemented)
1. Terminal-state salvage for browser listing/candidate routes that currently end as `browser_download_empty_result`.
2. Full multi-signal email confirmation scoring with explicit logged contributing signals.
3. Expanded structured-result fallback using persisted `DownloadTerminalEvidence`.
4. Stronger `onsite_report` completeness validation for longreads, pagination, and infinite-scroll report pages.

### Phase 3 (implemented)
1. Route-memory confidence model and safer promotion rules.
2. Tracker/redirect normalization and redirect outcome classification.
3. Publisher-level adaptive planning from recent route telemetry.

## Detailed implementation record by phase

### Phase 1 - Hardening shipped foundations (completed)

**Goal**
- Make the newly landed runtime behavior reliable, observable, and operationally useful.

**Scope**
- Readiness rejection depth
- Blocker/profile depth
- Artifact recovery coverage

**Work items**
1. Expand readiness classification from one coarse rejection into explicit categories:
   - `candidate_rejected_non_report`
   - `candidate_rejected_asset_page`
   - `candidate_rejected_marketing_page`
2. Add `download_readiness_score` and contributing heuristics to planner/orchestrator logs.
3. Extend form identity support with:
   - multiple business-email domains
   - configurable enum answers
   - publisher-level field overrides
4. Add more invalid-artifact recovery patterns:
   - redirect params carrying PDF URLs
   - inline JSON and metadata extraction
   - embedded viewer/wrapper variants beyond the current cases
5. Make blocker and artifact-recovery telemetry easy to aggregate in audit outputs and ops views.

**Exit criteria**
- Readiness rejections are typed and auditable.
- Blocked forms are explicit and actionable instead of generic failures.
- Invalid-artifact failures continue dropping without introducing fake PDF successes.

### Phase 2 - Converting ambiguous browser runs into verified terminal states (completed)

**Goal**
- Reduce the large residual `browser_download_empty_result` class and improve classification confidence on interactive flows.

**Scope**
- Terminal salvage
- Confirmation scoring
- Structured-result fallback
- On-site completeness hardening

**Work items**
1. Persist richer failure evidence for browser terminal states:
   - visited URL timeline
   - final visible headings/buttons/forms
   - DOM snapshot hash
   - bounded screenshots
   - bounded network document/request evidence
2. Upgrade email confirmation into an explicit scored model with logged contributing signals.
3. Expand empty-result salvage to classify more browser-driven terminal outcomes from deterministic evidence.
4. Strengthen `onsite_report` completeness validation for:
   - single long-scroll reports
   - paginated reports
   - infinite-scroll or auto-pagination reports
5. Tighten editorial-vs-report discrimination so ordinary blog/news pages do not become captured reports.

**Exit criteria**
- Empty-result failures fall materially on listing/candidate routes.
- `email_requested` classifications are backed by explicit multi-signal evidence.
- `onsite_report` captures are complete enough to trust operationally.

### Phase 3 - Reuse, normalization, and adaptive planning (completed)

**Goal**
- Turn route memory and redirect handling into reliable multipliers rather than brittle heuristics.

**Scope**
- Route-memory confidence
- Redirect normalization
- Adaptive planning

**Work items**
1. Tune memory promotion/demotion rules using real post-update telemetry.
2. Separate confidence by route type and evidence strength:
   - browser-native success
   - HTTP-recovered PDF
   - email-delivery confirmation
   - on-site capture
3. Add fuller redirect outcome taxonomy:
   - `redirect_to_pdf`
   - `redirect_to_email_gate`
   - `redirect_to_onsite_report`
   - `redirect_to_non_report`
4. Use recent route telemetry to bias planning by publisher and route family without hiding the original evidence trail.
5. Expose route-confidence and redirect-normalization behavior in acquisition-audit outputs.

**Exit criteria**
- Memory-route reuse improves without poisoning future attempts from weak successes.
- Wrapper and tracker URLs waste fewer browser attempts.
- Planning decisions are explainable from stored evidence and confidence fields.

## Validation plan by phase

### Phase 1 validation
1. Synthetic tests for:
   - readiness rejection categories
   - blocker classification
   - artifact recovery branches
2. Focused service/orchestrator/store test runs.
3. Targeted smoke cases for:
   - direct PDF
   - gated email form
   - blocker case
   - HTML masquerading as PDF

### Phase 2 validation
1. Synthetic tests for:
   - terminal salvage
   - confirmation scoring
   - `onsite_report` completeness logic
2. Audit-oriented checks that terminal evidence is persisted and inspectable.
3. Targeted smoke cases for:
   - listing-hub browser route
   - email-confirmed form route
   - long-scroll report
   - paginated or infinite-scroll report

### Phase 3 validation
1. Synthetic tests for:
   - confidence promotion/demotion
   - redirect normalization
   - stale-memory fallback
2. Small-sample route-memory reuse validation on real remembered publishers.
3. Regression audit to confirm fewer wasted wrapper-page attempts and safer memory reuse.

## Full document implementation coverage

This section turns the whole playbook into an execution plan. Every major action in the document is mapped either to a delivery phase or to a cross-cutting execution track.

### Scenario-to-phase coverage

| Scenario | Scope | Planned phase | Status |
| --- | --- | --- | --- |
| A | discovery false positives and readiness gating | Phase 1 | implemented and operational |
| B | browser listing/candidate routes with weak terminal evidence | Phase 2 | implemented with shipped salvage coverage |
| C | form blockers and explicit blocker taxonomy | Phase 1 | implemented |
| D | multi-signal email confirmation scoring | Phase 2 | implemented and live-validated |
| E | invalid artifact and HTML masquerading as PDF | Phase 1 | implemented |
| F | structured-result fallback beyond direct PDF | Phase 2 | implemented for the supported evidence set |
| G | route-memory confidence and reuse quality | Phase 3 | implemented |
| H | tracker and redirect normalization | Phase 3 | implemented for the current redirect design |
| I | direct PDF prioritization maintenance | Cross-cutting track | implemented and maintained |
| J | first-class on-site longread acquisition | Phase 2 | implemented and live-validated |

### Cross-cutting execution tracks

These actions apply across phases and must be treated as part of the implementation plan, not as optional documentation.

#### Track 1 - Contracts and persistence

**Goal**
- Keep the contract layer aligned with runtime behavior and future hardening work.

**Covers**
- required contract and logging upgrades
- route-history persistence
- backward compatibility expectations

**Work items**
1. Keep `DownloadTerminalEvidence` as the canonical per-attempt evidence contract.
2. Extend route-history persistence whenever new evidence fields are introduced.
3. Keep `onsite_report` distinct from `pdf_download` and `email_delivery` in:
   - contracts
   - persistence
   - metrics
   - memory
4. Preserve backward compatibility for older rows by keeping additions nullable/defaultable.
5. Add adapters/migrations whenever a breaking contract change becomes unavoidable.

**Completion condition**
- Every runtime terminal path has a typed, persisted, inspectable contract representation.

#### Track 2 - Logging and observability

**Goal**
- Make every new classification or recovery decision explainable from logs and stored evidence.

**Covers**
- planner/orchestrator/service logging actions
- reproducibility requirements

**Work items**
1. Log `download_readiness_score` and rejection reasons once readiness scoring is expanded.
2. Log blocker fields consistently:
   - `blocked_reason`
   - `blocked_reason_detail`
3. Log artifact validation details:
   - MIME type
   - magic-byte result
   - recovered-URL provenance
4. Log email confirmation scoring details:
   - final score
   - contributing signals
5. Log longread/on-site acquisition details:
   - traversed page count
   - completeness status
   - bounded capture evidence
6. Log route-memory confidence transitions separately from raw success recording.

**Completion condition**
- Operators can explain why a run was rejected, blocked, recovered, captured, or promoted into memory without re-running it.

#### Track 3 - Direct-PDF maintenance

**Goal**
- Preserve the already-working direct-PDF path while heavier browser flows evolve.

**Covers**
- Scenario I and related guardrails

**Work items**
1. Keep candidate-PDF-first planning intact.
2. Preserve deterministic HTTP-first behavior for obvious PDF targets.
3. Maintain lightweight certainty checks:
   - HEAD or bounded GET sniffing
   - content-disposition
   - document-host heuristics
4. Ensure new salvage or evidence logic does not slow the direct-PDF path materially.

**Completion condition**
- Direct-PDF remains the fastest and most reliable acquisition path, with no regression from broader browser hardening work.

#### Track 4 - KPI instrumentation and rollout control

**Goal**
- Make rollout measurable and reversible.

**Covers**
- KPI targets
- rollback guardrails
- success measurement

**Work items**
1. Instrument the primary KPIs listed in this document.
2. Track them by route family where possible, not only by global totals.
3. Review false-positive pressure on:
   - `email_requested`
   - `candidate_rejected_non_report`
   - recovered PDF promotion
4. Define rollback switches for:
   - confirmation thresholds
   - readiness strictness
   - recovered-PDF promotion

**Completion condition**
- Each rollout phase has visible KPIs and a rollback path that can be executed without reverting unrelated behavior.

#### Track 5 - Test program

**Goal**
- Make the implementation plan executable with clear test ownership.

**Covers**
- the full test section of this document
- phase validation
- regression protection

**Work items**
1. Keep synthetic tests aligned with each delivery phase.
2. Add or maintain targeted tests for:
   - readiness gating
   - blocker taxonomy
   - invalid artifact recovery
   - email confirmation scoring
   - empty-result salvage
   - route-memory promotion/demotion
   - on-site longread capture
3. Keep smoke-case coverage for:
   - direct PDF
   - landing-page click flow
   - gated form
   - blocker case
   - long-scroll report
   - paginated or infinite-scroll report
4. Keep audit-oriented assertions for persisted evidence and route-history inspectability.

**Completion condition**
- Every major scenario and every major rollout risk has at least one explicit positive-path and one negative-path validation path.

## End-to-end implementation sequence

Use this sequence if the document is going to be executed as a real program of work.

1. Run Phase 1 delivery plus Track 1 and Track 2 updates needed for those changes.
2. Validate Phase 1 with synthetic tests and targeted smoke runs.
3. Roll out Phase 1 behind KPI monitoring from Track 4.
4. Run Phase 2 delivery plus any contract/logging extensions required by richer salvage and confirmation scoring.
5. Validate Phase 2 with synthetic tests, audit checks, and targeted longread/browser smoke runs.
6. Roll out Phase 2 with false-positive monitoring for `email_requested`, recovered artifacts, and `onsite_report`.
7. Run Phase 3 delivery plus audit/reporting updates for route-memory and redirect behavior.
8. Validate Phase 3 with reuse-focused tests and remembered-route smoke cases.
9. Keep Track 3 direct-PDF maintenance active during every phase.
10. Keep the playbook updated after each completed phase so implemented items move from “build” to “harden” or “done”.

## Improvement decision matrix

### Improvement 1 - Download-readiness gate before browser spend

**Priority**
- P0

**Pros**
- Cuts the highest-volume wasted attempts early.
- Improves measured success rate quality by removing obvious non-report candidates from the denominator.
- Preserves browser budget for real report targets.

**Cons**
- Can reduce recall if the gate is too strict.
- Requires domain-pattern maintenance and good negative examples.

**Success looks like**
- `browser_download_empty_result` drops materially on `report_download_discovery`.
- New terminal rejections such as `candidate_rejected_non_report` are explainable and auditable.
- Manual spot checks show fewer support, case-study, and generic marketing pages entering download execution.

**Guardrails: must not break**
- Genuine report landing pages with weak titles or light metadata must still pass when provenance is strong.
- Direct-PDF candidates must never be rejected just because the landing page is thin.
- Rejection reasons must be logged and reviewable; silent drops are not acceptable.

### Improvement 2 - Blocker taxonomy plus identity/profile upgrades

**Priority**
- P0

**Pros**
- Turns opaque email-form failures into explicit terminal outcomes.
- Separates fixable identity gaps from true retryable browser failures.
- Enables publisher-specific workarounds such as accepted business-email domains and enum defaults.

**Cons**
- Adds configuration overhead.
- Can create maintenance churn if publisher-specific overrides become too ad hoc.

**Success looks like**
- `email_required` outcomes are split cleanly by blocker type.
- Fewer retries are wasted on domain rejection, CAPTCHA, archived pages, or missing required values.
- More gated publishers move from `email_required` to `email_requested` after profile/config improvement.

**Guardrails: must not break**
- The system must never invent missing field values.
- Blocked forms must remain terminal and explicit; they must not be reclassified as successful email delivery.
- Identity profiles must stay sanitized in logs.

### Improvement 3 - Artifact validation and recovery for HTML masquerading as PDF

**Priority**
- P0

**Pros**
- Directly addresses current `browser_download_invalid_pdf` and `browser_download_missing_file` failures.
- Converts false PDF failures into either recovered downloads or verified email-delivery states.
- Prevents HTML thank-you pages from being mis-stored as reports.

**Cons**
- Recovery logic can become brittle if too many page-specific extractors are added.
- More parsing and validation steps increase implementation complexity.

**Success looks like**
- Invalid-artifact failures drop sharply.
- Recovered PDF URLs are logged with provenance.
- Stored artifacts are consistently real PDFs with valid magic bytes.

**Guardrails: must not break**
- HTML pages must never be persisted as successful PDF downloads.
- Recovered URLs must be auditable; hidden heuristic jumps are not acceptable.
- Email-delivery outcomes must remain distinct from local-file downloads.

### Improvement 4 - Terminal-state salvage for empty browser results

**Priority**
- P1

**Pros**
- Attacks the largest remaining retryable failure class after readiness gating.
- Converts “browser reached something useful but returned nothing structured” into typed outcomes.
- Improves postmortem quality with deterministic evidence.

**Cons**
- Requires more failure-artifact storage and log volume.
- Can create false certainty if salvage rules are too optimistic.

**Success looks like**
- `browser_download_empty_result` falls on `browser_listing_hub` and `browser_pdf_click`.
- A meaningful share of prior empty-result failures are reclassified into explicit terminal outcomes.
- Failure analysis becomes reproducible from persisted evidence.

**Guardrails: must not break**
- Salvage must not invent success without concrete evidence.
- Retryable failures must remain retryable when terminal evidence is genuinely absent.
- Screenshot and DOM capture must remain bounded and safe for storage volume.

### Improvement 5 - Multi-signal email confirmation scoring

**Priority**
- P1

**Pros**
- Improves conversion of real form submissions into `email_requested`.
- Reduces dependence on brittle exact text matching.
- Works across thank-you pages, toasts, redirects, and form-removal flows.

**Cons**
- Threshold tuning can create false positives if signals are too weak.
- Needs consistent evidence capture from browser and network telemetry.

**Success looks like**
- `browser_download_email_submission_missing` and `browser_download_email_confirmation_missing` decrease.
- Manual review confirms `email_requested` events correspond to genuine submission completion.
- Confirmation evidence is logged consistently.

**Guardrails: must not break**
- `email_requested` must require real multi-signal evidence, not just a clicked submit button.
- Weak or ambiguous success copy must not bypass the threshold alone.
- Confirmation scoring changes must be reversible without affecting artifact validation logic.

### Improvement 6 - Expand structured-result fallback beyond direct PDF

**Priority**
- P1

**Pros**
- Extends an already-proven pattern beyond the easy direct-PDF path.
- Reduces failure caused purely by browser serialization gaps.
- Makes success less dependent on model output formatting.

**Cons**
- Harder to make deterministic on complex browser routes.
- Can overlap with salvage logic if boundaries are unclear.

**Success looks like**
- More non-direct routes finish with verified typed outcomes despite missing model JSON.
- `DownloadTerminalEvidence` is present for both successful and failed runs.
- Fallback decisions are reproducible from logged evidence.

**Guardrails: must not break**
- Fallback must remain evidence-driven and schema-valid.
- Direct-PDF success paths must stay fast; broader fallback must not slow them materially.
- Browser-structured success and fallback success must remain distinguishable in telemetry.

### Improvement 7 - Route-memory confidence model

**Priority**
- P2

**Pros**
- Improves long-term reuse once enough verified history exists.
- Reduces the chance that one brittle success poisons future route planning.
- Makes memory quality measurable instead of binary.

**Cons**
- Low immediate impact while live reuse volume is still small.
- Adds persistence and scoring complexity before the upstream precision issues are fully solved.

**Success looks like**
- Memory-route reuse success rate rises over time.
- Promotion and demotion decisions are explainable from logged confidence fields.
- `http_recovered` and weakly inferred outcomes do not pollute browser-route reuse.

**Guardrails: must not break**
- No route should become primary memory from one low-confidence success.
- Stale memory must degrade gracefully to normal planning.
- Memory scoring must not hide the original route evidence.

### Improvement 8 - Tracker and redirect normalization

**Priority**
- P2

**Pros**
- Reduces noise from marketing automation and redirect wrappers.
- Helps expose real PDF or email-gate destinations earlier.
- Can improve both readiness gating and artifact recovery.

**Cons**
- Redirect behavior varies across publishers and may need ongoing tuning.
- Some wrapped flows will still require browser execution.

**Success looks like**
- Fewer browser attempts are wasted on wrapper URLs.
- More redirect flows are classified upfront into PDF, email gate, or non-report outcomes.
- Redirect provenance remains visible in logs.

**Guardrails: must not break**
- Unwrapping must preserve the original candidate URL for auditability.
- Query stripping must not remove parameters required for legitimate access.
- Early redirect classification must not bypass real artifact validation.

### Improvement 9 - First-class on-site longread acquisition

**Priority**
- P1

**Pros**
- Expands acquisition beyond downloadable assets.
- Covers report publishers that use longread, paginated, or infinite-scroll article formats.
- Prevents valid report pages from being misclassified as failed downloads or false positives.

**Cons**
- Requires a contract change, not just better heuristics.
- Article completeness and report-intent validation are harder than checking for a PDF file.
- Risks accepting generic blog content if thresholds are too weak.

**Success looks like**
- A new route kind such as `onsite_report` is emitted for valid on-site reports.
- Pagination, long scroll, and auto-pagination flows produce complete article artifacts with traversal evidence.
- Manual review shows accepted longreads are genuine reports rather than ordinary blog posts.

**Guardrails: must not break**
- Generic blog posts, press releases, and thin marketing articles must not be promoted to report acquisitions.
- `onsite_report` must remain distinct from `pdf_download` and `email_delivery` in storage, metrics, and memory.
- Longread capture must prove completeness; partial first-page capture is not acceptable when pagination exists.
- Infinite-scroll handling must be bounded to avoid runaway capture or duplicated sections.

## Required contract and logging upgrades for reproducibility

To keep these changes auditable and deterministic:

- persist a typed `DownloadTerminalEvidence` contract for every attempt
- add a first-class route kind for on-site report acquisition, for example `onsite_report`
- add `download_readiness_score` and rejection reasons to planner logs
- add `blocked_reason` and `blocked_reason_detail` for form-terminal outcomes
- log artifact validation fields:
  - MIME type
  - magic-byte result
  - source of recovered PDF URL
- log longread acquisition fields when `onsite_report` is detected:
  - canonical article URL
  - traversed page count
  - scroll-depth/content-growth evidence
  - section count
  - completeness status
- log `confirmation_score` and contributing signals for email outcomes
- log route-memory confidence transitions separately from normal success recording

### Status after latest code update

- `DownloadTerminalEvidence` now exists and is persisted.
- `onsite_report` now exists in contracts, planner logic, runtime adaptation, and route-memory persistence.
- `blocked_reason` and `blocked_reason_detail` now exist in contracts and persistence.
- The remaining missing pieces are mostly deeper evidence fields and richer scoring telemetry, not the base contract layer itself.

## KPI targets and rollout guards

### Primary KPIs

- Verified download success rate (`outcome=downloaded`)
- Verified email delivery success rate (`outcome=email_requested`)
- Verified on-site report acquisition rate (`route_kind=onsite_report`)
- Blocked-email rate (`outcome=email_required`) split by blocker taxonomy
- Empty-result failure rate (`code=browser_download_empty_result`) by route family
- Invalid-artifact failure rate (`browser_download_invalid_pdf` plus `browser_download_missing_file`)

### 30-day target after rollout

- reduce `browser_download_empty_result` by at least 40%
- reduce invalid-artifact failures by at least 50%
- increase combined verified outcomes (`downloaded + email_requested`) by at least 25%

### Rollback guardrails

- if `email_requested` false positives rise, roll back confirmation thresholds only
- if `candidate_rejected_non_report` spikes unexpectedly, lower readiness strictness but keep rejection telemetry
- if artifact recovery starts misclassifying HTML pages as PDFs, disable recovered-PDF promotion and keep URL extraction logs

## Test additions required for safe rollout

1. Readiness-gate tests that reject non-report pages before browser execution.
2. Browser artifact tests where the fetched file is HTML, missing, or has invalid PDF bytes.
3. Email blocker tests covering rejected email domains, CAPTCHA, archived pages, and missing required enums.
4. Email confirmation tests asserting threshold logic across mixed signals.
5. Orchestrator tests asserting that empty browser results can still emit terminal evidence and correct typed outcomes.
6. Route-memory tests for confidence-based promotion/demotion after the higher-priority fixes land.
7. Longread acquisition tests for:
   - single long-scroll report pages
   - paginated report pages
   - auto-pagination/infinite-scroll reports
   - rejection of generic blog and news pages that do not meet report thresholds

## Summary recommendation

If only three adjustments should be made next, prioritize these:

1. richer readiness taxonomy and better non-report rejection telemetry
2. deeper identity/profile support for blocked email-gated forms, especially enum-heavy publishers
3. broader terminal-evidence salvage and confirmation scoring for browser listing/form routes

That ordering matches the April 5-7, 2026 run logs more closely than the earlier version. The original playbook direction was broadly right, but the live evidence shows the biggest gains now sit in precision, blocker classification, and artifact recovery, not in further tuning the already-working direct-PDF path.

On-site longreads are now a supported capability in code, so they should no longer be treated as a hypothetical future extension. The remaining work there is stricter completeness validation and better separation of genuine report longreads from generic editorial pages.
