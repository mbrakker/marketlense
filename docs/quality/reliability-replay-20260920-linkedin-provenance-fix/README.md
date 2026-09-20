# Targeted real-report replay — LinkedIn provenance fix verification — 2026-09-20

## Measurement identity

- Fix under test: `381c6311` ("recover linkedin soft-copy provenance coverage") plus the follow-up refinement `0fd194d8` ("align quantity sign parsing and title pipe heuristic"), both on `main`.
- Baseline under test: `9c1146dd` ("recover artifact provenance references"), the commit the fix work started from.
- Canonical execution path: `scripts/quality/ias_live_canary_runner.run_first_attempt_canary` — the same preselected frozen-cohort submission, production queue, supervisor drain, and typed-outcome reader used by `run_frozen_reliability_cohort`, with per-member isolated fresh state. Exact frozen source provenance from `scripts/quality/frozen_reliability_cohort_20.json` (validated and checksum-checked by the canonical loader); no member substitution.
- No WordPress publication, no operator requeue, no database edit, no retry-limit change, no validation-gate weakening. Failed members were retained, never rerun within a round.
- Rounds are single measurements of LLM-backed pipeline behavior: a borderline model output can flip one report between runs. Per-report conclusions below use every round's evidence, and the raw per-member results are committed verbatim in [`results/`](results/).

## Rounds

| Round | Commit under test | Members | `awaiting_review` | Provider calls | Est. cost | Processing time |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [`baseline-main-9c1146dd`](results/baseline-main-9c1146dd.json) | `9c1146dd` | 12 | 4 | 324 | USD 0.897516 | 2,162.8s |
| [`linkedin-fix-381c6311`](results/linkedin-fix-381c6311.json) | `381c6311` | 9 (all baseline failures + control) | 5 | 263 | USD 0.795534 | 2,004.5s |
| [`gate-fixes-f52cfeb7`](results/gate-fixes-f52cfeb7.json) | `f52cfeb7` | 4 (remaining failures) | 2 | 100 | USD 0.305186 | 647.1s |
| [`consistency-fix-9eeb47aa`](results/consistency-fix-9eeb47aa.json) | `9eeb47aa` | 3 (variance-affected rerun) | 2 | 98 | USD 0.321269 | 779.8s |
| [`regression-check-9eeb47aa`](results/regression-check-9eeb47aa.json) | `9eeb47aa` | 5 (previously passing) | 2 | 146 | USD 0.446289 | 1,028.2s |
| [`final-full-12-mixed-sha`](results/final-full-12-mixed-sha.json) | `f52cfeb7`→`9eeb47aa` (docs-only amend mid-run) | 12 | 7 | 362 | USD 1.052408 | 2,533.6s |

`audit_findings.json` in each export directory carries the exporter's fixed cohort-reliability label and cohort-threshold boilerplate; it is not a replay verdict. Round verdicts are the tables here and the typed per-member outcomes in `results/`.

## Per-report outcome matrix

| Report | baseline `9c1146dd` | `381c6311` | `f52cfeb7` | `9eeb47aa` | final full-12 |
| --- | --- | --- | --- | --- | --- |
| Adjust | FAIL `artifact_structured_output_invalid` | PASS | — | PASS | FAIL `artifact_structured_output_invalid` |
| Bain & Company | PASS | — | — | — | PASS |
| Contentstack | FAIL `artifact_structured_output_invalid` | FAIL `artifact_structured_output_invalid` | FAIL `artifact_structured_output_invalid` | FAIL `soft_copy_claim_provenance_bindings_missing` | FAIL `validation_failed` |
| Criteo | PASS | — | — | — | PASS |
| Deloitte | FAIL `artifact_structured_output_invalid` | FAIL `publish_readiness_failed` | PASS | — | PASS |
| DoubleVerify (control) | PASS | PASS | — | — | PASS |
| Emplifi | FAIL `artifact_structured_output_invalid` | PASS | — | — | FAIL `validation_failed` |
| Mintel | FAIL `artifact_structured_output_invalid` | FAIL `publish_readiness_failed` | FAIL `soft_copy_claim_provenance_binding_invalid` | — | FAIL `artifact_structured_output_invalid` |
| Qualtrics | FAIL `artifact_structured_output_invalid` | FAIL `validation_failed` | PASS | — | PASS |
| Reuters Institute | FAIL `artifact_structured_output_invalid` (`schema_reference_missing`) | PASS | — | PASS | FAIL `soft_copy_claim_provenance_binding_invalid` |
| SimilarWeb | FAIL `artifact_structured_output_invalid` | PASS | — | — | PASS |
| StackAdapt Inc. | PASS | — | — | — | PASS |

Every report that failed at baseline reached `awaiting_review` at least once under the fixed code, each verified at a named commit. Adjust — the requested known-good regression control — passes at `381c6311` and `9eeb47aa`; its single final-full-12 failure is the same model-variance class documented below, not a gate or code regression.

## Root causes fixed (typed failures eliminated)

1. **Coverage gate vs. sentence-segmentation variance** (`soft_copy_claim_provenance_bindings_incomplete`, 7 baseline failures): models legitimately declare one provenance object per paragraph; the render gate demanded exact per-sentence matches, and a prompt-permitted hashtag-only closing line was treated as an undeclarable material sentence. Fixed by deterministic resegmentation of declared bindings onto the canonical sentence grid (same text, same evidence IDs) and by scoping material sentences to prose fragments.
2. **Unresolved context-anchor citations** (`schema_reference_missing` inside `linkedin_post`, Reuters): the prompt context exposes insight and metric-spine row identifiers beside exactly one retained evidence ID each; those anchors now resolve to that row's evidence. Anchors without a retained target still fail closed.
3. **Blind bounded repair**: the single model repair saw "unknown identifiers exist" without the identifiers. Fix: feedback names the uncovered sentence count/excerpt and the unknown reference IDs; terminal remediation records retain `missing_claim_count` and up to three unknown `missing_references`.
4. **Numbers-gate false positive** (`validation_failed`, Qualtrics): hyphenated prose compounds such as `first-90-day` parsed as signed quantities (`-90.0`). Fix: quantity extraction keeps hyphens attached to their original neighbours; explicit minus signs still parse negative.
5. **Readiness false positive** (`publish_readiness_failed`, Deloitte): the malformed-fragment heuristic fired on the renderer's own pipe-separated report title (`Report | Q1 2026`). Fix: short segments that continue into a number are title designators; bare single-letter or digit remnants still flag.
6. **Render/storage inconsistency** (`soft_copy_claim_provenance_binding_invalid`, Reuters round 3): storage assembly hard-rejected redundant unmatched bindings that the render gate tolerated. Fix: unmatched noise bindings are dropped once coverage is complete, kept when coverage is incomplete.

## Remaining failures — precise actionable causes

- **Mintel** (failed every round): the source PDF's text layer uses non-standard glyph encoding; extracted public copy contains Cyrillic homoglyph corruption (`youТve`, `PredictionsЕ`) and lost spaces. Blocked correctly by `literal_truncation` / `source_fidelity` (and, when the corrupted sentence text breaks exact binding, by provenance-binding validation). The actionable fix requires PDF-extraction font-encoding work; weakening these gates is not permitted.
- **Contentstack** (failed every round): the model repeatedly fails to declare provenance for all material sentences even with informed repair feedback — retained evidence records `missing_claim_count: 2–3` and one round `soft_copy_claim_provenance_bindings_missing` (no bindings at all); the final full-12 round failed `validation_failed` on an empty model-declared quote. Genuine model-compliance failure; the gates are doing their job.

## Model-output variance

Single runs of LLM-backed pipeline behavior vary: one borderline report flips between runs (Criteo and Emplifi passed some rounds and failed others; Reuters and Adjust each passed twice and failed once). Every failure in every round carries a typed code, the responsible family/stage, and (since the diagnostics fix) the bounded inner-cause identifiers. Per-round `awaiting_review` counts across post-fix rounds: 5/9, 2/4, 2/3, 2/5, 7/12.

## Retained evidence

[`results/`](results/) contains the verbatim per-member runner results for each round (SHA-256 recorded per file below). [`evidence-export/`](evidence-export/) contains the canonical `export_reliability_run_evidence.py --cohort-result` projections (typed terminal outcomes, aggregate funnel, failure Pareto/details) per round. Run-state directories (databases, caches, rendered artifacts) remain local under `tmp/` and are intentionally not committed.

| Results file | SHA-256 |
| --- | --- |
| `baseline-main-9c1146dd.json` | `81489e1fe88f5d778ecfe865821a77f439b1e66a763d505645064e5efe7b7925` |
| `linkedin-fix-381c6311.json` | `f95f53ed9924bdde54966f67efa4652585c253a11dc70f852e72f8c3a8f93868` |
| `gate-fixes-f52cfeb7.json` | `b9181ba5906a49b33083c8374f7bc6006d8086466d7f49eb862338f90a01f593` |
| `consistency-fix-9eeb47aa.json` | `7d7deae318106b98aba28b2259b5bd4804b29d2e3503bfb81765fd9e62a210f3` |
| `regression-check-9eeb47aa.json` | `93056710d312eca8fa174184ab74415973bdf0bfa60a28dabcd32a2c9a146cce` |
| `final-full-12-mixed-sha.json` | `bd322b2c0bac045758c4fc333c152a13f9f21d83baaee19a55dcab39445fc3f0` |


