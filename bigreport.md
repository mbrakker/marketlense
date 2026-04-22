# Browser-use Random Report Download Probe

Date: 2026-04-21

## Scope

- Objective: test 10 random report-download candidates, document browser-use stalls, route issues, and inefficient slow choices, then remove issues once confirmed fixed by a real run.
- Execution path: real `run_report_download(...)` orchestration with `PublisherInventoryCandidateTrace` rows copied from `state/reports.sqlite`.
- Sample: 10 domain-distinct, non-PDF `report_sources` rows with `source_status='discovered'`.
- Random seed: `202604212105`.
- Final confirmation label: `random10_20260421_fresh7`.
- Final artifact: `out/browser_downloads/browser_use_random_report_probe_random10_20260421_fresh7_20260421_225823.json`.

## Fixes Confirmed By Final Run

- Removed slow browser-use form interaction for obvious email-gated report pages by adding a generic static email-gate preflight for route-confirmed email-delivery pages.
- Removed duplicated standalone HTTP probing before route-confirmed email-delivery attempts; the service still performs one bounded embedded-PDF probe inside the email step.
- Added generic gated-report route planning for report/resource detail URLs that look like downloadable assets, including numeric report detail pages and nested annual-report-style pages.
- Added generic direct HTML capture for route-confirmed longread pages without requiring publisher-specific shortcuts.
- Added generic downloaded-PDF relevance validation so unrelated same-site PDFs are rejected instead of accepted as successful artifacts.
- Reduced email-route static preflight timeout budgets so slow gated pages stop before browser-use instead of consuming the browser budget.

## Final Run Summary

| # | Domain | Outcome | Route family | Browser used | Elapsed | Artifact / terminal |
|---|---|---|---|---|---:|---|
| 1 | `datareportal.com` | `captured` | `browser_onsite_report` | no | 1.26s | `onsite_capture.html` |
| 2 | `www.nielsen.com` | `email_required` | `browser_email_form` | no | 0.84s | static email gate |
| 3 | `www.contentful.com` | `captured` | `browser_onsite_report` | no | 1.42s | `onsite_capture.html` |
| 4 | `business.adobe.com` | `email_required` | `browser_email_form` | no | 16.77s | static fetch timeout on gated email route |
| 5 | `yougov.com` | `email_required` | `browser_email_form` | no | 2.22s | static email gate |
| 6 | `www.marketplacepulse.com` | `captured` | `browser_onsite_report` | no | 1.57s | `onsite_capture.html` |
| 7 | `www.heap.io` | `downloaded` | `report_page_pdf_link_probe` | no | 1.20s | `240823_Mobile_Behavioral_Analytics_EBOOK.pdf` |
| 8 | `www.mintel.com` | `email_required` | `browser_email_form` | no | 0.90s | static email gate |
| 9 | `www.profitero.com` | `downloaded` | `report_page_pdf_link_probe` | no | 0.83s | `6859775d0c11a40ffd611cf0_One%20Pager%20-%20U.K.%20Toys%20SEO%2C%20Decoded%20-%20updated.pdf` |
| 10 | `www.centricsoftware.com` | `email_required` | `browser_email_form` | no | 1.66s | static email gate |

## Active Residuals

- No browser-use process stalls remained in the final run.
- No `app_error`, runner crash, or browser timeout remained in the final run.
- Five reports are site-level email gates (`email_required`), not script failures. The flow now classifies them before browser interaction instead of submitting forms with configured identity values.
- Adobe remains the slowest terminal case at 16.77s because both the bounded embedded-PDF probe and static email-gate probe time out against the page before classification. This is bounded and does not launch browser-use.

## Verification Commands Run

- `python -m pytest tests/test_browser_report_download_service.py tests/test_report_download_route_planner.py -q`
- `python -m py_compile src/orchestrators/_report_download_route_planner.py src/services/browser_report_download_service.py src/services/_browser_report_download/http.py src/services/_browser_report_download/artifact.py`
- Real-time confirmation run: `BROWSER_PROBE_RUN_LABEL=random10_20260421_fresh7`, `BROWSER_PROBE_RANDOM_SEED=202604212105`, `python .codex_tmp/run_browser_random10_probe.py`

## Verification Result

- 10 typed terminal results.
- 0 app errors.
- 0 runner crashes.
- 0 browser-use timeout events.
- 0 browser-use launches in the final sample.
- 5 deterministic non-browser acquisitions (`captured` or `downloaded`).
- 5 deterministic static email-gate classifications.
