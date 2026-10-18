# MarketLense — Verified Claims Step 2 Visual Shadow Evidence

**Date:** 2026-10-18
**Branch:** `codex/fix-retained-insight-evidence-validation`
**Step 1 comparison baseline:** `953555f`
**Prior Step 2 regression commit:** `1e966def`
**Frozen manifest SHA-256:** `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`
**Status:** **PARTIAL**

## Scope and decision

Step 2 remains shadow-only. It does not overwrite retained artifacts, promote a
corrected claim, change publication readiness, regenerate downstream artifacts,
or write to WordPress. Step 3 visual factualisation and canonical
verified-claim persistence remain unstarted.

This correction restores visual inspection of retained DocMap-only pages as
provisional context, while removing the unsafe Step 2-time rebinding of
candidate/final insight evidence. A DocMap section ID or page can be inspected
by the model, but it is not promoted to a canonical finding or authoritative
evidence binding. The live result is therefore evidence about Step 2 correction
and verification, not fresh Step 1 candidate-selection evidence.

## Latest final-code frozen-five evaluation

The latest final-code live output is
`out/verified_claims_step2_live_recovery_final_v4_20261018/report.json`.
It used the exact five hash-matched PDFs, complete physical pages, GPT-6 Luna
High, independent correction and verification calls, and no canonical or
publication writes. The final correction adds one fail-closed provenance rule:
when deterministic recovery was required, a verified replacement must cite a
supporting physical page from its bounded recovery candidates; the retained
page cannot be replacement provenance merely because it was inspected.

| Evaluation set | First pass | After retry | Verified total | Unresolved | Failed | Skipped | Input |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reference variants | 37 | 1 | 38 | 0 | 1 | 0 | 39 |
| Real retained shortlist | 28 | 0 | 28 | 1 | 0 | 0 | 29 |
| **All claims** | **65** | **1** | **66** | **1** | **1** | **0** | **68** |

Counts are mutually exclusive terminal outcomes and are checked by the replay
arithmetic guard. The reference gate matched **39/39** expected outcomes with
**0 false accepts** and **0 false rejects**. `ACT-004-wrong-page` failed closed
after two bounded correction attempts: the second correction was source-factual
for the supplied page but unrelated to the strict original direction. It was
not verified. `ADJ-001-unsupported-metric` was not accepted as written; the
final claim replaced churn/conversion with the page-19 install/session metrics
and was verified against the original PDF.

Measured v4 usage was **139 provider calls**, **2,262,219 input tokens**,
**83,192 output tokens**, **2,345,411 total tokens**, **$0.267819 estimated
cost**, **1,200.603 seconds** wall time, and **107 rendered physical pages**.
The cost ledger contained 139 selected and 139 seen rows; all five expected
PDF hashes matched. The separate seven-case recovery rerun completed **7/7
first-pass verified** with 14 calls, 327,059 total tokens, $0.036580, and
202.990 seconds.

### Final seven-case supporting-page ledger

These are the seven targeted recovered real claims, using the final v4 rows.
Original evidence IDs, spans and retained physical pages remained unchanged;
the support pages below are visual-verifier output, not canonical evidence.

| Report / stable ID | Original page(s) | Recovery pages inspected | Verified supporting page(s) | Outcome |
|---|---:|---:|---:|---|
| Capgemini `consumer-control-of-ai` | 30 | 35, 36, 5 | 35 | verified |
| Capgemini `human-support-remains-important` | 40 | 45, 32, 5 | 45 | verified |
| Capgemini `digital-assistants-engagement-recommendation` | 46 | 6, 47, 52 | 6 | verified |
| KPMG `buyer-standalone-platform-access` | 18 | 19, 21, 6 | 21, 6 | verified |
| Reuters `ai-search-platform-relationships` | 10 | 12, 6, 5 | 12 | verified |
| Reuters `distinctive-content-response` | 15 | 18, 6, 17 | 17 | verified |
| Reuters `subscription-membership-priority` | 36 | 38, 39, 40 | 38 | verified |

