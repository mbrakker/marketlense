# MarketLense — Verified Claims Step 2 Visual Shadow Evidence

**Date:** 2026-10-19
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

## Prior v5 frozen-five evaluation (historical comparison)

The latest final-code live output is
`out/verified_claims_step2_live_recovery_final_v5_20261019/report.json`.
It used the exact five hash-matched PDFs, complete physical pages, GPT-6 Luna
High, independent correction and verification calls, and no canonical or
publication writes. v5 rebuilds editorial-quality inputs from the final
corrected claim and actual inspected PDF page text when available; retained
metric/evidence fields remain lineage only, and verifier notes are not treated
as verbatim PDF evidence. The correction namespace now has a 4,096-token
structured-output budget; correction and verification attempt limits remain
two each.

| Evaluation set | First pass | After retry | Verified total | Unresolved | Failed | Skipped | Input |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reference variants | 36 | 2 | 38 | 1 | 0 | 0 | 39 |
| Real retained shortlist | 27 | 1 | 28 | 0 | 1 | 0 | 29 |
| **All claims** | **63** | **3** | **66** | **1** | **1** | **0** | **68** |

Counts are mutually exclusive terminal outcomes and are checked by the replay
arithmetic guard. The reference gate matched **39/39** expected outcomes with
**0 false accepts** and **0 false rejects**. `ACT-004-wrong-page` remained
unresolved after two bounded correction attempts. `ADJ-001-unsupported-metric`
was not accepted as written; the final claim replaced churn/conversion with the
page-19 install/session metrics and was verified against the original PDF.
Activate’s previously unresolved real claim now verifies after one retry with a
relevant page-96 traffic replacement; the replacement is still provisional and
is not canonical evidence.

Measured v5 usage was **144 provider calls**, **2,431,356 input tokens**,
**90,879 output tokens**, **2,522,235 total tokens**, **$0.288577 estimated
cost**, **1,275.670 seconds** wall time, and **107 rendered physical pages**.
The cost ledger contained 144 selected and 144 seen rows; all five expected
PDF hashes matched. These are live-run measurements, not estimates from the
prior v4 output.

## Latest v6 page-attribution, deduplication, and chart replay

This is the current evaluation for the reviewed baseline
`a352209fbad34099b597171e55235b31ca86cba9`. It preserves the exact frozen
manifest (`744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`),
the five retained PDFs and their expected SHA-256 identities, complete
physical-page rendering, GPT-6 Luna High, separate correction and verification
calls, and the existing two-attempt maximum for each. The replay remained
shadow-only: no retained artifact, canonical claim, readiness state, or
publication was written.

The root causes were narrow and deterministic at existing boundaries:

1. Correction and verification requests previously supplied an ordered image
   list without an explicit one-based page association. The prompt payload now
   carries `image N = physical PDF page P` for every image, and the binding
   records the same map. When native page text is available, a conservative
   deterministic check rejects a selected support page when the corrected
   claim's material numeric values occur together only on another inspected
   page. This keeps visual-only claims eligible while failing closed on the
   reproduced Activate mismatch.
2. Shadow replacement deduplication now treats a matching stable ID as the
   same provenance-repair candidate rather than a self-duplicate. Cross-ID
   near-duplicates use the existing public-editorial duplicate pairs without
   requiring identical provisional evidence IDs; existing metric-binding
   conflict checks still preserve distinct populations, metrics, periods and
   business implications.
3. The correction prompt now requires arithmetic and label reconciliation
   before combining chart totals with component values. If a chart's aggregate
   headline conflicts with its components, the model must narrow to a
   supported proposition or remain unresolved. On the inspected KPMG physical
   page 11, APAC's components are 12% + 46% = 58% against a displayed 62%
   headline, and the Americas components are 14% + 48% = 62% against a
   displayed 58% headline. Those incompatible values are not combined.

### Targeted real-PDF regressions

The Activate targeted run evaluated seven retained claims: 6 verified on the
first pass and 1 after retry, with no failed or unresolved terminal rows. The
first correction for `activate-super-user-time-and-spending` selected physical
page 14 even though the chart is on page 15; the deterministic page/value
guard rejected that verification. The bounded retry corrected the support to
pages **15 and 16**, preserving the video and sports findings. The full replay
also produced pages 15 and 16 for this stable ID.

The KPMG targeted run evaluated five retained claims: 5 first-pass verified,
with no retry, failed, or unresolved rows. `strategic-focus-capability-building`
now remains a narrower narrative claim supported on physical page
11; it does not combine the inconsistent chart headline totals with component
splits. The original source inconsistency remains a source limitation, not a
promoted factual relationship.

### Frozen-five terminal outcomes and measured comparison

Counts below are derived from terminal claim rows and are mutually exclusive;
a retry success is counted once under `verified after retry`.

| Evaluation set | v5 first pass | v5 retry | v5 verified | v5 unresolved | v5 failed | v6 first pass | v6 retry | v6 verified | v6 unresolved | v6 failed | Input |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Reference variants | 36 | 2 | 38 | 1 | 0 | 36 | 2 | 38 | 1 | 0 | 39 |
| Real retained shortlist | 27 | 1 | 28 | 0 | 1 | 29 | 0 | 29 | 0 | 0 | 29 |
| **All claims** | **63** | **3** | **66** | **1** | **1** | **65** | **2** | **67** | **1** | **0** | **68** |

The reference gate matched **39/39** expected outcomes with **0 false accepts**
and **0 false rejects**. `ACT-004-wrong-page` remained unresolved after its
bounded attempts. `ADJ-001-unsupported-metric` was verified only after the
final claim replaced unsupported churn/conversion wording with the
source-supported strategy/casino/slots install and session metrics on physical
page 19; its classification was not changed to make the model pass.

| Measure | v5 | v6 | Observed change |
|---|---:|---:|---|
| Provider calls / selected ledger rows | 144 | 140 | 4 fewer; no hidden retry increase |
| Input tokens | 2,431,356 | 2,277,696 | 153,660 fewer |
| Output tokens | 90,879 | 78,729 | 12,150 fewer |
| Total tokens | 2,522,235 | 2,356,425 | 165,810 fewer |
| Estimated cost | $0.288577 | $0.267140 | $0.021437 lower |
| Wall time | 1,275.670 s | 1,244.423 s | 31.247 s lower |
| Full-page renders | 107 | 107 | unchanged |
| Cache | enabled; reuse not measured | enabled; reuse not measured | no cache-efficiency claim |

All five PDF hashes matched. The current live report is
`out/verified_claims_step2_live_page_dedup_final_20261019/report.json`; the
provider-free input replay is
`out/verified_claims_step2_provider_free_page_dedup_20261019/report.json`.

### Current 29-claim provenance and wording ledger

Stable candidate IDs, retained source identities, evidence IDs, original
physical pages, spans, protected factual fields, metric-spine inputs and
key-figure inputs remained unchanged. Supporting pages below are visual
verifier outputs, not canonical evidence replacements. The v6 final wording
and page-specific notes are retained in the live report; rows marked “wording
changed” reflect a fresh model paraphrase, not an upstream binding mutation.

| Report | Stable ID | v5 terminal → v6 terminal | v6 supporting page(s) | Before/after observation |
|---|---|---|---|---|
| Capgemini | `value-fairness-transparency` | verified → verified | 4, 9 | wording changed; source binding unchanged |
| Capgemini | `online-deal-searching` | verified → verified | 9 | wording changed; 62%/64% values preserved |
| Capgemini | `consumer-control-of-ai` | verified → verified | 35, 36 | wording changed; provisional pages remain source-supported |
| Capgemini | `human-support-remains-important` | verified → verified | 45 | wording changed; survey populations preserved |
| Capgemini | `digital-assistants-engagement-recommendation` | verified → verified | 6 | wording changed; recommendation remains source-grounded |
| Activate | `activate-outlook-revenue-models` | verified → verified | 4, 5 | wording changed; forecast status and segment values preserved |
| Activate | `activate-super-user-time-and-spending` | verified → verified | **15, 16** | **p14 attribution corrected; video/sports binding preserved** |
| Activate | `activate-digital-assistant-access-forecast` | verified → verified | 30 | wording changed; cohort comparison preserved |
| Activate | `activate-platform-specific-web-video` | verified after retry → verified | 59 | model selected a different source-supported platform-topic proposition |
| Activate | `activate-news-discovery-and-direct-visits` | verified → verified | 99 | model selected a narrower source-supported platform proposition |
| Activate | `activate-ecommerce-capability-stack` | verified → verified | 115 | wording changed; GMV split and seller counts source-supported |
| Activate | `activate-podcasting-engagement-rationale` | verified → verified | 136 | wording changed; forecast and 12+ population preserved |
| KPMG | `buyer-standalone-platform-access` | verified → verified | 21, 6 | wording changed; multi-page qualification preserved |
| KPMG | `execution-governance-value-creation` | verified → verified | 33 | wording changed; talent/governance interpretation bounded |
| KPMG | `agentic-ai-deal-workflows` | verified → verified | 26 | wording changed; human-review condition preserved |
| KPMG | `buyer-appetite-execution-approaches` | verified → verified | 15, 16, 17 | wording changed; buyer populations and percentages preserved |
| KPMG | `strategic-focus-capability-building` | failed → verified | **11** | **narrowed away from contradictory chart totals** |
| Reuters | `ai-search-platform-relationships` | verified → verified | 12 | wording changed; survey and Chartbeat populations kept separate |
| Reuters | `distinctive-content-response` | verified → verified | 17 | wording changed; net percentage-point unit preserved |
| Reuters | `video-platform-discovery-shift` | verified → verified | 18 | wording changed; response direction preserved |
| Reuters | `newsroom-ai-uses-and-oversight` | verified → verified | 30 | wording changed; survey perceptions not treated as measured effects |
| Reuters | `subscription-membership-priority` | verified → verified | 38 | wording changed; commercial-publisher denominator preserved |
| Reuters | `ai-browsers-adaptable-content` | verified → verified | 41 | wording changed; 75% impact relationship preserved |
| Adjust | `cross-channel-measurement-recommendation` | verified → verified | 11 | wording changed; recommendation remains qualified |
| Adjust | `gaming-benchmark-coverage` | verified → verified | 17 | model selected a distinct region-level supported view |
| Adjust | `ecommerce-benchmark-coverage` | verified → verified | 27 | wording changed; global/regional metric relationships preserved |
| Adjust | `finance-benchmark-coverage` | verified → verified | 34, 37 | wording changed; retention/CPI fields remained source-supported |
| Adjust | `ai-marketing-applications` | verified → verified | 9 | wording changed; qualitative interpretation bounded |
| Adjust | `benchmark-methodology-context` | verified → verified | 13 | wording changed; period, regions and dataset limitations preserved |

The eight changed supporting-page lists are model-selected visual support, not
evidence-ID changes: `activate-super-user-time-and-spending` is the material
provenance correction; the other differences are fresh, source-supported
model selections or multi-page explanations. No live run can establish that
all wording differences are deterministic improvements over v5.

### Latest P2 source-attribution and deduplication hardening replay

The current correction is intentionally narrower than v6. It changes the
existing page-attribution boundary to compare all material numeric values
against the union of the cited pages. A cited page that contains only one
shared value no longer bypasses a conflict when the remaining values occur
together on another inspected page. If extracted text cannot demonstrate that
conflict, the guard remains permissive for visual-only, OCR-incomplete, and
legitimate multi-page cases. The regression set includes the Activate pages
14–16 partial-overlap failure and a valid split-value attribution across pages
14–15.

The shadow selector now separates provable final duplicates from ambiguous
public-quality near-duplicates. Exact final propositions and same-ID final
repairs retain their existing behavior; conflicting metric or temporal/
forecast bindings remain distinct. Near-duplicates without an authoritative
binding are retained and reported in `ambiguous_duplicate_pairs` for editorial
assessment instead of being silently removed. The corrected-input builder
continues to use final corrected wording and does not copy obsolete retained
metric/evidence fields.

The fresh live replay is
`out/verified_claims_step2_live_page_dedup_p2_20261019/report.json`. It used
the exact frozen five-report PDFs, GPT-6 Luna High, full pages, separate
correction and verification calls, and the unchanged two-attempt limits. The
provider-free replay hash-checked all five source PDFs.

| Evaluation set | First pass | After retry | Verified total | Unresolved | Failed | Skipped | Input |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reference variants | 38 | 0 | 38 | 1 | 0 | 0 | 39 |
| Real retained shortlist | 26 | 2 | 28 | 1 | 0 | 0 | 29 |
| **All claims** | **64** | **2** | **66** | **2** | **0** | **0** | **68** |

The reference gate matched **39/39** expected terminal outcomes with zero
false accepts and zero false rejects; `ACT-004-wrong-page` remained the sole
unresolved reference variant. The one unresolved real row was
`activate-outlook-revenue-models`: the corrected claim included the overall
forecast values visible on physical pages 4–5 and segment contributions visible
together on physical page 6, but the model cited only pages 4–5. The new guard
failed closed on both attempts. The prior v6 run accepted this row because its
single-value-overlap shortcut returned success; the PDF confirms that this is
a source-page attribution correction, not a forced 29/29 target.

Compared with v6, the current run used **142 provider calls**, **2,454,944
input tokens**, **87,489 output tokens**, **2,542,433 total tokens**,
**$0.289241 estimated cost**, **1,491.478 seconds** wall time, and **107
full-page renders**. v6 used 140 calls, 2,277,696 input tokens, 78,729 output
tokens, 2,356,425 total tokens, $0.267140, 1,244.423 seconds, and 107 renders.
The additional calls and other outcome changes are model-run variance plus the
demonstrated attribution rejection; no retry or model policy was increased.
Cache reuse was not measured in either run.

The actual report-level shadow selection retained the same eight replacement
IDs as v6 (Capgemini 3, KPMG 1, Reuters 4; none from Activate or Adjust), with
no duplicate pairs and no ambiguous pairs in either live report. One current
Reuters selected row, `distinctive-content-response`, is marked
`pending_visual_source_text`; it remains shadow-only and
`canonical_approval_status=not_approved`, so it is not publication-ready.
The provider-free replay remains
`out/verified_claims_step2_provider_free_page_dedup_p2_20261019/report.json`
and records 15 cases, 39 variants, 29 retained IDs, 29 theme slots, and no
fabricated fixtures.

### v5 seven-case supporting-page ledger (historical)

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

### v5 report-level shadow selection (historical)

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

### v5 editorial-input and replacement-selection correction

The v5 selector fixes two stale-input defects. `_verified_corrected_insight()`
now creates a fresh, provisional quality input containing the final corrected
wording and actual inspected page text when available; it does not copy the
retained metric, evidence ID, evidence excerpt, or original pages into the
replacement facts. Original IDs, spans, pages, source identity, and evidence
lineage remain separate audit fields. Verifier explanations remain
`source_truth_notes_by_page`, never verbatim PDF evidence. Exact normalized
final propositions are deduplicated before inherited metric compatibility is
considered; near duplicates still require compatible metric bindings.

| Report | Verified corrected set | Recovered candidates | Selected shadow replacements | v4 selected | Measured change |
|---|---:|---:|---|---|---|
| Capgemini Research Institute | 5 | 3 | `consumer-control-of-ai`, `human-support-remains-important`, `digital-assistants-engagement-recommendation` | same 3 | no identity change |
| Activate | 7 | 0 | none | none | prior unresolved claim verified after retry; no recovered replacement candidate |
| KPMG | 4 | 1 | `buyer-standalone-platform-access` | same 1 | one contradictory chart correction failed closed |
| Reuters Institute | 6 | 4 | `ai-search-platform-relationships`, `distinctive-content-response`, `subscription-membership-priority`, `ai-browsers-adaptable-content` | 1 | three valid recovered replacements retained |
| Adjust | 6 | 0 | none | none | no identity change |

The three newly selected Reuters replacements retain `source_binding_status =
provisional_recovered` and `canonical_approval_status = not_approved`. The
distinctiveness row is `editorial_quality_status =
pending_visual_source_text` because deterministic text extraction does not
reliably carry the chart’s percentage-point unit; the full physical page and
visual verification support the values. This is pending evidence state, not a
publication-quality waiver.

The Activate correction is source-grounded on physical page 96 and replaces
the unsupported news-discovery/direct-visits proposition with the relevant
top-news-site traffic chart. The KPMG `strategic-focus-capability-building`
row failed closed after two verification attempts because the corrected
response combined APAC and Americas headline totals with incompatible component
splits; no unsupported combined claim was promoted.

Independent review of the 28 real verified final claims found seven
deterministic numeric/text-quality warnings caused by chart extraction or unit
representation, not unsupported values: Activate pages 4–5, 14, 96 and 136;
KPMG pages 15/17; Reuters pages 17 and 18. Full-page visual inspection
confirmed the reported chart values. One material provenance limitation remains:
the Activate super-user row reports supporting physical page 14 although the
chart is visibly on physical page 15 (the page was among the inspected pages).
It was not selected as a recovered shadow replacement and no canonical artifact
was changed, but this mismatch blocks a clean Step 3 readiness verdict.

Provider-free replay command:
`py scripts/quality/replay_verified_claims_step2.py --provider-free --output out/verified_claims_step2_provider_free_after_fix_20261019/report.json`

The provider-free replay preserved the exact 29 retained identities, 39
reference variants, five PDF hashes, and all retained source artifacts. The v5
live run is evidence about this Step 2 implementation and this model replay;
it is not fresh evidence that Step 1 live selection quality improved.

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

- `py -m pytest tests/test_verified_claims_visual_generator.py tests/test_verified_claims_step2_replay.py tests/test_llm_routing_policy.py tests/test_llm_routing_retained_benchmark.py -q --disable-warnings --maxfail=10` — **75 passed**.
- `py -m pytest tests/test_artifact_insight_shortlisting.py -q --disable-warnings --maxfail=10` — **32 passed**.
- `py -m pytest tests/test_artifact_normalization_source_fidelity.py tests/test_public_editorial_quality_generator.py tests/test_public_editorial_quality_provenance.py tests/test_claim_validation_source_pages.py tests/test_claim_validation_source_excerpts.py tests/test_lineage_regeneration.py tests/test_regeneration_candidate.py tests/test_regeneration_finalization.py tests/test_contract_schema_gate.py -q --disable-warnings --maxfail=10` — **183 passed**.
- `py -m pytest tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py -q --disable-warnings --maxfail=10` — **78 passed**.
- `py scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3` — **passed** with the existing allowlist recording the measured **+783 validation-family tokens** for the explicit image/page map and chart-reconciliation instructions.
- `py scripts/ci/check_contract_schemas.py`, `py scripts/ci/check_backlog_source.py`, `py scripts/ci/check_repository_hygiene.py`, and `git diff --check` — **passed**.
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

**Verdict: PARTIAL.** The latest P2 hardening replay passes source-hash
checking, bounded correction/verification, final-claim validation, reference
accounting, duplicate protection, and the strengthened physical-support
fail-closed guard. It verified 28/29 real retained claims and correctly left
`activate-outlook-revenue-models` unresolved after the PDF demonstrated that
its cited pages omitted the segment values used in the final claim; the
adversarial `ACT-004-wrong-page` reference variant also remained unresolved.
The exact v6 29/29 result is retained as a comparison, not overwritten. This
does not prove fresh Step 1 selection effectiveness, canonical source-binding
completeness, or independent editorial acceptance. Canonical promotion and
Step 3 visual factualisation remain intentionally unstarted; Step 3 should
wait for canonical source-binding/selection approval and independent editorial
review.

## Current explicit retained-cohort replay and recovery correction (2026-10-20)

This section supersedes the stale additional-five shadow result for Step 2
evaluation. The implementation was inspected from `740ba5c` and the retained
artifact producer is `410f186b26f372c6b8eb5a82af16dc5b8740c4af`. The requested
cohort snapshot was used directly:

`tmp/verified-claims-premerge-20261019/frozen-reliability-28p518bm/cohort_result.json`

The source manifest was
`tmp/verified-claims-premerge-20261019/step2-new-cohort-reference.json`.
Its SHA-256 is `5868d6b8b62f4d97be8ed1f8160738f17d00ec1ccc3d7ab5b8e31bef360ff93e`;
the cohort-result SHA-256 is
`b9da85567108998bda61b3bb236183b912d9c475c05fa4085abf7e1d65158a9f`.

### Root cause and bounded correction

The Bigcommerce false negative was at the existing Step 2 provenance boundary.
Recovery correctly ranked methodology page 2 as a provisional inspection
candidate because the retained page-4 text did not meet the deterministic
native-text similarity threshold; the retained page's evidence spans and
visual content were not thereby disproved. The prompts, generator, and replay
selector nevertheless treated the recovery candidate list as an exhaustive
set of eligible supporting pages. That caused an independently visible page-4
wallet finding to fail closed.

The correction now allows any inspected original or recovered full PDF page to
support the final claim when the verifier independently cites it and provides
page-specific substantive notes. Recovery ranking remains an inspection aid,
not factual authority; recovered evidence remains provisional. Existing
inspected-page, page-note, numeric-attribution, source-hash, malformed-response,
and shadow-only guards were retained. The native-text positive-support helper
was removed only from the recovery-only acceptance shortcut; native text is
still used by the existing conservative attribution diagnostics.

The replay script now has explicit retained-input mode. It enumerates every
`insights_final` entry from the supplied cohort result, checks each source PDF
SHA-256 before dispatch, records artifact SHA-256 and producer commit, and
separates selected, eligible, evaluated, skipped, and unavailable claims. It
also accepts repeated `--artifact REPORT=PATH` inputs for a selected artifact
set. No page-less claim is omitted from the inventory. Exact evidence text is
given a bounded provisional physical page only when it occurs on exactly one
page of the hash-matched PDF; this is inspection context, never an authoritative
binding. The Merchant Risk Council section-level claim has no such safe
location and remains unavailable.

The exact current-cohort command was:

```powershell
python scripts/quality/replay_verified_claims_step2.py --live `
  --cohort-result tmp/verified-claims-premerge-20261019/frozen-reliability-28p518bm/cohort_result.json `
  --sources-manifest tmp/verified-claims-premerge-20261019/step2-new-cohort-reference.json `
  --output tmp/verified-claims-premerge-20261019/step2-current-cohort-shadow-v2/result.json
```

The raw report is retained at
`tmp/verified-claims-premerge-20261019/step2-current-cohort-shadow-v2/result.json`.
All five source hashes matched, all five retained artifacts were found, the
producer commit was recorded for every report, and `shadow_only=true`,
`canonical_mutation=false`, and `publication_write=false` were recorded.

| Report | Selected | Eligible | Evaluated | First pass / retry | Failed / unresolved / skipped | Unavailable |
|---|---:|---:|---:|---:|---:|---:|
| DoubleVerify | 5 | 5 | 5 | 5 / 0 | 0 / 0 / 0 | 0 |
| Merchant Risk Council | 5 | 4 | 4 | 3 / 1 | 0 / 0 / 0 | 1: `post-purchase-fraud-section-scope` |
| Algolia | 5 | 5 | 5 | 4 / 1 | 0 / 0 / 0 | 0 |
| Bain & Company | 5 | 5 | 5 | 5 / 0 | 0 / 0 / 0 | 0 |
| Bigcommerce | 5 | 5 | 5 | 5 / 0 | 0 / 0 / 0 | 0 |
| **Total** | **25** | **24** | **24** | **22 / 2** | **0 / 0 / 0** | **1** |

The complete source and artifact identities are in the raw JSON. The source
PDF SHA-256 values, artifact SHA-256 values, and common producer commit are:

| Report | Source PDF SHA-256 | Retained artifact SHA-256 | Producer commit |
|---|---|---|---|
| DoubleVerify | `99f0cc4f7787cac52b7f89eefa7659053b3703ea100b9e0522fa500c64463d7e` | `e0361e2e3aae1ef0e3cae6fb30b45ed205235b1d7d0b8d982ed4037a7fb79643` | `410f186b26f372c6b8eb5a82af16dc5b8740c4af` |
| Merchant Risk Council | `29c01d042b7020b3e43de3c6eb12c84e1fd7b960be6c73b877170fdec12932e6` | `2530c4ef6a8cc2a68b4250acffc711c7af73e6e93e5ffdad5278d950e4f24feb` | `410f186b26f372c6b8eb5a82af16dc5b8740c4af` |
| Algolia | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50` | `8d5a71b087337e92cfc3f05658bc20de03b8eca1098e6efd405604003da3d611` | `410f186b26f372c6b8eb5a82af16dc5b8740c4af` |
| Bain & Company | `07541f3433b72007010ff604a93d0c560b6c6709ffd7bb5a58fefa81908f86c7` | `dfd089ab3ade716abe7134022a2b0085729833fc5ee054ef1adde665e39e5968` | `410f186b26f372c6b8eb5a82af16dc5b8740c4af` |
| Bigcommerce | `29ffb53b9818460066c86e8d954bdd904bd0e11d2360d90dac040a5d33b9e7c3` | `71b83f2c96d0f367f1d8dd4e660942542084082c7b0f593190416cc249b2e868` | `410f186b26f372c6b8eb5a82af16dc5b8740c4af` |

The v2 live run made **52 provider calls** (52 ledger rows selected and
seen), used **829,972 input tokens** and **33,255 output tokens** (**863,227
total**), cost **$0.099628 estimated**, rendered **15** full physical pages,
and took **464.414 seconds**. Cache was enabled but fresh-run reuse was not
measured. The earlier current-snapshot pass is retained for comparison (22
eligible, 22 first-pass verified, 44 calls, $0.079482, 361.613 seconds); it
preceded the two exact Algolia page recoveries and is not the final result.

### Current per-claim ledger

The raw JSON retains the complete original and corrected text, stable ID,
evidence IDs, evidence spans, original pages, inspected pages, supporting
pages, recovery candidates, source notes, attempt records, artifact identity,
and PDF hashes. The compact ledger below records the material before/after
binding and terminal outcome; `? -> page` means the artifact had no original
physical page and the exact-text lookup supplied only a provisional inspection
page.

| Report | Stable ID | Terminal outcome | Original -> supporting page(s) | Review result |
|---|---|---|---|---|
| DoubleVerify | `attention-index-normalization-q1-2026` | verified | 9 -> 9 | Normalization, 28-day window, Q1 2026 and vertical context remained source-backed. |
| DoubleVerify | `quality-brand-suitability-regional-q1-2026` | verified | 3 -> 3 | APAC/EMEA/LATAM/North America values and ranking remained source-backed. |
| DoubleVerify | `regional-inapp-video-attention-q1-2026` | verified | 10 -> 10 | In-App Video regional values remained correctly labeled. |
| DoubleVerify | `quality-fraud-sivt-regional-q1-2026` | verified | 3 -> 3 | Global and regional Fraud/SIVT values, period and direction remained supported. |
| DoubleVerify | `global-video-benchmarks-ctv-scope-q1-2026` | verified | 4 -> 4 | CTV exclusion and device/video benchmark labels remained supported. |
| Merchant Risk Council | `realtime-payments-merchant-acceptance` | verified | 2 -> 2 | 43%, merchant population, geography and growth characterization remained supported. |
| Merchant Risk Council | `agentic-ai-payments-exploration-plans` | verified after retry | 2 -> 2 | 63% and the near-term exploration/implementation status remained supported. |
| Merchant Risk Council | `annual-survey-merchant-base` | verified | 2 -> 2 | Survey size, business sizes and 35+ country scope remained supported. |
| Merchant Risk Council | `realtime-payments-growth-characterization` | verified | 2 -> 2 | The qualitative growth statement stayed tied to the 43% acceptance finding. |
| Merchant Risk Council | `post-purchase-fraud-section-scope` | unavailable | — -> — | DocMap section-context span has no physical page; it was not inferred or evaluated. |
| Algolia | `ai-intent-revenue-link-perception` | verified | ? -> 12 provisional | Exact retained quote is uniquely on p.12; final wording distinguishes perceptions from measured effects. |
| Algolia | `revenue-investment-incentive` | verified | 5 -> 5 | Unsupported original incentive framing was replaced with p.5 search-investment values; relevant but materially different. |
| Algolia | `regional-ai-purchase-likelihood-agreement` | verified after retry | 12 -> 12 | US, total and Australia/NZ values retained with respondent bases. |
| Algolia | `agentic-search-integration-consideration` | verified | 27 -> 27 | Integration influence values and Top-2 relationship remained supported. |
| Algolia | `agentic-search-deployment-and-plans` | verified | ? -> 26 provisional | Exact retained quote is uniquely on p.26; 17% implemented and 61% planned remained supported. |
| Bain & Company | `born-tech-growth-share` | verified | 1 -> 1 | 52%, top-20-gainer cohort and 2015–20 comparison remained supported. |
| Bain & Company | `tech-value-creators-types` | verified | 1 -> 1 | 52%/20%/28% categories and denominator remained supported. |
| Bain & Company | `market-growth-share-breakdown` | verified | 1 -> 1 | Market-value growth split and period remained supported. |
| Bain & Company | `asset-light-scaling-recommendation` | verified | 1 -> 1 | Four source-listed actions remained defensible recommendations. |
| Bain & Company | `cloud-platform-catalysts` | verified | ? -> 1 provisional | Exact quote is on the one-page PDF; final claim uses source-backed 52%/20% plus the four actions. |
| Bigcommerce | `preferred-wallet-abandonment` | verified | 4 -> 2,4 | Former false negative fixed: p.4 finding and p.2 survey context were independently cited. |
| Bigcommerce | `discount-message-opt-in-out` | verified | 7 -> 7 | 74%, same-day opt-in/out and discount purpose remained supported. |
| Bigcommerce | `shopping-discovery-apps` | verified | 5 -> 5 | Algorithm narrative was kept distinct from the chart's platform-journey percentages. |
| Bigcommerce | `reviews-validate-purchase-decisions` | verified | 4 -> 4 | Two-in-three, review benefit ranking and purchase-validation purpose remained supported. |
| Bigcommerce | `guest-checkout-abandonment` | verified | 8 -> 8 | Guest-checkout percentage and the distinct 58% contact-detail condition remained supported. |

Independent review of the original full pages found **zero independently
confirmed unsupported material claims among the 24 verified rows**. Two
replacements deserve editorial attention even though they are source-grounded:
Algolia's `revenue-investment-incentive` moved from an unsupported revenue-
incentive proposition to the page-5 search-investment distribution, and Bain's
page-less `cloud-platform-catalysts` moved from a qualitative catalyst passage
to a quantitative value-growth/action formulation. Both remain commercially
related and are shadow-only, but neither is evidence that the model preserved
the exact original proposition. The complete verified-set quality check also
flagged near-duplicate final propositions for Bain's born-tech pair and
Merchant's two real-time-payment rows; no row was silently promoted or
deduplicated in this Step 2 replay.

### Unchanged 39-variant reference gate

The original five-report reference gate was run separately with retained real
claims excluded. It evaluated all **39 variants**: **37 first-pass verified,
1 verified after retry, 38 verified, 1 unresolved, 0 failed, 0 skipped**,
with **39/39 expected outcome matches, 0 false accepts, and 0 false rejects**.
`ACT-004-wrong-page` remained unresolved after its bounded attempts. The gate
therefore did not force the known wrong-page case into a pass. Its live usage
was **80 provider calls**, **676,546 input**, **38,176 output**, **714,722
total tokens**, **$0.086743 estimated**, and **540.282 seconds**; cache reuse
was not measured. The retained five-report reference expectations and 15-case
fixture definitions were not changed.

### Verification and remaining limitations

Focused tests after the correction include **66 passing tests** across the
visual generator and explicit/replay suites, plus the prompt, type, compile,
and Ruff checks. The full-repo mypy gate passed with zero tracked errors. The
provider-free inventory confirms the exact 25 selected identities and one
unavailable Merchant claim without fabricated fixtures. No canonical artifact,
publication-readiness state, or WordPress write was changed.

This remains a retained-artifact replay. It does not establish fresh Step 1
candidate recall, selection diversity, repeated-run stability, or canonical
source-binding completeness. Exact-text provisional pages are not canonical
evidence and do not authorize Step 3. The current Step 2 status is therefore
**PARTIAL**: the demonstrated Bigcommerce false negative and explicit-input
coverage defect are corrected and the reference gate remains green, but
canonical source-binding completeness and independent editorial approval are
still unresolved. Step 3 remains unstarted.

### Correction evidence — 2026-10-20 (provisional provenance, portable replay, and adversarial quality gate)

This close-out correction keeps retained physical pages and evidence spans
unchanged throughout explicit replay. A uniquely matched exact-text page is
now stored only as private inspection context and an existing recovery
candidate; it is not copied into the retained claim's `pages` field or
reported as an authoritative binding. `source_binding_status` is derived from
the pages that actually support the final claim: retained-only support is
`retained`, support from a recovered page is `provisional_recovered`, and
mixed retained/recovered support is also provisional. A retained page with an
unused recovery candidate therefore remains retained. Explicit physical-page
fields and evidence-span pages are accepted only when consistent, physical,
positive and in range; conflicting or ambiguous locations are unavailable.
The visual evaluator can inspect a page-less claim only when an existing
bounded recovery candidate supplies the page, without canonical promotion.

The Merchant Risk Council claim `post-purchase-fraud-section-scope` remains
unavailable. Its retained evidence is a DocMap section-context span with no
candidate text, finding evidence span or safe physical page in the four-page
PDF. The retained pool did not contain a stronger eligible alternative, so
the replay records one unavailable selected identity rather than inferring a
page or forcing 25/25 coverage.

#### Actual-PDF adversarial corpus

The corpus is committed at
`docs/quality/verified-claims-step2-adversarial-corpus-20261020.json` and the
replay harness is
`scripts/quality/replay_verified_claims_step2_adversarial.py`. It used the
existing evaluator, GPT-6 Luna High, the exact hash-matched PDFs from the
additional frozen-five manifest, and full rendered pages. The result is
`tmp/verified-claims-premerge-20261019/step2-adversarial-shadow-v4/result.json`.
The nine cases below were independently checked against the cited full PDF
pages; the final wording, not the intentionally mutated original wording, was
scored.

| Case | Mutation and expected source truth | Final corrected wording / terminal result | Pages | Manual assessment |
|---|---|---|---:|---|
| `ALG-ADV-001` | Geography: 68% is the USA result, while 63% is the overall result. | “Across 1,100 respondents, 63% say shoppers are more likely to complete a purchase using gen-AI-supported systems”; USA 68% and Australia/New Zealand 57% are labelled by market. **Verified.** | 12 | Correct population, total and market mapping. |
| `BAIN-ADV-001` | Chart components must total 100%: 52% born-tech, 20% tech-led strategy, 28% other. | Reports the 52%/20%/28% split for the top-20-gainer cohort and 2015–2020 period. **Verified.** | 1 | Components, denominator and period are source-supported. |
| `BIG-ADV-001` | The source observes 40% abandonment after a preferred-wallet failure; it does not prove sole causation or the main checkout driver. | States the observed 40% response and that wallet availability “can be a checkout friction point,” explicitly disclaiming causation and main-driver status. **Verified.** | 4 | Defensible qualitative interpretation without causal overclaim. |
| `BIG-ADV-002` | The preferred-wallet finding is on page 4; wrong page 8 must not rescue this strict claim. | No accepted final claim after two verification attempts; `verification_failed_twice`. **Failed closed.** | 8 original; none supporting | Strict source binding rejected unrelated page material. |
| `DV-ADV-001` | Values are percentages, not points: North America 3.7% and APAC 8.0% in Q1 2026. | Reports the Q1 2026 violation rates as 8.0% APAC and 3.7% North America, with a 4.3 percentage-point difference. **Verified.** | 3 | Unit and derived difference are correct. |
| `DV-ADV-002` | Attention values are geographically bound: APAC 131, EMEA 130, North America 128. | Labels all three regional values and identifies APAC as highest. **Verified.** | 10 | Metric-to-region relationships are preserved. |
| `DV-ADV-003` | The reporting period is Q1 2026, not Q2 2026. | Reports the four regional violation rates for Q1 2026 and their ordering. **Verified.** | 3 | Period, values and comparison are correct. |
| `MRC-ADV-001` | The population is 1,200+ eCommerce merchants, not consumers. | Attributes 43% real-time-payment acceptance to the annual survey of 1,200+ merchants across 35+ countries. **Verified.** | 2 | Cohort, denominator context and metric are correct. |
| `MRC-ADV-002` | 63% describes active exploration or planned implementation, not current use. | States that 63% are exploring or plan to implement agentic-AI payments and explicitly says this is not current use. **Verified.** | 2 | Forecast/planning status is not promoted to observation. |

The adversarial result was **8 verified first pass, 1 failed verification, 0
verified after retry, 0 unresolved, and 0 skipped**. It used **20 provider
calls**, **229,301 input tokens**, **8,915 output tokens**, **238,216 total
tokens**, **$0.027388 estimated cost**, and **168.718 seconds**. All five
source hashes matched. The eight accepted corrections were source-grounded
and commercially meaningful; the strict wrong-page case was not rescued by an
unrelated same-page replacement. No independently confirmed unsupported
material claim was marked verified.

#### Exact additional frozen-five replay

The exact selected roster remained **25 stable IDs**: DoubleVerify 5,
Merchant Risk Council 5, Algolia 5, Bain & Company 5, and Bigcommerce 5.
The corrected accounting is mutually exclusive: **25 selected, 24 eligible,
24 evaluated, 24 verified first pass, 0 verified after retry, 0 failed,
0 unresolved, 0 skipped, and 1 unavailable**. The unavailable identity is the
Merchant section-context claim documented above. All five source hashes
matched, and all 24 evaluated rows retained `canonical_approval_status` as
`not_approved`.

| Report | Selected | Eligible / evaluated | Verified first pass | Unavailable |
|---|---:|---:|---:|---:|
| DoubleVerify | 5 | 5 / 5 | 5 | 0 |
| Merchant Risk Council | 5 | 4 / 4 | 4 | 1 |
| Algolia | 5 | 5 / 5 | 5 | 0 |
| Bain & Company | 5 | 5 / 5 | 5 | 0 |
| Bigcommerce | 5 | 5 / 5 | 5 | 0 |
| **Total** | **25** | **24 / 24** | **24** | **1** |

