# Blinded Public Editorial Evaluation Template

> **Documentation type:** Quality procedure
> **Canonical topic:** Human acceptance evidence for public editorial release quality

Use this template after the deterministic gate passes its retained corpus. It is intentionally a human process: automated checks do not substitute for independent editorial judgement.

1. Select 30 retained production reports that passed `public_editorial_quality_after` without a waiver. Randomize their order and remove internal report IDs, validator results, source filenames, and model metadata.
2. Give each reviewer only the public rendering and its visible citations. Do not disclose whether any report was regenerated.
3. Each reviewer scores factual accuracy, insight value, naturalness, and executive usefulness on a 1–5 scale, and records a brief defect note only when a score is below 4.
4. Record the report slug, reviewer pseudonym, date, four scores, and any defect note in a private access-controlled evaluation record. Keep source documents and quality reports available only for adjudication.
5. Calculate per-dimension medians across the 30 reports. Acceptance requires a median of at least 4.0 for every dimension and zero unresolved critical factual defects. Re-run only the affected report through the deterministic gate and targeted regeneration after an adjudicated defect.

| Report | Reviewer | Accuracy | Insight value | Naturalness | Executive usefulness | Critical defect? | Note |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `public-report-slug` | `reviewer-01` |  |  |  |  |  |  |

The completed record is release evidence. Do not copy report text, private quality explanations, credentials, or raw source extracts into operational logs.
