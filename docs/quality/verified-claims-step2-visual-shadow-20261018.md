# MarketLense — Verified Claims Step 2 Visual Shadow Evidence

**Date:** 2026-10-18
**Branch:** `codex/fix-retained-insight-evidence-validation`
**Step 1 comparison baseline:** `953555f`
**Frozen manifest SHA-256:** `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`
**Status:** **PARTIAL**

## Scope and decision

Step 2 adds a shadow-only visual claim-correction and independent-verification
boundary. It does not overwrite retained artifacts, promote a corrected claim,
change publication readiness, regenerate downstream artifacts, or write to
WordPress. Step 3 visual factualisation and canonical verified-claim persistence
remain unstarted.

The implementation is complete and the provider-free behavior and policy tests
pass. The frozen-cohort evaluation below deliberately made no paid model calls:
the local environment does not establish access to the required GPT-6 Luna
provider/model (the dotenv model is `gpt-5`, with no configured provider base
URL). Therefore this record does not claim source verification, corrected-claim
quality, first-pass verification, retry effectiveness, or live selection
improvement. A live GPT-6 Luna High run is still required before Step 3.

## Implemented behavior

- Each claim is bound to its existing stable candidate ID, source identity,
  canonical evidence IDs, evidence spans, and one or more verified physical PDF
  pages. The complete page is rendered through the existing PDF service at the
  request DPI; no chart/table crop is used.
- Correction and verification use separate registered prompt namespaces and
  the existing `prepare_prompt_bundle`/execution-policy path. The evaluator
  fails closed unless the resolved model is GPT-6 Luna and reasoning effort is
  `high`.
- The correction model receives the original claim only as analytical
  direction. The complete source page is authoritative. It may rewrite or
  replace the conclusion, but the model cannot supply authoritative IDs, pages,
  spans, or protected factual bindings.
- Verification is a separate operation that receives the corrected claim and
  source binding, not the original claim or correction reasoning. It checks
  material values, labels, populations, cohorts, denominators, geography,
  periods, forecast/observed status, uncertainty, and analytical overreach.
- Each claim has at most two correction attempts and two verification attempts.
  Verification diagnostics feed one bounded retry; a second failure records
  `failed_verification` and processing continues with the next claim.
- Full-page render paths and eligible image-model responses use the existing
  artifact/semantic cache inputs, including source-derived image fingerprints,
  prompt hash, model settings, claim text, and verification inputs. Pages shared
  by multiple claims are rendered once per evaluation.
- Results are versioned typed records and remain separate from authoritative
  artifacts. Only a verified result contains a final corrected claim.

## Provider-free frozen-five replay

The replay used the retained real-report PDFs and artifacts from the Step 0
frozen cohort. It did not substitute fabricated source fixtures, call a model,
write publication state, or add canonical claims.

| Report | PDF pages | Expected SHA-256 matched | Retained selected insights | Theme slots | Reference cases / variants | Visual calls |
|---|---:|---|---:|---:|---:|---:|
| Capgemini Research Institute | 82 | yes | 5 | 5 | 4 / 9 | 0 |
| Activate | 140 | yes | 7 | 7 | 4 / 11 | 0 |
| KPMG | 42 | yes | 5 | 5 | 3 / 7 | 0 |
| Reuters Institute | 47 | yes | 6 | 6 | 3 / 8 | 0 |
| Adjust | 41 | yes | 6 | 6 | 1 / 4 | 0 |
| **Total** | — | **5/5** | **29** | **29/29** | **15 / 39** | **0 correction, 0 verification** |

The retained selected identities and final editorial wording are unchanged from
the Step 1 corrected baseline: 29/29 IDs, 29/29 theme slots, evidence IDs,
physical pages, spans, and protected metric bindings remain unchanged. This is
an input-preservation result, not a claim that visual correction improved those
outputs.

The exact retained identity rosters are:

- Activate: `activate-digital-assistant-access-forecast`,
  `activate-outlook-revenue-models`, `activate-super-user-time-and-spending`,
  `activate-platform-specific-web-video`,
  `activate-news-discovery-and-direct-visits`,
  `activate-ecommerce-capability-stack`,
  `activate-podcasting-engagement-rationale`.
- Capgemini: `online-deal-searching`, `value-fairness-transparency`,
  `consumer-control-of-ai`, `human-support-remains-important`,
  `digital-assistants-engagement-recommendation`.
- KPMG: `execution-governance-value-creation`,
  `strategic-focus-capability-building`, `agentic-ai-deal-workflows`,
  `buyer-appetite-execution-approaches`, `buyer-standalone-platform-access`.
- Reuters Institute: `ai-search-platform-relationships`,
  `distinctive-content-response`, `video-platform-discovery-shift`,
  `newsroom-ai-uses-and-oversight`, `subscription-membership-priority`,
  `ai-browsers-adaptable-content`.
- Adjust: `gaming-benchmark-coverage`,
  `cross-channel-measurement-recommendation`, `ecommerce-benchmark-coverage`,
  `finance-benchmark-coverage`, `ai-marketing-applications`,
  `benchmark-methodology-context`.

No metric-spine or key-figure changes were made. The known Capgemini
`online-deal-searching` limitation remains: the retained candidate has no safe
structured metric binding, so the source prose is not promoted into a 62%
metric-spine item during this shadow stage.

## Step 0 reference-case assessment