The actual run is
`tmp/verified-claims-premerge-20261019/step2-current-cohort-shadow-v3/result.json`.
It used **48 provider calls**, **955,105 input tokens**, **28,439 output
tokens**, **983,544 total tokens**, **$0.109730 estimated cost**, **18
rendered pages**, and **634.004 seconds**. Compared with the retained baseline
(52 calls, 829,972 input tokens, 33,255 output tokens, **$0.099628**, and
**464.414 seconds**), coverage and selected identities are unchanged; the
call, token, cost and latency differences are provider/model-run variance, not
a deterministic quality improvement claim. The current run had no retries,
whereas the baseline had two retry successes.

The three recovered-only claims are Algolia
`ai-intent-revenue-link-perception` (support page 12), Algolia
`agentic-search-deployment-and-plans` (page 26), and Bain
`cloud-platform-catalysts` (page 1). They remain
`provisional_recovered`; their retained original page arrays remain empty.
Bigcommerce `preferred-wallet-abandonment` remains **retained** with original
and supporting page 4; page 2 was inspected as recovery context but did not
support the final claim. Independent review of all 24 final claims against the
full pages found zero confirmed unsupported material claims. The review noted
that Algolia's investment replacement and Bain's page-less catalyst
replacement are source-grounded, commercially related replacements rather
than proof that the original proposition was preserved exactly. Near-duplicate
editorial propositions remain visible for later editorial review and were not
silently deduplicated.

#### 39-variant reference gate and CI

The independent reference gate evaluated all **39 variants** with **38
verified first pass, 0 verified after retry, 1 unresolved, 0 failed, 0
skipped**, **39/39 expected-outcome matches**, **0 false accepts**, and **0
false rejects**. `ACT-004-wrong-page` remained unresolved. Usage was **78
provider calls**, **652,185 input tokens**, **34,567 output tokens**, **686,752
total tokens**, **$0.082506 estimated**, and **811.364 seconds**. The changed
retry distribution versus the prior run (37 first pass plus one retry) did not
change the gate result.

The four clean-CI replay fixtures now create compact artifacts/PDFs in the
test process rather than depending on historical `tmp/` paths. The three
oversized test modules were split into six owned case modules; every case file
is below the repository's 1,000-line ownership threshold. The focused current
suite passed **115 tests**, with **1 expected integration skip** and **1
deselected test**; repository hygiene, compile, Ruff and formatting checks
also pass. The earlier GitHub run's remaining **35 failures** are unrelated
legacy grounding/report-analysis failures (18 retained-claim grounding, 15
grounding-cohort regressions, and 2 report-analysis tests); the 4 historical
replay-fixture failures and 1 ownership failure are addressed here without
restoring unsafe generated-finding self-support.

This is still a retained-artifact shadow evaluation. It does not establish
fresh Step 1 selection recall, diversity, repeated-run stability, or canonical
source-binding completeness, and no canonical artifact, publication-readiness
state or WordPress write occurred. The final Step 2 verdict is **PARTIAL**:
the demonstrated provenance, explicit-page, portable-fixture and factual
quality defects are corrected and the reference gate is green, but fresh
selection evidence and independent editorial approval remain unavailable.
Step 3 remains unstarted.

#### Ten-report live reliability follow-up and deterministic release guards — 2026-10-22

This checkpoint records real-report reliability evidence associated with the
ten-report Step 1/E18 acceptance work; it does not promote or mutate any Step 2
claim.

- The clean remaining-five replay at `6f09874c` used fresh isolated state and
  the exact source PDFs. It used 181 provider calls, 1,729,700 input tokens,
  373,333 output tokens, `$0.421650`, and 2,649.459 seconds. Bain, Emplifi,
  and StackAdapt passed validation/readiness. DoubleVerify failed on a
  confirmed metric-label false positive caused by noisy chart OCR being checked
  instead of its precise retained `findings_statement` span. Adjust passed
  validation but failed readiness because a composite quote identifier reached
  public citation text.
- The deterministic fix at `08be09bf` scopes only the relationship check to an
  authoritative `findings_statement` span when present; all other checks retain
  the full evidence bundle. The follow-up sanitizer correction at `9e32ac36`
  rejects composite internal quote/finding/insight/figure/claim tokens. The corrected follow-up
  used 85 provider calls, 1,003,936 input tokens, 163,685 output tokens,
  `$0.209432`, and 1,559.072 seconds: DoubleVerify passed validation/readiness;
  Adjust failed closed on a separate unsupported `2024–2025` timeframe and
  incomplete numeric displays after three bounded repairs. No canonical,
  readiness, publication, or WordPress write was made.
- A provider-free re-render of the earlier valid Adjust artifact at `9e32ac36`
  produced zero internal-identifier matches. This verifies the projection
  correction but is not a live Adjust readiness result and does not claim
  improved selection quality. The exact remaining-five live rosters varied
  from the initial run (shared evidence IDs: DoubleVerify 1/5, Adjust 0/6,
  Bain 3/5, Emplifi 0/5, StackAdapt 0/5); no source-recall credit was added.

Focused affected validation, grounding, render, readiness, regeneration, and
Step 2 suites passed **416 tests, 1 skipped, and 1 deselected** before the final
two-line sanitizer follow-up; the focused sanitizer and findings-statement
regressions passed afterward, and changed-file Ruff plus `git diff --check`
passed. The latest branch commit is `9e32ac36`. Step 2 remains
**PARTIAL/NO-GO**, Step 1/E18 remains **PARTIAL/Active**, P6 remains open, and
Step 3 remains unstarted.

### CI acceptance-gate correction — 2026-10-20

The reviewed `d3ec52a0` branch reproduced all **35** reported failures against
the current environment: 18 retained-claim grounding, 15 frozen-cohort
grounding, and 2 report-analysis tests. An isolated `origin/main` worktree at
`bf736b47695605a9a00a1a8355c0d27ab0b0ab88` passed the same 139-test group,
so these were branch-only fixture-contract regressions, not a production
validator regression. The common root cause was positive fixtures using
generated `findings[].text` as authoritative evidence after the existing
validator correctly stopped treating that field as source proof. Positive
fixtures now carry independent source excerpts through the existing
`evidence` contract; generated-text-only negative cases remain fail-closed.
The two report-analysis failures had the same missing independent `f1`
excerpt and were corrected without changing source-title authority.

The Step 2 adversarial runner now enforces its nine-case expected-terminal
contract: exactly one known result per candidate ID, accepted terminal states,
nonempty positive final text, and existing supporting-page/hash/note
provenance. Missing, duplicate, unknown, malformed, skipped, wrong-terminal,
or invalid-provenance rows produce per-case diagnostics and a nonzero exit;
raw replay output is still written before the exit decision. Provider-free
comparator coverage passed all **9/9** corpus identities and rejected a
deliberately corrupted strict-negative row. No live provider replay was run in
this CI-correction slice; the prior **39-variant** PDF evaluation remains the
source of live model measurements, and manual review remains separate.

The focused final suite passed **151 tests**, with **1 expected integration
skip** and **1 deselected test**. Formatting, Ruff, type checking, architecture,
policy, documentation, schema, hygiene, and the long-test-file gate passed.
The aggregate run executed **7,846** selected tests and reported **7,842
passed, 2 skipped, 32 deselected, and 2 failures** before the final test-file
split: the introduced 1,012-line split-module failure was fixed by moving
existing key-figure cases into a third owned module; the remaining
`test_existing_wheelhouse_reports_missing_active_artifact` failure reproduces
unchanged on `origin/main` and fails because this host is CPython 3.14 while
the native wheelhouse audit requires CPython 3.12. Therefore the repository
quality gate is **PARTIAL**, not green in this environment. No canonical
artifact, publication-readiness state, provider call, or WordPress write was
performed. Step 2 remains **PARTIAL** and Step 3 remains unstarted.

### Final acceptance-integrity correction — 2026-10-20

The acceptance comparator now validates the serialized attempt history rather
than trusting a terminal label alone. A positive result must contain a
matching corrected claim, a successful verification attempt for the terminal
attempt number, and identical supporting pages plus substantive page-specific
notes. A negative result must contain a bounded correction/verification trail
whose terminal verification attempt is a substantive source-grounded
rejection; skipped, provider-error, malformed-response, missing-input, and
correction-only failures are not accepted as source rejections. The strict
`BIG-ADV-002` case must retain original physical page **8**, explicitly assess
that binding, and cannot accept page **4** as a replacement.

The comparator also requires valid 64-character hexadecimal SHA-256 values,
equal expected/actual hashes, and the same hash embedded in `source_identity`.
The existing source-identity parser and supporting-page validator remain the
authorities; no production visual verifier was changed.

The provider-free regression now constructs result-shaped attempts for all
**9/9** corpus identities and passes. Deliberately changing `BIG-ADV-002` to
accept page 4 fails closed. Comparing the retained adversarial replay from
the prior live run now correctly reports one mismatch (`BIG-ADV-002` returned
`verified` against its strict negative expectation); this is an audit of
retained output, not a new provider replay.

