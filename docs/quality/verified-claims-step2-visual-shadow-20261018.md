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
