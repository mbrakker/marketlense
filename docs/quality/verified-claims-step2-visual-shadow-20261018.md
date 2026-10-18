# MarketLense — Verified Claims Step 2 Visual Shadow Evidence

**Date:** 2026-10-18

**Branch:** `codex/fix-retained-insight-evidence-validation`

**Step 1 comparison baseline:** `953555f`

**Frozen manifest SHA-256:** `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`
**Status:** **PARTIAL**

## Scope and decision

Step 2 remains a shadow-only visual correction and independent verification
boundary. It does not overwrite retained artifacts, promote a corrected claim,
change publication readiness, regenerate downstream artifacts, or write to
WordPress. Step 3 visual factualisation and canonical verified-claim
persistence remain unstarted.

The dotenv-backed configuration resolved `gpt-6-luna` with High reasoning and
the required API credential. The final live replay used the exact frozen
five-report PDFs and retained Step 1 artifacts, with no publication or
canonical-artifact writes. It evaluated both the 39 reference variants and all
29 real retained shortlist insights. This is evidence about Step 2 correction
and verification, not fresh candidate selection effectiveness or human editorial
acceptance.

## Implemented behavior

- The existing PDF file-service hash path verifies the actual source PDF against
  the `pdf-sha256` identity before any visual model call. Missing or conflicting
  hashes fail closed.
- Existing binding structures are checked before rendering. Conflicting physical
  pages, evidence-span pages, source identities, or top-level/span evidence IDs
  are skipped without blocking later claims. Empty render paths fail closed.
- Correction receives the original claim as analytical direction only. The
  complete supplied page is factual authority. A relevant source-supported
  metric replacement is allowed; unrelated topic, population, period, metric,
  or page substitutions are unresolved. The wrong-page example explicitly
  rejects replacing a platform creator/view-share comparison with a user
  time/spend cohort finding.
- Verification receives both the original analytical direction and final
  corrected claim. It evaluates the final claim for source truth, while using
  the original only to reject unrelated drift. It checks values, labels,
  metric relationships, cohorts, populations, denominators, geography, period,
  forecast/observed status, uncertainty, and defensible qualitative meaning.
- Verification requires substantive source-grounded notes for a verified result;
  malformed, incomplete, contradictory, or generic responses fail closed.
- Correction and verification remain independent and bounded at two attempts
  each. Typed provider, budget, timeout, retryability, and severity details are
  retained in attempt diagnostics instead of being replaced by a generic error.
- Stable IDs, original wording, evidence IDs, physical pages, evidence spans,
  protected metric bindings, and downstream schemas remain authoritative inputs.
  Only a verified shadow result has a final corrected claim.

## Provider-free frozen-five replay

The provider-free replay used the retained real-report PDFs and artifacts from
the Step 0 frozen cohort. It did not substitute fabricated fixtures, call a
model, write publication state, or add canonical claims.

| Report | PDF pages | SHA-256 | Retained claims | Theme slots | Reference variants | Real claims |
|---|---:|---|---:|---:|---:|---:|
| Capgemini Research Institute | 82 | matched | 5 | 5 | 9 | 5 |
| Activate | 140 | matched | 7 | 7 | 11 | 7 |
| KPMG | 42 | matched | 5 | 5 | 7 | 5 |
| Reuters Institute | 47 | matched | 6 | 6 | 8 | 6 |
| Adjust | 41 | matched | 6 | 6 | 4 | 6 |
| **Total** | — | **5/5** | **29** | **29/29** | **39** | **29** |

The selected identities and final editorial wording remain unchanged from the
Step 1 retained baseline. This is input preservation, not evidence of improved
fresh selection. The replay report confirms all 29 real claims were assembled
from retained artifacts and no unavailable-artifact substitution occurred.

The Capgemini `online-deal-searching` correction is a numeric-content
regression check: the final visual result retains the source-supported 62%
October 2025 value and its comparison context. The retained Step 1 metric
spine still has no safe structured binding for this item, so no speculative
metric-spine enrichment was made.

## Corrected reference benchmark methodology

The benchmark assesses the final corrected claim, not whether the original
analytical direction was already factually valid. A corrected claim may repair
or replace a metric when it remains relevant to the same source topic, question,
population and period. It may not drift to a different source finding merely
because that finding is visible on the supplied page.

The `ADJ-001-unsupported-metric` fixture was corrected after direct inspection
of physical PDF page 19. The original churn/conversion claim is unsupported,
but that page visibly binds strategy, casino and slots to install/session
measures. The corrected install/session statement is source-supported and
commercially relevant to the same gaming-performance question, so
`corrected_statement_assessment=supported` and `promotion=accept_corrected` are
the correct classifications. This is not an automatic acceptance of the
original claim.