The hosted full-CI result for baseline commit `225d603e8ffbd3c26b587ee6516e85992a01f444`
is [run 39407483027](https://github.com/mbrakker/marketlense/actions/runs/39407483027):
Python 3.12 completed with **7,845 pytest passes and 1 skip**, both mutation
jobs and release evidence passing. The actual local `origin/main` merge-base
used for comparison is
`bf736b47695605a9a00a1a8355c0d27ab0b0ab88`; the earlier one-character-short
hash was corrected. The separate local CPython 3.14 wheelhouse limitation is
not a hosted-CI failure.

This correction adds no live LLM calls, canonical mutations, publication
writes, or WordPress writes. Step 2 remains **PARTIAL**: fresh Step 1
selection effectiveness, canonical integration, and independent editorial
approval remain unproven; E18 remains Active and Step 3 remains unstarted.

### BigCommerce strict-page reconciliation and span-contamination correction — 2026-10-20

This correction was developed from branch `85e3a9d094a855ea582f44b48cf2530fad7ed90a`.
The actual local `origin/main` merge-base is
`bf736b47695605a9a00a1a8355c0d27ab0b0ab88`. The two retained adversarial
snapshots below are immutable and were not overwritten or combined.

| Snapshot | Immutable result and SHA-256 | Producer / ledger run | BigCommerce wrong-page row |
|---|---|---|---|
| v1 | `tmp/verified-claims-premerge-20261019/step2-adversarial-shadow-v1/result.json` / `00b00a1d01f376ed5a31c3b4d28596ad40ff3ce07f3e647d27e4cde9ac221710` | `adversarial-corpus` / `verified-claims-step2-explicit-1792476737` | Original `[8]`; inspected `[8,4,2,7]`; recovered `[4,2,7]`; supporting `[4]`; 1 correction and 1 verification attempt; **verified**. |
| v4 | `tmp/verified-claims-premerge-20261019/step2-adversarial-shadow-v4/result.json` / `6164b405af3ff094b618abb13e87dfd464226503a5abd561b098fa89cc96d157` | `adversarial-corpus` / `verified-claims-step2-explicit-1792477748` | Original and inspected `[8]`; recovered/supporting `[]`; 2 correction and 2 verification attempts; **failed_verification**. |

Both snapshots identify the same BigCommerce PDF by SHA-256
`29ffb53b9818460066c86e8d954bdd904bd0e11d2360d90dac040a5d33b9e7c3`:
`out/browser_downloads/www.bigcommerce.com/e72f39fe19e5/ebook_0225_future_commerce_new_modes_guide_en_us.pdf`.
The v1 retained span was the stale text “Page 8 discusses guest checkout and
does not contain the preferred-wallet 40% finding.” It accepted the page-4
wallet recovery. v4 used the current wallet excerpt while retaining original
page 8, had no strict recovery candidates, and rejected both guest-checkout
rewrites with `verification_strict_direction_drift` and
`verification_source_truth_notes_by_page_invalid`. The contradiction is
therefore an input/cache and policy-path difference: v1 is a historical false
acceptance, while v4 is the current strict fail-closed behavior. Neither
artifact is evidence that one result should replace the other.

The production correction is intentionally at the existing visual-verification
boundary. `_claim_binding()` and `_verification_attempt()` now project page,
ID, span-coordinate and source-identity provenance to the model without
passing retained `evidence_spans[].text` as source proof; the complete spans
remain in the internal/result binding. Under strict original-direction policy,
the verifier also compares a sufficiently specific retained excerpt with the
available native PDF page text. If the excerpt uniquely matches a different
physical page while the original page is present and sufficiently populated,
the outcome receives `verification_strict_source_page_mismatch` and cannot be
accepted or promoted from that other page. Missing, sparse, scanned, repeated
or ambiguous text remains conservative. Strict recovery remains disabled;
report-level recovery is unchanged. Non-verified attempts no longer retain
model-supplied supporting-page or page-note metadata as if it were accepted
evidence.

#### Actual-PDF narrow validation

Three isolated GPT-6 Luna High runs used the exact BigCommerce PDF and only
the two adversarial BigCommerce cases. They made no canonical, publication,
readiness or WordPress writes. Every run kept the valid page-4 wallet case
verified and the strict page-8 wrong-page case failed closed; the strict case
never recovered or inspected page 4. The replay helper returned the report in
memory and persisted caches, usage ledgers, renders and input snapshots, but
does not emit a single `result.json` for these narrow runs, so no fabricated
live-result hash is reported.

| Run | Provider calls | Input / output / total tokens | Est. cost | Wall time | BIG-ADV-001 valid page-4 wallet | BIG-ADV-002 strict page-8 wrong page |
|---|---:|---:|---:|---:|---|---|
| `step2-bigcommerce-narrow-v1` | 6 | 50,382 / 3,068 / 53,450 | $0.006573 | 53.760 s | verified; original `[4]`, inspected `[4,2]`, recovered `[2]`, supporting `[4]` | failed verification; original/inspected `[8]`, recovered/supporting `[]` |
| `step2-bigcommerce-narrow-v2` | 5 | 43,999 / 2,725 / 46,724 | $0.005763 | 44.546 s | verified; original `[4]`, inspected `[4,2]`, recovered `[2]`, supporting `[4]` | failed verification; original/inspected `[8]`, recovered/supporting `[]` |
| `step2-bigcommerce-narrow-v3` | 6 | 50,387 / 3,662 / 54,049 | $0.006871 | 61.428 s | verified; original `[4]`, inspected `[4,2]`, recovered `[2]`, supporting `[4,2]` | failed verification; original/inspected `[8]`, recovered/supporting `[]` |

The v3 extra supporting page 2 is report-level methodology context from the
model; the authoritative wallet binding remains page 4 and was not promoted
from page 2. The valid claim’s final wording remained source-grounded and
qualified the result as checkout friction rather than causation or the main
driver.

The stored v1 result still fails the provider-free adversarial comparator with
one expected historical mismatch (`BIG-ADV-002` was recorded as verified). The
stored v4 result has the correct 8-verified/1-failed terminal outcomes, but its
rejected attempts retain pre-correction supporting page-8 fields, so the new
serialized-attempt comparator reports the historical metadata mismatch. An
in-memory normalization of those rejected-attempt fields passes **9/9** with
8 verified and 1 failed. The stored v1/v4 files remain unchanged; no new
nine-case provider replay was claimed.

The affected visual, provenance, replay, adversarial and split-case suite
passed **279 tests**, with 1 expected integration skip and 1 deselected; the
prompt regression batch passed **78 tests**. Step 2 remains **PARTIAL**: this
correction establishes the BigCommerce strict-page boundary and actual-PDF
behavior, but does not prove fresh Step 1 selection effectiveness,
repeated-run stability or independent editorial approval. E18 remains Active
and Step 3 remains unstarted.

### Phase 2 — Restore Luna semantic authority — 2026-10-20

The visual verifier no longer applies deterministic lexical or native-text
semantic vetoes to a claim that GPT-6 Luna High has corrected and verified.
The removed helpers and terminal diagnostic paths were
`_strict_source_page_mismatch_diagnostics`, `_strict_direction_diagnostics`,
and `_supporting_page_attribution_diagnostics`; `_source_truth_notes_present`
now checks only the structural presence of non-empty notes. Luna remains the
semantic authority for whether the final corrected claim is factually supported,
preserves the relevant population/metric/timeframe/forecast relationship, and
has a defensible analytical interpretation. Production still hard-fails on
malformed or incomplete contracts, source-hash/source-identity conflicts,
ambiguous physical bindings, invalid pages/spans, and authoritative metric
conflicts. Correction and verification remain separate and bounded at two
attempts each.

The replay adapter now defers the four native-text quality rules
(`unsupported_numeric_claim`, `metric_label_relationship`,
`temporal_integrity`, and `incomplete_numeric_expression`) for visually
verified rows that have no authoritative retained metric binding. Mechanical
quality blockers and exact retained metric-binding conflicts remain hard
failures. The adversarial comparator independently checks serialized attempts,
source pages, page notes, hashes, and terminal outcomes; its only bounded
correction-only exception is a two-attempt, typed `correction_unresolved`
abstention with no final claim or support metadata.

#### Exact frozen-five live replay

The fresh canonical replay is
`tmp/verified-claims-step2-phase2-luna-20261020-v5/result.json`. It used the
exact frozen five reports, exact local PDFs, GPT-6 Luna High with high
reasoning, and shadow-only inputs:

| Report | Reference variants | Reference outcome | Real retained insights | Real outcome |
|---|---:|---|---:|---|
| Capgemini Research Institute | 9 | 9 verified | 5 | 5 verified |
| Activate | 11 | 10 verified, 1 unresolved (`ACT-004-wrong-page`) | 7 | 7 verified |
| KPMG | 7 | 7 verified | 5 | 5 verified |
| Reuters Institute | 8 | 8 verified | 6 | 6 verified |
| Adjust | 4 | 4 verified | 6 | 6 verified |
| **Total** | **39** | **38 verified, 1 expected unresolved** | **29** | **29 verified** |

All 39 reference outcomes matched their frozen expected classifications, with
zero false accepts and zero false rejects. Every real retained ID was evaluated
and retained; all 29 were verified first pass. The run made **136 provider
calls**, used **2,249,156 input tokens**, **83,324 output tokens**,
**2,332,480 total tokens**, cost **$0.266580 estimated**, rendered **107
pages**, and took **1,242.403 seconds**. The run ledger had 136 selected
rows; image-response caching was enabled, but measured cache reuse was false.
All 68 rows remained `canonical_approval_status: not_approved`.

The final-claim review covered the corrected outputs and their actual PDF page
bindings. `KPM-002-quantified-mutation` now accepts the source-supported
qualitative portfolio-reconfiguration/value-creation thesis on pages 12–13,
without preserving the unsupported 20% realized-outcome claim. The exact
seven-variant KPMG rerun independently produced **7/7 verified**, including
KPM-002, with 14 calls, 120,996 total tokens, and $0.013962 estimated cost.
`ADJ-001-unsupported-metric` is accepted only after replacing churn/conversion
labels with the page-19 install/session metrics (strategy sessions +57% YoY,
casino installs +22%, slots sessions −5%). `ACT-004-wrong-page` remains
unresolved after two correction attempts and has no final support pages. The
BigCommerce adversarial wrong-page case likewise remained unresolved in the
corrected v2 replay: **8 verified / 1 unresolved**, 18 provider calls,
224,598 total tokens, $0.025157 estimated, 136.169 seconds; the corrected
comparator recheck passed **9/9**.

The v5 results are better than the preceding v3 snapshot on the observed
reference gate (two KPMG reference semantic/provider mixed mismatches in v3
versus only the expected Activate wrong-page abstention in v5) and on the
observed real retry distribution (29 first-pass verified versus 25 first-pass
and 4 retry successes). These are provider/model-run observations, not a
claim of improved live Step 1 selection effectiveness. The final replay also
preserved report-specific source identity, physical-page arrays, evidence IDs
and retained spans; the provider-free hash check confirms all five expected
PDF SHA-256 values. No canonical artifact, metric-spine mutation, publication
readiness transition, or WordPress write occurred.

Shadow replacement selection remains only partially measurable: the retained
artifact/editorial-plan path produced complete replacement rows for Capgemini,
KPMG, and Reuters, but no candidate rows for Activate or Adjust. This is an
input/artifact limitation, not evidence that those reports lacked useful
replacements. Manual review of the final KPM-002, ADJ-001, ACT-004, BigCommerce
strict-page, and representative Capgemini/Reuters rows found no independently
confirmed unsupported material claim marked verified; it is not a substitute
for fresh editorial sign-off or a new Step 1 generation.

#### Provider-free and local verification

`python scripts/quality/replay_verified_claims_step2.py --provider-free
--output tmp/verified-claims-step2-phase2-provider-free-20261020/result.json`
passed with **15 cases / 39 variants**, all **29 retained IDs**, all five
expected/actual PDF hashes matching, and `fabricated_fixture_substitution:
false`. It deliberately makes no semantic/provider-quality claim. The focused
affected suite passed **82 tests** with **1 deselected**; prompt/routing tests
passed **95**; the prompt fixture regression gate passed after recording the
measured validation-prompt delta of **+1,310 tokens / +$0.000131**. Ruff and
compile checks passed. The complete repository gate remains subject to the
previously documented CPython 3.14 wheelhouse limitation and is not claimed
green here.

This phase restores model authority for semantic truth while preserving
contract, provenance, retry, and shadow-only safeguards. Step 2 remains
**PARTIAL**: live provider variance, incomplete retained source bindings,
limited replacement-path coverage, and independent editorial approval remain
open. Step 3 has not started.

### Final Phase 2 corrections — 2026-10-20

Baseline: `30b6070ad758f515c180441f0c4eed8eea70f769`. The hosted failure was
the existing 1,000-line ownership gate: `cases_02_visual.py` had 1,072 lines.
The coherent semantic-authority and wrong-page tests were moved to
`cases_03_visual.py`; the entrypoint imports both modules, all 21 original test
symbols remain present exactly once, and the resulting modules are 507 and 572
lines. The threshold and its policy were unchanged.

The adversarial comparator now has two mutually distinct negative categories.
An independently verified rejection requires a completed, source-grounded
verification rejection with a valid attempt trail and retained binding. A safe
correction-stage abstention requires exactly two ordered unresolved correction
attempts with nonempty issue details, no typed provider/malformed failure, no
verification trail, and empty final/support metadata; it is non-acceptance, not
independent factual rejection. Strict `BIG-ADV-002` page-8/original-page,
inspected-page, recovery and page-4 rescue checks execute before correction-only
early exits. The nine-case provider-free result-shaped comparator passed 9/9:
one independently verified rejection (`big-adv-wrong-page`) and zero safe
abstentions in that corpus. Focused synthetic regressions cover the safe path,
malformed/provider corrections, strict page-4 recovery, and category separation.

The replay quality adapter no longer treats any retained `metric` field as
factual authority. Visually verified rows keep the four native-source rules
(`unsupported_numeric_claim`, `metric_label_relationship`,
`temporal_integrity`, and `incomplete_numeric_expression`) pending/advisory;
unverified rows still block, and structural/provenance/mechanical blockers are
unchanged. Verified replacement inputs continue to omit the retained metric
object. The correction and verification prompt examples were generalized to
same-subject direction, causal/metric-condition preservation, qualitative
narrowing, and explicit report-level replacement policy; publisher-specific
wallet/checkout and portfolio examples were removed.

Verification on this correction used no provider or publication calls. The
provider-free replay
`out/verified_claims_step2_provider_free_final_phase2_20261020/report.json`
confirmed 15 source cases, 39 variants, all 29 retained IDs across
Capgemini/Activate/KPMG/Reuters Institute/Adjust, all five expected PDF hashes,
five report theme sets (5/7/5/6/6), and
`fabricated_fixture_substitution: false`. Compared with the retained replay
baseline, selected IDs, theme coverage, source identities, and physical-page
inputs were unchanged; this replay does not evaluate Luna correction quality.
The affected visual/replay/adversarial suite passed **229 tests**, with **1
expected integration skip** and **1 deselected**; the focused comparator/replay/
visual suite passed **83**, with **1 deselected**. The long-test-file ownership
test passed 2/2, formatting, Ruff, compile, and the three-iteration prompt
fixture gate passed. The prompt gate measured 105,296 current corpus tokens
versus 104,024 baseline (+1,272; +$0.000127), within the existing allowlist;
no baseline or threshold changed. Hosted CI [run 39483813670](https://github.com/mbrakker/marketlense/actions/runs/39483813670)
for implementation commit `c8082e3a764b07f78d9dc21ead26ae8baa2e59ce`
completed successfully: the Python 3.12 tests/coverage job, both mutation
partitions, and the release-evidence bundle passed. The optional WordPress
staging REST check was skipped by configuration. This confirms repository
gates, not fresh Luna semantic quality.

No new live semantic result, token/cost/latency measurement, canonical
promotion, publication-readiness change, or WordPress write is claimed. Step 2
remains **PARTIAL**, E18 remains Active, and Step 3 remains unstarted pending
fresh selection-effectiveness evidence and independent editorial approval.

### Final provenance fix and targeted live regression — 2026-10-20

Commit `27b09ed2` fixes the remaining strict supporting-page validation defect
at the replay/adversarial comparison boundary. `_valid_supporting_pages()` no
longer filters malformed list elements into a seemingly valid subset; it now
reuses the existing strict physical-page validator. The complete list must be
nonempty, unique, positive, and composed of actual integers (booleans are
rejected), every page must be inspected, and the existing exact page-note
validation remains in force. Because the adversarial comparator uses this same
boundary, identical malformed result and verification-attempt lists now fail
closed. Valid inspected multi-page bindings and existing recovery/negative
handling remain unchanged.

Focused red/green regressions covered `[3, "invalid"]`, `[3, true]`, `[3, 0]`,
duplicate pages, an uninspected page in `[3, 4]`, a valid inspected `[3, 4]`
binding, and malformed result/verification-attempt lists. The focused
visual/replay/adversarial/provenance suite passed **123 tests**, with **1
expected integration skip** and **1 deselected**. Formatting, Ruff, compile,
backlog, documentation, repository-hygiene, forbidden-patching and the full
repository mypy gate passed. No semantic veto or false metric authority was
reintroduced.

#### Five-case actual-PDF GPT-6 Luna High regression

The isolated regression used the current correction and verification prompts,
`gpt-6-luna` with high reasoning, complete pages, the four hash-matched local
PDFs, and a fresh cache at
`out/verified_claims_step2_phase2_final_live_20261020/cache`.
The source-manifest SHA-256 is
`64bbeb67351864bd47f1cb0ba2142e367d2dbc2271a709f7370c1bfeb89302c`.
Prompt identities were recorded in the cost ledger:
`report_vs/validate/visual_claim_correction` hash
`7072823e732c280109b008e744c18dfa67e57af967ac9352facc23d046cfbe97` and
`report_vs/validate/visual_claim_verification` hash
`68de26cfbf4f5dfe60989b83671d25a52ab5ddb1c34b0ff979cebd727a9279d3`.
All actual PDF hashes matched their manifest identities; cache reuse was
measured as false. The run was shadow-only and made no canonical, readiness,
publication, or WordPress writes.

| Case | Terminal result | Source-grounded review |
|---|---|---|
| `BIG-ADV-002` / `big-adv-wrong-page` | **unresolved** after two correction attempts | Page 8 supports guest-checkout/email requirements, not the preferred-wallet 40% finding on page 4; strict policy did not rescue the claim. |
| `BIG-VALID-001` / `big-valid-wallet-page` | **verified, first pass** | Page 4 supports the self-reported 40% preferred-wallet cart-abandonment finding; no broader causal or denominator claim was added. |
| `KPM-002-quantified-mutation` | **verified, first pass** | The unsupported 20% realized-outcome claim was replaced with a same-subject, page-12-supported current-approach comparison (56% corporates; 71% private equity). This is a valid source-supported quantitative replacement; the prior retained baseline produced a qualitative page-13 wording, so this is documented model wording variance rather than treated as an identical editorial output. |
| `ADJ-001-unsupported-metric` | **verified, first pass** | Page 19 supports installs/sessions, not churn/conversion: strategy sessions +57% with installs −1%, casino installs +22% with sessions −5%, and slots installs +46% with sessions −5%, for global 2024–2025. |
| `ACT-004` / `ACT-004-wrong-page` | **unresolved** after two correction attempts | Page 15 is the U.S. video time/spend cohort, not the global creator/platform visual; no silent fallback to page 53 occurred. |

The five terminal outcomes are mutually exclusive: **3 verified first pass,
0 verified after retry, 2 unresolved, 0 failed, 0 skipped**. The labeled
acceptance comparator matched **5/5** with **0 mismatches**. The two negative
cases were safe correction-stage abstentions, not independently completed
verification rejections; neither was accepted. The run made **10 provider
calls**, used **103,935 input**, **4,493 output**, and **108,428 total tokens**,
with estimated cost **$0.012639** and wall time **89.771 seconds**. It rendered
**7 full pages** and recorded run ID
`verified-claims-step2-explicit-1792527626`.

Compared with retained prior evidence, the valid BigCommerce page-4 case
remained verified and the Activate wrong-page case remained unresolved. The
historical BigCommerce page-8 replay that had accepted guest-checkout evidence
is now represented by the current unresolved result; no page-4 wallet evidence
was promoted into the strict row. Adjust remained source-grounded after the
unsupported metric replacement. KPMG remained source-grounded but its current
run chose a quantitative current-approach chart on page 12 instead of the
previous qualitative page-13 wording. These are targeted actual-PDF results,
not a claim that Step 1 live selection effectiveness or overall editorial
quality has improved.

Step 2 remains **PARTIAL**: the strict provenance fix and targeted live cases
pass, but the five-case run is not the full 29-claim frozen-five semantic
evaluation, and independent editorial approval, repeated live stability, and
Step 3 visual factualisation remain open. E18 remains Active and Step 3 is
unstarted.

### KPMG semantic continuity review — 2026-10-20

The prior five-case KPMG row requires a policy distinction. Its retained input
used `report_level_replacement_allowed`, not `strict_original_direction`. The
reported correction — “KPMG’s comparison of current portfolio-separation
approaches shows that 56% of corporates (32% open to but not actively seeking,
24% actively pursuing) and 71% of private equity (46% and 25%, respectively)
fall into one of those two categories.” — is factually supported by the full
physical page 12 chart: 32% + 24% = 56% for corporate organizations and 46% +
25% = 71% for private equity. The chart measures current approach categories,
not realized value creation, and the values are not unsupported.

It is nevertheless a different proposition from the KPM-002 reference
direction: portfolio separation and carve-outs as qualitative structural
mechanisms for portfolio reconfiguration and value creation/execution. Under
strict policy, the 56%/71% current-approach distribution would be a neighboring
quantitative proposition rather than the required same-subject qualitative
narrowing. Because the prior row explicitly allowed report-level replacement,
this is a fixture-policy mismatch in the targeted regression, not evidence of a
strict-policy production failure.

#### Fresh strict-policy KPMG replay

A fresh isolated one-case replay used the exact KPMG PDF
(`a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589`), full
physical pages 12–13, current GPT-6 Luna High prompts, and
`strict_original_direction`. The source-manifest SHA-256 was
`64bbeb67351864bd47f1cb0ba2142e367d2dbc2271a709f7370c1bfeb89302c`; cache
reuse was false. The exact corrected claim was:

> KPMG says organizations are increasingly willing to separate assets that no longer align with long-term growth priorities, as portfolio-level strategic decisions replace incremental asset-level optimization; the page does not report a 20% realized value-creation outcome.

The correction retained the qualitative portfolio-separation direction and
removed the unsupported realized-outcome percentage. The independent verifier
explicitly confirmed the page-12 strategic-direction text and distinguished the
chart’s corporate **20% “Holding due to strategic focus”** category from a
realized value-creation outcome. Supporting physical page **12** was retained;
page 13 was inspected as context but not cited as necessary support. The
The authoritative source identity and PDF hash remained unchanged:
`KPMG|pdf-sha256:a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589`.
The Step 0 identity resolution for KPM-002 is `partial_doc_map_only`:
`canonical_evidence_ids` and `persisted_findings_ids` are empty, `KPMG-2` is a
source-reference ID, `strategic-focus-in-a-fragmented-world` is contextual
DocMap metadata, and `strategic-focus-capability-building` is an editorial ID.
The string `portfolio-separation-qualitative-thesis` occurs only in the
isolated replay's retained `artifacts.json`; that replay snapshot has empty
`findings.json` and `doc_map.json`. It is therefore a retained
replay/evidence-span label, not canonical persisted evidence, a
source-reference ID, or a DocMap ID, and it was not promoted.

The strict run produced **1 verified first-pass outcome**, **2 provider calls**,
**26,908 total tokens**, estimated cost **$0.003630**, **31.097 seconds**, and
**2 rendered pages**. The correction and verification prompt hashes were the
current recorded hashes `7072823e732c280109b008e744c18dfa67e57af967ac9352facc23d046cfbe97`
and `68de26cfbf4f5dfe60989b83671d25a52ab5ddb1c34b0ff979cebd727a9279d3`.
The provider-free acceptance comparator matched **1/1**; no canonical,
publication-readiness, or WordPress write occurred. The focused visual/replay/
adversarial/provenance suite remained **123 passed, 1 skipped, 1 deselected**.

Assessment: factual accuracy **PASS**; strict analytical continuity **PASS**;
deterministic provenance **PASS**; editorial quality **acceptable for shadow
verification but not canonical approval**, because the model included an
explicit explanation of what the original page did not report. No production
prompt or code correction is justified by the evidence. The existing
report-level replacement behavior remains intentionally flexible, while the
strict prompt and verifier preserve the qualitative narrowing boundary. Step 2
remains **PARTIAL**, E18 remains Active, and Step 3 remains unstarted.

### Complete Step 2 acceptance review — 2026-10-20

This acceptance review uses the current branch at
`ef962589bcb0aaf49a4275eaa1df6b01c7764cb0` and the latest retained,
hash-bound replay artifacts. No production code, prompt, canonical artifact,
publication-readiness state, or WordPress write was changed for this review.
The KPMG correction above is a provenance/documentation classification fix:
the replay label is not promoted as canonical evidence.

#### Gate matrix

| Gate | Status | Evidence and limitation |
|---|---|---|
| Source identity and PDF hash | **PASS** | The frozen-five manifest `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7` and all five source hashes matched in the v5 replay; the additional-five replay also matched all five hashes. |
| Physical-page safety (automated) | **PASS** | Wrong-page reference/adversarial cases remained unresolved or failed closed; valid multi-page cases survived. This is an automated safety result, not independent approval of every retained binding. |
| Reference factual/semantic gate | **PASS** | All 39 reference variants matched their expected terminal classification: 38 verified first pass and `ACT-004-wrong-page` unresolved, with zero false accepts or false rejects. The result is a regression gate, not a human adjudication. |
| Real-claim terminal verification | **PASS** | The v5 replay recorded 29/29 retained real insights as terminal verified first pass; terminal verification is distinct from independent factual correctness. |
| Additional-five terminal verification | **PASS** | 24/24 eligible selected claims verified first pass and one Merchant Risk Council claim was unavailable because no safe physical page or stronger alternative existed; no failed or unresolved eligible rows. |
| Independent correction/verification contract | **PASS** | Correction and verification remained separate bounded calls, with no more than two attempts each; malformed, contradictory, wrong-page, and permanent-failure paths remain fail-closed. This is not P6 human review. |
| Negative safety and abstention | **PASS** | The current adversarial comparator recheck passed 9/9: eight verified outcomes and `BIG-ADV-002` unresolved through safe correction-stage abstention; no unsupported material claim was independently confirmed as verified. The immutable raw result retains an earlier stale embedded `passed: false` field from the pre-comparator state and was not overwritten. |
| Replacement-policy correctness | **PASS** | The KPMG strict replay was 1/1 verified with the same-subject qualitative correction; the earlier 56%/71% result is retained only as a report-level replacement-policy result, not a strict-direction result. |
| Canonical evidence provenance | **BLOCKED** | Step 0 still has partial/unresolved direct bindings, and KPM-002 has no canonical evidence ID. Retained/provisional replay labels and pages were not promoted. |
| Fresh shortlist quality and recall | **BLOCKED** | The retained Step 2 inputs contain post-selection artifacts only; raw pre-selector pools, fidelity decisions, and editorial-plan candidate alternatives are unavailable, so fresh selection effectiveness cannot be measured. |
| Editorial quality | **BLOCKED** | The replay contains source-grounded corrections and useful commercial interpretations, but P6 has no independent reviewer decision for these 29 claims. Near-duplicate propositions remain visible for human review rather than being silently removed. |
| Repeatability/autonomy | **BLOCKED** | Provider-free replay is reproducible, but no current-HEAD three-run generation/validator repeatability cohort is retained; E18 remains Active. |
| Regression and operational safety | **PASS** | No canonical promotion, publication, readiness mutation, or WordPress write occurred; retained IDs, source hashes, bounded retries, and downstream schemas remained intact in the replay gates. |

The overall acceptance status is therefore **BLOCKED/PARTIAL**, not PASS:
automated factual, provenance-safety, negative, retry, and regression gates are
green, while canonical-source completeness, fresh Step 1 evidence, repeatability,
and independent editorial acceptance remain open.

#### Frozen-five and additional-five measurements

The latest frozen-five v5 result evaluated all **15 cases / 39 reference
variants** and all **29 real retained insights**. Reference outcomes were **38
verified first pass and 1 unresolved**, with **0 false accepts/rejects**. Real
terminal outcomes were **29 verified first pass, 0 retry, 0 unresolved, 0
failed, and 0 skipped**. The run made **136 provider calls**, used **2,332,480
total tokens** (2,249,156 input and 83,324 output), estimated cost
**$0.266580**, and rendered **107 full pages**; cache reuse was false and no
writes occurred. The five source identities were hash-matched and every row
remained `canonical_approval_status: not_approved`.

The latest explicit additional-five v3 replay selected **25** identities,
evaluated **24** eligible claims, verified **24 first pass**, and marked **1
unavailable** (Merchant Risk Council); it had **0 retry, failed, unresolved, or
skipped** eligible outcomes. It made **48 provider calls**, used **983,544 total
tokens**, estimated cost **$0.109730**, rendered **18 full pages**, and took
**634.004 seconds**. Its provisional exact-page inspections remain inspection
context only and are not canonical evidence.

The KPMG strict one-case replay remains **1/1 verified first pass**, with two
provider calls, 26,908 total tokens, estimated cost $0.003630, 31.097 seconds,
and page 12 as the necessary supporting page. The source hash passed; the
replay evidence ID was not canonical and was not promoted.

#### Adversarial and repeatability interpretation

The nine-case actual-PDF adversarial result is immutable at
`tmp/verified-claims-step2-phase2-adversarial-20261020-v2/result.json`. Its
terminal rows are eight verified and one unresolved (`BIG-ADV-002`). The
embedded acceptance field was produced by an older comparator and is false
because it required a verification attempt for the safe correction-stage
abstention. Re-running the current comparator against that unchanged result and
corpus returns **9/9 matched**, with the same eight verified rows and one
bounded unresolved abstention. This correction is reported rather than written
back into the immutable raw artifact.

No retained input contains the raw Step 1 candidate pool or three independent
current-HEAD runs. Consequently this review does not claim improved live
shortlist recall, collision prevalence, or repeated-run stability from
post-selection replay alone.

#### Hash-bound P6 review packet

The smallest review packet is the v5 `result.json` plus its manifest SHA
(`744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`), the
five frozen source PDFs and their recorded SHA-256 values, and the 29 claim
rows containing stable ID, original claim, final corrected claim, inspected and
supporting physical pages, evidence identity, and terminal verification
explanation. The additional-five and adversarial result paths above are
separate regression supplements. No reviewer identity or approval is invented:
P6 remains **Active** and its human-review tables remain open.

#### Decision

**Step 2: PARTIAL — implementation and automated regression gates pass; full
acceptance is blocked.** The evidence supports retaining the current shadow-only
implementation and does not support Step 3. The minimum remaining acceptance
work is an attributed independent review of the 29 final claims against the
hash-bound PDFs, a fresh run retaining pre-selector evidence, and the E18
three-run repeatability baseline. Step 1 remains **PARTIAL**, E18 and P6 remain
**Active**, and Step 3 remains **unstarted**.

### Independent LLM editorial acceptance review — 2026-10-21

The missing independent review was completed as a separate, immutable,
shadow-only acceptance artifact. It reviewed the final corrected claim from the
retained Step 2 result against complete original PDF pages, report context, and
source identity/page mapping. The review prompt did not receive the prior
verifier verdict, verification rationale, quality score, or correction history;
it assessed factual fidelity, analytical validity, specificity, commercial
relevance, editorial quality, and selection quality independently. No wording,
evidence binding, canonical artifact, readiness state, or publication output was
mutated.

The authoritative review manifest is retained locally at
`out/verified-claims-step2-editorial-review-20261021-v2/manifest.json` with
SHA-256
`53c55f2af0cc96bb2d1c2e181ba2208d371bf2330b6f1994b32d7546a07b6b0b`. It binds
the two input result/manifests, all ten expected PDF hashes, the reviewer model
and reasoning policy, prompt hash
`8e80f044ee5c4f38152ce9777b3e212f28254b5a09414fe55e1ae8cb52d71cee`, every
original/final claim, stable ID, evidence identity, physical page list,
decision, dimension assessment, source-grounded explanation, and page-specific
diagnostics. All ten source hashes matched; no source-identity or page-render
failure occurred.

#### Review ledger

| Cohort/report | Reviewed records | Decisions | Supporting physical pages cited |
|---|---:|---|---|
| Frozen / Capgemini Research Institute | 5 | 5 approved | 4, 6, 9, 35, 36, 45 |
| Frozen / Activate | 7 | 7 approved | 4, 5, 14, 15, 26, 53, 96, 115, 136 |
| Frozen / KPMG | 5 | 5 approved | 6, 11, 15, 17, 19, 21, 26, 33 |
| Frozen / Reuters Institute | 6 | 6 approved | 12, 15, 18, 30, 36, 39 |
| Frozen / Adjust | 6 | 6 approved | 9, 11, 13, 17, 19, 27–30, 34–38 |
| Additional / DoubleVerify | 5 | 5 approved | 3, 4, 9, 10 |
| Additional / Merchant Risk Council | 5 | 4 approved, 1 unresolved/unavailable | 2 for the four eligible claims |
| Additional / Algolia | 5 | 5 approved | 5, 12, 26, 27 |
| Additional / Bain & Company | 5 | 4 approved, 1 revision_required | 1 |
| Additional / Bigcommerce | 5 | 5 approved | 4, 5, 7, 8 |

The frozen-five set therefore has **29/29 approved**. The additional-five set
has **24/24 eligible records reviewed**: **23 approved** and **1
revision_required**; the 25th selected identity is the pre-existing Merchant
Risk Council `post-purchase-fraud-section-scope` item with no safe page binding,
and remains explicitly unresolved without a review call. Across the visible
54-record denominator the decisions are **52 approved, 1 revision_required,
and 1 unresolved**; there are no failed or skipped review invocations.

The dimension results were: factual fidelity 52 strong / 1 material_issue;
analytical validity 52 strong / 1 adequate; specificity 52 strong / 1
minor_issue; commercial relevance 50 strong / 3 adequate; editorial quality
51 strong / 2 adequate; and selection quality 53 strong. The sole material
flag is the Bain `market-growth-share-breakdown` review. The reviewer read
“top 20 gainers across sectors” as potentially ambiguous against the chart
label “top 20 gainers per sector.” Direct inspection of the hash-matched PDF
page 1 shows that the source itself contains both the exact headline wording
used by the final claim (“top 20 gainers across sectors”) and the chart note
“top 20 gainers per sector.” The final claim is therefore source-consistent;
the reviewer flag is retained as an adversarial editorial diagnostic, not
confirmed as a production factual defect. No automatic suggested correction was
promoted.

#### Measured execution and comparison

The corrected review used **53 GPT-6 Luna High calls**, **1,309,714 input
tokens**, **57,364 output tokens**, **1,367,078 total tokens**, estimated cost
**$0.159650**, **804.018 seconds** wall time, **119 rendered full pages**, and
zero observed cache reuse. The initial review pass was deliberately not used as
the acceptance result: its inherited 2,048-token limit truncated two JSON
responses and its reviewer-side gate skipped three provisional-recovery rows.
The v2 pass raised only this new review namespace to 4,096 output tokens,
re-reviewed all 53 eligible records, allowed existing `provisional_recovered`
pages as inspection context without promotion, and produced complete responses.
The first pass was 46 approved / 1 revision_required / 7 unresolved; the
corrected acceptance pass is 52 / 1 / 1. The MRC unavailable row remained
unresolved in both passes. No retry was added; the review namespace retains
`provider_retry_count: 0`.

The existing frozen-five technical result remains the independent corrected
claim gate for all **15 reference cases / 39 variants**: **39/39 expected
classifications matched**, with 38 verified first pass and
`ACT-004-wrong-page` unresolved, and the 29 real retained claims were **29/29
verified first pass**. The independent review did not replace that comparator
or rewrite its raw result. The separate immutable adversarial acceptance record
is at
`out/verified-claims-step2-acceptance-20261021/adversarial-acceptance.json`,
SHA-256
`be6c681097397fc1ea7de5c6d9b0189eec1d938ed3ff333fca45bd2ecbee7d29`; it binds
the original corpus/result/comparator hashes, matches **9/9**, records eight
verified cases and one safe wrong-page abstention, and explicitly records
`canonical_mutation: false` and `publication_write: false`. The original raw
adversarial result was not overwritten and no second comparator was introduced.

#### Acceptance decision

The independent editorial review is **complete for the available retained
claims**, with no independently confirmed unsupported material claim approved;
the one reviewer material flag is source-consistent on manual PDF adjudication,
and the one unresolved record is a known unavailable binding rather than a
silent approval. The technical Step 2 implementation and its existing 39-case,
provenance, retry, and shadow-write gates remain **PASS** within scope.

Overall Step 2 remains **PARTIAL/BLOCKED**, not a canonical release approval:
Step 0 still contains partial/unresolved canonical direct bindings, the retained
inputs still lack raw pre-selector pools and a current-HEAD three-run selection
baseline, E18 remains Active, and P6 human acceptance remains Active. Step 3 is
therefore **NO-GO** and unstarted. This review demonstrates retained-artifact
editorial quality evidence; it does not claim fresh live shortlist recall,
repeatability, canonical claim promotion, publication readiness, or WordPress
writes.

### Editorial acceptance integrity correction — 2026-10-21

The acceptance boundary was corrected after the first independent review. The
review payload validator now separates structural validity from decision
consistency: malformed or incomplete responses are unresolved, while an
`approved` response containing an unresolved dimension, material dimension
rating, or material defect is an unresolved `review_decision_conflict`, not a
fabricated rejection. Adequate and minor findings remain eligible. Material
defect counts are claim-level counts. Approved responses also require a
substantive source-grounded explanation and complete page-specific notes.

The exact-cohort ledger now validates the 29 frozen-five identities and the 25
additional-five identities (24 eligible plus the explicit Merchant Risk Council
unavailable row) before provider calls. The frozen result also contains 39
reference variants; those are recorded as an independent out-of-scope reference
set rather than being silently treated as unknown selected claims. Missing,
duplicate, unknown, wrong-report, wrong-cohort, and incorrectly classified rows
block coverage. The written manifest carries separate `execution_status`,
`coverage_status`, `editorial_acceptance_status`, and reason fields; a non-PASS
manifest is still written for audit and the CLI exits nonzero afterward.

The review request now receives only neutral report metadata and scope. It does
not read retained generated summaries, topics, findings, or upstream answer
content. `selection_quality` is explicitly limited to individual-insight fit;
report-level recall, theme coverage, and duplicate suppression remain Step 1/E18
questions. The source-record loader also accepts the retained
`sha256_expected` source-ledger form and recomputes the actual PDF hash before
rendering.

#### Exact-cohort review comparison

The raw fresh review is retained at
`out/verified-claims-step2-editorial-review-20261021-v3/manifest.json`, SHA-256
`0ca7df70987eef9d7d65ff4dd76aa9e06fdd12839886610246925c951436e28a`. It made
53 GPT-6 Luna High calls, used 1,242,224 input tokens and 57,203 output tokens
(1,299,427 total), cost an estimated `$0.152829`, took 742.780 seconds, rendered
119 full pages, and observed zero cache reuse. A deterministic reconciliation of
the same terminal rows after the identity fix is retained at
`out/verified-claims-step2-editorial-review-20261021-v3-corrected/manifest.json`,
SHA-256 `b1dbc93228c7b65d7ed19b01a694c2ad8dc68532fb66dfc10d6f3166adf4561e`.
It made no provider calls and did not change any claim or review row.

| Cohort/report | v2 baseline | Fresh v3 review | Observed change |
|---|---:|---:|---|
| Frozen / Capgemini Research Institute | 5 approved | 5 approved | No decision change. |
| Frozen / Activate | 7 approved | 6 approved, 1 revision-required | `activate-ecommerce-capability-stack` omitted the PDF's exclusion of travel and tickets. |
| Frozen / KPMG | 5 approved | 5 approved | No decision change. |
| Frozen / Reuters Institute | 6 approved | 6 approved | Two supporting-page lists changed; one is an evidence defect noted below. |
| Frozen / Adjust | 6 approved | 6 approved | Finance supporting pages narrowed from 34-38 to 35-38; page 34 is required for the global install/session values, so this review row is held for evidence completeness. |
| Additional / DoubleVerify | 5 approved | 5 approved | No decision change. |
| Additional / Merchant Risk Council | 4 approved, 1 unavailable | 4 approved, 1 unavailable | Explicit unavailable identity preserved. |
| Additional / Algolia | 5 approved | 5 approved | No decision change. |
| Additional / Bain & Company | 4 approved, 1 revision-required | 3 approved, 2 revision-required | `cloud-platform-catalysts` received the same defensible scope warning as `market-growth-share-breakdown`. |
| Additional / Bigcommerce | 5 approved | 4 approved, 1 revision-required | `guest-checkout-abandonment` omitted the Digital Natives population. |

The exact identities remained **29 frozen plus 25 additional = 54 rows**. The
model terminal decisions changed from **52 approved / 1 revision-required / 1
unresolved** in v2 to **49 approved / 4 revision-required / 1 unresolved** in
v3. The corrected acceptance status is `execution_status=PASS`,
`coverage_status=PASS`, and `editorial_acceptance_status=PARTIAL`; the only
unresolved row is the known unavailable MRC binding. There were no failed or
skipped review calls. The four material review flags are the three genuine
scope/population issues above plus the existing Bain market-scope warning.
Original claims, final wording, stable IDs, evidence IDs/spans, protected
fields, source hashes, and retained source identity were unchanged across v2
and v3. Four reviewer supporting-page lists changed; the model's page lists
are not treated as canonical provenance without the source audit below.

#### Source audit and Bain adjudication

Manual inspection of the hash-matched original PDFs found two fresh-review
evidence-binding defects that remain held rather than promoted. Reuters
`ai-search-platform-relationships` was marked approved with physical page 10,
but the 43% survey, 33%/38% Chartbeat values, and 2,500-site population are on
physical page 12; page 10 is preceding context. Adjust
`finance-benchmark-coverage` was marked approved with pages 35-38, while page
34 contains the global -4% installs / +21% sessions values included in its final
claim. These are independent review-evidence defects, not new source claims;
the final claims remain shadow-only and are not counted as clean editorial
sign-off. This is why the result is not upgraded to PASS.

The Bain page-1 concern was adjudicated separately against the exact PDF hash
without changing the original review decisions. The source contains both the
headline wording "top 20 gainers across sectors" and the chart scope
"top 20 gainers per sector" plus a category-aggregation note. The two review
rows are therefore source-consistent but carry a defensible editorial-scope
warning. The immutable adjudication is
`docs/quality/verified-claims-step2-bain-source-adjudication-20261021.json`
(SHA-256 `934a677e34edd78d628f2204a6eacdda71ffb4b655581d101c22c88be6ee457a`);
it preserves both `revision_required` decisions, records `auto_approval=false`,
and records no canonical or publication mutation.

The retained Step 0 frozen-five technical gate remains independent: all 15
reference cases / 39 variants were evaluated with **39/39 expected outcome
matches**, **38 verified first pass**, one `ACT-004-wrong-page` unresolved, and
zero false accepts or false rejects. No correction or verification replay was
rerun for this acceptance-only correction.

#### Prompt-baseline provenance

The visual correction and verification token increases visible in the committed
baseline were not introduced by the `a1c5510e` editorial-review commit itself.
History shows that the Step 2 visual prompts changed across the preceding
`2e56b17b`, `9d9f5bef`, `92392238`, `964f1d03`, `30b6070a`, and `c8082e3a`
corrections while the corpus snapshot was not refreshed after every change.
`a1c5510e` measured the current 49-fixture corpus, including the new editorial
review namespace, so the visual correction (1,598 tokens) and verification
(1,801 tokens) values reflect an overdue accumulated refresh rather than an
unjustified reset. The current neutral-context/selection-scope wording adds a
measured **+121 validation tokens** (current corpus 106,779 versus baseline
106,658; estimated cost delta `$0.000012`); the prompt regression gate passes.
The time-bounded allowlist records this exact editorial-review delta separately.

#### Decision

This correction is **PARTIAL**, not PASS: structural acceptance accounting,
exact identity coverage, neutral review context, source-hash verification, and
model-review execution are corrected and measured; manual source-page audit
still holds two review rows, Bain scope remains revision-required, and P6 human
acceptance, fresh Step 1 selection evidence, and canonical source-binding
completeness remain open. Step 3 remains **NO-GO/unstarted**. No canonical
promotion, publication-readiness mutation, or WordPress write occurred.

### Final acceptance-integrity correction — 2026-10-21

This correction closes the remaining acceptance-boundary defects without
changing the independent reviewer decision or any canonical artifact. The
editorial record now preserves the retained Step 2
`supporting_physical_pages` and `source_truth_notes_by_page` under separate
`step2_*` fields. A reviewer page-set difference is compared as a set (so
ordering and valid multi-page evidence are preserved), but an approved record
with a different or structurally incomplete set is blocked as
`source_page_reconciliation_required` until an immutable, source-hash- and
review-response-hash-bound adjudication accepts the location. The adjudication
packet is
`docs/quality/verified-claims-step2-page-adjudication-20261021.json` (SHA-256
`e76fcfdc1cec06a45c40949b40e1edfaedfa68f656bddd9c6eabf445480e5b79`).

The frozen-five roster is no longer derived from the result under test. Each
report is now checked against the committed Step 0 reference metadata, its
retained `artifacts.json` SHA-256, and the exact `insights_final[].id` roster.
The provider-free replay therefore detects substitution, wrong-report
assignment, missing/duplicate IDs, malformed artifacts, and hash mismatch;
the exact frozen roster is **29 expected / 29 actual, PASS**. The 39 reference
variants remain a separate regression set and are not added to the 29-row
selected denominator.

#### Provider-free reconciliation ledger

The retained v3 review was reconciled without provider calls at
`out/verified-claims-step2-editorial-review-20261021-v3-reconciled-final/manifest.json`
(SHA-256
`83145be4153ab4e48b57c81a6083ba73cf788fc239f98cb9ee22483b4e0b089d`). It
preserved **54 records**, **49 approved / 4 revision_required / 1 unresolved**,
and `coverage_status=PASS`, `execution_status=PASS`. Three page differences
were accepted after source inspection: Reuters `ai-search-platform-relationships`
→ physical page 12 (reviewer page 10), Reuters
`ai-browsers-adaptable-content` → physical page 41 (reviewer page 39), and
Adjust `finance-benchmark-coverage` → the sufficient smaller set 35–38
(reviewer pages 35–38; Step 2 retained 34–38). The Adjust page 34 context is
not required because physical page 35 contains the global and regional growth
figures. Activate `activate-outlook-revenue-models` remains blocked: physical
page 4 is a contents page, page 6 contains the segment chart, and the retained
review wording reverses the access/paid-content bindings. Page reconciliation
cannot approve that factual error. The reconciled editorial status is therefore
`PARTIAL`, with one source-page block; no reviewer wording, decision, evidence
ID, span, protected field, or stable ID was rewritten.

#### Targeted actual-PDF checks

The targeted GPT-6 Luna High replay used the existing shadow correction and
independent verification boundary. The five disputed/flagged frozen claims
(Activate Outlook and eCommerce, Reuters AI Search and AI Browsers, and Adjust
Finance) used **10 calls**, **357,173 input tokens**, **8,369 output tokens**,
**365,542 total tokens**, estimated cost **$0.039901**, and **188.491 seconds**;
all five were verified first pass. The final claims were preserved in the
targeted report at
`out/verified-claims-step2-targeted-20261021/targeted-report.json` (SHA-256
`6c284ff2e3a75f0fa677d1a9370dd88320e1c7fdc2a8672023d80ff099f0a576`). This
is targeted evidence, not a claim of improved full-cohort live selection.
The actual-PDF check corrected Activate Outlook to the source-supported
segment wording and confirmed Reuters page 12 and Adjust's source-supported
subset. It nevertheless selected physical page 39 for the Reuters browser
claim; direct full-page inspection shows that page 39 is unrelated and page 41
is authoritative, so the adjudication uses page 41 and the model page error is
not promoted.

The explicit Bigcommerce retained-artifact replay evaluated five selected
rows, including `guest-checkout-abandonment`, using **12 calls**, **90,457 input
tokens**, **8,312 output tokens**, **98,769 total tokens**, estimated cost
**$0.013201**, and **136.712 seconds**. It produced **4 first-pass and 1
after-retry verified**, with no failed, unresolved, or skipped terminal rows.
The corrected guest-checkout claim explicitly retains the **Digital Natives**
population and the separate 58% promotional-discount relationship. The
existing v3 editorial row remains `revision_required`; this shadow result does
not mutate acceptance or canonical output. Bain's existing hash-bound
adjudication and both scope warnings remain unchanged; the Merchant Risk
Council row remains unavailable.

#### Final decision

Focused regressions pass (**44 passed** for the editorial acceptance module;
the broader affected Step 2/evidence/regeneration set passes **210 passed, 1
skipped, 1 deselected**), and the changed files pass Ruff formatting and
linting. The implementation is **PASS within this correction scope**: source
page provenance is preserved and reconciled, the frozen identity gate is
independent, valid alternatives remain available, and known conflicting
bindings fail closed. Overall Step 2 remains **PARTIAL / NO-GO for Step 3**:
the Activate Outlook editorial row is still blocked, four editorial rows remain
revision-required (including the known Activate, Bigcommerce, and Bain quality
findings), one retained identity is unavailable, fresh full-cohort selection
effectiveness and P6 human acceptance remain open, and no canonical promotion,
publication-readiness mutation, or WordPress write occurred.

### Review-manifest acceptance-integrity gap closure — 2026-10-21

The final acceptance corrections are limited to deterministic continuity and
coverage checks; correction/verification prompts, the LLM factual boundary, and
all canonical/publication behavior are unchanged. Acceptance now validates the
actual review manifest against the existing exact roster from both cohort
validations: **29 frozen-five + 25 additional-five = 54 identities**, including
the explicit unavailable Merchant Risk Council row. Missing, duplicate,
unexpected, wrong-report, wrong-cohort, availability-mismatched, and malformed
review records block coverage. The 39 reference variants remain accounted for
separately and are not part of the 54-record review denominator.

An accepted page adjudication is now bound to the exact Step 2 and reviewer
page sets recorded when it was created. Page order may differ, but invalid,
missing, or changed sets fail closed; Step 2 and reviewer sets are not required
to equal one another. The three existing accepted adjudications remain valid:
Reuters `ai-search-platform-relationships` (12 versus 10), Reuters
`ai-browsers-adaptable-content` (41 versus 39), and Adjust
`finance-benchmark-coverage` (34–38 versus 35–38). Activate
`activate-outlook-revenue-models` remains held because its rejected
adjudication cannot authorize the materially reversed segment bindings.

Reconciliation also compares each historical review row with its current Step 2
row before reusing the decision: candidate/report identity, exact final claim,
source identity, expected and actual PDF hashes, inspected pages, evidence IDs
and spans, physical-page fields, and binding status. A mismatch is recorded as
`stale_review_source_binding` and blocks editorial acceptance without changing
the historical decision or inventing a new review. Duplicate source rows are
treated as ambiguous rather than silently overwritten.

#### Provider-free before/after ledger

The retained v3 corrected review was reconciled with no provider calls using the
existing result manifests and committed page-adjudication packet. The updated
manifest is
`out/verified-claims-step2-editorial-review-20261021-v4-integrity-2/manifest.json`
(SHA-256
`e790dc58233f32daf413c95c39392a6147954e77732a59acb8deb8cc8d1fe51c`).

| Measure | v3 corrected baseline | v4 integrity reconciliation | Observed change |
|---|---:|---:|---|
| Review records | 54 | 54 | Exact identity set unchanged. |
| Review roster coverage | Not independently checked | 54 expected / 54 actual, PASS | Missing/duplicate/substitution protection added. |
| Decisions | 49 approved / 4 revision-required / 1 unresolved | 49 / 4 / 1 | No historical decision changed. |
| Final claim wording | Unchanged | Unchanged | No stale claim reuse detected. |
| Accepted page adjudications | Not continuity-checked | 3 retained | Reuters/Adjust adjudications remain valid. |
| Editorial acceptance | PARTIAL | PARTIAL | Activate Outlook remains the one page-reconciliation block. |

The 39 reference variants remain **39/39** accounted for in the frozen cohort
metadata. The reconciled record set preserved stable identities, final wording,
source identities/hashes, evidence IDs and spans, protected fields, and all
review decisions; the only deterministic additions are the retained Step 2
page/notes fields and acceptance diagnostics. No provider calls, canonical
mutations, readiness changes, publication writes, or WordPress writes occurred.

Focused acceptance regressions pass (**53 passed**), including missing or
duplicate review identities, the explicit unavailable identity, malformed
records, changed Step 2/reviewer adjudication page sets, valid page reordering,
and stale final-claim rejection. This correction is **PASS within its
deterministic integrity scope**. Overall Step 2 remains **PARTIAL / NO-GO for
Step 3** because the held Activate row, four revision-required editorial rows,
the unavailable retained identity, fresh Step 1 effectiveness evidence, and P6
human acceptance remain unresolved. This provider-free replay does not claim a
live semantic-quality improvement.

### Final factual/editorial quality closure — 2026-10-21

This correction closes two deterministic review-boundary defects while keeping
the shadow architecture unchanged. `_acceptance_summary()` now treats every
eligible record as editorially acceptable only when both `decision` is exactly
`approved` and `editorial_acceptance_status` is exactly `accepted`. Missing,
malformed, unknown, pending, blocked, or contradictory values fail the
editorial gate with candidate-specific diagnostics. An explicit
`availability=unavailable` record remains the documented exception and is
reported separately. The provider-free reconciliation of the immutable v4
manifest produced:

| Measure | Result |
|---|---:|
| Review identities | 54/54, coverage PASS |
| Frozen-five + additional-five | 29 + 25 |
| Decisions | 49 approved / 4 revision-required / 1 unavailable-unresolved |
| Eligible rows with both approval fields | 49/53 eligible records; the unavailable row is excluded from the eligible gate |
| Execution | PASS; 53 provider reviews invoked |
| Editorial acceptance | PARTIAL; 5 eligible rows not accepted |
| Source-page blocks | 1 (`activate-outlook-revenue-models`) |
| Stale source-binding blocks | 0 |

The reconciled manifest is
`out/verified-claims-step2-editorial-review-20261021-v5-reconciled/manifest.json`
(SHA-256 `9e10cf4a20a5a92fa87fcb9e8f912b28e7ddcac6ead295f9f904a20a33b14f1f`).
Its diagnostics explicitly name the four Bain/Bigcommerce/Activate revision
rows, the Activate page reconciliation block, and the expected unavailable
Merchant Risk Council identity. No historical decision, final wording, source
identity, evidence ID, span, protected field, canonical artifact, readiness
state, or publication output was mutated.

#### Physical-page and chart binding correction

The editorial reviewer now returns one-based `supporting_image_indices` and
`source_truth_notes_by_image`; the caller derives physical pages from the
authoritative attachment-to-physical-page map. A reviewer-supplied physical
page field that conflicts with that map fails closed. The historical v8/v9
comparison below used only retained Step 2 support pages; the subsequent full
context correction supersedes that attachment policy and is recorded below.

The final targeted GPT-6 Luna High replay used the exact retained PDFs and no
canonical or publication writes:

| Target set | Calls | Input tokens | Output tokens | Total tokens | Cost | Wall time | Outcome |
|---|---:|---:|---:|---:|---:|---:|---|
| Activate Outlook + Reuters AI browsers (v8) | 2 | 25,265 | 3,300 | 28,565 | $0.004176 | 32.328 s | Activate revision-required; Reuters approved |
| Activate eCommerce, Bigcommerce guest, Bain ×2, Reuters AI search (v9) | 5 | 93,832 | 9,933 | 103,765 | $0.014350 | 103.257 s | 4 revision-required; Reuters approved |
| **Final affected set** | **7** | **119,097** | **13,233** | **132,330** | **$0.018526** | **135.585 s summed** | **2 approved; 5 revision-required** |

The final page ledger is:

| Claim | Final reviewer result | Reviewer physical page(s) | Finding |
|---|---|---:|---|
| `activate-outlook-revenue-models` | revision-required | 5–6 | The PDF binds Internet access to **$128B / 5.7%**, ad revenue to **$108B / 4.7%**, and paid content to **$66B / 2.3%**. The retained claim reverses access and paid content, so it remains held. |
| `ai-browsers-adaptable-content` | approved | 41 | Physical page 41 supports browser capabilities, liquid content, publisher control/measurement concerns, base 265, and 60% + 15% = 75% expected impact. Physical page 39 is not promoted. |
| `ai-search-platform-relationships` | approved | 12 | The final reviewer preserved the page-12 survey/traffic distinction; printed page 10 is not used. |
| `activate-ecommerce-capability-stack` | revision-required | 115 | The reviewer required the source footnote “excluding travel and tickets” to remain in the final claim. |
| `guest-checkout-abandonment` | revision-required | 8 | The reviewer required the Digital Natives population and kept the separate promotional-discount relationship. |
| `market-growth-share-breakdown` | revision-required | 1 | The reviewer required “top 20 gainers per sector” rather than an unqualified top-20 population. |
| `cloud-platform-catalysts` | revision-required | 1 | The reviewer required the same per-sector population and December 31, 2015–2020 measurement scope. |

The v9 review files are
`out/verified-claims-step2-targeted-editorial-20261021-v9/targeted-review.json`
and v8 is
`out/verified-claims-step2-targeted-editorial-20261021-v8/targeted-review.json`.
The earlier v2 run independently surfaced the same eCommerce, guest-checkout,
and Bain qualifier objections; the final v8/v9 run confirms them under the
image-index contract. The explicit MRC unavailable identity remains held rather
than inferred. The existing Adjust finance adjudication remains immutable and
source-hash-bound; no golden expectation was changed.

#### Deterministic and regression verification

The provider-free replay at
`out/verified-claims-step2-final-20261021/provider-free-replay-final.json`
rechecked the exact **15 reference cases / 39 variants**, all five frozen PDF
hashes, the **29** retained insight IDs, and **29/29** report-theme slots. It
used zero provider calls and cannot establish live factual or editorial
quality; the prior live reference gate remains the independent 39-variant
semantic regression. No fabricated fixture substituted for a missing local
source artifact.

Focused verification results:

- Editorial acceptance tests: **65 passed**.
- Visual-generator regression files: **40 passed**.
- Prompt/LLM service gates: **115 passed**.
- Affected artifact, evidence-binding, generation, regeneration, publication-
  quality, and Step 2 tests: **616 passed, 1 skipped, 1 deselected**.
- Split-module regression suites under pytest importlib mode: **458 passed,
  1 skipped**.
- Ruff, compilation, and diff checks passed. The default pytest collection of
  split modules reports the repository's pre-existing duplicate-module import
  mismatch; rerunning those files with `--import-mode=importlib` passed.

One accidental invocation of the live editorial CLI was stopped after two
provider calls because that entry point is not the provider-free reconciliation
command. Those two calls used 47,146 input tokens, 2,331 output tokens, and
$0.005880; they produced no manifest or canonical/publication write and are
excluded from the affected-set measurements above. This is recorded to avoid
claiming that the final replay used no extra provider activity.

#### Final decision

Technical integrity for this correction is **PASS**: eligible editorial
acceptance is fail-closed, physical-page mapping is explicit, wrong Reuters
pages are not cleanly accepted, Activate chart bindings are independently
flagged, and the qualifier regressions are held. Interim live editorial
quality is **PARTIAL** because the affected set contains five legitimate
revision-required outcomes and only the targeted claims were freshly reviewed.
Overall Step 2 remains **PARTIAL / NO-GO for Step 3**. The retained claims were
not promoted, Step 3 visual factualisation was not started, and fresh
full-cohort selection effectiveness, canonical source-binding completeness,
P6 human acceptance, and any publication/readiness transition remain open.

### Independent full-context review and corrected-claim cycle — 2026-10-21

This follow-up corrects the remaining attachment-boundary defect. The
independent reviewer now receives every complete page in the already validated
`inspected_physical_pages` set, in deterministic order. Step 2 supporting pages
remain recorded separately as historical provenance; they no longer suppress
pages from the independent review. The prompt explicitly lists the pages
actually attached, and the existing image-index/page-map, PDF-hash, stale-row,
and page-reconciliation guards remain authoritative. A changed final claim
still requires a new result and a new review; no historical approval is reused.

#### Narrowed versus full bounded page context

The retained v8/v9 comparison used the narrowed Step 2 support-page set. The
new v10 run used the exact same seven real claims and full bounded inspected
pages. Both runs made 7 editorial calls and produced 2 `approved` decisions
and 5 `revision_required` decisions. The difference was source-page
availability, not a new approval of unsupported content:

| Claim | Narrowed reviewer pages/status | Full-context reviewer pages/status | Result |
|---|---|---|---|
| `ai-search-platform-relationships` | 12 / accepted | 10 / blocked by reconciliation | Full context exposed a wrong-page selection; it was not promoted. |
| `ai-browsers-adaptable-content` | 41 / accepted | 41 / accepted | Preserved. |
| `activate-outlook-revenue-models` | 5–6 / revision | 4–5 / revision | Still held; chart attribution objection remains. |
| `activate-ecommerce-capability-stack` | 115 / revision | 115 / revision | Same travel/tickets objection. |
| `guest-checkout-abandonment` | 8 / revision | 8 / revision | Same Digital Natives objection. |
| `market-growth-share-breakdown` | 1 / revision | 1 / revision | Same per-sector population objection. |
| `cloud-platform-catalysts` | 1 / revision | 1 / revision | Same per-sector/date-scope objection. |

The full-context run used **7 calls**, **201,184 input tokens**, **13,352
output tokens**, **214,536 total tokens**, estimated cost **$0.026795**, and
**144.259 seconds**. The narrowed v8/v9 runs used **132,330 total tokens**,
estimated cost **$0.018526**, and **135.585 summed seconds**. Thus full context
cost **$0.008269** and **82,206 tokens** more for this seven-claim comparison;
it preserved factual safety but reduced clean acceptance from 2 to 1 because
the search claim selected physical page 10. Existing reconciliation correctly
blocked that page mismatch. A retained-pages-first ordering experiment (v12)
also failed to improve page selection—2 controls were blocked—and was not
adopted (**7 calls**, **214,614 tokens**, **$0.026833**, **157.813 seconds**).
No unsupported claim was accepted in either full-context run.

The rendered full pages were independently inspected for the affected source
relationships. Reuters physical page 12 contains the search expectation and
traffic observations; physical page 41 contains the browser examples, liquid
content discussion, publisher measurement concern, and the 60% + 15% impact
chart. Bain physical page 1 visibly labels the top-20-gainers-per-sector
population, December 31, 2015–2020 comparison, and the 52%/20%/28% split.
BigCommerce physical page 8 visibly names Digital Natives and separately
labels 63% guest-checkout abandonment and 58% promotional-discount friction.
Activate physical pages 5–6 visibly bind Internet access to **$128B / 5.7%**,
advertising to **$108B / 4.7%**, and paid content to **$66B / 2.3%**.

#### Fresh correction → verification → editorial review

The five held IDs were evaluated from isolated, hash-matched retained-report
inputs. Existing GPT-6 Luna High correction and verification were run first;
the resulting corrected claims and actual verification provenance were written
to new shadow outputs, then sent to a fresh independent editorial review. The
historical Step 2/review manifests and canonical artifacts were not modified.

| Candidate | Corrected/verified result | Fresh editorial result | Source pages and material finding |
|---|---|---|---|
| `activate-outlook-revenue-models` | Verified first pass | Approved wording but **blocked** by page reconciliation | Visual verifier cited 4–5; independent review cited 5–6; the corrected values are source-supported but the page binding is not silently reconciled. Activate SHA `5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`. |
| `activate-ecommerce-capability-stack` | Verified first pass | Accepted | Page 115; corrected claim retains exclusion of travel and tickets. |
| `guest-checkout-abandonment` | Verified after retry | Accepted | Page 8; corrected claim retains Digital Natives and separates the promotional-discount relationship. BigCommerce SHA `29ffb53b9818460066c86e8d954bdd904bd0e11d2360d90dac040a5d33b9e7c3`. |
| `market-growth-share-breakdown` | Verified first pass | Accepted | Page 1; corrected claim says top 20 gainers per sector and December 31, 2015–2020. |
| `cloud-platform-catalysts` | Verified first pass | Revision required | Page 1; correction still says “across sectors” rather than the required per-sector population, so the fresh reviewer correctly withheld acceptance and supplied an actionable correction. Bain SHA `07541f3433b72007010ff604a93d0c560b6c6709ffd7bb5a58fefa81908f86c7`. |

The correction/verification outputs used **12 provider calls** (**4** for the
two Activate claims and **8** for the three additional claims), **324,268
input tokens**, **11,344 output tokens**, **335,612 total tokens**, estimated
cost **$0.038098**, and **177.35 seconds**. The fresh five-claim editorial
review used **5 calls**, **155,316 input tokens**, **6,521 output tokens**,
**161,837 total tokens**, estimated cost **$0.018793**, and **80.176 seconds**.
Combined: **17 calls**, **479,584 input tokens**, **17,865 output tokens**,
**497,449 total tokens**, estimated cost **$0.056891**, and **257.526 seconds**.
Terminal outcomes were mutually
exclusive: 4 verified first pass, 1 verified after retry, 0 failed, 0
unresolved, and 0 skipped. Every fresh approved result had substantive
source-grounded notes; the two remaining issues were blocked or
revision-required rather than promoted.

The replay CLI now requires explicit `--live` for provider dispatch. Without
that flag it requires an existing `--review-manifest` and runs only the
provider-free reconciliation path. The replay CLI also accepts repeated
`--real-claim-id` values for isolated retained-ID correction cycles. These are
additive shadow controls; no canonical claim, readiness state, or WordPress
content was changed.

#### Current verdicts

- Independent full-context attachment/provenance safety: **PASS** for exposing
  all bounded pages and failing closed on wrong-page selections; **PARTIAL** for
  live editorial availability because the model selected Reuters physical page
  10 when physical page 12 was required.
- Five-claim corrected factual/editorial cycle: **PARTIAL** — three claims were
  freshly accepted, Activate Outlook remains page-blocked, and Bain cloud
  remains revision-required.
- Step 1/E18 selection and repeatability: **PARTIAL**; these are post-selection
  replays and do not establish fresh live selection effectiveness.
- P6 human acceptance: **OPEN**.
- Step 3 canonical integration: **NO-GO**. No Step 3 code, canonical
  promotion, publication-readiness transition, or WordPress write was made.

The provider-free exact frozen-five replay remains unchanged: **15 reference
cases / 39 variants**, five matching PDF hashes, **29 retained IDs**, and
**29/29 theme slots** with zero provider calls and no fabricated fixture
substitution. Existing wrong-page, malformed-response, stale-review,
source-hash, and page-adjudication regressions remain covered by the focused
tests listed below. The immutable editorial-review roster remains **29 frozen
claims + 25 additional claims**, with the explicit unavailable identity kept
outside the eligible acceptance denominator. Final local verification after
this correction passed **682 affected tests (1 skipped, 1 deselected)**,
**115 prompt/LLM tests**, formatting, Ruff, mypy, documentation, backlog,
repository-hygiene, contract-schema, architecture-import, role-boundary, and
prompt-fixture gates.

### Targeted factual-acceptance and replay-integrity correction — 2026-10-21

This correction addresses the two remaining material holds from the `83ee68e`
baseline and the ambiguity in `--real-claim-id` accounting. It does not claim a
new Step 1 selection result: the live work below is a targeted, post-selection
replay over retained artifacts and explicitly corrected source bindings.

#### Targeted replay accounting

`replay_verified_claims_step2.py` now validates requested IDs against the
loaded eligible/unavailable roster before loading provider settings. Filtered
runs report `subset_only: true` and separate requested, matched, dispatched,
evaluated, skipped, unavailable, ambiguous, and unknown IDs/counts from the
full-cohort `selected_count`, `eligible_count`, and `unavailable_count`.
Unknown, ambiguous, and unavailable-only requests return `not_dispatched` with
an actionable reason and zero provider calls. Unfiltered execution retains the
existing full-cohort behavior. Focused replay coverage is **48 passed, 1
skipped**. The provider-free exact replay remains **15 cases / 39 variants**,
**29 retained IDs**, and **29/29 theme slots**, with all five source hashes
matching and no provider or publication writes.

The isolated retained Activate replay demonstrated why the distinction matters:
the first two-call replay was not accepted because the verifier produced only
the aggregate forecast and cited physical page 4; that result is retained as a
failed/insufficient targeted observation, not treated as evidence of improved
selection. A request for `cloud-platform-catalysts` against the frozen 29-ID
roster matched no eligible ID and made zero provider calls because that ID is in
the separate additional cohort. The correct explicit additional snapshot
reported **25 selected / 24 eligible / 1 unavailable**, and its targeted Bain
request dispatched only the unambiguous requested ID.

#### Activate Outlook corrected replay

The original PDF was inspected directly. Physical page 5 is the aggregate
forecast chart (`$1.7T` in 2017E, `$2.0T` in 2021E, `$302B`, `4.1%` CAGR and
approximately `3%` global GDP CAGR); physical page 6 is the segment chart. The
hash-matched source is
`5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`.

A fresh corrected-input shadow replay retained candidate ID and evidence
identity while binding inspection to pages **5–6**. The final verified claim
states the forecast segment relationships exactly: **Internet access `$128B /
5.7%`**, **ad revenue `$108B / 4.7%`**, and **paid content `$66B / 2.3%`**, with
Internet access defined to include fixed broadband, wireless, and mobile
Internet access. The visual stage was **verified first pass**, with 2 calls,
36,665 input tokens, 1,413 output tokens, 38,078 total tokens, estimated cost
`$0.004373`, 18.935 seconds, and zero cache reuse. The fresh independent
editorial review cited the same physical pages and was **approved / accepted**
with 1 call, 18,340 input tokens, 1,162 output tokens, 19,502 total tokens,
estimated cost `$0.002415`, and 13.8 seconds observed process time. Its fresh
review-response SHA is
`b424e3cad046c7ebcecf3b0b53309f16261833f146c6a5d41eaaea8abb3883d9`.

The new immutable source-grounded record
`docs/quality/verified-claims-step2-page-adjudication-20261022.json` binds that
response hash, the source hash, inspected pages `[5,6]`, verifier pages
`[5,6]`, reviewer pages `[5,6]`, and authoritative pages `[5,6]`. The page sets
match, so the record does not override a disagreement; it records the corrected
source location and does not reuse the historical rejected Activate
adjudication. The fresh visual and review manifests hash to
`6de8a48fee18ec00601f98eeb03ce516b6612e3cb7c62930f7bae12146bcda42` and
`329b773f5b3f7f894aa5fd7b18121a8144486e4b497ebc5a9b72b290aa0d30ce`.

#### Bain Cloud corrected replay

Physical page 1 of the hash-matched Bain PDF
`07541f3433b72007010ff604a93d0c560b6c6709ffd7bb5a58fefa81908f86c7` visibly
defines the chart as the top 20 gainers **per sector**, compares December 31,
2015 with December 31, 2020, and separately names cloud technology and platform
business models as catalysts with four actions. The fresh corrected claim says
that born-tech companies accounted for 52% of market-value growth among the top
20 gainers per sector from December 31, 2015 to December 31, 2020, while
tech-led strategy contributed another 20%, then preserves the distinct
cloud/platform strategic recommendation and actions. It is not merely a
paraphrase of accepted `market-growth-share-breakdown`: that insight is the
quantitative market-mix finding, while this one retains the operational
cloud/platform response.

The visual stage was **verified first pass**, with 2 calls, 70,158 input tokens,
2,272 output tokens, 72,430 total tokens, estimated cost `$0.008152`, 31.264
seconds, and zero cache reuse. The fresh independent editorial review cited
physical page 1 and was **approved / accepted** with 1 call, 35,103 input
tokens, 1,322 output tokens, 36,425 total tokens, estimated cost `$0.004171`,
and 17.7 seconds observed process time. Its fresh review-response SHA is
`13d7a45e83779ee6efda5b940356d7927b921990113e12212faf197e9a82f90b`. The
visual and review manifests hash to
`7dcfd5280e94d16d1eef1f36c6df711fc79a779527972f03507888bbc5594db6` and
`9d74cd6e5c520baa68d15f24011726cb7b8df44dbec4db68521906daa4f3aa37`.

Across these two corrected targeted cycles there were **6 provider calls**,
**160,266 input tokens**, **6,169 output tokens**, **166,435 total tokens**, and
`$0.019111` estimated cost. These measurements cover only the two corrected
claims and their independent reviews; they are not full-cohort cost or
selection-effectiveness measurements.

For completeness, two preliminary retained-input probes preceded the corrected
cycles: Activate used 2 calls, 69,842 input tokens, 2,987 output tokens,
72,829 total tokens, `$0.008478`, and 48.628 seconds; Bain used 2 calls,
70,854 input tokens, 2,096 output tokens, 72,950 total tokens, `$0.008133`,
and 34.422 seconds. The Activate probe produced only the aggregate claim with
the wrong physical-page citation, and the Bain probe retained the unqualified
“across sectors” wording; neither was accepted. Including those diagnostic
probes, the observed work used **10 calls**, **300,962 input tokens**, **11,252
output tokens**, **312,214 total tokens**, and **$0.035722** estimated cost.
Provider/cache reuse was not measured as a reuse hit in these isolated output
roots.

#### Preserved safeguards and verdict

The accepted eCommerce, guest-checkout, and market-growth outcomes were not
reprocessed. Reuters browser page 41, Reuters AI-search page 12, the existing
Adjust finance adjudication, the wrong-page fail-closed behavior, and the
Merchant Risk Council unavailable identity remain unchanged. No canonical claim,
readiness state, publication artifact, or WordPress content was written.

Targeted factual acceptance and subset accounting are **PASS** for the focused
correction. Overall Step 2 remains **PARTIAL**: the corrected Activate and Bain
holds are now source-grounded and independently accepted, but these are
post-selection targeted replays and do not establish fresh Step 1 selection
effectiveness, repeated-run stability, P6 human acceptance, or canonical
source-binding completeness. Step 3 remains **NO-GO / unstarted** until those
independent gates are satisfied.

#### Ten-report source-grounded selection audit — 2026-10-22

The exact frozen ten-report PDF/artifact cohort was independently audited at
physical-page level for all 59 accessible final-editorial rows. All ten source
hashes and page counts matched. The audit rated **33 HIGH, 22 MEDIUM, 4 LOW,
and 0 INVALID** source-grounded rows; LOW denotes a source-supported but weak
standalone editorial finding, not a factual failure. No independently confirmed
unsupported material claim was marked verified. The Criteo
`newer-channels-perceived-roi` row remains correctly `failed_verification`
after two malformed verification attempts.

The audit found no deterministic selector, semantic-deduplication,
fallback-fidelity, or cache defect that supports a production patch. It did
record bounded omissions within covered themes (including Reuters AI-browser
impact p.41, KPMG execution tooling p.24, Criteo US campaign-cost increase
p.7, Deloitte discovery-speed p.6, Emplifi positive-resolution repeat buying
p.18, and StackAdapt first-party/contextual data p.12), one source-supported
Emplifi final-stage roster substitution, one Algolia shadow binding-continuity
limitation, and three provisional page recoveries. The Step2 replay evaluates
`insights_final`, not necessarily the raw `insights_candidates` pool; stable
IDs are not used as a quality proxy. Full matrix and before/after ledger:
[`source-grounded-editorial-audit.md`](verified-claims-ten-report-acceptance-202610/source-grounded-editorial-audit.md).

The audit itself was provider-free. A separate explicit replay was mistakenly
started with a flag combination that does not enable provider-free operation;
it was interrupted after 14 bounded calls (DoubleVerify 10, KPMG 4), 95,499
input tokens, 4,930 output tokens, `$0.012016` estimated cost, and about 84
seconds. It produced no accepted result and no canonical, publication, or
WordPress write; those calls are excluded from all ten-report metrics.

Step 1/E18 and Step2 remain **PARTIAL**; P6 remains open and Step 3 remains
**NO-GO / unstarted**. No ranking, fallback, minimum-count, cache, canonical,
or publication behavior was changed by this audit.

#### Ten-report integrity corrections — 2026-10-22

This follow-up implements only the confirmed integrity defects from the
ten-report audit. It was verified locally from retained artifacts and did not
run a new provider evaluation. The prior ten-report live result remains the
measurement baseline: 59 rows, 58 first-pass verified and one Criteo
`failed_verification`; its malformed Criteo response was empty/non-JSON and
did not provide a safe repair payload.

- Corrected-claim lineage is now separate from original lineage. The Algolia
  58% revenue candidate keeps its original candidate/evidence/metric/page
  binding; a materially different 53%/39% investment correction retains only
  its verified final text and inspected-page record unless an independently
  bound corrected evidence/metric binding is present. The replay helper cannot
  promote the original binding into that changed proposition.
- Final insight admission now rejects an unmatched final-stage stable ID at
  the final artifact boundary and fills from eligible candidates. An eligible
  same-ID final rewrite keeps its editorial wording while restoring the
  candidate's protected factual fields. The retained Emplifi artifact was not
  rewritten; a provider-free selector check admitted `behavior-cross-check`
  and rejected the unmatched `behavior-high-value-research` identity.
- The existing fidelity results resolve unique physical pages for the three
  audited missing-page cases: KPMG quote-4 to page 35, Algolia quote-001 to
  page 26, and Bain quote-4 to page 1. Fresh evidence-pack construction now
  attaches such a page only when fidelity returns exactly one physical page;
  ambiguous or unsupported results remain unbound/provisional. Printed page
  labels are not substituted for physical PDF pages, and retained historical
  artifacts remain unchanged.
- Verification responses now distinguish malformed/schema-invalid output from
  substantive source rejection, require a substantive source-specific note
  and supporting pages for a verified outcome, retain typed provider failure
  metadata, and keep the existing two correction/two verification attempt
  bounds. The Criteo retained result therefore remains fail-closed.
- `--provider-free --live` is rejected before dispatch. The explicit
  provider-free replay completed with 0 provider calls, 0 fabricated fixture
  substitutions, 15 reference cases / 39 variants, 5/5 matching PDF hashes,
  29 retained IDs and 29/29 theme slots. Its limitation remains explicit: it
  does not measure live correction quality or selection effectiveness.

Focused verification after these changes passed **66 tests**, the broader
artifact/source/visual suite passed **147 tests with 1 expected skip**, the
affected generator/regeneration suite passed **395 tests**, and the focused
Step 2 acceptance/provenance suite passed **202 tests with 1 expected skip and
1 deselection**. Ruff passed for all changed files except the regeneration
module's seven pre-existing findings, and changed modules compiled. No
canonical claim, publication-readiness state, or WordPress content was
written. Step 1/E18 and Step 2 remain **PARTIAL**; this work does not claim
fresh live selection improvement and Step 3 remains **NO-GO / unstarted**.

#### Verified Claims integrity checkpoint — 2026-10-22

This checkpoint starts from `73af170` and closes the remaining demonstrated
contract and final-lineage defects without changing Step 2's shadow-only
boundary.

- The P0 CI failure was a generated-snapshot omission: `verified_claims` was
  already at schema v1.1, while `docs/quality/contract_schemas.json` still
  reflected the prior contract. The update produced only the five intentional
  v1.1 fields (`original_metric_binding`, `corrected_evidence_ids`,
  `corrected_evidence_spans`, `corrected_metric_binding`, and
  `corrected_source_binding_status`); the no-update checker then passed.
- Final insight payloads now pass through one deterministic lineage validator
  before admission, cached reuse, and targeted regeneration return. Unknown,
  duplicate, empty, or conflict-excluded stable IDs raise the existing
  structured-output error with bounded diagnostics; an invalid final ID can no
  longer be silently replaced while retaining its editorial identity. Cached
  final families are validated before reuse and regenerate through the existing
  family path when rejected. Valid same-ID editorial rewrites still retain
  their final wording while protected candidate facts and evidence bindings are
  restored. No selector ranking or fallback policy was changed.
- Regeneration validates the regenerated roster against both the current
  candidate pool and retained prior final bindings. This preserves legitimate
  targeted repairs while failing closed on a newly introduced identity. The
  cache regression proves one final-family regeneration, records the rejection
  reason, and emits no unmatched ID.
- The exact frozen-five provider-free replay remains **15 reference cases / 39
  variants**, **29 selected IDs**, **29/29 theme slots**, five matching source
  hashes, and zero provider calls or fabricated fixture substitutions. The
  selected identities, physical pages, evidence spans and protected bindings
  are unchanged from the retained Step 1 baseline. This is a replay of retained
  artifacts, not evidence of improved live selection effectiveness.
- A targeted live Criteo `newer-channels-perceived-roi` run used GPT-6 Luna
  High and the hash-matched PDF page 5. It was verified first pass with 2
  calls, 14,037 input tokens, 1,086 output tokens, 15,123 total tokens,
  estimated cost `$0.001947`, and 20.344 seconds. The corrected claim
  explicitly distinguishes a respondent expectation from measured ROI; its
  changed proposition correctly remains `unbound` rather than inheriting the
  original metric binding. This is one targeted recovery, not a full-cohort
  quality measurement.
- No deterministic omission, ranking, minimum-count, or shared-batch
  reliability change was justified by the retained audit. The known
  within-theme omissions remain editorial coverage limitations; the shared
  batch remains invalid for independent selection-repeatability evidence.
  KPMG quote-4, Algolia quote-001, and Bain quote-4 retain the existing unique
  physical-page-only recovery policy (pages 35, 26, and 1 respectively), with
  ambiguous cases remaining unbound.

Verification for this checkpoint: the affected artifact/source/visual,
shortlisting, regeneration, structured-output, and contract suites passed
**253 tests with 1 deselected**. Contract snapshot validation passed; changed
modules compiled; changed-file formatting passed after formatting the touched
files. Ruff still reports **eight pre-existing findings** in
`report_regeneration_generator.py` (introduced by older commits, including its
existing list-comprehension finding); no new finding is attributable to this
checkpoint. No canonical claim, readiness state, publication artifact, or
WordPress content was written.

Verdict: Step 1/E18 remains **PARTIAL** and Step 2 remains
**PARTIAL/NO-GO**. Step 3 remains unstarted. The checkpoint closes the
demonstrated integrity defects, but fresh full-cohort selection effectiveness,
clean shared-batch repeatability, source-recall measurement, and P6 human
editorial acceptance remain outstanding.

#### Regeneration lineage admission and retained-evidence continuity — 2026-10-22

This checkpoint closes the remaining regeneration-path lineage inconsistency;
it does not change initial selection, fallback ranking, visual correction, or
canonical persistence.

- **Checkpoint A — root cause and fix.**
  `_handle_insights_bundle_regeneration()` previously validated a regenerated
  final roster against the current candidates plus arbitrary prior-final
  records, then selected it against current candidates alone. A stale prior ID
  could therefore pass one boundary and disappear or be restored at another.
  The path now derives one eligible, source-bound candidate per stable ID using
  `_candidate_factual_fields()` and `_candidate_group_has_factual_conflict()`;
  it validates, restores factual fields, and selects regenerated finals only
  against that pool. `_restore_missing_final_insight_roster()` restores a prior
  editorial rewrite only when its ID is still in that pool. Stale IDs and
  conflicting source bindings are not substituted from prior-final text or an
  evidence ID alone. Valid same-ID repairs retain final editorial wording and
  receive the authoritative candidate binding. New valid candidates remain
  eligible. Existing cache reuse already revalidates final IDs against the
  current candidate facts, so no cache-key/version change was necessary.
- **Checkpoint B — malformed payload boundary.** The existing artifacts schema
  requires each `insights_final` item to be an object with `id`, `text`, and
  `evidence_id`; it rejects malformed/missing-identity entries while allowing
  an empty intermediate array. The lineage helper therefore remains focused on
  identity/conflict checks and does not duplicate schema validation or reject a
  legitimate empty intermediate state.
- **Checkpoint C — corrected-claim continuity.** The retained Algolia
  `revenue-incentive-58` correction changes the original 58% proposition to a
  53%/39% search-investment proposition. Its original page/evidence/metric
  binding is preserved as original provenance, while the corrected binding
  remains unbound because the retained evidence does not independently provide
  a complete authoritative replacement binding. The successful Criteo 61%
  correction is explicitly an expectation rather than measured ROI and remains
  source-bound to original page 5 while corrected metric fields stay empty.
  No stale metric, population, period, forecast, or page identity is inferred.
- **Checkpoint D — retained real-report trace.** Hash-matched retained outputs
  preserve KPMG `execution-risk-focus-areas` / `quote-4` on physical page 35,
  Algolia `agentic-search-deployment-and-plans` / `quote-001` on page 26,
  Bain `cloud_platform_action_frame` / `quote-4` on page 1, and Criteo
  `newer-channels-perceived-roi` / `s2-newer-channels-roi` on page 5. KPMG,
  Algolia, and Bain page recoveries remain `provisional_recovered` rather than
  canonical promotions because their original artifact page arrays were empty.
  Emplifi `behavior-high-value-research` remains a source-supported final-stage
  roster substitution with physical page 4; its absence from the raw
  candidate roster was not rewritten. No historical artifact was edited.
- **Checkpoint E — selection audit.** The retained ten-report source-grounded
  audit still locates the known omissions inside already-covered themes or at
  the final-stage roster boundary. It does not expose a deterministic selector
  rejection, fallback-fidelity, minimum-count, or cache defect, so no new
  ranking algorithm or selection policy was introduced. This is not fresh live
  Step 1 selection evidence.
- **Checkpoint F — shared-batch reliability.** The retained shared run shows
  eight `ias_canary_timeout` and two `validation_failed` terminal rows, all at
  semantic validation, and all ten members point at the same run directory.
  The retained telemetry does not establish whether provider contention,
  worker contention, or timeout configuration caused the canary failures; the
  isolated supplemental run used separate state and passed. No reliability
  change was made without an observed root cause, and the shared run remains
  invalid as an independent selection repetition.

Current verification: the provider-free frozen-five replay produced **15
reference cases / 39 variants**, **29 selected IDs**, **29/29 theme slots**,
**5/5 PDF hashes**, and zero provider calls or fabricated fixture substitutions;
selected IDs are unchanged from the retained baseline. The focused lineage,
artifact, Step 2, regeneration, cache, schema, and contract suite passed
**541 tests, 1 skipped, and 1 deselected**. The contract snapshot gate passed
and changed production modules compiled. Ruff passed for the changed
normalization, shortlisting, schema-test, and schema-validator files; the
regeneration module retains eight pre-existing findings and the split test
module retains three pre-existing line-length findings. No provider calls,
canonical mutation, publication-readiness transition, or WordPress write was
made by this checkpoint.

The local aggregate `py scripts/ci/run_quality_gate.py` reached the full
pytest stage and recorded **7,968 passed, 2 skipped, and 32 deselected**. It
stopped on the pre-existing `tests/test_build_hash_locked_wheelhouse.py::test_existing_wheelhouse_reports_missing_active_artifact`
failure because this workstation runs CPython 3.14 while that native
wheelhouse audit requires CPython 3.12; local coverage/mutation stages were
therefore not reached. Hosted CI remains the authoritative supported-runtime
check for those stages.

Verdict: Step 1/E18 remains **PARTIAL** and Step 2 remains
**PARTIAL/NO-GO**. The regeneration lineage defect is corrected and the
retained provenance trace is continuous for the audited rows, but clean
full-cohort live selection repeatability, a source-recall oracle, P6 human
acceptance, and canonical corrected-claim binding completeness remain open.
Step 3 remains unstarted.

#### Visual-authoritative editorial canary — 2026-10-22

This checkpoint adds an explicit, opt-in, shadow-only canary at the existing
candidate-to-final editorial boundary. It does not promote canonical verified
claims, change publication readiness, write WordPress, or implement Step 3.
The implementation checkpoints are `0079be14` (canary admission and wiring)
and `38bb36e1` (downstream propagation regressions).

**Boundary and authority rules.** `run_report_analysis()` and
`generate_artifacts()` retain their default behavior when no canary
configuration is supplied. In canary mode, the existing Step 2 evaluator is
called with a hash-bearing source identity and the actual source PDF. The
admission adapter requires a terminal `verified` or `verified_after_retry`
outcome, an exact source identity/hash match, the stable candidate ID, a
physical page, canonical evidence spans, and a complete protected metric
binding for a material correction. An unchanged proposition may retain its
original binding; a material `unbound` correction is quarantined. Duplicate or
conflicting stable IDs are failed closed rather than resolved by editorial
score. No evidence ID, page, span, metric, or factual field is invented.

Admitted candidates are the sole factual pool for final insights, metric
spine, expert commentary, LinkedIn output, and scoped regeneration. The
authority digest participates in affected family inputs and is retained in
the private cache metadata. Overall artifact-cache reads are bypassed until
admission runs, and regeneration reuses only the admitted pool/digest. The
legacy `preserve_public_source_displays()` correction is skipped inside this
canary path; the non-canary path is unchanged.

**Provider-free frozen-five replay.** The exact Step 0 cohort (Capgemini,
Activate, KPMG, Reuters Institute, and Adjust) used the retained real-report
artifacts, `evidence_fidelity` packs, DocMaps, and hash-matched PDFs. It
covered **15 reference cases / 39 variants**, **29 retained real IDs**, and
**29/29 retained theme slots**, with **5/5 PDF hashes matching** and zero
provider calls or fabricated fixture substitutions. This validates input and
admission coverage; it is not evidence of fresh live selection improvement.

The isolated GPT-6 Luna High frozen-five evaluation used **150 provider
calls**, **2,482,109 input tokens**, **100,241 output tokens**,
**2,582,350 total tokens**, estimated cost **$0.298333**, and **1,737.858 s**.
The 29 real retained claims were **26 first-pass verified, 3 verified after
retry, 0 failed, and 0 unresolved**. The 39 reference variants were **33
first-pass verified, 3 verified after retry, 3 unresolved, and 0 failed**;
the reference gate matched **37/39**, with **0 false accepts** and **2 false
rejects**. `ACT-004` remained correctly unresolved for its wrong page. The
two false rejects were `CAP-001` and `CAP-002`: the model supplied a
source-grounded neighboring correction, but the current benchmark evaluator
still applies the original-direction constraint. Golden expectations were
not changed.

For `ADJ-001-unsupported-metric`, the original churn/conversion claim was
not treated as valid. The evaluated final claim replaced those labels with
the source-supported global 2024–2025 gaming-app install/session tuple,
including strategy sessions `+57%`, strategy installs `-1%`, casino installs
`+22%`, casino sessions `-5%`, and slots installs `+46%` / sessions `-5%`.
The final claim is source-grounded on the expected physical page, but its
corrected binding is `unbound`; therefore the canary correctly quarantines it
instead of promoting the evaluator's `verified` label as editorial
authority.

**Ten-report live replay and admission ledger.** The requested cohort was
DoubleVerify, Adjust, Bain & Company, Emplifi, StackAdapt, Algolia, Criteo,
Deloitte, KPMG, and Reuters Institute. The hash-matched replay evaluated all
**59 real shortlisted claims** using **116 selected provider calls**
(118 ledger rows observed), **1,790,894 input tokens**, **54,838 output
tokens**, **1,845,732 total tokens**, estimated cost **$0.206506**, and
**1,060.387 s**. Terminal evaluator outcomes were **59 first-pass verified,
0 after-retry, 0 unresolved, 0 failed, and 0 skipped**. The 59 stable IDs
and per-report selected counts were unchanged from the retained baseline;
all 10/10 actual PDF hashes matched, and no physical-page or evidence-ID
differences were observed against that baseline. The evaluator rewrote the
final wording for 58/59 rows, so those result payloads alone cannot be
treated as a canary editorial result.

The provider-free admission replay over those exact responses produced
**1 admitted and 58 quarantined** claims. The single admission was the
unchanged StackAdapt `retail-2026-consumer-data-relevance-expectation`
binding. Quarantine reasons were **53 `corrected_binding_unbound`**, **3
`evidence_span_page_missing`**, and **2 `evidence_page_not_supported`**.

| Report | Input | Admitted | Quarantined | Main reason |
|---|---:|---:|---:|---|
| Adjust | 7 | 0 | 7 | 7 unbound corrections |
| Algolia | 6 | 0 | 6 | 5 unbound; 1 missing span page |
| Bain & Company | 5 | 0 | 5 | 4 unbound; 1 missing span page |
| Criteo | 5 | 0 | 5 | 5 unbound corrections |
| Deloitte | 6 | 0 | 6 | 4 unbound; 2 unsupported pages |
| DoubleVerify | 5 | 0 | 5 | 5 unbound corrections |
| Emplifi | 5 | 0 | 5 | 5 unbound corrections |
| KPMG | 6 | 0 | 6 | 5 unbound; 1 missing span page |
| Reuters Institute | 7 | 0 | 7 | 7 unbound corrections |
| StackAdapt Inc | 7 | 1 | 6 | 6 unbound corrections |

The four known-failure canary probes (Criteo, Algolia, DoubleVerify, and
Adjust) used **8 provider calls**, **188,631 input tokens**, **5,212 output
tokens**, **193,843 total tokens**, and estimated cost **$0.021470**. Each
returned an evaluator `verified` result with an `unbound` material correction;
none was admitted. The isolated Criteo probe independently used 2 calls,
15,411 total tokens, estimated cost `$0.002084`, and 22.758 s, with the same
fail-closed admission outcome. These are bounded source-evaluation probes,
not evidence of a successful end-to-end canary generation.

The retained Step 2 ledger had **58 verified / 1 failed** (the Criteo
`newer-channels-perceived-roi` row). The new evaluator's **59 verified**
count is not a measured quality improvement: it reflects a fresh model run,
and the canary admits only one unchanged row. No canary final artifact was
generated from the ten-report live results because no material corrected
binding was independently available. There were no canonical artifact
mutations, publication writes, or WordPress writes.

**Regression evidence.** The new canary suite covers unchanged and
independently bound corrections, unbound corrections, wrong hash/page/span,
duplicate and conflicting IDs, non-terminal outcomes, cache replay,
authority-digest changes, downstream metric-spine/expert/social propagation,
and scoped regeneration. The focused artifact, evidence-binding, visual
evaluation, shortlisting, normalization, public-projection, and canary
suites passed **219 tests with 1 skipped**. The focused regeneration suites
passed **219 tests**. Mypy passed for the four changed production modules;
changed canary/generation/orchestrator/test files pass Ruff. The regeneration
and storage modules retain previously existing Ruff findings and were not
broadly refactored. The local aggregate gate remains limited by the known
CPython 3.14 versus native CPython 3.12 wheelhouse failure recorded above.

**Verdict.** The visual-authority boundary is implemented and fails closed on
missing or ambiguous corrected provenance. The exact real-report replay
demonstrates source-hash coverage and stable selection identity, but it does
not yet demonstrate useful live canary editorial replacement: **58/59 live
results were quarantined**, and no fresh admitted final-family output exists
for comparison. Step 2 therefore remains **PARTIAL/NO-GO** for authority
promotion, and Step 3 remains **unstarted / not ready**. Remaining gaps are
independent corrected evidence bindings for material rewrites, fresh
end-to-end canary output, the two strict-direction reference false rejects,
and the supported-runtime CI gate.

#### Verified-fact downstream canary — 2026-10-22

This checkpoint implements the Step 3 authority boundary as an explicit,
opt-in canary. It remains shadow-only: no canonical claim promotion,
publication-readiness transition, WordPress write, or default-path authority
change occurs. Discovery DocMaps, findings, candidate propositions,
editorial-plan themes, and quote candidates are discovery inputs only. A
terminal visual result must instead provide a source-hash-bound verified fact
with a non-empty statement, valid structured metric (or an explicit
qualitative metric), inspected and supporting physical pages, and
source-specific verification notes. The verified-fact digest is stored with
the canary cache and regeneration snapshot; incomplete cache metadata fails
closed. Quotes are empty in this mode.

The smallest admitted record is `fact_id`, verified statement, protected
metric fields, exact source identity and PDF SHA-256, supporting physical
pages, terminal outcome, inspected pages, and page-level provenance notes.
The discovery candidate ID/evidence IDs remain traceability metadata only.
Final insights, summary evidence, metric spine, key figures, expert/social
generation inputs, evidence binding, and scoped regeneration all consume the
admitted verified-fact projection. Editorial plan and theme data may order or
label the output but cannot authorize a factual field. Existing correction and
verification calls remain independent and bounded at two attempts each.

**Focused real-report replay.** The isolated GPT-6 Luna High runs used the
retained real-report artifacts and exact hash-matched PDFs for Criteo, Adjust,
DoubleVerify, and Algolia. Source review used full physical PDF pages and
rendered page images; no cropped image was used for authority. The successful
outputs were independently checked against the following pages:

| Report | Terminal canary result | Downstream output | PDF/source review |
|---|---|---|---|
| Criteo | 5/5 facts admitted; 5 first-pass verified | 5 final insights, 4 metric-spine rows, 2 key figures, 0 quotes | Pages 5, 7, and 8 support the 61% expectation qualifier, 22% estimate, 50% retail-media implication, 51/45 and 47/40 plan comparisons, and 54% US focus. |
| Adjust | 5/5 facts admitted; 4 first-pass and 1 after retry | 5 final insights, 2 metric-spine rows, 2 key figures, 0 quotes | Pages 6, 9, 11, 21, and 34 support install/session growth, the over-20% advanced-GenAI qualifier, 31% satisfaction, all-games retention, and the finance install/session divergence. |
| DoubleVerify | 5/5 facts admitted; 5 first-pass verified | 5 final insights, 1 metric-spine row, 0 key figures, 0 quotes | Pages 3, 8, 9, and 10 support regional brand-suitability rates, the 20+ engagement definition, normalized-100 context, and APAC/North America device-format values. |
| Algolia | 0/6 admitted; five verification responses carried facts, while `revenue-as-critical-incentive` remained unresolved after its bounded correction path | No final artifact was produced; coverage failed closed | The hash matched and available source pages support the verified responses, including the page-23 investment correction and pages 22, 26, and 27 survey facts. No unresolved fact was promoted. |

The successful artifacts are under the ignored local replay root
`out/verified_claims_step3_live_20261022/` and contain exact source hashes in
every fact. Criteo, Adjust, and DoubleVerify final insight evidence IDs are
all `verified-fact:<fact_id>`; their final wording and protected fields were
reviewed against the PDF pages above. The four-report runs recorded:

The verified source hashes were Criteo
`17cf2e92c8804e35274faf3dd416db2fe6e4a81d7aa92418ada8ba90ee77c00c`, Adjust
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`,
DoubleVerify `99f0cc4f7787cac52b7f89eefa7659053b3703ea100b9e0522fa500c64463d7e`,
and Algolia
`d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50`.

| Report | Provider calls / visual calls | Input + output tokens | Estimated cost | Provider latency | Cache reuse |
|---|---:|---:|---:|---:|---:|
| Criteo | 17 / 10 | 186,154 + 33,755 | $0.035493 | 339.882 s | 0 hits |
| Adjust | 19 / 12 | 298,765 + 40,489 | $0.050020 | 389.581 s | 1 hit |
| DoubleVerify | 17 / 10 | 177,058 + 40,307 | $0.037759 | 379.156 s | 1 hit |
| Algolia | 17 / 12 | 381,146 + 38,004 | $0.057017 | 375.670 s | 1 hit |

These totals are from the isolated `cost-ledger.jsonl` files and include
artifact-generation calls; no measurements were inferred. The Algolia worker
was stopped after its provider work completed but before an artifact could be
written, because the canary had already failed closed on incomplete coverage.

**Provider-free and regression evidence.** The deterministic provider-free
path is covered by the verified-fact admission, digest/cache, downstream
projection, and regeneration tests; the retained pre-Step 3 artifacts do not
contain authoritative verified-fact snapshots and therefore cannot be reused
as a provider-free Step 3 fact source. A read-only replay of the new isolated
snapshots used zero provider calls: Criteo, Adjust, and DoubleVerify each had
5 facts, 5 final insights, exact PDF-hash matches, verified-fact-only final
evidence IDs, and zero quotes; Algolia had no admitted snapshot. The focused
suite passed **498 tests in 28.93 seconds**. `python -m compileall -q src tests`, the contract schema
snapshot gate, and `git diff --check` passed. Ruff is clean for the new
verified-claims visual/canary code and tests; the changed storage/regeneration
modules still report the repository's pre-existing formatting findings. No
full ten-report downstream Step 3 run was claimed from the older ten-report
Step 2 results because those results lack verified-fact snapshots.

**Verdict: PARTIAL.** The authority boundary, fail-closed admission,
source-hash/page checks, downstream verified-fact routing, cache identity, and
regeneration continuity are implemented and exercised. Three focused reports
produced PDF-reviewed final artifacts; Algolia correctly abstained. Step 3 is
not ready to close: the complete ten-report downstream replay, fresh
provider-free verified-fact snapshots for the retained cohort, and an
independent review of every final output remain outstanding. This checkpoint
does not claim improved live selection quality or alter the Step 2
PARTIAL/NO-GO status.

#### Step 3 stabilization — 2026-10-22 (current branch)

This checkpoint records the current-head correction after the first opt-in
verified-fact canary replay. The canary remains opt-in and shadow-only: no
canonical claim, publication-readiness, or WordPress state was mutated.

The root causes were bounded and were fixed without a new service or model
call:

* `admit_visual_authority_candidates()` previously returned an empty admission
  whenever any result was unresolved or failed, even when other candidates had
  complete independent verified facts. It now requires exact one-result
  accounting for every expected identity, records terminal outcome counts and
  quarantine reasons, fails closed on missing/duplicate/unexpected/conflicting/
  malformed identities, and admits only individually valid `verified` or
  `verified_after_retry` facts. `unresolved`, `failed_verification`, and
  `skipped` are terminal accounting outcomes, not facts.
* Verified-fact projections retain the stable
  `verified-fact:<fact_id>` reference, authoritative statement, metric, source
  hash, identity, and physical pages. Page notes are carried under the
  `verified_facts` source pack and are excluded from direct evidence and
  publisher-quote validation; they are analytical provenance, not PDF quotes.
* Verified editorial-plan remapping no longer assigns an unrelated fact by
  modulo index. Unmapped themes are omitted and the existing minimum insight
  requirement is enforced with typed `visual_authority_coverage_insufficient`
  errors when the admitted set cannot support a report.

Focused regressions now cover mixed verified/unresolved and
verified/failed-verification results, missing/duplicate/unexpected/malformed
accounting, wrong hash/page and metric failures, synthetic-span quote
exclusion, unsupported planning input, cache replay, regeneration, and
typed minimum coverage. The affected local suite passed **530 tests with 1
skip in 20.96 seconds**. Formatting, compilation, public-report quality, and
diff checks passed.

**Provider-free retained-artifact replay.** The exact retained Algolia cache
was replayed through the current admission function using its five actual
verified response payloads and its actual unresolved `revenue-incentive-58`
correction result. The previous behavior produced no artifact from this
6-claim run. The corrected accounting produced **5 admitted facts / 1
unresolved**, with `coverage_complete=true`, outcome counts of **5 verified,
1 unresolved**, and no fabricated fact or unsupported binding. This validates
the admission correction only; it is not fresh live editorial-generation
quality evidence.

The retained ten-report Step 2 result was also passed through the current
admission boundary: **59/59 identities were accounted for, but 0/59 were
admitted** because those result records contain no authoritative
`verified_fact` snapshots. This is the required fail-closed result, not a
quality regression. No ten-report Step 3 downstream run was claimed from
those records.

For the three retained Step 3 artifacts with authoritative snapshots, a
provider-free current-head rebind replay preserved all downstream numeric
content while changing only the provenance classification:

| Report | Facts / final insights | Metric spine before → after | Key figures before → after | Final span source before → after |
|---|---:|---:|---:|---|
| Criteo | 5 / 5 | 4 → 4 | 2 → 2 | `findings` → `verified_facts` |
| Adjust | 5 / 5 | 2 → 2 | 2 → 2 | `findings` → `verified_facts` |
| DoubleVerify | 5 / 5 | 1 → 1 | 0 → 0 | `findings` → `verified_facts` |

The DoubleVerify zero-key-figure result is therefore not projection loss. Its
existing normalization rejects composite semicolon-separated metric displays;
the retained authoritative facts do not provide a safe existing decomposition
into separate key-figure bindings. No speculative numeric enrichment was
added. Full-page PDF review confirmed the retained final claims on pages 3,
8, 9, and 10, including the page-10 North America Video values 128 (In-App)
and 88 (Mobile Web); no independent factual error was found in that review.

The prior bounded GPT-6 Luna High runs remain the measured live baseline:
they recorded **17/19/17/17 calls** for Criteo/Adjust/DoubleVerify/Algolia,
the tokens, costs, latency, and cache reuse listed in the preceding canary
checkpoint, with no publication writes. No new provider calls were made by
this correction; the current-head provider-free replay must not be presented
as a fresh live editorial-quality improvement. The current retained Criteo,
Adjust, and DoubleVerify editorial outputs were reviewed against full source
PDF pages; Algolia has no final artifact because the five-fact snapshot was
available only in the retained verification cache, not in a completed
current-head generation.

**Hosted CI limitation.** Prior hosted run `39815198918` passed the test job
(**8,008 passed, 1 skipped**) and both mutation partitions, including the
formatting, policy, architecture, schema, and repository gates. Its release
evidence job failed only at the retained prompt-fixture regression gate:
validation-family tokens were **9,597 vs 8,004** (+19.90%) and estimated cost
was **$0.001720 vs $0.001560** (+10.26%); the total-token delta was **+1.62%**.
A full rerun reproduced the same values. The final-SHA hosted run
`39818845777` reproduced the same release-evidence failure after passing the
tests and both mutation partitions. The prompt/config diff from the last
successful hosted run is confined to the pre-existing Step 2
visual-verification prompt changes; no Step 3 stabilization commit changes
prompts or model configuration. The gate was not weakened or allowlisted.
This leaves the aggregate hosted release evidence status PARTIAL even though
the changed Step 3 paths and all affected tests passed.

**Current verdict: PARTIAL.** The verified-fact authority boundary, exact
accounting, mixed-outcome admission, input isolation, quote semantics, cache
identity, regeneration continuity, and current-head regression suite pass.
Step 3 is not ready to close because a fresh current-head editorial generation
and independent review for the complete retained ten-report cohort remain
unavailable, and live selection effectiveness is still unmeasured. The
previous Step 2 **PARTIAL/NO-GO** status is unchanged.

#### Verified-facts authority boundary — 2026-10-23 (`b312b377`)

This checkpoint records the opt-in downstream authority correction. The
verified-facts path now treats the complete, hash-bound visual snapshot as the
only source-fact representation. Preparation does not load PDF text,
DocMap/legacy evidence, or vector retrieval for that mode; evidence collection,
metrics, quantities, claim support, grounding, public editorial quality, and
scoped regeneration consume the canonical verified-fact projection instead.
Normal validation mode remains on its existing path.

The retained deterministic safeguards are structural and operational: schema
validation, source identity and SHA-256 matching, inspected/supporting physical
pages, per-page source-truth notes, unique fact IDs, exact verified-fact
references, evidence-span/page/source checks, complete visual outcome
accounting, cache/digest identity, regeneration lineage, protected metric
bindings, editorial coverage, and publication-readiness/quarantine behavior.
Composite metrics retain structured `observations` through the metric-spine and
key-figure projections; no regex-based source interpretation or speculative
numeric enrichment was added.

Focused adversarial regressions cover a fact that differs from DocMap text,
composite observations, fabricated numbers, swapped label/value pairs, wrong
timeframes, unsupported expert/distribution claims, regeneration injection,
missing provenance, wrong PDF hashes, invalid references, and unchanged normal
mode. The affected clean-worktree suite passed **726 tests in 24.44 seconds**.
Selected-file Ruff (`F401,F821,I,B017`), compileall, and `git diff --check`
also passed.

**Provider-free retained replay.** The exact retained Step 2 replay covered
the frozen reference set (**15 cases / 39 variants**) with the five matching
source hashes and zero provider calls. The retained Step 2 artifacts do not
contain authoritative `verified_facts` snapshots, so this replay proves
fail-closed handling and regression behavior only; it does not measure fresh
verified-fact generation or live selection quality.

**Live normal-mode regression.** The requested Criteo, Adjust, DoubleVerify,
and Algolia runs were executed from clean SHA `b312b377` with retained PDFs,
GPT-6 Luna High, and no publication flags. All four reached `awaiting_review`
with validation and publication-readiness `pass`, `published=false`, and no
WordPress writes. The aggregate was **150 provider calls**, **1,454,059 input
tokens**, **306,787 output tokens**, **$0.345472 estimated cost**, and
**2,605.674 seconds** total duration:

| Report | Calls | Input + output tokens | Estimated cost | Duration | Artifact mode | Result |
|---|---:|---:|---:|---:|---|---|
| Criteo | 29 | 320,956 + 59,165 | $0.070854 | 411.000 s | normal (`findings`) | awaiting review / pass |
| Adjust | 42 | 336,634 + 86,685 | $0.095921 | 648.616 s | normal (`findings`) | awaiting review / pass |
| DoubleVerify | 37 | 381,335 + 77,386 | $0.085508 | 633.361 s | normal (`findings`) | awaiting review / pass |
| Algolia | 42 | 415,134 + 83,551 | $0.093189 | 912.697 s | normal (`findings`) | awaiting review / pass |

Because the production frozen-cohort runner does not inject a verified-fact
snapshot, these four outputs intentionally exercise unchanged normal mode and
must not be reported as verified-facts editorial evidence. The verified mode
itself is covered by the focused contract, downstream, regeneration, and
fail-closed tests above. No unsupported verified-fact promotion was observed
in the live normal-mode outputs; no independent human PDF review of all normal
mode prose is claimed here.

**Live ten-report normal-mode regression.** The exact ten-member cohort was
then run from the same clean SHA and retained source root in an isolated,
non-publishing worktree. Terminal accounting was complete for **10/10**
members. The aggregate used **372 provider calls**, **3,843,807 input tokens**,
**744,894 output tokens**, **$0.880189 estimated cost**, and **5,240.420
seconds**. Six reports reached `awaiting_review` with validation/readiness pass;
four failed closed. The mutually exclusive terminal ledger was:

| Report | Validation | Readiness / terminal result | Calls | Estimated cost |
|---|---|---|---:|---:|
| DoubleVerify | pass | pass / awaiting review | 28 | $0.064083 |
| KPMG | pass | pass / awaiting review | 37 | $0.099746 |
| Reuters Institute | pass | pass / awaiting review | 37 | $0.093971 |
| Adjust | fail | `summary_safe_removal_target_unresolved` | 54 | $0.125651 |
| Algolia | fail | `validation_failed` | 41 | $0.093094 |
| Bain & Company | pass | pass / awaiting review | 31 | $0.070463 |
| Criteo | pass | pass / awaiting review | 29 | $0.075790 |
| Deloitte | pass | `publish_readiness_failed` | 30 | $0.074602 |
| Emplifi | fail | `validation_failed` | 45 | $0.099696 |
| StackAdapt Inc | pass | pass / awaiting review | 40 | $0.083093 |

All ten remained `published=false` with no WordPress writes. The four failed
rows were not double-counted: Adjust stopped on an unresolved safe-removal
target after deterministic timeframe/provenance repair failures, Algolia and
Emplifi exhausted bounded validation/regeneration paths, and Deloitte passed
validation but failed the publication-readiness gate with an unresolved
retained claim. The separate four-report clean run had Adjust and Algolia pass,
so the retained ten-run failures do not by themselves establish a regression
from this change; they are recorded as live normal-mode reliability limits.

The standard frozen-cohort runner produced normal artifacts for the live
members (`findings` provenance and no authoritative `verified_facts` snapshot),
so neither the four-report nor ten-report generation is evidence that the
verified-facts mode was exercised end-to-end. This is intentional in the
comparison: normal mode remains unchanged. The verified mode is supported by
the focused contract/downstream/regeneration tests and provider-free checks,
but a fresh live generation that injects admitted verified-fact snapshots and
an independent PDF review of every such final output remain outstanding.

**Verdict: PARTIAL.** The implementation establishes the verified-fact
authority boundary and preserves deterministic integrity checks, with normal
mode unchanged. A fresh current-head verified-mode generation with injected
authoritative snapshots is still unavailable, so this does not close the
Step 3 readiness gate.

#### Verified-facts validation authority cleanup — 2026-10-23 (c3dbb844)

This correction narrows verified-facts validation to the authoritative
grounding path without changing normal-mode validation. In
`rules_for_validation_mode`, verified-facts modes no longer run the legacy
`semantic` or `numbers` rules; `verified_facts_grounding` runs only the
grounding rule. `_deterministic_claim_validation_issues` remains structural
and provenance-aware in verified mode, while normal mode keeps its previous
heuristics. `validate_retained_claims` and source/hash/page/reference checks
remain fail-closed.

`_validate_grounding_check_coverage` and `_public_factual_items` now require
verified public items to use known authoritative evidence bindings, have
exactly one identity verdict, carry a supported classification, and include a
substantive explanation. Unknown or missing IDs, malformed verdicts, empty
reasons, contradictory outcomes, and missing authoritative evidence fail
closed. The public editorial `_text_issues` path defers temporal, metric-label,
unsupported-number, and verified-metric-text heuristics in verified mode; the
canonical metric-binding mismatch check remains active. The grounding schema
and cache validator identity were versioned to invalidate incompatible cached
responses. Normal full/inline/deferred registries are unchanged.

The provider-free replay used the existing
`canonical_verified_evidence_packs` projection in memory only. The retained
snapshots for Criteo, Adjust, and DoubleVerify initially failed the existing
validator because their old spans used `source_pack=findings` beside
`verified-fact:*` IDs. That is a retained-artifact lineage limitation, not a
reason to weaken validation; after a read-only canonical rebind, the same
validator passed:

| Report | Facts | Final insights | Metric spine before → after | Key figures before → after | Quality |
|---|---:|---:|---:|---:|---|
| Criteo | 5 | 5 | 4 → 4 | 2 → 2 | pass |
| Adjust | 5 | 5 | 2 → 2 | 2 → 2 | pass |
| DoubleVerify | 5 | 5 | 1 → 1 | 0 → 0 | pass |

The replay made **0 provider calls**, wrote no artifacts, and exercised the
retained outputs only. Algolia has no completed authoritative artifact, and
the retained ten-report records have no authoritative verified-facts snapshots,
so no ten-report verified-mode run or current GPT-6 Luna High quality claim is
made. The earlier live ledgers in this document are historical normal-mode or
prior canary evidence, not fresh evidence for this correction.

Verification results on the clean worktree were **100 focused tests**, **790
expanded affected tests**, and **8,035 tests passed / 2 skipped** in the
repository-wide run with the CPython-3.14-incompatible wheelhouse test
excluded. Type checking, formatting, Ruff F-lint, contract schemas, risk
policy, documentation, agent policy, repository hygiene, public-report
quality, and diff checks passed. The release-evidence prompt fixture remains
red: runtime **66.1648 vs 61.68 seconds**, total tokens **108,624 vs
106,658**, and validation-family tokens **9,835 vs 8,004** (**+22.88%**), with
validation estimated cost **$0.001744 vs $0.001560** (**+11.79%**). This drift
was not hidden or allowlisted because the verified grounding inventory is
intentionally richer.

**Current verdict: PARTIAL / Step 3 not ready.** The structural and grounding
authority fixes are covered, normal mode remains green, and the retained
downstream numeric projections did not lose supported content. Fresh verified
mode generation with authoritative snapshots, Algolia completion, ten-report
coverage, and independent editorial review remain open. No canonical claim,
publication-readiness, or WordPress write occurred.

#### Hosted CI follow-up — 2026-10-23 (`4a89aca0`, run `39910854380`)

The follow-up hosted run passed the full tests/coverage job, both isolated
mutation partitions, formatting, Ruff, risk policy, type checking, the
architecture import gate, agent/role/service-boundary checks, repository
hygiene, contract schemas, documentation/backlog gates, and WordPress
subproject checks (the staging REST check was correctly skipped). The prior
architecture failure was resolved by placing the verified-facts implementation
in the utility layer and retaining a compatibility facade for existing imports;
the latest architecture gate passed.

The release-evidence job's only failed step was the existing prompt-fixture
corpus regression gate. Its measured totals were runtime **43.579091 vs
61.680000 ms**, total tokens **108,624 vs 106,658** (**+1.84%**), and estimated
cost **$0.024084 vs $0.023887**. The validation family measured **9,835 vs
8,004 tokens** (**+22.88%**) and **$0.001744 vs $0.001560** (**+11.79%**).
The gate was not weakened, and all other release-evidence checks completed
successfully; manifest/summary/review generation was skipped because this
regression gate is fail-closed.

This hosted result confirms repository and mutation safety, not fresh
verified-mode editorial quality. No current GPT-6 Luna High verified-facts
generation, authoritative Algolia or ten-report snapshot, independent
full-cohort PDF review, canonical promotion, publication-readiness mutation,
or WordPress write occurred. **Verdict remains PARTIAL / Step 3 not ready.**

#### Verified-facts authority-mode and prompt/cache follow-up — 2026-10-23 (`8bc5d67c`)

The verified-facts cleanup now recognizes the explicit
`verified_facts`/`verified_facts_inline`/`verified_facts_grounding` modes and
the existing visual-authority canary marker as one authority policy. Every
explicit verified request validates the complete hash-bound snapshot before
preparation; missing, empty, malformed, duplicate, or source-inconsistent
snapshots fail closed. Preparation, retained-claim validation, semantic
inputs, grounding payloads, summary evidence, and prompt variables use the
canonical verified-fact evidence projection. Legacy evidence remains available
only in normal mode. The authority policy and mode are part of grounding cache
identity, so a legacy response or a different snapshot cannot be reused across
modes. The normal validation path was not changed.

The focused clean-worktree suite passed **166 tests**. The repository-wide
clean-worktree run passed **8,047 tests with 2 skips** in 5:30, excluding only
the known CPython-3.14-incompatible wheelhouse test. Formatting, Ruff, mypy
(`786` source files, zero issues), and diff checks passed. The target worktree
still contains the user's two pre-existing `artifact_normalization.py` edits;
with those edits present, the focused suite was **165 passed / 1 failed**
because its changed `normalize_artifact_insights()` no longer accepts the
already-covered `verified_mode` keyword. Those edits were not overwritten or
committed.

**Frozen retained replay.** The exact Step 0 five-report replay remained
provider-free and unchanged: **15 cases / 39 variants**, **29 retained
identities**, **29 theme slots**, all five PDF SHA-256 values matched, and zero
provider calls. This is an input/provenance regression result, not evidence of
improved live selection quality.

**Live retained Adjust shadow claim.** One real shortlisted Adjust claim,
`multiplatform-measurement`, was evaluated against the retained PDF and
completed `verified` on the first correction and verification attempts. The
source binding remained Adjust's expected SHA-256 and physical page **11**;
the corrected response added the page-supported approximately-31% marketer
satisfaction statistic and the independent verification accepted the final
claim. The isolated run used **2 GPT-6 Luna calls**, **22,944 input + 1,607
output tokens** (**24,551 total**), estimated **$0.003098**, and **23.39 s**.
`canonical_mutation=false`; no canonical artifact, readiness state, or
WordPress write changed.

**Live verified-mode validation attempt.** A retained Adjust snapshot with
**5 authoritative verified facts** and the matching PDF hash was projected in
memory through the existing `project_verified_facts_as_insights` and canonical
evidence-pack helpers, then sent through `validation_mode=verified_facts`.
The run made **4 GPT-6 Luna grounding calls**, **20,383 input + 19,924 output
tokens** (**40,307 total**), estimated **$0.011694**, and failed closed with
**9 issues**: four artifact-quality, three grounding, and two retained
soft-copy-provenance issues. The retained artifact's public spans still label
verified-fact IDs with the legacy `findings` source pack, and the deliberately
minimal in-memory projection did not supply all editorial/provenance context.
This is evidence that the new boundary refuses an inconsistent retained
snapshot; it is not a passing end-to-end editorial-generation result and no
authority or validator was weakened to make it pass.

**Prompt/cache evidence.** The required three-iteration fixture command still
fails closed: runtime **51.0168 vs 61.6800 ms**, total tokens **108,348 vs
106,658** (**+1.58%**), total cost **$0.024057 vs $0.023887**, and validation
tokens **9,559 vs 8,004** (**+19.43%**) with validation cost **$0.001717 vs
$0.001560** (**+10.06%**). Grounding prompt tokens decreased by **87**; the
remaining validation drift is in the existing editorial-review and visual
correction/verification prompt families. No threshold, baseline, allowlist,
or factual safeguard was changed.

**Verdict: PARTIAL / Step 3 not ready.** The verified-facts source authority,
mode-separated cache identity, normal-mode compatibility, and fail-closed
tests are complete. Live Step 2 shadow evidence is source-bound and safe, but
the retained verified-mode editorial validation attempt did not pass, the
prompt-fixture release gate remains red, and no full fresh verified five-report
editorial cohort was run. Step 2 remains shadow-only; no canonical promotion,
publication-readiness mutation, or WordPress write occurred.

#### Canonical semantic-input authority and grounding prompt cleanup — 2026-10-23

This follow-up closes the lower-level verified-grounding bypass without adding a
validator stage or provider call. `run_grounding_check()` still builds
canonical verified-fact evidence once, but now checks any supplied retained
semantic package and semantic inputs against the current source identity,
candidate identity, canonical `verified-fact:*` statements, and the existing
semantic evidence hash before prompt preparation or cache reuse. Stale text,
source identity, duplicate, incomplete, or omitted inputs fail closed with a
typed non-retryable error. Normal-mode construction and validation remain
unchanged. The valid precomputed-input path is covered as well, so callers do
not pay for unconditional reconstruction.

The grounding authority policy now lives only in the system prompt. Legacy mode
explicitly retains file-search/original-visual corroboration, visible
row/callout/connector/legend binding, OCR-order caution, and visual label
reversal checks. Verified mode instead checks complete metric tuples only
against the canonical verified fact. The user prompt no longer repeats the
authority policy or the system-owned coverage/classification/schema rules.

The exact unchanged prompt-fixture gate was run with three iterations. It
remains fail-closed, with no baseline, threshold, pricing, or allowlist change:

| Prompt namespace/family | Current tokens | Baseline tokens | Delta | Current cost | Baseline cost | Delta |
|---|---:|---:|---:|---:|---:|---:|
| `report_vs/artifacts/insights_candidates` | 3,634 | 3,569 | +65 | $0.000643 | $0.000637 | +$0.000006 |
| `report_vs/artifacts/insights_final` | 3,377 | 3,307 | +70 | $0.000618 | $0.000611 | +$0.000007 |
| `report_vs/validate/editorial_review` | 2,030 | 1,362 | +668 | $0.000355 | $0.000288 | +$0.000067 |
| `report_vs/validate/grounding` | 2,163 | 2,323 | -160 | $0.000368 | $0.000384 | -$0.000016 |
| `report_vs/validate/visual_claim_correction` | 1,837 | 1,598 | +239 | $0.000336 | $0.000312 | +$0.000024 |
| `report_vs/validate/visual_claim_verification` | 2,536 | 1,801 | +735 | $0.000406 | $0.000332 | +$0.000074 |
| validation family | 9,486 | 8,004 | +1,482 (+18.52%) | $0.001709 | $0.001560 | +$0.000149 |
| all fixture namespaces | 108,275 | 106,658 | +1,617 (+1.52%) | $0.024049 | $0.023887 | +$0.000162 |

All other namespace token and cost deltas were zero. The increase is therefore
not caused by the shared grounding policy change: grounding decreased. The
remaining validation increase is concentrated in the existing independent
editorial-review and visual correction/verification instructions that protect
source pages, metric tuples, populations, periods, and output completeness.
Those requirements were not removed merely to fit the historical baseline.

The provider-free frozen replay passed for the exact **15 reference cases / 39
variants**, with all five pinned PDF hashes present and matching, and **29
retained real-report identities / 29 theme slots**. It made zero provider calls
and is an input/provenance check rather than evidence of live model quality.
The retained DoubleVerify and Adjust artifacts were inspected against the
original PDFs. DoubleVerify pages 8, 9, and 10 support the Engagement Index
definition, normalization, and the APAC/North America in-app versus mobile-web
composite tables. Adjust pages 6, 9, 11, 21, and 34 support the retained
install/session, AI-efficiency, marketer-satisfaction, retention, and
finance-install/session bindings. The protected fields, source identities,
physical pages, and evidence references in those retained artifacts were not
enriched with unsupported values.

An isolated live verified-mode validation replay used the existing GPT-6 Luna
route, canonical in-memory verified-fact projections, and no publication path.
The retained snapshots required a read-only source-pack rebind because their
old verified-fact spans still carried `source_pack=findings`; the authoritative
validator correctly rejected the unreconciled form. After that projection,
Adjust made **9 ledger provider events** (**7 grounding batches plus 2
structured-output recovery calls**), consumed **60,819 input + 52,890 output
tokens**, and cost **$0.031622**. DoubleVerify made **10 ledger provider
events** (**6 grounding batches plus structured-output recovery calls**),
consumed **71,270 input + 52,435 output tokens**, and cost **$0.032438**.
Both runs failed closed because the retained minimal replay did not produce a
substantive schema-valid grounding artifact; neither marked an unsupported
claim verified. Adjust retained only the quotes-missing warning in addition to
that grounding error. DoubleVerify additionally exposed broader summary/core
signal warnings. These runs are reliability evidence, not a passing end-to-end
editorial result. No canonical artifact or WordPress write changed.

Focused regression verification produced **169 passed / 1 failed**. The single
failure is pre-existing worktree state: the user's uncommitted
`artifact_normalization.py` edit removes the already-supported `verified_mode`
keyword from `normalize_artifact_insights()`. The changed grounding module and
three changed test modules pass targeted Ruff/format checks; grounding mypy
passes. The repository Ruff gate passes. The repository formatting gate and
full mypy are blocked only by the same unrelated worktree changes, including
the untracked duplicate `artifact_normalization (2).py`; neither file is part
of this correction.

**Current verdict: PARTIAL / Step 3 not ready.** Canonical verified semantic
inputs cannot bypass the verified-fact evidence/source boundary, authority
instructions are unambiguous, normal mode is preserved, and no additional LLM
stage was introduced. The release prompt-fixture gate remains red and a fresh
verified five-report editorial-quality pass is not established; those are the
remaining blockers.

#### Hosted CI for canonical semantic-input correction — 2026-10-23 (`8fce73a1`, run `39934588808`)

The hosted `tests` job passed the repository test/coverage suite and all
formatting, Ruff, type, architecture, policy, schema, documentation, hygiene,
and WordPress subproject checks. Both isolated mutation partitions also passed.
The only failed job was `release_evidence`, whose unchanged prompt-fixture
gate reproduced the measured regression: **108,275 vs 106,658 total tokens
(+1,617, +1.52%)** and **9,486 vs 8,004 validation-family tokens (+1,482,
+18.52%)**; estimated cost was **$0.024049 vs $0.023887** overall and
**$0.001709 vs $0.001560** for validation. Runtime and OCR/browser-count
metrics did not fail the gate. No release threshold, baseline, pricing, or
allowlist was changed.

This is the terminal hosted result for the code correction. It confirms the
canonical-input and prompt-authority changes pass the repository safety and
mutation gates, but the release-evidence status remains red because the
historical prompt corpus does not yet accept the existing Step 2 validation
instruction inventory. **Overall status remains PARTIAL; Step 3 is not ready.**

#### Prompt fixture baseline acceptance — 2026-10-23

The prompt corpus baseline was regenerated with the repository tooling
(`scripts/quality/build_prompt_fixture_corpus_baseline.py`, three iterations,
current `src/config/app.yaml`). No token, price, threshold, fixture, model, or
allowlist values were edited manually. The unchanged regression command now
passes against the regenerated baseline.

The stable old/new comparison is:

| Scope | Old tokens | New tokens | Delta | Old cost | New cost | Cost delta |
|---|---:|---:|---:|---:|---:|---:|
| all fixture namespaces | 106,658 | 108,275 | +1,617 (+1.52%) | $0.023887 | $0.024049 | +$0.000162 |
| validation family | 8,004 | 9,486 | +1,482 (+18.52%) | $0.001560 | $0.001709 | +$0.000149 |

The affected namespaces are `report_vs/artifacts/insights_candidates` (+65
tokens, +$0.000006), `report_vs/artifacts/insights_final` (+70, +$0.000007),
`report_vs/validate/editorial_review` (+668, +$0.000067),
`report_vs/validate/visual_claim_correction` (+239, +$0.000024), and
`report_vs/validate/visual_claim_verification` (+735, +$0.000074).
`report_vs/validate/grounding` decreased by 160 tokens and $0.000016 after the
duplicate user-side policy text was removed. All other namespace token and
cost values are unchanged. The regenerated runtime metadata is nondeterministic
and the fixture path/timestamp reflect this worktree; neither is a quality
assertion.

The net increase is accepted because it comes from the intentional factual
grounding inventory: canonical evidence authority, complete protected metric
dimensions, complete verdict coverage, and independent editorial factual
review. The increase is negligible in absolute cost and no factual-validation
coverage or release threshold was reduced to fit the historical baseline.
The prior hosted release-evidence failure was therefore a stale-baseline
failure, not a prompt-quality failure. This update changes only the measured
baseline; the regression gate and its enforcement remain unchanged.

The current status remains **PARTIAL / Step 3 not ready** pending a fresh
verified-mode real-report editorial-quality run and final hosted CI evidence.

#### Post-CI prompt-baseline and retained-PDF editorial evaluation — 2026-10-23

The regenerated prompt baseline was committed as `bd51264a` and pushed. Hosted
run `39949908828` passed all jobs: tests/coverage, both mutation partitions,
static/type/policy/schema/documentation/hygiene gates, the WordPress subproject
checks, and `release_evidence`. The release gate now accepts the measured
baseline; its thresholds, pricing, fixtures, model configuration, and factual
validation inventory were not changed.

The exact provider-free frozen-five replay still passed as an input and
provenance check: **15 reference cases / 39 variants**, **29 retained real
shortlist identities**, **29 theme slots**, and five matching pinned PDF
hashes. It made zero provider calls and is not live model-quality evidence.

The existing live Step 2 replay was then run against retained artifacts using
GPT-6 Luna High, full rendered PDF pages, and the frozen source manifest. It
was shadow-only (`canonical_mutation=false`, `publication_write=false`):

| Scope | Claims | First pass | After retry | Failed closed | Provider calls | Input / output tokens | Cost | Wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Adjust + Criteo + DoubleVerify | 15 | 7 | 3 | 5 | 46 | 393,955 / 43,184 | $0.060986 | 602.835 s |
| Algolia | 6 | 4 | 1 | 1 | 16 | 562,234 / 17,685 | $0.065066 | 295.758 s |

The outcomes are mutually exclusive. No claim was unavailable or skipped;
failed claims exhausted the existing two correction/two verification attempt
limits. Six terminal failures were rejected after malformed verification
responses (`verification_response_invalid` and
`verification_response_malformed`), rather than being promoted. All four
source hashes matched the manifest. The replay selected no replacement
artifact candidates because retained Step 1 artifacts do not carry the
replacement-candidate structure required by the existing shadow selector; no
downstream artifact was regenerated from this evaluation.

Independent editorial review used the existing source-grounded review workflow
and the same full PDF pages. For the 15-claim Adjust/Criteo/DoubleVerify set,
identity and page coverage passed, all 10 terminally verified claims were
approved, and the five failed Step 2 claims remained unresolved. The review
made 10 calls, used 82,139 input + 8,504 output tokens, cost $0.012466, and
took 110.537 s. DoubleVerify's five accepted claims match the Q1 2026
composite/index relationships on PDF pages 8–10; Adjust's accepted claims
match pages 6, 11, and 34; and Criteo's accepted claims match the 2023
recommendation and cost pages 7–8. No render failures or page mismatches were
found in this set.

Algolia's independent review also had complete six-claim identity coverage
and no render failures, but its acceptance status was PARTIAL: four claims
were approved, one required revision, and one remained unresolved. The
revision-required claim (`search-investment-and-adoption-activity`) has the
right page-23 values but omits that the 53%/51% figures are total respondents'
self-reported investment levels. The accepted `revenue-incentive-58` rewrite
is visibly supported by page 5 and commercially relevant to the report's
search topic, but its stable ID/evidence text still names the original revenue
proposition; this is a retained-lineage limitation, not evidence that the
original claim was true. The `agentic-search-deployment-and-plans` correction
is factually supported by page 26, but the independent reviewer also found a
page-9 binding and blocked acceptance pending source-page reconciliation.
The `agentic-adoption-considerations` claim failed closed after two malformed
verification responses. The Algolia review made 5 calls, used 162,215 input +
5,746 output tokens, cost $0.019094, and took 80.583 s.

The public-report quality gate was run against the retained Adjust, Criteo,
and DoubleVerify artifacts. It found no internal-ID leaks or duplicate
insights, but each artifact remains blocked by 20
`public_editorial_quality.material_claim_evidence_missing` findings because
its retained public spans still use the legacy `findings` source pack rather
than the authoritative verified-fact pack. This is a known retained-lineage
limitation; the current evaluation did not silently repair or publish it.

Compared with the retained Step 1/verified-fact canary baseline, the new
replay provides direct current-head factual and editorial evidence for the
three completed downstream artifacts plus Algolia's retained visual claims,
but it does not prove improved live selection quality or produce a new
publishable artifact. No WordPress write, canonical mutation, or publication
readiness change occurred.

**Current verdict: PARTIAL / Step 3 not ready.** Prompt-fixture CI is green
with the intentional negligible baseline increase accepted. Real-report
verified-mode factual review is safe and fail-closed, but Algolia still needs
the population qualifier and source-page reconciliation, and the retained
public evidence-pack lineage requires a real downstream regeneration before
promotion. These are the remaining blockers; no factual safeguard was
weakened.

#### Verified-facts P1/P2 correction pass — 2026-10-23

The finalizer/regeneration audit identified the remaining producer-side
lineage defect. `assemble_artifacts_payload()` already builds fresh verified
mode projections from the admitted visual-fact pool, but
`finalize_regeneration_candidate_artifacts()` could restore the promoted
baseline's discovery-era roots and soft-copy `source_spans` after assembly.
That left canonical `verified-fact:<fact_id>` IDs paired with legacy
`findings` provenance in retained public artifacts. Verified regeneration now
keeps the assembled summary, insight candidates/finals, expert comment, and
LinkedIn roots in its atomic patch, then reuses
`bind_artifact_evidence_spans()` and `artifact_evidence_span_index()` after
baseline reconciliation. Soft-copy spans and public evidence text are rebuilt
only from the canonical index; an absent canonical span remains unbound and is
not guessed. Normal-mode finalization is unchanged. A focused regression
passes for insight candidates/finals and soft-copy provenance; the clean-head
authority canary/regeneration suite passes **32 tests**.

The visual verification boundary had a second structural gap:
`_verification_attempt()` could return a terminal `verified` attempt when page
notes were complete but `verified_fact` was absent. The result adapter later
quarantined the claim, but the terminal attempt was misleading and did not
exercise the normal bounded failure path. A missing authoritative fact now
becomes a rejected verification attempt with
`verification_verified_fact_missing`; the existing maximum of two verification
attempts remains unchanged. Focused visual tests pass (**46 passed** in the
task worktree), including the new missing-fact regression and continuation
after permanent provider errors.

The retained malformed-response audit classified **16** cached verification
responses: **12** had `Extra data` from concatenated JSON objects and **4** had
`Unterminated string` truncation. The existing response-payload recovery
utility already extracts a complete first JSON object, so the image-backed
OpenAI boundary now enables that recovery path. Incomplete recovered objects
still fail the existing schema/completeness checks closed; no retry count or
output budget was increased. A service regression covers concatenated image
responses. The prior six claim failures therefore remain visible when the
recovered object is incomplete rather than being promoted on page notes alone.

The Algolia review did not demonstrate a missing canonical population field:
the admitted `verified_fact` retains the total-respondent qualifier for the
53%/51% page-23 metric. The retained final prose still omits that qualifier,
so it remains an editorial revision blocker rather than a deterministic
population rule. The agentic-search correction is authoritative on page 26;
the independent review's additional page-9 binding is not in the Step 2
supporting-page set and remains blocked by source-page reconciliation. No
Algolia-specific parser or semantic judge was added.

Prompt baseline reproducibility was corrected through the existing builder.
`fixture_path` is repository-relative and `generated_at_utc` is retained as an
empty schema-compatible field. Runtime references are preserved from the
previous baseline because they are host-noisy, while current token, cost,
model, namespace, and coverage values are still regenerated. Two consecutive
builder runs produced the same SHA
`12835943703A84A668843CCC779BB330389417F3059759D53362DC435FDB9066`.
The unchanged prompt gate passes with **108,275 total tokens / $0.024049** and
**9,486 validation-family tokens / $0.001709**; these are unchanged from the
accepted corrected baseline. The focused prompt regression suite passes **9
tests**.

The retained real-report replay remains the latest live evidence: Adjust +
Criteo + DoubleVerify had **7 first-pass, 3 after-retry, and 5 failed-closed**
outcomes across 15 claims; Algolia had **4 first-pass, 1 after-retry, and 1
failed-closed** across 6 claims. Those outcomes were recorded before the
producer fixes above and must not be presented as a fresh post-fix quality
improvement. The public-quality gate still reports historical retained-lineage
failures where old spans use `findings`; the clean producer regression is the
evidence for the correction, and no canonical or WordPress write was made.

**Current verdict: PARTIAL / Step 3 not ready.** The new producer, visual
completeness, parser-boundary, and reproducible-baseline regressions are
implemented without weakening factual safeguards. Fresh post-fix live
editorial generation and reconciliation of the retained public artifacts are
still required before promotion; the Algolia population wording and
page-9/page-26 review findings remain unresolved quality blockers.

#### Verified-facts JSON/provenance correction and fresh retained-PDF replay — 2026-10-23

This correction pass addressed two producer-side P1 defects without adding a
validator or another model stage:

- Image-backed Responses requests now use the provider-supported JSON-object
  response format. The existing first-complete-object recovery remains a
  fallback, while a Responses result whose provider status is explicitly not
  `completed` is treated as non-JSON for this path. Provider status and
  `incomplete_details.reason` are retained as bounded diagnostics. Normal
  Responses callers keep their existing behavior.
- Visual verification now has an explicit `gpt-6-luna`/High policy with a
  **16,384-token ceiling**. Correction remains **4,096**; the two correction
  and two verification attempt limits are unchanged. The cache key already
  includes response format and output budget, so old lower-budget entries
  cannot satisfy the new verification policy.
- Verified regeneration now reuses the existing
  `artifact_evidence_span_index()`/`bind_artifact_evidence_spans()` boundary
  and replaces `evidence_spans`, page fields, and evidence text from resolved
  canonical spans. If a `verified-fact:` ID has no canonical span, those
  fields are cleared instead of retaining discovery-era text. Normal-mode
  finalization is unchanged.

The retained malformed-response audit contains **16 classifications** (12
concatenated objects reported as `Extra data`, four truncated strings reported
as `Unterminated string`). The retained audit did not include raw response
payloads, so those exact 16 payloads could not be replayed byte-for-byte.
Provider-free recovery and incomplete-status regressions are covered by the
focused tests; the fresh live run below had **zero malformed or incomplete
responses**. This distinguishes syntax recovery coverage from evidence that a
new provider request would have emitted malformed JSON.

The exact frozen-five provider-free replay remained stable: **15 reference
cases / 39 variants, 29 retained identities, 29 theme slots, five matching
PDF SHA-256 values, and zero provider calls**. This is input/provenance
evidence, not live selection-quality evidence.

The fresh shadow replay used the retained real shortlist and the exact
hash-matched PDFs for Criteo, Adjust, DoubleVerify, and Algolia. It evaluated
all **21** available retained claims, with full rendered pages and GPT-6 Luna
High (`reasoning_effort=high`), and made no canonical or publication write:

| Report | Claims | First pass | After retry | Unresolved/failed/skipped | Pages inspected | Key source check |
|---|---:|---:|---:|---:|---|---|
| Criteo | 5 | 5 | 0 | 0 | 5, 7, 8 | 51/45 and 47/40 recommendations, 61% ROI expectation, and 22% US cost estimate match the cited text. |
| Adjust | 5 | 5 | 0 | 0 | 6, 9, 11, 21, 34 | 10%/7% global growth, 31% cross-platform satisfaction, 5% day-30 retention, and finance install/session values match the cited pages. |
| DoubleVerify | 5 | 5 | 0 | 0 | 3, 8, 9, 10 | APAC/North America rates, 20+ engagement inputs, normalized-100 context, and regional video indices match the composite tables. |
| Algolia | 6 | 5 | 1 | 0 | 5, 9, 12, 22, 23, 27 | Total-row qualifiers, 49/27/23 search approaches, regional 68/57/63 purchase values, and 17/61 agentic-search categories are retained. |

The terminal counts are mutually exclusive: **20 verified first pass, one
verified after retry, zero unresolved, zero failed verification, and zero
skipped**. The run made **44 provider calls** (22 corrections and 22
verifications), used **678,301 input / 47,738 output / 726,039 total tokens**,
cost **$0.091701**, rendered **19 pages**, and took **596.144 seconds**.
Correction/verification configured ceilings were 4,096/16,384; observed
maximum output usage was 1,741/2,341 tokens. All 44 ledger rows reported
provider status `completed` and parse status `valid`; cache was enabled in an
isolated directory, with no measured cache reuse. These are measured runtime
values from `out/verified_claims_post_fix_live_four_20261023/result.json`, not
reference estimates.

The previous retained ledgers are not treated as a controlled before/after
experiment. Their separate runs summed to 11 first-pass, four after-retry,
and six failed-closed outcomes across 21 claims, 62 calls, approximately
1,017,058 tokens, and $0.126052. The new run is observed post-fix evidence;
the different retained inputs, page recovery, and provider sampling prevent a
causal quality claim from the aggregate comparison alone.

The source-page and wording review found no independently confirmed
unsupported material claim in these 21 terminal results. In particular,
`revenue-incentive-58` now says “Total 2025”/“Total 2024” for the 53%/51%
search-investment rows, and `search-investment-and-adoption-activity` calls
53%/51% adequate site-search investment rather than ongoing investment. The
agentic-search correction inspected physical pages **26, 9, and 27**; the
current verified fact uses the visual response's supporting page **9**, while
the retained original page list is empty. Page 9 and page 26 both visibly
contain the same 17% implemented / 61% next-12-months Total n=1,100 chart, so
the current page-9 support is not an unsupported stale-original promotion.
Exact reconciliation to page 26 remains a provenance-review limitation and
is recorded rather than hidden.

This replay stopped at the existing Step 2 visual-shadow boundary. It did not
create a fresh canonical verified-fact snapshot and therefore did not claim a
full post-fix PDF → verified-fact admission → editorial regeneration →
grounding → public-quality artifact run. Existing retained downstream
artifacts still contain legacy evidence-pack lineage and are not post-fix
evidence. No WordPress write occurred.

Focused tests passed **281 tests**; the prompt fixture gate passed at the
accepted baseline of **108,275 tokens / $0.024049** (validation family 9,486 /
$0.001709). The clean affected-worktree suite passed **324 tests in 17.21s**;
formatting, Ruff, and mypy passed there, including **786 source files with no
type errors**. The actual shared worktree remains locally non-representative
because the user-owned dirty `artifact_normalization.py` and untracked
duplicate file remove the `verified_mode` parameter and produce eight known
mypy errors; those files were not changed or staged. Hosted run
`40002252041` on `1abff7409c5c68d49f35740aed6d808616996a49` passed `tests`,
both mutation partitions, and `release_evidence`, including the prompt-fixture
and release-evidence gates.

**Current verdict: PARTIAL / Step 3 not ready.** The provider JSON contract,
incomplete-response handling, output headroom, and canonical evidence clearing
are corrected and covered. The fresh visual shadow replay is strong and
fail-closed, but the missing raw malformed payloads, page-9/page-26
reconciliation limitation, and absence of a fresh downstream canonical/public
artifact keep promotion blocked.

#### Downstream verified-fact E2E checkpoint — 2026-10-23

This checkpoint exercised the existing downstream path after the retained
Step 2 visual result: verified-fact admission, editorial generation, final
insights, summary/metric-spine/key-figure projection, semantic grounding,
public-report quality, and final artifact inspection. It used the retained
hash-matched PDFs and the existing GPT-6 Luna High Step 2 result; it made no
visual provider calls, canonical persistence, readiness mutation, publication,
or WordPress write. It is therefore downstream integration evidence, not fresh
Step 1 selection or live source-recall evidence.

| Report | Admission | Final artifact | Downstream result | Observed calls / tokens / cost / wall time |
|---|---:|---:|---|---|
| Criteo | 5/5 | 5 insights; 5 metric-spine rows; 3 key figures | Validation **FAIL**: three substantive grounding errors about population/attribution scope; protected evidence and metrics passed | 14; 125,530 input + 67,938 output (14,526 cached input); $0.045216; 337.972 s |
| Adjust | 5/5 | 5 insights; 5 metric-spine rows; 3 key figures | Validation **PASS** with warning-only quote abstention and summary-breadth warnings | 13; 111,414 input + 56,115 output (12,849 cached input); $0.038042; 257.975 s |
| DoubleVerify | 5/5 | 5 insights; 5 metric-spine rows; 1 key figure | Validation **FAIL**: two grounding errors for unsupported unit/denominator/observation qualifiers; one comparison remained informational | 15; 144,114 input + 74,110 output (14,526 cached input); $0.050158; 399.882 s |
| Algolia | 0/6 final admission | No final artifact | Fail-closed: the retained six-fact result did not map to the five selectable editorial themes/evidence-pack snapshot; no fact was promoted | Diagnostic attempts accumulated 19 ledger rows; not used as a quality/cost comparison |

For the three completed artifacts, all five admitted facts per report remained
`verified-fact:*` bindings; every final insight retained physical-page spans;
field-level protected metric comparisons found **0 mismatches**; and no
evidence ID, page, span, source hash, or protected binding was promoted from a
final-only rewrite. The PDF review checked the cited native pages directly:
Criteo pages 5/7/8, Adjust pages 6/9/11/21/34, and DoubleVerify pages
3/8/9/10. Numeric values and category relationships in the final insight
texts were present on the cited pages; the non-numeric Criteo omnichannel
statement was supported by the page-8 narrative. Public-report quality passed
for all three completed artifacts (one report each, no remediation targets,
no duplicate-insight delta, and full advisory/so-what/now-what coverage).

The production changes exercised here are deliberately narrow: the selector
cache identity advanced to `evidence_backed_shortlisting:8` after stable
verified-fact fallback identities were preserved; complete protected metric
bindings are restored including empty fields; and exact repeated public
grounding rows are collapsed only when their text, evidence IDs, retained
evidence, classification, and source identity all match. Focused regressions
cover those paths and retain fail-closed behavior for conflicting bindings.

The Algolia result is an editorial coverage/lineage limitation, not a reason
to weaken admission: the six evaluated verified facts include an extra
`search-investment-and-adoption-activity` identity that the retained plan did
not select, and a correctly scoped two-phase replay still failed the existing
snapshot evidence-pack consistency check. No final artifact is claimed for
Algolia. Criteo and DoubleVerify remain blocked by substantive downstream
grounding validation, despite clean provenance and protected-field checks.
These results do not show a causal live-selection improvement because the
visual result and retained shortlist were replay inputs. **Verdict: PARTIAL /
Step 3 not ready.**

The final pushed checkpoint is `3e85cca9acd317d32a32f40b195792ca76c28914`.
Hosted CI run `40021563321` passed `tests`, both mutation partitions, and
`release_evidence`; the formatting-only follow-up also left all production
changes and the documented PARTIAL / Step 3-not-ready verdict unchanged.

#### Verified grounding complete-fact context correction — 2026-10-24

The verified grounding payload previously projected each authoritative metric
through a fixed twelve-field dictionary. That was the exact information-loss
boundary: report-specific fields such as `label`, `confidence`,
`forecast_status`, nested observation qualifiers, composite-methodology data,
and conditional assumptions were absent from the `insights_final` grounding
input even though they were present in the validated `verified_facts` snapshot.
The canonical evidence text remained source-bound, but it was not a substitute
for the complete fact object.

The minimal correction is verified-mode-only. `grounding_payload()` now deep
copies the complete validated authoritative metric object, while normal mode
keeps its existing projection. The payload carries the complete canonical fact
snapshot, and `_grounding_batches()` forwards only the fact objects referenced
by that batch under `canonical_verified_facts`. The existing system prompt now
binds each `verified-fact:<id>` evidence ID to that object and explicitly
prohibits final-artifact metric fields from extending or overriding it. The
grounding validator identity advanced from `grounding_validation_output:1.7`
to `:1.8`; existing relevant-input, prompt-content, and family-reuse checks
therefore cannot reuse a pre-change result. No new validator, service, model
call, or output contract was introduced.

Provider-free retained-payload comparison used the hash-matched Criteo and
DoubleVerify artifacts from the 2026-10-23 downstream checkpoint. This compares
the exact provider input shape; it is not a fresh live model-quality claim:

| Report | Selected facts / insights | Public items / batches | Old report JSON tokens | New report JSON tokens | Delta |
|---|---:|---:|---:|---:|---:|
| Criteo | 5 / 5 | 40 / 5 | 17,704 | 32,325 | +14,621 |
| DoubleVerify | 5 / 5 | 37 / 5 | 17,408 | 34,758 | +17,350 |

The token counts above use the local `o200k_base` tokenizer over each complete
batch `report_json`; they exclude the system/user prompt wrapper and provider
output. The new input contains all fact fields and batch-scoped canonical
provenance. The old projection exposed only the prior fixed metric keys. No
new provider call, cost, or latency was incurred by this replay. The unchanged
fixture gate passed with total **108,429 tokens / $0.024065** versus the
accepted baseline **108,275 / $0.024049** (+154 tokens / +$0.000016); the
validation family was **9,640 / $0.001725** versus **9,486 / $0.001709**.
Thresholds, fixtures, pricing, and factual checks were unchanged.

The retained model outputs were reapplied through the corrected grounding
boundary without a provider call. Criteo retained **69 checks / 3 unsupported**
and returned the same **3 `not_established` grounding issues** as the retained
result. DoubleVerify retained **66 checks / 3 unsupported** and returned the
same **3 `not_established` issues** (two error-level metric qualifier issues
and one informational comparison issue). This confirms the correction does not
silently turn existing failures into passes. The source review also checked the
full PDF pages directly: Criteo pages 5/7/8 contain the 61% ROI expectation,
22% US cost estimate, and 51%/45% plan comparison; DoubleVerify pages 3/8/9/10
contain the 8.0%/3.7% regional rates, 20+ engagement definition, normalized-100
window, and North America video table. The remaining Criteo failures concern
combining distinct respondent populations/attribution scope; the remaining
DoubleVerify failures concern qualifiers that the editorial metric wording
does not establish as a complete tuple. They remain fail-closed and were not
forced through by the added context.

Focused regressions cover unfamiliar nested metrics, composite observations
with multiple units/populations/timeframes, conditional forecast assumptions,
same-number contradictory editorial wording, final-only metric fields, and
batch-level canonical-fact availability. The new regressions passed **3/3**;
the affected top-level grounding/claim/prompt suite passed **401 tests**. The
shared worktree also has one known pre-existing local failure in
`test_verified_composite_metric_survives_normalization_and_metric_spine`
because the user-owned dirty `artifact_normalization.py` removes its
`verified_mode` parameter; that file and its untracked duplicate were not
changed or staged. Ruff and mypy passed for the changed grounding/contract/test
files. No canonical, publication, or WordPress write occurred.

**Verdict: PASS for the targeted grounding-input correction; Step 2 remains
PARTIAL / NO-GO.** The canonical fact cannot be bypassed by the lossy metric
projection and cache identity is invalidated. The provider-free replay does not
establish that a new model call would change Criteo or DoubleVerify editorial
verdicts, and no live improvement claim is made. Step 3 remains not ready.

#### Root-cause investigation: Criteo, DoubleVerify and Algolia — 2026-10-24

This investigation was provider-free and read-only. It used the retained
`artifacts.json`, grounding materializations, retained validation results,
selection/admission diagnostics, and the hash-matched PDFs. It did not call a
provider, mutate a canonical artifact, or write to WordPress. The direct source
identities were Criteo
`17cf2e92c8804e35274faf3dd416db2fe6e4a81d7aa92418ada8ba90ee77c00c`,
DoubleVerify
`99f0cc4f7787cac52b7f89eefa7659053b3703ea100b9e0522fa500c64463d7e`, and
Algolia
`d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50`.

The exact frozen-five provider-free gate was also rerun with the existing
`scripts/quality/replay_verified_claims_step2.py --provider-free` workflow. It
covered **15 reference cases / 39 variants**, found all five expected PDF
hashes, and reported retained shortlist counts of **5/7/5/6/6 = 29** for
Capgemini, Activate, KPMG, Reuters Institute, and Adjust. It made zero provider
calls and therefore establishes input and provenance availability only, not
visual correction or grounding quality.

##### Criteo: source and canonical fact are supported; the retained failure is an old grounding-authority failure

The chain is deterministic through the source and Step 1 artifact:

| Stage | Retained evidence | Finding |
|---|---|---|
| PDF | `out/browser_downloads/www.criteo.com/1fd90493947a/Agency-Guide-Report-Criteo.pdf`, physical page 5 | The 61% newer-channel ROI expectation is printed on the page. The same page’s table identifies the recommended-spend population as global media agency professionals and shows 19% retail media, 20% search, and 19% social. Pages 7 and 8 separately support the 22% US cost estimate and 51%/45%, 47%/40% plan comparisons. |
| Visual fact | `channel-roi-expectation`, page 5 | The verified fact preserves the separate ROI-response and global-spend populations, the recommendation/expectation status, and the source-truth note. Its source hash matches the PDF. |
| Final artifact | `channel-roi-expectation` | The final insight wording is the valid 61% expectation. The downstream key figure, expert comment, and LinkedIn rows additionally state the spend recommendations. |
| Retained grounding result | three `not_established` errors | The errors are on `key_figures:channel-roi-expectation.figure`, `expert_comment`, and `linkedin_post`; all reject the global-media-agency attribution for the spend rows. |

The original failure is not a PDF or Step 1 extraction failure. Before the
complete-fact correction, `grounding_payload()` reconstructed a fixed metric
projection and did not provide a canonical verified-fact object bound to the
`verified-fact:channel-roi-expectation` evidence ID. Some metric fields,
including `cohort`, appeared in the public claim text, but they were not
authoritative evidence with the source-truth/provenance contract. The old model
therefore treated the population statement as an unsupported final-artifact
addition even though the canonical fact and physical page support it. The
current code’s complete metric and `canonical_verified_facts` map address that
information boundary. A fresh model result has not been obtained, so it is not
yet proven that the new input changes the verdict.

##### DoubleVerify: two context failures and one genuine evidence-scope failure

| Claim | Source review | Retained result | Root-cause classification |
|---|---|---|---|
| `q1-2026-north-america-video-attention-by-environment.metric` | Physical page 10 contains the North America video values 128 In-App, 93 Desktop, and 88 Mobile Web. | Error: unit, denominator, and observed/forecast qualifiers were not established. | **Probable old authority-context failure.** The canonical fact explicitly records the unit as an index value, denominator as not stated, and forecast status as not identified. Those fields were not available as a complete canonical object in the retained pre-correction grounding request. |
| `q1-2026-brand-suitability-regional-spread.figure` | Physical page 3 contains 8.0% APAC and 3.7% North America under Brand Suitability Violation Rate; the source line identifies DV internal tag-based open-web data. | Error: denominator and observed/forecast characterization were not established. | **Probable old authority-context failure.** The canonical fact explicitly records the missing denominator/sample size and non-forecast ambiguity. The numeric tuple itself is source-supported. |
| `q1-2026-north-america-video-attention-by-environment.so_what` | Page 10 supports North America only. The APAC comparison is supported by the separate APAC fact on the same page, but that evidence is not attached to this public item. | Informational `not_established`: the attached evidence does not establish APAC’s ranking or the cross-region comparison. | **Proven editorial/evidence-scope defect.** Complete metric context cannot authorize a comparison when the public item carries only the North America binding. The safe outcome is to attach both fact IDs or remove the comparison. |

Page 9 independently confirms the normalized-100 Attention Index and 28-day
rolling-window context. No reviewed DoubleVerify numeric value was shown to be
wrong on the cited page. The provider-free corrected-boundary replay preserved
the old two error-level and one informational outcome because it reapplied the
retained model response; it did not make a new model call. Thus the first two
rows are a strong context-loss diagnosis, not a measured post-fix pass.

The retained grounding-input comparison quantifies the boundary:

| Report | Old report-JSON tokens | Corrected report-JSON tokens | Change |
|---|---:|---:|---:|
| Criteo | 17,704 | 32,325 | +14,621 |
| DoubleVerify | 17,408 | 34,758 | +17,350 |

The corrected payload includes the complete authoritative metric and the
batch-scoped canonical fact objects. It does not add an LLM stage or change the
fail-closed verdict contract.

##### Algolia: three separate lineage boundaries, with admission correctly failing closed

The retained Step 1 ledger selected six identities:
`revenue-incentive-58`, `search-capability-development-approaches`,
`ai-search-purchase-agreement-regional-range`,
`agentic-search-deployment-and-plans`, `agentic-adoption-considerations`, and
`search-investment-and-adoption-activity`. The exact source PDF is 29 pages.
Direct text inspection found the original 58% revenue-incentive sentence on
physical page 4, while physical page 5 contains the 53%/51% investment chart
and the 61% ROI text. The retained `ch2-revenue-incentive` binding says page 5.
Because the visual renderer converts a one-based physical page to the zero-based
render request (`page - 1`), this is a real source-page inconsistency unless a
separate printed-page convention is intended and recorded. The convention is
not recorded in the retained finding span.

The next defect is proposition/lineage drift. The Step 2 ledger accepts a
corrected `revenue-incentive-58` claim about 53% adequately invested and 39%
under-invested, but retains the original `ch2-revenue-incentive` evidence ID
and 58% candidate identity. The source-supported replacement is real, but the
binding is not. The later `admission_debug_after_fix.json` candidate list makes
the conflict explicit: its `revenue-incentive-58` row still says 58% while its
evidence ID is `verified-fact:revenue-incentive-58`. The current canary checks
fact ID, source identity/hash, pages, and source notes, but does not establish
that a changed proposition has a compatible discovery/evidence identity before
projection. This must remain blocked from canonical promotion.

The admission roster mismatch is independently proven by the retained
diagnostics:

| Diagnostic | Candidate snapshot | Evaluation result snapshot | Admission outcome |
|---|---|---|---|
| `admission_debug.json` | Six candidates, including mixed bare and `verified-fact:` identity forms and two revenue-related representations | Six terminal results, but five prefixed IDs are missing and five bare IDs plus `search-investment-and-adoption-activity` are unexpected | 0 admitted; `evaluation_coverage_incomplete` |
| `admission_debug_after_fix.json` | Five candidates: agentic deployment, adoption considerations, revenue incentive, regional purchase, and search approaches | Six terminal results; `search-investment-and-adoption-activity` is extra; expected count 5, evaluated count 6 | 0 admitted; `evaluation_coverage_incomplete`; digest unchanged at `138e41bbb3caa6f0ac7ebc806171cdac6965a724f924f4104d307d3ef453edf7` |

The first proven inconsistent operation is the existing one-to-one admission
check in `admit_visual_authority_candidates()`: it computes missing/extra IDs
and fails closed before any fact is admitted. The request builder copies the
shortlist exactly (`build_verified_claims_shadow_request()`), and
`evaluate_shortlisted_claims()` emits one result per request claim, so a
coherent single invocation cannot produce an extra sixth ID. The unchanged
digest and the fact that the extra ID is one of the earlier six make a stale or
mixed candidate/evaluation snapshot the most likely cause. The retained output
does not include the exact request/result pair or cache record needed to prove
which replay/cache boundary introduced the mix; that sub-stage remains
unresolved. Admission’s fail-closed behavior is correct and must not be
weakened to accept five of six results.

The six Algolia visual results themselves are not equivalent to six clean
editorial facts: the 58% row has an inherited binding, the agentic deployment
row uses a provisional recovered page 26, and the search-investment row is a
distinct 2025/2024 investment proposition rather than a duplicate of the
agentic/revenue rows. The evidence report’s earlier distinction between
editorial omission and factual error remains valid; no six-insight minimum is
justified by this diagnostic alone.

##### Cross-cutting disposition and next tests

| Priority | Proven issue | Minimal next action | Confidence |
|---|---|---|---|
| P0 | Algolia corrected propositions can inherit the old stable ID/evidence binding. | At the existing visual-fact admission boundary, require a compatible evidence/proposition rebind for a changed fact; otherwise quarantine it. Reuse current source-hash, page, evidence-span, and fact-ID checks. | High |
| P0 | Algolia admission can receive a five-candidate roster and six-result evaluation snapshot. | Bind the existing evaluation/admission exchange to one candidate-roster identity (using existing hashing/cache identity) and fail closed on mismatch; retain the full request/result diagnostic. | High at boundary; exact upstream mixing point unresolved |
| P1 | Criteo population/attribution and two DoubleVerify qualifier failures were evaluated without the complete verified-fact authority object. | Run a fresh GPT-6 Luna High grounding replay with validator identity 1.8 and inspect the final text against the cited pages. Do not reuse the pre-correction retained response. | High for context loss; post-fix outcome unresolved |
| P1 | DoubleVerify North America `so_what` compares against APAC without an attached APAC binding. | Attach the APAC fact as a second evidence binding or remove the comparison; keep the current fail-closed outcome until then. | High |
| P1 | Algolia `ch2-revenue-incentive` page binding conflicts with direct physical PDF page content. | Reconcile the finding/page resolver’s physical-versus-printed convention and regenerate the binding; do not repair the row at admission. | High |

Required regressions before any promotion are: changed-proposition same-ID
rejection, source/evidence identity rebind, five-versus-six roster mismatch,
correct multi-fact comparison, complete canonical metric authority, and a
fresh Criteo/DoubleVerify model replay. The existing reference gate remains
independent and passed provider-free; no evidence here supports changing its
39-variant expectations.

**Investigation verdict: PARTIAL / Step 2 remains NO-GO and Step 3 is not
ready.** The grounding-input correction is proven at the payload boundary, the
source-backed Criteo/DV facts are present, and Algolia correctly fails closed.
The remaining blockers are the unmeasured fresh-model grounding outcome, the
Algolia corrected-fact lineage conflict, the five-versus-six snapshot mismatch,
and the physical-page binding reconciliation. No live quality improvement is
claimed from this retained-artifact investigation.

#### Verified-fact snapshot and editorial-selection separation — 2026-10-24

This correction keeps one authoritative verified-fact snapshot after visual
admission and makes editorial selection a later, narrower operation. The
initial verified-mode selector now preserves the full eligible candidate pool
for visual evaluation; it does not apply the existing five-insight editorial
limit. After admission, the accepted `verified_facts` list is validated again
with the existing canonical snapshot validator and materialized into
artifact-shaped projections from the facts themselves. The admission's
candidate projection is therefore not a second factual authority. The final
selector then applies the existing editorial plan and minimum-count rules, so
six valid verified facts may yield five published insights without treating
the unselected fact as invalid. Legacy mode and the existing minimum insight
gate are unchanged.

The visual boundary is now bound to a deterministic
`verified_claims_candidate_roster:1` digest over all non-ranking candidate
fields. Requests carry the digest and evaluator responses return it; an
explicit mismatch fails closed as `evaluation_candidate_roster_mismatch`.
Equivalent score-only same-ID representations are collapsed before evaluation,
while conflicting same-ID representations remain in the roster and are
quarantined by the existing factual-conflict path. For legacy direct response
callers without a roster digest, the existing result binding now additionally
checks the original evidence spans exactly, including physical page and source
identity fields. A changed claim, evidence ID, metric binding, or span cannot
be selected by editorial score. These checks preserve the existing stable
candidate IDs, canonical `verified-fact:*` IDs, evidence pages, spans, source
hashes, and protected metric fields.

Verified-mode factual restoration also preserves the complete candidate metric
object, including unknown nested report-specific extensions, while removing
final-only fields. This is deliberately limited to authoritative candidate
materialization; it does not invent missing values or promote final editorial
text into a fact. The existing semantic grounding path remains responsible for
rejecting a final sentence that adds unsupported content.

Deterministic verification evidence:

- `tests/test_verified_claims_visual_authority_canary.py` and
  `tests/test_verified_claims_visual_authority_snapshot_integrity.py` passed
  **33 tests combined**, including stale same-ID wording/evidence/metric
  rejection, a changed-only physical span rejection, roster-digest mismatch,
  equivalent duplicate collapse, conflicting-ID fail-closed behavior, and a
  six-verified-facts to five-editorial-insights case.
- `tests/test_artifact_normalization_source_fidelity.py` covers complete
  nested metric preservation and final-only metric removal in verified mode.
- The combined affected shortlisting, admission, regeneration, provenance,
  grounding, prompt, and editorial-integrity suite passed **198 tests**; the
  prompt/grounding subset passed **116 tests**. Selected Ruff passed after the
  final test formatting correction. The repository type gate cannot represent
  this worktree because it scans the user-owned untracked duplicate
  `src/generators/artifact_normalization (2).py`, which has an unrelated
  pre-existing type error; that file was not modified or staged.

The exact provider-free frozen-five replay was rerun with the existing
`python scripts/quality/replay_verified_claims_step2.py --provider-free`
workflow. It retained the same **15 reference cases / 39 variants**, matched
all five source hashes, and retained **29 selected identities** with the same
report counts: Capgemini 5, Activate 7, KPMG 5, Reuters Institute 6, and
Adjust 6. It made zero provider calls. This is selection/provenance replay
evidence, not a live selection-quality claim.

##### Fresh retained Criteo and DoubleVerify visual review

The bounded live shadow command evaluated the exact retained five insights for
each report with GPT-6 Luna High, using the local PDFs whose SHA-256 values
matched the retained source identities:

| Report | Visual claims | Outcomes | Calls / tokens / cost / wall time | PDF pages independently reviewed |
|---|---:|---|---:|---|
| Criteo | 5/5 | 5 verified first pass; 0 after retry; 0 unresolved/failed/skipped | 10 / 68,721 input + 9,058 output / $0.0109 / included in 207.133 s | 5, 7, 8 |
| DoubleVerify | 5/5 | 5 verified first pass; 0 after retry; 0 unresolved/failed/skipped | 10 / 71,966 input + 9,606 output / $0.0125 / included in 207.133 s | 3, 8, 9, 10 |
| **Total** | **10/10** | **10 verified first pass** | **20 / 140,687 + 18,664 = 159,351 tokens / $0.0234 / 207.133 s** | hash matched |

The exact output is retained in ignored local evidence
`out/verified_claims_step2_live_simplification_20261024.json`. The final
visual wording was inspected against the native full pages, not just the
model verdicts. The Criteo wording correctly keeps the 61% newer-channel ROI
expectation separate from the page-5 global spend-recommendation table, and
the page-7 22% estimate and page-8 plan/omnichannel statements match their
populations and periods. DoubleVerify's final wording matches the page-3
regional brand-suitability table, page-8 Engagement Index definition, page-9
normalized-100/28-day context, and the page-10 APAC and North America video
tables. No unsupported material claim was independently confirmed in this
visual review. The visual result remained shadow-only: no canonical artifact,
publication-readiness state, or WordPress write changed.

##### Fresh complete-fact grounding replay

The existing grounding boundary was then run live, without an additional
validator or LLM stage, using the ten fresh verified facts above and the
retained Criteo/DoubleVerify downstream editorial artifacts in memory. The
run used validator identity `grounding_validation_output:1.8`, fresh isolated
cache/database paths, and no vector-store retrieval. It made **16 grounding
calls**, consumed **162,241 input + 101,357 output = 263,598 measured tokens**,
cost **$0.064630**, and produced no canonical or publication write. The output
is retained in `out/grounding_complete_fact_live_20261024.json`.

| Report | Facts | Grounding terminal result | Interpretation |
|---|---:|---:|---|
| Criteo | 5 | 20 fail-closed issues | The retained downstream artifacts still combine the 61% ROI fact with separate spend-recommendation values and combine the broad 22% estimate with channel-specific chart values. The complete fact snapshot correctly rejects those unsupported single-fact promotions; the source page supports the values only when separately bound. |
| DoubleVerify | 5 | 1 fail-closed issue | The only remaining issue is the retained North America `so_what` comparing to APAC without attaching the APAC fact. The separate APAC and North America facts both passed visual review, but the public comparison still lacks the required multi-fact binding. |

This is a measured post-1.8 result, not a claim that the retained public
artifacts are publication-ready. It shows that complete canonical context does
not mask evidence-scope defects: the Criteo population/attribution and
metric-composition failures remain fail-closed, while the DoubleVerify
cross-region issue remains the previously documented evidence-binding defect.
No individual report was patched and no unsupported value was enriched.

The fresh results establish the requested architecture boundary and remove
the previous “no post-1.8 grounding outcome” gap, but they do not close Step 2:
the retained Criteo downstream artifact needs separate fact bindings for its
additional chart values, and the DoubleVerify comparison needs both regional
fact IDs or narrower wording. Algolia's corrected-proposition lineage and the
original source-page convention remain unresolved and continue to fail closed.

**Current verdict: PARTIAL / Step 2 remains NO-GO; Step 3 is not ready.** The
authoritative snapshot and independent selection boundary are implemented and
covered. Fresh visual claims are source-supported, but downstream retained
editorial artifacts still contain genuine evidence-scope defects. No causal
live selection improvement is claimed because the live evaluation used
retained Step 1 candidates rather than a fresh end-to-end report selection.

#### Verified-mode downstream multi-fact binding correction — 2026-10-24

The retained grounding failures were traced to one downstream representation
gap, not twenty-one independent source or grounding failures. A generated
insight, metric-spine row, or key figure could contain a proposition assembled
from multiple verified findings while carrying only its primary
`evidence_id`. The existing multi-fact contract was present for soft-copy
provenance, but it was not retained consistently through final-insight
normalization, evidence-span binding, metric-spine/key-figure projection, or
the verified grounding inventory. The retained DoubleVerify comparison had the
same asymmetry: its text compared North America with APAC, but its insight row
exposed only the North America fact.

The smallest correction was to carry an optional primary-first `evidence_ids`
list alongside the backward-compatible primary `evidence_id` through the
existing artifact schema and validators. `artifact_normalization.py` now
preserves only exact known IDs, restores authoritative candidate metrics and
source bindings, derives spans for every bound fact, and supplies all bound
findings to expert synthesis. `generation.py` passes the list with the lead
insight; `storage.py` retains it in the claim ledger, metric spine, key
figures, and chart cards; `grounding.py` exposes all bound canonical evidence
texts in verified mode; and `verified_facts.py` validates every referenced fact,
the union of their authoritative pages, and each fact-specific span. The
insights-final prompt now requests additional exact IDs only when prose
materially combines supplied findings. Schema reference validation was updated
for the same existing artifact families. The selection/cache identity advanced
from `evidence_backed_shortlisting:8` to `:9`.

This does not attach every fact to every sentence. An unknown additional ID,
an unbound single-fact comparison, or a page/span outside the referenced facts
still fails closed. A valid multi-fact comparison keeps its primary ID for
compatibility and retains the secondary IDs needed to establish its other
premises. No protected metric value, population, period, forecast status,
source hash, physical page, or evidence span is synthesized.

Before/after failure inventory:

| Root cause | Retained baseline | Corrected behavior |
|---|---:|---|
| Criteo 61% newer-channel ROI expectation fused with separate 19%/20%/19% spend recommendations | 20 fail-closed grounding items, including executive summary, claim map, metric spine, key figures, insights, expert comment, and LinkedIn rows | Fresh Criteo generation keeps 61% as its own fact; no spend recommendations are transferred into that metric or binding |
| Criteo 22% US digital-campaign cost estimate fused with channel-specific 24%/23% values | Included in the same 20 fail-closed items across summary, metric spine, key figure, insight, expert, and LinkedIn rows | Fresh Criteo generation keeps the 22% estimate separate and preserves its US-agency/2023 scope |
| DoubleVerify North America `so_what` compared with APAC while carrying only North America | 1 fail-closed insight issue | A valid cross-region analytical sentence receives both APAC and North America IDs; an unbound comparison remains rejected |

The exact frozen-five provider-free replay still covers 15 reference cases / 39
variants, five matching PDF hashes, and 29 unchanged selected identities
(Capgemini 5, Activate 7, KPMG 5, Reuters Institute 6, Adjust 6), with zero
provider calls. This confirms stable selection/provenance replay only; it is
not a live claim about new candidate-selection quality.

##### Fresh downstream editorial and grounding replay

The requested fresh downstream run used the retained verified-fact snapshots,
isolated output/cache state, and the hash-matched local PDFs. It called the
existing artifact and grounding paths only; no visual re-admission, canonical
artifact mutation, readiness mutation, or WordPress write occurred.

| Report | PDF hash | Fresh final insights | Artifact calls | Grounding calls | Measured input + output tokens | Cost | Wall time | Grounding issues |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Criteo | matched | 5 | 7 | 8 | 119,132 + 67,122 | $0.045475 | 321.113 s | 0 |
| DoubleVerify | matched | 5 | 7 | 7 | 108,684 + 60,961 | $0.041350 | 296.769 s | 0 |
| Adjust control | matched | 5 | 7 | 7 | 114,030 + 71,207 | $0.047007 | 327.082 s | 0 |
| **Total** | **3/3 matched** | **15** | **21** | **22** | **341,846 + 199,290 = 541,136** | **$0.133832** | **944.964 s** | **0** |

Independent PDF review found the generated text aligned with the authoritative
pages: Criteo page 5 keeps the 61% expectation separate from page-7 cost and
incrementality findings and page-8 planning shares; DoubleVerify pages 3, 9,
and 10 preserve regional, normalization, and environment/value relationships;
Adjust pages 6, 11, 21, and 34 preserve global/category, population, and
period distinctions. The fresh Criteo expert analysis combines cost, expected
relative returns, and incrementality only as three explicitly distinct,
source-bound findings and gives conditional planning advice. The fresh
DoubleVerify expert analysis binds both regional video findings before making
the cross-region comparison. Adjust preserves the useful contrast between
accelerating global totals and opposite-direction finance-app metrics.

The generated artifacts are retained only in the ignored local replay output
`out/verified_claims_downstream_multifact_20261024/`. The old retained
artifacts remain unchanged; replaying them still correctly produces the old
20/1 fail-closed inventory. The new zero-issue result is therefore evidence of
fresh downstream generation after the binding correction, not retroactive
repair of stale artifacts.

Focused and affected tests passed **344 tests**, with **1 expected skip**.
The prompt-fixture gate passed against the unchanged baseline: 108,572 total
tokens versus 108,275 (+297), validation 9,640 versus 9,486 (+154), and
estimated cost $0.024080 versus $0.024049 (+$0.000031). Targeted mypy passed
for the six changed source modules; changed-file Ruff F checks and formatting
passed. The repository-wide full-rule Ruff check still reports two unrelated
pre-existing findings in `storage.py` (SIM102 and E501), outside this fix.

The implementation and the fresh Criteo/DoubleVerify/Adjust downstream
binding outcomes are **PASS** for this correction. Overall Step 2 remains
**PARTIAL / NO-GO** because Algolia's previously documented visual-admission
and lineage mismatch was not in scope for this correction and remains
fail-closed; Step 3 remains unstarted and not ready. No claim is made that the
provider-free 29-insight replay improves live selection effectiveness.

#### Algolia verified-fact admission and downstream E2E correction — 2026-10-24

This isolated replay used the retained Algolia artifact and the local original
PDF at physical-page level. The PDF SHA-256 was
`d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50` and its
29-page count matched the source manifest. No canonical artifact, readiness
state, publication record, or WordPress write was changed.

The remaining admission defect was at the visual-result-to-fact boundary. A
materially corrected claim could still carry a `retained` or partial copied
binding even though its proposition had changed. The correction in
`verified_claims_canary.py` keeps the existing roster/digest and canonical
validators, but requires the binding metadata to agree with the final fact:
`retained` is allowed only for an unchanged proposition with the exact
candidate evidence IDs, spans, and protected metric; `unbound` cannot carry
copied discovery binding; and `independently_bound` must carry complete
source-consistent metric and span metadata. Complete verified-fact metrics are
not narrowed or enriched. Multi-page fact snapshots are normalized only for
the existing canonical page-order contract.

The historical five-candidate/six-result mismatch is not reproducible in the
current coherent run. The request and response both covered these six IDs:

| Candidate ID | Admitted supporting page | Corrected-fact status |
|---|---:|---|
| `revenue-incentive-58` | 5 | material replacement, unbound discovery lineage |
| `search-capability-development-approaches` | 22 | retained source-supported fact |
| `ai-search-purchase-agreement-regional-range` | 12 | retained source-supported fact |
| `agentic-search-deployment-and-plans` | 26 | recovered source-supported fact |
| `agentic-adoption-considerations` | 27 | retained source-supported fact |
| `search-investment-and-adoption-activity` | 23 | retained source-supported fact |

The normalized candidate-roster digest was
`d650bb1de09357ef09d18651ac986193a37be50edb6506bc69657e93a6778564`.
Admission recorded `evaluated=6`, `expected=6`, `admitted=6`,
`verified_facts=6`, `quarantined=0`, and `coverage_complete=true`; the
verified-fact snapshot digest was
`301f73bce6e8a7834d4d8e4dee008ba88b40dda7b193e799161f70d338e480bb`.
An extra, missing, duplicate, or stale result remains rejected by the roster
boundary; the six-result outcome was not obtained by truncation or relabeling.

The `revenue-incentive-58` result is now a separate source-backed fact rather
than an inherited 58% revenue proposition. Physical page 4 contains the
original 58% revenue statement, while physical page 5 contains the corrected
Total 2025/2024 search-investment rows: 39% versus 32% under-invested and 53%
versus 51% adequately invested. The admitted fact keeps the stable candidate
ID and canonical `verified-fact:revenue-incentive-58` ID, but its authoritative
statement, metric, page, span, and source notes describe only the page-5
investment proposition. The original `ch2-revenue-incentive` ID remains
diagnostic discovery lineage, not authority for the replacement. Page 23 is
kept as the distinct FOMO/search-investment finding; its 53%/39% values are
not merged with page 5 or substituted for the page-5 53%/51% year comparison.

The fresh GPT-6 Luna visual shadow run evaluated all six retained candidates
against full PDF pages:

| Measure | Result |
|---|---:|
| Visual claims / terminal outcomes | 6 / 6 verified first pass |
| Retries, unresolved, failed, skipped | 0 / 0 / 0 / 0 |
| Provider calls | 12 (correction + verification per claim) |
| Input / output / total tokens | 375,982 / 15,233 / 391,215 |
| Estimated cost | $0.045215 |
| Rendered physical pages | 7 |
| Wall time | 207.15 s |

Independent page review confirmed the final relationships on pages 5, 12, 22,
23, 26, and 27: the purchase-likelihood values retain the USA/Australia-NZ
respondent bases; the search-approach values retain their category labels and
2025 Total row; the agentic 17%/61% values retain the implemented-versus-next-
12-month-plan distinction; and the integration ratings retain the 47% very,
43% somewhat, and 90% combined relationship.

The exact six-fact downstream replay then produced five final editorial
insights, five metric-spine rows, and four key figures. It retained all six
verified facts, including the omitted page-23 fact, and omitted only the
redundant investment insight under the existing editorial-plan/minimum-count
rules. Final insight IDs/pages were:
`agentic-search-deployment-and-plans`/26,
`revenue-incentive-58`/5,
`search-capability-development-approaches`/22,
`ai-search-purchase-agreement-regional-range`/12, and
`agentic-adoption-considerations`/27. The existing artifact path made six
model calls (two bounded `insights_final` attempts and one for each other
regenerated family), measured 102,590 input and 27,350 output tokens, cost
$0.023933, and took 238.742 s. Public editorial quality returned
`status=pass`, `publishable=true`, `hard_fail_count=0`, and `issue_count=0`.
The summary, Expert View, and LinkedIn text were checked against the same
pages; their recommendations remain conditional interpretations rather than
new facts.

A production-like ten-candidate replay also exercised the four available
fidelity-approved fallback alternatives. All four fallback visual evaluations
verified first pass, but the subsequent ten-candidate `insights_final` stage
failed closed after its existing primary/repair/regenerate bound with
`StructuredOutputFailure`; no artifact was accepted from that run and no
retry policy was expanded. The successful six-candidate artifact used the
existing explicit retained-roster replay seam to withhold those post-shortlist
alternatives, so it is evidence for the six-fact downstream path, not proof of
universal fallback-generation success.

The normal verified-mode grounding workflow was run on the accepted six-fact
artifact with the canonical verified evidence pack and no PDF/vector-store
retrieval. It made seven parallel grounding calls, measured 91,833 input
(9,025 cached) and 48,965 output tokens, cost $0.032855, and had an 89.256 s
provider span (366.740 s aggregate provider latency across parallel calls).
The retained claim package recorded 30 entailed factual/descriptive claims,
zero unsupported factual claims, and zero unresolved factual claims. The two
unresolved entries are non-factual recommendation sentences in Expert View
and LinkedIn, which the existing claim workflow keeps at `awaiting_review`;
they are not treated as verified facts. The overall validation result was
`status=pass`, `severity=warning`, with the expected abstained-quotes warning
and five deterministic breadth/quality warnings. No grounding error was
returned.

The provider-free frozen-five replay was rerun after the correction: all 15
reference cases and 39 variants remained covered, all five source hashes
matched, and the retained selection remained 29 IDs (Capgemini 5, Activate 7,
KPMG 5, Reuters Institute 6, Adjust 6) with zero provider calls. The prompt
fixture gate also remained green at 108,572 total tokens / `$0.024080` versus
the accepted 108,275 / `$0.024049` baseline; validation was 9,640 versus 9,486
tokens and `$0.001725` versus `$0.001709`.

Focused visual-authority regressions passed **40 tests**. The final authority/
grounding subset passed **146 tests**. The broader affected Step 2/provenance/
regeneration suite passed **275 tests, 1 expected skip, and 1 deselection**.
Changed-file Ruff check and formatting passed, targeted mypy passed,
and the prompt-fixture gate passed. One initial test invocation referenced a
nonexistent legacy test filename; it ran no tests and was immediately replaced
with the repository's actual modules. This is not counted as a test failure.

**Algolia shadow verdict: PASS for the coherent six-fact visual-admission →
editorial → grounding → public-quality path; overall Step 2: PARTIAL / NO-GO.**
The remaining qualification is the bounded ten-candidate generation failure
and the fact that the six-fact downstream run used the retained-roster replay
seam rather than a fresh end-to-end selection. Step 3 is not authorized by
this evidence, and no live selection-quality improvement is claimed from
post-selection replay.

#### Algolia full-roster structured-output recovery and retained-binding hardening — 2026-10-24

This follow-up used the same retained Algolia PDF and source identity in a new
isolated output, cache, state, and usage ledger. The PDF SHA-256 remained
`d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50` across
29 physical pages. No publication, canonical-claim persistence, readiness
mutation, or WordPress write was performed.

The prior ten-candidate failure is now characterized at the existing recovery
boundary. Its primary `insights_final` response reached the provider output
cap and parsed invalid; the prior repair and regeneration attempts did not
produce an accepted artifact. The current run still reached the same primary
cap once (`16,384` output tokens), but the existing bounded model-repair path
accepted a valid result and the complete artifact workflow finished. The
minimal change removes the duplicated internal `verified_fact` object from the
verified final-selection candidate prompt. The complete canonical facts remain
in the authoritative verified evidence pack, admission snapshot, downstream
lineage, and validation inputs. The shortlisting cache identity advanced from
`:9` to `:10`, so old selection results cannot bypass the changed prompt
composition.

The retained-binding correction in `verified_claims_canary.py` also checks that
the authoritative raw verified-fact metric agrees with the copied retained
metric and that every retained candidate page/span page is covered by the
authoritative supporting pages. The existing independently-bound correction
path remains available; valid multi-page snapshots continue to use the
canonical page-order contract. Conflicting authoritative metric or page
metadata is quarantined rather than resolved by editorial score.

The fresh production-like roster and terminal admission ledger were:

| Candidate ID | Physical page | Visual outcome | Final public insight |
|---|---:|---|---|
| `agentic-search-deployment-and-plans` | 26 | verified | selected |
| `revenue-incentive-58` | 5 | unresolved after the bounded correction path | omitted; no fact promoted |
| `purchase-likelihood-market-range` | 12 | verified | selected |
| `search-capability-development-models` | 22 | verified | selected |
| `agentic-search-adoption-considerations` | 27 | verified | selected |
| `agentic-ai-no-concrete-plans` | 26 | verified | omitted by editorial selection |
| `search-investment-postures` | 23 | verified | selected |
| `ch5-integration-consideration` | 27 | verified | omitted by editorial selection |
| `ch5-retailer-control-consideration` | 27 | verified | omitted by editorial selection |
| `ch2-accelerating-ai-search` | 23 | verified | omitted by editorial selection |

The run therefore evaluated all 10 roster entries, admitted 9 verified facts,
and completed with `coverage_complete=true`; the one unresolved candidate was
not promoted. The final artifact contained 5 candidates and 5 final insights,
5 metric-spine rows, and 4 key figures. Final IDs/pages were
`agentic-search-deployment-and-plans`/26,
`search-investment-postures`/23,
`purchase-likelihood-market-range`/12,
`search-capability-development-models`/22, and
`agentic-search-adoption-considerations`/27. Each retained final fact used a
`verified-fact:<id>` evidence identity with its physical page and authoritative
metric binding.

Independent review of the full rendered pages confirmed the final content:
the 17% implemented versus 61% planned distinction and `Total n=1,100` on
page 26; the 39% acceleration statement and the separately labelled 53%/51%
adequate-investment comparison on page 23; 63% overall with USA `n=300` and
Australia/NZ `n=200` on page 12; the 49%/27%/23% category mapping for 2025 on
page 22; and the 47%/39%/37% very-influential factor relationship on page 27.
Expert View and LinkedIn preserved conditional commercial interpretation and
did not turn stated plans into completed adoption. This replay did not execute
the downstream verified-grounding workflow, so it is not reported as a new
zero-grounding-error result; the prior six-fact grounding result remains the
applicable grounding evidence.

The isolated live ledger recorded 28 provider calls: 20 visual correction /
verification calls (11 corrections and 9 verifications, including the bounded
second correction for the unresolved candidate) and 8 artifact calls. It used
`616,264` input and `68,772` output tokens, estimated cost `$0.096015`, and
wall time `598.482 s`. The artifact primary/repair sequence was bounded and
was not expanded. The final family status was `generated`; quotes remained
abstained because the retained quote inputs were not part of the authoritative
verified-fact pool.

Focused visual-authority and related regression tests passed **35 tests**;
the affected artifact/evidence/regeneration/public-quality subset passed
**113 tests**. Ruff, formatting, and targeted mypy passed. The provider-free
frozen-five replay and 15-reference-case/39-variant coverage remain unchanged;
this live run does not claim improved selection recall. The live result is a
**PASS for full-roster terminal artifact recovery and retained-binding
fail-closed behavior**, but the one unresolved visual fact and the absence of a
new downstream grounding run keep overall Step 2 **PARTIAL / NO-GO**. Step 3
remains unstarted and not ready.

#### Ten-report verified-architecture benchmark and final-insight output headroom — 2026-10-24

Commit `e1bbc17582c12ff7150eed508732e12f9b892af4` changes only the
`report_vs/artifacts/insights_final` output policy from **16,384** to
**19,661** tokens. The model remains GPT-6 Luna with high reasoning effort;
unrelated artifact policies and the shared bounded recovery policies were not
increased. The provider request regression confirms that the value reaches
`max_completion_tokens` on the chat route and changes the semantic cache
identity. The fresh Algolia artifact records the effective
`max_output_tokens=19661` and a primary final-family result of 16,484 output
tokens, below the new cap. No additional LLM stage or retry was introduced.

The final-insight prompts now require one JSON object containing only the
requested final entries, concise `so_what`/`now_what` text, and preservation of
exact values, qualifiers, comparisons, and source bindings. The prompt does
not repeat the candidate roster, evidence packs, schema, editorial plan, or
large canonical fact objects; the authoritative verified evidence pack remains
available to the model. The existing 18-word headline constraint is unchanged.

The three-iteration prompt fixture baseline was regenerated with repository
tooling. The accepted old/new totals are:

| Scope | Old tokens | New tokens | Delta | Old cost | New cost | Delta |
|---|---:|---:|---:|---:|---:|---:|
| Total | 108,275 | 108,751 | +476 (+0.44%) | $0.024049 | $0.024098 | +$0.000049 |
| `report_vs/artifacts/insights_candidates` | 3,634 | 3,656 | +22 | $0.000643 | $0.000646 | +$0.000003 |
| `report_vs/artifacts/insights_final` | 3,377 | 3,677 | +300 | $0.000618 | $0.000648 | +$0.000030 |
| `report_vs/validate/grounding` | 2,163 | 2,317 | +154 | $0.000368 | $0.000384 | +$0.000016 |

The increase is the measured cost of the concise output instructions and the
existing canonical-evidence/protected-dimension grounding text; thresholds,
pricing, fixtures, and factual safeguards were not changed. The unchanged
fixture regression command passed against the regenerated baseline. The first
live attempt from the normal long worktree failed before provider calls with
the typed `analysis_pack_path_too_long` Windows path-budget error for all ten
members. It was discarded as an execution-environment failure and rerun from
a clean short-path worktree, with the same commit and the exact retained PDFs.

The successful fresh run used the exact
`scripts/quality/frozen_reliability_cohort_10.json` manifest, isolated state,
`--verified-facts-architecture`, and no publication or canonical writes:

- Run root: `C:\vfa-runs-20261024\frozen-reliability-g2q9n49o\`
- Cohort result: `frozen-reliability-g2q9n49o/cohort_result.json`
- Git SHA recorded by the runner: `e1bbc17582c12ff7150eed508732e12f9b892af4`
- Expected manifest MD5 equalled the actual retained-PDF MD5 for **10/10**
  reports. The run completed terminal accounting for all 10 reports.
- Cohort totals: **360 provider calls**, **3,910,328 input tokens**,
  **823,403 output tokens**, **$0.932674**, and **5,665.627 seconds**
  (94.43 minutes). No report was published.

| Report | Final state / readiness | Final / candidate entries | Metric spine / key figures | Calls | Input / output tokens | Cost | Seconds | Terminal result |
|---|---|---:|---:|---:|---:|---:|---:|---|
| DoubleVerify | failed / fail | 5 / 5 | 0 / 0 | 35 | 330,693 / 66,544 | $0.073339 | 598.033 | `validation_failed`; public-quality metric-label relationship failure remained fail-closed |
| KPMG | awaiting review / pass | 6 / 6 | 0 / 0 | 41 | 283,508 / 67,269 | $0.098384 | 463.203 | pass |
| Reuters Institute | awaiting review / pass | 7 / 7 | 4 / 4 | 38 | 552,688 / 114,230 | $0.124247 | 723.632 | pass |
| Adjust | awaiting review / pass | 5 / 5 | 2 / 2 | 45 | 537,276 / 119,334 | $0.123142 | 790.947 | pass; one structured-output repair |
| Algolia | awaiting review / pass | 5 / 5 | 0 / 0 | 32 | 317,684 / 75,906 | $0.081454 | 744.690 | pass; one structured-output repair |
| Bain & Company | awaiting review / pass | 5 / 5 | 1 / 1 | 24 | 201,344 / 57,144 | $0.062941 | 344.953 | pass |
| Criteo | awaiting review / pass | 5 / 5 | 4 / 4 | 30 | 351,499 / 76,639 | $0.082537 | 467.164 | pass; one structured-output repair |
| Deloitte | awaiting review / pass | 5 / 5 | 2 / 2 | 34 | 413,036 / 99,149 | $0.097311 | 484.081 | pass; three bounded repairs |
| Emplifi | failed / fail | 5 / 5 | 0 / 0 | 45 | 589,816 / 79,646 | $0.115536 | 627.544 | `regeneration_repair_decision_invalid`; fail-closed |
| StackAdapt | awaiting review / pass | 5 / 5 | 1 / 0 | 36 | 332,784 / 67,542 | $0.073783 | 421.380 | pass |

The mutually exclusive cohort outcome was **8/10 readiness passes and 2/10
failures**, with `typed_terminal_rate=1.0`, `missing_terminal_report_count=0`,
and `published_report_count=0`. The persisted artifact ledger does not expose
a separate per-candidate visual-admission file, so no candidate-level
first-pass/retry/rejection counts are invented here. The durable downstream
evidence is the hash-bound run, final/candidate artifacts, retained-claim
validation, validation reuse telemetry, and typed terminal result above.
The final-family usage ledger shows one primary call for eight reports, two
calls for Adjust, and three for Emplifi; the other recovery calls are reflected
in the report-level call totals and structured-output-repair counters.

Independent PDF review found the following report-specific results:

- DoubleVerify final insights match the Q1 2026 benchmark tables on physical
  pages 3 and 10, including the APAC/EMEA/LATAM/North America labels and the
  regional Video, Display, and Ad Interaction values. The report is not
  accepted because the existing public-quality validator still flags a
  metric-label relationship in the generated public artifact; the terminal
  failure is not hidden by the source match.
- KPMG pages 5, 17, 27, 28, and 36 support the six retained qualitative
  findings. The AI execution and carve-out implications remain conditional
  interpretations rather than fabricated measurements.
- Reuters Institute pages 12, 17, 24, 25, 30, 33, and 38 support the search,
  newsroom, creator, misinformation, jobs, and subscription findings. Bases
  and respondent populations remain visible in the source pages.
- Adjust pages 9, 19, 21, and 37 support the segmentation, gaming
  install/session, retention, maturity, and finance-CPI findings, including
  the 2024/2025 and global/regional qualifiers.
- Algolia pages 12, 22, 26, and 27 support the geography, development-model,
  agentic-adoption, and integration-factor findings. The `revenue-incentive`
  artifact retains page 5, while the exact sentence is present on physical PDF
  page 4 in the retained source; this page-binding discrepancy is a material
  provenance limitation despite the report-level validation pass and requires
  correction before treating Algolia as fully source-clean.
- Bain page 1 supports all five final claims, including the 2015–20 valuation
  comparison and the 52% born-tech / 20% tech-led-growth relationships.
- Criteo pages 5–8 support the 61% ROI, 47% CTV, 50% incrementality,
  performance-versus-awareness, and offline/online data claims.
- Deloitte pages 3–7 support the trust, onsite-control, 693% traffic,
  strategic-posture, and LLM-discovery findings.
- Emplifi pages 2, 13–15, and 19 support the authenticity, disclosure,
  source-trust, service, and operating-model findings, but the invalid
  regeneration repair decision prevented an accepted terminal report.
- StackAdapt pages 7, 11, 15, 17, and 19 support the budget mix, repeated
  digital engagement, values alignment, relevance capabilities, and
  programmatic-capability findings.

The separate Algolia stress replay was started from the same clean short-path
worktree and exact source PDF with `--report-ids
cohort-86858bdcb370266f26c2 --verified-facts-architecture`. It is intentionally
not included in the ten-report totals or used to replace the cohort's Algolia
result. It completed as a separate pass: **30 provider calls**, **364,830 input
tokens**, **68,780 output tokens**, **$0.085104**, and **669.490 seconds**;
validation/readiness passed, no repair was required, and no report was
published. The final-family call was primary, used `max_output_tokens=19661`,
returned 10,383 output tokens, and produced five final insights, two
metric-spine rows, and one key figure. Direct PDF checks found the final
claims on pages 12, 26, and 27; no unsupported retained factual claims were
reported. This stress pass is positive evidence that the new cap avoids the
previous Algolia final-family truncation, but it does not replace the cohort
Algolia result or remove the cohort's page-5/page-4 reconciliation issue. No
WordPress, canonical-claim, or publication mutation was allowed by either
run.

Local focused prompt/routing/provider tests passed **114 tests**; focused
pipeline/canary tests passed **59 tests**; the report-pipeline orchestrator
subset passed **19 tests**. Changed-file Ruff, formatting, compileall, and
diff checks passed. The first broad mypy invocation is not a clean signal: it
reproduces pre-existing mailbox-acquisition typing and existing test/helper
typing errors; the changed source subset is otherwise clear apart from that
imported mailbox error. Hosted CI remains the release decision gate.

**Ten-report verified-architecture verdict: PARTIAL / NO-GO.** The output cap
change is implemented and provider-confirmed, the exact ten-report run is
complete and fail-closed, and eight reports passed readiness. The definition
of success is not met because DoubleVerify and Emplifi failed, Algolia has a
physical-page reconciliation issue, and the benchmark ledger does not persist
an independent visual candidate-outcome table. Verified-fact authority should
not be enabled as the normal autonomous default from this evidence. Step 3
remains unstarted/not ready.

#### Hosted CI completion for output-cap benchmark — 2026-10-24

The final pushed benchmark correction is `62fe58ad7987307838bbda48684e286894c5a438`.
Hosted CI run `40092248838` passed all required jobs: `tests`, mutation
partitions `0` and `1`, and `release_evidence`. The default suite reported
`8,089 passed, 1 skipped`; the repository's static, architecture, role-I/O,
documentation, prompt-fixture, coverage, mutation, and release-evidence gates
were green. The provider-cap/cache regression was moved into a dedicated test
module after the prior run correctly rejected the larger OpenAI service test
file; no production behavior or gate threshold was weakened. The final
ten-report verdict therefore remains **PARTIAL / NO-GO** on measured report
quality, not CI health: DoubleVerify and Emplifi still fail closed, and the
Algolia physical-page discrepancy remains unresolved. Step 3 remains
unstarted/not ready.

#### Verified-facts architecture admission validation — 2026-10-24 (stopped after Criteo)

The latest run used commit `6784a8f2ed90a2ab64d4211baf66447132e70e93`, the
explicit opt-in verified-facts architecture, and the exact frozen ten-report
manifest with retained hash-matched PDFs. A dedicated Adjust run completed
architecture admission validation: 17/17 facts were evaluated and admitted,
coverage was complete, and the source PDF hash and verified-fact digest
matched the persisted canary. It still terminated with the existing
`summary_safe_removal_target_unresolved` workflow failure after artifacts were
persisted. It made 66 provider calls, used 658,665 input and 80,655 output
tokens, cost `$0.123596`, and ran for 1,199.545 seconds.

Per the requested stop boundary, the ten-report replay was stopped after
Criteo completed. Seven reports completed; Deloitte had initialized and made
one `rank_candidates` call before interruption, and Emplifi and StackAdapt
did not start. No cohort-level result exists for this stopped run. The
completed-ledger totals were 431 provider calls, 4,946,180 input tokens,
565,552 output tokens, and `$0.884213`.

| Report | Calls | Input / output tokens | Cost | Verified facts (evaluated / admitted / quarantined) | Final insights | Architecture proof |
|---|---:|---:|---:|---:|---:|---|
| DoubleVerify | 48 | 409,222 / 64,448 | $0.080547 | 12 / 12 / 0 | 5 | pass |
| KPMG | 47 | 291,559 / 58,204 | $0.090663 | 7 / 7 / 0 | 5 | pass |
| Reuters Institute | 84 | 743,923 / 105,352 | $0.141969 | 27 / 27 / 0 | 7 | pass |
| Adjust | 76 | 844,786 / 88,547 | $0.143654 | 22 / 21 / 1 | 6 | pass |
| Algolia | 62 | 1,106,551 / 83,475 | $0.164795 | 15 / 14 / 1 | 5 | pass |
| Bain & Company | 40 | 906,914 / 64,693 | $0.137940 | 10 / 10 / 0 | 5 | pass |
| Criteo | 73 | 642,621 / 100,650 | $0.124493 | 24 / 24 / 0 | 5 | pass |
| Deloitte (partial) | 1 | 604 / 183 | $0.000152 | not evaluated | 0 | unavailable |

Failure ledger and limitations:

- All seven completed reports ended with the typed
  `summary_safe_removal_target_unresolved` terminal failure after their
  artifacts were persisted; this is an existing downstream readiness/safe-
  removal failure, not a verified-facts source-admission failure.
- Every completed `validation.json` contains
  `verified_fact_snapshot_invalid`, even though the independent architecture
  proof passed. This is an unresolved downstream contract mismatch and is
  intentionally not bypassed or downgraded.
- Bain's public-quality artifact is rejected for
  `public_editorial_quality.duplicate_insight` between `f1` and
  `market-value-growth-share-breakdown`.
- Adjust quarantined `finance-global-sessions-2025` because its corrected
  binding conflicted with the retained authoritative binding; the report
  remains fail-closed on that fact.
- Algolia quarantined `revenue-incentive` as `outcome_unresolved`; its
  retained artifact also has a page-5/page-4 physical-page reconciliation
  limitation that remains unresolved.
- Deloitte has no artifacts or architecture proof because the run was stopped
  after its first ranking call. Emplifi and StackAdapt have no run members.
- No source-hash, verified-fact-digest, or evidence-ID mismatch was found in
  the seven completed architecture proofs. The separate Algolia retained
  page-reconciliation limitation remains as stated above. No
  WordPress/publication writes occurred.

This is **PARTIAL / NO-GO** evidence. It demonstrates genuine opt-in
verified-facts admission for the seven completed reports and the dedicated
Adjust run, but it is not a completed ten-report evaluation and does not clear
the downstream readiness blockers. Step 3 remains unstarted/not ready.

#### Verified-facts-first authority flow — 2026-10-24 (`fe77330b`)

The pushed implementation adds a typed `VerifiedAuthorityContext` to the
analysis state and checkpoint/resume contracts. In verified mode it binds the
qualified canary source identity, PDF SHA-256, verified-fact digest, complete
canonical verified facts, and canonical evidence packs. Discovery packs remain
available for navigation/context only. Regeneration, metric-spine/key-figure
inputs, retained-claim materialization, render provenance, and publication
readiness now use the authoritative packs and qualified identity; verified
structural failures are typed, non-retryable, and do not enter generic fallback
or broad editorial regeneration. Normal mode remains on the existing
discovery-evidence path.

Focused verification passed **106 tests** for authority/selection/evidence
regressions and **127 tests** for pipeline, checkpoint, resume, rendering, and
readiness behavior. The full local suite passed **8,098**, skipped **2**, and
deselected **32**; two pre-existing environment/repository failures remain:
the CPython 3.14 wheelhouse test requires native CPython 3.12, and two existing
test modules exceed the long-file threshold. Mypy reported no issues for the
nine changed source files. Compileall and diff checks passed. Ruff reported
only pre-existing findings in the touched checkpoint/resume modules.

The exact retained Adjust member was then run once from a clean short-path
worktree at this commit, with the ten-report manifest inventory and the
hash-matched retained PDF (`MD5 b638414df0b1fccea1cd8a93eaf8f5aa`, PDF
SHA-256 `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`).
The initial long-path attempt failed before provider execution with the typed
`analysis_pack_path_too_long` setup error. The first short-path retry stopped
before execution because the runner validates the complete manifest inventory;
copying only the ten retained PDFs into the isolated worktree resolved that
input issue. Neither setup attempt changed source code or publication state.

The completed provider-backed Adjust run used **66 calls**, **738,548 input
tokens**, **96,937 output tokens**, **$0.139822**, and **1,066.351 seconds**.
Admission, source ingest, and report selection passed. The visual claim stage
completed **17/17** terminal `verified` responses. The run then failed before
final artifact persistence with:

- primary terminal outcome: `artifact_structured_output_invalid`;
- inner cause: `artifact_final_insight_lineage_invalid` in `insights_final`;
- bounded recovery: the existing maximum of **two** structured-output recovery
  calls was exhausted;
- secondary architecture readback: `verified_facts_artifact_unreadable`
  (`FileNotFoundError`), because no final `artifacts.json` was emitted after
  the lineage failure.

The exact invalid/duplicate/missing final ID was not retained by the provider
audit, so it is not attributed more narrowly. No final insights, metric spine,
key figures, validation/readiness artifact, canonical mutation, or WordPress
write can be claimed for this run. The prior retained Adjust artifact had six
final insights, but its legacy downstream validation failed on
`verified_fact_snapshot_invalid`; the current run therefore provides no valid
before/after editorial comparison and no live quality improvement claim.

The persisted evidence-fidelity pack contained 27 finding rows: 17
deterministic passes, five fail-closed unsupported rows, and no unresolved row.
The excluded rows were `gaming-europe-latam-sessions`,
`gaming-casual-hypercasual-installs`, `gaming-casual-hypercasual-sessions`,
and `gaming-strategy-casino-slots-sessions` for
`protected_fact_timeframe_incompatible`, plus `finance-session-lengths` for
`quantity_not_entailed`. These are finding-level exclusions, not promoted
editorial claims. No unsupported factual finding was promoted.

This is **PARTIAL / NO-GO** evidence. The authority-state implementation and
deterministic safeguards are locally verified, but the retained real-report
run is blocked at final insight lineage and has no persisted authoritative
snapshot for downstream readiness. The requested stop boundary was honored:
the ten-report cohort was not started. Step 3 remains unstarted/not ready.

#### Verified-facts architecture integration — 2026-10-24 (`b5d32e2f`)

This correction closes the four confirmed integration boundaries from the
previous Adjust run. After verified visual admission, final-insight generation
now derives one evidence-bound stable-ID roster, caps the requested final
count to that roster, supplies the exact allowlist to the final prompt, and
keeps the existing fail-closed lineage validator and identifier-only recovery
diagnostics. Verified readiness now materializes and checks retained semantic
claims with the canonical authority evidence and an empty raw-PDF page
sequence. Verified regeneration disables broad fallback, while structurally
invalid verified snapshots propagate their typed failure instead of entering
editorial repair. The contract snapshot was regenerated through the existing
schema gate.

Focused affected tests passed **383 tests**. Ruff check and format checks
passed; the contract snapshot gate passed; the unchanged prompt-fixture gate
passed with **108,751 total tokens / $0.024098** and **9,640 validation-family
tokens / $0.001725**, both exactly matching the approved baseline. The full
repository type gate passed on the committed source (**786 source files, zero
tracked mypy errors**) after temporarily relocating the unrelated preserved
untracked duplicate `artifact_normalization (2).py`; with that user-owned file
present, the gate reports its pre-existing single-file typing error.

The provider-free exact frozen-five replay made **zero provider calls** and
confirmed all five PDF hashes, all 15 reference cases / 39 variants, and all
29 retained shortlisted identities (Capgemini 5, Activate 7, KPMG 5, Reuters
6, Adjust 6). This is input-coverage and provenance evidence only; it does
not claim live correction or selection improvement.

One fresh isolated Adjust run used the clean commit `b5d32e2f8f695486be3e8d2cf00792cc958f4dd9`
with the verified-facts architecture and no publication target. The source
identity was `source:8cb648b6bbd9dbae4ec1d915c38cf235` qualified by PDF
SHA-256 `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.
Architecture admission evaluated 25 facts, admitted 22, and quarantined 3;
coverage was complete and no unsupported retained factual claim was reported.
The generated final stable IDs were `global-finance-installs-sessions-2025`,
`gaming-retention-curves-2024-2025`,
`ecommerce-cpi-subvertical-divergence-2025`, `ai-advanced-efficiency`, and
`gaming-subvertical-growth-2025`; their authoritative evidence IDs remained
the corresponding `verified-fact:*` bindings.

The report did not reach final HTML or `PublishReadinessArtifact`. It failed
closed at `validation_failed` in `expert_comment` after **88 provider calls**,
**1,073,888 input tokens**, **143,586 output tokens**, **$0.193209**, and
**1,200.874 seconds**. The substantive issue was a grounding rejection of the
sentence claiming that installs and sessions moved in opposite directions
“across these two segments” after comparing finance and strategy. Physical
PDF page 19 confirms the bounded strategy relationship (−1% installs, +57%
sessions) but also shows casual and hyper-casual both rising; the validator
treated the commentary as a broader gaming generalization. The source is not
missing and no unsupported fact was promoted, but the final editorial
composition was not accepted. The single warning was `quotes_missing`.
Each of the exactly three targeted repair attempts then failed with the same
safe-removal/revalidation shape: `deferred_grounding_required` (1),
`regeneration_scope_violation` (33 undeclared paths), and the `quotes_missing`
warning (1). No broad verified-mode rewrite ran, no canonical artifact was
promoted, and no WordPress/publication write occurred.

**Integration verdict: PARTIAL / NO-GO.** The four code-level boundaries and
their local contracts are green, and the previous final-insight lineage
failure no longer occurs in this run. The independent Adjust editorial
grounding failure still blocks readiness; there is no claim of live quality
improvement and Step 3 remains unstarted/not ready. The ten-report cohort was
not started.

#### CI ownership and Adjust editorial-repair correction — 2026-10-25 (`b926137d`)

The hosted CI ownership failure was fixed without changing the ownership gate,
allowlist, or threshold. The oversized
`tests/test_frozen_reliability_cohort_runner.py` module was split by concern;
the seven cohort-execution/summary tests moved to
`tests/test_frozen_reliability_cohort_execution.py`. The original 23 test names
remain present across the two modules, the ownership/collection check now
collects **26 tests**, and the focused ownership tests pass. The preceding
implementation commit `eb2495c9` passed hosted CI run `40136119645`.

The retained Adjust failure was reproduced and traced to two producing-stage
issues. Expert-comment context did not expose the full composite observation
boundaries, and the verified finalizer rebound canonical summary evidence even
when `summary` was not an authorized repair root. The first correction
(`eb2495c9`) now retains `forecast_status` and named `observations` in expert
context, requires explicit population/subsegment naming in both expert-comment
prompts, and removes the verified-mode blanket replacement of all public source
roots. The final correction (`b926137d`) applies the existing atomic patch-root
boundary to verified summary span rebinding: summary binding is unchanged for
an explicit summary repair, but an expert-comment-only repair cannot mutate the
unrelated summary claim map. The focused regression is red before this change
and green after it.

The fresh isolated Adjust run was executed from clean commit `eb2495c9` with
the verified-facts architecture, no shared batch, and no publication target.
Its retained PDF identity matched
`source:8cb648b6bbd9dbae4ec1d915c38cf235` plus SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.
Architecture admission evaluated **24** facts, admitted **22**, quarantined
**2**, and reported complete coverage. The run used **93 provider calls**,
**1,222,346 input tokens**, **154,928 output tokens**, estimated cost
**$0.216223**, and **1,374.874 seconds**. It made no WordPress or publication
write and ended fail-closed at
`regeneration_evidence_rebind_unresolved`; validation and publication
readiness were both `fail`.

The run produced five retained final identities with authoritative bindings:

| Stable ID | Evidence ID | Physical page |
|---|---|---:|
| `ecommerce-cpi-subvertical-divergence` | `verified-fact:ecommerce-cpi-subvertical-divergence` | 29 |
| `cross-platform-data-satisfaction` | `verified-fact:cross-platform-data-satisfaction` | 11 |
| `gaming-install-session-divergence` | `verified-fact:gaming-install-session-divergence` | 19 |
| `finance-retention` | `verified-fact:finance-retention` | 37 |
| `genai-maturity-and-reported-efficiency` | `verified-fact:genai-maturity-and-reported-efficiency` | 9 |

The targeted candidate repair changed the CPI insight to:
“From 2024 to 2025, reported global e-commerce CPI fell from $1.00 to $0.98,
while deal-discovery CPI rose from $1.44 to $2.26.” The retained verified fact
on page 29 contains the global and subvertical values, so this is a
source-supported analytical improvement rather than an unsupported promotion.
The audit shows evidence-lineage `pass` and no change to the five insight
evidence IDs or pages. The earlier expert-comment grounding failure and its
**33** undeclared paths did not recur. The remaining candidate audit exposed
**five** undeclared `summary.claim_evidence_map[*].evidence` paths, caused by
the finalizer’s verified canonical rebind; `b926137d` closes that producer-side
scope defect. The run’s grounding artifact was still non-substantive and the
terminal candidate was rolled back, so this is not evidence of a completed
Adjust readiness pass.

The `unresolved_retained_factual_claims: 29` run metric is terminal downstream
validation accounting after the rebind failure, not 29 independently
confirmed factual errors. No unsupported retained factual claim was reported
by the architecture admission. Provider-free frozen-five replay remains
unchanged: **5/5** PDF hashes, **15/39** reference cases/variants, and all
**29** retained shortlisted identities are available with zero provider calls;
that replay establishes input/provenance coverage only, not live editorial
quality.

Local verification for `b926137d` passed the affected **220-test** suite,
ownership/collection checks, Ruff, formatting, forbidden-patching, contract
schema, compileall, changed-source mypy, and the prompt-fixture gate. The full
local suite reported **8,105 passed, 2 skipped, 32 deselected**, with the one
known CPython-3.14-only wheelhouse failure; that test passes under CPython
3.12. The prompt fixture baseline remains unchanged at **108,909 tokens /
$0.024114** versus **108,751 / $0.024098** (**+158 tokens / +$0.000016**),
because the intentional expert-context prompt requirement is within the
existing gate. Step 2 therefore remains **PARTIAL / NO-GO**: the code-level
ownership and targeted-repair safeguards are corrected, but the fresh report
did not reach final HTML/readiness and Step 3 remains **unstarted/not ready**.

#### Final verified-mode Adjust integration — 2026-10-25 (`9b6ce50c`)

The two producer-side defects exposed by the preceding isolated run are now
corrected. `canonical_fact_text()` carries the validated
`provenance.source_truth_notes_by_page` into the canonical grounding evidence,
so page-bound methodology qualifiers are not lost before semantic grounding.
Verified regeneration now receives explicit nested summary claim-map
authorization: an executive-summary-only repair does not rebind the claim map,
and a claim-map repair rebinds only the authorized item indices. The existing
scope validator and fail-closed evidence rebind remain unchanged.

Provider-free retained-artifact checks on the corrected code showed that an
expert-comment-only repair leaves the summary claim-map hash unchanged, while
a direct summary claim-map repair restores the canonical Adjust CPI evidence
on PDF page 29 (`source_pack: verified_facts`) rather than retaining stale
candidate text. These checks used the existing finalizer and validators and
made no provider calls.

The required fresh isolated Adjust run was executed from clean committed SHA
`9b6ce50cba401a64de17f9aec86fe3f243e211c1` with
`--verified-facts-architecture`, the frozen cohort manifest, and no publication
target. It completed with the following mutually exclusive terminal results:

| Stage/result | Observed outcome |
| --- | --- |
| Visual admission | 20 evaluated; 19 admitted; 1 quarantined; coverage complete |
| Verified facts | 19; source hash `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` |
| Final editorial | 5 insights; 5 summary claims; 0 automatic repairs |
| Grounding/readiness | validation pass (27 semantic validations); publication readiness pass; 0 unresolved retained factual claims; 0 unsupported claims |
| Workflow state | `awaiting_review`; publication false; no WordPress writes |
| Provider usage | 81 calls; 9 file-search calls; 1,017,364 input tokens; 148,466 output tokens; `$0.197232`; 1,151.925 seconds |

The final stable insight identities and authoritative pages were:

| Stable identity | Subject | Physical page |
| --- | --- | ---: |
| `insight-ecommerce-cpi-divergence` | E-commerce CPI divergence | 29 |
| `global-app-growth-2025` | Global app growth | 6 |
| `insight-genai-maturity-efficiency` | GenAI maturity and efficiency | 9 |
| `insight-gaming-subvertical-growth-divergence` | Gaming strategy divergence | 19 |
| `insight-finance-regional-growth` | Finance regional growth | 35 |

Direct PDF review covered pages 6, 9, 13, 19, 27, 29, and 35. The claims
match the cited values, categories, populations, and 2024–2025 timeframe. The
page-13 methodology caveat remains source evidence for grounding but was not
promoted into unsupported final editorial wording. The generated HTML retained
the five report-specific claims, including the conditional gaming
recommendation and the expert-comment distinction between installs and
sessions. Static inspection found one H1, the expected section structure, 57
paragraphs, one image, and nine links; the unsupported methodology-caveat
phrase was absent. The rendered contents preview was also inspected. The
browser-use DOM tool could not load under the available Python 3.14 SDK
(event-loop initialization failure), and no CUA browser surface was available;
therefore browser-DOM inspection is an explicit limitation, not a claimed
pass.

Focused tests passed (`45`), relevant regeneration/grounding/evidence tests
passed (`323`), and scope-regression tests passed (`9`). Ruff, changed-source
mypy, and the contract/prompt gates pass. The full local suite reports
`8,111 passed, 2 skipped, 32 deselected`; its only failure under the default
CPython 3.14 runner is the supported-wheelhouse test, which passes under
CPython 3.12 (`1 passed`). This isolated run is a **PASS** for the Adjust
verified-mode integration gate. Broader Step 2 shadow/live effectiveness
remains **PARTIAL / NO-GO** until the retained frozen cohort has equivalent
fresh evidence, and Step 3 remains **unstarted/not ready**.

#### E17 P1.1 — scoped verified-grounding input optimization — 2026-10-25 (`ee5ea175`)

This is the requested single-report optimization slice, not a new five-report
cohort. The only production change adds the private
`_grounding_batch_prompt_variables()` helper in
`src/generators/validation/grounding.py`. In verified mode it sends
`evidence_json="[]"` for each bounded batch while retaining the complete
canonical verified facts, linked evidence, source qualifiers, and
multi-fact relationships in the existing batch `report_json`. Normal mode
serializes `evidence_texts` exactly as before. The same helper output is used
for initial and post-reuse grounding, and recovery derives its source context
from those variables. The verified relevant-input identity now includes the
`linked_batch_v1` scope marker, so old verified materializations cannot be
reused; the normal-mode identity is unchanged. Prompts, schemas, model policy,
reasoning effort, and repair logic were not changed.

The accepted Adjust baseline was read from the retained run at `9b6ce50c`
and was not rerun. The one fresh optimized run used clean SHA
`ee5ea1754f03014452fad0deb6eb90f1cb1bc217`, a new isolated run directory,
the same retained PDF, and the same source identity plus PDF SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.
No publication target or WordPress write was enabled.

| Measure | Accepted baseline | Optimized run | Change |
| --- | ---: | ---: | ---: |
| Provider calls | 81 | 74 | -7 (-8.64%) |
| Input tokens | 1,017,364 | 831,132 | -186,232 (-18.31%) |
| Output tokens | 148,466 | 142,426 | -6,040 (-4.07%) |
| Reasoning tokens | 67,121 | 59,844 | -7,277 (-10.84%) |
| Reported cached-input tokens | 13,745 | 10,830 | -2,915 (-21.21%); not treated as savings |
| Estimated provider cost | $0.197232 | $0.168355 | -$0.028877 (-14.64%) |
| Runner total duration | 1,144.0 s | 1,063.0 s | -81.0 s (-7.08%) |
| Aggregate provider elapsed time | 1,290.432 s | 1,309.432 s | +19.000 s (+1.47%) |
| File-search calls | 9 | 6 | -3; not attributed to this slice |

The directly attributable grounding-family comparison was:

| Grounding measure | Baseline | Optimized | Change |
| --- | ---: | ---: | ---: |
| Calls | 7 | 7 | 0 |
| Input tokens | 138,905 | 76,560 | -62,345 (-44.88%) |
| Output tokens | 40,564 | 45,617 | +5,053 (+12.46%) |
| Reasoning tokens | 3,593 | 4,987 | +1,394 (+38.80%) |
| Reported cached-input tokens | 12,635 | 10,830 | -1,805 (-14.28%) |
| Estimated grounding cost | $0.033034 | $0.029490 | -$0.003544 (-10.73%) |
| Aggregate grounding provider elapsed | 269.454 s | 328.936 s | +59.482 s (+22.07%) |

The total-run call and cost deltas are not claimed as wholly caused by this
change: the fresh model run selected a different non-grounding call mix and
had stochastic output/reasoning variation. The grounding input reduction and
grounding-family cost reduction are measured directly. Provider cache-write
quantity was not exposed by the retained usage telemetry, so no cache-write
savings are claimed.

Recovery audit (the existing bounded mechanisms only) recorded three
structured-output recovery calls versus zero in the accepted baseline; no
automatic repair and no workflow retry occurred. All three succeeded:

| Observed issue | Recovery | Input / output | Cost / provider time | Result |
| --- | ---: | ---: | ---: | --- |
| Taxonomy primary parse invalid at output limit | 1 | 13,957 / 526 | $0.001659 / 5.383 s | valid recovery |
| Findings primary invalid JSON at output validation | 1 | 10,182 / 1,861 | $0.001949 / 16.293 s | valid recovery |
| Grounding batch 06 structured recovery; primary parse was valid and the retained event did not record a more specific trigger | 1 | 8,912 / 2,869 | $0.002326 / 22.293 s | valid recovery |
| **Total** | **3** | **33,051 / 5,256** | **$0.005934 / 43.969 s** | **3/3 successful** |

The final optimized artifact retained five insights, five metric-spine rows,
and three key figures; the baseline retained five insights, five metric-spine
rows, and one key figure. Fresh model selection changed the stable insight
roster, so the identity difference is reported as run variation rather than
an optimization benefit:

| Stable ID | Page | Source-grounded final wording and review |
| --- | ---: | --- |
| `casino-slots-install-session-counter-signal` | 19 | Casino installs +22% and slots +46%, while sessions fell 5% in both; full chart and text support the install/session distinction. |
| `gaming-subvertical-growth` | 19 | Casual sessions +37% and hyper-casual +31% YoY; the page also supports the linked install values and the recommendation keeps the measures separate. |
| `finance-regional-install-session-growth` | 35 | Finance installs +76% in LATAM and +42% in MENA; the page supports the linked session values and region/timeframe qualifiers. |
| `ecommerce-cpi-subvertical-divergence` | 29 | Deal-discovery CPI rose from $1.44 to $2.26; the page supports the complete global and subvertical CPI tuple. |
| `advanced-generative-ai-efficiency-gains` | 9 | A small advanced-deployment group reportedly achieved gains over 20%; the wording preserves the report’s qualifier and does not generalize the result. |

Direct full-page review of Adjust pages 9, 19, 29, and 35 confirmed the five
final claims and their material qualifiers. The generated summary, expert
comment, metric spine, key figures, and linked claim ledger were checked
against the same canonical facts. Retained-claim validation recorded 28
semantic checks, all supported; unsupported and unresolved retained factual
counts were both zero. Public editorial quality passed, publication readiness
passed, and the only family warning was the pre-existing `quotes_missing`
abstention. The final family remained generated, and no canonical or
publication artifact was promoted.

Focused verification passed **92** grounding/authority tests and **18**
regeneration/finalization tests. Ruff, changed-source mypy, formatting, and
the unchanged prompt-fixture gate passed. The prompt fixture gate remained at
its current enforced baseline comparison of **108,909 vs 108,751 tokens** and
**$0.024114 vs $0.024098**; no prompt, threshold, pricing, or fixture change
was made by this slice. The optimized change is therefore **KEPT**: it shows a
real measured 44.88% reduction in grounding input and $0.003544 grounding-cost
saving with the same validation/readiness outcome and no reviewed factual or
editorial regression. The aggregate provider-elapsed increase and the
single-run/stochastic attribution limits remain documented. E17 remains
Active, broader Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
unstarted/not ready.

#### E17 P1.1 completion verification — 2026-10-25 (`cdb649c5`)

The completion pass made no production change. It closes the two remaining
verification gaps with provider-free regressions. The multi-fact test now
constructs a real verified assertion through `grounding_payload()` and
`_grounding_batches()`: the provider batch contains exactly the two referenced
`verified-fact:*` records, including complete metric observations, source-truth
notes, provenance, and qualifiers; an unrelated third report fact is absent;
and an unknown evidence ID still fails at the existing verified snapshot
boundary. The recovery integration test runs `run_grounding_check()` with the
existing fake provider, captures the actual structured-recovery prompt
variables, and proves that verified recovery receives `evidence_json="[]"`
with the same batch `report_json` as the initial call. The parametrized legacy
case confirms that normal recovery still receives its original serialized
evidence list. The bounded recovery count and incomplete-response gates remain
unchanged.

The retained Adjust audit was reconciled without rerunning either report. Both
runs have seven primary grounding calls. The accepted baseline producer is
`9b6ce50c`; the optimized producer is
`ee5ea1754f03014452fad0deb6eb90f1cb1bc217`. Both use the same source PDF SHA
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` and the
optimized source identity is
`source:8cb648b6bbd9dbae4ec1d915c38cf235|pdf-sha256:ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.
The primary grounding namespace reconciles exactly to 138,905 → 76,560 input
tokens, 40,564 → 45,617 output tokens, 3,593 → 4,987 reasoning tokens,
12,635 → 10,830 reported cached-input tokens, and $0.033034 → $0.029490
estimated cost. The $0.003544 reduction is therefore a primary grounding
namespace saving, not a cached-token saving. The optimized batch-06 recovery
cost of $0.002326 is recorded under the separate structured-output-repair
namespace and is included once in the authoritative whole-run total; adding
that recovery gives an observed grounding-plus-batch-06-repair cost of
$0.031816 versus the baseline primary grounding cost. No ledger event was
double-counted.

The summed grounding provider elapsed time increased by 59.482 seconds
(269.454 → 328.936 seconds). This is an observation only; retained request
bodies do not support a deterministic same-input latency attribution. It is
distinct from report wall-clock duration, which decreased from 1,144.0 to
1,063.0 seconds. The retained records do not expose provider cache-write
quantity or the removed prompt body, so no additional cache or duplication
estimate is claimed.

Batch 06 remains explicitly **unknown in trigger cause**. Its primary event
(`validation_grounding_batch_06_primary`) was parse-valid with blank
`error_code`, `error_stage`, and `schema_validation_status=not_applicable`;
the retained structured-output event does not persist the validation failure
that caused the model-repair call. The repair was parse-valid and completed
successfully (8,912 input / 2,869 output / 192 reasoning tokens, $0.002326,
22.293 seconds). The final validation and publication-readiness artifacts show
zero unsupported or unresolved retained factual claims, so no factual issue
remained. No diagnostic production change was justified by this missing
historical field.

The optimized run recorded three successful structured-output recovery calls,
zero automatic artifact-regeneration repairs, zero workflow retries, and one
workflow attempt. The existing Adjust factual/editorial review remains valid:
five final insights, five metric-spine rows, three key figures, grounding and
publication readiness passing, and no publication write. The new focused suite
passed **236 tests**; the hosted CI run for the follow-up commit passed the
default tests/coverage, both mutation partitions, static gates, and
`release_evidence`. E17 P1.1 is therefore **Complete**. E17 remains Active,
broader verified-facts Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
unstarted/not ready. No E17.2 work was started.

#### E17 P1 visual-claim parallelism experiment — 2026-10-25 (`b27dd1c0`, reverted)

This bounded experiment prepared all source-bound pages sequentially and used
an opt-in two-worker pool only for independent `_evaluate_claim()` calls. It
preserved indexed result order, per-claim correction/verification sequencing,
the existing provider limiter, cache, usage ledger, retries, and fail-closed
worker-exception handling. Deterministic acceptance tests passed before the
live run; the production/configuration change was then reverted in
`d064e39d` and the experiment-only test was removed in `a594cea7` after the
quality gate failed. The default sequential implementation is restored.

The one fresh isolated Adjust run used clean `b27dd1c0`, the retained source
identity and PDF SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`,
`VERIFIED_VISUAL_CLAIM_PARALLEL_WORKERS=2`, verified-facts architecture,
`shared_batch=False`, and no publication target. Output was isolated under
`C:\\ml-vfa-20261025-adjust-p1-parallel-run`; no WordPress write occurred.

| Measure | Retained P1.1 scorecard | Parallel run | Change |
|---|---:|---:|---:|
| Provider calls | 74 | 78 | +4 (+5.41%) |
| Input tokens | 831,132 | 942,509 | +111,377 (+13.40%) |
| Output tokens | 142,426 | 164,256 | +21,830 (+15.33%) |
| Estimated provider cost | $0.168355 | $0.192903 | +$0.024548 (+14.58%) |
| Total runner duration | 1,063.000s | 963.246s | -99.754s (-9.38%) |
| Structured-output recoveries | 3 | 2 | -1; one recovery exhausted |
| Automatic repairs | 0 | 0 | unchanged |

The retained per-namespace profile records 18 visual correction and 17 visual
verification calls; the task's retained scorecard describes 20 candidates and
19 admitted facts. That source-evidence discrepancy is preserved rather than
normalized. Against the available profile, the candidate recorded 20/20
visual calls. The visual provider-request envelope fell from **362.039s to
218.996s (-39.51%)**, with measured overlap of **190.060s** and maximum
simultaneous visual calls increasing from **1 to 2**. Summed provider elapsed
time increased from **344.050s to 408.952s (+18.86%)**, so overlapping call
durations are not reported as wall time. Visual limiter wait was 0ms in both
profiles; total report limiter wait was 4,226ms versus 4,229ms. One candidate
needed a second correction attempt in each run; the parallel run's second
attempt also produced the paired second verification call. No visual provider
call failed or retried at the transport layer.

The parallel terminal audit evaluated 19 of 19 supplied candidates, admitted
16 facts and quarantined 3, while the requested retained scorecard expects 20
candidates and 19 admitted facts. It still produced five final insights. Full
PDF review found those five final texts source-supported: finance CPI and
retention on page 37, gaming installs/sessions on page 19, e-commerce partner
counts on page 31, and the qualified advanced-GenAI result on page 9. Public
editorial quality passed and no independently confirmed unsupported material
claim was found in those five texts. Nevertheless, the terminal grounding
artifact was non-substantive, the report ended `validation_failed`, reported
28 unresolved retained factual claims, and publication readiness failed. The
two structured-output recovery sequences were: grounding batch 01 repair and
regeneration succeeded; grounding batch 04 repair and regeneration remained
invalid. These are the observed recovery records, not newly invented repair
scenarios.

**Decision: REVERT / FAIL for the optimization.** The end-to-end reduction
was below the required 10% threshold, cost and raw token usage increased, and
the only fresh candidate run did not preserve the grounding/readiness gate or
the requested admitted-fact coverage. The single stochastic run does not prove
that concurrency caused the grounding failure, but it is sufficient to reject
this candidate under the pre-declared quality rule. No broader worker setting
was enabled, and no additional optimization was started. Step 2 remains
**PARTIAL/NO-GO** and Step 3 remains **unstarted/not ready**.
#### P1 verified-grounding recovery diagnostics — 2026-10-25 (`1d496ece`)

The retained Adjust experiment was inspected provider-free from the exact run
under `C:\\ml-vfa-20261025-adjust-p1-parallel-run`, including the usage ledger,
validation artifacts, workflow stage records, and the original PDF identity
(`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`). Batch
04's earliest observable failed contract was post-provider grounding acceptance:
the primary provider event was parse-valid, but the persisted validation result
was non-substantive for grounding and recorded `28` unresolved factual results.
The exact coverage/protected-fact sub-rule and offending IDs were not persisted;
the remediation record retained `context_keys=[]`. Therefore the historical
trigger is **unknown**, and the diagnostic correction is not claimed to explain
that run's failure.

| Batch-04 attempt | Provider result | Tokens (input / output / reasoning / cached input) | Cost | Provider time |
| --- | --- | ---: | ---: | ---: |
| Primary | completed; parse `valid`; schema status `not_applicable`; no provider error | 13,731 / 8,688 / 785 / 1,805 | `$0.005555` | 71.698 s |
| Model repair | completed; parse `invalid`; schema status `not_applicable`; no provider error | 21,247 / 8,192 / 8,192 / 0 | `$0.006221` | 62.926 s |
| Regeneration | completed; parse `invalid`; schema status `not_applicable`; no provider error | 21,234 / 8,192 / 8,192 / 0 | `$0.006219` | 56.737 s |
| **Total** | **1 parse-valid primary, 2 invalid bounded recoveries** | **56,212 / 25,072 / 17,169 / 1,805** | **`$0.017995`** | **191.360 s** |

Both recovery responses reached the configured 8,192-token output ceiling,
which is evidence of a separate truncation/invalid-JSON failure after the
primary semantic/coverage failure. No retained artifact contains the original
model response or its missing/unknown item list, so no stronger causal claim is
made. The grounding stage and semantic-validation stage were recorded as
`validation_failed`; regeneration was skipped at the workflow layer. The five
final insights were not treated as factually false solely because the grounding
artifact was incomplete.

The confirmed production defect was the structured-output recovery allowlist:
`missing_or_ambiguous_public_item_ids`, `unknown_item_ids`, and `item_ids` were
emitted by the existing grounding validator but dropped before model repair and
terminal retention. `structured_output_service.py` now admits those existing
identifier lists, applies the existing safe identifier character/length policy
to repair feedback, and retains the bounded
`missing_or_ambiguous_public_item_count`. The grounding validator, protected
dimensions, source bindings, schemas, retry budget and prompts were unchanged.

Before the correction, a coverage error reached repair as only
`grounding_claim_check_coverage_invalid:Verified grounding must return one
identity-matching verdict for every public item`. Afterward the same existing
validator path reaches repair as that message plus
`missing or ambiguous public item ids: insight:fact-2:so_what`; unsafe and
overlong identifiers are excluded. A fake repair then succeeds on the same
single model-repair attempt. Repeated invalid output still makes exactly the
existing primary → deterministic check → model repair → regeneration sequence
and fails closed with bounded identifier-only context.

Focused provider-free regressions passed: **7** new recovery/grounding tests,
the affected grounding/validation/recovery cohort **250 passed**, changed-source
mypy passed, and Ruff/formatting passed for changed clean files. A clean
committed-source worktree also passed the full repository type gate: **786
source files, 0 tracked errors**. The dirty task worktree still contains the
pre-existing protected untracked `src/generators/artifact_normalization (2).py`
duplicate (one unrelated unbaselined mypy error plus the environment's CPython
3.14 mypy assertion), so its direct type-gate result is not a clean signal; no
new error was reported for the changed production file. No provider call,
publication write, visual-parallelism run, or E17.2 work was performed.

**Verdict: PASS for the confirmed recovery-diagnostics correction; PARTIAL for
historical/live effectiveness.** Deterministic evidence proves actionable IDs
now reach bounded recovery, while the retained batch-04 cause and any live
first-repair improvement remain unproven because the original diagnostics were
not retained. Step 2 remains **PARTIAL/NO-GO** and Step 3 remains
**unstarted/not ready**.

#### P1 grounding recovery output budget and feedback correction — 2026-10-25

Current-source inspection confirmed two independent recovery defects exposed by
the retained Adjust batch-04 audit. The primary grounding policy already
allowed 16,384 output tokens, while the shared structured-output recovery
family and its explicit `repair` and `regenerate` policies allowed only 8,192.
The effective recovery policies were corrected to 16,384 in
`src/config/app.yaml`; the explicit repair policy was also aligned to the
required existing medium reasoning effort. Model, timeout, seed/temperature,
JSON-schema identity, zero provider retries, and same-provider fallback remain
governed by the existing policies. No prompt, schema, validator, batch-size or
publication behavior changed. The shared-family change applies to other
structured-output recovery callers that resolve through the same policy.

The provider-free contract path now proves
`app.yaml -> execution policy -> PreparedPromptBundle.effective_max_output_tokens
-> OpenAIJSONPromptRequest.max_output_tokens -> provider max_completion_tokens`.
The configured cap remains authoritative when a smaller compatibility
call-site value is supplied. The cap is already included in the execution
identity and policy hash, so a changed cap cannot reuse the prior semantic
cache identity.

When model repair returns empty text, regeneration now receives the original
primary response plus the original exact validation feedback and the bounded
empty-repair error. A non-empty repair continues to be the sole regeneration
source with its latest validation feedback. Recovery remains exactly primary,
deterministic evaluation, model repair, and regeneration; no fourth provider
call was added. Exhausted recovery now retains the original primary
`error_class` alongside the terminal recovery class in the existing bounded
attempt/outcome and `StructuredOutputFailure` context, without retaining raw
responses or prompts.

| Contract | Before | After |
| --- | ---: | ---: |
| Primary grounding output cap | 16,384 | 16,384 |
| Model-repair output cap | 8,192 | 16,384 |
| Regeneration output cap | 8,192 | 16,384 |
| Empty-repair regeneration feedback | repair-only error | primary exact errors + repair error |
| Exhaustion diagnostic | terminal error class | original primary + terminal classes |

Focused provider-free verification passed **47 tests** for structured-output
service, policy resolution, governed request construction and provider request
translation. The broader recovery, prompt, routing, report-generation,
grounding, claim-validation and readiness cohort passed **576 tests**. Ruff and
format checks passed for all five changed Python service/test files. The full
repository type gate remains blocked by the protected pre-existing untracked
`src/generators/artifact_normalization (2).py` error and the local CPython 3.14
mypy assertion; no changed-file error was reported before that assertion.

The accepted retained Adjust reference (74 calls, 831,132 input tokens,
142,426 output tokens, `$0.168355`, 1,063 seconds, five insights and passing
grounding/editorial/readiness) was **not rerun**. No provider call, live
recovery replay, visual parallelism run, E17.2 output compaction or publication
write was performed. Consequently this correction proves the governed budget,
feedback and diagnostic contracts but does not claim that a fresh provider run
would recover the historical batch-04 response or improve live quality.

**Verdict: PASS for the deterministic recovery correction; PARTIAL for live
recovery effectiveness.** Step 2 remains **PARTIAL/NO-GO**, Step 3 remains
**unstarted/not ready**, and E17 remains Active.

#### P1/P2 recovery correction and fresh verified-facts Adjust evaluation — 2026-10-25 (`654a5cf1`)

The corrected producer SHA was `654a5cf1a7f12113b28c5d70f23fde61025e40d8`.
The P1 change restores the existing structured-output repair policy to
`reasoning_effort: low` while retaining the requested 16,384-token cap. The
P2 change in `src/services/structured_output_service.py` merges bounded,
sanitized diagnostic context from the primary, repair, and regeneration
evaluations rather than selecting only the last context. It preserves the
original and terminal error classes, keeps safe actionable identifiers in
deterministic original-first order, deduplicates them, and retains no raw
responses, prompts, or source text. No prompt, schema, validator, retry count,
grounding rule, publication rule, or visual-parallelism setting changed.

Provider-free verification passed the focused recovery/policy/diagnostic
checks (**6 passed**) and the affected grounding, validation, report-generation
and recovery cohort (**579 passed in 29.49s**). Ruff and formatting passed for
the changed clean files. The local dirty worktree type invocation remains
unusable because of the protected untracked duplicate
`src/generators/artifact_normalization (2).py` and the CPython 3.14/mypy
`dotenv.main.find_dotenv` assertion; the clean hosted type gate passed. Hosted
CI run [40199401059](https://github.com/mbrakker/marketlense/actions/runs/40199401059)
passed tests, Ruff, hosted type checks, schema/architecture gates, both
mutation partitions, and `release_evidence`.

One fresh provider-backed run was executed from the corrected SHA, with no
publication target or WordPress write:

```text
python -u scripts/quality/run_frozen_reliability_cohort.py \
  --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json \
  --sources-root "C:\\Programing\\Market lense-step2-final" \
  --runs-root "C:\\Programing\\Market lense-step2-final\\tmp\\adjust-recovery-final-20261025" \
  --max-duration 7200 \
  --report-ids cohort-b638414df0b1fccea1cd \
  --verified-facts-architecture
```

The input PDF was verified before processing: SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.
The isolated terminal result is `awaiting_review` with validation and
publication readiness `pass`, `published=false`, one workflow attempt, and
no terminal failure. The retained run directory is
`tmp/adjust-recovery-final-20261025/frozen-reliability-9uhv62el7/members/cohort-b638414df0b1fccea1cd/ias-first-attempt-47jbsxl/`;
the final HTML and JSON artifacts are under its `output/` directory.

| Measure | Accepted baseline (not rerun) | Fresh run | Change |
| --- | ---: | ---: | ---: |
| Provider calls | 74 | 75 | +1 (+1.35%) |
| Input tokens | 831,132 | 707,174 | -123,958 (-14.92%) |
| Output tokens | 142,426 | 115,340 | -27,086 (-19.02%) |
| Estimated provider cost | $0.168355 | $0.147414 | -$0.020941 (-12.44%) |
| Runner duration | 1,063.000s | 1,001.563s | -61.437s (-5.78%) |
| Visual candidates | 20 (baseline record) | not exposed by result contract | not comparable |
| Verified facts admitted | 19 | 17; complete for emitted roster | -2; stochastic roster difference |
| Final insights | 5 | 5 | unchanged |
| Structured-output recoveries | 3 | 0 | -3; path not exercised |
| Automatic repairs | 0 | 0 | unchanged |
| Grounding / editorial / readiness | PASS / PASS / PASS | PASS / PASS / PASS | no regression observed |

The fresh usage profile records 49,725 reasoning tokens, 10,830 cached-input
tokens, 8 file-search calls, zero provider errors, 4.206s of limiter waits,
and provider elapsed time of 1,218.159s (active provider-time union
848.088s; maximum concurrency 6). Grounding used 7 calls and cost $0.027096;
visual correction used 17 calls and visual verification 17 calls, sequentially,
with no visual retries. No repair or regeneration call occurred, so there is
no live repair response, recovery cost, output-cap event, or repair latency to
attribute. The deterministic tests exercise the existing primary -> check ->
repair -> regeneration sequence and the 16,384-token request policy, but this
run does not prove live recovery effectiveness or resolve the historical
Adjust batch-04 trigger, whose original diagnostic was not retained.

The final HTML was inspected against the original PDF and the retained
full-page PNGs (no cropped page was used). The five selected insight/evidence
pairs were:

| Stable fact | Physical page | Review result |
| --- | ---: | --- |
| `ecommerce-finding-installs-sessions` | 27 | -10% installs and +5% sessions, 2025; distinct signals retained |
| `gaming-hypercasual-sessions` | 19 | +31% sessions and +4% installs, 2025; no causal inference |
| `finance-global-installs` | 34 | -4% installs and +21% sessions; comparison-basis caveat retained |
| `gaming-casual-sessions` | 19 | +37% sessions, 2024–2025; not treated as absolute scale |
| `gaming-casual-installs` | 19 | +19% installs, 2024–2025; not treated as forecast |

The prose was commercially useful and specific: it separates acquisition from
engagement, keeps the finance comparison caveat, and recommends separate
install/session review without claiming unsupported causality. The final
retained-claim validation found **0 unsupported and 0 unresolved material
factual claims**; five descriptive/interpretive items were intentionally
outside factual semantic validation. The intermediate evidence-fidelity pack
correctly rejected three unsupported introduction/forecast findings (5.8B
users, 10.6%/$167B spending, and $1.23T by 2035) and none reached the final
artifact. The only validation warning was `quotes_missing`; the report did
not fabricate quotations. Public editorial quality and readiness passed.

This is a successful single-report integration result, not proof of stable
selection quality: the fresh run admitted 17 rather than 19 facts and did not
exercise recovery. **Verdict: PASS for the deterministic P1/P2 correction and
this Adjust report; PARTIAL/NO-GO for broader Step 2.** Step 3 remains
unstarted/not ready. No canonical artifact was promoted or mutated, and no
WordPress publication occurred.

#### P1 editorial-selection quality and Adjust candidate-funnel verification — 2026-10-25 (`83870a1c`)

The retained Adjust checkpoint was traced before the fresh evaluation. The
archived `report_vs/artifacts/insights_candidates` record contained an empty
normalized output, but its raw provider response was not retained. The usage
ledger shows one completed primary candidate call (4,687 input / 704 output /
675 reasoning tokens; `$0.000821`; parse-valid; no schema or provider error;
no recovery call). The existing artifact contract treats an empty candidate
array as a permitted abstention, so normalization preserved the empty result
and the existing findings fallback supplied the downstream roster. The retained
evidence therefore establishes **accepted empty output followed by fallback**;
it cannot prove whether the provider explicitly returned `[]` or omitted the
root before normalization. No independent candidate-generation defect is
confirmed, and the fallback remains the safety mechanism.

The implementation changes are limited to the existing selection boundaries:

- `fallback_artifact_insights_from_findings()` now resolves exact finding IDs
  and exact `finding.section_id` references, with direct IDs taking precedence;
  fidelity-approved findings retain their real IDs, pages and evidence. Theme
  coverage is selected before a concentration-aware fill, using existing
  confidence, score, plan priority and section metadata without keyword
  scoring or fixed quotas.
- `remap_editorial_plan_to_verified_facts()` receives the original findings
  pack and maps section references only through admitted fact provenance. Direct
  aliases remain authoritative; absent, conflicting or unadmitted mappings are
  dropped and the existing minimum-coverage error remains fail-closed.
- Verified final selection now passes `preserve_all=True`, so every admitted
  fact remains an alternative until the final model chooses the existing target
  count. The selection cache identity advanced from `evidence_backed_shortlisting:11`
  to `:12`. A bounded `_cache.candidate_generation` audit records model output,
  fallback output, selected source and verified-admission counts without raw
  prompts or responses.

Provider-free replay of the exact retained 36-finding Adjust input reproduced
the old bounded roster as 17 items: gaming 9, finance 5, ecommerce 1,
introduction 2, and AI/cross-platform 0. The corrected fallback still returned
17 items, but its coverage was gaming 4, finance 4, ecommerce 3,
introduction 4, AI 1 and cross-platform 1. The supported
`ecommerce-finding-retention-cpi` finding was present and assessed in the
eligible inventory; it was not forced into the bounded replay shortlist. The
old admitted 17-fact roster became only 5 pre-final candidates; the corrected
verified selector retains all 17 as final-model alternatives. The original old
roster did not contain admitted AI or cross-platform facts, so those themes
correctly remain absent in that replay; the new section remapping admits them
only when their source-linked facts are actually present.

One fresh isolated Adjust run was then executed from clean commit
`83870a1cb0064a1d37ecd5d5cb70653938c927f8` using the frozen source manifest,
`--verified-facts-architecture`, sequential visual processing, and no
WordPress target. The source PDF SHA-256 was
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.

| Funnel stage | Observed result |
| --- | ---: |
| Fidelity-supported findings in fresh run | 27 |
| Model candidate checkpoint | 7 |
| Findings fallback candidates | 17 |
| Pre-visual selected candidates | 24 (`model_and_fallback`) |
| Visual candidates evaluated / admitted / quarantined | 24 / 24 / 0 |
| Remapped verified-plan themes | 4; only admitted source-linked themes retained |
| Eligible final-model candidates | 24 |
| Final insights | 5 |

The fresh run completed terminally but failed the existing semantic grounding
gate: 84 provider calls, 983,264 input tokens, 134,403 output tokens, 56,271
reasoning tokens, 10,830 cached input tokens, `$0.182050`, and 1,098.765
seconds. It used 24 visual-correction and 24 visual-verification calls, 7
grounding calls, and zero structured-output recovery or automatic repairs. All
provider calls completed. Visual admission passed 24/24 with 24 canonical
facts; public editorial quality passed with zero listed issues, but validation
failed on `insight:finance-latam-growth-2025:so_what`: the final wording
described the supported install result as “acquisition”. The source supports
installs and sessions, not that broader acquisition interpretation. This is a
real fail-closed downstream quality result, not an unsupported claim promotion.
No final HTML/PDF publication artifact was produced and no WordPress or
canonical write occurred.

The fresh final five were source-bound to PDF pages 6 (global app growth), 19
(strategy-game divergence), 27 (global ecommerce installs/sessions), 35
(LATAM finance growth), and 29 (deal-discovery CPI). Direct inspection of the
retained full-page images confirmed the numeric/category relationships for
these five; the grounding blocker remains on the qualitative interpretation.
Compared with the immediately preceding retained run (75 calls, 707,174
input, 115,340 output, `$0.147414`, 1,001.563 seconds, 17 admitted facts),
the fresh run used +9 calls, +276,090 input tokens, +19,063 output tokens,
`+$0.034636` and +97.202 seconds. The additional visual workload was 7
correction and 7 verification calls. These are measured run differences, not
causal quality claims; the provider generated a different 27-finding input.

**Verdict: PASS for the deterministic selection/fallback correction and
candidate-funnel audit; PARTIAL/FAIL for the required fresh report-quality
gate.** The empty checkpoint is now explainable and no significant candidate
coverage was silently lost, but the one unsupported qualitative interpretation
keeps grounding/readiness failed. Step 2 remains **PARTIAL/NO-GO** and Step 3
remains **unstarted/not ready**. No further stochastic rerun was performed.

#### P1 autonomous candidate recovery and fresh Adjust verification — 2026-10-25 (`5182502d`)

The retained empty candidate checkpoint was traced to an accepted, parse-valid
empty primary result at the candidate-generation boundary. The old usage row
has no schema/provider error or recovery attempt, and the old normalizer then
invoked findings fallback unconditionally. The raw provider response was not
retained, so the evidence cannot distinguish an explicit `[]` from a missing
root normalized to the same checkpoint; it does establish that empty output
was accepted without bounded recovery. The preceding `83870a1c` run supplied
seven model candidates plus 17 fallback candidates and reached the grounding
gate with a qualitative “acquisition” broadening of supported finance-app
installs.

The correction is confined to existing boundaries. When eligible
fidelity-approved findings satisfy the existing minimum, empty/missing
candidate output is no longer accepted as an abstention: the existing bounded
model-repair/regeneration path is available. Findings fallback remains the
fail-closed safety path when the primary roster lacks minimum or editorial-plan
theme coverage, but is not invoked when the primary is already adequate. The
interpretation-only regeneration path now keeps the canonical fact available
for targeted `so_what`/`now_what` wording repair; factual/metric failures still
quarantine as before. Selection cache version advanced to 13 and the private
candidate audit records the source, counts, recovery disposition, fallback
reason and verified admission.

One fresh provider-backed Adjust run from commit `5182502d` used the frozen
PDF (SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`). It
completed with 53 provider calls, 566,731 input tokens, 118,909 output tokens,
`$0.135151`, and 831.0 seconds; no automatic repair, structured-output
recovery, workflow retry, publication, or WordPress write occurred. The final
state was `awaiting_review`, validation passed, and publication readiness
passed. Candidate audit values were model output 8/8 raw-to-normalized,
eligible evidence available, fallback not invoked (`primary_adequate`), 8
selected, 7 admitted verified facts, and one quarantined conflicting fact.

The final five were independently checked against the original full PDF:

| Stable ID | Page | Result |
| --- | ---: | --- |
| `insight-ecommerce-install-session-divergence` | 27 | -10% installs / +5% sessions; distinct signals retained. |
| `insight-ecommerce-retention-by-day` | 29 | Day-1 retention 13.2% to 12.6%; no cause asserted. |
| `insight-finance-install-session-divergence` | 34 | -4% installs / +21% sessions; no “acquisition” broadening. |
| `insight-genai-maturity-efficiency` | 9 | Over-20% result remains scoped to the small advanced-deployment group. |
| `insight-ecommerce-cpi-subvertical-divergence` | 29 | Deal-discovery CPI $1.44 to $2.26; not generalized to all e-commerce. |

All five retained one direct `verified-fact:` evidence ID and physical page,
and independent review found no material factual, numeric, provenance, or
unsupported-causality defect. Compared with the failed `83870a1c` run, the
fresh run used 31 fewer calls, 416,533 fewer input tokens, `$0.046899` less
cost, and 267.765 fewer seconds; compared with the preceding accepted
`654a5cf1` run, it used 22 fewer calls and `$0.012263` less cost. These are
stochastic run comparisons, not proof of universal live selection improvement.

Focused tests and static checks passed; the full default suite had 8,141
passes, 2 skips, 32 deselections and 24 subtests, with one local CPython 3.14
native-wheelhouse failure that passed under CPython 3.12. The PDF candidate
benchmark passed all four rows with matching hashes/signatures. Full per-claim
review, audit fields, artifact paths and limitations are in
[the P1 evidence supplement](verified-claims-step2-p1-candidate-recovery-20261025.md).

**Verdict: PASS for the P1 candidate-generation/recovery correction and this
fresh Adjust report; PARTIAL/NO-GO for broader Step 2 live selection
effectiveness.** Step 3 remains unstarted/not ready. No canonical artifact was
promoted or mutated.

**Step 1 selection-coverage correction and fresh Adjust follow-up —
2026-10-25:** `e0e7cb22c043c794dc6540094e04b65245092e29` separates the two-item
minimum from the five-item editorial target, supplements a short model roster
only from bounded, distinct, fidelity-approved findings, resolves section-ID
theme references through original findings, and preserves explicit verified
final-model selection without arbitrary padding. Post-admission diagnostics
record planned/supported/lost themes and alternatives. The fresh run returned
8 model candidates, invoked no fallback, admitted 7 of 8 facts, quarantined
the conflicting `cross-platform-data-satisfaction` fact, supported 4 of 5
planned themes, lost one optional (not central) cross-platform theme, and kept
7 admitted alternatives. The explicit final model selected five facts on
pages 34, 19, 9, 27, and 21; direct PDF review found no material factual or
editorial defect. It used 56 calls, 545,144 input tokens, 113,908 output
tokens, 47,106 reasoning tokens, `$0.125492`, and 924.187 seconds, versus the
accepted `5182502` run's 53 calls, 566,731 input, 118,909 output, 49,057
reasoning, `$0.135151`, and 831.0 seconds. These stochastic run deltas are
not attributed to the selector. Provider-backed readiness failed only on the
existing renderer's internal `verified-fact:` public-identifier leak; the
minimal correction `8bd2b15f` suppresses that label, and provider-free
rerender evidence reports zero leaks and zero editorial blockers. The
provider-backed readiness record was not rewritten and no second provider run
was made. The first nested invocation failed preflight with
`analysis_pack_path_too_long` and is excluded from quality counts. The result
is **PASS** for deterministic coverage/selection and renderer corrections but
**PARTIAL/NO-GO** for broader Step 2 live selection effectiveness; Step 3
remains unstarted/not ready. Full ledger and artifact paths are in the
[P1 candidate-recovery supplement](verified-claims-step2-p1-candidate-recovery-20261025.md).