The replay confirmed that all 15 cases have complete physical pages available
in the hash-matched local PDFs. Since provider-free mode was used, every case
has an explicit `skipped_provider_free` visual assessment, no model claim
output, and no verified or rejected model result. The table records the source
truth that must be checked in a future live run; it does not manufacture a
corrected claim.

| Case / page(s) | Source truth to compare | Provider-free result |
|---|---|---|
| ACT-001 / p.5 | `$302B`, 4.1% CAGR, scope and 2017E–2021E forecast qualifiers stay bound. | Input available; correction and verification not dispatched. |
| ACT-002 / p.15 | Preserve the 61%/34% time-versus-spend direction and cohort labels. | Input available; correction and verification not dispatched. |
| ACT-003 / p.17 | Preserve the 64%/47% time-versus-spend direction and cohort labels. | Input available; correction and verification not dispatched. |
| ACT-004 / p.53 | Keep platform, cohort, metric and population bound to the correct visual panel. | Input available; correction and verification not dispatched. |
| CAP-001 / p.11 | Preserve reported switching reasons and survey scope. | Input available; correction and verification not dispatched. |
| CAP-002 / p.11 | Do not expand N=12,000 survey percentages to the whole population. | Input available; correction and verification not dispatched. |
| CAP-003 / pp.21–22 | Keep deal-searching and non-essential-spending motives separate; reject a 49% transfer. | Input available; correction and verification not dispatched. |
| CAP-004 / p.34 | Do not attach chatbot denominator/willingness-to-pay values to another population. | Input available; correction and verification not dispatched. |
| KPM-001 / p.15 | Keep private-equity/corporate cohorts, means and forward-looking status bound. | Input available; correction and verification not dispatched. |
| KPM-002 / pp.12–13 | Preserve the qualitative capability thesis without numeric or realized-outcome upgrades. | Input available; correction and verification not dispatched. |
| KPM-003 / p.19 | Treat the carve-out increase as a 12–24 month expectation, not a realized outcome. | Input available; correction and verification not dispatched. |
| REU-001 / p.12 | Keep the search decline as a publisher forecast, not an observed result. | Input available; correction and verification not dispatched. |
| REU-002 / p.13 | Keep platform, referral measure, sign and comparison periods exact. | Input available; correction and verification not dispatched. |
| REU-003 / pp.12–13 | Keep the Google Search alternative period/geography binding exact. | Input available; correction and verification not dispatched. |
| ADJ-001 / p.19 | Keep gaming category, install/session measures, direction and 2024–2025 period bound. | Input available; correction and verification not dispatched. |

Consequently, first-pass verification rate, verified-after-retry rate, final
failure count, false accepts, false rejects, human-reference accuracy,
analytical quality, tokens, cost, latency, and cache reuse are **not
measurable** from this replay. They are not reported as zero-quality outcomes.

## Regression verification

Passed:

- `python -m pytest -q tests/test_verified_claims_visual_generator.py tests/test_verified_claims_step2_replay.py` — **10 passed**.
- `python -m pytest -q tests/test_prompt_dry_run_validation.py tests/test_llm_routing_policy.py tests/test_report_generation_execution_policy.py` — **57 passed**.
- `python -m pytest -q tests/test_artifact_insight_shortlisting.py tests/test_artifact_normalization_source_fidelity.py` — **39 passed**.
- `python -m pytest -q tests/test_artifact_generator.py tests/test_report_regeneration_generator.py` — **199 passed**.
- `python -m pytest -q tests/test_artifact_evidence_binding.py tests/test_claim_validation_source_pages.py tests/test_claim_validation_source_excerpts.py tests/test_retained_claim_grounding.py tests/test_source_identity_provenance.py` — **48 passed**.
- `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_publish_readiness_gate.py` — **124 passed**.
- `python -m pytest -q tests/test_pdf_crop_decomposition.py tests/test_pdf_text_service.py tests/test_pdf_contents_service.py tests/test_openai_chat_service.py` — **35 passed**.
- `python scripts/quality/replay_verified_claims_step2.py --provider-free` — **success; 15 cases / 39 variants, 5/5 PDFs hash-matched, 29 retained insights**.
- Scoped Ruff checks for the new contracts, generator, replay, and tests — **passed**.

The focused regressions cover complete-page rendering, multi-page bindings,
stable/source binding preservation, independent verifier input isolation,
malformed outputs, explicit unresolved correction retry, one-retry repair,
two consecutive verification failures with continuation, page/render skips,
cache-enabled image requests, and GPT-6 Luna High policy enforcement.

## Remaining limitations and recommendation

- No actual GPT-6 Luna High visual call was made, so source truth has not been
  independently compared with corrected model claims.
- The provider-free replay starts from retained post-selection artifacts; it
  cannot measure fresh candidate recall or live visual correction quality.
- Shadow results are not persisted as canonical claims and are not sent through
  downstream regeneration or publication.
- Step 0's 15 cases and 39 variants are available locally and hash-verified;
  they must be used in a live, budgeted evaluation before any promotion policy
  or Step 3 work.

**Verdict: PARTIAL.** Step 2's deterministic boundary, contracts, prompts,
retry behavior, cache wiring, and fail-closed isolation are implemented and
tested. The required live visual evaluation and independent human/reference
comparison remain outstanding. Step 3 is not justified by this evidence.
