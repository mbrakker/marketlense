# Acquisition Route Upgrade Plan

## Purpose

This document consolidates the acquisition audit results captured on 2026-04-05 and turns them into an engineering work plan for improving report acquisition coverage.

The goal is not only to list what failed, but to separate:

- routes the current download pipeline already handles reliably
- routes the system can partially handle but cannot yet verify robustly
- cases where discovery quality is the real blocker rather than the download pipe

## Source Artifacts

Primary artifacts used for this document:

- `out/acquisition_audit/20260405__session_combined/combined_acquisition_results.json`
- `out/acquisition_audit/20260404__222301/acquisition_audit_partial_recovery.json`

Supporting runtime data:

- per-run route memory: `out/acquisition_audit/<run>/audit_report_download.sqlite`
- downloaded files: `out/acquisition_audit/<run>/downloads/`
- logs: `logs/market_lense_2026-04-05.log`
- browser identity side effects: `src/config/browser_download_identity.yaml`

## Scope and Caveat

This audit is a strong first pass, but it is not the full universe of publishers in the repo. The combined artifact covers:

- 15 publishers in standard acquisition-audit runs
- 16 candidate-level rows in the merged standard result
- 7 recovered route records from the interrupted long-running batch

The standard merged artifact is best for current publisher classification. The recovered partial artifact is best for proving that some email-gated flows are already partially supported.

## Current Route Taxonomy

### Route families actually discovered

| Route family | Internal route kind | Current readiness | Evidence |
| --- | --- | --- | --- |
| Direct PDF URL | `pdf_download` | Ready | Activate direct `cdn.sanity.io` PDF |
| Page click that leads to PDF | `pdf_download` | Ready with browser fragility | Adobe, Barclays, BCG, recovered Activate, recovered Adjust |
| Email-gated delivery request | `email_delivery` | Partially ready | Recovered Activate and Adjust runs completed as `email_requested` |

### Failure classes observed

| Failure class | Meaning | Current readiness |
| --- | --- | --- |
| `browser_download_empty_result` | Browser automation produced no structured acquisition result | Not ready |
| `browser_download_email_submission_missing` | Flow looked email-gated, but submission could not be confirmed | Not ready |
| `browser_download_email_confirmation_missing` | Submission may have happened, but no confirmation was captured | Not ready |
| `browser_download_route_summary_too_weak` | Browser run returned a result without reusable action detail | Not ready |
| discovery false positive | Candidate is not a real report/download target | Download pipe is not the main blocker |
| discovery infrastructure failure | Discovery run failed before acquisition started | Download pipe is not the main blocker |

## Coverage Snapshot

### Standard merged result

- Publishers audited: 15
- Candidate rows: 16
- Acquisition outcome counts:
  - `downloaded`: 4
  - `failed_retryable`: 12
- Publisher flow recommendations:
  - `publisher_prefers_pdf_download`: 3
  - `mixed_automation`: 1
  - `manual_review_required`: 11

### Recovered partial supplement

- Route records: 7
- `downloaded`: 3
- `email_requested`: 4
- Last blocker on the interrupted batch: `OpenRouter 402 Payment Required`

## What Is Already Working

### 1. Direct PDF acquisition

This route is ready.

Observed successful examples:

- Activate Consulting: direct Sanity PDF URL
- recovered partial: direct `cdn.sanity.io` PDF route

Why it is ready:

- the download pipe now short-circuits direct `.pdf` URLs before browser-use
- the route produces a verified local PDF file

Primary code path:

- `src/services/browser_report_download_service.py`

### 2. Page-to-PDF acquisition

This route works, but still depends on browser stability and page-specific interactions.

Observed successful examples:

- Adobe: search result to PDF
- Barclays: disclosures page to PDF link
- BCG: article page to `Download Article`
- recovered Activate: page flow to downloadable PDF
- recovered Adjust: report page to displayed PDF in new tab

Primary code path:

- `src/services/browser_report_download_service.py`

### 3. Some email-gated delivery requests

This route is partially working.

Observed successful examples from the recovered partial artifact:

- Activate: form completed and request submitted as `email_requested`
- Adjust: multiple ebook request flows completed as `email_requested`

Why it is only partially ready:

- the service can classify and complete some email-gated flows
- the standard audit still fails several email routes because confirmation and submission validation are too brittle

