# Isolated timeout-cohort acquisition validation — 2026-08-22

## Verdict: NO MATERIAL IMPROVEMENT

This is an acquisition-only replay of the frozen 15-report Browser Use timeout
cohort. It ran no discovery, ingest, analysis, extraction, generation,
publishing, or WordPress work. Every report remains in the denominator and a
success requires the normal `verified_usable_artifact` verification.

The current replay preserves the previously demonstrated rendered on-site PDF
capability: the separate retained nine-report replay at
`../browser_isolated_rendered_9_20260822_123000/` verified 7/9 artifacts as
`rendered_onsite_pdf`. The current changes are scoped to the outer replay
supervisor; they do not alter route selection or rendered-PDF verification.
`test_artifact_verification_preserves_verified_browser_printed_pdf` passed as
part of the focused suite.

## Comparability and retained inputs

- Exact previous same-scope result: `baseline_evidence/current_acquisition_attempts.jsonl`
  from `browser_timeout_cohort_final_20260822_110123`, SHA-256
  `31AC9B6A382401B205E8444B0A5177491A9F0B4CA96BEF10AA08757729DB4CAC`.
- Exact frozen cohort: `baseline_evidence/baseline_manifest.json`, SHA-256
  `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`.
- Current acquisition records: `acquisition_attempts.jsonl`, SHA-256
  `F9B269886C1E692327E8597D2569293077B666D4F6A54057B645488CDDE5E8F1`.
- Current configuration: `configuration.yaml`, SHA-256
  `803A4BBC4C1BC82D10D1786FB99EAF789E176E36C65FD6D416C9CA567F2C1CCF`.
- Current commit: `65714772cfd2ad22e43f7c79fd1cb8bc854c6d91`.
- Both runs use `gpt-5-mini`, zero retries, a 240-second/24-step
  `browser_email_form` budget, a 600-second mailbox poll limit, and disabled
  route/private-API playbook promotion. The new run uses fresh state/output
  paths and a process-isolated worker per candidate.
- The supervisor limit is 720 seconds: the widest configured inner service
  timeout (600 seconds) plus 120 seconds of cleanup grace. It never pre-empts
  a configured route or mailbox timeout.

## Exact cohort

| Candidate | Publisher | URL |
| --- | --- | --- |
| fac_fa1889b4c19f0f238659145e | Criteo | https://go.criteo.com/commerce-media-trends-report |
| fac_0ef70242a602b9ed7641c056 | Adjust | https://www.adjust.com/resources/ebooks/all |
| fac_3e630244e5c22fe8fa787255 | GWI | https://www.gwi.com/reports/5-reasons-to-buy |
| fac_4da62bac17be2e7185090695 | GWI | https://www.gwi.com/reports/ad-blocking-trends |
| fac_c0e4c925c1ed4ce6149711b8 | GWI | https://www.gwi.com/reports/ad-sales-pitching |
| fac_6f994caaf9a413e4038f18f1 | GWI | https://www.gwi.com/reports/ad-targeting-media-planning |
| fac_79d2b1c0c59436f8eacd7de4 | Jungle Scout | https://www.junglescout.com/resources/reports/3p-seller-disruption |
| fac_057817530e711866e5fea457 | Jungle Scout | https://www.junglescout.com/resources/reports/amazon-benchmark-report-2026 |
| fac_74ff8c2c4382773a4f8d5f55 | Jungle Scout | https://www.junglescout.com/resources/reports/amazon-data-arts-crafts-sewing-brands |
| fac_80dc158f27be79e08f090b8c | Jungle Scout | https://www.junglescout.com/resources/reports/amazon-innovation-report |
| fac_c21286d0bf9647749fa4dae3 | Jungle Scout | https://www.junglescout.com/resources/reports/amazon-market-trends-body-skincare |
| fac_6dae1d79b7340a3e0fd5055b | Jungle Scout | https://www.junglescout.com/resources/reports/amazon-market-trends-camping-hiking-products |
| fac_248c234f4d797e8eca595ff3 | Jungle Scout | https://www.junglescout.com/resources/reports/amazon-market-trends-car-care |
| fac_0a2d080a0bcc92e54f50e171 | Jungle Scout | https://www.junglescout.com/resources/reports/amazon-market-trends-car-parts-accessories |
| fac_05b9e5cae6b0bbaf35801e27 | Jungle Scout | https://www.junglescout.com/resources/reports/amazon-market-trends-cosmetics |

