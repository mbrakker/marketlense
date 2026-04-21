# Browser-use Random Report Download Probe

Date: 2026-04-21

## Scope

- Objective: confirm the download flow uses generic acquisition logic, not report- or publisher-specific shortcuts.
- Execution path: real `run_report_download(...)` orchestration with `PublisherInventoryCandidateTrace` rows copied from `state/reports.sqlite`.
- Sample: 10 domain-distinct, non-PDF `report_sources` rows with `source_status='discovered'`.
- Random seed: `202604211600`.
- Settings override: `timeout_seconds=120.0`, `max_steps=17`, model `google/gemini-2.5-flash-lite`, `headed=true`.
- Route memory hits in sample: `0`; this was a cold-run verification.

## Generic Fixes Confirmed

- Removed the hardcoded known-publisher PDF URL constructor from the download service.
- Removed host-specific email-form/access-challenge routing; whitepaper/ebook/download/register/form paths are now handled by generic path heuristics.
- Kept the PDF shortcut generic: landing-page HTML is fetched, embedded `.pdf` links are extracted, and candidates are accepted only when path/title tokens match the target report.
- Tightened the PDF-link relevance check after a live false positive: host/domain tokens no longer count toward PDF relevance, which prevented unrelated same-site legal PDFs from being accepted.

## Latest Generic Run Summary

Artifact: `out/browser_downloads/browser_use_random_report_probe_random10_20260421_generic2_20260421_204536.json`

| # | Domain | Outcome | Route family | Elapsed | Artifact / blocker |
|---|---|---|---|---:|---|
| 1 | `datareportal.com` | `captured` | `browser_onsite_report` | 1.99s | `onsite_capture.html` |
| 2 | `www.quid.com` | `downloaded` | `report_page_pdf_link_probe` | 2.31s | `Stanford_HAI_2024_AI-Index-Report.pdf` |
| 3 | `www.algolia.com` | `downloaded` | `report_page_pdf_link_probe` | 7.30s | `Ebook_transforming-search-ai_compressed.pdf` |
| 4 | `www.centricsoftware.com` | `email_required` | `browser_email_form` | 1.60s | `blocked_captcha` |
| 5 | `www.nielsen.com` | `email_required` | `browser_email_form` | 47.99s | `blocked_email_domain` |
| 6 | `impact.com` | `captured` | `browser_onsite_report` | 1.92s | `onsite_capture.html` |
| 7 | `www.brightlocal.com` | `captured` | `browser_onsite_report` | 1.72s | `onsite_capture.html` |
| 8 | `www.omnisend.com` | `captured` | `browser_onsite_report` | 6.13s | `onsite_capture.html` |
| 9 | `www.harriswilliams.com` | `downloaded` | `report_page_pdf_link_probe` | 2.47s | `HCLS_Sector_Brief_Med_Products_Q1_2026_FINAL.pdf` |
| 10 | `www.bain.com` | `downloaded` | `report_page_pdf_link_probe` | 3.00s | `bain_report_machinery-and-equipment-report-2022.pdf` |

## Active Residuals

- Centric is blocked by an anti-bot/access challenge and is classified as `blocked_captcha`; this is a site blocker, not a browser-use process stall.
- Nielsen rejects the configured email domain and is classified as `blocked_email_domain`; this is a form policy blocker, not a script timeout.
- Nielsen remains the only slow path in the sample because it requires live browser form interaction before terminal blocker classification.

## Verification Commands Run

- `python -m pytest tests/test_browser_report_download_service.py tests/test_report_download_route_planner.py -q`
- `python -m py_compile src/orchestrators/_report_download_route_planner.py src/services/browser_report_download_service.py src/services/_browser_report_download/http.py`
- Real-time generic run: `BROWSER_PROBE_RUN_LABEL=random10_20260421_generic2`, `BROWSER_PROBE_RANDOM_SEED=202604211600`, `python .codex_tmp/run_browser_random10_probe.py`

## Verification Result

- 10 typed terminal results.
- 0 app errors.
- 0 runner crashes.
- 0 browser-use timeout events.
- 0 known-publisher shortcut events.