## Failure Inventory by Root Cause

### A. Browser returned no structured result

This is the dominant failure class.

Count in merged standard result: 8

Affected candidates:

| Publisher | Report title | Report URL | Likely issue |
| --- | --- | --- | --- |
| Adjust | About us | `https://www.adjust.com/company` | Discovery false positive, not a real report target |
| Algolia | Get started | `https://dashboard.algolia.com/users/sign_up` | Discovery false positive, sign-up page |
| BlueCore | Cracking the Code... | `http://bluecore.com/lp/consumer-electronics-retailers-guide` | Real-looking landing page, browser route extraction failed |
| Bright Local | Enroll Today | `https://academy.brightlocal.com/course/create-winning-local-seo-strategy-for-any-business` | Discovery false positive, course page |
| Cardlytics | Accessibility | `https://www.cardlytics.com/accessibility` | Discovery false positive |
| Centric Market Intelligence | Centric Market Intelligence | `https://www.centricsoftware.com/centric-market-intelligence` | Candidate quality unclear, browser route extraction failed |
| Channel Engine | Download the report | HubSpot CTA tracking URL | Browser route extraction failed after CTA redirect |
| Circana | Job Openings | `https://jobs.circana.com/careers?filter_department=-Scanscape+Field` | Discovery false positive, careers page |

Upgrade implication:

- This is not one bug. It is a mixture of:
  - weak candidate filtering in discovery
  - browser-use instability on real acquisition pages
  - insufficient structured-result validation or fallback extraction

### B. Email route found, but submission not confirmed

Count in merged standard result: 2

Affected candidates:

| Publisher | Report title | Report URL | Likely issue |
| --- | --- | --- | --- |
| Beano Brain | Case Studies | `https://beanobrain.com/case-study` | Route likely gated form, but no reliable submit confirmation |
| Channel Engine | Download the report | HubSpot CTA tracking URL | Embedded or redirected form submit was not reliably observed |

Upgrade implication:

- The pipeline needs stronger post-submit verification for forms.
- The current success condition is too dependent on browser-use surfacing a clean confirmation signal.

### C. Email route found, but confirmation not captured

Count in merged standard result: 1

Affected candidate:

| Publisher | Report title | Report URL | Likely issue |
| --- | --- | --- | --- |
| Brand Finance | Consulting | `https://brandfinance.com/consulting` | Submission may succeed, but the visible confirmation heuristic is too weak |

Upgrade implication:

- Need more than one confirmation heuristic.
- Confirmation should consider URL changes, thank-you fragments, toast/modal text, email confirmation copy, and network-side submit success when available.

### D. Route summary was too weak to reuse

Count in merged standard result: 1

Affected candidate:

| Publisher | Report title | Report URL | Likely issue |
| --- | --- | --- | --- |
| Boston Consulting Group (BCG) | Featured Insights and Perspectives from BCG | `https://www.bcg.com/publications` | Browser run described too little detail to create a reusable acquisition route |

Upgrade implication:

- The route summarization contract is underspecified for reusable automation.
- We need stricter structured extraction of action sequences, not just natural-language summaries.

### E. Discovery failed before acquisition started

Affected publisher:

| Publisher | Discovery error | Impact |
| --- | --- | --- |
| Bain & Company | `drive_upload_failed` | No candidate-level acquisition audit was possible |

Upgrade implication:

- This is a discovery infrastructure issue, not a download route issue.
- Acquisition work should not be blocked by unrelated Drive upload behavior.

## Discovery Quality Problems Exposed by the Audit

Some failures should not be assigned to the download pipeline at all because the discovered candidate is clearly not a report.

### Strong discovery false positives

| Publisher | Discovered candidate | Why this is not a usable report candidate |
| --- | --- | --- |
| Adjust | About us | company page |
| Algolia | Get started | sign-up page |
| Bright Local | Enroll Today | academy course enrollment page |
| Cardlytics | Accessibility | accessibility policy page |
| Circana | Job Openings | careers page |

### Discovery quality edge cases