The `ACT-004-wrong-page` fixture remains unresolved: the supplied physical page
15 is a U.S. video time/spend cohort page, not the retained global Q2 2017
platform creator/view-share visual. The model must not silently fall back to
page 53 or promote the unrelated cohort finding.

## Final GPT-6 Luna High replay

Command:

`python scripts/quality/replay_verified_claims_step2.py --live --output out/verified_claims_step2_live_final_20261018_r3/report.json`

The run used full original PDF pages at 216 DPI, hash-matched source identity,
shadow mode, and an isolated fresh cache/output root.

| Report | Reference variants | Ref. verified | Ref. unresolved | Real shortlist | Real verified | Real unresolved |
|---|---:|---:|---:|---:|---:|---:|
| Capgemini Research Institute | 9 | 9 | 0 | 5 | 3 | 2 |
| Activate | 11 | 10 | 1 | 7 | 6 | 1 |
| KPMG | 7 | 7 | 0 | 5 | 4 | 1 |
| Reuters Institute | 8 | 8 | 0 | 6 | 2 | 4 |
| Adjust | 4 | 4 | 0 | 6 | 6 | 0 |
| **Total** | **39** | **38** | **1** | **29** | **21 first-pass + 6 retry = 27** | **8** |

Measured run data:

- Model: `gpt-6-luna`, High reasoning.
- 142 provider calls; 2,158,300 input tokens; 86,202 output tokens.
- Estimated cost: `$0.258931`; wall time: `1313.441` seconds.
- 90 distinct full-page renders; cache enabled; fresh-run cache reuse was not
  counted as a quality result.
- 68 claims evaluated in one replay: 39 reference variants plus 29 real
  shortlist claims.
- Reference comparison: 39/39 expected outcomes matched, 0 false accepts,
  0 false rejects. The one expected-unsupported variant was
  `ACT-004-wrong-page` and remained unresolved.
- No provider failures, skipped claims, publication writes, or canonical-claim
  writes occurred in the final pass.

## Real shortlist result ledger

The live JSON at the command output path preserves each original claim,
corrected claim, outcome, source identity, physical pages, evidence IDs, spans,
and all bounded attempts. The compact ledger below records the same identity
and source binding plus an independent editorial/factual review.

### Capgemini Research Institute

| Stable ID | Outcome | Pages / evidence | Final corrected claim and review |
|---|---|---|---|
| `value-fairness-transparency` | verified | 4,8,9 / `value-fairness-quality` | Value includes transparency, ethical practices, quality and fairness; page 4 retains 74%/71% switching reasons. Source-grounded and commercially useful. |
| `online-deal-searching` | verified | 5,9 / `careful-spending-and-indulgence` | October 2025 deal searching is 62%, compared with 64% in November 2024 and other charted periods. Numeric context retained; metric-spine binding limitation remains. |
| `consumer-control-of-ai` | unresolved | 30 / `ai-consumers-trusted-guide` | Page is a chapter divider and does not support the retained consumer-control proposition. Correct abstention. |
| `human-support-remains-important` | verified | 40 / `reliable-tech-loyalty` | Reliable technology is framed as a potential loyalty driver with boundaries. Factually cautious but analytically generic; not promoted beyond shadow output. |
| `digital-assistants-engagement-recommendation` | unresolved | 46 / `recommendations` | Section-title page does not support the retained recommendation. Correct abstention. |

### Activate

| Stable ID | Outcome | Pages / evidence | Final corrected claim and review |
|---|---|---|---|
| `activate-outlook-revenue-models` | verified after retry | 3–6 / `s1` | 2017E–2021E Internet/media revenue rises from $1.7T to $2.0T; access, ads and paid content are bound to $128B/$108B/$66B growth. Specific and commercially useful. |
| `activate-super-user-time-and-spending` | verified after retry | 12–16 / `s3` | U.S. 2017 top video-attention quartile is 61% of time and 34% of spend; all other users are 39%/66%. Cohort and denominator preserved. |
| `activate-digital-assistant-access-forecast` | unresolved | 18,26,30 / `s4` | Supplied pages do not support the digital-assistant access-cost forecast. Correct abstention. |
| `activate-platform-specific-web-video` | verified | 49,53–59 / `s6` | Global Q2 2017 top-creator split is YouTube 83%/17% and Facebook 52%/48%, with the 50M+ and view-share qualifiers. Source-specific and useful. |
| `activate-news-discovery-and-direct-visits` | verified after retry | 93,96,97,99,100,105,108 / `s9` | U.S. 2017 discovery options differed across Facebook Instant Articles/Live, Google AMP and Apple Featured Subscriptions. Supported, though more descriptive than analytical. |
| `activate-ecommerce-capability-stack` | verified | 111,115,117–119 / `s10` | Marketplaces account for 84% of $1.2T 2016 GMV versus 16% direct sales, with transaction/fulfillment implications. Specific and commercially useful. |
| `activate-podcasting-engagement-rationale` | verified | 124,136 / `s11` | U.S. podcast ad revenue forecasts $237M to $642M and listening 24% to 39%; radio comparison retained. Forecast status preserved. |