The physical-page check matters: Reuters page 15 is a different Q8 page, while
page 17 contains the Q13 distinctiveness chart; Reuters page 36 is a section
locator, while page 38 contains the commercial-publisher revenue chart. The
final guard therefore cannot silently accept a model response that cites only
the retained locator. Recovered IDs remain provisional audit metadata and each
selected shadow row is `source_binding_status=provisional_recovered` with
`canonical_approval_status=not_approved`.

### Final report-level shadow selection

Selection used the complete verified corrected insight set per report, the
existing public editorial-quality evaluator, and duplicate checks. It did not
sort or assign provenance from retrieval scores.

| Report | Verified corrected set | Recovered candidates | Selected replacements | Decision |
|---|---:|---:|---|---|
| Capgemini Research Institute | 5 | 3 | `consumer-control-of-ai`, `human-support-remains-important`, `digital-assistants-engagement-recommendation` | retained; distinct themes and candidate support pages |
| Activate | 6 | 0 | none | no safe recovered replacement; one retained claim unresolved after malformed correction responses |
| KPMG | 5 | 1 | `buyer-standalone-platform-access` | retained; support pages 21/6, provisional only |
| Reuters Institute | 6 | 4 | `subscription-membership-priority` | retained; other recovered final claims abstained by existing numeric-evidence quality blocker |
| Adjust | 6 | 0 | none | no recovery candidates |

The three Reuters abstentions (`ai-search-platform-relationships`,
`distinctive-content-response`, and `ai-browsers-adaptable-content`) were not
silently promoted: their corrected wording was source-grounded on pages 12,
17, and 41 respectively, but the retained evidence text did not carry the
material numeric bindings required by the existing public-quality validator.
The selector records those blockers rather than treating visual verification
as canonical evidence. This is a conservative editorial/provenance outcome,
not evidence that the source pages are factually wrong.

This v4 run improves provenance safety relative to the v3 replay by rejecting
retained-locator-only replacement support. It is not a claim of improved live
Step 1 selection effectiveness: the inputs are the retained 29-insight replay
cohort, and model output remains run-dependent.

## Prior v2 recovery run (historical comparison)

The current implementation was evaluated against reviewed baseline
`1a65158db2caf38a05bf05da713cd68a0c0efe70` and the Step 1 retained-selection
baseline `953555f`. The authoritative live output is
`out/verified_claims_step2_live_recovery_final_v2_20261018/report.json`.
It used the exact frozen-five PDFs, GPT-6 Luna with High reasoning, complete
physical pages, deterministic recovery candidates, independent correction and
verification calls, and no canonical or publication writes.

| Evaluation set | First pass | After retry | Verified total | Unresolved | Failed | Skipped | Input |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reference variants | 36 | 2 | 38 | 1 | 0 | 0 | 39 |
| Real retained shortlist | 27 | 2 | 29 | 0 | 0 | 0 | 29 |
| **All claims** | **65** | **2** | **67** | **1** | **0** | **0** | **68** |

The reference gate matched **39/39** expected outcomes with **0 false accepts**
and **0 false rejects**. The one unresolved reference is the deliberate
`ACT-004-wrong-page` fixture; recovery is disabled for reference/adversarial
claims, so the supplied wrong page cannot be bypassed. Retry-success counts are
mutually exclusive with first-pass counts.

Measured live usage was **139 provider calls**, **2,307,350 input tokens**,
**80,029 output tokens**, **$0.270749 estimated cost**, **1,310.451 seconds**
wall time, and **107 rendered physical pages**. The per-run ledger contained
139 selected and 139 seen rows. All five expected PDF hashes matched. The
provider-free replay separately confirmed 15 cases, 39 variants, 29 retained
claims, 29/29 theme slots, and no fabricated fixtures.

After the v2 dispatch, a final fail-closed guard was covered by focused tests:
claims carrying the strict reference policy cannot consume a recovery map even
if one is accidentally supplied, and unresolved recovered claims retain their
inspected-page metadata. This does not change the v2 rows because reference
claims had no recovery candidates.

