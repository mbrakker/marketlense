# P6 editorial acceptance validation

Status: **ACTIVE — Batch 1 human-review score matrix recorded**

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

### Score matrix — latest five-report rerun

The following reviewer-supplied matrix applies to the latest five-report
rerun. It is a qualitative human-review record, not an automated judgment and
does not change any generated HTML, prompt, editorial rule, or cohort member.
Charts and tables are excluded from this benchmark as agreed. Scores are out
of 10; LinkedIn quality is assessed separately; `Weighted /100` uses the same
editorial weighting as the prior matrix, normalized without charts/tables.

| Dimension | Activate eCom 2025 (#2) | IAB 2024 (#3) | YouGov AI (#4) | Omnisend (#1) | Activate 2026 (#5) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Factual fidelity | 9.5 | 9.5 | 9.5 | 9.5 | 9.0 |
| Evidence selection | 9.0 | 9.0 | 9.5 | 9.0 | 9.0 |
| Analytical depth | 8.0 | 8.5 | 9.0 | 9.0 | 8.5 |
| Insight specificity | 9.5 | 9.5 | 9.5 | 9.0 | 9.0 |
| Commercial relevance | 9.5 | 9.0 | 9.0 | 9.0 | 9.0 |
| Charts & tables | — | — | — | — | — |
| Narrative structure | 9.0 | 9.0 | 9.0 | 9.0 | 8.5 |
| Editorial clarity | 9.0 | 9.0 | 9.0 | 9.0 | 8.5 |
| Expert credibility / human feel | 8.5 | 8.5 | 9.5 | 8.5 | 8.0 |
| Completeness | 9.0 | 9.0 | 9.5 | 9.0 | 8.0 |
| LinkedIn quality | 9.2 | 9.1 | 9.2 | 9.0 | 9.0 |
| **Weighted /100** | **89.7** | **90.0** | **92.8** | **90.3** | **86.7** |

Exact reviewed HTML outputs:

| # | Report | Reviewed final HTML |
| --- | --- | --- |
| 1 | Omnisend | [final HTML](../../out/p6_editorial_acceptance/batch_01_evidence_reliability_20260831_v6/pipeline_output/2023-email-sms-and-push-report-pdf.html) |
| 2 | Activate eCom 2025 | [final HTML](../../out/p6_editorial_acceptance/batch_01_evidence_reliability_20260831_v6/pipeline_output/2412-activate-technology-and-media-outlook-2025-ecommerce-pdf.html) |
| 3 | IAB 2024 | [final HTML](../../out/p6_editorial_acceptance/batch_01_evidence_reliability_20260831_v6/pipeline_output/iab-pwc-internet-ad-revenue-report-full-year-2024-pdf.html) |
| 4 | YouGov AI | [final HTML](../../out/p6_editorial_acceptance/batch_01_evidence_reliability_20260831_v6/pipeline_output/uk-attitudes-to-ai-in-media-report-2025-pdf.html) |
| 5 | Activate 2026 | [final HTML](../../out/p6_editorial_acceptance/batch_01_evidence_reliability_20260831_v6/pipeline_output/activate-technology-media-outlook-2026-acig-pdf.html) |

## Batch 1 upgraded-checkout rerun (2026-08-31)

The same five frozen canonical sources were generated afresh on the upgraded checkout. Only exact source PDFs and canonical source-identity provenance were recovered for admission; prior editorial, analysis, HTML, and validation artifacts were not reused. No prompt, editorial logic, source selection, generated HTML, or report content was manually changed.

| # | Report | Publisher | Source PDF | Final HTML | Pipeline | Readiness |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Email, SMS, and push marketing statistics for ecommerce in 2024 | Omnisend | [Google Drive PDF](https://drive.google.com/file/d/1_7x4DqjM4r52fo3qyZNiw1v0l11K0WrO/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260831/report_01/final.html) | failed: validation_failed | held: publish_readiness_failed |
| 2 | Activate Technology & Media Outlook 2025: eCommerce | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/19BcPSRlpaxSSLFsitNaoRLTUgptmvPq1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260831/report_02/final.html) | pass (warning) | publish_ready |
| 3 | Internet Advertising Revenue Report: Full-year 2024 results | IAB | [Google Drive PDF](https://drive.google.com/file/d/1UrnZwv5BD8Jiy8ML8nU4CA0W9-ImUF6-/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260831/report_03/final.html) | failed: validation_failed | held: publish_readiness_failed |
| 4 | Trust or trepidation?: How Brits feel about generative AI in media | YouGov | [Google Drive PDF](https://drive.google.com/file/d/1sZqPKxGqkEAvQr-fP90m53z2Y0l0jLkd/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260831/report_04/final.html) | pass (warning) | publish_ready |
| 5 | Activate Technology & Media Outlook 2026 | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/1mXGpczPyU-BCF9nhgQPsMQ7xoUQ7QGM1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260831/report_05/final.html) | pass | publish_ready |

- Repository HEAD: `8034f69e1b85ab450e0fa2cb93564db6621cdfa3`.
- Generation run: `4828e5e0-bca3-4189-997d-c4e697de4088`; validation run: `validation:31a397c3506c40b657e8bb7527cd844c58eb388f769d04371d0715c1f468f04c`.
- Configuration: [`p6_editorial_acceptance_batch_01_upgrade_rerun_20260831`](../../src/config/app.p6_editorial_acceptance_batch_01_upgrade_rerun_20260831.yaml), hash `eb9399c82b12805dbbbaa1b41f0910e98a761ef94fae8d07583f8faa4d2874d8`.
- Attributable provider use: 159 calls, 1,685,386 input tokens, 184,371 output tokens, estimated USD 0.558318.
- All five sources received the pipeline's bounded targeted validation recovery. It succeeded for reports 2, 4, and 5; reports 1 and 3 reached terminal validation failure and remain in the cohort denominator.

All five Google Drive IDs, PDF MD5 checksums, and canonical source identities match the frozen cohort. The retained HTML files are byte-identical SHA-256 copies of their pipeline HTML counterparts. The normal admission, schema, grounding, semantic, chart/table, editorial, final-HTML, and publish-readiness stages reached their recorded terminal outcomes; none was bypassed. Google Drive reads/writes, WordPress writes, browser launches, and public writes were zero.

The review package is [manifest.json](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260831/manifest.json), with [cohort provenance](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260831/cohort_manifest.json).

### Human-review results for the 2026-08-31 rerun

| # | Reviewer | Review date | Editorial decision | Notes |
| --- | --- | --- | --- | --- |
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |

## Batch 1 upgraded-checkout rerun for human review (2026-08-30)

This is a fresh rerun of the same frozen five-source P6 Batch 1 cohort after the system upgrade. It retained only exact source-PDF and canonical source-identity provenance for admission; no earlier editorial, analysis, or generated-report artifact was reused. No prompt, editorial rule, source selection, or generated HTML was manually changed.

| # | Report | Publisher | Source PDF | Final HTML | Pipeline | Readiness |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Email, SMS, and push marketing statistics for ecommerce in 2024 | Omnisend | [Google Drive PDF](https://drive.google.com/file/d/1_7x4DqjM4r52fo3qyZNiw1v0l11K0WrO/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260830_v2/report_01/final.html) | pass | publish_ready |
| 2 | Activate Technology & Media Outlook 2025: eCommerce | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/19BcPSRlpaxSSLFsitNaoRLTUgptmvPq1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260830_v2/report_02/final.html) | pass (warning) | publish_ready |
| 3 | Internet Advertising Revenue Report: Full-year 2024 results | IAB | [Google Drive PDF](https://drive.google.com/file/d/1UrnZwv5BD8Jiy8ML8nU4CA0W9-ImUF6-/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260830_v2/report_03/final.html) | pass (warning) | publish_ready |
| 4 | Trust or trepidation?: How Brits feel about generative AI in media | YouGov | [Google Drive PDF](https://drive.google.com/file/d/1sZqPKxGqkEAvQr-fP90m53z2Y0l0jLkd/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260830_v2/report_04/final.html) | pass (warning) | publish_ready |
| 5 | Activate Technology & Media Outlook 2026 | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/1mXGpczPyU-BCF9nhgQPsMQ7xoUQ7QGM1/view) | [final.html](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260830_v2/report_05/final.html) | pass | publish_ready |

- Repository HEAD: `015c91e5f31b43c069130391b092879df38b42ea`.
- Generation run: `ab82ec36-ecda-4da9-964c-3d5ed3a2cc92`; validation run: `validation:886a74a398aee4e9c4b9981d8be52de7d2c5123ca691150a08554e40c0685629`.
- Configuration: [`p6_editorial_acceptance_batch_01_upgrade_rerun_20260830_v2`](../../src/config/app.p6_editorial_acceptance_batch_01_upgrade_rerun_20260830_v2.yaml), hash `0be543ac4d0af98bd810a17916188ed62e6cb95bc9fe46a3d0c9e5dda98c8c42`.
- Attributable provider use: 127 calls, 1,178,058 input tokens, 125,718 output tokens, estimated USD 0.386468.
- Normal bounded validation regeneration ran for reports 1, 4, and 5; it was not an operator-initiated quality rerun. Reports 2 and 3 required no regeneration.

All five source PDF MD5 values and five canonical identities match the frozen admitted cohort. The retained files are byte-identical SHA-256 copies of the final pipeline HTML. The normal admission, schema, grounding, semantic, chart/table, editorial, final-HTML, and publish-readiness stages all reached their recorded terminal outcomes; no gate was bypassed. Drive reads/writes, WordPress writes, public writes, and browser launches were zero.

The current review package is [manifest.json](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260830_v2/manifest.json), with [cohort provenance](../../out/p6_editorial_acceptance/batch_01_upgrade_rerun_20260830_v2/cohort_manifest.json).

### Human-review results for the upgraded-checkout rerun

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

## Batch 2 cohort definition

Status: **ACTIVE — Batch 2 human-review score matrix recorded**

Batch 2 is a fixed five-report blind editorial-review cohort. Its immutable admission record is [cohort_manifest_final_generation.json](../../out/p6_editorial_acceptance/batch_02/cohort_manifest_final_generation.json); all five admitted reports remain in the denominator, including outputs held by final publish-readiness.

| # | Report | Publisher | Source PDF | Retained final HTML | Pipeline | Readiness |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Activate Consulting Technology & Media Outlook 2025 | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/1snMTUyfA1GMDKMMT5Y8XZs8kivti7m1f/view) | [final.html](../../out/p6_editorial_acceptance/batch_02/report_01/final.html) | held: `publish_readiness_failed` | fail |
| 2 | The Post-COVID Online Shopper: New Challenges and Opportunities | Activate Consulting | [Google Drive PDF](https://drive.google.com/file/d/1E0hEr2nEfRjTsgT3clKCn4b30Hg6xp1Z/view) | [final.html](../../out/p6_editorial_acceptance/batch_02/report_02/final.html) | processed (validation warning) | pass |
| 3 | Annual Report 2025 | IAB | [Google Drive PDF](https://drive.google.com/file/d/1xyRvXkqInet89EjHW4hyfAoMRO69Vpow/view) | [final.html](../../out/p6_editorial_acceptance/batch_02/report_03/final.html) | held: `publish_readiness_failed` | fail |
| 4 | Retail Marketing Trends: How To Win in 2026 | StackAdapt Inc. | [Google Drive PDF](https://drive.google.com/file/d/1zt4RcZ-7dFNtf9zVWK2kUMpqJMSouUGn/view) | [final.html](../../out/p6_editorial_acceptance/batch_02/report_04/final.html) | processed | pass |
| 5 | Your definitive guide to AI-powered mobile marketing | Adjust | [Google Drive PDF](https://drive.google.com/file/d/1Y6gEFvvBcsabWsOX-t0LDxtlDo87Ue3h/view) | [final.html](../../out/p6_editorial_acceptance/batch_02/report_05/final.html) | processed | pass |

## Selection methodology

Selection occurred before final generation from real Drive PDFs, excluding every Batch 1 canonical identity. Admission preflight required a unique canonical source identity, duplicate/mirror exclusion, matching PDF MD5 provenance, readable structure, and sufficient evidence potential. The deterministic cohort includes a 206-page, data-heavy technology/media outlook; a 38-page online-shopper report; a 49-page digital-advertising annual report; a 22-page retail-marketing trend report; and a 24-page AI-powered mobile-marketing guide. This gives coverage of ecommerce, marketplace/shopper behaviour, digital advertising, retail/consumer behaviour, and an adjacent MarketLense topic without selecting on generated editorial quality.

## Run and configuration identity

- Repository HEAD and producer build identity: `3b0baa0f1f4a6705d36a39b0e42e718ba4e31f39`
- Final generation run: `85e8effd-a70e-45f9-b7ae-41eb4d992df6`
- Validation run: `validation:cee70e95a26bf1f87183b0be7f04f7de9594a351437d15617dc35491289bac29`
- Cohort ID: `6bc24060e7fb7d5e107c17d012492f9a550f2ceff67bf5dc3f3dcb2d99e55d64`
- Profile: [`p6_editorial_acceptance_batch_02_final_generation_20260901`](../../src/config/app.p6_editorial_acceptance_batch_02_final_generation_20260901.yaml); configuration hash `8bacef60b0bb707fae98285a6280d0bfae67109bb665eec1df0fe6a74932b25c`; policy hash `77302ec0862da786102ee09959e210ef62e9bf9ae8b2df1e5972b9cbaf9e2df7`
- Model: `gpt-5.6-luna`

Only immutable source identity and source-PDF provenance were recovered into the final isolated run; no E8/E9 editorial, analysis, validation, report, or rendered-HTML artifact was reused. A report-agnostic validation-manifest source-identity correction was made before this clean run; it preserved the admitted canonical identity at the report-analysis stage and did not modify prompts, editorial logic, or individual report content.

## Pipeline and readiness results

All five sources completed the normal fresh ingest/report-generation path and emitted an HTML artifact. Reports 1 and 3 reached terminal `publish_readiness_failed` holds after the normal bounded regeneration path; their outputs are retained for human review and were neither replaced nor manually repaired. Report 2 had one normal retry after `llm_usage_projection_busy`; report 4 had two such retries; report 5 had no retry. Reports 1 and 3 also had three bounded validation/artifact regeneration attempts each. No retry or regeneration was initiated to improve an editorial review result.

The canonical publish-readiness evidence reports three passes (2, 4, 5) and two failures (1, 3). The held reports failed the existing `editorial_quality`, `regeneration_promotion`, and `semantic_grounding` readiness rules; this is a recorded automated gate outcome, not a human editorial score.

Every retained `final.html` is a byte-identical SHA-256 copy of the pipeline HTML artifact. The source cache MD5 values match the frozen Drive file identities. The normal admission, schema, grounding, semantic, chart/table, editorial, final-HTML, and publish-readiness gates reached recorded terminal outcomes; none was bypassed. Google Drive remained read-only: Drive writes, WordPress writes, and public writes were zero.

The full package, including source IDs, canonical identities, pipeline paths, readiness, recovery history, hashes, and per-report provider attribution, is [manifest.json](../../out/p6_editorial_acceptance/batch_02/manifest.json).

## Attributable provider usage

| # | Calls | Input tokens | Output tokens | Estimated cost (USD) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 59 | 788,396 | 82,736 | 0.246267 |
| 2 | 29 | 241,033 | 25,285 | 0.078547 |
| 3 | 38 | 562,533 | 50,423 | 0.167967 |
| 4 | 24 | 174,958 | 21,621 | 0.059244 |
| 5 | 20 | 212,207 | 17,959 | 0.063992 |
| Final-output run total | 170 | 1,979,127 | 198,024 | 0.616017 |

Three earlier held runs are retained only for audit: the first reached an immutable validation-manifest identity hold before provider generation (zero calls), and the other two used 49 calls, 37,784 input tokens, 22,088 output tokens, and USD 0.034062. Across all Batch 2 generation attempts the total was 219 calls, 2,016,911 input tokens, 220,112 output tokens, and USD 0.650079.

## Human-review results

| # | Reviewer | Review date | Editorial decision | Notes |
| --- | --- | --- | --- | --- |
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |

### Score matrix — upgraded rerun

The following reviewer-supplied scores apply to the fresh upgraded rerun
(`46203b2a-4820-4392-863a-d6964fcf69f6`), not the earlier final-generation
attempt recorded above. This is a human-review record, not an automated
judgment; it does not change the cohort, prompts, editorial logic, or generated
HTML. The review date and reviewer identity were not supplied. Charts and
tables are excluded from this benchmark. Scores are out of 10; LinkedIn quality
is assessed separately; `Weighted /100` uses the established editorial weighting
normalized without charts/tables.

| Dimension | Adjust AI Mobile (#5) | StackAdapt Retail 2026 (#4) | IAB Annual 2025 (#3) | Activate Post-COVID (#2) | Activate Outlook 2025 (#1) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Factual fidelity | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 |
| Evidence selection | 9.0 | 9.0 | 9.0 | 9.5 | 8.5 |
| Analytical depth | 8.5 | 8.5 | 9.0 | 9.0 | 8.5 |
| Insight specificity | 8.5 | 9.0 | 9.5 | 9.5 | 9.0 |
| Commercial relevance | 9.0 | 9.5 | 9.0 | 9.0 | 9.0 |
| Charts & tables | — | — | — | — | — |
| Narrative structure | 9.0 | 8.5 | 9.0 | 9.5 | 8.5 |
| Editorial clarity | 9.0 | 8.5 | 9.0 | 9.5 | 9.0 |
| Expert credibility / human feel | 8.5 | 9.0 | 9.0 | 9.5 | 8.5 |
| Completeness | 9.0 | 8.5 | 8.5 | 9.5 | 8.0 |
| LinkedIn quality | 9.1 | 9.2 | 9.2 | 9.3 | 8.9 |
| **Weighted /100** | **88.9** | **89.4** | **91.1** | **93.6** | **87.8** |

Exact reviewed rerun outputs:

| # | Report | Reviewed final HTML |
| --- | --- | --- |
| 1 | Activate Consulting Technology & Media Outlook 2025 | [final HTML](../../out/p6_editorial_acceptance/batch_02/pipeline_output_rerun_20260901/activate-technology-and-media-outlook-2025-pdf.html) |
| 2 | The Post-COVID Online Shopper: New Challenges and Opportunities | [final HTML](../../out/p6_editorial_acceptance/batch_02/pipeline_output_rerun_20260901/activate-2022-post-covid-shopper-pdf.html) |
| 3 | IAB Annual Report 2025 | [final HTML](../../out/p6_editorial_acceptance/batch_02/pipeline_output_rerun_20260901/2025-iab-annual-report-pdf.html) |
| 4 | StackAdapt Retail Marketing Trends 2026 | [final HTML](../../out/p6_editorial_acceptance/batch_02/pipeline_output_rerun_20260901/stackadapt-retail-marketing-trends-report-2026-pdf.html) |
| 5 | Adjust AI-powered mobile marketing | [final HTML](../../out/p6_editorial_acceptance/batch_02/pipeline_output_rerun_20260901/adjust-ai-and-machine-learning-guide-pdf.html) |

The machine-readable companion is [rerun_20260901_human_review.json](../../out/p6_editorial_acceptance/batch_02/rerun_20260901_human_review.json).