| Publisher | Discovered candidate | Why it needs better filtering |
| --- | --- | --- |
| BCG | Publications hub | generic listing hub, not a concrete report page |
| Centric Market Intelligence | product page | may be product collateral, not a report |
| BlueCore | long landing-page title | likely valid asset, but title extraction is noisy and needs normalization |
| Channel Engine | raw HubSpot CTA URL | discovery preserved the tracker instead of the underlying content/report target |

Upgrade implication:

- A meaningful portion of failed acquisition rows are caused by upstream candidate quality.
- Discovery should score and suppress generic pages, policy pages, sign-up pages, careers pages, and tracker URLs before download audit begins.

## Publisher-by-Publisher Status

| Publisher | Discovery route | Candidate count | Current classification | Result summary | Upgrade focus |
| --- | --- | --- | --- | --- | --- |
| Activate Consulting | `browser_render` | 1 | `publisher_prefers_pdf_download` | standard audit succeeded on direct PDF; recovered run also showed email-gated flow | keep as PDF-first, add optional alternate email route memory |
| Adjust | `browser_render` | 1 | `manual_review_required` | standard candidate was a false positive, recovered run proved both PDF and email routes exist | fix discovery ranking and preserve known successful routes |
| Adobe | `browser_render` | 1 | `publisher_prefers_pdf_download` | success via page-to-PDF flow | keep as stable PDF route |
| Algolia | `browser_render` | 1 | `manual_review_required` | discovered sign-up page | discovery filtering |
| Bain & Company | failed | 0 | `manual_review_required` | discovery failed with `drive_upload_failed` | decouple discovery from Drive failure |
| Barclays | `browser_render` | 1 | `publisher_prefers_pdf_download` | success via page PDF link | keep as stable PDF route |
| Beano Brain | `browser_render` | 1 | `manual_review_required` | likely email-gated, submit confirmation missing | email form verification |
| BlueCore | `http_parse` | 1 | `manual_review_required` | likely valid LP, but browser returned empty result | LP handling and browser fallback |
| Boston Consulting Group (BCG) | `browser_render` | 2 | `mixed_automation` | one concrete PDF success, one publications-hub failure | stronger candidate filtering and route summarization |
| Brand Finance | `browser_render` | 1 | `manual_review_required` | email confirmation missing | confirmation heuristics |
| Bright Local | `browser_render` | 1 | `manual_review_required` | discovered course page | discovery filtering |
| Cardlytics | `browser_render` | 1 | `manual_review_required` | discovered accessibility page | discovery filtering |
| Centric Market Intelligence | `browser_render` | 1 | `manual_review_required` | browser returned empty result on product-like page | candidate qualification plus browser fallback |
| Channel Engine | `browser_render` | 2 | `manual_review_required` | tracker URLs with email submit and empty-result failures | tracker resolution, form verification |
| Circana | `browser_render` | 1 | `manual_review_required` | discovered careers page | discovery filtering |

## Recommended Upgrade Priorities

### Priority 1: Separate discovery false positives from real acquisition failures

This will remove a large amount of noise immediately.

Required work:

- suppress obvious non-report pages during candidate generation
- down-rank titles and URLs containing patterns like:
  - `about`
  - `sign_up`
  - `accessibility`
  - `careers`
  - `job`
  - `course`
- reject generic hubs unless the page points to a concrete asset or report detail page
- resolve raw CTA/tracking links into canonical target URLs before candidate persistence

Primary code areas:

- `src/services/publisher_inventory_service.py`
- `src/services/_publisher_inventory_browser_service.py`
- `src/services/_publisher_inventory_fetch_service.py`
- `src/orchestrators/publisher_inventory_orchestrator.py`
- `src/generators/publisher_inventory_generator.py`

Expected win:

- convert several current `failed_retryable` rows into "not a candidate" before the download pipe runs

### Priority 2: Make email-gated flows verifiable

This is the biggest acquisition capability gap after discovery cleanup.

Required work:

- treat form submission success as multi-signal, not single-signal
- verify email submit through at least one of:
  - URL transition to thank-you state
  - visible success copy
  - modal/dialog success state
  - disabled or replaced submit button
  - network response success for form submit request
- store encountered field metadata and final submit evidence in the route contract
- normalize common gated-flow platforms:
  - HubSpot embedded forms
  - marketing LP forms
  - modal lead-gen forms

Primary code areas:

- `src/services/browser_report_download_service.py`
- `src/contracts/browser_download.py`
- `src/orchestrators/report_download_orchestrator.py`