### Seven-row recovery and replacement ledger

Original bindings remain immutable. “Candidate pages” are the bounded pages
sent as provisional visual context; “primary support” identifies the page(s)
that independently support the final wording. Recovered finding/DocMap IDs are
audit metadata only and are never promoted to canonical evidence.

| Report / stable ID | Original binding | Candidate pages → primary support | Final claim and factual/value assessment | Terminal outcome |
|---|---|---|---|---|
| Capgemini `consumer-control-of-ai` | `ai-consumers-trusted-guide`, p.30 divider | 35, 36, 5 → 35–36 | 12,000-consumer October 2025 results: 76% want strict assistant boundaries, 66% trust explanations more, and 71% report concern about Gen-AI data-use transparency. Source labels and population were preserved; the final wording adds a defensible trust implication. | verified after retry |
| Capgemini `human-support-remains-important` | `reliable-tech-loyalty`, p.40 divider | 45, 32, 5 → 45 | Human interaction increasing loyalty rose from 54% to 74% at customer support and 40% to 66% at purchase stage across the two 12,000-consumer surveys. The two periods and population were preserved. | verified |
| Capgemini `digital-assistants-engagement-recommendation` | `recommendations`, p.46 divider | 6, 47, 52 → 6, 47 | The report recommends assistants as engagement channels, preference-aware interactions, and channel-specific promotions. This is an explicit source recommendation, not an invented causal result. | verified |
| KPMG `buyer-standalone-platform-access` | `portfolio-simplification-as-a-value-creation-strategy`, p.18 divider | 19, 21, 6 → 19, 21 | Carve-outs can give buyers more clearly defined standalone platforms with transformation levers and operational upside, subject to execution complexity. The wording remains a bounded commercial implication of the source. | verified |
| Reuters `ai-search-platform-relationships` | `answer-engines-and-traffic`, p.10 irrelevant locator | 12, 6, 5 → 12 | Surveyed publishers expect search traffic to fall 43% over three years; Chartbeat reports 33% global and 38% US declines, while attribution to AI Overviews remains uncertain. Forecast, observed data, bases, periods, and uncertainty remain distinct. | verified |
| Reuters `distinctive-content-response` | `content-strategies-distinctiveness`, p.15 section start | 18, 6, 17 → 17 | Q13 base 264: +91 investigations, +82 contextual analysis, +76 chart value for community-building, +72 human stories, +63 verification. The final claim explicitly records the accompanying prose’s +75 community-building value. | verified |
| Reuters `subscription-membership-priority` | `business-models-and-innovation`, p.36 irrelevant locator | 38, 39, 40 → 38 | Among commercial publishers excluding publicly funded broadcasters (n=259), 76% expected subscription/membership to be important or very important in 2026, the leading expected stream/focus. The expectation is not presented as realized revenue. | verified |

The shadow replacement selector retained all seven recovered candidates with
editorial-theme bindings (Capgemini 3, KPMG 1, Reuters 3), while rejecting one
Reuters candidate as semantically duplicate of its existing baseline insight.
Activate and Adjust had no provisional replacement candidate. This selection
is an audit comparison only; it does not call `select_artifact_insights()` and
does not mutate the retained 29-insight artifacts.

### Before/after and independent review

The pre-recovery retained-artifact replay had 22/29 real claims verified (16
first pass, 6 after retry), 6 unresolved, and 1 failed. The recovery run has
29/29 verified, with 27 first pass and 2 after retry. The v2 rerun versus the
immediately preceding recovery run changed only the retry distribution (29/29
real and 39/39 reference outcomes remained the same); it removed a Reuters
Contents page from provisional context without changing the selected
replacement set. The earlier v1 run recorded 142 calls/$0.278674; v2 recorded
139 calls/$0.270749. This difference is a measured run-to-run result, not a
claim of model-quality improvement from replay alone.

