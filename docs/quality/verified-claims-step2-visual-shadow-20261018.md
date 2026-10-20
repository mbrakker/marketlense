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