### KPMG

| Stable ID | Outcome | Pages / evidence | Final corrected claim and review |
|---|---|---|---|
| `buyer-standalone-platform-access` | unresolved | 18 / `portfolio-simplification-as-a-value-creation-strategy` | Section-title page has no substantive evidence for the retained buyer-platform claim. Correct abstention. |
| `execution-governance-value-creation` | verified | 30,31,33 / `execution-discipline-as-a-decisive-source-of-advantage` | Talent continuity, decision rights, integrated teams and tracking support execution; 32% talent-retention context is bound. Useful qualitative interpretation. |
| `agentic-ai-deal-workflows` | verified | 23–28 / `ai-driven-transformation-of-deal-execution` | Agentic AI executes multi-step M&A workflows while humans review exceptions and decide. Source-supported and commercially meaningful. |
| `buyer-appetite-execution-approaches` | verified | 14–17 / `diverging-risk-appetites-between-buyers` | PE versus corporate appetite and carve-out/minority-to-majority percentages are preserved. Specific and decision-relevant. |
| `strategic-focus-capability-building` | verified | 10–13 / `strategic-focus-in-a-fragmented-world` | Dealmakers prioritize capability, market position and strategic focus over diffuse expansion. Supported qualitative synthesis. |

### Reuters Institute

| Stable ID | Outcome | Pages / evidence | Final corrected claim and review |
|---|---|---|---|
| `ai-search-platform-relationships` | unresolved | 10 / `answer-engines-and-traffic` | Supplied page discusses trusted content and AI concerns, not answer engines/referral traffic. Correct abstention. |
| `distinctive-content-response` | unresolved | 15 / `content-strategies-distinctiveness` | Supplied page covers licensing expectations, not the retained distinctive-content survey proposition. Correct abstention. |
| `video-platform-discovery-shift` | verified | 18 / `social-media-mid-life-crisis-video` | Search decline/direct relationships and 79% video/71% audio priorities are retained, while unsupported causal referral claims are removed. Strong correction. |
| `newsroom-ai-uses-and-oversight` | unresolved | 30 / `latest-tales-ai-newsroom` | Supplied page reports media-position perceptions, not newsroom AI uses/oversight. Correct abstention. |
| `subscription-membership-priority` | unresolved | 36 / `business-models-and-innovation` | Supplied page covers AI content adaptation, not subscription/membership priorities. Correct abstention. |
| `ai-browsers-adaptable-content` | verified after retry | 39 / `whats-next-in-technology` | 59% prioritize improving existing products versus 37% new products; AI personalization/experimentation implication is source-grounded. Useful and specific. |

### Adjust

| Stable ID | Outcome | Pages / evidence | Final corrected claim and review |
|---|---|---|---|
| `cross-channel-measurement-recommendation` | verified | 11 / `multiplatform-strategy` | 31% complete-satisfaction context and integrated measurement/deep-linking recommendations are retained. Specific and commercially useful. |
| `gaming-benchmark-coverage` | verified | 17–21,23 / `gaming-finding-keeping-users` | Global subvertical installs/sessions, CPI and mixed growth are bound to 2024–2025. Strong numeric correction with no unsupported churn/conversion enrichment. |
| `ecommerce-benchmark-coverage` | verified after retry | 27–30 / `ecommerce-finding-keeping-users` | Global and regional installs/sessions, retention, CPI and paid/organic divergence are preserved. Specific and decision-relevant. |
| `finance-benchmark-coverage` | verified after retry | 34–38 / `finance-finding-keeping-users` | Global/regional acquisition, engagement, retention, CPI and paid/organic metrics remain bound. Strong numeric coverage. |
| `ai-marketing-applications` | verified | 9 / `ai-infrastructure` | Data assistants, predictive segmentation, generative AI, maturity caveat and reported >20% efficiency gain are preserved. Source-grounded and useful. |
| `benchmark-methodology-context` | verified | 13 / `takeaways-methodology` | Scope, January 2024–January 2026 range, dataset, country sets and limitations are preserved. Factually sound context, but lower standalone editorial value. |