Independent inspection of the original PDF pages confirmed the seven primary
support locations above, including Capgemini pp.35–36 and 45, Capgemini
recommendation pp.6/47, KPMG pp.19/21, Reuters p.12, p.17’s chart/prose
discrepancy, and Reuters p.38. `ACT-004-wrong-page` remained unresolved, and
`ADJ-001-unsupported-metric` was accepted only for the source-supported gaming
install/session metrics on Adjust p.19. No independently reviewed unsupported
material claim was marked verified. Capgemini’s supported online-deal numeric
content remains preserved in the upstream artifact; no speculative metric-spine
enrichment was added.

The successful Activate platform-video row also retained its multi-page
binding; its final claim names the nested top-creator cohort before stating the
YouTube/Facebook view split, so the component percentages are not promoted as
unrestricted platform totals.

The recovery resolver now rejects a hash-mismatched PDF, distinguishes printed
labels from physical indices, skips divider/contents pages, limits candidates
to three, and keeps recovered source identities provisional. Recovery is
enabled only for the 29 real retained claims, not for the 39 adversarial
reference variants.

## Root causes fixed

Commit `1e966def` introduced two coupled regressions:

1. `bind_artifact_evidence_spans()` could replace a retained DocMap locator
   with a finding ID during normal artifact normalization and during replay.
   The proposition/token heuristic could bypass missing fidelity approval and
   mutate retained evidence IDs, pages, excerpts, and factual context.
2. The visual generator rejected a claim whenever all supplied spans came from
   `doc_map`, so the model could not inspect the retained provisional page.

The fix removes that Step 2 rebinding path and keeps the original binding
unchanged. The visual generator now renders the complete retained physical
page when its source identity, page, span, PDF hash, and evidence metadata are
internally consistent. DocMap-only evidence is recorded as
`provisional_page_inspection` with `canonical_promotion: false`. Conflicting
source identity, page, evidence ID, or malformed span metadata still fails
closed. Existing source/PDF, evidence-fidelity, and validation boundaries are
reused; no new service, LLM stage, or persistence path was added.

The verification prompt and deterministic response handling now also require
source-grounded explanatory notes and reject a final claim that merely
restates a section heading. The original claim remains analytical direction,
not factual authority; the final corrected claim is evaluated.

## Provider-free frozen-five replay

Command:

`python scripts/quality/replay_verified_claims_step2.py --provider-free --output out/verified_claims_step2_provider_free_final_20261018/report.json`

The replay used retained real-report PDFs and artifacts without a model,
fabricated fixtures, publication state, or canonical-claim writes.

| Report | PDF pages | SHA-256 | Retained claims | Theme slots | Reference variants |
|---|---:|---|---:|---:|---:|
| Capgemini Research Institute | 82 | matched | 5 | 5 | 9 |
| Activate | 140 | matched | 7 | 7 | 11 |
| KPMG | 42 | matched | 5 | 5 | 7 |
| Reuters Institute | 47 | matched | 6 | 6 | 8 |
| Adjust | 41 | matched | 6 | 6 | 4 |
| **Total** | — | **5/5** | **29** | **29/29** | **39** |

The retained IDs, public wording, evidence IDs, physical pages, spans,
protected factual fields, metric-spine inputs, and key-figure inputs were not
changed. This confirms input preservation and coverage, not fresh-selection
quality.

## Historical pre-recovery GPT-6 Luna High replay (comparison only)

Command:

`python scripts/quality/replay_verified_claims_step2.py --live --output out/verified_claims_step2_live_final_20261018/report.json`

The run used the exact five hash-matched PDFs, complete original pages at
216 DPI, `gpt-6-luna`, High reasoning, independent correction and
verification calls, and the existing bounded two-attempt paths.

| Evaluation set | Verified first pass | Verified after retry | Verified total | Unresolved | Failed | Skipped | Input |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reference variants | 38 | 0 | 38 | 1 | 0 | 0 | 39 |
| Real retained shortlist | 16 | 6 | 22 | 6 | 1 | 0 | 29 |
| **All claims** | **53** | **6** | **60** | **7** | **1** | **0** | **68** |

