# Jungle Scout acquisition validation — 2026-08-23

## Verdict: VERIFIED IMPROVEMENT

Acquisition-only, process-isolated replay of the exact nine Jungle Scout candidates
that timed out in the retained baseline. No discovery, ingest, analysis, extraction,
generation, publishing, or WordPress stage was run.

## Comparable evidence

| Item | Retained location / value |
| --- | --- |
| Baseline cohort | `../browser_gated_recovery_15_20260822_191800/frozen_source_manifest.json` |
| Baseline attempts | `../browser_gated_recovery_15_20260822_191800/baseline/acquisition_attempts.jsonl` |
| Baseline manifest SHA-256 | `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9` |
| Baseline attempts SHA-256 | `F9B269886C1E692327E8597D2569293077B666D4F6A54057B645488CDDE5E8F1` |
| Current code SHA | `00706cd76bb6298d02b8123e56cd062c11145496` |
| Current configuration | `configuration.yaml` (SHA-256 `E98A65C1B1651BAE682264AA7F4393AF6D38DF8848D49D02C8FE826FEDA86B9B`) |
| Current attempt evidence | `current_replay/acquisition_attempts.jsonl` (SHA-256 `B6141517DE08EE71AD612DE3F077A2EF667E6B77202C1977D22B3C47546EDF0C`) |
| Current replay summary | `current_replay/diagnostic_replay.json` (SHA-256 `888B979B0778C4024F5F9A16812CBF9E8463F37F6756F4304BE7A74E881B051A`) |

The replay uses the retained identities/model configuration, an isolated state and
output directory, zero retries, and a 720-second process-isolated per-attempt cap.
The implementation did not call a model for this cohort.

## Results

| Metric | Baseline | Current | Change |
| --- | ---: | ---: | ---: |
| Attempted reports | 9 | 9 | 0 |
| Verified acquisitions | 0 | 9 | +9 |
| Acquisition success rate | 0.0% | 100.0% | +100.0 pp |
| Browser Use Agent reports / calls | 0 / 0 | 0 / 0 | 0 / 0 |
| Input / cached / output tokens | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Browser launches | 9 | 0 | -9 (100.0%) |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.000000 | $0.000000 | $0.000000 |
| Cost per verified acquisition | n/a | $0.000000 | n/a |
| Total acquisition duration | 3,137.488 s | 167.845 s | -2,969.643 s (-94.65%) |

Each current acquisition passed the normal verification requirements: artifact exists,
Drive persistence is recorded, PDF signature is valid, route verification passed, and
the artifact is marked usable. The result is a complete PDF rendered from every
publicly available page in the embedded Issuu reader; it is not represented as the
publisher's original PDF.

## Current route counts

| Route | Reports |
| --- | ---: |
| HTTP/direct (public form redirect to public Issuu reader) | 9 |
| Private API | 0 |
| Browser preflight | 0 |
| Deterministic standard form | 0 |
| Deterministic learned playbook | 0 |
| Remembered blocker | 0 |
| Browser Use Agent | 0 |

## Per-report results

| Candidate | Slug | Pages | Route | Duration |
| --- | --- | ---: | --- | ---: |
| `fac_79d2b1c0c59436f8eacd7de4` | `3p-seller-disruption` | 44 | HTTP/direct → `browser_onsite_report` rendered PDF | 27.382 s |
| `fac_057817530e711866e5fea457` | `amazon-benchmark-report-2026` | 109 | HTTP/direct → `browser_onsite_report` rendered PDF | 24.165 s |
| `fac_74ff8c2c4382773a4f8d5f55` | `arts-crafts-sewing` | 18 | HTTP/direct → `browser_onsite_report` rendered PDF | 19.349 s |
| `fac_80dc158f27be79e08f090b8c` | `innovation` | 35 | HTTP/direct → `browser_onsite_report` rendered PDF | 21.688 s |
| `fac_c21286d0bf9647749fa4dae3` | `body-skincare` | 10 | HTTP/direct → `browser_onsite_report` rendered PDF | 13.387 s |
| `fac_6dae1d79b7340a3e0fd5055b` | `camping-hiking` | 26 | HTTP/direct → `browser_onsite_report` rendered PDF | 20.830 s |
| `fac_248c234f4d797e8eca595ff3` | `car-care` | 10 | HTTP/direct → `browser_onsite_report` rendered PDF | 14.197 s |
| `fac_0a2d080a0bcc92e54f50e171` | `parts-accessories` | 10 | HTTP/direct → `browser_onsite_report` rendered PDF | 13.398 s |
| `fac_05b9e5cae6b0bbaf35801e27` | `cosmetics` | 11 | HTTP/direct → `browser_onsite_report` rendered PDF | 13.449 s |

A visual check of representative first pages is retained in `screenshots/`. The PDF
pages were rendered locally with PyMuPDF because Poppler was unavailable in this
environment.
