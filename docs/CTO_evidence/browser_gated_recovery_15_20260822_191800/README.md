# Gated-route recovery validation — 2026-08-22

## Verdict: NO MATERIAL IMPROVEMENT

This is an acquisition-only replay of the exact retained 15-report Criteo,
Adjust, GWI, and Jungle Scout cohort. It ran no discovery, ingest, analysis,
extraction, generation, publishing, or WordPress work. All attempts used the
normal artifact verifier; no validation rule was weakened and every failed
report remains in the denominator.

The tested producer commit was
`c074834f6925515866a50425c21103ebf11711ea` (`fix: recover deterministic
gated report routes`). The change adds a bounded generic same-page report-CTA
activation before deterministic form submission and detects a real embedded
PDF after submission for normal verification. It does not restore the rejected
generic Browser Use context-reduction experiment.

## Retained, comparable inputs

- Previous same-scope evidence: `baseline/`, copied exactly from
  `../browser_isolated_timeout_15_20260822_144500/`.
- Frozen source manifest: `frozen_source_manifest.json`, SHA-256
  `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`.
- Baseline records: `baseline/acquisition_attempts.jsonl`, SHA-256
  `F9B269886C1E692327E8597D2569293077B666D4F6A54057B645488CDDE5E8F1`.
- Current records: `acquisition_attempts.jsonl`, SHA-256
  `DC9AAFB9951913B440B21377882626E10B4DB8DD837AFA332D6DC6D858C222F6`.
- Current configuration: `configuration.yaml`, SHA-256
  `9DF0C5018531A909B892394C4C83C3FACC84CC2070DB87916C8F9E3C852114C8`.
- The same `gpt-5-mini` model, `browser_email_form` 240-second/24-step
  budget, zero retry setting, disabled route/private-API playbook promotion,
  600-second mailbox poll limit, and per-attempt process isolation were used.
  Fresh state and output paths were used.

The frozen source manifest contains 30 candidates; the exact selected 15 are
the rows below and are the same in both record sets.

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

## Baseline vs current

| Metric | Previous | Current | Change |
| --- | ---: | ---: | ---: |
| Attempted reports | 15 | 15 | 0 |
| Verified acquisitions | 0 | 0 | 0 |
| Acquisition success rate | 0.00% | 0.00% | 0.00 pp |
| Browser Use Agent reports | 2 | 2 | 0 |
| Browser Use Agent calls | 11 | 9 | -2 (-18.18%) |
| Input / cached / output tokens | 262,425 / 81,536 / 12,080 | 204,883 / 81,536 / 9,141 | -57,542 / 0 / -2,939 |
| Browser launches | 15 | 15 | 0 |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.071419 | $0.051158 | -$0.020261 (-28.37%) |
| Cost per verified acquisition | not defined | not defined | not comparable |
| Acquisition duration | 5,258.190 s | 5,228.395 s | -29.795 s (-0.57%) |

No report passed normal artifact verification. The results are comparable and
show reduced Agent work, model cost, and elapsed acquisition time, but no
verified acquisition improvement; therefore the result is not a verified
success improvement.

## Current per-report results

Every record used `browser_email_form`, terminated as
`browser_download_agent_timeout`, and failed normal artifact verification.
The two reports with Agent calls were Criteo (3) and Adjust (6).

| Candidate | Agent calls | Verified | Duration |
| --- | ---: | --- | ---: |
| fac_fa1889b4c19f0f238659145e | 3 | no | 344.742 s |
| fac_0ef70242a602b9ed7641c056 | 6 | no | 357.498 s |
| fac_3e630244e5c22fe8fa787255 | 0 | no | 352.030 s |
| fac_4da62bac17be2e7185090695 | 0 | no | 352.360 s |
| fac_c0e4c925c1ed4ce6149711b8 | 0 | no | 350.877 s |
| fac_6f994caaf9a413e4038f18f1 | 0 | no | 353.619 s |
| fac_79d2b1c0c59436f8eacd7de4 | 0 | no | 348.735 s |
| fac_057817530e711866e5fea457 | 0 | no | 345.201 s |
| fac_74ff8c2c4382773a4f8d5f55 | 0 | no | 344.708 s |
| fac_80dc158f27be79e08f090b8c | 0 | no | 346.278 s |
| fac_c21286d0bf9647749fa4dae3 | 0 | no | 346.153 s |
| fac_6dae1d79b7340a3e0fd5055b | 0 | no | 346.484 s |
| fac_248c234f4d797e8eca595ff3 | 0 | no | 345.480 s |
| fac_0a2d080a0bcc92e54f50e171 | 0 | no | 346.950 s |
| fac_05b9e5cae6b0bbaf35801e27 | 0 | no | 347.280 s |

Verified route resolution counts: HTTP/direct 0; private API 0; browser
preflight 0; deterministic standard form 0; deterministic learned playbook 0;
remembered blocker 0; Browser Use Agent 0.

Against the previously retained run of the same report-acquisition scope,
current main reduced Browser Use incidence by 0 reports, Agent calls by 2,
input/cached/output tokens by 57,542/0/2,939, browser launches by 0, cost by
$0.020261, and acquisition time by 29.795 seconds. Verified acquisition
success did not regress: it remained 0/15.