The reference gate matched **39/39** expected terminal outcomes with **0 false
accepts** and **0 false rejects**. `ADJ-001-unsupported-metric` was accepted
only after direct review of PDF page 19 showed that the final install/session
claim was source-supported and relevant to the original gaming-performance
direction. `ACT-004-wrong-page` remained unresolved; the model did not use a
different page to bypass the supplied physical-page binding.

Counts are mutually exclusive terminal outcomes. A retry success is counted
once in `verified_after_retry`, not again as a first-pass or separate
verified result. The sole failed row was the KPMG buyer-platform claim, whose
heading-only correction did not receive substantive source-grounded
verification evidence. The Capgemini human-support row terminated unresolved
after the deterministic heading-only claim check. The Adjust finance claim
was corrected on retry to state the source-supported LATAM +57% versus APAC
+50% session comparison.

Measured run data:

- Provider calls: **294**; input tokens: **4,431,510**; output tokens:
  **172,910**.
- Estimated cost: **$0.529617**; wall time: **1,217.198 seconds**.
- Full-page renders: **90**; cache enabled. Fresh-run cache reuse was not
  measured, so no cache-efficiency claim is made.
- Source PDFs: **5/5** expected hashes matched.
- No provider failure, canonical-claim mutation, publication write, or
  WordPress write occurred.

## Eight previously unresolved source-binding rows

The eight rows reported by the previous evaluation were not patched
individually. Their common defect was treating broad DocMap navigation/context
IDs as canonical factual evidence or allowing the replay to rebind them.

| Report / stable ID | Retained provisional binding | Root cause at the boundary | Corrected handling |
|---|---|---|---|
| Capgemini `consumer-control-of-ai` | `ai-consumers-trusted-guide`, p.30 | Related finding had no fidelity-supported source reference. | Provisional page inspection; no promotion. |
| Capgemini `digital-assistants-engagement-recommendation` | `recommendations`, p.46 | Related finding was unsupported/ambiguous. | Provisional page inspection; no promotion. |
| Activate `activate-digital-assistant-access-forecast` | `s4`, pp.18, 26, 30 | No authoritative proposition-compatible finding was retained. | Provisional page inspection; no promotion. |
| KPMG `buyer-standalone-platform-access` | `portfolio-simplification-as-a-value-creation-strategy`, p.18 | Same-section material was not an equivalent, fidelity-approved binding. | Provisional page inspection; no promotion. |
| Reuters `ai-search-platform-relationships` | `answer-engines-and-traffic`, p.10 | Nearby search-traffic material was a different proposition. | Provisional page inspection; no promotion. |
| Reuters `distinctive-content-response` | `content-strategies-distinctiveness`, p.15 | Related finding was not fidelity-supported. | Provisional page inspection; no promotion. |
| Reuters `newsroom-ai-uses-and-oversight` | `latest-tales-ai-newsroom`, p.30 | Related finding was not fidelity-supported. | Provisional page inspection; no promotion. |
| Reuters `subscription-membership-priority` | `business-models-and-innovation`, p.36 | Related finding was not fidelity-supported. | Provisional page inspection; no promotion. |

This correction does not claim that those eight pages support their original
propositions. It preserves their source identity and page for provisional
inspection and fails closed when correction cannot establish a supported final
claim.

## Historical pre-recovery real shortlist ledger (comparison only)

The replay JSON contains the complete original/corrected claim payload,
protected fields, evidence spans, request metadata, and per-attempt notes. The
ledger below records the observable before/after binding and terminal reason.
`retained` means an existing source-bound finding was left unchanged;
`provisional_page_inspection` means the retained DocMap locator was used only
for visual context and was not promoted.

### Capgemini Research Institute

