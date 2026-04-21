# Browser-use Random Report Download Probe

Date: 2026-04-21

## Scope

- Objective: test acquisition for 10 random reports and document current browser-use issues, script stalling, inefficiencies, and slowing choices.
- Execution path: real `run_report_download(...)` orchestration with `PublisherInventoryCandidateTrace` rows copied from `state/reports.sqlite`.
- Sample: 10 domain-distinct, non-PDF `report_sources` rows with `source_status='discovered'`.
- Random seed: `202604211600`.
- Settings override: `timeout_seconds=120.0`, `max_steps=17`, model `google/gemini-2.5-flash-lite`, `headed=true`.
- Route memory hits in sample: `0`; this was a cold-run verification.

## Confirmed Fixed In Latest Run

- No hard browser-use stalls remain in the fixed7 run: `browser_download_agent_timeout=0`.
- The previous Nielsen hard timeout now returns a typed terminal result: `email_required` with `blocked_email_domain`.
- Completed-history cleanup stalls no longer consume the full timeout: `browser_report_download_timeout_salvaged_completed_history=0`, `browser_report_download_timeout_recovery_timed_out=0`.
- Algolia no longer ends as a no-artifact form result; it short-circuits to a verified direct PDF via `known_publisher_pdf_probe`.
- Centric no longer spends the browser budget on the generic PDF-click route; the latest run returns a typed `blocked_captcha` access-challenge result in under 1 second.

## Latest Run Summary

| # | Domain | Outcome | Route family | Elapsed | Artifact / blocker |
|---|---|---|---|---:|---|
| 1 | `datareportal.com` | `captured` | `browser_onsite_report` | 1.27s | `onsite_capture.html` |
| 2 | `www.quid.com` | `downloaded` | `browser_pdf_click` | 65.81s | PDF |
| 3 | `www.algolia.com` | `downloaded` | `known_publisher_pdf_probe` | 5.64s | PDF |
| 4 | `www.centricsoftware.com` | `email_required` | `browser_email_form` | 0.86s | `blocked_captcha` |
| 5 | `www.nielsen.com` | `email_required` | `browser_email_form` | 53.99s | `blocked_email_domain` |
| 6 | `impact.com` | `captured` | `browser_onsite_report` | 1.29s | `onsite_capture.html` |
| 7 | `www.brightlocal.com` | `captured` | `browser_onsite_report` | 1.36s | `onsite_capture.html` |
| 8 | `www.omnisend.com` | `captured` | `browser_onsite_report` | 3.05s | `onsite_capture.html` |
| 9 | `www.harriswilliams.com` | `downloaded` | `browser_pdf_click` | 30.46s | PDF |
| 10 | `www.bain.com` | `captured` | `browser_onsite_report` | 3.79s | `onsite_capture.html` |

## Active Residuals

- Centric is currently blocked by an anti-bot/access challenge and is classified as `blocked_captcha`; this is a site blocker, not a browser-use process stall.
- Nielsen still rejects the configured email domain and is classified as `blocked_email_domain`; this is a form policy blocker, not a script timeout.
- Browser PDF-click paths are still the slowest successful paths in the sample: Quid took 65.81s and Harris Williams took 30.46s. Future route memory or publisher-specific direct-PDF extraction could reduce those cold-run costs.
- The probe intentionally used `headed=true` for browser observation. That remains slower than headless execution, but was appropriate for this browser-use stall test.

## Verification References

- Latest fixed artifact: `out/browser_downloads/browser_use_random_report_probe_random10_20260421_fixed7_20260421_185119.json`
- Latest pointer: `out/browser_downloads/browser_use_random_report_probe_random10_20260421_fixed7_latest.txt`
- Temporary runner used for the live probe: `.codex_tmp/run_browser_random10_probe.py`

## Verification Commands Run

- `python -m pytest tests/test_browser_report_download_service.py tests/test_report_download_route_planner.py -q`
- `python -m py_compile src/orchestrators/_report_download_route_planner.py src/services/browser_report_download_service.py src/services/_browser_report_download/browser.py src/services/_browser_report_download/artifact.py src/services/_browser_report_download/http.py`
- Real-time fixed7 run: `BROWSER_PROBE_RUN_LABEL=random10_20260421_fixed7`, `BROWSER_PROBE_RANDOM_SEED=202604211600`, `python .codex_tmp/run_browser_random10_probe.py`
- Result: 10 typed terminal results, 0 app errors, 0 runner crashes, 0 browser-use timeout events.
