# Frozen full 20-report grounding and readiness measurement

## Run identity

- Implementation revision: `23fec7388553041aabcc3e1e0775abb559c6695d`
- Frozen manifest: [`../frozen_cohort.json`](../frozen_cohort.json), SHA-256 `4da8f4112f37bf880254fe85dc8784752fda089f0cac59f3989520370ae12286`; all 20 source files match their pinned checksums.
- Selected cohort SHA-256: `f48a54e301d667b7704cb091d6aa6128572b3ab14097cedfe0f7683dec1c46f6`
- Sanitized cohort result SHA-256: `2dc32d138076295c27c364ed283b116ce3e13a1854696ab018609083fc600b0d`
- Started: `2026-10-02T21:27:02Z`; completed: `2026-10-03T00:37:18.471183Z`
- Runner wall time: 11416.471s; summed report time: 11404.166s.
- State was fresh and isolated per report. The canonical production workflow ran all 20 frozen members; publication was disabled.
- The full workflow state and provider payloads remain in ignored isolated run storage. The committed JSON is a content-free measurement projection with report, artifact, package, validator, configuration, policy, evidence, and semantic lineage hashes only.

## Cohort statistics

| Measure | Result |
| --- | ---: |
| Admitted / terminal reports | 20 / 20 |
| Missing terminal reports | 0 |
| Reports passing final validation | 18 |
| Eligible for final package materialization | 18 |
| Final packages materialized and lineage-bound | 18 / 18 |
| Unexplained `package_missing` among eligible reports | 0 |
| `package_invalid` among eligible reports | 0 |
| Packages marked `not_publishable` | 1 |
| Report-scoped readiness passes | 16 / 20 overall (80.0%); 16 / 18 eligible reports (88.9%) |
| Readiness failures after package materialization | 2 |
| Typed pre-package validation failures | 2 |
| Provider calls during readiness | 0 |
| Publication jobs / published rows | 0 / 0 |
| Unsupported factual claims in materialized packages | 0 |
| Unresolved factual claims in materialized packages | 20 (all on Reuters Institute; retained claims remain blocked) |
| Provider calls across cohort processing | 720 |
| Input / output tokens | 6,486,716 / 1,443,087 |
| Estimated cohort cost | $1.321959 |
| Mean / median report duration | 570.208s / 493.472s |
| Mean / median report cost | $0.066098 / $0.065120 |
| Reports with bounded automatic repair | 8 / 20 (40%) |
| Operator interventions | 0 |

Package eligibility means final validation passed and the report entered report-scoped readiness. Each of these 18 reports has exactly one canonical `retained_claim_validation.json` and one `publish_readiness.json`; package hash, final artifact hash, report ID, source checksum/identity, validator versions, configuration/policy hashes, evidence-pack identity, semantic identity where present, and readiness bindings were verified. The two candidate-only reports did not have a final package or readiness record, and their candidate packages did not satisfy readiness.

Sixteen reports reached `awaiting_review` with readiness pass. That is a report-level readiness result; no report was published. The two reports that reached readiness and remained blocked are described below. Readiness and lineage checks made no provider calls.

## Per-report outcomes and performance