| Stable ID | Outcome | Binding and pages | Final wording / terminal reason |
|---|---|---|---|
| `value-fairness-transparency` | verified | `value-fairness-quality` pp.4,8,9; retained | Consumers’ value expectations extend beyond competitive price to transparency, ethical practices, uncompromised quality, and fairness in pricing, policies, and treatment; 74% would switch for a lower regular price and 71% for reduced pack size/quality without clear communication. |
| `online-deal-searching` | verified | `careful-spending-and-indulgence` pp.5,9; retained | In October 2025, 62% agreed they were spending more time searching online for deals and discounts, versus 64% in November 2024. The supported numeric content remained intact; no unsupported metric-spine enrichment was added. |
| `consumer-control-of-ai` | unresolved | `ai-consumers-trusted-guide` p.30; provisional | Two correction attempts could not establish a supported final claim. |
| `human-support-remains-important` | unresolved | `reliable-tech-loyalty` p.40; provisional | The page was identified as a section divider with no supporting detail; the heading-only qualitative rewrite was not verified after two attempts. |
| `digital-assistants-engagement-recommendation` | unresolved | `recommendations` p.46; provisional | Two correction attempts could not establish a supported final claim. |

### Activate

| Stable ID | Outcome | Binding and pages | Final wording / terminal reason |
|---|---|---|---|
| `activate-outlook-revenue-models` | verified | `s1` pp.3–6; provisional | Forecast global consumer Internet/media revenue rises from $1.7T in 2017E to $2.0T in 2021E, with $302B added at 4.1% CAGR; Internet access contributes $128B, ad revenue $108B, and paid content $66B. |
| `activate-super-user-time-and-spending` | verified | `s3` pp.12–16; provisional | In U.S. 2017 data, the top 25% of video users accounted for 61% of video time and 34% of spend; sports super fans were 27% of users and 61% of time. |
| `activate-digital-assistant-access-forecast` | verified_after_retry | `s4` pp.18,26,30; provisional | Among U.S. smart-speaker owners, weekly music use was 74% for super users versus 48% for average users; the corrected claim preserves the n=820 population and listed use comparisons. |
| `activate-platform-specific-web-video` | verified | `s6` pp.49,53–59; provisional | In Q2 2017, top-creator views were 83% influencer/17% media on YouTube versus 52%/48% on Facebook; the >50M-view cohort and footnote shares were preserved. |
| `activate-news-discovery-and-direct-visits` | verified_after_retry | `s9` pp.93,96,97,99,100,105,108; provisional | The corrected claim describes platform-mediated publishing/discovery options in the U.S. in 2017 and explicitly rejects unsupported direct-visit traffic inference. |
| `activate-ecommerce-capability-stack` | verified | `s10` pp.111,115,117–119; provisional | In 2016, marketplaces represented 84% of the top-15 e-commerce companies’ $1.2T global GMV; the page describes attention, transactions, fulfillment, and third-party sellers. |
| `activate-podcasting-engagement-rationale` | verified | `s11` pp.124,136; provisional | U.S. podcast ad revenue is forecast to rise from $237M in 2017E to $642M in 2021E, while 12+ podcast listening is forecast to rise from 24% to 39%; 2017E remains a small fraction of linear radio’s $15B advertising market. |

### KPMG

| Stable ID | Outcome | Binding and pages | Final wording / terminal reason |
|---|---|---|---|
| `buyer-standalone-platform-access` | failed_verification | `portfolio-simplification-as-a-value-creation-strategy` p.18; provisional | Heading-only correction lacked substantive verification evidence after the bounded attempts. |
| `execution-governance-value-creation` | verified | `execution-discipline-as-a-decisive-source-of-advantage` pp.30,31,33; provisional | Talent retention, decision rights, integrated teams, and disciplined tracking are described as ways to protect execution and value capture during complex transactions. |
| `agentic-ai-deal-workflows` | verified | `ai-driven-transformation-of-deal-execution` pp.23–28; provisional | Organizations are deploying agentic AI for multi-step deal workflows while flagging exceptions for human review and decision. |
| `buyer-appetite-execution-approaches` | verified | `diverging-risk-appetites-between-buyers` pp.14–17; provisional | Private equity reported greater deal confidence and a larger planned pipeline (7.3 vs. 5.2 deals), and more often considered carve-outs (55% vs. 21%) and minority-to-majority investments (50% vs. 18%). |
| `strategic-focus-capability-building` | verified | `strategic-focus-in-a-fragmented-world` pp.10–13; provisional | Dealmakers increasingly prioritize transactions that deepen capabilities, strengthen market position, and accelerate strategic intent over expansion that diffuses focus. |

### Reuters Institute

| Stable ID | Outcome | Binding and pages | Final wording / terminal reason |
|---|---|---|---|
| `ai-search-platform-relationships` | unresolved | `answer-engines-and-traffic` p.10; provisional | Two correction attempts could not establish a supported final claim. |
| `distinctive-content-response` | unresolved | `content-strategies-distinctiveness` p.15; provisional | Two correction attempts could not establish a supported final claim. |
| `video-platform-discovery-shift` | verified | `social-media-mid-life-crisis-video` p.18; provisional | The page does not support linking publisher traffic decline to feeds/video; separately, Q14 reports 79% prioritizing more video investment and 71% more audio. |
| `newsroom-ai-uses-and-oversight` | verified_after_retry | `latest-tales-ai-newsroom` p.30; provisional | Among publishers (base 273), 52% said audience concerns about inaccurate news/AI slop strengthen news media’s position versus 27% who said they weaken it; these are perceptions, not measured effects. |
| `subscription-membership-priority` | unresolved | `business-models-and-innovation` p.36; provisional | Two correction attempts could not establish a supported final claim. |
| `ai-browsers-adaptable-content` | verified_after_retry | `whats-next-in-technology` p.39; provisional | Respondents prioritize improving existing products (59%) over developing new products/services (37%); the page describes AI as enabling both personalization and lower-cost new products. |

### Adjust

| Stable ID | Outcome | Binding and pages | Final wording / terminal reason |
|---|---|---|---|
| `cross-channel-measurement-recommendation` | verified | `multiplatform-strategy` p.11; provisional | Only about 31% of marketers report complete satisfaction with cross-platform data; the page recommends integrated journeys, deep linking, segmentation, retargeting, and web-to-app solutions. |
| `gaming-benchmark-coverage` | verified | `gaming-finding-keeping-users` pp.17–21,23; provisional | 2024–2025 acquisition, sessions, retention, CPI, and partner breadth diverged across regions and genres; the corrected claim preserves the stated percentage and retention series. |
| `ecommerce-benchmark-coverage` | verified_after_retry | `ecommerce-finding-keeping-users` pp.27–30; provisional | 2025 e-commerce installs fell 10% while sessions rose 5% globally; regional, engagement, CPI, and paid/organic changes are preserved as a mixed benchmark rather than one-direction trend. |
| `finance-benchmark-coverage` | verified_after_retry | `finance-finding-keeping-users` pp.34–38; provisional | Global installs fell 4% while sessions rose 21%; LATAM led install growth at +76% and sessions at +57%, versus APAC +50% session growth, with the other reported finance metrics retained. |
| `ai-marketing-applications` | verified | `ai-infrastructure` p.9; provisional | AI is framed as marketing/measurement infrastructure, with cross-channel assistants, predictive segmentation, creative testing, journey modeling, and uneven maturity; advanced deployments reportedly exceeded 20% efficiency gains. |
| `benchmark-methodology-context` | verified | `takeaways-methodology` p.13; provisional | The report’s verticals, regions, January 2024–January 2026 period, mixed app datasets, country sets, aggregation/anonymization, and limitations are preserved. |

## Historical pre-recovery independent factual/editorial review

- Direct text extraction from the retained original PDFs spot-checked the
  changed cases: Capgemini p.9 contains the 62% October 2025 / 64% November
  2024 deal-search values; KPMG p.18 is a section-cover page containing only
  the portfolio-simplification heading; and Adjust pp.34–35 explicitly show
  LATAM at +57% finance-session growth versus APAC at +50%, with LATAM at
  +76% install growth.
