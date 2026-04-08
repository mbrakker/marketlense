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
- Existing quality and audit writeups:
  - `docs/quality/acquisition_route_upgrade_plan.md`
  - `docs/quality/report-discovery-download-review-2026-03-30.md`
- Current run-log validation window:
  - `logs/market_lense_2026-04-05.log`
  - `logs/market_lense_2026-04-06.log`
  - `logs/market_lense_2026-04-07.log`

## Run-log check: what is still relevant and what changed

This playbook is still relevant, but the current logs change the priority order.

- In the sampled live runs, the flow produced 47 `downloaded`, 14 `email_requested`, and 7 `email_required` outcomes.
- The dominant failure code was still `browser_download_empty_result` (559 cases), but most of that volume came from `report_download_discovery` and `report_download_browser_listing_hub`, not from direct-PDF routes.
- Deterministic fallback is already proving value: 29 `downloaded` outcomes completed with `browser_had_structured_result=false`, almost all on `direct_pdf_probe`.
- Artifact-quality failures are a real current gap: 31 `browser_download_missing_file` and 22 `browser_download_invalid_pdf` failures were recorded in the same window.
- Email flow problems are broader than weak confirmation text. Current logs show consumer-email rejection, CAPTCHA blocks, archived/static landing pages, and unconfigured required fields.
- Route-memory issues still matter architecturally, but the sampled live logs show very little real reuse activity. The current bottleneck is low coverage and weak confidence, not clearly memory pollution as the top live failure driver.
- A separate capability gap remains: the current acquisition model centers on `pdf_download` and `email_delivery`. On-site report longreads are not yet first-class terminal outcomes.

## Current bottleneck pattern from the April logs

The current ordering should be treated as:

1. discovery false positives and weak download-readiness gating
2. browser listing/candidate routes returning no terminal result
3. form blockers before confirmation can even be trusted
4. invalid or non-PDF artifacts being treated like report downloads
5. post-submit confirmation classification for genuine email-gated flows
6. route-memory quality and reuse coverage
7. tracker/redirect handling
8. direct-PDF prioritization
9. missing first-class support for on-site report longreads

The implication is important: direct-PDF handling is no longer the main weakness. The bigger gaps are upstream precision, terminal-state evidence, blocker classification, and artifact recovery.

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
- The current route model does not treat these as a valid terminal acquisition type, so they risk being rejected as non-report pages or mishandled by PDF-oriented logic.

**Adjustment**
- Introduce a third acquisition route kind, for example `onsite_report`.
- Add longread acquisition handling with explicit completeness checks:
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

**Expected impact**
- Expands acquisition coverage for publishers that publish research as HTML instead of downloadable files.
- Reduces false negatives on genuine report content that currently has no valid route kind.

## High-impact implementation plan reordered by live evidence

### Phase 1 (highest current ROI)
1. Download-readiness gate for non-report and low-confidence discovery candidates.
2. Typed blocker classification for email forms, including domain rejection, CAPTCHA, static archives, and missing identity fields.
3. Artifact validation and recovery for HTML masquerading as PDF.

### Phase 2 (convert ambiguous runs into verified terminal states)
1. Terminal-state salvage for browser listing/candidate routes that currently end as `browser_download_empty_result`.
2. Multi-signal email confirmation scoring.
3. Expanded structured-result fallback using `DownloadTerminalEvidence`.
4. Add first-class `onsite_report` acquisition for longreads, pagination, and infinite-scroll report pages.

### Phase 3 (stability and adaptive reuse)
1. Route-memory confidence model and safer promotion rules.
2. Tracker/redirect normalization and redirect outcome classification.
3. Publisher-level adaptive planning from recent route telemetry.

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

If only three adjustments can be made immediately, implement these first:

1. strict download-readiness gating before browser spend
2. blocker taxonomy plus identity/profile upgrades for email-gated forms
3. invalid-artifact recovery for HTML and thank-you pages that hide the real PDF or should be classified as email delivery

That ordering matches the April 5-7, 2026 run logs more closely than the earlier version. The original playbook direction was broadly right, but the live evidence shows the biggest gains now sit in precision, blocker classification, and artifact recovery, not in further tuning the already-working direct-PDF path.

If support for on-site longreads is a product requirement, treat it as the next adjacent capability after the Phase 1 fixes. It is not a small extension of PDF download logic; it needs its own route kind, completeness checks, and storage/validation path.