| Report | Validation | Readiness | Final package | Terminal reason | Calls | Input tokens | Output tokens | Cost | Duration | Bounded repair |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Capgemini Research Institute | pass | pass | awaiting_review | — | 35 | 315793 | 65763 | $0.063527 | 508.660s | no |
| Activate | pass | pass | awaiting_review | — | 56 | 394304 | 96308 | $0.081815 | 771.133s | yes |
| DoubleVerify | pass | pass | awaiting_review | — | 29 | 397419 | 61883 | $0.069747 | 444.626s | no |
| KPMG | fail | not evaluated | none | regeneration_evidence_rebind_unresolved | 44 | 480685 | 89811 | $0.087071 | 679.371s | yes |
| Reuters Institute | pass | fail | not_publishable | publish_readiness_failed | 51 | 561538 | 144275 | $0.119520 | 1058.086s | yes |
| Merchant Risk Council | pass | pass | awaiting_review | — | 27 | 186555 | 42797 | $0.039286 | 322.359s | no |
| Adjust | pass | pass | awaiting_review | — | 41 | 350359 | 85537 | $0.074962 | 655.202s | yes |
| Algolia | pass | pass | awaiting_review | — | 43 | 303208 | 49448 | $0.054448 | 498.704s | no |
| Bain & Company | pass | pass | awaiting_review | — | 27 | 173643 | 58064 | $0.045463 | 434.470s | no |
| Bigcommerce | pass | pass | awaiting_review | — | 31 | 280690 | 49489 | $0.051881 | 458.851s | no |
| Criteo | pass | pass | awaiting_review | — | 31 | 321432 | 76475 | $0.068508 | 700.172s | yes |
| Deloitte | pass | pass | awaiting_review | — | 32 | 304358 | 77432 | $0.066714 | 679.648s | yes |
| DHL eCommerce | fail | not evaluated | none | validation_failed | 50 | 384953 | 103577 | $0.082259 | 1007.745s | yes |
| Emplifi | pass | pass | awaiting_review | — | 26 | 265744 | 53557 | $0.052587 | 429.712s | no |
| Qualtrics | pass | pass | awaiting_review | — | 27 | 283669 | 59068 | $0.056796 | 460.781s | no |
| StackAdapt Inc | pass | pass | awaiting_review | — | 33 | 278537 | 59048 | $0.056704 | 439.779s | no |
| Robeco | pass | fail | awaiting_review | publish_readiness_failed | 24 | 343497 | 71049 | $0.069108 | 488.240s | no |
| SimilarWeb | pass | pass | awaiting_review | — | 38 | 257179 | 59352 | $0.054219 | 412.961s | no |
| Contentstack | pass | pass | awaiting_review | — | 31 | 316753 | 57269 | $0.059204 | 374.947s | no |
| Mintel | pass | pass | awaiting_review | — | 44 | 286400 | 82885 | $0.068140 | 578.719s | yes |

## Blocking outcomes

- **KPMG** — final validation stopped with `regeneration_evidence_rebind_unresolved`. Candidate grounding existed, but no final package or readiness record was produced. This is a typed pre-package failure; it is not an eligible report with `package_missing`.
- **DHL eCommerce** — final semantic validation stopped with `validation_failed` on the grounding rule after one bounded repair attempt. Candidate artifacts did not become a final package or readiness result.
- **Reuters Institute** — a lineage-bound final package was materialized; readiness blocked it as `not_publishable` with 20 unresolved factual claims and zero unsupported claims. The `publish_readiness.retained_claim_grounding` rule failed and remains blocking.
- **Robeco** — a lineage-bound final package had zero unsupported and unresolved claims, but readiness blocked it because `publish_readiness.category_consistency` found the canonical category assignment missing.

Failure-code counts were `publish_readiness_failed` (2), `regeneration_evidence_rebind_unresolved` (1), and `validation_failed` (1). These are preserved as four typed failures; all 20 reports have terminal outcomes.

## CTO evidence refresh

The strict collector regenerated [`../../../CTO_evidence/consistency_validation.json`](../../../CTO_evidence/consistency_validation.json) at exact HEAD `23fec7388553041aabcc3e1e0775abb559c6695d` (evidence run `6d9982163d8348f9b4ec19193f43b4b2`, run-manifest SHA-256 `7e6b0d298ec0df0cc6cb267f2339e8fcae897b407c642b9bf9e10c6d90c75df4`). Overall consistency status is `passed`. Exact HEAD, artifact hashes, snapshot integrity, source/editorial canary coverage, and summary consistency passed.

Canonical log content and freshness are **unavailable** in that collector bundle: this cohort retained isolated per-report usage/workflow databases and did not produce run-owned canonical application logs. The collector used an empty run-owned log directory and recorded that limitation; repository-wide logs were not substituted. Its repository-level state/ and out/ telemetry is a separate snapshot from the full-cohort metrics above.

## Reproduction command

```powershell
python scripts/quality/run_frozen_reliability_cohort.py `
  --sources-manifest docs/quality/reliability-cohort-20260927-grounding/frozen_cohort.json `
  --runs-root <fresh-isolated-runs-root> `
  --max-duration 1512
```

This is one full 20-report measurement of the frozen inputs, not a controlled causal comparison. Provider calls, token usage, costs, and durations are run observations.
