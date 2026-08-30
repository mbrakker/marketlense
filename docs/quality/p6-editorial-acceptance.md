# P6 editorial acceptance validation

Status: **ACTIVE — Batch 1 awaiting human review**

## Batch 1 cohort definition

Batch 1 is a fixed five-report blind editorial-review cohort. It was admitted before generation under `validation:22dca463b14045be841b46c4464a7392a3a2257cfb863c7361aa0d9723f913f0`; no source was substituted or removed because of generated output.

| # | Report | Publisher | Source PDF | Retained final HTML |
| --- | --- | --- | --- | --- |
| 1 | Email, SMS, and push marketing statistics for ecommerce in 2024 | Omnisend | [Google Drive PDF](https://drive.google.com/file/d/1_7x4DqjM4r52fo3qyZNiw1v0l11K0WrO/view) | [final.html](../../out/p6_editorial_acceptance/batch_01/report_01/final.html) |
| 2 | Activate Consulting Technology & Media Outlook 2025: eCommerce | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/19BcPSRlpaxSSLFsitNaoRLTUgptmvPq1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01/report_02/final.html) |
| 3 | Internet Advertising Revenue Report: Full-year 2024 results | IAB | [Google Drive PDF](https://drive.google.com/file/d/1UrnZwv5BD8Jiy8ML8nU4CA0W9-ImUF6-/view) | [final.html](../../out/p6_editorial_acceptance/batch_01/report_03/final.html) |
| 4 | Trust or trepidation?: How Brits feel about generative AI in media | YouGov | [Google Drive PDF](https://drive.google.com/file/d/1sZqPKxGqkEAvQr-fP90m53z2Y0l0jLkd/view) | [final.html](../../out/p6_editorial_acceptance/batch_01/report_04/final.html) |
| 5 | Activate Technology & Media Outlook 2026 | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/1mXGpczPyU-BCF9nhgQPsMQ7xoUQ7QGM1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01/report_05/final.html) |

## Selection methodology

The cohort was deterministically selected before generation from real Drive PDFs with distinct canonical source identities, exact Drive-file MD5 provenance, and duplicate/mirror exclusion. It intentionally spans ecommerce lifecycle marketing; marketplace-adjacent ecommerce and retail media; digital advertising; consumer attitudes; and a broader technology/media outlook. It includes 17-, 19-, 24-, 36-, and 250-page reports, including data-heavy chart/table reports and a narrative trend report. The selection did not use generated editorial quality, and all five admitted reports remain in the denominator.

The exact selection/admission record is [cohort_manifest.json](../../out/p6_editorial_acceptance/batch_01/cohort_manifest.json). The completed review package is [manifest.json](../../out/p6_editorial_acceptance/batch_01/manifest.json).

## Run and configuration identity

- Repository HEAD: `e8879163ddcfe5054be2a37d20b80b9c3e02dc8f`
- Cohort-freeze run: `9bdca704-9fcd-42ba-a6f0-1f55ea2f09cb`
- Generation run: `b6bae5cd-01e6-41a6-a5db-8f213721f072`
- Validation run: `validation:22dca463b14045be841b46c4464a7392a3a2257cfb863c7361aa0d9723f913f0`
- Configuration profile: `p6_editorial_acceptance_batch_01` ([config](../../src/config/app.p6_editorial_acceptance_batch_01.yaml)); configuration hash `e02fd53f0198a020650d7f5bbd60027f82ba0392cc5d31bede7149ab508120a7`
- Model: `gpt-5.6-luna`

Only source identity/provenance required for admission was seeded into the isolated P6 state. No E8/E9 retained editorial or derived report artifacts were reused.

## Pipeline and readiness results

All five reports completed the normal fresh ingest/report-generation pipeline. Every final validation and publish-readiness artifact reports `pass`; reports 3–5 retained non-blocking validation warnings. Normal bounded validation regeneration occurred for reports 1 (three attempts, third promoted), 4 (three attempts, third promoted), and 5 (two attempts, second promoted). No report was regenerated or altered by an operator to improve review quality.

The retained `final.html` files are byte-identical SHA-256 copies of the pipeline HTML outputs. Google Drive was read-only; Drive writes, WordPress writes, and public writes were all zero.

## Attributable provider usage

| # | Calls | Input tokens | Output tokens | Estimated cost (USD) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 35 | 329,059 | 33,510 | 0.106027 |
| 2 | 21 | 170,043 | 18,913 | 0.056704 |
| 3 | 22 | 202,324 | 26,966 | 0.072825 |
| 4 | 38 | 278,974 | 31,209 | 0.093248 |
| 5 | 38 | 376,057 | 34,976 | 0.117183 |
| Total | 154 | 1,356,457 | 145,574 | 0.445987 |

## Human-review results

| # | Reviewer | Review date | Editorial decision | Notes |
| --- | --- | --- | --- | --- |
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |

## Batch 1 rerun after system upgrade (2026-08-30)

The same five frozen canonical sources were rerun with the production-intended upgraded checkout. The rerun used only the exact source-PDF provenance required for admission; it did not reuse the original Batch 1 editorial or derived report artifacts. No prompt, editorial logic, generated HTML, or individual report content was manually changed.

| # | Report | Publisher | Source PDF | Rerun final HTML | Pipeline | Readiness |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Email, SMS, and push marketing statistics for ecommerce in 2024 | Omnisend | [Google Drive PDF](https://drive.google.com/file/d/1_7x4DqjM4r52fo3qyZNiw1v0l11K0WrO/view) | — | held: `report_payload_incomplete` | not evaluated |
| 2 | Activate Technology & Media Outlook 2025: eCommerce | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/19BcPSRlpaxSSLFsitNaoRLTUgptmvPq1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_rerun_20260830/report_02/final.html) | pass (warning) | pass |
| 3 | Internet Advertising Revenue Report: Full-year 2024 results | IAB | [Google Drive PDF](https://drive.google.com/file/d/1UrnZwv5BD8Jiy8ML8nU4CA0W9-ImUF6-/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_rerun_20260830/report_03/final.html) | pass (warning) | pass |
| 4 | Trust or trepidation?: How Brits feel about generative AI in media | YouGov | [Google Drive PDF](https://drive.google.com/file/d/1sZqPKxGqkEAvQr-fP90m53z2Y0l0jLkd/view) | — | held: `report_payload_incomplete` | not evaluated |
| 5 | Activate Technology & Media Outlook 2026 | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/1mXGpczPyU-BCF9nhgQPsMQ7xoUQ7QGM1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_rerun_20260830/report_05/final.html) | pass | pass |

- Repository HEAD: `e702a918c259b88ab37cbff6b36eb9b9960a51f2`
- Generation run: `2df49a0c-a92a-4b25-8221-8ec8a4651b81`; validation run: `validation:1f7baf088800db32f8da65ad2151f69085c683eea8f8ffb81b42c0fdc8191bb7`
- Configuration: [`p6_editorial_acceptance_batch_01_rerun_20260830`](../../src/config/app.p6_editorial_acceptance_batch_01_rerun_20260830.yaml), hash `f2f341af1fcb234710bc480773a5bbff0fa77eb87464328b205f11037872b5a5`
- Attributable provider use: 130 calls, 1,194,670 input tokens, 123,473 output tokens, estimated USD 0.387106.

Reports 1 and 4 remain in the denominator: their normal recovery path created non-retryable `report_payload_incomplete` holds, so no substitute source, editorial repair, or extra generation was performed. Reports 2, 3, and 5 include only the pipeline's bounded validation regenerations. The retained HTML copies were verified byte-identical to their final pipeline outputs. Google Drive, WordPress, and public writes were zero.

The rerun review package is [manifest.json](../../out/p6_editorial_acceptance/batch_01_rerun_20260830/manifest.json); its cohort provenance is [cohort_manifest.json](../../out/p6_editorial_acceptance/batch_01_rerun_20260830/cohort_manifest.json).

## Batch 1 systematic payload-completeness rerun (2026-08-30)

The same five frozen sources were generated afresh after report-agnostic fixes to (1) ensure the final artifact selector supplies the report payload's required five grounded insight slots when the plan has fewer themes, and (2) bound crop artifact names so fingerprint sidecars fit in deep isolated output directories on Windows. The fixes do not rank, score, or repair individual reports, and no prompt or editorial rule was changed based on the quality of a specific output.

| # | Report | Publisher | Source PDF | Final HTML | Pipeline | Readiness |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Email, SMS, and push marketing statistics for ecommerce in 2024 | Omnisend | [Google Drive PDF](https://drive.google.com/file/d/1_7x4DqjM4r52fo3qyZNiw1v0l11K0WrO/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_payload_fix_crop_path_20260830/report_01/final.html) | pass (warning) | pass |
| 2 | Activate Technology & Media Outlook 2025: eCommerce | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/19BcPSRlpaxSSLFsitNaoRLTUgptmvPq1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_payload_fix_crop_path_20260830/report_02/final.html) | pass (warning) | pass |
| 3 | Internet Advertising Revenue Report: Full-year 2024 results | IAB | [Google Drive PDF](https://drive.google.com/file/d/1UrnZwv5BD8Jiy8ML8nU4CA0W9-ImUF6-/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_payload_fix_crop_path_20260830/report_03/final.html) | pass (warning) | pass |
| 4 | Trust or trepidation?: How Brits feel about generative AI in media | YouGov | [Google Drive PDF](https://drive.google.com/file/d/1sZqPKxGqkEAvQr-fP90m53z2Y0l0jLkd/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_payload_fix_crop_path_20260830/report_04/final.html) | pass (warning) | pass |
| 5 | Activate Technology & Media Outlook 2026 | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/1mXGpczPyU-BCF9nhgQPsMQ7xoUQ7QGM1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_payload_fix_crop_path_20260830/report_05/final.html) | pass (warning) | pass |

- Repository HEAD before the run: `e702a918c259b88ab37cbff6b36eb9b9960a51f2`.
- Generation run: `7b8c4c2b-de4c-4aff-995d-4305299a1210`; validation run: `validation:465c54f28694e230af78410beb5ce5b45d1dbe9fc41dc914d4a3a3206ed07dfc`.
- Configuration: [`p6_editorial_acceptance_batch_01_payload_fix_crop_path_20260830`](../../src/config/app.p6_editorial_acceptance_batch_01_payload_fix_crop_path_20260830.yaml), hash `b1b3d7334df57831909c10e6887fb0d0411fe394ed56473c7b93027121c8d305`.
- Attributable provider use: 119 calls, 1,058,031 input tokens, 107,980 output tokens, estimated USD 0.341182.

All five canonical identities and exact Drive file IDs were verified against the admitted-source provenance. The retained copies are byte-identical SHA-256 copies of the final pipeline HTML. The isolated profile remained Drive read-only and disabled WordPress/public writes; no quality, grounding, semantic, chart/table, editorial, or publish-readiness gate was bypassed. The current review package is [manifest.json](../../out/p6_editorial_acceptance/batch_01_payload_fix_crop_path_20260830/manifest.json), with its [cohort provenance](../../out/p6_editorial_acceptance/batch_01_payload_fix_crop_path_20260830/cohort_manifest.json).

### Human-review results for the current rerun

| # | Reviewer | Review date | Editorial decision | Notes |
| --- | --- | --- | --- | --- |
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |
