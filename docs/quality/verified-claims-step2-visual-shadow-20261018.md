# MarketLense — Verified Claims Step 2 Visual Shadow Evidence

**Date:** 2026-10-18
**Branch:** `codex/fix-retained-insight-evidence-validation`
**Step 1 comparison baseline:** `953555f`
**Frozen manifest SHA-256:** `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`
**Status:** **PARTIAL**

## Scope and decision

Step 2 remains shadow-only. It does not overwrite retained artifacts, promote a
corrected claim, change publication readiness, regenerate downstream artifacts,
or write to WordPress. Step 3 visual factualisation and canonical
verified-claim persistence remain unstarted.

The live replay used dotenv-backed `gpt-6-luna` with High reasoning, the exact
five frozen PDFs, and retained Step 1 artifacts. It evaluated all 39 reference
variants and represented all 29 retained shortlist insights. The replay is
evidence about Step 2 correction, verification, and provenance handling; it is
not fresh candidate-selection evidence.

## Implemented behavior

- The existing PDF service hash path verifies the actual source PDF against the
  expected `pdf-sha256` identity before a visual model call. Missing or
  conflicting hashes fail closed.
- Existing evidence binding is resolved before rendering. DocMap section IDs
  and pages are navigation context, not factual authority. A retained DocMap
  binding is replaced only when exactly one proposition-compatible direct
  finding exists and that finding is already `supported` by the existing
  evidence-fidelity artifact. Otherwise the claim is held without a model call.
- Conflicting physical pages, evidence-span pages, source identities, or
  top-level/span evidence IDs are skipped without blocking later claims. Empty
  render paths fail closed.
- Correction receives the original claim as analytical direction only. The
  complete supplied page is factual authority. A relevant source-supported
  metric replacement is allowed; unrelated topic, population, period, metric,
  or page substitutions are unresolved.
- Verification receives the original direction and final corrected claim. It
  evaluates the final claim for values, labels, metric relationships, cohorts,
  populations, denominators, geography, period, forecast/observed status,
  uncertainty, and defensible qualitative meaning. A verified qualitative
  result must explain a bounded source-grounded relationship and implication;
  generic “supported” notes fail closed.
- Correction and verification remain independent and bounded at two attempts
  each. Non-retryable provider, budget, and configuration failures stop that
  claim immediately while preserving typed diagnostics and allowing later
  claims to continue. Malformed or incomplete responses remain bounded and
  fail closed.
- Stable IDs, original wording, authoritative evidence IDs, physical pages,
  evidence spans, protected metric bindings, and downstream schemas remain
  unchanged inputs. Only a verified shadow result has a final corrected claim.

## Provider-free frozen-five replay

Command:

`python scripts/quality/replay_verified_claims_step2.py --provider-free --output out/verified_claims_step2_provider_free_current_20261018/report.json`

The replay used the retained real-report PDFs and artifacts without a model,
fabricated fixtures, publication state, or canonical-claim writes.

| Report | PDF pages | SHA-256 | Retained claims | Theme slots | Reference variants |
|---|---:|---|---:|---:|---:|
| Capgemini Research Institute | 82 | matched | 5 | 5 | 9 |
| Activate | 140 | matched | 7 | 7 | 11 |
| KPMG | 42 | matched | 5 | 5 | 7 |
| Reuters Institute | 47 | matched | 6 | 6 | 8 |
| Adjust | 41 | matched | 6 | 6 | 4 |
| **Total** | — | **5/5** | **29** | **29/29** | **39** |

The retained identities and public wording were not changed. This confirms
input preservation and theme coverage, not fresh-selection quality.

## Upstream source-binding correction

The old Step 2 replay treated DocMap section IDs as sufficient source bindings.
The corrected boundary distinguishes them from canonical findings. The exact
eight previously unresolved real claims were inspected as follows:

| Report / stable ID | Previous binding | Direct-finding check | Corrected result |
|---|---|---|---|
| Capgemini `consumer-control-of-ai` | `ai-consumers-trusted-guide`, p.30 | Matching finding exists at pp.35–36, but its fidelity result is `unsupported` because it has no source reference. | Fail closed; DocMap navigation only. |
| Capgemini `digital-assistants-engagement-recommendation` | `recommendations`, p.46 | Matching finding exists at pp.6,46, but its fidelity result is `unsupported` because it has no source reference. | Fail closed; DocMap navigation only. |
| Activate `activate-digital-assistant-access-forecast` | `s4`, pp.18,26,30 | No proposition-compatible direct finding was retained for `s4`. | Fail closed; DocMap navigation only. |
| KPMG `buyer-standalone-platform-access` | `portfolio-simplification-as-a-value-creation-strategy`, p.18 | The same-section carve-out finding is a different proposition and is not fidelity-supported. | Fail closed; no promotion. |
| Reuters `ai-search-platform-relationships` | `answer-engines-and-traffic`, p.10 | The direct search-traffic finding is a different proposition and is not fidelity-supported. | Fail closed; no promotion. |
| Reuters `distinctive-content-response` | `content-strategies-distinctiveness`, p.15 | Matching finding exists at pp.4,16, but is not fidelity-supported. | Fail closed; DocMap navigation only. |
| Reuters `newsroom-ai-uses-and-oversight` | `latest-tales-ai-newsroom`, p.30 | Matching finding exists at p.30, but is not fidelity-supported. | Fail closed; DocMap navigation only. |
| Reuters `subscription-membership-priority` | `business-models-and-innovation`, p.36 | Matching finding exists at p.36, but is not fidelity-supported. | Fail closed; DocMap navigation only. |

This is a general binding correction, not an eight-report patch. The existing
fidelity result, proposition matching, source identity, and physical-page
validators are reused. No unsupported finding or nearby section was promoted.
The two Capgemini findings that are already canonical and supported remain
eligible; the `online-deal-searching` correction still preserves the source
62% value and 64% comparison without speculative metric-spine enrichment.

## Corrected reference benchmark methodology

The benchmark assesses the final corrected claim, not whether the original
analytical direction was already factually valid. A corrected claim may repair
or replace a metric when it remains relevant to the source topic, question,
population, and period. It may not drift to a different source finding merely
because that finding is visible on the supplied page.

`ADJ-001-unsupported-metric` is accepted only after direct inspection of PDF
page 19: the original churn/conversion claim is unsupported, while the
corrected install/session statement is visibly source-supported and relevant
to the same gaming-performance question. `ACT-004-wrong-page` remains
unresolved because physical page 15 is a U.S. video time/spend cohort page, not
the retained global platform creator/view-share visual. The model cannot fall
back to page 53.

## Final GPT-6 Luna High replay

Command:

`python scripts/quality/replay_verified_claims_step2.py --live --output out/verified_claims_step2_live_step2_rootfix_20261018/report.json`

The run used full original pages at 216 DPI, hash-matched source identity,
shadow mode, and an isolated cache/output root. Terminal outcome counts are
mutually exclusive: `verified_total` is exactly
`verified_first_pass + verified_after_retry`.

| Evaluation set | Verified first pass | Verified after retry | Verified total | Unresolved | Failed | Skipped | Input |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reference variants | 38 | 0 | 38 | 1 | 0 | 0 | 39 |
| Real retained shortlist | 2 | 0 | 2 | 0 | 0 | 27 | 29 |
| **All claims** | **40** | **0** | **40** | **1** | **0** | **27** | **68** |

The 27 real skips are not hidden failures or retry successes: each had a
DocMap-only or otherwise non-canonical binding and therefore made no provider
call. This corrects the prior report's inconsistent “27 verified / 8
unresolved” wording. The eight old unresolved IDs are explicitly listed
above; under the corrected terminal taxonomy they are fail-closed skips.

Measured run data:

- Model: `gpt-6-luna`, High reasoning.
- 82 provider calls; 668,010 input tokens; 38,874 output tokens.
- Estimated cost: `$0.086243`; wall time: `569.721` seconds.
- 19 full-page renders; cache enabled; fresh-run cache reuse was not counted
  as a quality result.
- Source PDFs: 5/5 expected hashes matched.
- Reference comparison: 39/39 expected outcomes matched, with 0 false accepts
  and 0 false rejects. The one expected-unsupported variant was
  `ACT-004-wrong-page` and remained unresolved.
- No provider failure, canonical-claim mutation, publication write, or
  WordPress write occurred.

## Real shortlist before/after ledger

The live JSON preserves each original claim, final corrected claim when a
model call occurred, terminal outcome, source identity, physical pages,
evidence IDs, spans, and bounded attempts. `before → after` below is the
binding identity/page transition observed in that JSON.

### Capgemini Research Institute

| Stable ID | Outcome | Binding before → after | Review |
|---|---|---|---|
| `value-fairness-transparency` | verified | `value-fairness-quality` pp.4,8,9 → same, `findings` | Final wording corrects “consistent quality” to “consistent policies”; source notes identify the value relationship and fairness implications. |
| `online-deal-searching` | verified | `careful-spending-and-indulgence` pp.5,9 → same, `findings` | Final claim preserves 62% in Oct. 2025, 64% in Nov. 2024, populations, and sample sizes. |
| `consumer-control-of-ai` | skipped | `ai-consumers-trusted-guide` p.30 → same, `doc_map` | Chapter-divider/navigation binding; unsupported direct finding not promoted. |
| `human-support-remains-important` | skipped | `reliable-tech-loyalty` p.40 → same, `doc_map` | Direct finding is not fidelity-supported; no visual evaluation. |
| `digital-assistants-engagement-recommendation` | skipped | `recommendations` p.46 → same, `doc_map` | Section-title/navigation binding; unsupported direct finding not promoted. |

### Activate

| Stable ID | Outcome | Binding before → after | Review |
|---|---|---|---|
| `activate-outlook-revenue-models` | skipped | `s1` pp.3–6 → same, `doc_map` | Direct finding `f1` is not fidelity-supported. |
| `activate-super-user-time-and-spending` | skipped | `s3` pp.12–16 → same, `doc_map` | Direct finding `f2` is not fidelity-supported. |
| `activate-digital-assistant-access-forecast` | skipped | `s4` pp.18,26,30 → same, `doc_map` | No proposition-compatible direct finding. |
| `activate-platform-specific-web-video` | skipped | `s6` pp.49,53–59 → same, `doc_map` | No fidelity-approved direct finding for this retained binding. |
| `activate-news-discovery-and-direct-visits` | skipped | `s9` pp.93,96,97,99,100,105,108 → same, `doc_map` | Direct finding `f4` is not fidelity-supported. |
| `activate-ecommerce-capability-stack` | skipped | `s10` pp.111,115,117–119 → same, `doc_map` | No fidelity-approved direct finding for this retained binding. |
| `activate-podcasting-engagement-rationale` | skipped | `s11` pp.124,136 → same, `doc_map` | Direct finding `f5` is not fidelity-supported. |

### KPMG

| Stable ID | Outcome | Binding before → after | Review |
|---|---|---|---|
| `buyer-standalone-platform-access` | skipped | `portfolio-simplification-as-a-value-creation-strategy` p.18 → same, `doc_map` | Same-section carve-out material is a different proposition and not fidelity-supported. |
| `execution-governance-value-creation` | skipped | `execution-discipline-as-a-decisive-source-of-advantage` pp.30,31,33 → same, `doc_map` | Direct finding is not fidelity-supported. |
| `agentic-ai-deal-workflows` | skipped | `ai-driven-transformation-of-deal-execution` pp.23–28 → same, `doc_map` | Direct finding is not fidelity-supported. |
| `buyer-appetite-execution-approaches` | skipped | `diverging-risk-appetites-between-buyers` pp.14–17 → same, `doc_map` | Direct finding is not fidelity-supported. |
| `strategic-focus-capability-building` | skipped | `strategic-focus-in-a-fragmented-world` pp.10–13 → same, `doc_map` | No fidelity-approved direct finding for this retained binding. |

### Reuters Institute

| Stable ID | Outcome | Binding before → after | Review |
|---|---|---|---|
| `ai-search-platform-relationships` | skipped | `answer-engines-and-traffic` p.10 → same, `doc_map` | Direct search-traffic finding is a different proposition and not fidelity-supported. |
| `distinctive-content-response` | skipped | `content-strategies-distinctiveness` p.15 → same, `doc_map` | Direct finding is not fidelity-supported. |
| `video-platform-discovery-shift` | skipped | `social-media-mid-life-crisis-video` p.18 → same, `doc_map` | Direct finding is not fidelity-supported. |
| `newsroom-ai-uses-and-oversight` | skipped | `latest-tales-ai-newsroom` p.30 → same, `doc_map` | Direct finding is not fidelity-supported. |
| `subscription-membership-priority` | skipped | `business-models-and-innovation` p.36 → same, `doc_map` | Direct finding is not fidelity-supported. |
| `ai-browsers-adaptable-content` | skipped | `whats-next-in-technology` p.39 → same, `doc_map` | No fidelity-approved direct finding for this retained binding. |

### Adjust

| Stable ID | Outcome | Binding before → after | Review |
|---|---|---|---|
| `cross-channel-measurement-recommendation` | skipped | `multiplatform-strategy` p.11 → same, `doc_map` | No canonical direct finding binding. |
| `gaming-benchmark-coverage` | skipped | `gaming-finding-keeping-users` pp.17–21,23 → same, `doc_map` | No canonical direct finding binding. |
| `ecommerce-benchmark-coverage` | skipped | `ecommerce-finding-keeping-users` pp.27–30 → same, `doc_map` | No canonical direct finding binding. |
| `finance-benchmark-coverage` | skipped | `finance-finding-keeping-users` pp.34–38 → same, `doc_map` | No canonical direct finding binding. |
| `ai-marketing-applications` | skipped | `ai-infrastructure` p.9 → same, `doc_map` | No canonical direct finding binding. |
| `benchmark-methodology-context` | skipped | `takeaways-methodology` p.13 → same, `doc_map` | No canonical direct finding binding. |

## Baseline comparison and quality review

The retained Step 1 roster remains 29/29 identities, 29/29 theme slots, and
unchanged public wording. Compared with the previous Step 2 replay, the
material change is provenance handling: claims formerly evaluated through
DocMap-only pages are now held before visual evaluation. This is a correctness
improvement in evidence authority, not a demonstrated improvement in editorial
selection quality.

The two evaluated Capgemini claims retained protected factual content. The
`online-deal-searching` result preserved source-supported numeric information;
the metric spine still has no safe structured binding, so no enrichment was
added. The 39 reference variants had no factual false accepts or false rejects.

The principal remaining quality limitation is upstream retained-artifact
completeness: 27 of 29 shortlist rows lack a fidelity-approved direct finding
binding in this frozen corpus. Step 2 correctly refuses to invent a source
location or treat a section heading as proof, but this replay cannot establish
fresh Step 1 recall or repair those artifacts.

## Regression verification

Passed in this worktree:

- `python -m pytest -q tests/test_artifact_evidence_binding.py tests/test_artifact_normalization_source_fidelity.py tests/test_artifact_insight_shortlisting.py` — **45 passed**.
- `python -m pytest -q tests/test_verified_claims_visual_generator.py tests/test_verified_claims_step2_replay.py` — **22 passed**.
- `python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py` — **78 passed**.
- `python -m compileall -q src/generators/artifact_normalization.py src/generators/verified_claims_visual_generator.py scripts/quality/replay_verified_claims_step2.py` — **passed**.
- `python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3` — **passed**; the 48-token fixture delta remained within the existing allowance.
- `python scripts/ci/run_type_check.py` — **pre-existing failure**: seven unbaselined mypy errors at unchanged lines in `artifact_normalization.py` and `verified_claims_visual_generator.py`; the errors are present in the branch parent and were not introduced by this Step 2 diff. No baseline was changed.
- Provider-free frozen-five replay — **passed**; 15 cases, 39 variants, 5/5 PDF hashes, 29 retained claims, and 29/29 theme slots.

The focused regressions cover DocMap-only rejection, direct-finding proposition
matching, unsupported-finding abstention, source-page preservation, malformed
responses, substantive qualitative notes, typed non-retryable failures,
continuation after a failed claim, bounded retries, empty images, conflicting
bindings, hash mismatch, stable IDs, protected fields, and cache behavior.

## Remaining limitations and Step 3 verdict

- This is a retained-artifact replay, not fresh Step 1 generation. It does not
  prove candidate recall, selection diversity, or repeated-run stability.
- Twenty-seven real shortlist entries remain unavailable for visual evaluation
  because their current binding is DocMap-only or lacks a fidelity-approved
  direct finding. The eight previously unresolved claims remain explicit,
  justified fail-closed outcomes rather than unsupported promotions.
- Capgemini online-deal numeric content is visually supported but still lacks a
  safe structured Step 1 metric binding; speculative enrichment remains
  excluded.
- Shadow results remain non-authoritative and are not passed to regeneration or
  publication readiness.

**Verdict: PARTIAL.** Step 2 correction, verification, source identity checks,
provenance handling, typed errors, retry bounds, and reference-benchmark
methodology are implemented and regression-tested. Step 3 cannot safely begin
because the frozen retained artifacts do not provide canonical direct source
bindings for most shortlisted claims, and no fresh selection evidence exists.