- No retained artifact was mutated and no provisional binding was promoted.
- The two canonical Capgemini findings preserved their source-supported values,
  populations, periods, and evidence IDs. The online-deal 62%/64% comparison
  survived correction; the absence of a safe structured metric binding remains
  documented rather than filled speculatively.
- The 22 verified real claims were reviewed for values, labels, cohorts,
  populations, denominators, geography, period, forecast/observed status, and
  qualitative defensibility. The two rejected real corrections were not
  counted as verified.
- The heading-only Capgemini and KPMG rewrites were rejected. The verification
  prompt permits defensible commercial interpretation, but requires an
  observed relationship, bounded pattern, or source-supported explanation; it
  does not require literal source wording.
- The 39 reference variants remained a separate regression gate. Their
  outcome match is not treated as a substitute for editorial review of every
  real corrected sentence.

## Regression verification

Passed in this worktree:

- `python -m pytest -q tests/test_artifact_evidence_binding.py tests/test_artifact_normalization_source_fidelity.py tests/test_artifact_insight_shortlisting.py` — **50 passed**.
- `python -m pytest -q tests/test_verified_claims_visual_generator.py tests/test_verified_claims_step2_replay.py tests/test_prompt_dry_run_validation.py` — **71 passed**.
- `python -m pytest -q tests/test_artifact_generator.py tests/test_report_regeneration_generator.py tests/test_report_regeneration_identity_and_failures.py tests/test_llm_service.py tests/test_llm_routing_policy.py tests/test_pdf_crop_decomposition.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py` — **342 passed**.
- `py scripts/ci/check_contract_schemas.py` — **passed**.
- `ruff check` on all changed Python files, `py -m compileall` on changed Python files, and `git diff --check` — **passed**.
- Provider-free frozen-five replay — **passed**; 15 cases, 39 variants, 5/5 hashes, 29 retained claims, 29/29 theme slots, no fabricated fixtures.

The focused regressions cover removal of automatic DocMap rebinding,
provisional page inspection, missing-fidelity and lexical-overlap abstention,
source-page/hash conflicts, malformed/empty render inputs, typed non-retryable
failures, continuation after a failed claim, bounded retries, substantive
qualitative notes, heading-only rewrites, stable IDs, protected fields, and
cache behavior.

The repository type check remains a pre-existing failure with seven mypy
errors at unchanged lines in the parent branch; no type baseline was changed.
The remaining validation and CI checks are recorded with their exact results
in the delivery message and must not be represented as passed here until run.

## Remaining limitations and Step 3 verdict

- This is a retained-artifact replay, not fresh Step 1 generation. It does not
  prove candidate recall, selection diversity, or repeated-run stability.
- The 39 reference variants and 29 real claims now have complete terminal
  accounting, but provider output remains model- and run-dependent. The
  reference gate is a regression guard, not a substitute for independent
  editorial review of every corrected sentence.
- DocMap-only pages remain provisional inspection context. The frozen retained
  corpus does not provide canonical direct finding bindings for most selected
  claims, so this work does not establish upstream source-binding completeness.
- Capgemini online-deal numeric content is preserved in the corrected shadow
  claim but still lacks a safe structured Step 1 metric binding; speculative
  enrichment remains excluded.
- The seven recovered propositions are not persisted as canonical verified
  claims, are not passed to regeneration or publication readiness, and have not
  been evaluated through Step 3 visual factualisation.
- Fresh source generation and human editorial sign-off remain outside this
  replay. No live-selection effectiveness claim is made from post-selection
  replay alone.

**Verdict: PARTIAL.** The Step 2 shadow implementation and frozen-five
evaluation pass source-hash checking, bounded recovery, final-claim validation,
reference accounting, and the physical-support fail-closed guard. The v4 run
still has one unresolved real retained claim and conservative report-level
abstentions where retained numeric evidence is insufficient. Canonical
promotion and Step 3 visual factualisation remain intentionally unstarted;
Step 3 should wait for canonical source-binding/selection approval and
independent editorial review.