Expected win:

- convert `browser_download_email_submission_missing` and `browser_download_email_confirmation_missing` into `email_requested`

### Priority 3: Improve browser result extraction for real landing pages

Required work:

- add fallback extraction when browser-use does not return structured output
- salvage route data from:
  - current page URL
  - final tab URL
  - downloaded file presence
  - visible button labels
  - observed form fields
- tighten the required structured output schema so route kind, action sequence, and evidence are mandatory
- store richer action traces instead of relying on a weak summary string

Primary code areas:

- `src/services/browser_report_download_service.py`
- `src/contracts/browser_download.py`

Expected win:

- reduce `browser_download_empty_result`
- eliminate `browser_download_route_summary_too_weak`

### Priority 4: Preserve and reuse successful route memory

Recovered partial runs proved some publishers have workable acquisition routes even when the bounded audit selected a bad candidate later.

Required work:

- persist and prioritize known-good publisher/report routes
- when a publisher already has a verified PDF or `email_requested` route, use it to guide future candidate selection and download attempts
- distinguish:
  - verified route
  - inferred route
  - failed route

Primary code areas:

- `src/services/report_store_service.py`
- `src/orchestrators/report_download_orchestrator.py`
- `src/orchestrators/acquisition_audit_orchestrator.py`

Expected win:

- prevents regressions like Adjust, where the system already demonstrated valid acquisition paths in the recovered run

### Priority 5: Decouple discovery from unrelated infrastructure failures

Required work:

- ensure discovery can still return candidates if optional artifact uploads fail
- isolate Drive upload failures from publisher inventory completion

Primary code area:

- `src/services/drive_service.py`
- `src/services/publisher_inventory_service.py`

Expected win:

- lets acquisition audit proceed for publishers like Bain even when auxiliary upload infrastructure fails

## Concrete Next-Step Backlog

### Backlog A: discovery filtering

1. Add URL/title negative-pattern filtering for obvious non-report pages.
2. Resolve tracker URLs to canonical targets before storing candidates.
3. Reject generic listing hubs unless a concrete downloadable/report detail target is extracted.
4. Add tests for false-positive suppression using the current bad examples.

### Backlog B: email-gated verification

1. Expand the browser download result contract with explicit submit evidence fields.
2. Add confirmation heuristics beyond visible success text.
3. Add HubSpot-specific form handling and verification.
4. Add pipeline tests asserting `email_requested` for known successful recovered routes.

### Backlog C: browser fallback extraction

1. When browser-use returns no structured result, inspect downloaded files and final page state before failing.
2. Preserve action traces and final resolved URLs in route storage.
3. Replace weak route summaries with structured action lists.
4. Add tests for empty-result fallback and route-summary completeness.

### Backlog D: route memory reuse

1. Mark recovered successful routes as verified historical evidence.
2. Prefer known-good patterns for publishers with prior success.
3. Add idempotent route-memory updates so audit runs improve future acquisition rather than only reporting failures.

## Test Targets for the Upgrade Work

Every upgrade should add both positive and negative coverage.

Recommended minimum additions:

- service tests for direct PDF fallback and page-to-PDF extraction
- service tests for email submit verification across:
  - visible thank-you state
  - no visible thank-you state but successful network submit
  - submit clicked but no evidence
- discovery tests proving current false positives are rejected
- orchestrator tests proving known-good historical routes are preferred when available
- contract round-trip tests if browser download contracts are extended

Primary test files to expand:

- `tests/test_browser_report_download_service.py`
- `tests/test_report_download_orchestrator.py`
- `tests/test_acquisition_audit_orchestrator.py`
- publisher inventory tests covering candidate filtering

## Summary

The audit shows that the system is already competent at PDF acquisition, but not yet robust at gated email flows or noisy discovery environments.

The fastest route to materially better pass rates is:

1. eliminate obvious discovery false positives
2. strengthen email submit and confirmation verification
3. add fallback evidence extraction when browser-use returns weak or empty output
4. reuse route memory from previously successful runs

If those four upgrades land, a substantial portion of the current `failed_retryable` rows should either:

- disappear before acquisition because they are no longer treated as report candidates, or
- convert into `downloaded` / `email_requested` outcomes with reusable route memory
