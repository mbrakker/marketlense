# Browser-use Random Report Download Probe

Date: 2026-04-20
Updated: 2026-04-21

## Scope

- Objective: test random report-download candidates, document browser-use failures, script stalling, inefficient paths, and slowing choices, then remove issues once a real run confirms success.
- Execution path: real `run_report_download(...)` orchestration with `PublisherInventoryCandidateTrace` built from rows in `state/reports.sqlite`.
- Sample: 10 domain-distinct, non-PDF `report_sources` rows with `source_status='discovered'`, fixed seed `20260421`.
- Live settings used for verification: `timeout_seconds=120.0`, `max_steps=17`, model `google/gemini-2.5-flash-lite`, headed browser enabled.

## Current Verification Status

The latest focused fixes were verified with real browser/download runs on 2026-04-21. Confirmed-success items have been removed from active issues.

| Sample # | Candidate | Latest verified result | Elapsed | Artifact |
|---:|---|---|---:|---|
| 4 | Datareportal / Digital 2022: Wallis and Futuna | `captured`, `onsite_report`, `browser_onsite_report` | 2.823s | `browser_use_random_report_probe_20260421_afterfix_focus2_20260421_132342.json` |
| 5 | GWI / Understanding consumers in South Africa | `email_required`, `email_delivery`, `browser_email_form` | 143.110s | `browser_use_random_report_probe_20260421_afterfix_focus2_20260421_132342.json` |
| 6 | Impact / B2B Content Operations Workflow | `captured`, `onsite_report`, `browser_onsite_report` | 143.221s | `browser_use_random_report_probe_20260421_afterfix_focus2_20260421_132342.json` |
| 7 | Bright Local / Local RankFlux Data | `captured`, `onsite_report`, `browser_onsite_report` | 7.965s | `browser_use_random_report_probe_20260421_afterfix_focus2_20260421_132342.json` |
| 9 | Capgemini / The multi-year AI advantage | `downloaded`, `pdf_download`, `browser_download` | 142.889s | `browser_use_random_report_probe_20260421_afterfix_20260421_121545.json` |
| 10 | VML / The Single Age | `captured`, `onsite_report`, `browser_onsite_report` | 142.905s | `browser_use_random_report_probe_20260421_afterfix_vml_20260421_134020.json` |

VML capture was confirmed on disk:

- `out/browser_downloads/verification_fixed10_afterfix_vml_downloads_20260421_134020/www.vml.com/96df69062d1d/The Single Age.md`
- File exists, 1435 bytes.

## Confirmed Fixes

- Datareportal no longer reuses stale weak email/listing memory or retries an unverified PDF claim. The report-detail page now direct-captures as onsite HTML in 2.823s.
- GWI no longer starts from the source listing hub for `/reports/south-africa-consumers`; it reaches a terminal email-gated outcome instead of timing out mid-flow.
- Impact guide/article URLs now route to onsite capture instead of wandering into unrelated external links.
- Bright Local no longer treats `algorithm` as a tracker marker and no longer lets weak email memory override a research longread route.
- VML no longer treats worker metadata JSON as a downloaded artifact and now materializes missing onsite captures from extracted route-step text. Singular `/insight/<slug>` detail URLs route directly to onsite capture.
- Capgemini no longer reproduces the earlier hard browser-use timeout in the fixed 10-run verification; it completed as a downloaded PDF.
- Hidden script text such as `grecaptcha` no longer blocks direct onsite HTML capture when the rendered HTML contains a real article.
- Non-report markers are now token-aware, so `press` inside words like `self-expression` no longer blocks onsite report salvage.

## Residual Active Issues

- Browser-use completed-history salvage is still slow. GWI, Impact, and VML terminal runs each took about 143s because the worker result was only harvested after the bounded browser timeout/salvage window.
- GWI is a valid terminal result but not a downloaded artifact: the site remains email-gated for the configured identity path.
- VML still requires browser-use because direct HTTP fetch returns a JavaScript/cookie challenge. The latest fix makes the browser run successful, not fast.
- Impact is successful but still slow; direct onsite short-circuit did not fire in the live run, so browser-use consumed the timeout budget before completed-history salvage.

## Inefficiencies And Slowing Choices

- The outer worker and completed-history salvage budgets extend a nominal 120s browser timeout to roughly 143s per slow terminal attempt.
- Browser-use can reach a terminal `done` action while the orchestrator only receives the result after timeout salvage. This is no longer losing results, but it still costs a full timeout window.
- Direct HTTP capture is high value when allowed: Datareportal fell from a previous 298s timeout path to 2.823s.
- Browser form/onsite routes still depend heavily on prompt compliance. VML succeeded after route-planner changes, but browser-use still needed visible navigation and extraction.

## Verification Artifacts

- Full fixed 10-run before the final focused patches: `out/browser_downloads/browser_use_random_report_probe_20260421_afterfix_20260421_121545.json`
- Focused rerun after Datareportal/GWI/Impact/BrightLocal fixes: `out/browser_downloads/browser_use_random_report_probe_20260421_afterfix_focus2_20260421_132342.json`
- Final VML-only rerun: `out/browser_downloads/browser_use_random_report_probe_20260421_afterfix_vml_20260421_134020.json`
- Structured logs: `logs/market_lense_2026-04-21.log`
- Console logs:
  - `out/browser_downloads/browser_use_random_report_probe_20260421_afterfix_focus2.console.log`
  - `out/browser_downloads/browser_use_random_report_probe_20260421_afterfix_vml.console.log`

## Verification Commands Run

- `pytest tests/test_report_download_route_planner.py tests/test_browser_report_download_service.py tests/test_report_download_orchestrator.py tests/test_browser_use_vendor_compat.py`
- Result: `109 passed, 1 warning`
- Real focused run: `BROWSER_PROBE_RUN_LABEL=afterfix_focus2`, `BROWSER_PROBE_INDICES=4,5,6,7,10`
- Real VML confirmation run: `BROWSER_PROBE_RUN_LABEL=afterfix_vml`, `BROWSER_PROBE_INDICES=10`

## Historical Baseline

- The earlier fresh 10-report batch had 6 `app_error` and 4 `result` outcomes.
- The most important prior failures were Datareportal timeout, GWI timeout, Impact timeout, Bright Local wrong email route, Capgemini timeout, and VML artifact/capture failure.
- Those named failures now have real-run confirmations listed above, so they are no longer active failure issues in this report.
