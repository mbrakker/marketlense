# Production-workflow validation reuse — 2026-09-14

> **Evidence type:** retained bounded live-validation record
> **Scope:** one retained report; full canary path, not `--preflight-only`

## Result

The retained Algolia report
`out/browser_downloads/www.algolia.com/2ef62190c537/2026%20B2C%20ecommerce%20AI%20trends_eBook_EN_2.pdf`
(MD5 `86858bdcb370266f26c29b40316a4db0`) completed through the normal
production workflow refactored in commit
`ea3870346b0591bc7e2c24415eb34b674fbd447a`.

| Evidence | Retained value |
| --- | --- |
| Production admission | `admitted` |
| Report/source identity | `cohort-86858bdcb370266f26c2` / `source:4ea9ae5709898e763efb0945d8d4fa1e` |
| Validation run | `validation:f73183ffa616d260cec2ebb670dbf91148c09d7a3ae756d9bcccf21789da1977` |
| Root workflow | `e522a3e2-33d0-41f5-b8d3-96903732c750` |
| Terminal result | `awaiting_review`; validation and publication-readiness both passed |
| Execution owner | `ias-live-canary:e522a3e2-33d0-41f5-b8d3-96903732c750:<queue>` supervisor workers |
| Publication side effect | none; the run stopped at the normal `awaiting_review` boundary |
| Duration / model cost | 676.242 seconds / USD 0.166396 |

The durable queue lineage was `source_ingest` → `report_selection` →
`report_analysis` → `report_render` → `publication_readiness`; every listed
stage succeeded in one attempt. The non-blocking `analytics_projection` job
subsequently ended `dead_letter` with `cross_report_contract_invalid`; it did
not change the already-completed report terminal state.

The validation manifest retained successful records for `admission_preflight`,
`candidate_qualification`, `source_preparation`, `source_validation`,
`discovery`, `taxonomy`, `category_fit`, `evidence_generation`,
`semantic_validation`, `grounding_validation`, `artifact_generation`,
`analysis_complete`, `regeneration`, `rendering`, `final_html_validation`, and
`publication_preflight`; `structured_output_repair` was explicitly `skipped`.
Every record carries the root workflow ID above.

The isolated runtime produced 82 report artifacts. Bounded artifact evidence:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Final HTML | 69,343 | `36ae8bcac1b981d5ca9945df88f070e45a14d1f3ff2250ce0fe085740343f357` |
| Validation record | 1,063 | `790e00eef34b5c2a6604cd9ed6ac16076e764f593a095953bf066518e58321a1` |
| Publication-readiness record | 8,911 | `cd1ff992fadf29743a73968992af06614da1d8433e95a3f02965b1ad3d32d16f` |
| Report-card manifest | 2,494 | `f5bf4826959f9485347a107a2e8221fd6a1efecc433a4f1d4750b510f8156ad6` |
| Preview image | 2,128,153 | `fa76cfc4944194d2637d38c81c80803a4d061e904a1992d8eb594238714982d4` |

## Defect found and corrected during verification

The first live attempt reached the production supervisor but failed in
`report_analysis` with the typed `category_mapping_missing` error: the isolated
copied configuration resolved repository-owned relative paths below its
temporary configuration directory. The runner now pins the immutable category
mapping, publisher-profile, and cover-style resources to their repository
locations while preserving isolated mutable paths. The successful rerun above
is the evidence for the corrected path.

`--preflight-only` was not used for this result; it remains a separately scoped
component admission check and is not end-to-end evidence.