## Baseline comparison and quality review

Against the prior Step 1/Step 2 live baseline documented before these fixes:

| Measure | Prior live baseline | Final live replay | Change |
|---|---:|---:|---:|
| Reference variants evaluated | 39 | 39 | unchanged |
| Reference verified outcomes | 38 | 38 | unchanged count |
| Reference false accepts | 1 | 0 | **improved** |
| Reference false rejects | 0 | 0 | unchanged |
| Real retained claims evaluated | not evaluated | 29 | newly measured |
| Real claims verified | not evaluated | 27 | newly measured |
| Real claims unresolved | not evaluated | 8 | explicit fail-closed holds |
| Full-page/source-hash checks | partial | 5/5 PDFs matched | strengthened |

The final replay confirms no independently identified unsupported factual claim
was marked verified in the 39-case reference gate. The real shortlist review
found no source-binding or protected-field regression in the verified outputs.
It did find eight retained claims whose current page bindings are section
dividers, mismatched pages, or insufficiently specific source locations; these
were correctly unresolved rather than replaced with nearby findings.

The principal editorial limitation is not factual fabrication but retained
input quality: a few verified outputs are descriptive or generic
(`human-support-remains-important`, `activate-news-discovery-and-direct-visits`,
and `benchmark-methodology-context`), while the Reuters page-binding issues
produce four unresolved claims. Step 2 correctly refuses to invent stronger
claims, but it cannot repair a weak or misbound Step 1 shortlist without fresh
selection evidence.

## Regression verification

Passed:

- `python -m pytest -q tests/test_verified_claims_visual_generator.py tests/test_verified_claims_step2_replay.py` — **18 passed**.
- `python -m pytest -q tests/test_prompt_dry_run_validation.py tests/test_llm_routing_policy.py tests/test_report_generation_execution_policy.py` — **57 passed**.
- `python -m pytest -q tests/test_artifact_insight_shortlisting.py tests/test_artifact_normalization_source_fidelity.py` — **39 passed**.
- `python -m pytest -q tests/test_artifact_generator.py tests/test_report_regeneration_generator.py` — **199 passed**.
- Evidence-binding, claim-validation, retained-grounding and source-identity suites — **48 passed**.
- Public editorial-quality, report-quality and publish-readiness suites — **124 passed**.
- PDF crop/text/contents and OpenAI service suites — **35 passed**.
- `python -m ruff check src/generators/verified_claims_visual_generator.py scripts/quality/replay_verified_claims_step2.py tests/test_verified_claims_visual_generator.py tests/test_verified_claims_step2_replay.py` — **passed**.
- `python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3` — **passed** after recording the two new Step 2 prompt namespaces in the authoritative fixture baseline; token/cost totals are unchanged on subsequent replay.
- `python scripts/quality/replay_verified_claims_step2.py --provider-free --output out/verified_claims_step2_provider_free_final.json` — **success; 15 cases / 39 variants, 5/5 PDFs hash-matched, 29 retained claims**.
- The focused regressions cover PDF hash mismatch, missing hash, empty image path,
  conflicting span pages, continuation after a skipped claim, malformed
  correction/verification responses, substantive verification notes, typed
  provider errors, bounded retries, original-direction verifier context,
  multi-page rendering, stable bindings and exact 29-claim retained assembly.

The earlier repository suites from the Step 1 baseline remain the relevant
regression set; the new production changes do not alter public contracts,
canonical artifact schemas, regeneration, safe removal or publication gates.
The final live run itself provides the cross-stage visual evidence; it did not
perform downstream regeneration or publication writes by design.

## Remaining limitations and Step 3 verdict

- Live evaluation starts from retained post-selection artifacts. It does not
  prove fresh candidate recall, selection diversity, or live Step 1 quality.
- Eight real retained claims remain unresolved because their supplied pages do
  not support the retained proposition. This is honest fail-closed behavior,
  but it is not sufficient evidence to begin visual factualisation or canonical
  verified-claim persistence.
- The Capgemini online-deal numeric content is visually supported but still has
  no safe structured Step 1 metric binding; speculative enrichment remains
  intentionally excluded.
- Shadow results remain non-authoritative and are not passed to downstream
  regeneration or publication readiness.

**Verdict: PARTIAL.** Step 2 correction, verification, provenance checks,
error handling, retry bounds and benchmark correctness are implemented and
verified. The frozen reference gate is clean and the 29 real retained claims
were actually evaluated, but the unresolved/misbinding rate and lack of fresh
selection evidence mean Step 3 cannot safely begin on this evidence alone.