## Previous same-scope run vs current main

| Metric | Previous | Current | Change |
| --- | ---: | ---: | ---: |
| Attempted reports | 15 | 15 | 0 |
| Verified acquisitions | 0 | 0 | 0 |
| Acquisition success rate | 0.00% | 0.00% | 0.00 pp |
| Browser Use Agent reports | 2 | 2 | 0 |
| Browser Use Agent calls | 14 | 11 | -3 (-21.43%) |
| Input / cached / output tokens | 329,367 / 127,744 / 14,790 | 262,425 / 81,536 / 12,080 | -66,942 / -46,208 / -2,710 |
| Browser launches | 15 | 15 | 0 |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.083183 | $0.071419 | -$0.011764 (-14.14%) |
| Cost per verified acquisition | not defined | not defined | not comparable |
| Acquisition duration | 5,228.627 s | 5,258.190 s | +29.563 s (+0.57%) |
| Supervisor-produced incomplete records | n/a | 0 | 0 |

No report passed ordinary artifact verification. Therefore, despite fewer Agent
calls and lower token/cost consumption, the fixed cohort has no actual
acquisition-success improvement and a small duration regression.

## Current per-report terminal results

All 15 records used `browser_email_form`, ended
`browser_download_agent_timeout`, and failed normal artifact verification.

| Candidate | Agent calls | Verified | Duration |
| --- | ---: | --- | ---: |
| fac_fa1889b4c19f0f238659145e | 1 | no | 346.088 s |
| fac_0ef70242a602b9ed7641c056 | 10 | no | 346.556 s |
| fac_3e630244e5c22fe8fa787255 | 0 | no | 353.804 s |
| fac_4da62bac17be2e7185090695 | 0 | no | 357.099 s |
| fac_c0e4c925c1ed4ce6149711b8 | 0 | no | 359.272 s |
| fac_6f994caaf9a413e4038f18f1 | 0 | no | 357.883 s |
| fac_79d2b1c0c59436f8eacd7de4 | 0 | no | 346.673 s |
| fac_057817530e711866e5fea457 | 0 | no | 345.559 s |
| fac_74ff8c2c4382773a4f8d5f55 | 0 | no | 346.340 s |
| fac_80dc158f27be79e08f090b8c | 0 | no | 345.434 s |
| fac_c21286d0bf9647749fa4dae3 | 0 | no | 355.881 s |
| fac_6dae1d79b7340a3e0fd5055b | 0 | no | 351.068 s |
| fac_248c234f4d797e8eca595ff3 | 0 | no | 350.575 s |
| fac_0a2d080a0bcc92e54f50e171 | 0 | no | 347.393 s |
| fac_05b9e5cae6b0bbaf35801e27 | 0 | no | 348.565 s |

Verified-route resolution counts: HTTP/direct 0; private API 0; browser
preflight 0; deterministic standard form 0; deterministic learned playbook 0;
remembered blocker 0; Browser Use Agent 0. The route used for every report was
`browser_email_form`; the two reports that invoked the Agent still failed
normal verification.

Against the previously retained run of the same report-acquisition scope,
current main reduced Browser Use incidence by 0 reports, Agent calls by 3,
input/cached/output tokens by 66,942/46,208/2,710, browser launches by 0,
and cost by $0.011764; acquisition time increased by 29.563 seconds.
Verified acquisition success did not regress, but it also did not improve: it
remained 0/15.
