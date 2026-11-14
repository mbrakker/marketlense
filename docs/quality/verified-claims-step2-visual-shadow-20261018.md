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

### Single-report live end-to-end acceptance — Adjust — 2026-11-02

This is the one fresh, isolated provider-backed run requested for the current
HEAD `f68d8e75b19697b924ec6c075fd34dbafabdde2c`. No source, prompt, model,
threshold, canonical artifact, or production code was changed for the run; no
WordPress or publication write was attempted. The run was not rerun after its
terminal result.

**Input and identity.** The exact frozen Adjust source was the retained local
PDF `mobile-app-trends-2026.pdf`, 41 pages, 3,571,623 bytes, MD5
`b638414df0b1fccea1cd8a93eaf8f5aa`, and SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`. The
preflight admitted the report with report ID
`cohort-b638414df0b1fccea1cd`, source identity
`source:8cb648b6bbd9dbae4ec1d915c38cf235`, zero provider calls, and no writes.
The live run retained the same source identity and PDF hash, ran in isolated
fresh state, and used workflow root
`d5df8e7a-4713-4b2f-aed3-7771572ee340`.

**Run and artifact locations.** The complete run root is
`C:\ml-adjust-e2e-20261102\frozen-reliability-6oe2ci36`; the member root is
`C:\ml-adjust-e2e-20261102\frozen-reliability-6oe2ci36\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-gkvz6nvh`.
The authoritative runner result is `cohort_result.json`. The report-analysis
artifacts are under the member's
`output\mobile-app-trends-2026-pdf\report_analysis` directory, including
`artifacts.json`, `evidence_fidelity.json`, `validation.json`,
`public_editorial_quality_before.json`,
`public_editorial_quality_after.json`, and
`validation_claim_reuse_decisions.jsonl`. The source-page review renders are
under `C:\ml-adjust-e2e-20261102\original_pdf_pages`.

**Stage ledger.**

| Stage | Observed result | Evidence |
|---|---|---|
| Preflight and source admission | PASS; 1/1 admitted | Exact source hash and source identity matched; no provider call in preflight |
| Extraction, DocMap, findings, and evidence preparation | Completed | Analysis artifacts were emitted from the retained PDF; no source identity substitution was observed |
| Visual/verified-fact admission | PASS; 7 evaluated, 7 admitted, 0 quarantined | Admission audit `coverage_complete=true`, `verified_fact_count=7`, source hash exact |
| Candidate and final insight generation | Completed; 7 candidates and 7 final insights | Stable IDs and source-bound evidence IDs/pages were retained in `artifacts.json` |
| Grounding and retained-claim validation | Retained factual claims: 0 unsupported, 0 unresolved | 40 claims were newly validated; no prior package was reusable; evidence-fidelity separately rejected two non-retained source-finding candidates |
| Independent public-editorial semantic review | FAIL closed | Both primary review responses were invalid JSON; bounded structured recovery did not produce an acceptable review |
| Final validation and readiness | FAIL / FAIL | `validation_failed`, rule `public_editorial_quality.semantic_review_unresolved` |
| HTML and publication | Not produced / not attempted | `render_complete.json` has `rendered_html: ""`; `FinalHtml=0`; `published=false`, no WordPress post |

The runner reports one workflow attempt, zero workflow retries, zero automatic
repairs, seven file-search calls, and two structured-output recovery cycles.
The canonical usage ledger (`llm_usage.sqlite`) contains 153 completed
provider rows: two primary public-quality calls returned invalid JSON, and the
bounded recovery ledger contains two repair and two regenerate calls across
those review passes. This distinction is recorded rather than treating
recovery rows as workflow retries. No provider call failed at the transport or
provider-status layer.

The terminal failure is not a source-fact admission failure. Both
`public_editorial_quality_before.json` and `public_editorial_quality_after.json`
are fail-closed with the same hard issue,
`public_editorial_quality.semantic_review_unresolved`; recovery status is
`abstained` and not eligible for automatic repair. The review measurements were
still material (role diversity 5, repeated syntax 0, average insight length
15.57 words, source-note completeness 1, action specificity 1), but they do
not authorize readiness without a valid independent semantic-review result.

**Source-grounded audit of the generated editorial artifact.** No final HTML
was available, so HTML completeness, layout, internal-ID leakage, and public
render quality are **not** passed or claimed. I independently rendered and
inspected the full original PDF pages used by the final insights (PyMuPDF was
used because Poppler was unavailable) and compared the final artifact text in
`artifacts.json` with those pages:

| Final stable ID | Page | Audit result |
|---|---:|---|
| `genai-maturity-outcomes` | 9 | Low/moderate maturity, the small advanced-deployment group, reported gains over 20%, and the experimentation/discipline distinction are source-supported and appropriately qualified |
| `cross-platform-measurement-satisfaction` | 11 | Around 31% and the cross-platform measure are supported; the final wording does not add an unstated period or geography |
| `gaming-strategy-engagement` | 19 | Global strategy sessions +57% and installs -1% from 2024 to 2025 are supported as separate metrics |
| `ecommerce-installs-sessions-rebound` | 27 | Global e-commerce installs -10% and sessions +5% in 2025 are supported; the unsupported monthly rebound detail is not in the final wording |
| `ecommerce-marketplace-retention` | 29 | Global day-1 retention 13.2% to 12.6% from 2024 to 2025 is supported; the day checkpoint is preserved |
| `finance-session-duration` | 36 | Global finance-app session length 7.18 minutes and +8% in 2025 are supported |
| `finance-paid-organic-ratio` | 38 | Global 1.13 and LATAM 3.26 paid/organic ratios and the 2024–2025 comparison are supported |

The exact final claim texts audited were: “For global e-commerce apps,
installs declined 10% year over year in 2025 while sessions increased 5%.”;
“Most organizations report low or moderate GenAI maturity; a small group with
advanced deployment reportedly achieved efficiency gains over 20%.”; “Around
31% of marketers report complete satisfaction with their ability to unify and
read data across platforms.”; “Globally, strategy-game sessions grew 57% year
over year from 2024 to 2025, while installs declined 1%.”; “Global e-commerce
app day-1 retention fell from 13.2% in 2024 to 12.6% in 2025.”; “Global
finance-app session length increased 8% to 7.18 minutes in 2025.”; and “From
2024 to 2025, finance-app paid/organic ratios increased to 1.13 globally and
3.26 in LATAM.”

The final seven retained insights therefore had no independently confirmed
unsupported material factual claim in this artifact-level review. The separate
evidence-fidelity result contains 39 supported and 2 unsupported findings:
the gaming CPI/$0.56 proposition on page 22 and a December/November rebound
misattribution on page 27. Both were rejected source-finding candidates and
were not retained in the seven final insights. They must not be counted as
published or retained factual errors, but they also must not be reported as
41/41 supported findings.

The seven admitted facts have exact source identity, physical page, evidence
ID, and verified outcome. The final artifact retained those bindings and
protected fields. `metric_spine` contains 6 rows and `key_figures` contains 5;
the five `chart_insight_cards` are present but all are marked
`weak_evidence` with empty candidate IDs and `crop_qa_accepted=false`. That is
a downstream linkage limitation, not evidence that the seven source facts were
unsupported.

**Selection comparison with the accepted Adjust baseline.** The baseline was
not rerun. The retained accepted run `8fe133005b62e27b6681d88c3d8dd2d61a9777a0`
had 6 visual candidates/admissions, 5 final insights, 52 provider calls,
512,814 input tokens, 116,754 output tokens, 52,648 reasoning tokens, 10,830
cached input tokens, `$0.123682`, 946.248 seconds, 6 file-search calls, 1
structured recovery call, zero automatic repairs, and validation/readiness
PASS/PASS. The current run had 7 admitted verified facts and 7 final insights,
153 calls, 1,296,653 input tokens, 198,143 output tokens, 82,295 reasoning
tokens, 179,835 cached input tokens, `$0.230052`, 1,527.079 seconds, 7
file-search calls, 2 structured recovery cycles, zero automatic repairs, and
validation/readiness FAIL/FAIL.

| Measurement | Baseline | Current | Change |
|---|---:|---:|---:|
| Provider calls | 52 | 153 | +101 (+194.23%) |
| Input tokens | 512,814 | 1,296,653 | +783,839 (+152.85%) |
| Cached input tokens | 10,830 | 179,835 | +169,005 (+1,560.53%) |
| Output tokens | 116,754 | 198,143 | +81,389 (+69.71%) |
| Reasoning tokens | 52,648 | 82,295 | +29,647 (+56.31%) |
| Total input + output | 629,568 | 1,494,796 | +865,228 (+137.43%) |
| Estimated cost | `$0.123682` | `$0.230052` | +`$0.106370` (+86.00%) |
| Total wall-clock | 946.248s | 1,527.079s | +580.831s (+61.38%) |
| File-search calls | 6 | 7 | +1 |
| Structured recovery | 1 | 2 | +1 |
| Automatic workflow repairs | 0 | 0 | unchanged |
| Final validation/readiness | PASS/PASS | FAIL/FAIL | regression |

The current final roster is also different: it retains
`ecommerce-installs-sessions-rebound`, `genai-maturity-outcomes`,
`cross-platform-measurement-satisfaction`, `gaming-strategy-engagement`,
`ecommerce-marketplace-retention`, `finance-session-duration`, and
`finance-paid-organic-ratio`. The baseline roster contained
`advanced-genai-efficiency-gains`, `gaming-strategy-growth-gap`,
`gaming-casino-slots-divergence`, `ecommerce-installs-sessions-diverge`, and
`ecommerce-subvertical-cpi-divergence`. Because this was a single current-head
run with no implementation change from the baseline comparison, the roster
difference is observed provider/pipeline variability, not attributable
selection improvement. The current run cannot be used to claim better live
selection quality.

**Verdict and correction list.** Source identity, verified-fact admission,
physical-page provenance, protected factual bindings, and retained-claim
factual safety are **PASS** for this run. The single-report end-to-end
acceptance is **FAIL** because independent public-editorial semantic review
remained invalid after bounded recovery, final validation failed, and no final
HTML was produced. The frozen-five/Step 3 decision is **NO-GO**; overall Step 2
remains **PARTIAL/NO-GO** and E18 remains **Active/PARTIAL**.

The next corrections are prioritized, not implemented by this acceptance run:

1. Diagnose the malformed independent public-editorial semantic-review output
   and its bounded recovery result while preserving fail-closed behavior.
2. Re-run the single-report acceptance only after that demonstrated reliability
   defect is corrected, then independently audit the actual final HTML against
   the source PDF.
3. Investigate the weak chart-card lineage and current seven-versus-five
   selection difference separately; this run does not establish that either is
   an implementation regression.

No canonical claim promotion, publication-readiness override, WordPress write,
or Step 3 implementation occurred.

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

**Final Step 1 coverage correction and fresh Adjust replay — 2026-10-25
(`3eb0eadc`):** The selector now uses original-finding theme relationships,
not fallback-filled source order, and the shared final validator protects
supported central themes. The selection cache identity is
`evidence_backed_shortlisting:15`. Focused and affected tests passed 355;
formatting, Ruff, mypy, architecture imports, and generated-documentation
checks passed. The exact deterministic and live evidence ledger is in the
[candidate-recovery supplement](verified-claims-step2-p1-candidate-recovery-20261025.md).

One fresh isolated Adjust run completed without publication or canonical
mutation. It made 51 provider calls, used 645,698 input and 103,218 output
tokens, cost `$0.135208`, and took 782.212 seconds. The candidate model
returned an empty roster after three structured-output attempts, with recovery
exhausted; the existing evidence-backed fallback supplied and retained seven
opportunities. This is recorded as fallback recovery, not model selection
success. Five of seven admitted candidates survived visual admission (two
quarantined), and five final claims were selected. Validation and
publication-readiness passed. Direct review of full PDF pages 6, 9, 19, and
27 confirmed the five final claims' values, periods, populations, qualifiers,
and provenance; no unsupported retained claim was found.

The run supported two of seven post-admission planned themes and lost five
optional themes, but lost no central theme; final selection retained all
supported central coverage. Against the latest corrected Step 1 baseline
(56 calls, 545,144 input, 113,908 output, `$0.125492`, 924.187 seconds,
8 model candidates, 7 admitted, 5 final), the run had -5 calls, +100,554
input tokens, -10,690 output tokens, +`$0.009716`, and -141.975 seconds.
These differences are stochastic and are not attributed to the selector. The
current compact result does not retain a separate cached-token breakdown.

**Current status:** PASS for the deterministic coverage/fallback/final-
selection correction and source-faithful retained output; **PARTIAL/NO-GO**
for live selection effectiveness and Step 2 promotion. Step 3 remains
unstarted/not ready.

**Candidate evidence-ID and multi-fact follow-up — 2026-10-26
(`c45dbfed` / `1c7164f2`):** The candidate prompt now receives the complete
eligible factual evidence-ID vocabulary, and the candidate boundary rejects
DocMap, `source:page:*`, unsupported, unknown, and ambiguous primary or
secondary IDs. The existing verified grounding path passed the linked
multi-fact regression with complete metrics and provenance and failed closed
for a missing secondary fact; no extra validator or LLM stage was added.

The one fresh isolated Adjust run (exact frozen PDF SHA
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`) recorded
53 provider calls, 619,294 input tokens, 138,957 output tokens, `$0.147772`,
and 879.368 seconds. The model produced seven candidates and the existing
fallback supplied one supplement, yielding six selected candidates and six
visual facts admitted. The run failed later at
`regeneration_evidence_rebind_unresolved` because the authoritative
`verified_facts` source-pack spans had physical pages but the targeted rebind
boundary only recognized `findings`/`quote_candidates`. That failure was
fail-closed; no unsupported claim or publication was promoted.

`1c7164f2` extends the existing page-bound and canonical span checks to
physical-page `verified_facts` spans and adds full rebind coverage while
preserving DocMap rejection. The provider run was not repeated after this
correction, so it is not a post-fix live-quality claim. Focused affected tests
passed 613, changed-file Ruff F/format checks passed, and targeted mypy
passed. Full ledger, candidate audit, final wording, and artifact paths are
in the [candidate-recovery supplement](verified-claims-step2-p1-candidate-recovery-20261025.md).

**Status:** PASS for deterministic candidate evidence authority, secondary-ID
fail-closed behavior, multi-fact preservation, and verified-fact physical-page
rebinding; **PARTIAL/NO-GO** for fresh post-fix live editorial acceptance.
E18 remains Active/PARTIAL and Step 3 remains unstarted/not ready.

#### P0-P2 root-cause verification and c8 Adjust replay — 2026-10-26 (`c8a09eaf`)

The targeted regeneration fix corrected a demonstrated package-boundary defect:
`alternative_evidence` repairs previously excluded all issue evidence IDs,
including valid current evidence attached to non-quarantined `artifact_quality`
warnings. The package now excludes only explicitly quarantined IDs and uses an
alternative only when a quarantined binding exists. The focused regression and
the affected suite passed 220 tests. No ranking, fallback, prompt, schema,
visual-admission, or publication policy changed.

One fresh isolated Adjust replay from c8 used the hash-matched retained PDF
and made 44 calls, 348,173 input tokens, 60,562 output tokens, estimated cost
`$0.090001`, and 726.949 seconds. It evaluated six visual candidates, admitted
four, quarantined two, and ended at pre-validation with typed
`report_payload_incomplete`; no HTML, readiness, canonical, publication, or
WordPress write occurred. The page-11 31% platform-satisfaction statement was
visually verified but failed the corrected-binding consistency boundary. The
gaming-CPI candidate was unresolved after two bounded corrections because the
inspected page contains session metrics rather than CPI. Four non-central
theme opportunities remained supported and selected; the lost platform theme
was not promoted without a safe binding.

Hosted CI run [40310685397](https://github.com/mbrakker/marketlense/actions/runs/40310685397)
passed all jobs. This run does not establish a successful post-fix editorial
or readiness outcome, and no live selection improvement is claimed. The
detailed ledger, full-page source review, artifact paths, and failure reasons
are recorded in [the P1 supplement](verified-claims-step2-p1-candidate-recovery-20261025.md).

**Verdict:** **PASS** for the targeted deterministic regeneration correction
and fail-closed source admission; **PARTIAL/NO-GO** for the required complete
Adjust E2E and Step 3 readiness. E18 remains Active/PARTIAL and Step 3 remains
unstarted/not ready.

#### Root-cause remediation and independently reviewed Adjust acceptance — 2026-10-26 (`8fe13300`)

This correction closes the three demonstrated upstream defects without lowering
the report-payload or final-insight thresholds:

1. The c8 `report_payload_incomplete` terminal state was downstream of two
   admission losses, not an insufficient-threshold problem. The prior run had
   four admitted visual candidates, so the existing payload producer could not
   satisfy its required five insights. The visual-admission boundary now binds
   candidates through the existing direct finding evidence before rendering;
   stale model-supplied page metadata is discovery input, not source authority.
   The final run produced five final insights and passed the unchanged payload,
   grounding, editorial-quality and publication-readiness gates.
2. The page-11 `marketers-platform-data-satisfaction` case was previously
   rejected because a sparse corrected metric was compared as if it were a
   complete authoritative metric. Retained non-empty candidate dimensions are
   still constraints, but source-authoritative enrichment of omitted dimensions
   is now accepted. Material cohort, forecast, observation, value and other
   protected-field conflicts remain rejected. The fresh run admitted all six
   eligible facts; no conflicting binding was promoted.
3. The `gaming-cpi-2025`/page-20 diagnostic was a source-location defect. The
   authoritative finding for the gaming strategy fact is physical page 21; the
   candidate was previously rendered from page 20, whose content is not CPI.
   Existing finding-span binding now runs before visual evaluation, so the
   rendered request used the zero-based page index 20 for physical page 21.
   The page-20 CPI candidate is no longer promoted by topic or nearby heading.
4. Multi-fact artifact validation now requires a validated physical span for
   every cited verified fact and checks the reported page set against those
   per-fact spans. Valid multi-page comparisons remain accepted; a page union
   cannot authorize a missing or swapped fact location.

Focused regressions cover source-page rebinding, sparse source-consistent
metrics, conflicting cohorts/forecast statuses, per-fact multi-page spans and
the visual admission boundary. The focused set passed `86`; the expanded
verified-claims/artifact-binding/normalization set passed `317`, with one skip
and one deselection. Ruff was clean on changed production and test files, and
targeted mypy passed for `verified_claims_canary.py` and `verified_facts.py`.

One fresh isolated provider-backed Adjust run was then executed from clean code
commit `8fe133005b62e27b6681d88c3d8dd2d61a9777a0`, using the frozen PDF with
SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` and
source identity
`source:8cb648b6bbd9dbae4ec1d915c38cf235|pdf-sha256:ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.

The exact recorded run identity and metrics are:

| Measure | Result |
| --- | ---: |
| Reports / terminal outcome | 1 / admitted, awaiting review |
| Visual facts evaluated / admitted / quarantined | 6 / 6 / 0 |
| Final insights | 5 |
| Provider calls | 52 |
| Input / output tokens | 512,814 / 116,754 |
| Reasoning tokens | 52,648 |
| Provider cached-input tokens | 10,830 |
| Estimated cost | `$0.123682` |
| Wall-clock / core processing | 946.248s / 939.0s |
| File-search calls | 6 |
| Structured-output recovery / automatic repairs | 1 / 0 |
| Workflow attempts / retries | 1 / 0 |
| Validation / publication readiness | pass / pass |
| Publication or WordPress write | none |

The provider usage database supplies the 52-call token, cache and reasoning
totals; the cohort result supplies the report-scoped cost and duration. No
additional baseline run was made. Against the failed c8 replay (44 calls,
348,173 input, 60,562 output, `$0.090001`, 726.949s, four admitted and two
quarantined), the successful run used +8 calls, +164,641 input tokens,
+56,192 output tokens, +$0.033681 and +219.299s. These are observed
cross-run differences, not an attribution of all variance to the fix.

Independent full-page PDF review found the following final claims factually
supported and commercially usable:

| Stable insight | Physical page | Review result |
| --- | ---: | --- |
| `advanced-genai-efficiency-gains` — small advanced-deployment group reportedly achieved efficiency gains over 20% | 9 | supported; the report qualifies the result as reported and deployment-specific |
| `gaming-strategy-growth-gap` — installs -1%, sessions +57% YoY | 19 | supported; chart labels and population/timeframe agree |
| `gaming-casino-slots-divergence` — Casino +22% / -5% sessions and Slots +46% / -5% sessions | 19 | supported; category/value bindings agree |
| `ecommerce-installs-sessions-diverge` — installs -10%, sessions +5% in 2025 | 27 | supported; global population and YoY relationship agree |
| `ecommerce-subvertical-cpi-divergence` — global CPI `$1.00` to `$0.98` | 29 | supported; the rendered page contains the global and subvertical CPI relationships |

The sixth admitted fact, `finance-regional-paid-organic-ratios`, is also
supported by the full page-38 chart and prose. It was not selected into the
five-item final editorial set: the selection audit records four supported
planned themes, three selected themes, zero omitted central themes and one
non-central finance opportunity omitted. This is an editorial coverage
limitation, not a factual admission error, and no weak duplicate was forced
into the final set. The quotes family abstained with the existing
`quotes_missing` reason; this did not fail readiness. The final HTML readiness
check passed the public-identifier leak rule and no internal evidence IDs were
found in public claim text.

The retained-claim artifact contains 32 entries: 27 supported semantic
factual entries and five unresolved descriptive soft-copy recommendations.
The latter are intentionally not material factual claims; the authoritative
readiness record reports `unsupported_factual_count=0` and
`unresolved_factual_count=0`. The run also recorded no automatic repair and no
operator intervention. No demonstrated canonical editorial-plan or summary
repair-authority defect remained after this run, so no speculative P2 change
was made.

**Verdict:** **PASS** for the requested root-cause corrections, source-bound
admission, and one independently reviewed Adjust E2E. **PARTIAL** for broader
live selection effectiveness: only the required single report was run, the
non-central finance opportunity was omitted, and the ten-report cohort was
intentionally not rerun. E18 remains Active/PARTIAL; broader Step 2 stability
and Step 3 promotion remain unproven and Step 3 was not started.

#### P1 data-flow integrity and semantic-authority correction — 2026-10-26 (`8da464f9`)

This slice closes the demonstrated verified-facts data-flow loss without
adding another factual validator, LLM stage, metric taxonomy, or prompt
authority. The existing GPT-6 Luna visual-verification result remains the
semantic authority for whether a claim is factually correct, whether a metric
correction is source-supported, and whether a sparse enrichment is meaningful.
Deterministic code continues to enforce PDF/source identity, physical-page
lineage, evidence IDs and spans, schema completeness, and the retained-fact
binding contract.

The confirmed producer-to-consumer mismatch was:

| Producer | Consumer / expected contract | Observed mismatch | Root cause and minimal fix | Evidence |
| --- | --- | --- | --- | --- |
| Visual verifier's `verified_fact.metric` | `verified_claims_visual_generator` should pass the authoritative metric, including report-specific qualifiers, nested observations, methodology and composite structure | The normalizer rebuilt a fixed protected-field dictionary, dropping unfamiliar fields before the fact was persisted and consumed downstream | Preserve the complete metric mapping by deep copy; retain only existing contract defaults/validation for required protected fields | `test_verified_fact_preserves_report_specific_metric_structure`; 370-test focused suite; fresh Adjust run |
| Visual verifier's complete fact and source-backed correction | `verified_claims_canary` retained-fact admission should trust the existing LLM semantic result, then enforce immutable source/lineage and corrected-binding contracts | `_retained_metric_is_source_consistent` applied a second deterministic semantic comparison and rejected source-authoritative sparse enrichment or valid LLM-authorized metric changes | Remove the redundant semantic comparison; retain exact proposition/evidence/span/metric checks for `retained` bindings and strict independent-binding checks | Authority-admission regressions; sparse-metric, cohort/forecast and page-binding regressions; 370-test suite |
| Verified-fact projections and editorial planning | Editorial remapping must use canonical `verified-fact:<id>` bindings; discovery/DocMap identifiers are aliases/navigation only | No new defect was reproduced in the current retained artifacts; ambiguous aliases continue to fail closed and one-to-many fact links remain explicit | No speculative production change; existing `remap_editorial_plan_to_verified_facts` and coverage diagnostics were retained | Editorial-plan, artifact-binding, normalization and live selection tests |
| Canonical verified-fact spans | Rebinding, multi-fact validation and HTML must require per-fact authoritative spans and preserve valid multi-page unions | No new loss or artifact-authority promotion was reproduced after the earlier physical-page rebind correction | No additional change; existing `verified_facts` span validators and source-pack distinction remain authoritative | Multi-fact, page-binding, regeneration and artifact-evidence tests |
| Artifact-derived fallback spans | `source_pack="artifact"` may support artifact diagnostics but must not become verified-facts source authority | No current verified-mode path promoted an artifact fallback over a canonical verified-fact binding | No change; the existing verified-facts source pack and fail-closed lineage checks remain in force | Artifact evidence-binding and source-fidelity regressions |

The code change is intentionally narrow. `verified_claims_canary.py` no longer
uses the removed `_retained_metric_is_source_consistent` semantic gate. It still
rejects changed retained propositions, mismatched retained evidence IDs or
spans, unsupported candidate pages, and incomplete or contradictory independent
bindings. `verified_claims_visual_generator.py` now forwards every metric field
returned in the canonical verified fact, including unknown nested fields; it
does not fill missing values or infer fields. Existing observation, qualifier,
page, source-identity and schema checks remain unchanged.

Focused adversarial coverage includes numeric swaps, distinct valid
populations, percentage versus percentage-point meaning, revenue versus
profit, ROAS versus ROI, observed versus forecast status, period/geography and
denominator changes, paraphrase/enrichment, supported correction, and
post-verification mutation. The changed tests prove that a valid LLM-authorized
metric correction is preserved, while a retained binding or independently
bound correction with contradictory protected/source fields still fails closed.
The new structure regression uses unfamiliar nested metric fields and confirms
that they survive the real visual-generator path.

##### Fresh isolated Adjust verification

The exact frozen source was used without publication or WordPress writes:

```text
PDF SHA-256: ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3
Source identity: source:8cb648b6bbd9dbae4ec1d915c38cf235|pdf-sha256:ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3
Code: 8da464f95c32bb7052d821534a9bc924c496be3d
Run root: C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9
Member: C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-uduti_em
```

| Measure | Accepted Adjust run (`8fe13300`) | Fresh P1 run (`8da464f9`) | Difference |
| --- | ---: | ---: | ---: |
| Visual facts evaluated / admitted / quarantined | 6 / 6 / 0 | 6 / 6 / 0 | unchanged |
| Verified facts | 6 | 6 | unchanged |
| Final insights | 5 | 6 | +1; stochastic selection, not an attributed quality gain |
| Provider calls | 52 | 52 | 0 |
| Input tokens | 512,814 | 537,915 | +25,101 (+4.89%) |
| Output tokens | 116,754 | 113,884 | -2,870 (-2.46%) |
| Estimated cost | $0.123682 | $0.127099 | +$0.003417 (+2.76%) |
| Wall-clock / core processing | 946.248s / 939.0s | 894.838s / 887.0s | -51.410s / -52.0s |
| File-search/tool calls | 6 | 7 | +1 |
| Structured-output recovery / automatic repairs | 1 / 0 | 0 / 0 | -1 / 0 |
| Workflow attempts / retries | 1 / 0 | 1 / 0 | unchanged |
| Retained unsupported / unresolved material claims | 0 / 0 | 0 / 0 | unchanged |
| Validation / publication readiness | pass / pass | pass / pass | unchanged |

The first clean-worktree attempt was blocked before provider execution because
the isolated worktree intentionally had no `.env` and therefore could not
prepare runtime dependencies; it made zero provider calls and was not counted
as an evaluation. The corrected run loaded the existing local credentials in
process and completed the same workflow. No secrets were copied into the
worktree or recorded in the ledger.

The fresh run admitted all six visual candidates and selected all six planned
themes. Its final stable IDs were
`ecommerce-install-session-divergence`, `cross-platform-data-satisfaction`,
`global-app-growth-accelerates`, `gaming-subvertical-metric-divergence`,
`latam-finance-acquisition-and-sessions`, and
`genai-maturity-efficiency-qualification`. It selected different useful
opportunities from the prior five-item run (including global growth, platform
data satisfaction and LATAM finance rather than the prior standalone CPI and
casino/slots entries). This is a stochastic editorial-selection difference;
the audit recorded six supported planned themes, zero lost central themes, and
no weak duplicate padding. It does not establish universal live selection
improvement.

Independent full-page inspection of physical pages 6, 9, 11, 19, 27 and 35
confirmed the final numerical, population, period and qualification bindings:

| Final insight | Physical page | Independent result |
| --- | ---: | --- |
| Global installs +10% and sessions +7% in 2025 versus +8% and +2% in 2024 | 6 | Chart and prose support the separate metrics and periods |
| Small advanced-deployment group reportedly achieved efficiency gains over 20% | 9 | Qualified cohort and reported status preserved; no generalization |
| Around 31% of marketers report complete platform-data satisfaction | 11 | Visible source wording and population support the claim |
| Strategy gaming sessions +57%, installs -1% YoY 2024–2025 | 19 | Chart supports category, metric and period; other subvertical values remain in the verified fact |
| Global e-commerce installs -10%, sessions +5% in 2025 | 27 | Chart and prose support the global population and separate metrics |
| LATAM finance installs +76%, sessions +57% YoY 2024–2025 | 35 | Chart legend supports region, category and separate metrics |

The final HTML contains no internal evidence IDs or stable IDs. The public
editorial-quality artifact reports `pass`, the retained-claim validator reports
zero unsupported and zero unresolved material factual claims, and the
publication-readiness artifact reports `pass`. The ordinary evidence-fidelity
artifact independently records six unsupported intermediate entries before
the retained-claim reconciliation; this is not the final readiness authority
and is retained as a diagnostic rather than hidden. Its difference is a
measurement caveat, not evidence that unsupported claims were published.

Artifacts (recorded paths; the run output is intentionally outside the
repository and is not linked as a repository Markdown target):

```text
C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\cohort_result.json
C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-uduti_em\cohort_members.json
C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-uduti_em\output\mobil-a5407b768f97\report_analysis\artifacts.json
C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-uduti_em\output\mobile-app-trends-2026-pdf.html
C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-uduti_em\output\mobil-a5407b768f97\report_analysis\evidence_fidelity.json
C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-uduti_em\output\mobil-a5407b768f97\report_analysis\retained_claim_validation.json
C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-uduti_em\output\mobil-a5407b768f97\report_analysis\publish_readiness.json
C:\ml-adjust-acceptance-frozen-20261026\tmp\p1-adjust-data-flow-20261026\frozen-reliability-hh522zd9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-uduti_em\output\mobil-a5407b768f97\report_analysis\public_editorial_quality_after.json
```

**Verdict:** **PASS** for the bounded P1 semantic-authority and complete-metric
data-flow correction, the focused regression suite, and one independently
reviewed Adjust E2E. **PARTIAL/NO-GO** for broad Step 2 live effectiveness:
only one report was rerun, normal provider variability changed the final
editorial roster, and the ten-report cohort was not started. Step 3 remains
unstarted/not ready. No claim is made that this single run proves a universal
selection improvement or that the intermediate evidence-fidelity diagnostic
is equivalent to the final retained-claim gate.

#### Final integrity verification and frozen ten-report E2E — 2026-10-26 (`db1bfe0c`)

The exact frozen ten-report manifest was executed through the existing
verified-facts architecture from a clean isolated worktree. The initial
provider-backed cohort run used code `7f728c30476c5b9de3e4d7d21086af0508bf4e32`;
the narrow diagnostic change was then committed as
`db1bfe0c313fbe1cb2b95b47aaafc304926d024c`. The diagnostic change does not
alter selection, grounding rules, schemas, retries, or publication policy. It
preserves the inner structured-output/grounding contract failure class in the
existing validation issue and structured log when a grounding batch fails.

The source PDFs were read from the retained local source root, not reacquired,
and their hashes were independently recomputed before review:

| Publisher | SHA-256 |
| --- | --- |
| DoubleVerify | `99f0cc4f7787cac52b7f89eefa7659053b3703ea100b9e0522fa500c64463d7e` |
| KPMG | `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589` |
| Reuters Institute | `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52` |
| Adjust | `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` |
| Algolia | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50` |
| Bain & Company | `07541f3433b72007010ff604a93d0c560b6c6709ffd7bb5a58fefa81908f86c7` |
| Criteo | `17cf2e92c8804e35274faf3dd416db2fe6e4a81d7aa92418ada8ba90ee77c00c` |
| Deloitte | `cb3a6420505366198c519929726ecc2749e310686541339d749361d239ba65` |
| Emplifi | `54a6726033fce9474929dec62bc85fc4dd3ada574398d043d12ec48b0eaddeb5` |
| StackAdapt | `909444f8721c9ec21d2f734bd5f0575bc147f2d5493f4960d3173003f6ceb305` |

The run was isolated, used `--verified-facts-architecture`, made no WordPress
or publication writes, and did not substitute cached final artifacts for the
workflow. Its aggregate ledger is:

| Measure | Result |
| --- | ---: |
| Reports / terminal outcomes | 10 / 10 |
| Verified-facts architecture evidence passed | 9 / 10 |
| Readiness passes / failures | 5 / 5 |
| Provider calls | 491 |
| Input / output tokens | 5,304,357 / 1,233,714 |
| Cached input / reasoning tokens | 338,208 / 469,877 |
| Estimated provider cost | `$1.264371` |
| Cohort wall-clock | 8,328.688s |
| File-search/tool calls | 59 |
| Operator interventions / publication writes | 0 / 0 |

The five readiness failures are not hidden in the aggregate: three were
grounding validation failures, one was an editorial-plan coverage failure, and
one was a publication-readiness failure. The per-report terminal ledger is:

| Report | Visual facts evaluated/admitted/quarantined | Accepted final insights / HTML | Validation / readiness | Calls | Cost / seconds | Recovery |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| DoubleVerify | 6 / 6 / 0 | 5 / yes | pass / pass | 42 | `$0.103989` / 791.387 | 0 / 0 |
| KPMG | 6 / 6 / 0 | 5 / yes | pass / pass | 49 | `$0.108982` / 818.685 | 0 / 1 structured |
| Reuters Institute | 7 / 7 / 0 | — / no | fail / fail | 50 | `$0.144265` / 1,097.571 | 3 targeted / 1 structured |
| Adjust | 6 / 6 / 0 | 5 / yes | pass / pass | 52 | `$0.117394` / 811.978 | 0 / 0 |
| Algolia | — / — / — | — / no | fail / fail | 34 | `$0.095197` / 691.481 | 0 / 0 |
| Bain & Company | 6 / 6 / 0 | 5 / yes | pass / pass | 37 | `$0.125184` / 623.531 | 0 / 0 |
| Criteo | 6 / 6 / 0 | — / no | fail / fail | 43 | `$0.107582` / 744.258 | 0 / 1 structured |
| Deloitte | 6 / 6 / 0 | — / no | pass / fail | 57 | `$0.132973` / 787.422 | 3 targeted / 3 structured |
| Emplifi | 6 / 6 / 0 | — / no | fail / fail | 70 | `$0.208152` / 1,173.199 | 3 targeted / 0 |
| StackAdapt | 6 / 6 / 0 | 5 / yes | pass / pass | 57 | `$0.120653` / 789.176 | 3 targeted / 0 |

Durations in this table come from the final cohort result, not the failed
members' partial `core_processing_duration_seconds` fields. The isolated
member records for Reuters, Criteo, Deloitte, and Emplifi persisted the early
failure duration while the runner retained the complete elapsed time. This is
a real ledger-persistence limitation and is not treated as a successful
timing measurement for those member records.

The failure causes and evidence are:

* Reuters, Criteo, and Deloitte reached canonical verified facts and the
  grounding stage. Their parse-valid provider responses failed the existing
  exact retained-claim coverage contract (`grounding_claim_check_coverage_invalid`)
  after bounded recovery. The validator requires one unambiguous check for
  every retained claim and rejects incomplete, duplicated, or ambiguous
  identities; sibling batch results are discarded on batch failure. The
  original ten-run responses are not retained, so no narrower provider-output
  defect can be asserted. The diagnostic patch now preserves this inner cause
  in `validation.json` and structured logging. No batch-splitting or semantic
  relaxation was added.
* Emplifi reached grounding but one final qualitative sentence attributed an
  unsupported “some users say” relationship to the source-supported
  “generative AI can speed shopping” finding. Three bounded targeted repairs
  did not produce a safe replacement, so the claim remained unresolved and
  publication was correctly blocked.
* Algolia failed before a canonical verified-facts artifact was materialized.
  The generic source-fidelity pack contained a supported revenue finding on
  physical page 4 (represented there by the non-authoritative `source:page:5`
  alias), but the visual admission/verified-fact set did not retain that
  binding. The
  editorial remapper therefore reported the central planned theme
  “Revenue is a stated incentive for ecommerce search investment: increasing
  revenue was cited as a critical incentive by 58% of B2C organizations, up
  9% since 2024” as unmapped and failed closed. This is an evidence-coverage
  gap, not permission to promote a generic fidelity finding or a navigation
  ID; no workaround was introduced.

The three shared grounding failures were rechecked without changing the
grounding validator or prompts. A fresh isolated Reuters+Criteo diagnostic
rerun on `db1bfe0c313fbe1cb2b95b47aaafc304926d024c` passed both reports:
45 and 41 calls, respectively; aggregate 86 calls, 865,361 input, 222,281
output, 29,295 cached-input, 100,620 reasoning tokens, `$0.225040`, and
1,744.678 seconds; zero repairs and zero publication writes. A separate
Deloitte diagnostic rerun on the same commit reproduced the grounding failure:
45 calls, 384,389 input, 114,605 output, `$0.101840`, 706.352 seconds, and
30 unresolved retained claims. Its retained validation issue now records the
inner class `grounding_claim_check_coverage_invalid`. This establishes that
the Reuters/Criteo failures are provider-output variability under an
unchanged contract, while the Deloitte failure is reproducible; the contract
must remain fail-closed until the exact rejected response shape is retained
and a minimal contract-preserving correction is demonstrated.

#### Independent editorial and PDF review

The five accepted HTML artifacts were inspected against the full original
PDF pages named by each canonical verified fact. All five contain five final
insights, pass the retained-claim and publication-readiness gates, and have no
visible internal evidence or stable IDs. The public-identifier check passed;
the only `finding-card` matches are CSS class names, not evidence identifiers.

| Report | Reviewed source pages and material checks |
| --- | --- |
| DoubleVerify | pp. 3, 9, 10; APAC/North America suitability rates, regional fraud/SIVT rates, viewability, and APAC in-app Display/Video attention values retain the Q1 2026 period, region, placement, and tag-based/open-web qualifiers. |
| KPMG | pp. 16, 24, 35; transaction-value shares retain Corporate/Private Equity categories, and qualitative AI, carve-out, and industrial-separation claims remain source-bound. |
| Adjust | pp. 9, 11, 19, 27, 29; installs versus sessions, strategy-gaming relationships, the 31% platform-satisfaction result, qualified efficiency claim, and deal-discovery CPI preserve population, period, unit, and direction. |
| Bain & Company | p. 1; 52% born-tech share, 20% tech-led share, 28% other, `$6.5T`/`$894B`, 2015–2020, and the asset-light recommendation agree with the page. |
| StackAdapt | pp. 7, 11–13, 15; 2025 platform channel shares, 3+ engagements, privacy-safe data, Salesforce 68%, and Kearney 51% preserve source attribution and cohorts. |

The accepted Adjust run in this cohort is also compared with the prior accepted
`8fe13300` baseline without rerunning that baseline:

| Measure | Prior accepted baseline | Ten-cohort Adjust member | Difference |
| --- | ---: | ---: | ---: |
| Visual facts evaluated/admitted/quarantined | 6 / 6 / 0 | 6 / 6 / 0 | unchanged |
| Final insights | 5 | 5 | unchanged |
| Provider calls | 52 | 52 | unchanged |
| Input / output tokens | 512,814 / 116,754 | 498,026 / 102,655 | −2.88% / −12.08% |
| Cached input / reasoning tokens | 10,830 / 52,648 | 13,745 / 39,672 | run variance |
| Cost | `$0.123682` | `$0.117394` | −`$0.006288` (−5.08%) |
| Wall-clock | 946.248s | 811.978s | −134.270s (−14.19%) |
| Validation / readiness | pass / pass | pass / pass | unchanged |
| Unsupported / unresolved material claims | 0 / 0 | 0 / 0 | unchanged |

The Adjust delta is an observed fresh-run difference, not an attribution of
selection or quality improvement: the model roster and provider/cache timing
are stochastic. No canonical artifact or editorial authority was mutated.

#### Artifact locations and acceptance decision

Initial ten-report run:

```text
C:\ml-ten-20261026\frozen-reliability-l_xtlovj\cohort_result.json
C:\ml-ten-20261026\frozen-reliability-l_xtlovj\members\
```

Reuters/Criteo diagnostic rerun:

```text
C:\ml-grounds-diagnostic-20261026\frozen-reliability-v2auv4ib\cohort_result.json
C:\ml-grounds-diagnostic-20261026\frozen-reliability-v2auv4ib\members\
```

Deloitte diagnostic rerun:

```text
C:\ml-grounds-diagnostic-20261026-deloitte\frozen-reliability-erflcoor\cohort_result.json
C:\ml-grounds-diagnostic-20261026-deloitte\frozen-reliability-erflcoor\members\
```

The new test covers preservation of the inner grounding contract cause. The
focused diagnostics suite passed 6 tests before this report update; the prior
full local suite passed 8,194 tests with 2 skips and 39 deselections, with two
pre-existing CPython wheelhouse failures outside this slice. Ruff, formatting,
and the repository mypy wrapper passed for the diagnostic code. No hosted CI
run has been started from the final documentation commit yet.

**Verdict:** **PARTIAL / NO-GO.** The verified-facts architecture is proven
through HTML and independent PDF review for 5/10 reports, and the remaining
reports fail closed with typed terminal outcomes. The diagnostic change makes
the shared grounding failure actionable and Deloitte reproduces the remaining
contract failure, but the ten-report acceptance gate requires all ten reports
to produce validated HTML with zero unresolved material claims. The Algolia
coverage failure, the grounding contract/recovery reliability gap, and the
member-duration persistence defect remain open. Step 3 must not begin.

#### P0/P1 E2E correction and frozen affected-five replay — 2026-10-27 (`51f45fcc`)

This slice addressed the five affected reports from the previous ten-report
replay. The changes were kept at the earliest demonstrated boundaries:

* The findings fallback previously selected only the first high-scoring
  sections. For Algolia that excluded the supported revenue-incentive finding
  on physical page 4 and left the central revenue theme unmapped. The fallback
  now ranks missing key-point coverage, keeps a bounded qualitative coverage
  slot, and retains late substantive sections. It still reuses the existing
  fidelity-approved findings and does not promote DocMap navigation IDs.
* A successfully removed visual insight could be re-added by a later
  `fill_missing` visual-authority pool application. Regeneration now records
  removed stable IDs for the current execution and does not reintroduce them.
* Emplifi's qualitative strategy section was previously excluded by the
  bounded findings retrieval target set. The coverage reservation retained the
  page-19 strategy/operating-model fact. The public-quality OCR detector also
  misclassified the source-backed mixed-case metric name `Top2Box`; its
  lowercase-only OCR fragment pattern now preserves legitimate metric names
  while the existing lowercase OCR regression remains covered.
* The final Algolia replay exposed a separate integrity defect: admission
  calculated the authority digest before the existing canonical verified-fact
  validator normalized multi-page provenance. The page order in the retained
  fact was valid, but the digest represented the pre-canonical list. Admission
  now canonicalizes the fact snapshot before constructing projections, evidence
  packs, audit data, and the digest. Invalid snapshots still fail closed.

Focused regression coverage includes fallback theme reservation and late
section eligibility, removed-insight non-reintroduction, the legitimate
`Top2Box` metric name, and canonical multi-page admission digests. The focused
verified-claims suites passed 90 tests; the current post-commit broader
affected-slice suite passed 167 tests (the preceding full affected slice at
`cb2d9bc4` passed 190), and Ruff passed on the changed files. No publication or
WordPress write was performed.

The exact affected-five replay at `cb2d9bc4071237ad7dd8b56a1990e499e33f19dc`
used the frozen source PDFs, isolated member state, and no cached final
artifacts. It produced four complete passes and one integrity failure before
the final digest correction:

| Report | Visual facts | Final HTML | Validation / readiness | Calls | Cost / seconds | Terminal result |
| --- | ---: | --- | --- | ---: | ---: | --- |
| Reuters Institute | 7 / 7 / 0 | yes | pass / pass | 53 | `$0.157279` / 1,252.191 | pass |
| Criteo | 6 / 6 / 0 | yes | pass / pass | 51 | `$0.120932` / 871.648 | pass |
| Deloitte | 6 / 6 / 0 | yes | pass / pass | 40 | `$0.094506` / 723.025 | pass |
| Algolia | 6 / 6 / 0 | no | blocked before readiness | 43 | `$0.106842` / 1,009.800 | `verified_facts_snapshot_digest_mismatch` |
| Emplifi | 6 / 6 / 0 | yes | pass / pass | 59 | `$0.166700` / 889.425 | pass |
| **Aggregate** | **28 / 28 / 0** | **4 / 5** | **4 / 5** | **246** | **`$0.646259` / 4,746.089s** | **4 pass / 1 fail** |

The initial affected-five run used 2,842,047 input tokens and 614,891 output
tokens, with zero operator interventions and zero publication writes. Reuters,
Criteo, Deloitte, and Emplifi each had zero unsupported and zero unresolved
retained material claims. Emplifi required three bounded automatic repairs in
this run but ended with validation/readiness pass; Criteo had two structured
output recovery calls and Reuters one.

The Algolia failure was not a factual promotion: its artifacts contained six
source-hash-bound facts, but the external architecture check correctly rejected
the stale pre-canonical digest before HTML was accepted. The targeted rerun
after `51f45fcc02f16ecac169d65154dc28de6f98eb81` used the same frozen Algolia
report in a new isolated run and passed:

| Measure | Corrected Algolia result |
| --- | ---: |
| Visual facts evaluated / admitted / quarantined | 6 / 6 / 0 |
| Final insights / validation / readiness | 5 / pass / pass |
| Unsupported / unresolved retained material claims | 0 / 0 |
| Provider calls / input tokens / output tokens | 50 / 641,181 / 112,192 |
| Estimated cost / wall-clock | `$0.131476` / 976.093s |
| Structured recovery / automatic repairs / intervention | 0 / 0 / 0 |
| WordPress writes | 0 |

Its verified-facts architecture evidence passed with six facts and the
canonical digest
`f43ff6cd1874e054a82ec976d27726cac577a09294a1ad965d997fcf60db55f3`.
The corrected final IDs were `agentic-search-adoption-status`,
`revenue-investment-incentive`, `ai-tool-purchase-likelihood`,
`agentic-search-integration-factor`, and `third-party-search-development`.
The revenue fact is bound to physical page 4 and states the 58% 2025 versus
49% 2024 critical-incentive comparison; the page text independently supports
both values and the nine-point change. No evidence alias or navigation ID was
promoted.

#### Independent HTML/PDF review of the affected five

The four successful members of the affected-five run and the corrected Algolia
member were inspected against their original full PDFs. Every final artifact
had a matching source PDF SHA-256, and every retained final insight referenced
an admitted `verified-fact:` ID with physical pages inside the source. The
public HTML files contained no internal evidence IDs, candidate IDs, source
identities, or fact IDs. The following material checks were observed:

| Report | Independent factual/editorial checks |
| --- | --- |
| Reuters Institute | Pages 9, 12, 21, 24, 32, and 38 support the reported traffic expectation, AI-use priority, platform effort balances, creator concerns, commercial revenue selection, and 2022/2026 confidence comparison; survey bases and future-expectation qualifiers were retained. |
| Criteo | Pages 4–8 support the US strategy factors, incrementality/retail-media finding, omnichannel focus, campaign waiting-list statement, and 2023 recommendations; the final wording preserves the next-year and expectation qualifiers. |
| Deloitte | Pages 3, 5, and 6 support the 14% trust result, LLM discovery/data requirements, retailer partnerships, and 23% product-discovery observation; qualitative implications remain tied to the report rather than presented as new measured values. |
| Emplifi | Pages 4, 12, 13, 16, 18, and 19 support the $/£500 research behavior, 27% UGC snapshot, 91% disclosure expectation, service checklist, hypothetical stop-buying responses, and operational authenticity theme. |
| Algolia (corrected rerun) | Pages 4, 15, 16, 22, 26, and 27 support revenue incentives, task-effectiveness percentages, AI-tool purchase likelihood, search-solution shares, adoption plans, and integration ratings; 17% current adoption versus 61% planned adoption remains explicitly separated. |

The review found no independently confirmed unsupported material claim in the
accepted HTML. Numeric presence checks were supplemented by page-level reading;
the checks are not treated as a substitute for the retained-claim and
publication gates. The provider-backed replay demonstrates the specific
fallback, removal, OCR, and digest corrections on the affected inputs. It does
not prove universal provider-output stability or establish a new ten-report
acceptance result after the final commit, because only the failing Algolia
member was rerun at `51f45fcc`.

Artifacts:

```text
C:\ml-five-20261027-final5\frozen-reliability-4geij3zr\cohort_result.json
C:\ml-five-20261027-final5\frozen-reliability-4geij3zr\members\
C:\ml-five-20261027-algolia-fix\frozen-reliability-25vmr3s6\cohort_result.json
C:\ml-five-20261027-algolia-fix\frozen-reliability-25vmr3s6\members\cohort-86858bdcb370266f26c2\ias-first-attempt-nc4g6348\output\2026-20b2c-20ecommerce-20ai-20trends-ebook-en-2-pdf.html
C:\ml-five-20261027-algolia-fix\frozen-reliability-25vmr3s6\members\cohort-86858bdcb370266f26c2\ias-first-attempt-nc4g6348\output\2026-20b2c-20ecommerce-20ai-20trends-ebook-en-2-pdf\report_analysis\artifacts.json
```

**Verdict:** **PASS** for the demonstrated P0/P1 root-cause corrections,
focused regressions, and corrected Algolia E2E; **PARTIAL / NO-GO** for broad
Step 2 live effectiveness and Step 3 readiness. The affected-five evidence is
4/5 on the initial same-commit replay plus a corrected isolated Algolia pass;
the ten-report cohort was not rerun, and no claim is made that stochastic
provider-output or grounding-coverage behavior is universally resolved. Step 3
must not begin.

#### Targeted P1 reliability hardening and three-report live verification — 2026-10-27 (`c5439d19`)

This slice was limited to the remaining grounding-recovery, repeated-work,
split-safety, and findings-fallback risks before the ten-report E2E. Inspection
of the current implementation found that the required production safeguards
were already present at the relevant boundaries, so no new validator, model
stage, raw batch cache, or nested executor was added. The commit adds focused
provider-injected regressions for the previously under-covered subdivision
outcomes.

| Boundary | Evidence and result |
| --- | --- |
| Grounding recovery feedback | Existing structured-output recovery preserves a bounded coverage category and actionable missing/unknown/duplicate/text-mismatch IDs. The new success test drove three full-batch attempts followed by two scoped split calls and required exact final coverage; no validator relaxation was used. |
| Subdivision failure | A persistent split failure raises `grounding_claim_check_coverage_invalid`, captures the inner failure, promotes no successful sibling package, and does not continue the unrelated batch. |
| Classification safety | An invalid retained-claim classification is rejected with the affected public item ID. Malformed or incomplete responses remain fail-closed. |
| Repeated grounding work | Existing retained semantic reuse requires compatible artifact/source/evidence/prompt/policy/retrieval identities. Existing matching, mismatch, ambiguity, and incomplete-package tests passed; no persistent raw batch response cache was introduced. |
| Findings fallback | Retained artifacts show fidelity-approved findings for the target reports: Algolia 16 findings/7 conservative DocMap targets, Deloitte 17/8, and Emplifi 25/11. The conservative text-containment audit leaves broad DocMap target wording unmatched in these artifacts; that is a measured false-negative risk in the audit heuristic, not evidence that the fidelity-approved findings are absent. Existing bounded fallback and prior Algolia revenue/Emplifi strategy corrections were preserved; no fuzzy semantic-equivalence validator or quota increase was added. |
| Split latency | A provider-free delayed benchmark measured the current sequential split at 0.314s with one active split versus a 0.101s two-way parallel reference. The reference would require moving split work into the existing bounded scheduler; nested executor use could oversubscribe or deadlock. No live recovery latency problem justified that risk, so concurrency was not implemented. |

The focused affected suite passed **204 tests**. The new test module covers
subdivision success, persistent subdivision failure without sibling promotion,
and invalid retained classification. Ruff, architecture imports, forbidden
patching, contract schemas, and the full-repository mypy baseline all passed:

```text
python -m pytest -q tests/test_grounding_recovery_effectiveness.py \
  tests/test_grounding_recovery_diagnostics.py \
  tests/test_structured_output_service.py \
  tests/test_structured_output_recovery_effectiveness.py \
  tests/test_structured_output_recovery_diagnostics.py \
  tests/test_retained_claim_grounding.py \
  tests/test_verified_grounding_batch_context.py \
  tests/test_grounding_cohort_false_positive_regressions.py \
  tests/test_grounding_semantic_outcomes.py \
  tests/test_grounding_editorial_interpretation.py \
  tests/test_grounding_protected_facts.py \
  tests/test_grounding_public_identity.py \
  tests/test_candidate_recovery_and_selection_regressions.py \
  tests/test_report_analysis_validation_fallback.py \
  tests/_test_claim_validation_generator tests/_test_evidence_pack_generator
204 passed in 31.05s
python scripts/ci/check_ruff_lint.py                         PASS
python scripts/ci/check_contract_schemas.py --snapshot ...   PASS
python scripts/ci/check_architecture_imports.py              PASS
python scripts/ci/check_forbidden_patching.py                PASS
python scripts/ci/run_type_check.py                          PASS (0 baseline errors)
```

The isolated provider-backed run used the original Deloitte, Algolia, and
Emplifi PDFs, GPT-6 Luna High, verified-facts architecture, no WordPress
publication, and fresh per-report application state. The source hashes were
checked independently against the retained verified-fact identities.

| Report | Verified visual facts | Final insights | Calls | Input / output / cached / reasoning tokens | File-search calls | Cost | Duration | Structured recovery / automatic repairs | Validation / readiness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Deloitte | 6 / 6 / 0 | 5 | 66 | 551,048 / 213,181 / 98,590 / 58,506 | 3 | `$0.160324` | 1,062.250s | 4 / 3 | pass / pass |
| Algolia | 6 / 6 / 0 | 5 | 50 | 641,947 / 118,715 / 15,550 / 52,885 | 4 | `$0.132153` | 1,138.438s | 0 / 0 | pass / pass |
| Emplifi | 6 / 6 / 0 | 5 | 58 | 712,569 / 157,113 / 67,021 / 52,424 | 5 | `$0.156283` | 990.000s | 1 / 3 | pass / pass |
| **Total** | **18 / 18 / 0** | **15** | **174** | **1,905,564 / 489,009 / 181,161 / 163,815** | **12** | **`$0.448760`** | **3,190.688s** | **5 / 6** | **3 / 3** |

Candidate-generation checkpoints explain the live fallback outcome for all
three reports: each model response produced eight normalized candidates, the
existing bounded fallback supplied one eligible supplement because the
primary roster was incomplete, and six candidates were selected from the
combined pool. No location-only or invalid evidence references were removed
in these runs; all planned themes were covered (Deloitte 5/5, Algolia 5/5,
Emplifi 4/4), and each report admitted six verified candidates. Thus fallback
participated as a bounded supplement, not as an unexplained replacement of the
model roster.

The final HTML was independently inspected against the original PDF pages.
The material checks were: Deloitte pages 3, 5, and 6 retained the 14% trust
statistic, 693% traffic comparison, website infrastructure recommendation,
blanket-blocking risk, and 9x study qualifier; Algolia pages 4, 12, 22, 26,
and 27 retained the 58%/49% revenue comparison, 63% respondent belief,
49% third-party approach, 17% current adoption, 61% planned adoption, and
90% integration result; Emplifi pages 4, 10, 13, 14, and 17 retained the
$/£500 research cohort, 79%/77% review benchmark, 91% disclosure expectation,
35%/28% regional comparison, and 52%/59% service outcomes. The HTML visible
text contained zero `verified-fact:`, source-identity, or stable candidate IDs.
All three source PDFs matched the hashes recorded by the verified-facts
artifacts, and all final insight evidence IDs/pages/spans matched their
authoritative facts.

Recovery audit review found no unsafe promotion. Deloitte had three bounded
targeted repairs; its first regeneration candidate was rolled back because it
introduced a new hard grounding failure, and the later rebinding candidate
was promoted. Emplifi had three bounded repairs and promoted a source-bound
replacement that resolved the LinkedIn grounding item without changing the
final-insight evidence. Algolia required no recovery. The compact live
result is terminally complete for all three reports: admission 3/3,
publication readiness 3/3, unsupported retained material claims 0, unresolved
retained material claims 0, operator interventions 0, and WordPress writes 0.

Artifacts:

```text
C:\ml-p1-targeted-20261027\frozen-reliability-ne592nip\cohort_result.json
C:\ml-p1-targeted-20261027\frozen-reliability-ne592nip\members\cohort-b10ed6c82b76739a806a\ias-first-attempt-t22ohz7j\output\q1-2026-emerging-retail-and-consumer-trends-pdf.html
C:\ml-p1-targeted-20261027\frozen-reliability-ne592nip\members\cohort-86858bdcb370266f26c2\ias-first-attempt-b8ii5usa\output\2026-20b2c-20ecommerce-20ai-20trends-ebook-en-2-pdf.html
C:\ml-p1-targeted-20261027\frozen-reliability-ne592nip\members\cohort-f62048b469dd784e6e7c\ias-first-attempt-fsbx9hv7\output\emplifi-digital-authenticity-ai-2026-pdf.html
```

**Verdict:** **PASS** for the targeted P1 reliability hardening, focused
regressions, and the three-report Deloitte/Algolia/Emplifi verified-mode E2E.
**PARTIAL / NO-GO** for ten-report acceptance and Step 3 readiness: the
ten-report cohort was intentionally not run, and this evidence does not prove
universal provider-output stability or live recovery behavior outside the
three exercised reports. No canonical artifacts or publication state were
mutated.

#### Full frozen ten-report E2E acceptance — 2026-10-27 (`872cc67e` producer)

The exact frozen ten-report manifest was run once from the clean isolated
worktree at producer SHA `872cc67e1a2667aa48d1999933c0ddcb4f99759e`. The run
used the existing production-equivalent verified-facts path, GPT-6 Luna High,
fresh per-report application state, and the original local PDFs. It did not
use `--enable-wordpress-staging`, `--shared-batch`, or any publication flag.
The runner completed all ten report records; no report was selectively rerun
or manually repaired after a terminal outcome.

Run identity and preflight evidence:

```text
Manifest: C:\ml-step1-p1-hardening-20261027\scripts\quality\frozen_reliability_cohort_10.json
Preflight: C:\ml-ten-acceptance-20261027\frozen-reliability-preflight-6z6bekfn\cohort_preflight.json
Live root: C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\
Cohort result: C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\cohort_result.json
Members: C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\members\
```

All ten manifest entries were rehashed before the run and matched the frozen
roster. The live architecture evidence repeated the same hash for the nine
reports that reached verified-fact admission; Emplifi failed before that
artifact was readable.

| Publisher | Frozen PDF SHA-256 |
| --- | --- |
| DoubleVerify | `99f0cc4f7787cac52b7f89eefa7659053b3703ea100b9e0522fa500c64463d7e` |
| KPMG | `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589` |
| Reuters Institute | `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52` |
| Adjust | `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` |
| Algolia | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50` |
| Bain & Company | `07541f3433b72007010ff604a93d0c560b6c6709ffd7bb5a58fefa81908f86c7` |
| Criteo | `17cf2e92c8804e35274faf3dd416db2fe6e4a81d7aa92418ada8ba90ee77c00c` |
| Deloitte | `cb3a6420505366198c519929726ecc2749e310686541339d749361d239ba65` |
| Emplifi | `54a6726033fce9474929dec62bc85fc4dd3ada574398d043d12ec48b0eaddeb5` |
| StackAdapt Inc. | `909444f8721c9ec21d2f734bd5f0575bc147f2d5493f4960d3173003f6ceb305` |

The authoritative runner totals are:

| Measure | Result |
| --- | ---: |
| Reports / terminal outcomes | 10 / 10 |
| Workflow admission outcomes | 10 / 10 admitted |
| Visual facts evaluated / admitted / quarantined | 56 / 56 / 0 across the nine readable verified-fact artifacts |
| Verified-facts architecture evidence passed | 9 / 10 |
| Rendered HTML files / readiness passes | 8 / 10 / 6 / 10 |
| Validation passes / failures | 8 / 10 / 2 / 10 |
| Provider calls | 478 |
| Input / output tokens | 5,174,726 / 1,122,734 |
| Cached input / reasoning tokens | 164,009 / 457,419 |
| Estimated provider cost | `$1.209086` |
| Cohort wall-clock | 8,320.406s |
| File-search calls | 58 |
| Structured-output recovery / automatic repairs | 10 / 3 |
| Workflow retries / operator interventions / WordPress writes | 0 / 0 / 0 |

Cached and reasoning totals were independently summed from each isolated
member's `llm_usage_events` records. Provider-side cache usage is reflected in
the ledger; no application-level final artifact was supplied to the run.
All ten members recorded `isolated_fresh_state=true`. The aggregate runner
field `verified_facts_architecture_outcome` is unset, so the 9/10 architecture
figure above is the explicit per-member evidence result, not an inferred
aggregate pass.

Per-report terminal ledger:

| Report | Visual facts eval/admit/quarantine | Artifact insights / HTML | Validation / readiness | Calls | Input / output / cached / reasoning | Cost / seconds | Structured / automatic | Terminal result |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| DoubleVerify | 6 / 6 / 0 | 5 / yes | pass / pass | 44 | 439,457 / 123,972 / 10,830 / 44,907 | `$0.114957` / 815.750 | 1 / 0 | awaiting review |
| KPMG | 6 / 6 / 0 | 5 / no | fail / fail | 62 | 461,983 / 121,582 / 15,550 / 49,806 | `$0.138095` / 881.437 | 2 / 0 | `summary_safe_removal_no_supported_replacement` |
| Reuters Institute | 7 / 7 / 0 | 6 / rendered, rejected | pass / fail | 44 | 534,215 / 131,623 / 10,135 / 67,895 | `$0.140823` / 1,033.969 | 1 / 0 | `card_tldr_compact_invalid` |
| Adjust | 6 / 6 / 0 | 6 / yes | pass / pass | 50 | 519,934 / 111,362 / 13,745 / 43,110 | `$0.121433` / 914.812 | 0 / 0 | awaiting review |
| Algolia | 6 / 6 / 0 | 5 / rendered, rejected | pass / fail | 56 | 723,173 / 145,589 / 13,745 / 66,268 | `$0.156371` / 1,255.953 | 3 / 0 | `card_tldr_compact_invalid` |
| Bain & Company | 6 / 6 / 0 | 5 / yes | pass / pass | 48 | 747,140 / 130,486 / 52,244 / 40,886 | `$0.150257` / 719.266 | 0 / 3 | awaiting review |
| Criteo | 6 / 6 / 0 | 5 / yes | pass / pass | 41 | 357,587 / 97,900 / 15,550 / 39,945 | `$0.090814` / 671.141 | 0 / 0 | awaiting review |
| Deloitte | 6 / 6 / 0 | 5 / yes | pass / pass | 45 | 397,534 / 113,026 / 17,355 / 39,335 | `$0.102205` / 752.703 | 2 / 0 | awaiting review |
| Emplifi | no artifact | 0 / no | fail / fail | 34 | 489,762 / 38,296 / 1,110 / 22,391 | `$0.080525` / 496.812 | 0 / 0 | `verified_fact_editorial_coverage_insufficient` |
| StackAdapt Inc. | 7 / 7 / 0 | 7 / yes | pass / pass | 54 | 503,941 / 108,898 / 13,745 / 42,876 | `$0.113606` / 778.563 | 1 / 0 | awaiting review |

Here “rendered, rejected” means an HTML file exists but the publication
readiness contract failed; it is not an accepted HTML outcome. KPMG's
artifact insight count is retained analysis state, not a public output.

#### Failure and recovery review

The runner's mutually exclusive terminal outcomes are six complete
`awaiting_review` passes and four typed failures:

* KPMG admitted six visual facts and produced retained artifacts, but the
  final summary repair path ended with
  `summary_safe_removal_no_supported_replacement`. Its `validation.json`
  also records `grounding_claim_check_coverage_invalid`; the final package had
  24 unresolved retained claims and no accepted HTML. This is a fail-closed
  summary/grounding contract failure, not an evidence promotion.
* Reuters and Algolia both rendered HTML and passed retained validation, but
  both ended with `card_tldr_compact_invalid`. Their readiness ledgers fail
  `publish_readiness.report_card_manifest` (`report card manifest missing`),
  and their retained artifact summaries have empty `card_tldr_compact` values.
  Their HTML is therefore rejected, even though the independent source review
  below found the retained numerical claims source-supported.
* Emplifi ended with `verified_fact_editorial_coverage_insufficient`. Its
  selection checkpoint contains nine input candidates but blank insight
  placeholders and an empty evidence-pack map; no canonical verified-fact
  artifact was readable (`FileNotFoundError`), so neither model output nor a
  fidelity-approved fallback supplied an authoritative final roster. No HTML
  was emitted.

The ten structured-output recovery calls and three automatic repairs were
bounded by the existing workflow. There were no workflow retries, operator
interventions, publication writes, or unsafe evidence promotions. No failure
was repaired and rerun during this acceptance run.

#### Independent PDF/HTML review

Eight HTML files were inspected against the original full PDF pages; all eight
had zero visible `verified-fact:`, source-identity, candidate, or claim IDs.
The six readiness-passing outputs were independently checked as follows:

| Report | Source-page review and editorial result |
| --- | --- |
| DoubleVerify | Pages 3, 9, and 10 support the four-region suitability/viewability ranges, the 100-point/28-day Attention Index definition, and the APAC Display/Video and EMEA engagement index values. Qualitative implications remain framed as recommendations. |
| Adjust | Pages 6, 9, 11, 19, 29, and 34–35 support the install/session, maturity, gaming, cross-platform, finance, and CPI statements. A material internal binding defect remains: the `ecommerce-cpi-subvertical-divergence` public sentence correctly states deal-discovery CPI `$1.44` to `$2.26`, but its retained `metric.value` is the different aggregate e-commerce CPI `$1.00` to `$0.98`. The source page supports both figures, but they are not the same proposition. |
| Bain & Company | Page 1 supports the 52% born-tech, 20% tech-led, 28% other mix, 2015–2020 period, and asset-light recommendation. |
| Criteo | Pages 5, 7, and 8 support the country exploration percentages, 50% incrementality/retail-media statement, 2023 cost estimate, omnichannel priority, and recommendation percentages. |
| Deloitte | Pages 3–6 support the 14% trust statistic, 693% traffic comparison, first-party assistant interpretation, LLM discovery use, and blanket-blocking implication. |
| StackAdapt Inc. | Pages 5, 7, 10, 13–15, and 19 support channel shares, social discovery, data relevance, personalization/daily AI use, values alignment, and programmatic implications. |

Reuters's rejected HTML was additionally checked on pages 9, 12, 17, 24,
32, and 41; the 60%/38%, 33%/38%, +91/+82, 70%/39%, 64%, and 15%/60%/75%
claims match the source. Algolia's rejected HTML was checked on pages 4, 16,
22, 26, and 27; the 58%/49%, 63%, 49%/27%/23%, 17%/61%, and 47%/43%/90%
claims match the source, including the current-versus-planned distinction.
Those findings do not override their readiness failures. KPMG and Emplifi had
no accepted public HTML to review.

The Adjust metric/text disagreement is the only independently confirmed
material factual-integrity defect in the rendered outputs reviewed here. It
does not make the public deal-discovery sentence unsupported, but it violates
the requirement that the authoritative protected metric binding and editorial
proposition remain the same. It must remain open; no speculative correction
was made during this run.

#### Comparison with the previous frozen ten-report baseline

The previous retained baseline is the `db1bfe0c` ledger above. The current
observed deltas are:

| Measure | Previous | Current | Difference |
| --- | ---: | ---: | ---: |
| Readiness passes | 5 / 10 | 6 / 10 | +1 report |
| Architecture evidence passed | 9 / 10 | 9 / 10 | unchanged |
| Provider calls | 491 | 478 | −13 (−2.65%) |
| Input tokens | 5,304,357 | 5,174,726 | −129,631 (−2.44%) |
| Output tokens | 1,233,714 | 1,122,734 | −110,980 (−8.99%) |
| Cached input tokens | 338,208 | 164,009 | −174,199 (−51.51%) |
| Reasoning tokens | 469,877 | 457,419 | −12,458 (−2.65%) |
| Estimated cost | `$1.264371` | `$1.209086` | −`$0.055285` (−4.37%) |
| Wall-clock | 8,328.688s | 8,320.406s | −8.282s (−0.10%) |
| File-search calls | 59 | 58 | −1 |

The readiness improvement and cost/timing deltas are observed run differences,
not a causal quality claim: provider output, repair paths, and report failure
composition changed. The current run still has only 6/10 accepted HTML, a
9/10 architecture result, and the Adjust binding inconsistency, so it does
not satisfy the ten-report acceptance gate.

Artifacts for the complete run are retained here:

```text
C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\cohort_result.json
C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\members\
C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\members\cohort-e854b71d6fb10333b47f\ias-first-attempt-jc7rj8z5\output\dv-qualityandattentionbenchmark-q1-2026-pdf.html
C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-1q79hhjj\output\mobile-app-trends-2026-pdf.html
C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\members\cohort-77bc67b2bc98187d9d58\ias-first-attempt-hl4dth99\output\tech-tonic-shifts-pdf.html
C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\members\cohort-979a63a1633a7f2ccc51\ias-first-attempt-zxscomr0\output\agency-guide-report-criteo-pdf.html
C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\members\cohort-b10ed6c82b76739a806a\ias-first-attempt-h5ugzfm0\output\q1-2026-emerging-retail-and-consumer-trends-pdf.html
C:\ml-ten-e2e-20261027\frozen-reliability-9xhis2bv\members\cohort-8ef1021c332aa85ba008\ias-first-attempt-vf5iqvo6\output\stackadapt-retail-marketing-trends-report-2026-pdf.html
```

**Verdict: PARTIAL / NO-GO.** The exact ten-report workflow is terminally
complete and provider/audit evidence is retained, but the acceptance gate is
not met: 6/10 readiness passes, 8/10 rendered HTML files, 9/10 verified-fact
architecture evidence, four typed failures, and one independently confirmed
Adjust protected-metric binding conflict. Step 3 must not begin. No code fix
or selective rerun is authorized by this ledger entry.

#### Affected-five P0/P1 remediation and replay — 2026-10-28 (`651609e8` producer)

This entry records the next affected-five verification requested after the
ten-report run. It uses the exact frozen KPMG, Reuters Institute, Adjust,
Algolia, and Emplifi PDFs, GPT-6 Luna High, fresh per-report application state,
and no publication flags. The source PDFs were independently SHA-256 checked:

| Report | SHA-256 | Material source pages reviewed |
| --- | --- | --- |
| KPMG | `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589` | 7, 13, 15, 24 |
| Reuters Institute | `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52` | 12, 14, 17, 20, 24, 32 |
| Adjust | `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` | 9, 11, 19, 21, 29, 35 |
| Algolia | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50` | 12, 16, 18, 22, 24, 27 |
| Emplifi | `54a6726033fce9474929dec62bc85fc4dd3ada574398d043d12ec48b0eaddeb5` | 4, 10, 13, 15, 17, 19 |

The single affected-five live replay was terminally complete, but not all five
reports passed readiness. Its authoritative aggregate is:

| Reports | Calls | Input / output tokens | Cost | Wall-clock | Validation / readiness |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 5 / 5 terminal, 5 / 5 admitted | 171 | 1,965,697 / 352,346 | `$0.449937` | 3,157.908s | 4 / 5 validation, 3 / 5 readiness |

There were three bounded automatic repairs, no operator intervention, no
WordPress writes, and no canonical publication mutation. The two focused
reruns below were separate terminal runs and are not added to the cohort
aggregate or counted as a second success for the same report.

| Report | Affected-five terminal result | Focused same-SHA result |
| --- | --- | --- |
| KPMG | `report_payload_incomplete`; 3 final insights could not satisfy the existing five-slot report-payload contract; 35 calls, `$0.057924`, 340.606s | **Pass** after an isolated rerun: 5 final insights, 40 calls, 317,333 input / 70,491 output, `$0.110980`, 537.425s, validation/readiness pass, zero unsupported or unresolved retained claims |
| Reuters Institute | Validation passed but readiness failed on source fidelity; 31 calls, `$0.106274`, 735.290s | Workflow **pass** before the render-only correction: 6 final insights, 40 calls, 632,345 input / 118,018 output, `$0.134759`, 957.391s, three bounded repairs, validation/readiness pass, zero unsupported or unresolved retained claims |
| Adjust | 6 final insights, 34 calls, `$0.101130`, 755.726s, validation/readiness pass, zero unsupported or unresolved retained claims | Not selectively rerun |
| Algolia | 5 final insights, 38 calls, `$0.090062`, 804.045s, validation/readiness pass, zero unsupported or unresolved retained claims | Not selectively rerun |
| Emplifi | 6 final insights, 33 calls, `$0.094547`, 522.241s, validation/readiness pass, zero unsupported or unresolved retained claims | Not selectively rerun |

The two live failures were traced to different causes:

1. The KPMG model response generated only three final insights. The existing
   `report_payload_incomplete` gate correctly rejected padded blanks; the
   existing artifact-family minimum remains two, but the legacy report payload
   contract requires five non-empty insights. The focused rerun produced five
   valid qualitative insights without changing the gate. This is provider
   variability, not evidence promotion, and the KPMG rerun had no metric spine
   entries; its five retained insights are therefore useful but numerically
   sparse.
2. Reuters produced a DocMap Executive Summary key point that said referral
   declines occurred over the “previous three years.” The original PDF states
   the Facebook and X declines occurred over the last two and a half years on
   the printed page 18 / retained physical source page 20. The source-backed
   Section 4 copy was correct, but the public renderer also exposed the
   `toc_only` Executive Summary navigation prose in the Coverage and Signals
   surfaces. The existing readiness result did not reject that navigation
   surface in the focused pass.

The minimal correction is at the existing render boundary in
`src/services/_render_service/normalization.py`: a topic explicitly marked
`status: toc_only` keeps its title and page label but cannot contribute factual
summary or key-point prose to public HTML. `source_backed` topic copy is
unchanged. This is not a new validator or LLM stage. A focused regression
reproduces the Reuters wording and proves it is absent from HTML while the
source-backed path remains present.

The semantic reliability correction in producer `651609e8` is also covered by
the live reruns and focused tests: an incomplete semantic verdict roster now
enters the existing bounded structured-output recovery path instead of being
treated as an unrelated provider failure. No verdict is materialized until
the expected IDs are complete.

#### Independent PDF and HTML review

The retained final insight texts were checked against the listed PDF pages.
Adjust retained the gaming session/installation relationship on page 19, day
30 retention on page 21, the aggregate and subvertical CPI distinction on
page 29, and the LATAM/APAC finance comparison on page 35. Algolia retained
the 68% US versus 57% Australia/New Zealand purchase-likelihood distinction,
91% image-search preference, 49%/27%/23% search-development split, and
47%/39%/37% agentic-adoption factors. Emplifi retained the $/£500 research
cohort, 85% willingness-to-pay result, 91% AI-disclosure expectation, 84%
response-time result, and 59% repeat-purchase result. KPMG's rerun retained
source-grounded qualitative claims from pages 7, 13, 15, and 24. Reuters'
rerun retained the 43% search-traffic expectation, +91 original-reporting
priority, +74 YouTube / +61 AI-platform effort differences, 70%/39% creator
concerns, 64% back-end-automation importance, and 69% licensing-income
expectation.

The original live HTML from the Reuters focused rerun exposed the incorrect
DocMap sentence, so it is not accepted as independently clean despite its
readiness PASS. A provider-free re-render of the exact retained artifacts
after the render correction produced five HTML files with **5/5 final insight
texts present, zero internal-identifier leaks, zero deterministic editorial
blockers, and no “previous three years” phrase**. The correct
“preceding two and a half years” Section 4 wording remained present. This is
the appropriate post-fix verification for a deterministic render-only change;
the provider-backed generation was not silently re-run or presented as a
post-fix model-quality result.

#### Regression and artifact evidence

The current deterministic checks are:

```text
python -m pytest -q \
  tests/test_grounding_recovery_effectiveness.py \
  tests/test_grounding_recovery_diagnostics.py \
  tests/test_structured_output_service.py \
  tests/test_structured_output_recovery_effectiveness.py \
  tests/test_structured_output_recovery_diagnostics.py \
  tests/test_retained_claim_grounding.py \
  tests/test_verified_grounding_batch_context.py \
  tests/test_grounding_cohort_false_positive_regressions.py \
  tests/test_grounding_semantic_outcomes.py \
  tests/test_grounding_editorial_interpretation.py \
  tests/test_grounding_protected_facts.py \
  tests/test_grounding_public_identity.py \
  tests/test_candidate_recovery_and_selection_regressions.py \
  tests/test_report_analysis_validation_fallback.py \
  tests/_test_claim_validation_generator tests/_test_evidence_pack_generator
205 passed in 17.93s

python -m pytest -q tests/test_render_service_public_prose.py \
  tests/_test_render_service_artifacts/cases_01_metadata_and_artifact_sections.py \
  tests/_test_render_service_artifacts/cases_02_render_identity_and_publication.py \
  tests/_test_validation_generator/cases_03_grounding_cache_and_reuse.py \
  tests/test_report_analysis_validation_fallback.py
103 passed in 14.96s

ruff check src/services/_render_service/normalization.py \
  tests/test_render_service_public_prose.py
PASS
python scripts/ci/run_type_check.py
PASS (786 source files, 0 tracked errors)
```

Retained artifacts:

```text
C:\ml-affected-five-e2e-live-20261028-final3\frozen-reliability-btn45j7_\cohort_result.json
C:\ml-affected-five-e2e-live-20261028-kpmg-rerun\frozen-reliability-wf9cihj0\cohort_result.json
C:\ml-affected-five-e2e-live-20261028-reuters-rerun\frozen-reliability-s36vnpi5\cohort_result.json
C:\ml-affected-five-render-recheck-20261028\
```

No ten-report cohort was started after the prior run. The affected-five live
evidence therefore demonstrates the semantic recovery correction and isolated
KPMG/Reuters behavior, while the render correction is demonstrated by exact
retained-artifact re-rendering and focused regressions. It does not establish
universal provider-output stability or fresh Step 1 candidate recall.

**Verdict: PARTIAL / NO-GO.** Deterministic P0/P1 safeguards and the
render-boundary provenance correction pass. All five reports have isolated
same-SHA pass evidence across the affected-five run plus focused reruns, but
the single five-report cohort itself reached only 3/5 readiness and one
focused output exposed a source-fidelity defect before the deterministic
render fix. KPMG's numeric coverage also remains sparse. Step 3 must not
begin; E18 remains **Active/PARTIAL**.

#### Hosted-CI gate remediation — 2026-10-28

Hosted run `40648283236` at `29e18c28` passed the policy, formatting, lint,
typing, architecture, contract, mutation, and repository-hygiene gates but
failed two default-pytest assertions. The selection-cache regression still
expected the intentionally superseded `evidence_backed_shortlisting:19`
constant after the producer had moved to `:20`. The semantic-verdict recovery
regression added in the preceding fix also left its split validation module at
1,049 lines, two above the repository's 1,047-line test-module limit. No
production assertion failed and no release evidence or publication write was
performed by that run.

The follow-up correction synchronizes the cache-version expectation and moves
the recovery regression into `cases_06_semantic_verdict_recovery.py`; it does
not change production behavior, thresholds, or the recovery contract. The
focused correction set passed 132 tests locally. A new hosted run was pushed
for the corrected tree; its final status is reported with this entry's
delivery record rather than inferred from the local run.

#### End-to-end stage alignment and evidence lineage — 2026-10-28 (`04a050a4` producer)

This entry records the completed affected-five replay for the stage-alignment
slice. It uses the exact retained original PDFs, GPT-6 Luna High, isolated
per-report state, the existing bounded recovery paths, and no publication or
WordPress write. The previous corrected-selection baseline is `96db6736`; the
intermediate diagnostic replay at `3f833c9e` is retained as evidence of the
remaining root cause and is not counted as an acceptance run.

##### Root cause and minimal correction

The previous composite-metric correction was present in
`_restore_candidate_factual_fields()`, but `_candidate_factual_fields()` dropped
the internal `verified_fact` marker while building the factual index used by
final selection. Consequently, an authoritative verified composite was treated
as an ordinary candidate and was re-scoped against a narrower final rewrite.
The Adjust diagnostic replay reproduced the resulting finance failure: the
public sentence described sessions `+21%` and installs `-4%`, while the retained
metric was reduced to the sessions observation and failed the authoritative
fact comparison. The same path affected composite gaming facts.

The minimal fix preserves the verified-fact marker through the internal factual
index and, when that marker is present, restores the complete protected metric
binding rather than re-selecting an observation. Final editorial wording is
still retained; protected metric fields, evidence IDs, pages, spans and source
identity remain authoritative. The existing selection cache identity was
advanced to `evidence_backed_shortlisting:23`. No validator, service, LLM stage,
schema, threshold, retry policy or publication path was added or weakened.

##### Stage-contract matrix

| Boundary | Producer → consumer | Required handoff | Existing enforcement | Demonstrated defect / correction | Regression |
| --- | --- | --- | --- | --- | --- |
| PDF → findings | extraction/DocMap → evidence packs | source identity, physical page, span, finding/evidence ID | evidence fidelity and source binding | navigation and source evidence remain distinct; retained source spans were preserved | source-fidelity and evidence-pack suites |
| findings → candidates | evidence packs → shortlisting | finding ID, evidence IDs, pages/spans, protected metric | candidate normalization and fail-closed selection | no arbitrary title/section authority; all five runs retained source-backed candidate rosters | artifact-normalization suite |
| candidates → verified facts | visual admission → verified-fact roster | stable fact ID, discovery provenance, canonical evidence, PDF hash | visual authority admission and verified-fact contracts | all final runs had six source-bound facts; Emplifi quarantined one failed candidate | live admission audit; provenance tests |
| verified facts → editorial plan | fact roster → plan remapping | `verified-fact:{fact_id}` aliases and central-theme evidence IDs | `remap_editorial_plan_to_verified_facts()` fail-closed mapping | themes remained mapped to facts; omissions are recorded as editorial selection, not lost lineage | remapping/coverage regressions |
| plan/candidates → final insights | final rewrite → artifact selection | final wording plus complete authoritative metric/evidence binding | `_candidate_factual_fields()` and `_restore_candidate_factual_fields()` | verified composite marker was lost and then preserved; complete composite metrics now survive final selection | two Adjust composite regressions |
| final insights → grounding | artifacts → retained grounding/validation | exact evidence IDs, source identity, pages/spans, protected metric tuple | semantic/grounding and retained-claim validators | all five terminal artifacts passed validation; no unsupported/unresolved retained material claim | 293-test affected suite |
| artifacts → HTML | normalized artifacts → renderer | source-backed public copy; `toc_only` navigation non-authoritative | render normalization and public-prose tests | navigation-only text cannot become factual HTML; no internal IDs appeared in visible text | render/public-prose suite |
| HTML → readiness | renderer/report-card → readiness | valid HTML, compact TLDR, source identity, manifest | readiness and report-card gates | all five manifests were schema `1.0`, source identity resolved, compact TLDR valid | live manifests and readiness pass |

##### Frozen affected-five result

The fresh run root is:

```text
C:\ml-stage-alignment-live-20261028-fix5\frozen-reliability-zho2zji2
```

All source hashes matched the frozen manifest:

| Report | PDF SHA-256 | Candidates evaluated/admitted | Verified facts | Final insights | Plan themes mapped / represented in final roster | Validation / readiness |
| --- | --- | ---: | ---: | ---: | --- | --- |
| Adjust | `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` | 6 / 6 | 6 | 5 | 5 / 5 | pass / pass |
| KPMG | `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589` | 6 / 6 | 6 | 5 | 5 / 4 | pass / pass |
| Emplifi | `54a6726033fce9474929dec62bc85fc4dd3ada574398d043d12ec48b0eaddeb5` | 7 / 6 | 6 | 6 | 6 / 6 | pass / pass |
| Reuters Institute | `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52` | 6 / 6 | 6 | 6 | 6 / 6 | pass / pass |
| Algolia | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50` | 6 / 6 | 6 | 5 | 5 / 4 | pass / pass |

KPMG's `us-reported-confidence-and-readiness` candidate and Algolia's
`future-ai-search-features` candidate were source-bound and available but were
explicitly omitted by the five-slot final editorial selection; neither was
silently lost during remapping or promoted with substituted evidence. Adjust's
`finance-global-annual-and-monthly-pattern` was also available but the final
roster retained the distinct finance install finding instead. Emplifi's
`facebook-generational-use` was quarantined with
`outcome_failed_verification`; the six remaining mapped themes were retained.
These are editorial disposition records, not factual errors.

| Report | Provider calls | Input / output tokens | Cost | Complete duration | File-search calls | Structured repairs | Targeted automatic repairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Adjust | 47 | 528,541 / 119,127 | `$0.131607` | 1,043.839s | 8 | 1 | 0 |
| KPMG | 50 | 356,499 / 91,632 | `$0.110395` | 654.274s | 12 | 0 | 3 |
| Emplifi | 55 | 730,405 / 117,356 | `$0.145318` | 897.818s | 6 | 0 | 0 |
| Reuters Institute | 63 | 609,074 / 214,609 | `$0.181357` | 1,258.942s | 8 | 2 | 3 |
| Algolia | 49 | 634,095 / 117,902 | `$0.133625` | 883.372s | 5 | 0 | 0 |
| **Total** | **264** | **2,858,614 / 660,626** | **`$0.702302`** | **4,738.245s** | **39** | **3** | **6** |

All five reports were isolated, admitted, validated, readiness-pass and
awaiting review; operator intervention was zero, WordPress writes were zero,
and publication was false. The cohort baseline at `96db6736` was 205 calls,
2,368,040 input tokens, 346,408 output tokens, `$0.553748`, 3,913.302 seconds,
and 1/5 readiness. The corrected run therefore adds 59 calls (+28.78%),
490,574 input tokens (+20.72%), 314,218 output tokens (+90.71%), `$0.148554`
(+26.83%), and 824.943 seconds (+21.08%). This is provider/recovery
variability plus the successful completion of the previously failing reports;
the replay does not establish a general cost or speed improvement.

##### Evidence-lineage and independent PDF/HTML review

The retained chain was reconstructed for every final insight as:

```text
original PDF/hash → source finding/evidence span → candidate ID
→ verified-fact:{fact_id} → final insight ID/evidence ID
→ retained grounded claim → HTML/public report-card manifest
```

Representative source checks on the original PDFs found no material mismatch:

| Report | Reviewed source-backed claims and physical pages | Result |
| --- | --- | --- |
| Adjust | CPI aggregate/deal-discovery distinction p.29; installs/sessions p.27; finance installs p.34; casino/slots p.19; cross-platform satisfaction p.11 | Composite metric retained in full; final wording matches the cited observation(s) |
| KPMG | 52% operational disentanglement p.31; recovery/pipeline p.5; AI analysis p.26; talent and execution capability p.33 | Five qualitative/quantitative claims remain source-grounded; one lower-priority plan theme explicitly omitted |
| Emplifi | inauthentic-service response p.17; research cohort p.4; reviews p.10; AI disclosure p.13; Carhartt p.12; infrastructure p.20 | Six supported themes retained; one failed candidate quarantined |
| Reuters Institute | confidence p.6/p.9; search expectation p.12; reporting priority p.17; creator concerns p.24; newsroom AI p.33; subscriptions p.38 | Population, timeframe and survey bases remain attached; no navigation-only factual prose leaked |
| Algolia | agentic adoption p.26; image-search value p.18; third-party development p.22; backend integration p.14; purchase likelihood p.12 | Four quantitative and one qualitative final claims are source-consistent; future-feature candidate explicitly omitted |

Every final insight uses a `verified-fact:{fact_id}` evidence ID and each
verified fact retains its discovery candidate/evidence IDs, source identity,
PDF hash and physical pages. The final HTML files are retained under the run
root's five member directories. Visible HTML text contained zero
`verified-fact:`, `candidate_id` or `discovery_candidate_id` markers in all five
files. The two raw `source:` occurrences per file are the existing source trace
metadata, not public prose. Reuters visible HTML contains no unsupported
“previous three years” sentence; the source-backed two-and-a-half-year wording
remains available in the original PDF lineage. All five report-card manifests
are schema `1.0`, have resolved source identity, and contain a nonempty compact
TLDR within the existing word contract.

##### Verification and acceptance

The final deterministic checks were:

```text
python -m pytest -q tests/test_artifact_normalization.py tests/test_artifact_normalization_source_fidelity.py --tb=short
59 passed in 2.20s

python -m pytest -q tests/test_grounding_recovery_effectiveness.py \
  tests/test_grounding_recovery_diagnostics.py \
  tests/test_structured_output_service.py \
  tests/test_structured_output_recovery_effectiveness.py \
  tests/test_structured_output_recovery_diagnostics.py \
  tests/test_retained_claim_grounding.py \
  tests/test_verified_grounding_batch_context.py \
  tests/test_grounding_cohort_false_positive_regressions.py \
  tests/test_grounding_semantic_outcomes.py \
  tests/test_grounding_editorial_interpretation.py \
  tests/test_grounding_protected_facts.py \
  tests/test_grounding_public_identity.py \
  tests/test_candidate_recovery_and_selection_regressions.py \
  tests/test_report_analysis_validation_fallback.py \
  tests/_test_claim_validation_generator \
  tests/_test_evidence_pack_generator \
  tests/test_render_service_public_prose.py \
  tests/_test_render_service_artifacts/cases_01_metadata_and_artifact_sections.py \
  tests/_test_render_service_artifacts/cases_02_render_identity_and_publication.py \
  tests/_test_validation_generator/cases_03_grounding_cache_and_reuse.py --tb=short
293 passed in 21.50s

python scripts/ci/check_formatting.py                 PASS
python scripts/ci/check_ruff_lint.py                  PASS
python scripts/ci/run_type_check.py                   PASS (786 source files)
python scripts/ci/check_architecture_imports.py       PASS
python scripts/ci/check_contract_schemas.py            PASS
python scripts/ci/check_role_io_boundaries.py         PASS
python scripts/ci/check_service_boundary_map.py       PASS
```

Hosted CI for producer `04a050a4` passed all jobs, including tests, mutation
partitions, static/architecture/type checks, release prerequisites and hygiene:
<https://github.com/mbrakker/marketlense/actions/runs/40716016044>.

**Affected-five verdict: PASS.** The one unattended original-PDF cohort reached
5/5 readiness with zero independently confirmed unsupported or unresolved
retained material claims, and the previously demonstrated composite-binding,
coverage and provenance failures were either corrected or fail-closed. **Overall
Step 2 promotion verdict: PARTIAL / NO-GO.** This run does not prove broad
provider-output stability, universal editorial selection quality, or replace
the unresolved broader ten-report acceptance evidence; Step 3 remains
unstarted. The explicit KPMG and Algolia editorial omissions and non-blocking
artifact-quality warnings remain documented rather than being treated as
factual failures.

#### Verified-facts theme-fallback correction and provider-limited replay — 2026-10-29 (`2654424d`)

This entry records the final targeted correction after the `04a050a4` stage-
alignment run. The demonstrated KPMG failure was not an evidence or source
binding failure: the admitted visual fact supported the central proposition,
but `render_task()` and the non-DAG final validator checked the model's raw
`insights_final` roster before the existing post-render selector could fill an
eligible admitted alternative. The model's omission therefore failed the
central-theme gate instead of using the already source-bound candidate pool.

The minimal correction adds no validator or LLM stage. In verified mode only,
final coverage validation and final selection use the admitted, hash-bound
candidate pool for deterministic supplementation after raw stable-ID lineage
validation. Matching stable IDs retain the final editorial wording and the
authoritative protected binding; normal mode and the existing fail-closed
unknown-ID behavior are unchanged. The regression
`test_verified_generation_fills_omitted_theme_from_admitted_candidate` proves
that a model roster omitting a supported planned theme is completed from an
admitted candidate, while the existing semantic-coverage and lineage tests
continue to reject unsupported IDs and uncovered central themes.

##### Focused verification

The affected suite passed **102 tests**. The exact local gates also passed:

```text
python scripts/ci/check_formatting.py                         PASS
python scripts/ci/check_ruff_lint.py                          PASS
python scripts/ci/run_type_check.py                           PASS (786 source files, 0 tracked errors)
python scripts/ci/check_architecture_imports.py                PASS
python scripts/ci/check_forbidden_patching.py                  PASS
python scripts/ci/check_prompt_fixture_regression.py ...        PASS (baseline unchanged)
```

The prompt fixture corpus was not changed by this correction; the accepted
baseline remains 110,410 total tokens and `$0.024543`, with the intentional
verified-grounding increase already recorded above. No new prompt family was
called by the live Adjust run.

##### Retained real-claim semantic replay

The existing live GPT-6 Luna High retained-input replay evaluated **27/27**
real shortlisted claims across the exact five frozen PDFs. All five source
hashes matched. Outcomes were mutually exclusive: **25 verified first pass,
2 verified after retry, 0 unresolved, 0 failed, and 0 skipped**. The ledger
recorded **58 provider calls, 957,446 input tokens, 49,082 output tokens,
1,006,528 total tokens, `$0.120286`, and 696.923 seconds**. Per-report
results were Adjust 5/5, KPMG 5/5, Emplifi 6/6 (one after retry), Reuters
Institute 6/6, and Algolia 5/5 (one after retry). This is a live visual-
verification replay over retained artifacts produced at `04a050a4`, not fresh
candidate selection evidence and not a claim that the new final-theme fallback
was exercised by the provider response.

##### Fresh affected-five E2E attempt at `2654424d`

The fresh isolated run used the exact frozen PDFs, verified-facts architecture,
GPT-6 Luna High, no publication target, and no final-artifact reuse:

```text
C:\ml-stage-alignment-live-20261029-p1-fresh\frozen-reliability-iwf1q6ne
```

The run reached terminal records for all five members and recorded **115
provider calls, 631,725 input tokens, 142,617 output tokens, `$0.178410`, and
1,867.918 seconds**. Adjust was the only report able to complete the verified
editorial path: 6/6 visual facts admitted, 5 final insights, 5/5 planned
themes represented, 49 calls, 391,304 input / 100,121 output tokens,
`$0.108219`, 858.886 seconds, validation/readiness PASS, and zero unsupported
or unresolved material claims. Its final source pages were 34, 40, 19, 27,
and 9; metric-spine and key-figure coverage were 4 and 1; the HTML contained
zero `verified-fact:`, `candidate_id`, or `discovery_candidate_id` markers.
Independent review found the global finance install/session, strategy-game,
e-commerce install/session, cross-channel, and advanced-GenAI claims
source-consistent, with the advanced-group limitation retained.

KPMG, Emplifi, Reuters Institute, and Algolia did not reach evidence admission
or editorial generation. KPMG's remediation record retains the underlying
provider `RateLimitError` (with model/provider/status context keys), followed
by the configured `llm_circuit_open`; the other three members received the
same circuit-open terminal outcome. A separate isolated retry of exactly those
four reports confirms the limitation rather than masking it:

```text
C:\ml-stage-alignment-live-20261029-p1-retry\frozen-reliability-n_mhm8cz
```

The retry recorded **26 provider attempts, 0 tokens, `$0.000000`, and
704.554 seconds**; all four terminated with typed `llm_circuit_open` and no
verified-fact, HTML, readiness, canonical, or publication artifacts. This is
an external provider/quota limitation, not a selection or factual-validation
failure. No code change was made to weaken the circuit breaker or retries.

##### Status

The deterministic theme-omission correction is **PASS**, and the retained
visual semantic replay is **PASS** for its stated post-selection scope. The
fresh affected-five verified editorial acceptance is **PARTIAL / NO-GO**:
only Adjust reached the corrected path, while four reports were blocked by the
provider rate limit before the new behavior could be evaluated. Broad live
selection effectiveness, repeated-run stability, and Step 3 readiness remain
unproven. No ten-report cohort was started, no canonical claim was promoted,
and no WordPress write occurred.

#### Verified-facts central-theme fallback and CI correction — 2026-10-29 (`01d2d61e`)

The follow-up correction closed the remaining implementation and test-contract
issues exposed by the first hosted run. The verified final-selection helper now
first restores final editorial wording together with the complete authoritative
candidate binding. It supplements only a genuinely omitted **central** planned
theme, and only from an admitted candidate whose evidence identity covers that
theme. Optional or lower-priority theme omissions remain valid; unsupported or
unbound candidates still fail closed. This keeps the existing selection order,
stable IDs, source pages/spans, protected factual fields, and normal-mode
behavior unchanged. The new `editorial_theme_coverage` family is also persisted
in prompt-family checkpoints so downstream replay has complete lineage.

The first follow-up hosted run, `40790458154`, failed for stale expectations:
three snapshot assertions still expected the pre-fallback roster/call count,
the canary exceeded the enforced test-file ownership limit, and the new prompt
family was not included in the checkpoint-materialization expectation. Those
were test/lineage maintenance defects, not a relaxation of a production gate.
After the surgical correction, the affected local suite passed **123 tests**.
Formatting, Ruff, mypy, architecture imports, forbidden-patching,
documentation, quality-ledger, and prompt-fixture gates all passed. Hosted run
`40792156557` then passed all jobs: `ci_start`, both mutation partitions,
`tests`, and `release_evidence` (including the quality non-regression, PDF
benchmark, prompt-fixture, LLM-accounting, and release-manifest gates). The
WordPress staging REST check remained the repository's expected skipped check;
no WordPress write occurred.

The provider-backed evidence remains the same as the preceding entry: the
fresh affected-five run at `2654424d` completed only Adjust, while KPMG,
Emplifi, Reuters Institute, and Algolia were blocked by the retained provider
rate-limit/circuit-open condition before the corrected selection path could be
exercised. The deterministic correction and its focused regressions therefore
pass, but this does not establish fresh current-HEAD selection quality for
those four reports. The retained semantic replay remains a post-selection
replay, not new selection evidence.

**Final status:** deterministic implementation **PASS**; retained semantic
replay **PASS for its stated scope**; fresh affected-five acceptance
**PARTIAL / NO-GO** because of the external provider limitation. Step 2 remains
**PARTIAL/NO-GO** for promotion and Step 3 remains **unstarted/not ready**.
No ten-report cohort was started, no canonical claim was promoted, and no
publication write occurred.

#### Final central-theme coverage correction and exact frozen-five audit — 2026-10-29 (`a8a7787c75a55a505de6dd3e229ca84dc2c66983`)

This entry records the remaining P1/P2 implementation slice and the first
clean exact-cohort run from the corrected tree. The implementation is split
across the following surgical commits:

| Commit | Evidence-backed change |
| --- | --- |
| `6fcedaef` | Assesses every supported editorial-plan theme against the admitted verified facts, not only themes whose IDs happen to overlap the final roster; adds bounded existing-mechanism repair. |
| `5c8ae244` | Gives the persisted semantic theme-coverage checkpoint its correct prompt contract identity. |
| `c1ffc9db` | Makes the existing final-insight repair explicitly substantive for every omitted central theme while preserving IDs, bindings and no-new-facts rules. |
| `1e7bd7f9` | Adds a final bounded source-bound candidate fallback after model repair, then reruns the same semantic assessment; exhaustion remains fail-closed. |
| `a8a7787c` | Reverts an unproven prompt-clarification experiment; no unsupported prompt relaxation is retained. |

No new validator, service, database, LLM stage, publication path or canonical
claim mutation was introduced. Normal-mode behavior is unchanged. The
existing stable-ID, evidence-binding, protected-field and publication gates
remain authoritative.

##### Exact frozen-five run

The run was isolated, provider-backed, GPT-6 Luna High, verified-facts mode,
and used the original local PDFs without publication writes or final-artifact
reuse:

```text
C:\ml-stage-alignment-live-20261029-frozen-five-clean\frozen-reliability-wqoag3t1
```

The source lineage rows matched the required PDFs:

| Report | Required source SHA-256 | Run terminal outcome |
| --- | --- | --- |
| Adjust | `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` | `artifact_final_insight_coverage_invalid` |
| KPMG | `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589` | `verified_fact_editorial_coverage_insufficient` |
| Emplifi | `54a6726033fce9474929dec62bc85fc4dd3ada574398d043d12ec48b0eaddeb5` | `verified_fact_editorial_coverage_insufficient` |
| Reuters Institute | `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52` | `artifact_final_insight_coverage_invalid` |
| Algolia | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50b` | `artifact_final_insight_coverage_invalid` |

All five inputs were admitted and all five received typed terminal records.
No report reached verified-facts artifact materialization, final HTML,
readiness pass, or publication. Aggregate measurements were **200 provider
calls**, **2,274,603 input tokens**, **341,448 output tokens**, **$0.495184**,
and **3,736.475 seconds**; automatic repairs and operator intervention were
zero. The complete machine-readable result is
`C:\ml-stage-alignment-live-20261029-frozen-five-clean\frozen-reliability-wqoag3t1\cohort_result.json`.

| Report | Calls | Input / output | Cost | Duration | File search | Structured repairs | Earliest terminal stage and reason |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Adjust | 45 | 456,650 / 94,431 | `$0.110279` | 924.138s | 7 | 1 | Final artifact semantic central-theme coverage remained invalid after bounded repair and source-bound fallback. |
| KPMG | 36 | 215,025 / 31,552 | `$0.064681` | 375.795s | 11 | 0 | Verified-fact remapping lost an unambiguous central editorial-plan binding; the workflow failed closed before final insights. |
| Emplifi | 36 | 518,614 / 43,123 | `$0.088324` | 500.502s | 6 | 0 | Verified-fact remapping lost the central “Make authenticity consistent across customer interactions” binding; the workflow failed closed before final insights. |
| Reuters Institute | 40 | 455,033 / 95,475 | `$0.113138` | 991.640s | 8 | 1 | Final artifact semantic central-theme coverage remained invalid after bounded repair and source-bound fallback. |
| Algolia | 43 | 629,281 / 76,867 | `$0.118762` | 944.400s | 7 | 0 | Final artifact semantic central-theme coverage remained invalid after bounded repair and source-bound fallback. |

The exact failure split is therefore **3 semantic final-coverage failures and
2 upstream verified-fact editorial-remap failures**. The KPMG workflow error
persisted only the bounded count-key diagnostic, so its specific lost theme is
not recoverable from the exported summary; the remap message and terminal
code are retained. This is an auditability limitation, not evidence to infer
or silently repair the missing binding.

For the three final-coverage failures, the live ledger shows the original
theme-coverage call, one existing final-insight repair call, and a third
theme-coverage call after source-bound candidate fallback. The responses were
structured and the gate still reported an omitted supported central theme.
That is the intended fail-closed result when the model does not produce a
substantive supported development, not proof that the source lacked evidence.
For KPMG and Emplifi, the failure occurred earlier at
`remap_editorial_plan_to_verified_facts()`, where a plan reference had no
single admitted-fact identity; no topic, heading or nearby page was promoted
as a substitute.

##### Baseline comparison and review limits

Against the accepted successful producer `04a050a4` baseline (5/5 readiness,
30 facts, 264 calls, 2,858,614 input tokens, 660,626 output tokens, `$0.702302`,
4,738.245 seconds), the clean `a8a7787c` attempt used 64 fewer calls, 584,011
fewer input tokens, 319,178 fewer output tokens, `$0.207118` less cost and
1,001.770 fewer seconds. These are **not improvements**: the current run
terminated before final facts and HTML, so the lower resource use is caused by
incomplete processing and cannot be compared for editorial quality.

The source PDFs and pre-materialization evidence-fidelity artifacts were
available for inspection, but there was no final PDF-to-HTML output to review.
Consequently this run cannot establish final insight identities, wording,
metric-spine coverage, HTML completeness, or independent editorial quality.
The prior successful retained-artifact semantic replay remains post-selection
evidence and is not substituted for fresh selection evidence here.

##### Verification

The focused regression suite passed **102 tests**:

```text
python -m pytest -q tests/test_verified_claims_visual_authority_snapshot_integrity.py \
  tests/test_adjust_editorial_selection_p1.py \
  tests/test_candidate_recovery_and_selection_regressions.py \
  tests/test_report_checkpoint_lineage_validation.py \
  tests/test_artifact_normalization.py --tb=short
102 passed in 12.71s
```

The current-tree checks also passed: full-repository mypy (**786 source files,
0 tracked errors**). Formatting and Ruff reported no changed Python files in
the clean worktree. No WordPress, canonical-claim, publication, or ten-report
cohort operation occurred.

**Verdict: PARTIAL / NO-GO.** The deterministic P1/P2 implementation and
regressions pass, and all five exact source inputs were admitted with
fail-closed terminal outcomes. The fresh provider-backed cohort did not reach
final artifacts, so Step 2 is not promotion-ready and Step 3 remains
unstarted/not ready. The remaining material blocker is reliable live mapping
and substantive central-theme completion under provider-generated plans; it
must not be addressed by weakening provenance or coverage gates.

#### Final hosted-CI fixture correction — 2026-10-29 (`52b853b961281337450e4669796c4e620939b1ae`)

The first hosted run for the evidence update (`40866392374`) exposed one
regression-fixture defect: the verified full-roster test exercised the newly
required `editorial_theme_coverage` call but did not provide that family in its
fake provider response. The failure was therefore a stale test fixture, not a
production coverage failure or a missing recovery path. The fixture now
contains a complete seven-theme semantic response; no production code,
prompt, schema, gate, retry limit, source binding, or provider call was
changed.

The affected local suite passed **113 tests**. Hosted run `40867896202` for
the final pushed SHA passed `ci_start`, `tests` (**8,243 passed, 1 skipped**),
both mutation partitions, and `release_evidence`; the WordPress staging REST
check remained the expected skipped check. This confirms the deterministic
implementation and its regression coverage are green. It does not change the
exact frozen-five provider result above: that run remains **PARTIAL / NO-GO**
because it failed closed before final verified-facts and HTML artifacts.

#### Exact frozen-five verified-facts editorial audit after admitted-alternative recovery — 2026-10-29 (`287d690488354916601ee0a0a1b21da71562a7b5`)

This is the current provider-backed verification of the surgical admitted-alternative
recovery correction. The implementation preserves final editorial wording for a
matching stable ID, keeps authoritative verified spans in the metric spine, and lets
the existing bounded semantic-recovery path replace a selected source-bound fact with
an admitted alternative when the selected fact does not satisfy the supported central
theme. It adds no validator, service, LLM stage, prompt relaxation, publication path,
or canonical-claim mutation. The semantic-recovery regression was moved to a separate
test module so the repository's 1,000-line test-file ownership gate remains active.

##### Run identity and source integrity

The exact frozen-five manifest was run in verified-facts mode with GPT-6 Luna High,
the original retained PDFs, no publication writes, and no final-artifact substitution:

```text
C:\Users\Михаил\ml-stage-alignment-live-20261029-final-five-287d6904b\frozen-reliability-5e5mfdja
```

All five source lineage records matched the required SHA-256 values:

| Report | Required source SHA-256 | Match |
| --- | --- | --- |
| Adjust | `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` | yes |
| KPMG | `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589` | yes |
| Emplifi | `54a6726033fce9474929dec62bc85fc4dd3ada574398d043d12ec48b0eaddeb5` | yes |
| Reuters Institute | `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52` | yes |
| Algolia | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50b` | yes |

The machine-readable result is
`C:\Users\Михаил\ml-stage-alignment-live-20261029-final-five-287d6904b\frozen-reliability-5e5mfdja\cohort_result.json`.
All five reports were admitted and reached typed terminal outcomes. The aggregate
was **295 provider calls**, **3,341,130 input tokens**, **828,380 output tokens**,
estimated cost **$0.830416**, and **5,153.028 seconds**. Operator intervention was
zero. There were no WordPress writes, canonical claim promotions, or publication
side effects.

##### Terminal outcomes and resources

| Report | Outcome | Visual facts | Calls | Input / output | Cost | Duration | Structured recovery | Automatic repairs | Readiness |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Adjust | admitted / validation pass | 7/7 | 55 | 622,849 / 146,484 | `$0.151352` | 898.658s | 2 | 0 | pass |
| KPMG | admitted / validation failed | 6/6 | 69 | 488,863 / 189,432 | `$0.170570` | 889.428s | 1 | 6 | fail closed |
| Emplifi | admitted / validation pass | 7/7 | 54 | 621,856 / 125,796 | `$0.136232` | 917.192s | 0 | 0 | pass |
| Reuters Institute | admitted / validation failed | 7/7 | 64 | 856,395 / 235,376 | `$0.220677` | 1,320.227s | 5 | 0 | fail closed |
| Algolia | 5/6 admitted, 1 quarantined | 6 evaluated | 53 | 751,167 / 131,292 | `$0.151585` | 1,127.523s | 1 | 0 | pass |

The passing/readiness split was **3/5**. Algolia's admission audit retains aggregate
evidence-fidelity failures for five pre-admission source candidates, but the exported
artifact does not retain an individual candidate-level reason for the one quarantined
visual candidate. This is reported as an auditability limitation rather than an
inferred assignment. No unsupported material claim was promoted in a passing report.

##### Root-cause outcomes

KPMG failed closed in the existing grounding gate. The retained executive-summary
and expert-comment wording stated that dealmakers emphasize integration readiness
before close rather than post-close fixes, while the authoritative evidence supported
that contrast specifically in the context of post-deal value realization. Six bounded
targeted repairs attempted supported replacements or safe removal, but the resulting
rosters introduced new grounding problems or failed to preserve the required
authoritative context and were rolled back. An isolated KPMG replay at the same SHA
selected a different admitted fact set and passed, but it is not combined with this
exact-five result and demonstrates provider/model selection variability, not a reason
to weaken the gate.

Reuters failed closed on a semantic interpretation error: the evidence established
declines in publisher-site referrals from Facebook and X in the global dataset, but
did not establish the final `so_what` description that these were “two major social
platforms”. The issue is a qualitative overstatement, not an unsupported numerical
promotion. The final artifact was withheld because the existing validation contract
correctly treats this as material.

Adjust retained seven final insights and Emplifi six. Independent inspection of their
original PDF pages confirmed the selected numerical relationships, populations,
periods, units and qualifiers. Adjust's final pages were 19, 21, 29, 30, 34, 35 and
36; examples include finance installs `-4%` YoY with sessions `+21%`, the paid/organic
ratio `0.48` to `0.54`, LATAM installs `+76%` with sessions `+57%`, and the 7.18-minute
session length. Emplifi's pages 4, 10, 13, 15, 18 and 19 supported the selected
survey/research percentages and the stated hypothetical or recommendation qualifiers.
Algolia's five final insights were independently supported on pages 12/16, 22, 25
and 26, including the market-specific 63/68/57 likelihoods with their sample sizes,
17% implemented versus 61% planned, and the 49/27/23 implementation approaches.

The final Adjust, Emplifi and Algolia HTML files contained zero occurrences of
`candidate_id`, `evidence_id`, `verified-fact:`, `source_pack`, `fact_id`, or
`metric_binding`. KPMG and Reuters had no HTML because the fail-closed validation
outcome correctly prevented materialization.

##### Comparison with the accepted producer

The accepted `04a050a4` run produced 5/5 readiness passes, 30 visual facts, 264
provider calls, 2,858,614 input tokens, 660,626 output tokens, `$0.702302`, and
4,738.245 seconds. The current run produced 3/5 readiness passes, 295 calls,
3,341,130 input tokens, 828,380 output tokens, `$0.830416`, and 5,153.028 seconds.
That is **+$0.128114 (+18.24%) cost**, **+31 calls (+11.74%)**, **+482,516 input
tokens (+16.88%)**, **+167,754 output tokens (+25.39%)**, and **+414.783 seconds
(+8.75%)**. The differences include the current bounded recovery/coverage work and
provider variability; they are not a quality improvement because the current exact
cohort has two fail-closed reports and only three readiness passes. The run does,
however, demonstrate that the new recovery path preserves source-bound alternatives
without promoting the two materially unsupported interpretations.

##### Verification

The affected focused suite passed **17 tests** after the new regression was split out
of the long snapshot module. The expanded affected suite passed **234 tests** in
**52.82s**, including artifact normalization, semantic recovery, regeneration,
lineage, generation, and shortlisting tests. The long-test-file ownership check passed.
The new regression proves that a selected source-bound fact can be replaced by an
admitted source-bound alternative during semantic recovery while preserving the
alternative's authoritative wording and bindings. Existing tests continue to cover
stable IDs, protected fields, source spans, cache behavior, fallback coverage, and
fail-closed validation.

**Verdict: PARTIAL / NO-GO.** The deterministic correction and focused regressions
pass, and the exact frozen-five run preserved source identity and fail-closed factual
gates. Three reports passed independent PDF/HTML review; KPMG and Reuters remain
material editorial-grounding blockers. Step 2 is not promotion-ready and Step 3
remains unstarted/not ready. No additional corrective work is justified solely for
hypothetical edge cases, and no ten-report cohort was started.

#### P1 root-cause remediation and transactional regeneration — 2026-10-30 (`750979af`; renderer follow-up `62c848b6`)

This section records the exact requested five-report provider-backed run after the
transactional evidence-preservation and verified-fact projection corrections. The
run used GPT-6 Luna High, the retained original PDFs, isolated fresh report state,
and no publication or WordPress writes. The requested five is an explicit slice of
the committed ten-report manifest; there is no separate committed five-report
manifest. The source-manifest SHA-256 is
`190CFF0D3EC7B80190BB7B8791BA4255081278AEDF0433BED542C1216694FDA6`.

```text
scripts/quality/run_frozen_reliability_cohort.py \
  --sources-manifest scripts/quality/frozen_reliability_cohort_10.json \
  --sources-root C:\Programing\Market lense-step2-final \
  --runs-root C:\ml-p1-root-cause-runs-20261030 \
  --max-duration 7200 \
  --report-ids cohort-2acb4a56e14add5d7717 \
    cohort-4b763ae2286ca69fe8ac \
    cohort-b638414df0b1fccea1cd \
    cohort-86858bdcb370266f26c2 \
    cohort-f62048b469dd784e6e7c \
  --verified-facts-architecture
```

The immutable machine-readable result is
`C:\ml-p1-root-cause-runs-20261030\frozen-reliability-cixcvcy4\cohort_result.json`.
All five source hashes matched the selected manifest:

| Report | Source identity | PDF SHA-256 | Evaluated / admitted | Final insights | Readiness |
| --- | --- | --- | ---: | ---: | --- |
| KPMG | `source:1ffb71d718276f8a1761fc706a2a3cb3` | `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589` | 6 / 6 | 5 | pass |
| Reuters Institute | `source:79cb8c886c55b49bfdec2128d5b25e0b` | `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52` | 7 / 7 | 7 | pass |
| Adjust | `source:8cb648b6bbd9dbae4ec1d915c38cf235` | `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` | 6 / 6 | 6 | pass |
| Algolia | `source:4ea9ae5709898e763efb0945d8d4fa1e` | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50b` | 6 / 5 | 5 | pass |
| Emplifi | `source:dda03b3a0d65814672444674bb59908f` | `54a6726033fce9474929dec62bc85fc4dd3ada574398d043d12ec48b0eaddeb5` | 6 / 6 | 6 | pass |

The 29 selected stable IDs were:

| Report | Final stable IDs |
| --- | --- |
| KPMG | `insight-carveout-outlook`, `insight-ma-momentum-2025`, `insight-talent-retention-execution`, `insight-ai-knowledge-codification`, `insight-us-confidence-readiness` |
| Reuters Institute | `search-traffic-expectation`, `agentic-apps-impact-expectation`, `ai-era-distinctive-content-priorities`, `publisher-platform-effort-plans`, `section_7_q10_ai_importance`, `commercial-publisher-revenue-priorities`, `section_5_q19_creator_concerns` |
| Adjust | `casino-slots-install-session-divergence`, `global-app-installs-2025`, `ecommerce-cpi-subvertical-divergence`, `finance-retention-by-checkpoint`, `cross-platform-data-satisfaction`, `advanced-generative-ai-efficiency` |
| Algolia | `agentic-search-plans-and-implementation`, `ai-tools-purchase-likelihood`, `genai-effectiveness-varies-by-task`, `search-provider-sourcing-choices`, `agentic-adoption-factors` |
| Emplifi | `high-value-research-validation`, `ai-disclosure-expectation`, `service-interactions-authentic`, `inauthentic-service-stated-churn`, `review-reading-change`, `carhartt-ugc-conversion` |

The aggregate run produced **259 provider calls**, **3,319,653 input tokens**,
**593,660 output tokens**, estimated cost **$0.714479**, and **4,399.016 seconds**.
File-search calls were 11/8/6/6/6 for KPMG/Reuters/Adjust/Algolia/Emplifi.
Adjust and Emplifi each used one structured-output recovery call; there were no
automatic repairs, operator interventions, publication writes, or workflow retries.
Every report has a typed terminal record, validation pass, zero retained unsupported
claims, and zero retained unresolved factual claims. Algolia's admission audit
quarantined one candidate, `revenue-search-investment-incentive`, with
`outcome_unresolved`; its retained record had no evidence spans and only an
unapproved page-5 locator. The other five admitted facts covered all five planned
editorial themes, so this was an explicit fail-closed omission rather than silent
coverage loss.

##### Root causes and demonstrated corrections

The earlier exact-five run at `287d6904` had KPMG and Reuters fail closed after
grounding/repair attempts: KPMG's soft-copy contrast overreached the context of
post-deal value realization, while Reuters described publisher-site referral
declines as “two major social platforms” without source support. The targeted
regeneration correction in `e3b7c3f7` preserves authoritative evidence for explicit
editorial/soft-copy issues, revalidates unresolved siblings, and still quarantines
real binding failures. The current five-report run had no automatic repair, so this
live run confirms no regression but does not claim to exercise those repair paths.

The current `750979af` correction removes the demonstrated lossy verified-fact
projection: grounding and canary inputs now carry deterministic JSON for the complete
authoritative fact, including nested observations and qualifiers. Verified mode also
skips the source-display normalization that previously made evidence text diverge
from public copy, and evidence-backed optional copy survives summary abstention.
These changes are covered by focused regeneration, grounding, verified-fact, and
soft-copy tests; the exact five run showed no protected-field or evidence-lineage
regression. No unsupported fact was promoted from the quarantined Algolia candidate.

Independent PDF review matched the final physical support: KPMG pages 7, 19, 27,
and 33; Reuters pages 12, 17, 20, 24, 32, 38, and 41; Adjust pages 6, 9, 11,
19, 29, and 37; Algolia pages 12, 15, 22, 26, and 27; and Emplifi pages 4, 10,
12, 13, 15, and 17. The review checked numerical values, units, populations,
periods, forecast/plan status, and qualitative qualifiers against the original
PDFs. The resulting metric-spine/key-figure counts were KPMG 1/1, Reuters 6/5,
Adjust 6/3, Algolia 5/4, and Emplifi 6/4.

The review also found a separate deterministic public-rendering defect in the
provider-backed HTML generated at `750979af`: `_sanitize_public_prose()` preserved
only `Q1`–`Q4`, so it stripped `Q5`, `Q10`, and `Q19` from Reuters hero/core/overview
copy even though the claim strip and evidence metadata retained them. Commit
`62c848b6` changes only that existing allow-list to numbered survey items and adds
regressions for `Q5`, `Q10`, `Q19`, and internal `finding_12` removal. A provider-free
rerender from each immutable completed checkpoint produced corrected HTML under
`C:\ml-p1-root-cause-runs-20261030\post-run-render-all-qid-fix\`; Reuters now retains
all three survey IDs and all five rerendered HTML files contain zero internal
candidate/evidence/source tokens. This deterministic rerender made no provider or
publication calls and does not replace a fresh provider-backed run at `62c848b6`.

##### Resource comparison and limitations

Compared with the prior exact-five run at `287d6904` (295 calls, 3,341,130 input,
828,380 output, `$0.830416`, 5,153.028 seconds, 3/5 readiness), the current run
used **36 fewer calls (-12.20%)**, **21,477 fewer input tokens (-0.64%)**,
**234,720 fewer output tokens (-28.33%)**, **$0.115937 less cost (-13.96%)**,
and **754.012 fewer seconds (-14.63%)**, while reaching 5/5 readiness. This is
useful evidence of the corrected run's observed outcome, not a causal performance
claim: provider/model variability and changed retained facts contribute, and the
renderer correction was committed after this provider run. Relative to the accepted
`04a050a4` producer, the current run used 5 fewer calls but more input tokens and
slightly more cost; it is not an optimization result.

##### Verification and verdict

The focused render regression passed **36 tests**; the expanded affected suite
passed **522 tests in 47.62s**. Ruff passed for the changed renderer/test files,
`git diff --check` passed, and the full-repository type gate reported **0 tracked
errors across 786 source files**. The transactional regeneration and evidence
projection regressions remain in the earlier focused suites and are included in
the affected run. No hosted CI result is claimed from this local verification.

**Verdict: PARTIAL / NO-GO for Step 3.** The demonstrated P1 root causes are fixed,
the exact provider-backed five reached 5/5 readiness with no retained factual
errors, and the renderer defect is corrected deterministically. A fresh provider
run at `62c848b6`, repeated selection evidence, independent human editorial sign-off,
and broader Step 2 effectiveness remain open. Step 3 remains unstarted; no
canonical claim promotion or WordPress publication occurred.

#### Transactional claim repair contract and corrected Algolia replay — 2026-10-30 (`e486a84a`)

This section records the transactional claim-repair implementation and the live
replay that exposed and corrected its first production-path compatibility defect.
The change is deliberately limited to the existing regeneration boundary. For an
atomic single-claim scope, the model now returns the strict
`regeneration_claim_repair_proposal` v1 contract: `action`, replacement text, and
already-admitted evidence IDs. Deterministic code owns the target path, patch,
provenance, protected fields, and promotion decision. Family/structural repairs
continue to use the existing `regeneration_repair_decision` contract. Every
proposal is checked for an exact envelope, an atomic allowed target, admitted and
non-quarantined evidence IDs, and complete downstream validation before promotion.
The outer orchestrator keeps the existing copy, integrity, grounding, editorial
quality, and rollback gates.

The first implementation also rejected a valid narrow safe-removal outcome. In the
fresh exact-five run at `3342d676`, Algolia failed with
`regeneration_repair_decision_invalid` / `claim_proposal_removal_not_permitted`.
The model had returned removal for one existing soft-copy claim leaf while the
planner's first strategy was `REGENERATE_ITEM`; the proposal boundary treated that
combination as invalid even though the existing soft-copy safe-removal path could
handle the exact leaf. The targeted correction in `e486a84a` permits removal only
for an exact single claim leaf in `summary`, `expert_comment`, or `linkedin_post`.
Non-atomic and root-level removal remains rejected, and the existing final
validation and promotion gates remain authoritative. The focused regression suite
now covers valid replacement, model-authored path/protected-field rejection,
quarantined evidence, non-atomic removal rejection, valid soft-copy leaf removal,
and exact-replacement no-op handling.

##### Initial exact-five run at the transactional implementation SHA

The run used the retained original PDFs and GPT-6 Luna High with isolated state,
no publication or WordPress writes, and no operator intervention:

```text
C:\ml-p1-transactional-repair-20261030\frozen-reliability-xri__hqr\cohort_result.json
producer SHA: 3342d6764835f9b9a05eccc96cca11c45608f8bc
```

The source hashes matched the frozen manifest. Results were terminal and mutually
exclusive, but this run was not an acceptance pass:

| Report | Terminal result | Calls | Input tokens | Output tokens | Cost | Seconds | Admission / repair detail |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| KPMG | failed: `visual_authority_coverage_insufficient` | 44 | 300,938 | 38,321 | $0.079150 | 518.811 | 3 targeted repairs; failed before final verified-facts materialization |
| Reuters Institute | awaiting review; validation/readiness pass | 60 | 906,028 | 196,279 | $0.206087 | 1,255.135 | 7/7 admitted; 3 targeted repairs, 1 structured recovery |
| Adjust | awaiting review; validation/readiness pass | 50 | 736,700 | 143,058 | $0.158849 | 1,012.325 | 6/6 admitted; 3 targeted repairs, 1 structured recovery |
| Algolia | failed: `regeneration_repair_decision_invalid` | 54 | 804,139 | 119,985 | $0.148891 | 894.767 | 6/6 admitted; proposal removal rejected before repair |
| Emplifi | awaiting review; validation/readiness pass | 56 | 776,334 | 135,089 | $0.158826 | 1,228.576 | 5/6 admitted; 1 candidate quarantined, 1 structured recovery |

Aggregate: **264 calls**, **3,524,139 input tokens**, **632,732 output
tokens**, **$0.751803**, and **4,909.614 seconds**. The run had two workflow
failures and therefore does not establish five-report acceptance. The KPMG failure
was the existing pre-artifact visual-authority coverage gate and was not caused by
the atomic proposal contract. The Algolia failure was the reproducible contract
compatibility defect fixed by `e486a84a`.

Against the preceding accepted exact-five baseline at `750979af` (259 calls,
3,319,653 input, 593,660 output, $0.714479, 4,399.016 seconds), the initial
transactional run used **5 more calls**, **204,486 more input tokens**, **39,072
more output tokens**, **$0.037324 (+5.23%)**, and **510.598 more seconds
(+11.61%)**. This is provider/model and bounded-repair variability, not a claimed
optimization or quality improvement; the current run also had two failures.

##### Corrected Algolia replay

The exact affected report was rerun in a fresh isolated worktree at `e486a84a`:

```text
C:\ml-p1-transactional-repair-20261030-algolia-rerun\frozen-reliability-px117eau\cohort_result.json
```

Algolia completed with `awaiting_review`, validation/readiness **pass**, no
publication, no operator intervention, and no retained unsupported or unresolved
claim. It made **54 provider calls**, used **942,868 input tokens** and **137,274
output tokens**, cost **$0.176413**, and took **1,206.173 seconds**. It admitted
**7/7** verified-facts candidates, quarantined none, and required no structured
recovery or automatic repair. The changed behavior demonstrated by this replay is
specifically that the valid exact soft-copy removal no longer aborts the report;
the replay is not a corrected five-report cohort rerun.

The corrected Algolia artifacts contain six final insights with source bindings:

| Stable finding | PDF page | Independently checked support |
| --- | ---: | --- |
| `insight-agentic-search-deployment-and-plans` | 26 | 17% implemented; 61% planned within 12 months; total n=1,100 |
| `insight-revenue-incentive` | 4 | 58% versus 49% critical revenue incentive comparison |
| `insight-perceived-purchase-likelihood` | 12 | 63% respondent belief; population n=1,100 |
| `insight-accelerated-search-investment` | 23 | Total 2025 adequate 53% versus Total 2024 51% |
| `insight-agentic-adoption-considerations` | 27 | retailer control 86% top-two and 37% very influential |
| `insight-search-development-approaches` | 22 | 49% third-party collaboration in Total 2025 |

The original Algolia PDF SHA-256 is
`d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50b`.
Independent HTML inspection found no visible `verified-fact`, `evidence_id`,
`claim_index`, `source_identity`, `pdf-sha256`, or `validation_run_id` tokens and
confirmed the material numerical, population, period, and qualification fields.
The existing non-rendered `marketbearing-build` HTML comment still contains build
metadata including source and validation identifiers; it is not visible editorial
content and was not changed in this task.

##### CI and regression evidence

The hosted run `41024885107` passed tests (8,264 passed, 1 skipped), both mutation
partitions, and `release_evidence` at `b90a117d`. Its only prerequisite failure
was a test fixture that returned a generic replacement for an atomic target; the
fixture was corrected to return an explicit abstain so the existing safe-removal
path was exercised. The latest `e486a84a` production/test correction still requires
its own final hosted run after this evidence update.

The latest local focused suite passed **366 tests in 57.06s** across transactional
proposal, regeneration, candidate identity, report analysis, validation lineage,
semantic residual, soft-copy, grounding-authority, and normal-mode regression
modules. Type checking reported **0 tracked errors across 786 source files**;
contract-schema, architecture-import, role-boundary, forbidden-patching, and
formatting checks passed. The changed-file Ruff/format gates were already clean;
the raw full-file Ruff command still reports unrelated pre-existing violations in
the large regeneration module. No new LLM stage, service, database, publication
write, or WordPress write was introduced.

The retained raw traces for the older `287d6904` KPMG/Reuters failures were not
present in the available local run roots, so those historical repairs are covered
by deterministic regressions and the new transactional replay rather than claimed
as a fresh raw-trace replay. This is a real evidence limitation.

**Verdict: PARTIAL / NO-GO for Step 3.** The transactional claim-repair boundary,
evidence admission, safe removal, promotion, and rollback protections are covered;
the Algolia defect is corrected and live-replayed. The exact five at the initial
implementation SHA was 3/5 ready with KPMG and Algolia failures, and the corrected
replay covered Algolia only. A fresh five-report replay at `e486a84a`, retained raw
KPMG/Reuters traces, and independent broader Step 2 effectiveness evidence remain
open. Step 3 remains unstarted; no canonical claim promotion or WordPress
publication occurred.

#### Transactional claim-repair root-cause correction — 2026-10-30 (post-`c32e66de`)

This correction closes the remaining implementation defects identified in the
transactional claim-repair review. The change stays inside the existing claim
validation, regeneration, and promotion boundaries; it adds no model stage,
service, store, publication gate, or normal-mode route.

##### Confirmed root causes and fixes

* **Inherited editorial classification bypass:** adversarial tests confirmed
  that a repaired numeric or causal sentence could retain `interpretive` or
  `recommendation` classification and therefore avoid the factual candidate
  gate. `_claim_requires_factual_validation()` now reuses the existing
  claim-kind detection and also gates numeric, quoted, causal, and explicit
  comparative propositions regardless of editorial voice. Pure analytical
  recommendations remain non-factual when they make no source-derived
  proposition. Changed soft-copy claims are included in candidate support
  checks rather than being silently omitted.
* **Action semantics:** explicit `abstain` and exact no-op proposals preserve
  the target text and provenance. Missing support and rejected replacements
  record an auditable abstention and leave the claim unchanged. Only an
  explicit, authorized `remove` mutates the target, and invalid replacements
  are not converted into deletion. Summary claim-map repairs process original
  indexes in descending order.
* **Execution/audit mismatch:** claim-level remove, abstain, no-op, and rejected
  replacement paths now append an existing `RepairDecision` describing the
  executed action and strategy. The response and candidate audit therefore do
  not fall back to the planner's intended `REGENERATE_ITEM` label.
* **Ambiguous targeting:** the old lowest-index summary fallback was removed.
  Duplicate wording without a unique authoritative path now fails closed with
  `atomic_repair_target_unresolved_or_ambiguous`.
* **Partial promotion state:** promotion is now marked as attempted before the
  atomic artifact replacement. If a later related write raises, the existing
  artifact, promoted claim-validation package, and canonical validation report
  are restored where present. Reuse additionally requires an exact artifact
  hash, so a stale or partially written package cannot authorize a different
  artifact. The final-insight path was reviewed and left unchanged: its stable
  ID, allowed leaf paths, deterministic evidence restoration, and downstream
  lineage checks already provide the appropriate constraint for text,
  `so_what`, and `now_what`; structured metric, quote, and source operations do
  not use the claim-only contract. The proposal schema now accepts only version
  `1.0`.

##### Focused and repository verification

The new fault-injection module covers candidate persistence, canonical artifact
replacement, promoted claim-validation persistence, and canonical validation
persistence. The affected suites passed:

| Check | Result |
| --- | --- |
| Claim validation, candidate integrity, proposal contract | **174 passed** |
| Report regeneration generator | **97 passed** |
| Report analysis, identity, and regeneration failures | **94 passed** |
| Combined affected regeneration/validation suites | **365 passed** |
| Contract schema roundtrip and schema gate | **2,364 tests passed; schema gate passed** |
| Role I/O boundary and forbidden-patching gates | **passed** |
| Ruff changed-file gate and formatting gate | **passed** |
| Full-repository mypy baseline | **0 tracked errors across 786 source files** |

##### Genuine retained real-report repair

The available genuine repair trace is the Reuters Institute run at producer
SHA `3342d6764835f9b9a05eccc96cca11c45608f8bc`, retained at
`C:\\ml-p1-transactional-repair-20261030\\frozen-reliability-xri__hqr\\members\\cohort-4b763ae2286ca69fe8ac\\ias-first-attempt-n56hynjz\\output\\trends-and-predictions-2026-pdf\\report_analysis`.
It predates the current uncommitted correction, so it is integration evidence,
not a causal live result for this final tree.

The failed claim was the Reuters Q11 newsroom-AI assessment in
`summary.executive_summary[claim_index=3]`. The retained audit records:

* `before_sha256=03d02224dae7e1b1c9242a182756d5bc53557ba157daa8258cbd53eaf313a4f9`;
  `after_sha256=19518b0bac86105764638a295d5d41ef680f6f043bfa2a1e2a14b533645ebc3c`;
* executed action/strategy `REGENERATE_ITEM` / `current_evidence`, with the
  exact claim-only replacement recorded in the audit and evidence ID
  `verified-fact:newsroom-ai-initiative-assessments`;
* semantic grounding **evaluated**, mutation scope **pass**, evidence lineage
  **pass**, zero introduced hard failures, candidate promotion **promoted**,
  validation **pass**, and publish-readiness **pass**;
* the authoritative claim-map row remained bound to the same canonical fact,
  source identity, and physical page 33. The final HTML contains the repaired
  Q11 sentence and no visible internal evidence identifiers.

The original PDF was independently rehashed as
`f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52`. Text
extraction from physical page 33 states Q11's base is 265 and reports 44%
promising, 42% limited, 13% transformational, and 2% disappointing. This
matches the canonical fact's observed (not forecast) status and the promoted
editorial wording. The exact pre-repair sentence is not retained in the
available candidate artifact; the audit's differing input/output hashes and
minimal patch are the available proof of change.

##### Current-SHA live limitation and verdict

No provider-backed report was rerun from the current uncommitted tree in this
turn, and no publication or WordPress write occurred. The focused regressions
demonstrate the new failure paths; the retained Reuters run demonstrates one
real repair/promotion, but does not establish that the new rollback and action
semantics were exercised live. The exact-five run at `3342d676` remains 3/5
ready (KPMG visual-authority coverage failure and the original Algolia proposal
compatibility failure); the corrected Algolia replay remains the only later
single-report live replay. A fresh current-SHA Reuters/KPMG repair replay and a
fresh corrected five-report cohort remain open.

**Verdict: PARTIAL / NO-GO for Step 3.** The requested transactional root causes
are corrected and regression-tested, and one genuine retained repair is
source-grounded, fully validated, promoted, and independently checked. Current-
SHA live causal acceptance and broader repair effectiveness remain unverified;
Step 3 remains unstarted.

#### Transactional claim-repair hosted-CI follow-up — 2026-10-30 (post-`92647785`)

The first hosted run for the implementation commit was `41111279717`. Both
mutation partitions and the CI start job passed. The test job exposed four
concrete issues: the audit schema rejected valid empty `ABSTAIN` records, the
IAS multi-claim lineage fixture still described safe removal as abstention, the
existing expert-comment visual repair lacked a usable source binding, and one
split test module exceeded the repository ownership limit. `release_evidence`
failed only because the test job was its prerequisite. No production or
publication side effect occurred.

The corrective changes are deliberately bounded:

* `regeneration_candidate_audit.schema.json` now expresses the existing action
  contract: `ABSTAIN` has no changed paths or patch, `REMOVE_CLAIM` has an
  executed changed path and no patch, and replacement actions require both.
  This does not make an abstention a successful repair or authorize deletion.
* The lineage fixture now returns an explicit `remove` proposal for the
  isolated safe-removal case. The production handler continues to preserve a
  claim for an explicit abstain, invalid replacement, or unavailable support
  unless the deterministic planner has selected its existing authorized
  safe-removal strategy.
* Verified-mode soft-copy normalization now maps a discovery-era evidence ID
  to a canonical verified-fact evidence ID only when the mapping is uniquely
  established by the retained fact snapshot. Issue evidence IDs are included
  in claim-scoped repair packages, so valid planner bindings are not lost.
* Empty-support preflight now uses the same claim-scoped evidence builder as
  the handler. Mixed soft-copy targets are partitioned by stable claim ID:
  supported siblings keep the existing repair route, while unsupported claims
  take an explicit safe-removal target. Supported repairs execute before the
  removal target so sentence indexes cannot shift underneath an active repair.
  Ambiguous claim IDs or duplicate sentence identities are left unresolved
  rather than guessed. No additional model call or validation stage is added.
* The response now de-duplicates repeated family names when one family has
  multiple claim-scoped targets. The moved test case keeps the ownership gate
  green without changing its assertions.

Current local verification after these corrections:

| Check | Result |
| --- | --- |
| Frozen-lineage disposition regression | **3 passed** |
| Visual-authority regeneration regression | **4 passed** |
| Report-regeneration generator suite | **97 passed** |
| Combined affected repair/validation/evidence suites | **222 passed** |
| Contract-schema snapshot, Ruff, formatting, forbidden-patching, role-I/O and diff gates | **passed** |
| Full-repository mypy | **0 tracked errors across 786 source files** |

The IAS multi-claim fixture now proves the corrected action split: the two
source-independent analytical recommendations remain, unsupported factual
claims are not silently deleted, and the explicit safe-removal decision is
recorded. The visual expert regression also confirms that canonical evidence
and issue-level bindings reach the existing claim repair path. These are
provider-free regression results; they are not a live-quality claim.

The retained Reuters Q11 repair remains the only available genuine real-report
repair/promotion trace. Its producer SHA is
`3342d6764835f9b9a05eccc96cca11c45608f8bc`; it predates both this correction
and the current final commit, so it proves integration compatibility but not
causal current-SHA behavior. No fresh provider-backed Reuters/KPMG replay was
available in this correction, and no publication or WordPress write occurred.

**Verdict: PARTIAL / NO-GO for Step 3.** The hosted failures have targeted local
corrections and the affected regression suites are green, but a new hosted run
for the corrective commit and current-SHA live repair evidence remain required.
Step 3 remains unstarted.

##### Corrective hosted run — 2026-10-30

Commit `5bf15d69471eb6a6592a4f046b9381b0a8001a8d` was pushed to
`codex/fix-retained-insight-evidence-validation`. Hosted CI run
`41115544716` completed successfully: `ci_start`, `tests`, both mutation
partitions, and `release_evidence` all passed. This closes the CI defects
identified by run `41111279717`; it does not constitute a fresh provider-backed
real-report replay. The retained Reuters repair trace remains pre-correction,
so the Step 3 verdict stays **PARTIAL / NO-GO** pending current-SHA live repair
evidence.

#### Current-SHA Reuters transactional-repair replay — 2026-10-30 (`b579f8e0`)

The targeted implementation is now recorded at commits
`34643c4fafb82dc7bf11b37d19469651c57ddcec` and
`b579f8e01a1cf14c68ca732cc52e25805bc54d00`. The production changes remain
inside the existing claim-validation, regeneration, and candidate-audit
boundaries: material numeric, quoted, causal, comparative, or evidence-bound
recommendations can no longer bypass factual validation merely because their
editorial voice is `interpretive` or `recommendation`; the same source-derived
soft-copy obligations apply during candidate lineage validation; and, when
execution decisions exist, the audit reports their actual evidence IDs rather
than planner-intended evidence for explicit `ABSTAIN`/`REMOVE` outcomes. No new
validator, provider stage, database, service, or publication behavior was
added.

The focused regressions cover inherited classification with a material
qualitative premise, invalid repair lineage, explicit abstain/remove audit
semantics, multi-decision evidence attribution, and exact-hash restart
re-entry. The restart test confirms that replacing an artifact while retaining
a stale candidate package makes that package non-reusable. The affected suite
passed 239 tests; changed-file Ruff and formatting passed; full-repository
mypy remained at zero tracked errors across 786 source files.

##### Live run and source identity

One isolated provider-backed Reuters replay was executed at producer SHA
`b579f8e01a1cf14c68ca732cc52e25805bc54d00`. It used the frozen
`Trends_and_Predictions_2026.pdf`, MD5 `4b763ae2286ca69fe8acb63b17508dfb`,
and SHA-256
`f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52`.
The run directory is
`C:\\ml-transactional-repair-final-20261030\\frozen-reliability-y8yeqf5t\\members\\cohort-4b763ae2286ca69fe8ac\\ias-first-attempt-7fh1j02r`.
The verified-facts source identity is
`source:79cb8c886c55b49bfdec2128d5b25e0b|pdf-sha256:f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52`.

The runner loaded credentials from the existing parent `.env` in-process;
secrets were not copied into the worktree or logs. The unrelated dirty
`Wordpress/dist/marketlense.zip` was temporarily stashed only to satisfy the
runner's clean-SHA precondition and then restored unchanged; it was not staged.

| Measure | Result |
| --- | --- |
| Workflow terminal | **PASS**; `final_state=awaiting_review` |
| Visual facts | 7 evaluated, 7 admitted, 0 quarantined; coverage complete |
| Final insights | 7; stable IDs match the admitted verified facts |
| Validation / readiness | `pass` / `pass` |
| Unsupported / unresolved retained factual claims | 0 / 0 |
| Provider / file-search calls | 51 / 8 |
| Input / output tokens | 699,972 / 147,182 |
| Estimated cost / wall-clock | `$0.162183` / `913.574s` |
| Structured-output / automatic transactional repairs | 1 / 0 |
| Workflow retries / operator intervention | 0 / 0 |
| Publication / WordPress writes | 0 / 0 |

The validation-reuse ledger recorded one event with `prior_package_missing`,
39 newly validated claims, and zero reused validation results or avoided
grounding calls. The structured-output repair was not a transactional claim
repair.

##### Editorial and PDF review

All seven final insight identities, protected metrics, evidence IDs, and
physical pages were inspected against the original PDF and rendered HTML:

| Stable ID | Physical page | Source-supported final claim |
| --- | ---: | --- |
| `search-traffic-outlook` | 12 | Q5 average expected search-traffic change −43% over the next three years, base 268; expectation, not observed traffic. |
| `social-referral-declines` | 20 | Chartbeat referrals to news websites declined 43% from Facebook and 46% from X over the last two and a half years. |
| `content-effort-divergence` | 17 | Q13 net difference +91 for original investigations/on-the-ground reporting and −42 for service journalism, base 264. |
| `creator-concern-comparison` | 24 | Q19 concern was 70% for creators taking time/attention and 39% for losing talent, base 263. |
| `newsroom-ai-assessments` | 33 | Q11 impact adjectives were 44% promising, 42% limited, 13% transformational, and 2% disappointing, base 265. |
| `ai-newsroom-backend` | 32 | 64% rated back-end automation very important for 2026, base 266; expected importance, not realized use. |
| `paid-content-revenue-priority` | 38 | 76% of commercial-publisher respondents expected subscription/membership to be important or very important in 2026, base 259, excluding publicly funded broadcasters. |

Rendered source-page inspection confirmed the Q5 slider/base, Q11 chart/base,
and Q16 revenue-stream chart/base; text extraction and retained evidence
spans covered the other five rows. Final `so_what` wording retained bounded
interpretation without changing protected facts. The final HTML was non-empty,
contained all seven material insight values, and had zero matches for
`verified-fact:`, `evidence_id`, `claim_id`, `physical_page`, `source:page`, or
`provenance_hash`. Public-editorial-quality and publication-readiness artifacts
passed with zero issues/hard fails.

The retained claim-validation artifact contains 39 records and 35 semantic
validation records, with zero unsupported and zero unresolved material factual
counts. Four non-factual soft-copy records remain deterministically
`unresolved` under the existing policy; this did not block the existing gate
and is recorded rather than reclassified.

##### Repair disposition and limitations

No failed claim, unique repair target, provider replacement, promotion, or
rollback was needed in this run. The required terminal interpretation is:

**LIVE WORKFLOW PASS — TRANSACTIONAL REPAIR NOT EXERCISED**

This demonstrates current-SHA workflow integrity, source binding, final
editorial preservation, and no-publication behavior, but not live repair
success or rollback under provider failure. The initial attempt was blocked
before provider dispatch by the dirty ZIP and the runner's clean-SHA
precondition; the isolated retry after preserving that file completed
normally. No live provider failure was hidden or converted into a success.

**Verdict: PASS for the targeted implementation and Reuters workflow replay;
PARTIAL / NO-GO for overall Step 3 readiness.** Transactional repair remains
unexercised live, broader repair effectiveness and independent human editorial
acceptance remain open, and no canonical claim promotion or WordPress
publication occurred.

#### Hosted regression correction — 2026-10-30 (`0d97c913`)

The first hosted run after the documentation/live-replay commit exposed four
existing-suite regressions at the new effective-factual boundary: an unchanged
interpretive sibling carried an evidence ID but no persisted source-span
metadata, and the added identity regressions pushed one split test module over
the repository's 1,000-line ownership threshold. Mutation partitions and all
static gates were already green. The production correction is narrow:
semantic/evidence validation still applies to material evidence-bound content,
but missing source-span metadata is tolerated only for an unchanged
interpretive/recommendation representation; source spans supplied for it are
still checked. Factual claims, new claims, and any claim with repair lineage
remain strict and fail closed when canonical spans are absent. The three
identity tests were moved to a new existing-facade split module; no assertion
or production identity behavior changed.

The exact focused repair/validation command then passed **379 tests in
54.14s**. Changed-file Ruff and formatting, architecture-import, role-I/O,
forbidden-patching, contract-schema, and full-repository mypy gates passed.
The follow-up hosted run was `41126623405` at `0d97c913`:

* `tests`: **8,286 passed, 1 skipped**;
* `mutation (0)`, `mutation (1)`, and `release_evidence`: **passed**;
* no provider calls, canonical artifact mutation, publication, or WordPress
  write were introduced by the correction.

This closes the demonstrated CI compatibility defect without weakening the
material repaired-claim guard. The live Reuters producer remains
`b579f8e0`; this hosted result does not change the live disposition:

**LIVE WORKFLOW PASS — TRANSACTIONAL REPAIR NOT EXERCISED**

The overall status remains **PARTIAL / NO-GO for Step 3** because a current-SHA
provider-backed failed-claim replacement and broader repair-effectiveness
evidence were not available. No additional live replay was run merely to seek
a repair failure.

#### Final transactional-repair hardening — 2026-10-31 (`24c889ad`)

The final repair hardening is committed as `d072f81f` with the test-ownership
and formatting corrections in `7d22c656` and `24c889ad`. The changes are
limited to existing validation, regeneration, planner, audit, and regression
boundaries:

| Boundary | Correction | Safety result |
| --- | --- | --- |
| Soft-copy factual eligibility | Evidence-bound source-derived premises remain in semantic grounding; standalone normative recommendations remain editorial/non-factual. Validator identity advanced to `retained_claim_validation:v9`. | Existing factual gates remain active; no evidence-free recommendation is promoted as a fact. |
| Provider repair proposals | Known invalid evidence, action, path, and patch proposals become recorded `ABSTAIN` decisions and advance the bounded strategy ladder. Unknown/structural `AppError` failures still propagate typed. | No rejected provider patch mutates the target; safe removal remains deterministic. |
| Removal authority | Model `remove` is accepted only when the planner selected `REMOVE_CLAIM`; `REGENERATE_ITEM` and `REBIND_EVIDENCE` cannot delete claims. | Unsupported model deletion is rejected and later explicit safe removal can run. |
| Retry/audit identity | Stable target strategy keys prevent a split target from repeating a rejected strategy; executed decision action, strategy, and evidence IDs are authoritative in audit and `RepairDelta`. | Planner metadata cannot masquerade as executed evidence or reset the bounded ladder. |
| Source-span guard | New material/repaired factual claims require a meaningful source location; equivalent page-only/complete spans remain compatible. | Evidence-ID-only factual provenance fails closed. |

Focused verification at the final SHA passed **467 tests**. Changed-source
targeted mypy passed for all six production modules; the changed-file Ruff and
Ruff-format checks passed. The full local parallel suite at the preceding
implementation state recorded **8,291 passed, 2 skipped, 2 failures**: the
long-test-file ownership failure was corrected and its final targeted gate
passed; the remaining failure is the existing CPython 3.14 wheelhouse guard,
which requires CPython 3.12 and is unrelated to this slice.

The exact frozen E13 manifests were copied from retained local artifacts and
their **90 input-file hashes** matched the manifests. At final SHA
`24c889ad9b50246b3e77c3069d765544fbec5be6`, all three manifest replays
(A21 five-case, Mobile editorial, and DoubleVerify public-editorial) stopped
in existing preflight before model-client construction. Each retained figure
asset lacks fields required by the current `ReportFigureAsset` contract, so
the runner returned `ValueError: ... figure asset 0 payload fields are
incomplete`; provider calls, repair attempts, scorecards, and replay artifacts
were **0/unavailable**. No legacy payload was edited or padded. This is a
frozen-corpus compatibility limitation, not a repair-quality result.

The prior isolated provider-backed Reuters workflow remains the only retained
real-report repair-adjacent run and ended exactly as:

**LIVE WORKFLOW PASS — TRANSACTIONAL REPAIR NOT EXERCISED**

The focused regressions demonstrate provider rejection/strategy advancement,
explicit removal authority, audit provenance, and rollback safety, but no
current-SHA provider failure produced a genuine replacement-and-promotion
repair. No canonical artifact, readiness state, publication, or WordPress
write was changed.

**Verdict: PASS for the targeted transactional-repair safeguards and focused
regressions; PARTIAL / NO-GO for live repair effectiveness and Step 3
readiness.**

#### Semantic-authority migration — 2026-10-31 (implementation based on `e7f4fd1a`)

This slice applies the GPT-6 semantic-authority decision across active
production paths. Existing LLM stages now own material factuality, entailment,
interpretation, recommendation quality, public-editorial quality, report
qualification, category fit, visual significance, and cross-report semantic
agreement. Deterministic code remains responsible for source identity,
physical-page and evidence-ID integrity, schema/coverage, immutable verified
facts, exact arithmetic, orchestration, retries, cache identity, and
publication transactions. Retrieval heuristics remain ordering/recall aids;
they no longer certify or veto semantic content before the relevant model
stage. Repair evidence remains bounded to source-authorized identities and is
independently grounded before promotion.

The grounding contract was advanced to
`retained_claim_validation:v10` / `grounding_validation_output:2.0`, with
complete canonical verified facts and evidence available to the existing
grounding call. The public-editorial release boundary now uses the existing
structured-output/recovery/reuse path for an independent semantic review;
technical HTML, identity, asset, schema, and source-integrity checks remain
deterministic and unwaivable. The grounding user prompt no longer duplicates
the system-side authority policy. A valid rejected factual item is represented
by a consistent non-entailed `checks` record plus its matching `unsupported`
disposition; mismatched or incomplete pairs fail closed.

The three-iteration prompt fixture baseline was regenerated with repository
tooling. The prior baseline was 111,573 total tokens / `$0.024659` across 50
fixtures; the new baseline is 113,206 / `$0.024974` across 51 fixtures. The
validation family is 9,640 → 10,921 tokens and `$0.001725` → `$0.002005`;
the increase is 35 tokens from complete grounding instructions plus 1,246
tokens for the new independent public-editorial review. Report is 22,875 →
23,144 tokens (`$0.008573` → `$0.008600`), from the category-fit authority
context; cross-report is 2,385 → 2,468 (`$0.000599` → `$0.000607`). Publishing,
browser, ranking, and crop families are unchanged. The fixture gate passed
with zero deltas against the regenerated baseline; thresholds and pricing were
not changed.

Focused verification passed:

* 83 semantic-authority, prompt, cross-report, and signal tests;
* 16 canonical verified-grounding, multi-fact, and fabricated-number tests;
* full-repository mypy baseline: 0 tracked errors across 786 source files;
* changed-file Ruff, Python compilation, diff checks, and the prompt-fixture
  gate.

The exact Step 0 reference replay is recorded at
`out/verified-claims-step2-semantic-authority-replay-20261031.json`. It covers
all 15 cases and 39 variants across Capgemini, Activate, KPMG, Reuters
Institute, and Adjust, with no fabricated fixture substitution. It was
provider-free: the active worktree has no retained frozen-five artifacts or
source PDFs at the manifest paths, so all 39 visual assessments were skipped,
the five retained-report selections were unavailable, and provider calls,
tokens, cost, latency, and live quality outcomes are null/zero. The parent
worktree contains `.env`, but credentials alone do not establish a valid
current-SHA real-report replay. This run therefore proves input/reference
coverage only and does not claim improved live semantic quality.

The broader legacy grounding/public-editorial suites still contain assertions
that intentionally require the removed deterministic semantic authority (for
example lexical quote support, numeric pre-support, and deterministic metric
mismatch findings). They are recorded as migration debt rather than restored
through heuristic compatibility. The targeted contract suite is green; the
full local Ruff invocation still reports the repository's pre-existing debt
outside the changed-file gate. No provider, canonical artifact, publication,
or WordPress write was performed.

**Verdict: PASS for the implemented semantic-authority boundaries and local
contract/static gates; PARTIAL for real-report effectiveness. Step 3 remains
unstarted/not ready until a current-SHA provider-backed retained-report replay
with available source PDFs and artifacts is completed.**

#### Final semantic-authority five-fix reconciliation — 2026-10-31 (`2e503304`)

This follow-up closes the five root causes identified in the preceding
semantic-authority review. The earlier migration-debt paragraph above describes
the `e7f4fd1a` implementation state; the affected local regression suites are
reconciled here rather than restored to deterministic semantic acceptance.

| Issue | Root cause | Targeted correction | Evidence |
| --- | --- | --- | --- |
| Contradictory grounding verdict | An `entailed` result could still carry incompatible protected dimensions or a non-compatible proposition status. | `_apply_semantic_results()` now accepts an entailed result only when the model's protected-fact comparison is complete and internally compatible; otherwise it is unresolved/fail-closed. The grounding validator identity advanced to `grounding_validation_output:2.1`. | `tests/test_semantic_authority_contract.py` covers compatible, incompatible value/population/timeframe, contradicted, not-established, and incomplete verdicts. |
| Final editorial authority | The final independent review was persisted but its disposition was not merged into the validation report consumed by readiness. | Final review is merged with replacement of stale `public_editorial_quality.*` issues, and the authoritative `validation` snapshot is rewritten for the final artifact. Reusable unchanged reviews remain eligible through the existing identity path. | Semantic-authority and public-editorial/readiness regressions pass; structural blockers remain preserved. |
| Source-backed key figures | Numeric-text matching could discard a canonical metric before grounding/editorial review. | `_select_key_figure_metrics()` now performs only structured binding, metric-ID, display-field, and stable-cap checks; semantic numeric/category interpretation remains downstream. | `tests/test_key_figure_selection.py` covers alternate display formatting, qualifiers, missing prose matches, unresolved metrics, and invalid bindings. |
| Visual pre-review cap | Feature-ranked overflow candidates were omitted before multimodal assessment. | Technical candidates are retained and sent through existing bounded ranking batches; rank coverage is logged as complete or `incomplete_unassessed`. Model-rejected rows are not resurrected by fallback. | Candidate prefilter, batching, overflow, fallback-rejection, and coverage regressions pass. |
| Cross-report evidence cap | Source/order truncation could make one report consume the semantic-synthesis budget and hide other reports. | The existing total budget now uses stable round-robin report diversity and records `unassessed_overflow` plus `coverage_status`; retrieval remains ordering telemetry only. | Cross-report assembly/signal regressions cover overflow, diversity, provenance, and incomplete coverage. |

The affected focused command completed with **428 passed, 7 deselected in
13.60s**. Changed-file Ruff and formatting passed; full-repository mypy passed
with **0 tracked errors across 786 source files**; and the prompt-fixture gate
passed. The prompt corpus was not changed by this slice: current and baseline
totals remain **113,206 tokens / `$0.024974`**, including validation
**10,921 tokens / `$0.002005`**, with zero token or cost delta. No prompt
compression, threshold, pricing, schema-output, or retry weakening was used.

Provider-free replay remains limited to the retained reference artifact
`out/verified-claims-step2-semantic-authority-replay-20261031.json` (15 cases,
39 variants). The worktree has no retained frozen-five source PDFs/artifacts
at the required live input paths; therefore no current-SHA Capgemini, Activate,
KPMG, Reuters Institute, Adjust, DoubleVerify, Criteo, or Algolia real-report
run was performed, and there are no live calls, tokens, cost, latency,
candidate-recall, or editorial-quality measurements to report for this slice.
No canonical artifact, publication state, or WordPress write changed.

**Verdict: PASS for the five deterministic semantic-authority boundaries,
focused regressions, static gates, and cache/contract invalidation; PARTIAL for
real-report effectiveness and editorial-quality acceptance. Step 3 remains
unstarted/not ready until source-backed current-SHA replay is available.**

The canonical full local gate was also attempted. Its unit stage reached the
entire 8,311-test selection and stopped with **7,838 passed, 2 skipped, 471
failures, and 39 deselected**; later coverage/mutation/quality-regression
stages were therefore not run by the gate. A clean `4120f981` worktree
reproduced the representative quotation, validation, public-editorial,
category-fit, and legacy artifact assertions that still encode the earlier
deterministic semantic contract, so those failures predate this five-fix diff
and are not claimed as resolved here. The current-only long-test-file failure
caused by the migrated test additions was split and its ownership gate now
passes. The remaining isolated wheelhouse failure is the existing CPython
3.14-versus-3.12 environment guard. This is a release limitation, not a
quality pass: hosted CI must still confirm the branch's complete test state.

#### Hosted CI terminal result — 2026-10-31 (`2e503304`, run `41216218560`)

The hosted policy, architecture, formatting, Ruff, type, documentation,
backlog, schema, and WordPress-subproject checks completed successfully; the
WordPress staging REST check was skipped by its existing guard. Mutation
partition 1 passed. Mutation partition 0 failed before mutation because its
unmutated target suite did not pass for
`src/generators/_artifact_generator/generation.py`; no mutation result was
produced. The hosted default suite completed with **7,841 passed, 469 failed,
and 1 skipped in 480.73s**. Its failures are the same legacy semantic-
migration, regeneration, category-fit, publisher-inventory, artifact, and
PDF-heuristic families reproduced from the clean pre-slice worktree, rather
than a focused failure in the five semantic-authority boundaries. Coverage and
later release-gate steps did not run after the unit-stage failure. The
`release_evidence` prerequisite check correctly failed because the `tests` and
`mutation` jobs were non-success; no release bundle, canonical artifact, or
WordPress write was created. Hosted run URL:
`https://github.com/mbrakker/marketlense/actions/runs/41216218560`.

## Semantic-authority migration and local CI reconciliation — 2026-11-01

### Scope and production changes

The current implementation slice applies the semantic-authority decision at the
existing generation and validation boundaries. LLM stages own material
factuality, entailment, interpretations, recommendations, public-editorial
quality, report qualification, category fit, visual significance, and
cross-report semantic agreement. Deterministic code remains responsible for
source identity, physical PDF pages and evidence IDs, schema/coverage,
immutable verified facts, exact arithmetic, cache identity, bounded retries,
orchestration, and publication transactions.

The production corrections are narrow:

- grounding, claim validation, public-editorial review, and regeneration now
  preserve model decisions and fail closed only on malformed, incomplete,
  contradictory, or structurally unbound results;
- evidence-pack and key-figure paths preserve source-bound facts without
  numeric-text or keyword semantic vetoes;
- publisher/download and taxonomy paths retain semantic model output while
  exposing technical qualification signals as telemetry;
- the visual extractor rejects only the demonstrated oversized embedded-wrapper
  geometry, while ambiguous/low-confidence candidates remain available for the
  existing multimodal review path;
- cache/reuse, stable IDs, source provenance, safe removal, readiness, and
  publication guards remain unchanged and are covered by the migrated tests.

No new LLM stage, validator, service, database, publication path, or WordPress
write was introduced.

### Local verification matrix

| Gate | Result |
| --- | --- |
| CPython 3.12 default suite | **8,311 passed, 2 skipped, 39 deselected; 24 subtests** |
| Coverage | **85.1591% global; 85.1995% generators; 86.2372% orchestrators; 84.6411% services**; configured floors pass |
| Mutation | **65/65 killed** across 16 configured targets |
| Full mypy | **0 tracked errors** across 786 source files |
| Formatting / changed-file Ruff | Pass |
| Architecture, role/I/O, policy, schema, documentation, ledger, runbooks, backlog, hygiene | Pass |
| WordPress subproject / public-site quality | Pass; credential-gated staging REST remains guarded/skipped |
| Prompt fixture comparator | Pass after baseline regeneration |
| Retained quality comparator | **Fail**: generators 85.1995% < historical 87.1763% |

The full default suite was also run under CPython 3.14 before the environment
correction; its only failure was the existing CPython 3.12 wheelhouse guard.
The authoritative run used installed CPython 3.12 and passed the full suite.
Background-thread logging teardown emitted the existing closed-stream warning
without failing tests.

### Prompt baseline evidence

The existing prompt-baseline tooling regenerated
`docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json`. The stable
before/after values are:

| Scope | Previous | Current | Change |
| --- | ---: | ---: | ---: |
| Total tokens | 113,206 | 113,387 | +181 (+0.16%) |
| Estimated cost | $0.024974 | $0.024992 | +$0.000018 (+0.07%) |
| Validation tokens | 10,921 | 11,102 | +181 (+1.66%) |
| Validation cost | $0.002005 | $0.002023 | +$0.000018 (+0.90%) |
| Public-editorial input tokens | 866 | 1,047 | +181 |

The delta is the intentional source-authority, protected-dimension, and
missing-evidence guidance. Pricing, model selection, schemas, fixture set,
retry budgets, and comparator thresholds were unchanged. The prompt gate passed;
runtime remained host-variable but within the existing comparator tolerance.

### Release and live-report limitations

The retained historical quality comparator was not weakened: the current
generator coverage of **85.1995%** is below the retained **87.1763%** baseline.
This is the remaining local release blocker and keeps R3 active. The current
worktree does not contain the retained frozen-five source PDFs/artifacts at the
required live paths, so a provider-backed verified-mode editorial regression
could not be run. No live provider calls, fresh source-page inspection,
provider-token/cost/latency measurements, canonical mutation, publication, or
WordPress write occurred in this slice. The provider-free reference replay is
not a substitute for current-SHA editorial-quality evidence.

**Verdict: PARTIAL / NO-GO for release promotion.** The semantic-authority
implementation, full unit suite, coverage floors, mutation, prompt, static,
schema, and policy checks pass. The retained generator non-regression gate and
current-SHA real-report evidence remain unresolved; Step 3 must not begin.

### PDF candidate benchmark reconciliation — 2026-11-01

Hosted mutation partition 0 exposed an expected benchmark mismatch caused by
the visual-recall correction in this slice. The extractor now retains
technically valid ambiguous/overflow candidates for the existing multimodal
review batches; it rejects only the demonstrated oversized embedded-wrapper
geometry. The source PDF hashes were unchanged, and the repository benchmark
tool regenerated the committed roster/signature baseline:

| Fixture | Previous count | Current count | PDF SHA unchanged |
| --- | ---: | ---: | --- |
| Capgemini | 12 | 28 | Yes |
| IAS | 13 | 86 | Yes |
| Julius Baer | 13 | 20 | Yes |
| Global Food & Drink | 0 | 3 | Yes |

The refreshed signatures are the observed deterministic outputs from the same
PDFs, not fabricated counts or threshold exemptions. A clean local recheck
against the refreshed baseline passed all four rows with zero warnings, zero
degraded pages, matching counts/signatures, and no runtime failure. This is a
candidate-recall/visual-review compatibility update; it does not establish
semantic admission or live editorial quality.

### Hosted CI terminal result — 2026-11-01 (`10906a99`, run `41282490348`)

The fixture correction following the first refreshed-baseline run derives the
warning and failure test observations from the authoritative current Global
Food baseline, so the tests continue to exercise the existing 25% warning and
75% failure thresholds after a legitimate baseline refresh. The focused
release-evidence tests passed **61/61**; formatting, Ruff, and `git diff
--check` passed.

On the pushed SHA, hosted `tests` passed **8,312 tests with 1 skipped in
461.98s**, including all static/policy/schema/documentation checks and coverage
floor validation; the credential-gated WordPress staging REST check remained
skipped by its existing guard. Mutation partitions 0 and 1 passed, and the
refreshed PDF candidate benchmark passed. The release-evidence job then failed
only at the retained historical quality comparator:

| Quality slice | Current | Retained baseline | Result |
| --- | ---: | ---: | --- |
| Global coverage | 85.1049% | 83.3816% | Pass |
| `src/generators` coverage | 85.1995% | 87.1763% | **Fail** |
| `src/orchestrators` coverage | 86.2439% | 84.8022% | Pass |
| `src/services` coverage | 84.5030% | 82.5763% | Pass |

All mutation targets, docpack metrics, and candidate-extraction metrics passed
the comparator. The historical generator baseline was not lowered or
regenerated to manufacture a release pass; R3 remains active. The release job
therefore correctly stopped before later release-evidence stages. No provider
calls, current-SHA retained-report run, canonical mutation, publication, or
WordPress write occurred. Hosted run:
`https://github.com/mbrakker/marketlense/actions/runs/41282490348`.

**Updated verdict: PARTIAL / NO-GO.** Semantic-authority tests and hosted
pre-release gates are green, but the retained generator non-regression gate and
current-SHA real-report evidence remain open; Step 3 must not begin.

## Pre-E2E P0/P1 closure and release-gate recheck — 2026-11-01

This section records the provider-free correction pass based on reviewed HEAD
`81bd56fb`. It does not claim a current-SHA real-report or live-provider
acceptance result.

### Root-cause corrections and observed evidence

| Defect | Earliest correction | Observed behavior | Evidence |
| --- | --- | --- | --- |
| Verified authority could be absent or stale at the final render/readiness boundary. | `report_render_generator.py` now rebuilds and compares the canonical `VerifiedAuthorityContext` against source identity, digest, facts, evidence packs, artifact bindings, and serialized projections before render/readiness side effects. | Missing authority, invalid snapshot, stale context, stale packs, and serialized projection mismatches fail with nonretryable structural errors; normal mode continues through its existing path. | `tests/test_pre_e2e_integrity.py` boundary tests; existing checkpoint/reentry authority tests. |
| Explicit public-editorial `evidence_ids=[]` inherited the original item IDs. | `_public_editorial_review_issue()` now distinguishes `None` (unspecified) from `[]` (explicitly unavailable); reason validation is structural nonempty text. | Missing-evidence outcomes remain unbound and non-repairable; a short but nonempty reason is accepted structurally. | Targeted attribution and reason tests in `tests/test_pre_e2e_integrity.py`. |
| Independent editorial review lacked report-level materiality context. | The existing public-editorial review call now receives the plan, final public surfaces, complete canonical facts once, evidence context, source identity and digest; schema/validator/cache identities advanced to the current report-review contract. | Complete report verdicts are required in production verified mode; unsafe, incomplete, unlocalized, or mismatched verdicts fail closed, while precisely targeted failures retain existing scoped repair. | Report-scope, dimension, target, and controlled-review regressions in `tests/test_pre_e2e_integrity.py`; existing validation/regeneration suites. |
| Historical generator comparator failed after semantic-ownership cleanup. | Removed only the unreachable duplicate verified-metric heuristic after repository-wide caller/compatibility inspection; retained technical identity/provenance checks and added behavior-backed tests for public surfaces, metadata, metric relationships, and fail-closed authority. | No threshold, baseline, exclusion, or semantic-quality gate was changed; the fresh full-suite generator comparator passes. | Fresh full suite, coverage comparator, and mutation partitions below. |

Structural quarantine, transactional repair, safe removal, retained-claim
validation, cache invalidation, and publication-readiness protections were not
weakened. No additional LLM stage, service, validator, database, provider call,
canonical artifact mutation, publication, or WordPress write was introduced by
this correction pass.

### Before/after release measurements

| Slice | Hosted failing baseline (`10906a99`, run `41282490348`) | Fresh local corrected tree | Retained comparator | Result |
| --- | ---: | ---: | ---: | --- |
| Global | 85.1049% | 85.6226% | 83.3816% | Pass |
| `src/generators` | 85.1995% | **87.2055%** | **87.1763%** | **Pass** |
| `src/orchestrators` | 86.2439% | 86.1626% | 84.8022% | Pass |
| `src/services` | 84.5030% | 84.6387% | 82.5763% | Pass |

The fresh CPython 3.12 default run passed **8,339 tests, 2 skipped, 39
deselected, and 24 subtests in 1,461.18 seconds (24:21)**. The configured
coverage floors and unchanged quality comparator passed. Local mutation
partition 0 passed with **32/33** mutants killed (the one taxonomy survivor
remains at the retained 75% target); partition 1 passed with **35/35** killed.
The prompt, contract-schema, documentation-reference, Ruff, and full mypy
gates passed; mypy reported **0 tracked errors across 786 source files**.

The prompt fixture baseline was regenerated through the existing tool. The
current approved configuration is **113,935 tokens / `$0.025046`**, versus the
prior committed **113,387 / `$0.024992`**: **+548 tokens / +$0.000054**. The
validation family is **11,650 / `$0.002077`**, versus **11,102 / `$0.002023`**:
**+548 tokens / +$0.000054**. The affected public-editorial namespace is
**1,595 / `$0.000349`**, versus **1,047 / `$0.000295`**. The unchanged fixture
thresholds, pricing, model configuration, schemas, and factual checks were
preserved; the regression gate passes exactly against the regenerated baseline.

The full suite emitted two existing threaded logging-teardown messages about a
closed stream during crop-refine tests; they did not fail or alter test results.

### Scope and remaining acceptance

This pass intentionally did **not** run a real report, frozen-five/ten cohort,
live LLM/provider workflow, browser acquisition, or WordPress publication.
Therefore it establishes the code-fixable P0/P1 and release-gate evidence only;
it does not establish calibrated current-SHA editorial quality, transactional
repair effectiveness on source reports, or Step 2 live selection/grounding
improvement. Hosted CI confirmation is recorded in the addendum below.

**Pre-E2E verdict: PASS** for the implemented authority/attribution/editorial
contract corrections, fresh local full suite, static/schema/prompt/coverage/
mutation/quality gates, and provider-free regressions. **Overall Step 2 verdict:
PARTIAL / NO-GO** pending later source-backed acceptance. E18 remains
**Active/PARTIAL** and Step 3 remains
**unstarted/not ready**.

### Hosted confirmation — 2026-11-01

The code commit `6f5cf8e0609c5ce84eed88a674ce296be6d9ed01` passed hosted CI run
`41310882638`: `tests` passed in 7m53s, mutation partition 1 passed in 4m40s,
mutation partition 0 passed in 6m38s, and `release_evidence` passed in 1m14s.
The WordPress staging REST check was skipped by its existing credential guard;
no publication or provider-backed report run occurred. Hosted warnings were
limited to the runner's existing Ubuntu label and Node.js 20 action-deprecation
notices. This confirms the deterministic pre-E2E gates on the code commit; it
does not change the later source-backed Step 2 limitation.

**Hosted pre-E2E verdict: PASS.** The overall Step 2 verdict remains
**PARTIAL / NO-GO** for lack of fresh current-SHA source-report editorial
evidence. E18 remains **Active/PARTIAL** and Step 3 remains
**unstarted/not ready**.

## Final P0/P1 pre-E2E corrective implementation — 2026-11-01

This addendum records the follow-up from starting commit
`f73f307f081a1518a25b06515ebc66a242a49c95`. It is provider-free and does not
claim fresh report selection, visual verification, live editorial quality, or
publication readiness.

### Corrections and evidence

| Area | Minimal correction | Evidence |
| --- | --- | --- |
| Qualified source identity | Render/readiness now accepts either the exact qualified runtime identity or the exact base runtime identity only when the authority is exactly `base|pdf-sha256:<64 hex>`. Invalid qualifiers, loose prefix/suffix matches, mutable/file IDs, and mismatches fail closed before render side effects. Canonical authority is rebuilt against the qualified identity. | `tests/test_pre_e2e_integrity.py`; focused and full suites. |
| Verified-mode continuity | A trusted authority context or explicit verified workflow intent selects verified mode. Missing facts, digest, canary, packs, or authority context are structural failures; they cannot trigger generic legacy fallback or broad regeneration. Candidate repair, checkpoint resume, and report validation carry the same mode and authority. | `tests/test_pre_e2e_integrity.py`, existing checkpoint/reentry and regeneration suites. |
| Public editorial contract | `report_verdict` is now required at the public-review root, and the validator/cache contract advanced from `v18` to `v19`. Missing or malformed report-level verdicts fail before acceptance or cache reuse. | `tests/test_schema_validator.py`, public-editorial and validation suites. |
| Missing-evidence attribution | Explicit empty evidence remains `evidence_ids=[]`; `material_claim_evidence_missing` and `semantic_evidence_missing` survive normalization with their severity, hard-fail class, target, and nonrepairable semantics. | `tests/test_pre_e2e_integrity.py`, semantic-authority suite. |
| Report-level authority | Verified public review receives the qualified source identity, verified-fact digest, and complete canonical fact map through the existing review call. Invalid authority cannot fall back to retained evidence. | `tests/test_pre_e2e_integrity.py`, full validation/regeneration suites. |
| Prompt contract | Removed the duplicated malformed public-editorial authority paragraph. The existing authority policy remains the single source of instruction; no new prompt namespace, LLM stage, or schema relaxation was added. | Prompt fixture regeneration and regression gate. |

The protected unrelated `Wordpress/dist/marketlense.zip` modification remains
untouched. No provider call, PDF acquisition, canonical artifact mutation,
publication, or WordPress write was performed.

### Provider-free verification results

| Check | Result |
| --- | --- |
| Focused authority/schema/semantic/regeneration suite | **170 passed** in 8.73s |
| Prompt/editorial/render/regeneration suite | **464 passed** in 48.53s |
| Full CPython 3.12 suite | **8,344 passed, 2 skipped, 39 deselected, 24 subtests** in 1,461.19s |
| Coverage | **85.61%** overall; contracts 97.97%, orchestrators 86.09%, generators 87.21%, services 84.64%, control-plane 90.60%; all floors passed |
| Mypy | **0 tracked errors across 786 source files** |
| Mutation partition 0 | **32/33** killed; the retained taxonomy survivor remains within the existing 75% target |
| Mutation partition 1 | **35/35** killed |
| Quality comparator | **PASS**; all retained coverage, mutation, docpack, and candidate metrics passed |
| Contract schemas, Ruff, prompt/schema gates | **PASS** |

The regenerated prompt baseline was produced by the repository tooling, with
thresholds, pricing, model configuration, fixtures, schemas, and factual
checks unchanged:

| Namespace | Previous baseline | Current baseline | Change |
| --- | ---: | ---: | ---: |
| Total fixtures | 113,935 / `$0.025046` | 113,900 / `$0.025043` | −35 tokens / −$0.000003 |
| Validation family | 11,650 / `$0.002077` | 11,615 / `$0.002074` | −35 tokens / −$0.000003 |
| Public editorial quality | 1,595 / `$0.000349` | 1,560 / `$0.000346` | −35 tokens / −$0.000003 |

The fixture regression passes against the regenerated baseline. The apparent
decrease is solely the removed duplicate prompt text; no factual instruction
was compressed or removed.

### Verdict and remaining evidence

The deterministic P0/P1 correction slice is **PASS**: source identity,
verified-mode continuity, report-level schema/authority, attribution, cache
invalidation, and prompt integrity are covered by focused, full-suite, static,
coverage, mutation, and quality evidence. The complete report pipeline remains
**PARTIAL / NO-GO** for Step 2 promotion because this pass intentionally did
not execute the retained real-report/frozen-five workflow or obtain fresh live
editorial evidence. E18 remains **Active/PARTIAL** and Step 3 is
**unstarted/not ready**. Hosted CI on the pushed commit is still required.

## Authority and contract closure — 2026-11-01 (provider-free)

This addendum records the P0/P1 correction slice from parent `8ba0663a`. It
does not claim a fresh report, PDF, provider, or publication result.

### Producer-to-consumer authority matrix

| Producer | Contract / identity | Consumer | Enforced invariant | Regression evidence |
| --- | --- | --- | --- | --- |
| Public editorial review response | Complete item/report verdict schema, retained item evidence IDs, source identity and fact digest | Review validator and `ValidationReport` adapter | Pass cannot carry error/failure/repair fields; fail/unresolved must be blocking; failed/nonpublishable persisted reports cannot merge to warning-only PASS | `tests/test_authority_contract_regressions.py`, public-editorial/semantic-authority suites |
| Verified analysis artifacts | `VerifiedAuthorityContext`, canonical evidence packs, source identity, PDF SHA-256, fact digest | Analytics projection | Verified findings/metrics come only from canonical authority; complete metric objects and evidence spans remain available; legacy discovery/quotes cannot become authority | `tests/test_analytics_projection_foundation.py`, `tests/test_pre_e2e_integrity.py` |
| Projection write/read | Reports DB v32 additive lineage columns and report-scoped IDs | Cross-report source/evidence/metric selection | A successful write is not eligibility; verified selection requires source validation, exact identity, PDF hash, and fact digest; stale/legacy rows are diagnostic-only | `tests/integration/test_analytics_store_cross_report_reads.py`, cross-report input suite |
| Analysis/render checkpoints | Serialized authority/evidence packs plus current canary/runtime source identity | Checkpoint reentry and render | Reentry revalidates current canonical snapshot before render; no-canary saved verified state fails closed; normal mode is unchanged | `tests/test_authority_contract_regressions.py`, `tests/test_report_checkpoint_lineage_validation.py` |
| Runtime source identity | Exact base or exact qualified identity; SHA hex case may normalize | Verified checkpoint/projection/source eligibility | No opaque case-fold, prefix, suffix, or mutable-ID match can authorize a source | `test_verified_source_identity_runtime_matching_is_exact` and cross-report regressions |

### Provider-free verification

| Check | Result |
| --- | --- |
| Focused authority-contract regressions plus original pre-E2E module, migration, and long-file ownership gate | **47 passed** |
| Broader authority/analytics/cross-report/checkpoint/editorial regression suite | **158 passed**; integration analytics-store regression **8 passed** |
| Full CPython 3.12 default pytest | **8,360 passed, 2 skipped, 24 subtests** in **583.52s (9:43)** |
| Coverage gate | **PASS** — global 85.61%, contracts 97.98%, orchestrators 86.14%, generators 87.21%, services 84.60%, control-plane 90.60% |
| Configured formatting/Ruff gate | **PASS** |
| Full-repository mypy | **PASS** — 0 tracked errors across 786 source files |
| Contract schema snapshot | **PASS** after repository-tool regeneration for the v32/lineage fields |
| Prompt fixture corpus gate | **PASS** — 113,900 tokens / `$0.025043`, validation 11,615 / `$0.002074`; no prompt fixture or threshold was weakened in this slice |
| Architecture, role/I/O, service-boundary, policy, logging, hygiene, ledger, runbook, backlog, and documentation gates | **PASS** |

The full suite emitted the repository's existing closed-stream logging-teardown
message during crop-refine tests; it did not fail a test or change an outcome.

The mutation gate killed **67/68 mutants** across 17 targets. The one survivor
is the retained taxonomy mutant; its target remains at the existing **75%**
threshold. The quality regression comparator passed global, generator,
orchestrator, and service coverage, every retained mutation target, all golden
docpack metrics, and all candidate-extraction metrics. These are release-gate
results, not provider evidence.

### Confirmed versus untested claims

Confirmed by provider-free tests: public review contradictions fail closed;
warning-only failed snapshots are blocking; verified analytics cannot use
discovery evidence as authority; complete metric context and lineage survive
projection; stale/missing/legacy cross-report rows cannot be selected under
verified policy; checkpoint authority and exact source identity are rechecked;
and normal-mode behavior remains covered by existing tests.

Not established by this slice: current-SHA source-page correctness on retained
real PDFs, live LLM semantic quality, report-specific metric interpretation,
fresh frozen-five/ten-report results, call/token/cost/latency behavior, or
publication readiness. No provider call, PDF acquisition, canonical artifact
mutation, WordPress write, or publication write occurred.

## Editorial coverage and repair reliability closure — 2026-11-03

This checkpoint addresses the remaining deterministic coverage/recovery
defects without claiming a new provider-backed selection result.

### Adjust page-21 coverage root cause

The retained Adjust artifacts do not support a shortlist-cap diagnosis for the
page-21 gaming CPI omission. `findings.json` contains 32 findings, but the
only page-21 gaming finding is `gaming-overall-retention`; no gaming-CPI
finding was extracted into the authoritative findings pack. The evidence-
fidelity pack separately contains an unsupported proposed claim,
`Global gaming-app CPI reached $0.56 in 2025, up 30%`, whose evidence discusses
gaming session lengths/sessions per user rather than CPI or 30% growth. It was
correctly rejected. The retained candidate-generation audit reports model
output 10, target 7, opportunity count 7, selected 7, and `fallback_invoked`
false. Therefore widening the candidate pool would not recover the missing
source finding and would risk admitting the rejected claim. The confirmed
limitation is upstream source finding extraction/authoritative binding, not
shortlisting; no keyword relevance score or report-specific patch was added.

### Implemented reliability corrections

| Defect | Minimal correction | Result |
| --- | --- | --- |
| Failed technical validation could become PASS during final editorial reconciliation | `_merge_public_editorial_quality()` now preserves non-pass technical status, including missing diagnostics and warning-only diagnostics; only a genuinely editorial-only stale failure can be replaced by a passing final review. | Fail-closed status is retained. |
| Candidate validation derived status only from issue severity | `_candidate_validation_report()` now preserves an incoming failed status even when the issue list is empty or non-error. | Candidate promotion cannot occur from a diagnostic-free failure. |
| Empty final-insight rewrite returned success without a change | `_regenerate_one_final_insight()` records the existing typed ABSTAIN decision for an empty required text result. The regeneration loop treats an unchanged ABSTAIN as rejected, skips candidate provider/editorial revalidation, and rolls back. | No-op repair is not reported as successful. |
| Final reconciliation could clear an unchanged ABSTAIN | The final merge preserves the original failure for a rolled-back, unchanged ABSTAIN; real mutations retain the existing stale-editorial-review replacement path. | No false success from a no-op. |
| Distinct visible placements shared a stable public review ID | Verified semantic review projection now fails closed for duplicate `public_item_id` values with distinct public text, while exact-text duplicates retain existing dedupe. | No silent review-item loss. |

No new LLM stage, service, validator framework, schema, provider call, or
publication side effect was introduced. The latest successful provider-backed
Adjust baseline remains the isolated run recorded above (7/7 admitted, 7
verified facts, 7 final insights, validation/public-quality/readiness pass,
HTML produced). This correction was verified provider-free; it must not be
presented as a live model-selection improvement.

### Verification and limitations

The exact provider-free Step 2 replay was executed with the repository's
retained reference corpus: 15 cases / 39 variants, with no fabricated fixture
substitution, provider calls, or publication writes. The replay reports its
expected limitation: source PDFs and retained report artifacts are not present
under the default repository `out/` paths, so it checks retained-input
coverage only and does not claim live source verification.

The focused affected suite passed **300 tests in 29.74 s**. Changed-file Ruff
and full-repository mypy passed (`0` tracked errors across 786 source files).
The default-interpreter full suite previously passed 8,464 tests with 2
skips/48 deselected and had one unrelated failure because CPython 3.14 was
used for a wheelhouse test that requires CPython 3.12; the supported
interpreter version of that test passed. Hosted CI and the supported full
quality gate remain the release evidence for this commit.

The page-21 gaming CPI finding, optional signal cards, quotes, stochastic
selection breadth, and live repair quality remain unresolved limitations. E18
remains **Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO** for broader
effectiveness, and Step 3 remains **unstarted/not ready**.

### Verdict

The deterministic authority/contract correction slice is **PASS** for the
provider-free local gates. Overall Verified Claims Step 2 remains
**PARTIAL / NO-GO** because current-SHA source-report editorial evidence is
still absent. E18 remains **Active/PARTIAL** and Step 3 remains
**unstarted/not ready**.

### Hosted CI confirmation — 2026-11-01

Commit `38b0e6d7b6b3f4274cd273eaa0b8651d076c8837` passed hosted CI run
`41321929178`: `tests`, mutation partitions 0 and 1, and `release_evidence`
all completed successfully. The default tests job completed at 15:44:56 UTC;
mutation 0 completed at 15:42:57 UTC, mutation 1 at 15:42:37 UTC, and release
evidence at 15:46:12 UTC. The existing WordPress staging REST step was skipped
by its configured credential/variable guard. The release manifest had zero
unwaived issues and the retained release-evidence bundle is available at
<https://github.com/mbrakker/marketlense/actions/runs/41321929178/artifacts/13089054717>.

This hosted run verifies deterministic CI, mutation, benchmark, schema, and
release-evidence gates only. It did not run a retained real-report/provider
editorial workflow or publish to WordPress. The overall Step 2 verdict remains
**PARTIAL / NO-GO**; E18 remains **Active/PARTIAL** and Step 3 remains
**unstarted/not ready**.

## Adjust public-editorial review reliability correction — 2026-11-02

This addendum starts from `6e11a0af38d3c5c8ae0c0355bebe97284fe5459e` and is
based on the retained isolated Adjust run
`C:\\ml-adjust-e2e-20261102\\frozen-reliability-6oe2ci36`. It does not run
another provider-backed ingestion-to-HTML workflow, publish to WordPress, or
claim a live post-fix quality result.

### Confirmed failure boundary

The exact frozen PDF SHA-256 was
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`. The
retained run admitted **7/7** visual candidates and produced **7/7** verified
facts, **7** final insights, **6** metric-spine entries, and **5** key figures.
Retained unsupported and unresolved factual claims were both **0**. The
terminal failure was `validation_failed` at
`public_editorial_quality.semantic_review_unresolved`, with no final HTML.

Both independent primary public-editorial calls used GPT-6 Luna High with
high reasoning and an effective **8,192-token** output limit. Each recorded
**82,439 input tokens**, exactly **8,192 output tokens**, and **8,192 reasoning
tokens**; both were parse-invalid. The retained recovery rows and regeneration
rows produced valid envelopes but did not yield an accepted complete public
review. The run recorded **153 provider calls**, **1,296,653 input tokens**,
**198,143 output tokens**, **$0.230052**, **1,527.079 seconds**, seven
file-search calls, two structured-output recovery cycles, zero workflow retries,
zero automatic repairs, and zero operator interventions.

The retained artifacts do not contain `finish_reason`, refusal, raw provider
content, or complete request metadata for those two primary rows. Therefore
output-capacity exhaustion is the strongest supported explanation (exact
provider truncation status remains unproven); the artifacts do not support a
claim that the failure was schema coverage rather than JSON parsing. The
before/after quality reports agree on the same fail-closed rule and explanation:
`public_editorial_quality_review_invalid_json`.

### Minimal corrections

| Boundary | Correction | Safety retained |
| --- | --- | --- |
| Provider response state | `OpenAIResponseResult` and the modern/legacy adapters now preserve finish reason, refusal, provider status, and incomplete reason, with optional fields appended for cache/positional compatibility. | Unknown or missing provider metadata remains representable; raw responses are not logged. |
| Strict structured output | Explicit client-compatibility fallback remains limited to supported legacy `json_object`; strict `json_schema`/`strict=true` is never silently removed and unsupported clients return a typed nonretryable error. | Public-editorial schema authority and fail-closed behavior remain intact. |
| Review capacity | The review-family-only `max_output_tokens` is **16,384**; global budgets, reasoning effort, prompts' factual checks, schemas, and retry limits were not changed. | The existing two correction/two verification maximum remains bounded. |
| Recovery | Explicit truncation skips punctuation-only repair and uses the existing bounded model-repair path; refusals and provider-incomplete states fail closed without blind format retries. | Original failure classifications remain in diagnostics and later claims can continue. |
| Cache | Incomplete, refused, malformed, or otherwise unusable semantic responses are rejected on read and skipped on write; valid cache identity and legacy valid entries remain compatible. | No invalid response can be reused as a successful semantic result. |
| Review input | Redundant public item text was removed from `report_scope.public_content`; full wording remains in top-level `public_items`, with plan, evidence, canonical facts, and whole-report context preserved. | No public surface or authoritative factual context was dropped. |

### Provider-free measurements and limits

On the retained Adjust `artifacts.json`, the public-review scope was **621,148
JSON characters** before the duplicate-text removal and **614,030** after it:
**7,118 characters (1.15%)** removed. The repeated item text accounted for
**5,878 characters**; no evidence, verified fact, stable ID, page, span, metric
binding, editorial-plan entry, or report-level context was removed. The exact
final insight IDs and physical pages remained: gaming strategy/page 19,
cross-platform measurement/page 11, GenAI outcomes/page 9, e-commerce
installs/sessions/page 27, e-commerce marketplace retention/page 29, finance
session duration/page 36, and finance paid/organic ratio/page 38. All retained
source identities included the expected PDF hash.

The retained five chart cards remain `weak_evidence`, have empty candidate IDs,
and report `No chart candidate was linked to the metric evidence`; all three
card/figure linkage measurements are 0.0. This is consistent with the existing
conservative fallback because no accepted chart candidate was present in the
retained artifact. No deterministic candidate-to-card defect was demonstrated
by this review failure, so chart acceptance and provenance were not forced or
speculatively refactored.

The focused provider-free regressions cover completed strict JSON, length
truncation, refusal/content filtering, strict-schema compatibility, invalid
semantic cache entries, bounded structured recovery, retained failure causes,
review-scope duplication, and the review-specific output budget. These tests
demonstrate engineering correctness only. A fresh live run is still required
to determine whether 16,384 tokens is sufficient and whether editorial review
now reaches HTML.

The prompt-fixture gate remains green without a baseline change: **114,262
tokens / $0.025080** versus **114,247 / $0.025078** (**+15 tokens / +$0.000002**)
overall, and **11,630 / $0.002076** versus **11,615 / $0.002074** for the
validation family. The small increase is from the intentional public-editorial
instruction clarification; thresholds, pricing, model configuration, fixtures,
schemas, and factual checks were preserved.

### Verdict

The deterministic reliability correction is **PASS** for the demonstrated
provider-state, strict-schema, bounded-recovery, cache, and input-duplication
defects under provider-free tests. The retained Adjust result remains a failed
pre-fix run, and no post-fix provider-backed result or HTML exists. Overall
Step 2 remains **PARTIAL / NO-GO**; E18 remains **Active/PARTIAL**; Step 3
remains **unstarted/not ready**. The next required evidence is one genuine
provider-backed Adjust rerun followed by independent PDF-to-editorial review.

## Final pre-E2E editorial reliability corrections — 2026-11-02

This addendum is based on reviewed HEAD
`6fb964686730f1fbbf540a1bae1c231023793a98`. It is provider-free evidence only:
no new ingestion, retained-PDF provider run, canonical artifact mutation, HTML
generation, publication, or WordPress write was performed.

### Demonstrated corrections

The report-analysis orchestrator previously invoked the public-editorial
semantic review independently for the before and after quality packs. The
correction captures the terminal semantic result, including a fail-closed
result, with a private identity covering the public wording/evidence and
editorial plan, source identity, verified-fact digest, prompt/policy/execution
identity, validator, and output-schema identity. When the complete identity is
unchanged, the after pack reuses that result; deterministic quality checks and
both pack materializations still run. Changed wording, evidence, source,
fact, editorial plan, prompt, or review policy invalidates reuse. Regeneration
reviews remain independent and are not suppressed.

The semantic-response cache predicate now requires a parsed JSON object. It
rejects missing/null/corrupt structured payloads and explicit length,
max-output, content-filter, refusal, or incomplete responses on both cache read
and write. Existing valid cache identity, TTL, and legacy valid structured
entries remain compatible.

### Verification evidence

| Gate | Result |
| --- | --- |
| Focused reuse/cache regressions | **20 passed** |
| Affected orchestration/editorial suite | **183 passed** |
| Full CPython 3.12 pytest (no coverage) | **8,419 passed, 2 skipped, 48 deselected, 24 subtests** in **975.91s** |
| Full CPython 3.12 pytest with coverage | **8,419 passed, 2 skipped, 48 deselected, 24 subtests** in **1,465.01s** |
| Coverage floors | **PASS** — global 85.49%, contracts 97.98%, orchestrators 86.06%, generators 87.18%, services 84.34%, control-plane 90.60% |
| Mutation inventory | **PASS** — 67/68 mutants killed across 17 targets; the retained taxonomy target is 3/4 (75%), matching its existing baseline |
| Quality non-regression | **PASS** — coverage, retained mutation targets, golden docpacks, and candidate-extraction metrics all met baseline |
| Prompt-fixture regression | **PASS** — 114,262 tokens / `$0.025080` versus 114,247 / `$0.025078` (**+15 / +$0.000002**); validation 11,630 / `$0.002076` versus 11,615 / `$0.002074` |
| Ruff, full mypy, schema, architecture/policy and repository gates | **PASS** — full mypy reports 0 tracked errors across 786 source files |

The unchanged before/after review path is now one semantic provider/cache
evaluation rather than two while still persisting both quality packs. A
terminal failed review remains failed and is reused as such; a changed input
causes a fresh review. These are deterministic regression results, not proof
of improved live editorial quality.

### Limitations and status

The retained Adjust run still represents the pre-fix failure: 7/7 visual
candidates, 7/7 verified facts, 7 final insights, and no final HTML after the
public-editorial review became unresolved. No post-fix provider-backed run was
authorized in this slice, so live review completion, HTML readiness, provider
call/token/cost/latency impact, and source-report editorial quality remain
unmeasured. Chart-card handling remains conservative and unchanged.

The deterministic correction is **PASS** for the demonstrated duplicate-review
and semantic-cache defects. Overall Verified Claims Step 2 remains **PARTIAL /
NO-GO**; E18 remains **Active/PARTIAL**; Step 3 remains **unstarted/not ready**.
The next bounded action is a controlled provider-backed Adjust rerun with
independent PDF-to-editorial inspection.

### Hosted CI confirmation

Hosted CI run [41481984102](https://github.com/mbrakker/marketlense/actions/runs/41481984102)
for commit `ddfbde822e5979cb293b893f263470888b5f303e` completed successfully.
The `tests` job, mutation partitions 0 and 1, and `release_evidence` all
passed. The WordPress staging REST step was skipped by its configured
credential guard; no WordPress write occurred. The release-evidence bundle is
[artifact 13161665350](https://github.com/mbrakker/marketlense/actions/runs/41481984102/artifacts/13161665350).
GitHub emitted only existing action-runtime/deprecated-input warnings. This is
hosted deterministic-gate evidence; it does not replace the missing
post-fix provider-backed Adjust run or establish Step 2 promotion readiness.

## Live single-report Adjust acceptance — 2026-11-02

This addendum records the bounded provider-backed acceptance attempt required
before expanding to the frozen five-report cohort. It used one isolated Adjust
member only (`cohort-b638414df0b1fccea1cd`), the retained PDF
`C:\Programing\Market lense-step2-final\out\browser_downloads\www.adjust.com\b6b998e34a7c\mobile-app-trends-2026.pdf`, and the exact expected SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`. The
workflow ran with the existing ingestion, extraction, evidence, verified-fact,
visual, editorial, grounding, validation, and rendering stages. No WordPress
authentication, publication, or canonical artifact write was enabled.

### Capacity decision and run ledger

The previous retained failure used an 8,192-token public-editorial output cap
and both primary reviews ended at exactly that cap. The first post-fix run
raised the review-family-only cap to 16,384 (`bfee5cb1`); its primary review
still failed after two bounded recovery calls. Because the primary output was
14,893 tokens, the run supplied equivalent-capacity evidence for one further
review-specific increase to 32,768. No prompt, schema, reasoning setting,
retry limit, or validation rule was changed. The change and its routing test
are in `bc1f03749670f21bd18d50142886f13adce904d2`, which passed hosted CI.

| Run | SHA / root | Terminal result | Provider calls | Input tokens | Output tokens | Cost | Wall-clock | File-search calls | Structured recovery | Verified facts | Final insights | HTML |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Retained baseline, 8,192 | `f68d8e75`; `C:\ml-adjust-e2e-20261102\frozen-reliability-6oe2ci36` | `public_editorial_quality.semantic_review_unresolved` | 153 | 1,296,653 | 198,143 | `$0.230052` | 1,527.079s | 7 | 2 | 7/7 | 7 | 0 |
| Post-fix, 16,384 | `bfee5cb1`; `C:\ml-adjust-e2e-20261102-live\frozen-reliability-7y2cfely` | same fail-closed semantic gate | 153 | 1,210,979 | 195,054 | `$0.239681` | 1,546.672s | 9 | 2 | 6/6 | 6 | 0 |
| 32,768 first attempt | `bc1f0374`; `C:\ml-adjust-e2e-20261102-live-32768\frozen-reliability-1tqn49ek` | `context_category_fit_unknown_rule_id` | 114 | 250,646 | 57,651 | `$0.071397` | 800.610s | 7 | 0 | not reached | not reached | 0 |
| 32,768 isolated retry | `bc1f0374`; `C:\ml-adjust-e2e-20261102-live-32768-retry\frozen-reliability-wfstjesu` | `public_editorial_quality.semantic_review_unresolved` | 147 | 1,025,625 | 179,010 | `$0.205462` | 1,478.954s | 6 | 1 | 6/6 | 6 | 0 |

The 32,768 retry's public-editorial primary response completed at 13,775
output tokens, with recovery responses of 832 and 2,926 tokens. The usage
ledger records completed provider envelopes and valid parsing status, but the
review payload was not accepted as a complete schema/substantive result after
the bounded recovery sequence. The terminal code remains the existing
fail-closed `public_editorial_quality_review_invalid_json`; raw failed
responses and the validator's detailed intermediate payload are intentionally
not retained. Since the response was far below 32,768, a 65,536-token increase
is not justified by this evidence and was not attempted.

The first 32,768 attempt stopped earlier because the model returned an include
rule ID in `rejected_topic_rule_ids`; the existing context-category validator
correctly rejected that contradictory rule classification. The clean retry
passed that boundary and reached visual verification, grounding, and public
editorial review. No safe deterministic reclassification is justified, so no
production code change was made for this transient model-output failure.

### Verified-fact and source audit

The retry admitted **6/6** visual candidates, produced **6/6** verified facts,
quarantined **0**, and passed the verified-facts architecture gate with the
exact PDF hash. The verified fact digest was
`2da6db99dc16759b4345a3519949a49f983798ce00299bcdf9cb37ced44d5aa`; every
final insight used the canonical `verified-fact:<id>` evidence binding.

The final artifact was independently checked against full, uncropped PDF pages
and rendered page images. The six retained rows were:

| Stable ID | Physical page | Source-supported final wording / metric check |
| --- | ---: | --- |
| `genai-maturity-and-reported-gains` | 9 | Advanced-deployment organizations reportedly achieved efficiency gains over 20%; the final wording preserves the reported qualifier and does not add a timeframe or forecast. |
| `cross-platform-satisfaction` | 11 | Around 31% of marketers report complete satisfaction with cross-platform data unification/readability; population and approximate qualifier match. |
| `gaming-growth-diverges-by-genre` | 19 | Casual installs/sessions were +19%/+37%; strategy installs/sessions were -1%/+57%, global YoY 2024–2025; category/value relationships match the chart. |
| `gaming-paid-organic-overall` | 22 | Global “All” gaming paid/organic ratio rose 2.07→3.33, +61%; denominator and overall cohort remain bound. |
| `ecommerce-install-session-divergence` | 27 | Global 2025 e-commerce installs fell 10% YoY while sessions rose 5%; period, population, and metric directions match. |
| `finance-cpi-and-retention-moved-down` | 37 | Final public wording states day-1 retention fell 13%→12% from 2024 to 2025; the authoritative fact also retains the page's CPI binding, without adding unsupported CPI text to the final wording. |

The retained artifacts contain six metric-spine entries and five key figures;
all five visual cards remain the conservative `weak_evidence` fallback with
empty chart-candidate linkage. This is an observed artifact limitation, not a
factual promotion. Retained factual validation reported **0 unsupported** and
**0 unresolved** claims. The source audit therefore found no independently
confirmed unsupported material claim, but it does not convert the failed
public-editorial semantic gate into a publishable result.

### Acceptance outcome

No final HTML or rendered final report page exists in either 32,768 run, so
HTML completeness, internal-ID absence, publication readiness, and end-to-end
editorial usefulness cannot be accepted. The final insight/source audit above
is evidence for factual grounding only; it is not a post-selection replay
claim or a substitute for the missing HTML acceptance.

Focused regressions on the routing, context-category, public-review reuse,
structured-output, recovery, and execution-policy boundaries passed **76
tests**. Hosted CI run
[41504085301](https://github.com/mbrakker/marketlense/actions/runs/41504085301)
for `bc1f03749670f21bd18d50142886f13adce904d2` passed `tests`, both mutation
partitions, and `release_evidence`. The live attempt itself remained
unpublished and made no WordPress write.

The single-report live acceptance is therefore **PARTIAL / NO-GO**. The
32,768 configuration change is retained because it was the smallest measured
response-capacity correction and did not weaken validation, but no further
budget increase is justified. E18 remains **Active/PARTIAL**, Step 2 remains
**PARTIAL/NO-GO**, and Step 3 must not begin. Expansion to the frozen
five-report cohort is **NO-GO** until the existing public-editorial review
produces a complete accepted result and a final HTML artifact on a fresh
provider-backed run.

## Public-editorial review contract and diagnostics correction — 2026-11-02

This correction is based on reviewed HEAD
`1d699b4daaf0aa91486d22ea018511cce492aedd`. It is a provider-free
implementation and regression pass; it did not run a new report, mutate a
canonical artifact, generate final HTML, publish, or write to WordPress.

### Retained failure classification

The retained 32,768-token Adjust retry has three relevant usage rows. The
primary public-editorial provider envelope completed and parsed as JSON
(13,775 output tokens); the bounded model-repair and regeneration envelopes
also completed and parsed as JSON (832 and 2,926 output tokens). The retained
terminal result is nevertheless `public_editorial_quality.semantic_review_unresolved`
with the older generic inner code `public_editorial_quality_review_invalid_json`.
The old run did not retain raw provider responses or the intermediate
validator exception, so the exact first returned item/dimension failure cannot
be recovered from that artifact. It is therefore not claimed as a proven
model omission or truncation.

Code inspection did confirm a deterministic producer/validator contract gap:
the producer omitted the item's permitted repair target from the model input,
while the validator enforced exact repair-target equality against the retained
item. A parsed response could consequently fail the downstream contract even
when its JSON was valid. This correction supplies that existing target under
`allowed_repair_target`; it does not authorize new targets or deterministic
semantic judgments.

### Corrections and safeguards

- Advanced the public-review validator identity from v19 to v20 so stale
  semantic-review cache/checkpoint results cannot bypass the changed contract.
- Supplied exact item repair targets, item-scoped evidence-ID rules, and
  report-level affected-item/target rules to the existing review prompt.
- Added public-review-specific requirements to the existing bounded repair and
  regeneration prompts: exactly one verdict for every expected item, no
  duplicate/foreign IDs, complete fields, item-bound evidence, valid targets,
  consistent failure fields, all four report dimensions, and source-grounded
  reasons. The existing two recovery attempts and fail-closed validator remain
  unchanged.
- Preserved bounded scalar/list diagnostics and now retain item IDs, missing /
  unexpected / duplicate IDs, dimensions, expected/actual counts, parse state,
  provider completion state, and per-attempt error classes without retaining
  raw prompts, responses, or source prose. Parsed-but-rejected responses remain
  distinguishable from malformed JSON.
- Clarified context-category prompt authority: supported IDs are configured
  include IDs only; rejected IDs are configured exclude IDs only; unsatisfied
  includes are omitted from both fields; invented IDs remain invalid.
- Chart cards remain conservative `weak_evidence` fallbacks with no candidate
  linkage in the retained Adjust artifacts. No chart evidence was manufactured
  and no chart production behavior was changed.

### Provider-free verification

| Check | Result |
| --- | --- |
| Focused public-editorial, structured-output recovery, context-category, prompt, cache, and pre-E2E regressions | **180 passed** in 14.32s |
| Formatting gate | **PASS** |
| Changed-file Ruff gate (CI-enforced F rules) | **PASS** |
| Full mypy baseline gate | **PASS** — 0 tracked errors across 786 source files |
| Prompt fixture regression | **PASS** — unchanged thresholds and pricing |

The prompt fixture run measured the intentional contract text rather than a
baseline edit:

| Affected scope | Previous | Current | Delta |
| --- | ---: | ---: | ---: |
| `report_vs/context_category_fit` tokens / cost | 1,161 / `$0.000188` | 1,331 / `$0.000205` | +170 / +$0.000017 |
| `report_vs/validate/public_editorial_quality` tokens / cost | 1,940 / `$0.000346` | 2,179 / `$0.000370` | +239 / +$0.000024 |
| Report family tokens / cost | 23,144 / `$0.008600` | 23,314 / `$0.008617` | +170 / +$0.000017 |
| Validation family tokens / cost | 11,615 / `$0.002074` | 11,854 / `$0.002098` | +239 / +$0.000024 |
| Corpus total tokens / cost | 114,247 / `$0.025078` | 114,656 / `$0.025119` | +409 / +$0.000041 |

The existing time-bounded allowlist covers these measured prompt-contract
changes; the committed fixture baseline, thresholds, model configuration, and
pricing were not manipulated. No additional LLM call or validator was added.

### Status and next evidence

The deterministic contract, recovery-instruction, diagnostics, cache
invalidation, and strict context-ID corrections are **PASS** under the
provider-free tests. No post-fix provider-backed public-editorial review or
accepted final HTML exists yet. The retained source/fact and chart audit
therefore cannot establish live recovery, editorial usefulness, latency/cost,
or publication readiness after this correction.

Overall Verified Claims Step 2 remains **PARTIAL / NO-GO**; E18 remains
**Active/PARTIAL**; Step 3 remains **unstarted/not ready**. The minimum next
action is one fresh isolated Adjust run (or an existing stage-only replay that
uses the actual public-editorial workflow) with no publication side effects,
followed by independent inspection of the resulting HTML against the retained
PDF. Until that produces an accepted complete review and HTML, no promotion
claim is made.

## Live Adjust public-editorial replay / E2E acceptance — 2026-11-02

This is the one-report provider-backed verification requested after the
provider-free correction pass. The target source was the exact frozen Adjust
PDF (SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`) and the
workflow ran from clean commit
`85b5b5cdc2ad72a5286d16a7d00c33cd78595198`. No code, prompt, model, budget, or
quality policy was changed during the run.

No safe existing stage-only wrapper was available for invoking the production
`_public_editorial_semantic_review` path with a complete retained package.
The allowed fallback was therefore used once: the canonical isolated
`run_frozen_reliability_cohort.py` workflow, restricted to
`cohort-b638414df0b1fccea1cd`, with `--verified-facts-architecture` and no
publication side effects. The no-provider preflight was run separately; its
CLI validates the full manifest even when report IDs are supplied, so it is
not included in the live metrics below.

### Run identity and terminal outcome

| Item | Observed result |
| --- | --- |
| Run directory | `C:\ml-adjust-live-85b5-e2e\frozen-reliability-6c1ajwnb` |
| Member directory | `...\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-c_1bb8mn` |
| Source identity | `source:8cb648b6bbd9dbae4ec1d915c38cf235` plus the exact PDF SHA above |
| Verified-facts architecture | **PASS**; 7 evaluated, 7 admitted, 0 quarantined, 7 verified facts; digest `62cb859f0648c5a5ede70c0d651b2edd4855c64524c4d5e0821de8ff23da5317` |
| Terminal workflow state | `failed`; `validation_failed` at `semantic_validation` |
| Public-editorial gate | **FAIL closed**; `public_editorial_quality.semantic_review_unresolved` |
| Final HTML | Not produced; report render ended `dead_letter` after validation failure |
| Publication | Not ready; no WordPress authentication, write, or operator intervention |

The production public-editorial semantic validator was v20 with schema v3.0.
The persisted deterministic quality pack reports its own `v16` validator
identity; these are separate contracts and are not being conflated.

The failure was not an unparsed or truncated provider response. All three
public-review envelopes were marked `completed` and `valid` in the usage
ledger, but all three failed the existing status-consistency validator for
`soft_copy:summary:87e02b46e8730ce3`:

`terminal=public_editorial_quality_review_invalid_json; inner=public_editorial_quality_review_status_conflict; attempts=primary ... model_repair ... regeneration ...`

The outer terminal code is a compatibility wrapper; the inner status-conflict
code is the actionable diagnostic. The primary response and both bounded
recovery responses were structurally parsed, so the existing two-recovery
limit was reached without an accepted review. Raw provider responses are not
retained by policy; the exact conflicting fields therefore cannot be asserted
from the audit record. This is a provider-output contract failure, not grounds
for weakening the validator or adding a third attempt.

### Provider and recovery measurements

| Scope | Calls | Input tokens | Output tokens | Total tokens | Cost | File-search calls | Recovery |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Complete isolated Adjust run | 154 | 1,088,825 | 201,469 | — | `$0.228010` | 8 | 2 structured-output recovery calls; 0 automatic repairs |
| Public-editorial review only | 3 | 284,154 | 28,238 | 312,392 | `$0.042535` | 0 | primary + model repair + regeneration; all completed/valid but rejected by status conflict |

The run took 1,568.163 seconds wall-clock (the recorded core-processing
scope is partial at 452.0 seconds), with zero workflow retries and zero
operator interventions. Validation reuse telemetry recorded one
`prior_package_missing` event: 40 claims were newly validated, with no reused
results and no semantic or grounding calls avoided. The current review output
cap was 32,768; no cap increase or repair-policy change was made for this run.

### Final insight and source audit

The final artifact contained seven source-bound insights. Each retained
evidence span used a `verified-fact:<id>` binding, the exact source identity,
and its physical PDF page. Independent inspection used the original full PDF
pages and rendered images; no cropped or synthetic page was used.

| Stable fact / insight ID | Page | Source check |
| --- | ---: | --- |
| `ecommerce-cpi-by-app-type` | 29 | Deal-discovery CPI `$1.44` to `$2.26` matches the page narrative and the deal-discovery bars in the global 2024–2025 CPI chart. |
| `global-install-growth` | 6 | Global installs `+10%` in 2025 versus `+8%` in 2024; the page separately labels sessions `+7%` and `+2%`, so the metrics were not swapped. |
| `genai-maturity-and-reported-gains` | 9 | The `over 20%` efficiency-gain qualifier remains attached to the small advanced-deployment group; no unsupported population, period, or denominator was added. |
| `multiplatform-satisfaction` | 11 | Around `31%` remains a marketer satisfaction response about unifying and reading data across platforms, with no invented timeframe or geography. |
| `gaming-casual-growth` | 19 | Global casual-game installs `+19%` and sessions `+37%` match the narrative and the two Casual bars in the chart. |
| `finance-growth-divergence` | 34 | Global finance-app installs `-4%` and sessions `+21%` in 2025 match the narrative and the chart’s separate series. |
| `methodology-date-range` | 13 | The methodology panel explicitly states January 2024–January 2026 and the retained wording does not turn that date range into a performance metric. |

The audit found **0 independently confirmed unsupported material factual
claims** and **0 unresolved retained factual claims**. It does not establish
publication readiness because the independent public-editorial gate failed and
no final HTML exists. The artifact has six metric-spine entries and five key
figures; CPI and methodology are not promoted into those numeric downstream
collections. Five chart cards remain conservative `weak_evidence` fallbacks
with empty candidate linkage, and the quotes family abstained as
`quotes_missing`. These are observed coverage limitations, not evidence to
be repaired by manufacturing bindings or chart facts.

### Comparison with the retained 32,768 baseline

The immediately preceding retained Adjust run was
`C:\ml-adjust-e2e-20261102-live-32768-retry\frozen-reliability-wfstjesu`.
The comparison is descriptive; it does not attribute ordinary LLM variation
to the implementation.

| Measure | Previous retained run | Current isolated run | Change |
| --- | ---: | ---: | ---: |
| Provider calls | 147 | 154 | +7 (+4.76%) |
| Input tokens | 1,025,625 | 1,088,825 | +63,200 (+6.16%) |
| Output tokens | 179,010 | 201,469 | +22,459 (+12.55%) |
| Cost | `$0.205462` | `$0.228010` | +`$0.022548` (+10.97%) |
| Wall-clock | 1,478.954 s | 1,568.163 s | +89.209 s (+6.03%) |
| Visual candidates / verified facts | 6 / 6 | 7 / 7 | +1 / +1 |
| Final insights | 6 | 7 | +1 |
| Semantic gate | unresolved | unresolved | no acceptance improvement |
| Final HTML | absent | absent | no change |

The current run exposed a more specific status-conflict diagnostic than the
retained run, but it did not produce an accepted review. The additional
candidate/fact/insight counts are source-run variability and cannot be claimed
as a code-attributable editorial improvement. No cost or latency benefit is
claimed.

### Acceptance decision

This live acceptance is **PARTIAL / NO-GO**. The source-bound factual layer
passed its admission and retained-claim checks, but the public-editorial
semantic review failed closed after its two permitted recoveries, so HTML
completeness, editorial usefulness in the rendered report, publication
readiness, and absence of internal IDs in HTML remain unverified. The exact
provider conflict is not recoverable from the redacted usage ledger; a new
provider-backed attempt should be considered only after that boundary is
diagnosed through existing audit-safe mechanisms. No speculative code change,
budget increase, third recovery attempt, publication, or frozen-five run is
justified by this result.

E18 remains **Active/PARTIAL**. Verified Claims Step 2 remains
**PARTIAL/NO-GO**. Step 3 remains **unstarted/not ready**. The frozen-five
promotion decision is **NO-GO**.

## Cross-stage contracts and public-output coverage correction — 2026-11-03

This correction was developed from reviewed HEAD `0409dc4647dfff9f98e3d444d3cb6e961a27cd3c`
on `codex/fix-retained-insight-evidence-validation`. It addresses the
cross-stage failures reproduced in the provider-free category-fit, public
editorial, and verified-render regressions. No canonical artifact, readiness
approval, publication, WordPress write, or provider call was made during this
correction pass.

### Root causes and bounded fixes

- **Public-editorial P0:** the validator already enforced the status contract,
  but the public-review and structured-recovery prompts did not state all of
  its pass/fail/unresolved field combinations. The validator now retains a
  typed `status_conflict_type` discriminator without raw model text, advances
  its cache identity to `public-editorial-quality:v21`, and the system/recovery
  prompts state the existing item and report contracts. Negative semantic
  judgments remain blocking.
- **Category-fit P1:** topic-semantic normalization and selected/decision
  consistency ran after the structured-output service's schema callback, so a
  schema-valid response could fail outside bounded recovery; cache reuse also
  performed only schema validation. The same existing deterministic checks now
  run in the validator callback and on reuse, malformed normalized values are
  preserved for rejection, and the category-fit validator identity advances
  from `2.0` to `2.1`. Recovery remains bounded by the existing policy.
- **Public review/render P1:** the review inventory omitted reader-visible
  metric-spine, accepted-chart, advisory, claim-support, and bound topic-signal
  fields, while including weak/non-rendered chart cards. Topic evidence could
  also be overwritten by later navigation records. The review now projects the
  renderer's material fields through the existing evidence bindings, filters
  weak or unbound optional surfaces, and deduplicates identical verified text;
  accepted chart cards use the renderer's eligibility predicate. The verified
  renderer uses the same binding boundary and no longer falls back to legacy
  `data.insights`, `data.quote`, `data.tldr`, or `data.commentary`.
- **Methodology-date-range P2:** the retained Adjust date-range observation was
  checked against physical PDF page 13 and is source-valid. No blacklist,
  threshold reduction, or special-case production change was justified.

### Provider-free verification before live acceptance

| Check | Result |
| --- | --- |
| Category-fit and cache/recovery regressions | **23 passed** |
| Public-editorial status, projection, renderer, and pre-E2E regressions | **61 passed** |
| Full supported CPython 3.12 suite with coverage | **8,440 passed, 2 skipped, 48 deselected, 24 subtests** in 1,548.99s |
| Coverage floors | **PASS** — global 85.50%, contracts 97.98%, generators 87.20%, orchestrators 86.07%, services 84.34%, control-plane 90.60% |
| Mutation gate | **PASS** — 67/68 killed; the single taxonomy survivor matches its retained baseline |
| Quality regression comparator | **PASS** — coverage, mutation, docpacks, and candidate-extraction baselines unchanged |
| Prompt fixture regression | **PASS** — 115,051 tokens / `$0.025158` versus 114,247 / `$0.025078` (+804 / +$0.000080); report +285 tokens / +$0.000028, validation +519 / +$0.000052; thresholds and pricing unchanged |

The prompt increase is the measured status/category contract and public-surface
authority text. It was not produced by a new LLM stage or by editing the
fixture counts, pricing, or thresholds.

The retained Adjust artifact was also rendered provider-free to
`C:\ml-cross-contract-html-replay\mobile-app-trends-2026-pdf.html`. Its
existing seven findings and physical-page bindings remained intact; the full
PDF audit confirmed the retained CPI, installs, GenAI maturity/efficiency,
satisfaction, casual-gaming, finance, and methodology observations. The HTML
contained no internal evidence identifiers or quality placeholders. Unbound
topic signals, weak chart cards, and abstained quotes were omitted fail-closed;
this is correct safety behavior but leaves optional public coverage unproven.
The inherited methodology label rendered with mojibake in one metric card;
that encoding limitation predates this correction and is not silently repaired.

### Live acceptance status

One isolated provider-backed Adjust acceptance remains required after the
correction. It must use the exact frozen PDF SHA
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, the
verified-facts workflow, no WordPress target, and independent HTML/PDF review.
Until that single run produces terminal artifacts, this section provides no
live claim about provider variability, editorial acceptance, cost, latency, or
publication readiness. Step 2 therefore remains **PARTIAL / NO-GO** and Step 3
remains **unstarted / not ready**.

## Live single-report Adjust acceptance after cross-stage correction — 2026-11-03

One fresh provider-backed Adjust run was executed after hosted CI passed, using
the exact frozen PDF SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, the
verified-facts architecture, and no WordPress/publication target. The run used
commit `def2c1de105cd06e75dac810e90df125a4ab5b81` from a clean detached
worktree at `C:\ml-cross-contract-live-worktree-1103` because the primary
implementation worktree intentionally retained the unrelated dirty
`Wordpress/dist/marketlense.zip`. A preflight invocation from that dirty
worktree stopped before provider execution with the runner's clean-SHA
precondition; it is not counted as a provider run. No provider-backed retry was
made after the isolated run below.

Run artifacts:

- Cohort root:
  `C:\ml-cross-contract-live-1103-final\frozen-reliability-q19pm_xk`
- Report run:
  `C:\ml-cross-contract-live-1103-final\frozen-reliability-q19pm_xk\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-zhx4nnup`
- Final artifact:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`
- Terminal validation:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\validation.json`
- Retained-claim validation:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\validation_retained_claim_validation_candidate.json`
- Public-quality snapshot:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\public_editorial_quality_before.json`

### Terminal outcomes and measurements

| Outcome or measure | Result |
| --- | ---: |
| Visual candidates evaluated / admitted / quarantined | 6 / 6 / 0 |
| Verified facts | 6; architecture admission passed |
| Final source-bound insights | 6 |
| Unsupported retained factual claims | 0 |
| Unresolved retained factual claims | 0 |
| Terminal validation / publication readiness | `fail` / `fail` |
| Provider calls | 148 |
| Input / output tokens | 996,045 / 185,296 |
| Estimated cost | `$0.208144` |
| File-search calls | 7 |
| Wall-clock | 1,312.148 seconds |
| Structured-output recovery calls / automatic repairs | 0 / 0 |
| Workflow attempts / retries / operator intervention | 1 / 0 / 0 |

The run was isolated (`isolated_fresh_state=true`). Validation reuse recorded
`prior_package_missing`; 40 claims were newly validated, with no reused
results and no calls avoided. These figures come from the terminal cohort
summary and canonical usage ledger, not from estimates made after the run.

### Source and editorial audit

The verified-fact source identity was
`source:8cb648b6bbd9dbae4ec1d915c38cf235` combined with the exact PDF hash
above. The six final insight bindings were independently checked against the
original full PDF pages:

| Stable fact / insight | Physical page(s) | Result |
| --- | ---: | --- |
| `ecommerce-installs-sessions-diverge` | 27 | Global e-commerce installs `-10%` and sessions `+5%`, YoY 2024–2025, matched the chart and narrative. |
| `ecommerce-cpi-subvertical-divergence` | 29 | Global CPI and the named subvertical values matched their labels and 2024–2025 comparison. |
| `gaming-subvertical-growth-patterns` | 19 | Strategy installs `-1%` and sessions `+57%` matched the correctly mapped series. |
| `finance-global-latam-growth` | 34–35 | Global 2025 figures and LATAM `+76%` installs / `+57%` sessions retained their distinct periods and populations. |
| `genai-maturity-and-reported-efficiency` | 9 | The `over 20%` efficiency result remained qualified to the small advanced-GenAI group and was reported, not asserted as universal. |
| `cross-platform-measurement-satisfaction` | 11 | Around `31%` remained a marketer complete-satisfaction measure about unifying and reading data across platforms. |

No unsupported material factual claim was independently confirmed in these
retained insights, and every verified fact retained its canonical evidence ID,
source identity, physical page, and protected metric structure. However, the
run did not reach final HTML. Therefore rendered completeness, absence of
internal IDs in the final HTML, and publication-ready editorial usefulness
cannot be claimed from this run.

### Remaining live blocker

The terminal failure was typed as
`regeneration_repair_target_unsupported` at
`public_editorial_quality.semantic_review`, first observed for `claim:12`.
The persisted public-quality evidence contains 12 blocking issues: four
claim-ledger fragments omitted material geography/timeframe/cohort or
attribution context; five key-figure values omitted protected metric context;
one metric-spine value was an isolated percentage; the decision-brief
confidence note was generic; and the compact summary TL;DR repeated the
summary finding. These are appropriate fail-closed public-quality findings,
not unsupported-fact promotions.

The actionable cross-stage defect is that the public-review projection assigns
`executive_advisory` as the repair target for claim-ledger/advisory findings,
while the existing regeneration planner's supported target contract does not
include `executive_advisory`. The planner therefore dead-letters the report
before a targeted repair can be attempted. This is a deterministic integration
gap demonstrated by the live run, not a reason to weaken public semantic
validation or add another LLM stage. It was not changed or provider-rerun in
this acceptance pass because the requested live budget was limited to one
fresh isolated run.

### Comparison with the immediately preceding retained Adjust run

The previous retained run was the 32,768-budget run recorded above. The
comparison is descriptive and does not attribute ordinary model variability to
the code change.

| Measure | Previous retained run | Current run | Change |
| --- | ---: | ---: | ---: |
| Provider calls | 154 | 148 | -6 (-3.90%) |
| Input tokens | 1,088,825 | 996,045 | -92,780 (-8.52%) |
| Output tokens | 201,469 | 185,296 | -16,173 (-8.03%) |
| Cost | `$0.228010` | `$0.208144` | -`$0.019866` (-8.71%) |
| Wall-clock | 1,568.163 s | 1,312.148 s | -256.015 s (-16.33%) |
| Visual candidates / verified facts | 7 / 7 | 6 / 6 | -1 / -1 |
| Final insights | 7 | 6 | -1 |
| HTML / publication readiness | absent / fail | absent / fail | no acceptance improvement |

The lower cost and latency occurred with a different model-selected candidate
count and are not claimed as an optimization benefit. The source-fact layer
remained intact, but the public-output stage did not complete.

### Acceptance decision

This live acceptance is **PARTIAL / NO-GO**. Cross-stage source identity,
visual admission, verified-fact bindings, factual safeguards, and final insight
provenance passed for the six retained insights. The public-editorial repair
boundary failed closed on an unsupported target, so no HTML or publication
readiness was produced. E18 remains **Active/PARTIAL**. Verified Claims Step 2
remains **PARTIAL/NO-GO**, the frozen-five promotion decision remains
**NO-GO**, and Step 3 remains **unstarted/not ready**. No WordPress write,
publication mutation, or second live provider run occurred.

## Public editorial repair and render contract correction — 2026-11-03

This addendum records the provider-free correction of the remaining public
editorial repair boundary. The implementation was based on the retained
Adjust failure at `953900bc`; no new provider call or publication write was
used for this diagnosis.

### Confirmed root causes and corrections

- `executive_advisory` and `claim_ledgers` are derived projections, but the
  public semantic-review projection exposed them as regeneration roots. The
  verified projection now carries a hidden, deterministic `repair_field` only
  when existing lineage identifies one supported producer: metric IDs route to
  `insights_final[item=<id>].metric.value`; key figures route through their
  originating insight; summary/quote claims use their canonical section and
  ID; and advisory text routes only on an exact unique insight field. An
  unmappable derived issue remains blocking and now returns a `skip` plan
  rather than raising `regeneration_repair_target_unsupported` or triggering a
  broad unrelated rewrite. `executive_advisory` was not added to the planner's
  supported targets.
- Verified semantic review now reuses the existing renderer normalization and
  eligibility boundaries: the public limits are four metric-spine rows, six
  key-figure rows, four claim-support rows, and four accepted chart cards.
  Metric and figure cards are reviewed as one combined visible claim, while
  distinct visible placements remain separate review items. The non-rendered
  compact TLDR, weak/unbound optional cards, and advisory implications already
  suppressed by the renderer are not presented as public review blockers.
  Full retained-claim validation remains separate and unchanged.
- Universal metric-ledger claims now reuse `metric_claim_text()` so existing
  timeframe, geography, segment, cohort, denominator, observation status,
  forecast status, and observation context are retained when present. Public
  metric/key-figure normalization exposes the same available context and
  stable evidence lineage without filling missing fields.
- Advisory production now leaves the optional `confidence_note` empty. The
  presentation boundary also suppresses the two historical availability
  strings so a stale derived artifact cannot reintroduce deterministic
  confidence boilerplate. Renderer-level duplicate suppression remains in
  force; no distinct insight is removed.
- The public semantic-review/cache identity advanced from `v21` to `v22`, and
  the public quality contract validator advanced from `v16` to `v17` so old
  projection batches cannot be reused. GPT-6 Luna High, the 32,768-token cap,
  schemas, recovery bounds, and semantic authority are unchanged.

### Provider-free retained Adjust replay

The retained artifact was replayed through the current projection and planner
without provider calls. The resulting public review inventory contained 47
items: 18 final-insight placements, 10 summary placements, 8 expert-comment
placements, 3 LinkedIn placements, 4 claim-support cards, 2 metric-spine cards,
1 key-figure card, and 1 decision-brief placement. The old raw claim rows that
were outside the renderer's four-card limit no longer create false public
review blockers; they remain available to the separate retained-claim checks.

The live artifact's two eligible metric cards retained their full available
context, including subject/segment/cohort/denominator/geography/timeframe and
observed/reporting qualifiers. The one eligible key-figure card retained its
available context and source evidence. No evidence ID, source identity,
protected metric value, page, or span was changed. A metric review issue was
resolved to the existing path
`insights_final[item=genai-maturity-and-reported-efficiency].metric.value`.
An explicit replay of the former `claim:12` / `executive_advisory` issue now
returned `mode=skip`, one unmappable blocking issue, and
`broad_retry_allowed=false`; it did not crash and did not broaden repair.

### Focused verification

| Check | Result |
| --- | --- |
| Public pre-E2E/projection/lineage regressions | **51 passed** |
| Authority, rendering, regeneration, storage, and artifact regressions | **370 passed** |
| Contract schema snapshot gate | **PASS** |
| Changed-file Ruff (E/F/I) | **PASS** |
| Changed-source mypy | **PASS** — 8 files |
| Full-source mypy | **PARTIAL** — one pre-existing error in `src/services/mailbox_acquisition_service.py:2028` (`anchor.parent` may be `None`); no changed-file errors |

The retained failed run did not produce HTML. Its retained vector-store text
contains U+FFFD replacement characters around the contents/methodology
extraction, but the original PDF is not present in that retained run root.
The first decoding boundary therefore cannot be reproduced safely from the
available artifacts; no broad text substitution was made. Weak chart cards
remain omitted by the existing renderer eligibility gate.

The deterministic correction is **PASS / provider-free**. Step 2 remains
**PARTIAL / NO-GO** until one fresh isolated provider-backed Adjust run after
hosted CI is green produces final HTML and independent PDF-grounded editorial
acceptance. Step 3 remains **unstarted / not ready**. No live quality
improvement or publication readiness is claimed from this replay alone.

## Fresh live Adjust acceptance after hosted CI — 2026-11-03

Hosted CI was green before this run: workflow `41602367146`
(`https://github.com/mbrakker/marketlense/actions/runs/41602367146`) passed
`tests`, both mutation partitions, `release_evidence`, and the CI start job.
The implementation revision was `4515f36b0c3f888b40c0124a640cdaf6957e4510`.

Exactly one fresh isolated provider-backed Adjust run was executed with the
verified-facts architecture, no WordPress target, and no publication write.
The source artifact was the frozen PDF with SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` and
MD5 `b638414df0b1fccea1cd8a93eaf8f5aa`.

Run artifacts:

- Cohort result:
  `C:\ml-cross-contract-live-1103-public-contract\frozen-reliability-wht6hvw1\cohort_result.json`
- Attempt:
  `C:\ml-cross-contract-live-1103-public-contract\frozen-reliability-wht6hvw1\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-gg3hrfmn`
- Artifacts:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`
- Public-quality pack:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\public_editorial_quality_before.json`
- Terminal validation:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\validation.json`

### Terminal outcome and measured usage

| Measure | Result |
| --- | ---: |
| Visual candidates evaluated / admitted / quarantined | 7 / 7 / 0 |
| Verified facts | 7 |
| Final insights | 7 |
| Unsupported / unresolved retained factual claims | 0 / 0 |
| Public review inventory in retained quality pack | 51 items |
| Provider calls | 152 |
| Input / output tokens | 1,033,800 / 185,087 |
| Estimated cost | `$0.209313` |
| File-search calls | 6 |
| Wall-clock | 1,669.032 seconds |
| Structured-output recovery / automatic repair calls | 0 / 0 |
| Workflow attempts / retries / operator intervention | 1 / 0 / 0 |
| Validation / publication readiness | `fail` / `fail` |
| Terminal failure | `regeneration_target_item_unchanged` |

The run was source-admitted and factually bounded, but it produced no final
HTML. The prior `regeneration_repair_target_unsupported` defect did not recur:
the public projection and planner accepted supported upstream targets, and the
former unsupported derived-target case now remains an explicit unmappable,
fail-closed issue. The new terminal failure came after one bounded
`report_vs/artifacts/regenerate/insights_final` call returned valid output that
did not change the declared insight field. No second live run was started.

### Actual public-quality blockers

The retained public-quality pack has three blocking issues:

1. The hyper-casual insight's `so_what` says only that install and session
   growth differ, so the model correctly rejected it as a restatement without
   meaningful implication. Its source fact remains valid on PDF page 19.
2. The derived metric-spine card for
   `cross-platform-data-satisfaction` was rendered as
   `around 31% percent of marketers` followed by repeated population and
   status fragments. The underlying ~31% fact and binding are correct, but
   this presentation is not analyst-quality. The planner mapped the issue to
   the authoritative insight metric path; that path is not the actual derived
   display field, so the unchanged repair correctly failed closed.
3. The report-level coverage review found that the public wording omitted the
   admitted MENA/APAC finance figures and the slots/idle-RPG/strategy CPI
   values, while repeating several claims. It also identified that the source
   gives no survey timeframe or geography for the ~31% statement. This issue
   has no single safe source leaf and remains intentionally unmappable.

These are editorial/render completeness blockers, not unsupported-fact
promotions. The model's factual verdicts for the retained claims remained
source-consistent. The generated public inventory and the full source-backed
artifact were inspected directly; no HTML exists to inspect for internal IDs,
rendered completeness, or publication readiness.

### Independent source check

The original PDF was independently checked at the physical pages referenced by
the verified facts: page 11 supports the ~31% marketer satisfaction statement;
page 19 supports hyper-casual `4%` installs / `31%` sessions and the other
subvertical relationships; page 21 supports global gaming CPI `$0.56` and the
`$4.47` / `$3.19` / `$1.03` category values; page 27 supports global
e-commerce installs `-10%` and sessions `+5%`; page 29 supports the global and
subvertical e-commerce CPI values; and page 35 supports LATAM `+76%` / `+57%`,
MENA `+42%` / `+10%`, and APAC `+5%` / `+50%`. No independently confirmed
unsupported material factual claim was found in the admitted verified-fact
layer. Because the run stopped before HTML, this source check does not imply
public-render acceptance.

The PDF text extraction also contains replacement characters around some
methodology/content text. With no reproducible first-boundary corruption in
the live HTML (because HTML was not produced), no speculative decoding change
was made. Weak or unbound chart cards remained excluded by the existing
renderer gate.

### Decision

This run is **PARTIAL / NO-GO**. The public repair/render contract correction
passed provider-free regression and removed the former unsupported-target
crash, but the fresh live run exposed a remaining malformed derived metric
display, an analytically weak insight implication, and an unscoped coverage
gap. No final HTML, publication mutation, or WordPress write occurred. Step 2
remains **PARTIAL/NO-GO** and Step 3 remains **unstarted/not ready**. Per the
acceptance instruction, the exact new blocker is retained rather than hidden
behind a stochastic rerun.

## LLM-owned public metric copy correction — 2026-11-03

The retained Adjust failure above identified a deterministic public-output
contract defect: the verified renderer reconstructed reader prose from
`label`, `value`, unit, scope, confidence, and the diagnostic claim ledger.
That produced the malformed `around 31% percent of marketers` output and made
the visible derived metric appear to be the repair target. The final
`insights_final` call did not have an editable, reader-facing metric sentence
that could be reviewed and repaired independently.

The smallest correction keeps the existing final-insight call, evidence
bindings, and public semantic-review call. It adds optional
`metric_public_copy` to the existing final-insight, metric-spine, and key-figure
contracts. `insights_final` now asks GPT-6 Luna High for one concise,
source-faithful sentence when the complete metric tuple is available; the
bounded repair prompt gives the same leaf an exact, atomic repair contract.
Protected metric fields, evidence IDs, pages, spans, and source identity are
still restored from the authoritative candidate and are never replaced by the
copy. The selection identity advanced to
`evidence_backed_shortlisting:27`; public semantic-review cache identity
advanced from `v22` to `v23`.

Derived metric-spine and key-figure projections now carry the validated copy
alongside their structured fields. In verified mode, a missing copy is omitted
from reader-facing metric surfaces rather than serialized from the universal
claim ledger. The ledger remains an audit/diagnostic projection; it is not
rendered as public metric prose. Visible metric review items use the copy and
route wording defects to
`insights_final[item=<stable_id>].metric_public_copy`; implication defects
remain on `so_what`/`now_what`, and factual defects remain on protected metric
authority. No new provider call, validator, service, or regeneration root was
introduced.

### Provider-free regressions

The retained-authority replay and focused contract tests demonstrate that a
supported copy survives final normalization, selection, metric-spine and
key-figure derivation; missing verified copy is omitted; diagnostic
`label=`/`value=` serialization is not exposed; the natural copy is rendered;
and a semantic review issue resolves to the exact final-copy leaf. The repair
prompt explicitly preserves protected fields and fails closed when a complete
source-backed sentence cannot be stated. These tests do not claim live model
quality improvement; the previous live Adjust run remains the baseline to be
replayed after hosted CI.

### Prompt fixture baseline refresh

The committed baseline was regenerated with the repository tooling and current
pricing/configuration. No threshold, fixture, model, or pricing value was
changed to manufacture a pass.

| Scope | Previous baseline | New baseline | Change |
| --- | ---: | ---: | ---: |
| Total input tokens | 80,111 | 81,377 | +1,266 (+1.58%) |
| Total output tokens | 34,136 | 34,136 | 0 |
| Total tokens | 114,247 | 115,513 | +1,266 (+1.11%) |
| Estimated corpus cost | `$0.025078` | `$0.025204` | +`$0.000126` (+0.50%) |

The affected families were publishing (+462 input tokens, +`$0.000046`),
validation (+519, +`$0.000052`), and report (+285, +`$0.000028`). The largest
namespace changes were `insights_final` (+293),
`validate/public_editorial_quality` (+519),
`regenerate/insights_final` (+140), and schema-bearing context/selection
prompts (+29 to +170). The increase is the intentional contract and
source-scope text needed for LLM-owned metric copy, complete semantic review,
and bounded copy repair. The unchanged prompt regression gate passed with all
regression thresholds intact.

### Current verification status

Focused tests, changed-file Ruff, changed-source mypy, contract-schema
snapshot validation, and the prompt fixture gate pass locally. Hosted CI and
the one post-CI isolated provider-backed Adjust run are still required. Until
that run produces HTML and the final HTML is independently checked against PDF
pages 11, 19, 21, 29, and 35, this correction is **PARTIAL / NO-GO** for
Step 2 promotion. No WordPress or publication write is permitted.

## Post-CI isolated Adjust acceptance — 2026-11-03

Hosted CI completed successfully before this attempt: workflow `41646173342`
(`https://github.com/mbrakker/marketlense/actions/runs/41646173342`) passed
`ci_start`, `tests`, both mutation partitions, and `release_evidence`. The
attempt below is the one and only fresh provider-backed run after that CI result;
it used commit `53971638484ef09cf00d486cf8087f04b1da260c`, a new isolated state,
cache, and output root, the unchanged frozen Adjust PDF, and the WordPress queue
disabled.

Source and artifacts:

- PDF SHA-256:
  `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`
- Cohort result:
  `C:\ml-cross-contract-live-1103-public-copy-53971638\frozen-reliability-90z_l3zl\cohort_result.json`
- Attempt root:
  `C:\ml-cross-contract-live-1103-public-copy-53971638\frozen-reliability-90z_l3zl\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-52mv5d_j`
- Artifacts:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`
- Public-quality pack:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\public_editorial_quality_before.json`
- Terminal validation:
  `...\output\mobile-app-trends-2026-pdf\report_analysis\validation.json`
- Full-page PDF review renders:
  `C:\ml-cross-contract-live-1103-public-copy-53971638\pdf_full_pages\page-{11,19,21,29,35}.png`

### Terminal outcome and measured usage

| Measure | Current run | Previous retained baseline | Change |
| --- | ---: | ---: | ---: |
| Visual candidates evaluated / admitted / quarantined | 7 / 7 / 0 | 7 / 7 / 0 | unchanged |
| Verified facts / final insights | 7 / 7 | 7 / 7 | unchanged |
| Unsupported / unresolved retained factual claims | 0 / 0 | 0 / 0 | unchanged |
| Provider calls | 159 | 152 | +7 (+4.6%) |
| Input / output tokens | 1,217,027 / 216,421 | 1,033,800 / 185,087 | +183,227 / +31,334 (+17.7% / +16.9%) |
| Cached input tokens (usage ledger) | 21,568 | not retained in baseline summary | measured only in current run |
| Estimated cost | `$0.242970` | `$0.209313` | +`$0.033657` (+16.1%) |
| File-search calls | 6 | 6 | unchanged |
| Wall-clock | 1,824.185 seconds | 1,669.032 seconds | +155.153 seconds (+9.3%) |
| Structured-output recovery calls / automatic repairs | 3 / 0 | 0 / 0 | +3 / unchanged |
| Workflow attempts / retries / operator intervention | 1 / 0 / 0 | 1 / 0 / 0 | unchanged |
| Validation / publication readiness | `fail` / `fail` | `fail` / `fail` | unchanged |
| Terminal failure | `regeneration_target_item_unchanged` | `regeneration_target_item_unchanged` | unchanged |

The usage ledger records model `gpt-6-luna`; its execution metadata records
`reasoning_effort=medium`, so this run is not evidence of a GPT-6 High execution.
The isolated application cache started empty. The ledger recorded 105 calls with
cache enabled, 12 provider-cache hits, and 42 calls with caching disabled. The
three structured recovery calls were bounded grounding recovery events; there
were no automatic editorial repairs and no operator intervention. WordPress
publication was not attempted (`published=false`, no post ID, and the publish
queue was disabled).

The new copy contract itself is present in the live artifacts: all seven
`insights_final` rows have source-bound `metric_public_copy`; six derived
`metric_spine` rows and five `key_figures` rows carry the corresponding copy.
The 31% copy is the natural sentence `Only around 31% of marketers report
complete satisfaction with their ability to unify and read data across
platforms.`; it does not contain diagnostic `label=`/`value=` serialization.
The protected metric objects, verified-fact IDs, source identity, PDF SHA, and
physical pages remain intact. The universal claim ledger still contains its
structured diagnostic projection by design; no HTML was produced to assert its
reader-facing absence.

### Public/editorial outcome

The run failed before final HTML emission. The retained public-quality pack has
three hard errors:

1. `insight-ai-maturity-efficiency.so_what` says disciplined execution itself
   is the gap, while the source describes a gap between experimentation and
   disciplined execution. This is a semantic interpretation error, not a
   protected-fact binding failure.
2. `linkedin_post` says casino and slots sessions declined while installs
   increased but omits the material 2024–2025 comparison boundary. The issue
   is repair-eligible, but no successful repair was committed in this run.
3. The report-level review found a repeated strategy subset in the claim ledger
   and missing source-limit qualifications for the satisfaction and GenAI
   findings (including unstated timeframe, geography, denominator, sample size,
   and measurement method). It has no single safe atomic repair target and
   abstained.

The previous malformed 31% concatenation was not present in the live
`insights_final`, `metric_spine`, or `key_figures` artifacts. This is evidence
that the new field survives the generation and derived-artifact path, but not
evidence of accepted public HTML because `regeneration_target_item_unchanged`
stopped the run. The page-19 final insight text remains source-grounded for
strategy, casino, and slots, but its new metric copy names only the strategy
pair; the independent review therefore treats broader coverage as unresolved,
not as an improvement claim.

### Independent PDF audit

Full original pages were rendered and inspected, without cropping:

- Page 11 visibly states “only around 31% of marketers” report complete
  satisfaction with cross-platform data unification/readability; it gives no
  survey timeframe or geography.
- Page 19 visibly labels the chart as global 2024–2025 YoY and supports
  hyper-casual `+4%` installs/`+31%` sessions, strategy `-1%`/`+57%`, casino
  `+22%`/`-5%`, and slots `+46%`/`-5%`, with the legend distinguishing installs
  from sessions.
- Page 21 visibly supports global gaming CPI `$0.56` in 2025, up 30%, and
  separately shows slots `$4.47`, idle RPG `$3.19`, and strategy `$1.03`.
- Page 29 visibly supports global e-commerce CPI `$1.00` to `$0.98`, deal
  discovery `$1.44` to `$2.26`, marketplace/classifieds `$0.99` to `$0.88`,
  shopping `$0.93` to `$0.91`, and the regional bonus figures.
- Page 35 visibly supports finance install/session growth of global `-4%`/`+21%`,
  APAC `+5%`/`+50%`, Europe `+15%`/`+19%`, LATAM `+76%`/`+57%`, MENA
  `+42%`/`+10%`, and North America `+5%`/`+17%`. The missing regional finance
  coverage is therefore a real omission, not a source-binding ambiguity.

No independently confirmed unsupported material claim was promoted in the
verified-fact layer. Because the workflow produced no HTML, internal-ID
exclusion, final rendered completeness, visible metric-copy use, and
publication readiness remain unverified.

### Decision

**PARTIAL / NO-GO.** The implementation is pushed and hosted CI is green, but
the one permitted live run failed with the exact terminal blocker
`regeneration_target_item_unchanged`; it also exposed the three editorial
quality errors above. The live result shows source-faithful metric-copy
generation and derived propagation, but no accepted HTML and no evidence that
the remaining implication, qualification, or coverage defects are repaired.
Per the task constraint, no stochastic live rerun was attempted. Step 2
remains **PARTIAL/NO-GO** and Step 3 remains **unstarted/not ready**.

## Remaining editorial E2E and public-output corrections — 2026-11-03

This checkpoint addresses the retained Adjust failure and the latent
cross-stage public-output gaps without adding a validator, provider stage, or
publication path. The implementation is on top of the retained branch HEAD
and preserves the unrelated working-tree ZIP modification.

### Root causes and targeted corrections

| Observed defect | Earliest responsible boundary | Correction | Evidence |
| --- | --- | --- | --- |
| A repair response could apply a syntactically valid patch that changed no artifact value. The retained live audit only records `regeneration_target_item_unchanged`; it does not preserve the exact attempted field. | Atomic repair decision validation, after patch application and protected-field checks | Reject an unchanged candidate with the existing typed provider-rejection path as `patch_has_no_effect`; retain the existing bounded recovery/ABSTAIN handling. | Direct decision regression plus the existing targeted regeneration contract. The old audit cannot identify the exact leaf. |
| Verified review inspected public rows different from those rendered: unbound/legacy topic sources and over-broad summary/derived lists could be reviewed while the renderer suppressed or replaced them. | Shared verified public-surface projection | Reuse the existing verified topic, metric-spine, key-figure and claim-support projections for review and rendering; cap review inputs to the visible summary rows and bounded quote rows. Normal mode is unchanged. | Verified review/render parity regressions and provider-free retained replay. |
| Verified public metric sentences could repeat in metric spine, key figures and claim support. | Verified public advisory normalization | Deduplicate only exact normalized text with the same evidence-ID set, retaining metric spine as the canonical visible placement. Distinct wording or evidence remains distinct; normal mode is unchanged. | Exact-deduplication regression and public-quality missing-copy regression. |
| Verified summary claim maps could retain a legacy primary evidence ID even when a secondary ID was the authoritative verified binding. | Verified claim-map normalization | Select the first intersecting verified evidence ID rather than the first supplied ID; unbound rows remain omitted. | Secondary-binding regression in `test_pre_e2e_integrity.py`. |
| Final insight copy could lose complete admitted metric context before semantic theme coverage, so material subrelationships were not visible to the coverage review. | Final-insight-to-coverage handoff | Merge the complete authoritative metric and verified proposition into coverage input by stable verified-fact identity; pass the complete admitted-fact roster, not only plan-linked IDs. Final-only metric fields are not trusted in verified mode. | Unknown nested metric-field regression and focused verified-authority suite. |
| Source-grounded interpretation could reverse a gap/relationship, and bounded LinkedIn comparisons could lose their period/category boundary. | Existing final-insight and LinkedIn prompt contracts | Add narrowly scoped instructions to preserve direction, both sides, period, population, category and qualification. No schema or model-routing change. | Prompt assertions and fixture regression. |

The previous retained run's three public-quality failures remain the live
quality targets: the AI-maturity gap interpretation, the unscoped casino/slots
comparison, and the report-level strategy/qualification coverage. These are
not declared repaired by provider-free replay alone.

### Provider-free retained Adjust replay

The retained artifacts were replayed through the current deterministic public
quality, verified review-input, advisory-normalization and render-view paths.
No provider call, publication write, or final artifact mutation occurred.

| Check | Result |
| --- | --- |
| Retained terminal state | Historical `regeneration_target_item_unchanged`; exact attempted leaf unavailable from the retained audit |
| Deterministic public-quality evaluation | `pass`; no deterministic issues |
| Public review items | 45: summary 8, expert comment 6, LinkedIn 4, final insights 21, metric spine 1, advisory 1, claim ledger 4 |
| Rendered visible surfaces | summary claim map 5, signal cards 0, key figures 0, metric spine 1, claim support 4, visible insights 7, quotes 0 |
| Verified topic cards | 0; all retained `topics_covered` rows were `toc_only` with no bound verified evidence |
| Composite metric display | Omitted by the existing fail-closed public metric-display contract; no speculative numeric enrichment was added |
| Source-bound metric copy | Retained satisfaction copy remains natural source-backed prose and is carried into the metric spine; diagnostic `label=`/`value=` serialization is absent |

The replay confirms that the old no-op terminal is now rejected at the
existing repair boundary and that review/render projections use the same
verified eligibility rules. It does not prove live model correction, complete
topic coverage, composite-metric display, HTML completeness, or publication
readiness. The retained artifacts contain no source-bound topic-card evidence
from which to reconstruct those surfaces safely.

### Local verification before the permitted live run

The focused cross-stage suite passed **796 tests** and the grounding/prompt
suite passed **299 tests**. The added secondary-binding regression and the
render/public-advisory subset passed **111 tests** after the final projection
correction. Changed-file Ruff and source mypy passed. The prompt fixture gate
also passed without baseline or threshold manipulation:

| Prompt corpus scope | Current | Committed baseline | Change |
| --- | ---: | ---: | ---: |
| Total tokens | 115,762 | 115,513 | +249 (+0.22%) |
| Estimated cost | `$0.025229` | `$0.025204` | +`$0.000025` (+0.10%) |
| Validation family | 12,134 | 12,134 | 0 |
| Publishing family | 47,201 | 46,952 | +249 |

The small increase is attributable to the added complete-fact coverage and
public-output contract wording. Existing fixture model configuration, pricing,
thresholds, schemas and all factual safeguards are unchanged.

Hosted CI and the one fresh isolated provider-backed Adjust run remain
required. Until that run produces and passes an independently inspected HTML
artifact, the implementation remains **PARTIAL / NO-GO** for Step 2
promotion; Step 3 remains unstarted.

## Single-report live Adjust acceptance — 2026-11-03

Hosted CI passed for commit `2f72700948f0ceb105b83eb82e5ef96c4fc5c90d` in
[workflow 41679969027](https://github.com/mbrakker/marketlense/actions/runs/41679969027).
One fresh, isolated provider-backed Adjust run then used the unchanged frozen
PDF SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` with
WordPress disabled and no publication write. The run ended in the normal
queue state `awaiting_review`; its validation and publication-readiness gates
passed and its HTML artifact was produced.

### Run identity and terminal result

| Measure | Result |
| --- | --- |
| Cohort/report | `cohort-b638414df0b1fccea1cd` / Adjust |
| Source identity | `source:8cb648b6bbd9dbae4ec1d915c38cf235` |
| Visual candidates | 7 evaluated, 7 admitted, 0 quarantined |
| Verified facts / final insights | 7 / 7 |
| Unsupported / unresolved retained factual claims | 0 / 0 |
| Validation / publication readiness | `pass` / `pass` |
| Public editorial quality | `pass`, 0 issues, 0 hard failures |
| Structured-output recovery / automatic repairs | 1 / 0 |
| Retries / operator intervention | 0 / 0 |
| Provider calls / file-search calls | 153 / 6 |
| Model / tokens | `gpt-6-luna`; input 1,132,247; output 189,734; cached input 19,716; reasoning 70,375 |
| Estimated cost / wall-clock | `$0.221315` / 1,551.242 s (core 1,548.0 s) |
| WordPress | disabled; published `false` |

Artifacts are retained at:

- Run root: `C:\ml-adjust-live-2f727009-1103\frozen-reliability-0fxrrova`
- Cohort result: `C:\ml-adjust-live-2f727009-1103\frozen-reliability-0fxrrova\cohort_result.json`
- Report attempt: `C:\ml-adjust-live-2f727009-1103\frozen-reliability-0fxrrova\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-rx770xep`
- Artifacts: `C:\ml-adjust-live-2f727009-1103\frozen-reliability-0fxrrova\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-rx770xep\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`
- Validation: `C:\ml-adjust-live-2f727009-1103\frozen-reliability-0fxrrova\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-rx770xep\output\mobile-app-trends-2026-pdf\report_analysis\validation.json`
- Public-quality report: `C:\ml-adjust-live-2f727009-1103\frozen-reliability-0fxrrova\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-rx770xep\output\mobile-app-trends-2026-pdf\report_analysis\public_editorial_quality_before.json`
- HTML: `C:\ml-adjust-live-2f727009-1103\frozen-reliability-0fxrrova\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-rx770xep\output\mobile-app-trends-2026-pdf.html`

### Comparison with the retained pre-fix Adjust run

The comparison run was commit `53971638`, which terminated at
`regeneration_target_item_unchanged` and produced no HTML. The current run
improved the terminal outcome and public gates, but the resource deltas are
not attributed solely to code because provider/cache behavior and model
selection are stochastic.

| Measure | Previous | Current | Change |
| --- | ---: | ---: | ---: |
| Visual admission | 7/7/0 | 7/7/0 | unchanged |
| Verified facts / final insights | 7 / 7 | 7 / 7 | unchanged |
| Unsupported / unresolved claims | 0 / 0 | 0 / 0 | unchanged |
| Provider calls | 159 | 153 | -6 (-3.8%) |
| Input tokens | 1,217,027 | 1,132,247 | -84,780 (-7.0%) |
| Output tokens | 216,421 | 189,734 | -26,687 (-12.3%) |
| Cached input tokens | 21,568 | 19,716 | -1,852 (-8.6%) |
| Reasoning tokens | 90,448 | 70,375 | -20,073 (-22.2%) |
| Estimated cost | `$0.242970` | `$0.221315` | -`$0.021655` (-8.9%) |
| File-search calls | 6 | 6 | unchanged |
| Wall-clock | 1,824.185 s | 1,551.242 s | -272.943 s (-15.0%) |
| Structured recovery | 3 | 1 | -2 |
| Automatic repairs | 0 | 0 | unchanged |
| HTML/readiness | absent / failed | present / pass | corrected terminal outcome |

The implementation-attributable evidence is the no-op repair rejection and
the shared verified review/render projections. The live run did not exercise
an automatic repair, so changed-repair acceptance remains regression-test
evidence rather than live evidence.

### Independent source and public-output audit

The original PDF was checked using full pages, without cropping, including
pages 6, 11, 19, 21, 29, 34 and 35. The retained final claims and their
authoritative source bindings were:

| Stable insight | Page(s) | Independent result |
| --- | ---: | --- |
| `global-app-growth-2025` | 6 | Adjust text supports 2025 installs +10% and sessions +7%, versus +8% and +2% in 2024. |
| `finance-global-install-session-divergence` | 34 | Finance installs -4% and sessions +21% in 2025 are supported; the final copy preserves the opposing measures. |
| `finance-latam-growth` | 35 | LATAM +76% installs and +57% sessions for 2024–2025 are supported; no denominator or sample size was invented. |
| `gaming-strategy-session-growth` | 19 | Strategy sessions +57% and installs -1% from 2024 to 2025 are supported by the text/chart relationship. |
| `ecommerce-cpi-subvertical-divergence` | 29 | Deal-discovery CPI `$1.44` to `$2.26` is supported; the final public copy does not substitute the broader e-commerce CPI. |
| `ecommerce-retention-2025` | 29 | Day 1 `13.2%` to `12.6%` and Day 7 `6.3%` to `6.0%` are supported and remain checkpoint-specific. |
| `cross-platform-data-satisfaction` | 11 | “Around 31%” is supported; the source supplies no survey period, geography, denominator or methodology, and the public wording adds none. |

Page 21 supports gaming CPI of `$0.56` in 2025, up 30%, and the separate
slots/idle-RPG/strategy values. That finding was not selected into this run's
seven final insights; it is an omission/selection limitation, not a factual
promotion. Likewise, the current selection differs from the prior run's
casino/slots, AI-maturity, gaming-CPI and paid/organic findings. This is
reported as provider selection variability and remaining breadth risk, not as
an improvement claim.

The produced HTML contains no `verified-fact:` tokens, evidence IDs or private
source paths in reader-facing surfaces. The required non-visible
`marketbearing-build` traceability comment still contains source/build
provenance, as required by the existing readiness contract; this is not
reader-facing evidence text. The visible report contains seven final insight
claims, a metric spine and claim-support surfaces, and no unsupported numeric
or material qualitative assertion was found in the independent review.

Two optional surfaces remain deliberately fail-closed: all twelve
`topics_covered` rows were `toc_only`, so the rendered signal section says no
report signals were extracted, and the quotes family abstained with the
existing `quotes_missing` warning. These do not invalidate the accepted
claims, but they mean this single run does not prove complete report-level
coverage or quote availability.

### Verdict

**PASS for the isolated single-report Adjust E2E acceptance.** The no-op
failure no longer blocks HTML generation, the final output passed validation,
public-editorial quality and publication-readiness gates, and the independent
PDF review found zero unsupported or unresolved material claims. **PARTIAL for
broader Step 2 effectiveness:** material source findings can still be omitted
by stochastic selection, and optional signal/quote surfaces were absent in
this run. Step 3 remains **unstarted** and must not be inferred ready from
this one-report result alone.

## Coverage and projection follow-up — 2026-11-04

This follow-up covers the bounded opportunity-pool change (`fe20442c`,
selection cache version `evidence_backed_shortlisting:28`), the verified
projection correction (`abfcc4f2`), and the test-contract follow-up
(`ab40dcf4`). The final branch state is
`ab40dcf4fd16ae04ee0a434e8a4679349eedb85e`.

### Adjust page-21 investigation

The exact frozen Adjust PDF SHA was
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.
Full-page inspection confirms that page 21 contains gaming CPI of `$0.56` in
2025, up 30%, plus the slots, idle-RPG and strategy values. The retained
authoritative findings pack contains the family-game retention finding but no
gaming-CPI finding. Candidate generation therefore had no eligible gaming-CPI
proposition to shortlist; this is an upstream finding-extraction omission, not
a shortlist-cap failure. No unsupported finding, page-specific patch or
keyword business-relevance score was introduced.

### Projection regression and correction

The first fresh provider-backed replay at `cf4cc640` failed closed at
`verified_fact_snapshot_invalid`: `key_figures[1]` retained multi-fact evidence
IDs but dropped the required per-fact spans. It made 147 provider calls, used
898,640 input and 127,859 output tokens, cost `$0.171184`, and ran for
1,379.625 seconds; it produced no HTML and made no publication write.

The root cause was deterministic public projection: `build_key_figures()` and
the downstream chart-card projection copied verified evidence IDs but not
`evidence_spans`. `abfcc4f2` preserves those spans in verified mode and adds a
regression that validates the complete multi-fact binding. Normal-mode
projection is unchanged. The follow-up test-only commit `ab40dcf4` updates
stale assertions for the intentional 10–12 opportunity pool and does not
alter production behavior.

### Corrected live replay

The fresh isolated replay at production commit `abfcc4f2` reused no final
artifact and disabled WordPress. The source identity and PDF hash matched the
expected frozen source. It reached 10 verified facts and 10 candidates, then
selected 6 final insights. The terminal outcome was `validation_failed`, with
no HTML and no WordPress write:

| Measure | Result |
| --- | ---: |
| Provider calls | 170 |
| File-search calls | 7 |
| Input / output tokens | 1,126,200 / 212,674 |
| Estimated cost | `$0.229790` |
| Wall-clock | 1,503.187 s |
| Automatic repairs | 3 targeted; all rolled back/ABSTAINed |
| Operator intervention | 0 |
| Verified-facts snapshot | pass; 10 facts, correct source SHA |

The failure was factual and editorial rather than a provenance bypass:

1. The final key figure said “global all-app CPI”, but page 29 supports global
   e-commerce apps and the All-versus-Deal-discovery comparison, not that
   broader wording. Grounding correctly rejected it.
2. The public-quality gate found admitted findings omitted from the final
   report: e-commerce retention, hyper-casual gaming, and LATAM finance
   growth. It also reported repeated surfaces and missing limitations for the
   AI-efficiency and satisfaction findings.

The repair audit shows unchanged evidence IDs, pages and spans; no repair
promoted unsupported evidence. The run therefore demonstrates that exact
source-backed opportunities now reach verified admission and that the strict
projection failure is fixed, but it does not demonstrate improved live final
selection coverage. The page-21 gaming-CPI omission remains a source-finding
limitation. The original PDF pages 9, 19, 21, 29, 34 and 35 were independently
reviewed; no unsupported claim was promoted.

### Verification and status

The focused regression suite passed (292 affected tests before the test-only
follow-up, plus 41 contract-follow-up tests). Editorial-quality tests passed
(76), render/public-prose tests passed (44), the public quality gate passed,
formatting passed, Ruff passed, and full mypy reported zero tracked errors.
Hosted workflow `41739013186` passed all jobs, including tests, both mutation
partitions and `release_evidence`.

The evidence verdict is **PASS for the deterministic verified-projection
correction and CI**, but **PARTIAL/NO-GO for broader Step 2 editorial
acceptance**. The live run correctly failed closed, produced no HTML, and
leaves final selection coverage and wording reliability unresolved. Step 3 is
not ready and remains unstarted.

## E2E editorial-quality correction replay — 2026-11-04

This is the one fresh provider-backed Adjust run required after the source-
context and planned-theme corrections. It used commit `8efbb03a0409058d989523ab5b2c4912b2dae4b9`, the frozen PDF
`C:\ml\out\browser_downloads\www.adjust.com\b6b998e34a7c\mobile-app-trends-2026.pdf`, and WordPress disabled. The PDF SHA-256 was independently rechecked as
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.

### Provider-free verification and hosted CI

The corrected focused suite passed **282 tests**. Changed-file Ruff,
repository formatting, and the repository mypy gate passed. The prompt fixture
gate passed without threshold or baseline manipulation: current total tokens
were 115,908 versus 115,513 baseline (**+395, +0.34%**) and estimated cost was
`$0.025243` versus `$0.025204` (**+$0.000039, +0.15%**); the validation family
was unchanged. Hosted workflow
[41785780616](https://github.com/mbrakker/marketlense/actions/runs/41785780616)
passed tests, both mutation partitions, `release_evidence`, and the prompt
fixture gate. No new provider run was started after the result below.

### Live terminal result

| Measure | Result |
| --- | ---: |
| Run root | `C:\ml-e2e-editorial-fix-live-8efbb03a-20261104\frozen-reliability-wh8h9nf_` |
| Report attempt | `...\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-wvfd3heq` |
| Admission | admitted; one isolated report |
| Terminal state | `failed` |
| Terminal code | `artifact_final_insight_coverage_invalid` |
| Terminal message | `Semantic theme coverage omitted planned themes` |
| Provider calls | 144 |
| Input / output tokens | 630,023 / 107,020 |
| Estimated cost | `$0.128900` |
| Wall-clock | 1,153.899 s |
| File-search calls | 5 |
| Structured recovery / automatic repairs | 0 / 0 |
| Operator intervention / WordPress writes | 0 / 0 |
| HTML / publication readiness | not produced / fail |

The ledger records ten visual-claim correction calls and ten corresponding
verification calls for the ten retained claim identities. It also records one
`insights_candidates` call, two `insights_final` calls (primary and semantic
repair), and three independent theme-coverage calls (primary, semantic repair,
and bounded source-candidate fallback). Because the workflow failed before
final artifact persistence, there is no authoritative final candidate count,
final insight roster, HTML, or terminal verified-facts artifact to report; the
cohort result records
`verified_facts_architecture_evidence=FileNotFoundError`.
Those counts are intentionally not inferred from provider-call counts.

### Provenance and root-cause lineage

The source-finding correction was exercised successfully in the live run:

| Stage | Observed result |
| --- | --- |
| Original PDF page 21 | Full-page text states: “Gaming CPI rose globally to $0.56 in 2025, up 30%.” |
| DocMap | Gaming section now includes the CPI proposition in its third key point and retains pages 17–24. |
| Findings | 45 findings were materialized, including `gaming-global-cpi`, page `21`, and direct evidence text for `$0.56` and `30%`. |
| Evidence fidelity | `gaming-global-cpi` binds to `source:page:21`; status `supported`, semantic outcome `entailed`, and the pack totals report 0 unsupported / 0 unresolved findings. |
| Step 1 / final selection | Not available as a terminal artifact because the later coverage failure aborted persistence. |
| Public projection / HTML | Not reached; no “global all-app CPI” wording was promoted and no unsupported claim can be credited as verified. |

This separates the fixed upstream omission from the remaining downstream
blocker. The earlier live failure’s overbroad “global all-app CPI” wording and
omitted e-commerce-retention, hyper-casual, and LATAM-finance findings are not
repeatedly treated as fixed: the current run stopped before a final public
projection could test them. The source page 21 and page 29 full-page text were
reviewed directly; no crop or topic-only inference was used.

The new failure is a real coverage-contract defect exposed by the correction:
the independent semantic coverage boundary now evaluates all planned themes,
but the bounded final-insight repair/fallback path did not produce a roster
that the model assessed as substantively covering every planned theme. The
workflow correctly failed closed as non-retryable. The retained audit exposes
the terminal message and repair stages, but does not retain the raw semantic
coverage response or a final artifact, so the exact model-selected omitted
theme list is not reconstructible from this run. No speculative post-failure
change or second paid replay was made.

The three targeted repairs recorded for the previous `abfcc4f2` run remain
unchanged evidence: both candidate attempts were rolled back/ABSTAINed, their
source bindings and evidence lineage passed mutation checks, and no repair
promoted an unsupported fact. The current run performed no automatic repair.

### Resource comparison (not a quality improvement claim)

Against the previous failed Adjust replay (`abfcc4f2`: 170 calls, 1,126,200
input, 212,674 output, `$0.229790`, 1,503.187 s, 7 file-search calls), this
run used 26 fewer calls, 496,177 fewer input tokens, 105,654 fewer output
tokens, `$0.100890` less estimated cost, 349.288 fewer seconds, and two fewer
file-search calls. Against the prior successful replay (`2f727009`: 153 calls,
1,132,247 input, 189,734 output, `$0.221315`, 1,551.242 s, 6 file-search
calls), the run also used fewer resources. These deltas are not attributable
to quality improvement: the current run terminated earlier and produced no
accepted final article.

### Verdict

**PARTIAL / NO-GO.** The live run demonstrates the page-21 retrieval and
source-binding correction, and all provider-free and hosted gates are green.
It does not satisfy E2E acceptance because planned-theme coverage still fails
closed before final artifact persistence; there is no final HTML to inspect,
no live proof of the corrected CPI scope in public copy, and no evidence that
the missing admitted findings, repetition, or limitations are resolved. Step 2
remains broader **PARTIAL**, E18 remains active, and Step 3 must not begin.

## Verified editorial selection/recovery — 2026-11-05

This is the one fresh provider-backed Adjust run required for the selection and
recovery correction at commit `db1d317b5a3a4eeabae9faab4e92bbedc95c0141`.
It used an isolated worktree and fresh application state, the exact frozen PDF
SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, and
WordPress was disabled. No final artifact was reused; normal provider-side
caching was allowed. The required live run was not retried after its terminal
failure.

### Deterministic correction and provider-free evidence

The implementation bumps the evidence-backed shortlist cache identity from
`:28` to `:29`, recomputes the final target after the authoritative verified
editorial plan, keeps an independent 10-item admitted candidate pool, requires
an authored source-bound roster, removes raw verified-fact projection and
post-repair deterministic backfill, and fails closed when semantic coverage is
incomplete. Final theme coverage now also requires the selected insight's
canonical evidence ID to support the planned theme. Bounded terminal
diagnostics retain only plan theme names/priorities/fact IDs, final roster and
bound IDs, per-theme verdict/support/reason, missing themes, substitutions and
terminal classification; raw prompts, responses and source extracts are not
added to standard audit output.

The focused regression set passed **69 tests**; the verified-authority suite
passed **67**, and the artifact/generator/evidence suite passed **246**.
Repository-native Ruff, formatting, mypy (786 files, zero errors), architecture,
forbidden-patching, bounded-logging and prompt-fixture gates passed. The full
provider-free suite completed with **8,473 passed, 2 skipped and 1 failure**:
the existing native-wheelhouse test requires CPython 3.12, while this local
interpreter is CPython 3.14.2. Hosted workflow
[41936819813](https://github.com/mbrakker/marketlense/actions/runs/41936819813)
passed tests, both mutation partitions and `release_evidence` at the
implementation commit.

### Live selection and terminal evidence

The run admitted all **10/10** verified facts and visual candidates, with
**0 quarantined** and the expected source identity and PDF hash. The retained
candidate pool contained these stable IDs:
`insight-01`, `insight-02`, `insight-03`, `insight-04`, `insight-05`,
`gaming-strategy-growth`, `ecommerce-session-length`, `finance-latam-growth`,
`conclusion-vertical-trends`, and `gaming-download-ranking`. The authoritative
plan authored five themes bound to `insight-01` through `insight-05`; the
retained final roster therefore contained those five IDs and did not use raw
fact projections as public prose.

The final public-quality gate correctly rejected the result for two reasons:

1. `insight-01.metric_public_copy` changed the source's “small group of
   organizations with advanced deployment” into “advanced GenAI deployers”,
   which broadens the population while retaining the number.
2. The complete admitted fact map contained two material findings absent from
   the public roster: the conclusion-level vertical trends
   (`conclusion-vertical-trends`) and the worldwide 2025 gaming-download
   ranking (`gaming-download-ranking`, Block Blast! first and ROBLOX second).

The existing transactional regeneration attempted to repair the failed
editorial bundle but returned no declared change and terminated with
`regeneration_target_item_unchanged`. The workflow consequently failed
closed; there was no HTML, no publication-readiness pass, no WordPress write,
and no unsupported or unresolved retained factual claim was promoted. This is
an actual downstream quality failure, not a selection checkpoint omission.

### Live resource ledger and artifact paths

| Measure | Result |
| --- | ---: |
| Provider calls | 163 |
| File-search calls | 6 |
| Input / output tokens | 1,300,462 / 214,310 |
| Ledger cached input tokens | 17,864 |
| Estimated cost | `$0.250594` |
| Wall-clock | 1,705.877 s |
| Structured-output recoveries | 2 |
| Automatic repairs | 0 |
| Workflow retries / operator intervention | 0 / 0 |
| Validation / publication readiness | fail / fail |

The retained evidence is available at these local paths: the cohort result
`C:\ml-e2e-selection-recovery-live-db1d317b-20261105\frozen-reliability-2vcyvzd3\cohort_result.json`,
artifact checkpoint
`C:\ml-e2e-selection-recovery-live-db1d317b-20261105\frozen-reliability-2vcyvzd3\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-b5pli5ly\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`,
validation result
`C:\ml-e2e-selection-recovery-live-db1d317b-20261105\frozen-reliability-2vcyvzd3\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-b5pli5ly\output\mobile-app-trends-2026-pdf\report_analysis\validation.json`,
and workflow database
`C:\ml-e2e-selection-recovery-live-db1d317b-20261105\frozen-reliability-2vcyvzd3\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-b5pli5ly\state\workflow.sqlite`.
The source PDF used for the run is
`C:\Programing\Market lense\out\browser_downloads\www.adjust.com\b6b998e34a7c\mobile-app-trends-2026.pdf`.

### Verdict

**PARTIAL / NO-GO for live editorial acceptance.** The deterministic selection
and recovery safeguards are implemented and regression-tested, and the live
run proves that verified-fact admission and candidate retention completed with
the expected provenance. It does not prove acceptable final editorial quality:
the plan/roster omitted material admitted findings, one protected population
qualifier was broadened, and transactional repair failed closed without an
HTML artifact. The implementation shows no live improvement claim beyond the
provider-free contract evidence. E18 remains **Active/PARTIAL**, Step 2 remains
**PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**. The remaining
material blockers are final-plan coverage completeness and successful
transactional repair of a substantive editorial wording defect; no further
provider retry was made for this checkpoint.

## Verified editorial regeneration and theme coverage — 2026-11-05

This entry records the remediation of the failed Adjust regeneration run above.
The final implementation state is commit
`b346f1235fa2e27348db59425e0424df70958acd`; hosted CI workflow
[41993003205](https://github.com/mbrakker/marketlense/actions/runs/41993003205)
passed `ci_start`, the full test/coverage job, both mutation partitions, and
`release_evidence`. The correction stayed within the existing editorial-plan
and final-insight prompt namespaces. It strengthened the existing requirement
to represent every materially distinct admitted fact and made every planned
theme a hard final-roster coverage requirement. It did not add a validator,
service, LLM stage, deterministic business-relevance scorer, or post-selection
fact backfill.

### Before/after live evidence

The first fresh run from `0b82c8b49f22d91e302725742fad925fb4379075` was a real
failure, not an unexplained empty checkpoint. It admitted the source-backed
candidate pool but terminated at `artifact_generation` with
`artifact_final_insight_coverage_invalid` / `Semantic theme coverage omitted
planned themes`, after the bounded final-selection repair still failed its
coverage check. It produced no final `artifacts.json`, HTML, validation pass,
or WordPress write. The retained audit did not preserve the raw provider
responses or exact omitted-theme names, so this ledger does not infer them.

The targeted correction was then verified in a new isolated worktree and fresh
application state. The corrected run used the exact frozen PDF SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, the
source identity recorded in the artifacts, and WordPress disabled. Its
terminal state is the expected shadow-review state `awaiting_review`, with
validation and publication readiness both `pass`.

| Measure | Pre-fix run (`0b82c8b4`) | Corrected run (`b346f123`) |
| --- | ---: | ---: |
| Visual/verified facts admitted | 10/10 (no quarantine) | 10/10 (no quarantine) |
| Planned themes / final selected themes | coverage invalid / no terminal artifact | 7 / 7, omitted themes 0 |
| Final insights persisted | none | 7 |
| Validation / publication readiness | fail / fail | pass / pass |
| Provider calls | 145 | 169 |
| Input / output tokens | 721,591 / 136,351 | 1,221,126 / 224,368 |
| Ledger cached input tokens | 1,196 | 21,568 |
| Estimated cost | `$0.155223` | `$0.249857` |
| Wall-clock | 1,458.482 s | 1,812.369 s |
| File-search calls | 6 | 7 |
| Structured-output recoveries | 2 | 3 |
| Automatic repairs / workflow retries | 0 / 0 | 0 / 0 |
| WordPress writes | 0 | 0 |

The corrected run costs `$0.094634` more (+60.95%) and takes 353.887 seconds
longer (+24.27%) than the failed pre-fix run because it completes the full
editorial, grounding, rendering, and readiness path. This is a resource
regression relative to a failed run, not a claim of efficiency improvement.
Against the earlier `db1d317b` selection/recovery run (163 calls,
`$0.250594`, 1,705.877 seconds, no HTML), the corrected run is six calls
more, `$0.000737` cheaper, and 106.492 seconds slower; the meaningful change
is that it now completes with an inspectable HTML artifact and passing gates.

### Selection, evidence handover, and source audit

The admitted verified-fact set contained ten stable facts. The final seven
insights retained the following stable primary identities and canonical source
pages; composite entries retain the additional fact bindings shown rather than
silently dropping them:

| Final insight | Canonical source pages | Retained material evidence |
| --- | ---: | --- |
| `insight-001` | 3 | More than 112.1 billion app downloads in 2025; no invented geography or category split. |
| `insight-002` | 11, 40 | Around 31% marketer satisfaction finding plus the qualitative touchpoint/long-term-value outlook. |
| `insight-003` | 9 | Most organizations low/moderate GenAI maturity; a small advanced-deployment group reportedly achieved over 20% efficiency gains. |
| `insight-004` | 19, 40 | Global strategy-game sessions +57% and installs −1% YoY, with the retention/reach outlook. |
| `insight-005` | 27, 28, 40 | Global e-commerce installs −10%, sessions +5%, average session length 10.04 to 9.6 minutes, and the AI-personalization/agents outlook. |
| `insight-006` | 34, 35, 40 | Global finance installs −4% and sessions +21%; LATAM +76% installs and +57% sessions; finance-app outlook. |
| `insight-008` | 37 | Global finance CPI $1.51 to $1.13; payment CPI separately +29% to $1.44 with its unspecified geography/years preserved. |

The two admitted facts not used as standalone final IDs (`insight-007` LATAM
finance growth and `insight-009` e-commerce session length) remain in the
authoritative `evidence_ids` of `insight-006` and `insight-005`, respectively.
The qualitative `conclusion-vertical-trends` fact is similarly retained in
the composite evidence bindings. The final coverage record reports seven
supported themes, seven selected themes, and zero omitted or omitted-central
themes. The bounded semantic coverage repair was exercised: its initial
coverage feedback named five omitted themes, then the repair succeeded without
adding or displacing a stable final ID.

The original PDF was independently checked at physical pages 3, 9, 11, 19,
27, 28, 34, 35, 37, and 40. The checked text confirms the download threshold,
31% population and subject, GenAI population qualifier, strategy-game legend
mapping, e-commerce install/session and session-length relationships, global
and LATAM finance relationships, CPI scopes, and the qualitative conclusion.
The required PDF hash and source identity are present in every verified fact.

The final HTML is at
`C:\ml-e2e-editorial-regeneration-live-b346f123-20261105\frozen-reliability-reijifz2\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mckv372o\output\mobile-app-trends-2026-pdf.html`.
The authoritative artifact is at
`C:\ml-e2e-editorial-regeneration-live-b346f123-20261105\frozen-reliability-reijifz2\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-mckv372o\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`.
Validation, retained-claim validation, public-quality before/after, and
readiness artifacts are in the same `report_analysis` directory. Public
quality passed before and after with zero issues; source-note completeness and
action specificity were 1.0, repeated syntax was 0, and average insight
length was 39.14 words. The rendered HTML contains no `verified-fact`, stable
candidate, or other internal evidence identifiers, and no WordPress markers.
The only validation warning is the pre-existing abstention of the optional
`quotes` family; it is not a material factual or readiness failure.

### Verdict and remaining scope

**Targeted Adjust regeneration acceptance: PASS.** The same class of failure
that previously stopped before HTML now produces a complete, source-bound
seven-insight HTML artifact with zero unsupported or unresolved retained
factual claims, passing public editorial quality, validation, and publication
readiness. The public population-broadening defect did not recur: the GenAI
wording preserves “a small group with advanced deployment” and the source
qualifiers remain in the canonical metric/evidence handover.

**Overall Step 2: PARTIAL / NO-GO for broader promotion.** This is one
corrected Adjust report, not the frozen-five cohort or a fresh generation
effectiveness study. Normal Luna variability and the additional bounded
coverage call cannot be separated completely from the prompt correction by
this single run. E18 remains **Active/PARTIAL** and Step 3 remains
**unstarted/not ready**. No Step 3 implementation or publication write was
performed.

## Frozen five-report E2E acceptance and full artifact retention — 2026-11-05

The exact authoritative frozen cohort
docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json was
executed once at fixed producer SHA
95379a8decc5d4f1ca814170619e832c8bacf95f using a fresh isolated run root,
--verified-facts-architecture, no shared batch and no publication flag. The
run identity is frozen-reliability-oboqn82y and the retained evidence package
is
docs/quality/reliability-cohort-20261001-next-five/verified-facts-20261105-95379.
The provider-backed command was:

    python -u scripts/quality/run_frozen_reliability_cohort.py \
      --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json \
      --runs-root C:\ml-frozen-five-live-95379-20261105 \
      --sources-root C:\Programing\Market lense \
      --max-duration 7200 \
      --verified-facts-architecture

No production code, prompt or validator was changed during this experiment.
No report was restarted after a terminal failure, and there were zero
publication attempts or WordPress writes.

### Aggregate result

| Measure | Frozen-five result |
| --- | ---: |
| Reports admitted | 5 / 5 |
| Terminal complete | 0 / 5 |
| Terminal failed | 5 / 5 |
| Final HTML artifacts | 0 |
| Provider calls | 914 |
| Input tokens | 4,168,035 |
| Output tokens | 840,654 |
| Estimated cost | $0.937278 |
| Wall-clock | 9,202.773 s |
| Automatic repairs | 0 |
| Workflow retries | 0 |
| Operator interventions | 0 |
| Publication attempts / writes | 0 / 0 |

The terminal outcomes are mutually exclusive and are taken from the
machine-readable cohort result: four
artifact_final_insight_coverage_invalid failures and one
validation_failed failure. The frozen-five verdict is FAIL / NO-GO. This
run does not support a Step 3 start.

### Per-report outcome and failure reasons

| Report | Calls | Cost | Duration | Terminal result | Reason / retained output |
| --- | ---: | ---: | ---: | --- | --- |
| Capgemini | 95 | $0.124882 | 1,291.421 s | artifact_final_insight_coverage_invalid | Final insight coverage validation stopped artifact generation; no final artifact or HTML. Findings/evidence-fidelity records were retained for diagnosis only. |
| Activate | 470 | $0.270949 | 3,585.285 s | artifact_final_insight_coverage_invalid | Final insight coverage validation stopped artifact generation; evidence fidelity also recorded one unsupported result. No final artifact or HTML. |
| KPMG | 95 | $0.144853 | 1,165.343 s | artifact_final_insight_coverage_invalid | Final insight coverage validation stopped artifact generation; no final artifact or HTML. Findings/evidence-fidelity records were retained for diagnosis only. |
| Reuters Institute | 94 | $0.165084 | 1,431.846 s | artifact_final_insight_coverage_invalid | Final insight coverage validation stopped artifact generation; no final artifact or HTML. Findings/evidence-fidelity records were retained for diagnosis only. |
| Adjust | 160 | $0.231510 | 1,728.878 s | validation_failed | Verified-fact admission and source hash passed, but public editorial quality rejected repeated e-commerce/finance output and a GenAI limitation omission. Artifact exists; no HTML or readiness. |

The exporter retained the same Pareto counts (4 coverage failures, 1
validation failure). The four coverage failures expose no detailed inner
validator diagnostic in the terminal contract, so their exact omitted-theme
sets are not inferred here. That missing diagnostic is itself a remaining
operational limitation, not evidence that the reports were factually correct.

### Independent source and editorial review

The exact Adjust PDF SHA was
ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3; it has
41 physical pages. Pages 3, 9, 19, 21, 27, 29, 34, 35 and 36 were inspected
against the seven retained Adjust insights. The numeric relationships,
populations and qualifications in those retained insights are supported by
the corresponding source pages, including the page-9 restriction that
efficiency gains over 20% apply to a small group with advanced deployment.
Page 35 does not provide counts or denominators, and none were invented.
This is not a publication pass: the run failed public editorial distinctness
and limitation completeness before HTML.

Capgemini, Activate, KPMG and Reuters had no final public output to inspect.
Their retained findings and evidence-fidelity artifacts are diagnostic
evidence only. Consequently, the run confirms zero independently confirmed
unsupported material claims marked verified, but cannot claim zero factual
errors in final public output for four reports because no such output existed.

### Artifact retention and exclusions

The evidence package contains the cohort result and manifests, provider-free
preflight, per-report source/cohort records, checkpoints, findings,
verification/validation/export projections, reuse records, safe derived
images and visual-canary fingerprints. artifact_manifest.json inventories
all 2,470 runtime files and 874 retained package files with runtime-relative
paths, repository-relative paths, sizes, SHA-256 hashes and committed/excluded
status. Raw state, caches, databases, raw provider/usage ledgers and local
runtime configuration are listed as excluded with reasons and hashes. Source
PDF bytes are not committed; source_identity_manifest.json records the
frozen MD5 values, actual SHA-256 values, physical page counts and retrieval
references. The initial dirty-worktree setup block and the environment
preflight block are recorded in run_invocation_failures.json.

The package link after the evidence commit is:
https://github.com/mbrakker/marketlense/tree/codex/fix-retained-insight-evidence-validation/docs/quality/reliability-cohort-20261001-next-five/verified-facts-20261105-95379.

### Verdict

Frozen-five E2E acceptance: FAIL / NO-GO. The run was complete as an
experiment and all safe evidence was retained, but zero reports reached final
HTML/readiness. This is not a live selection-quality improvement claim. E18
remains Active/PARTIAL, Step 2 remains PARTIAL/NO-GO, and Step 3 remains
unstarted/not ready. The next bounded work is to diagnose the general
final-insight coverage failure and the Adjust public-distinctness failure,
then rerun only affected reports under the normal recovery policy; those fixes
were deliberately not made in this acceptance run.

## Frozen five-report E2E acceptance and full artifact retention — 2026-11-05 — producer d02897a9

The exact frozen cohort in
`docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json` was
executed once at producer SHA
`d02897a91e2f1773c611ade56c41f3af41ec2661` with isolated per-report state,
`--verified-facts-architecture`, no shared batch, no cross-report analysis and
publication disabled. The run identity is
`frozen-reliability-t1n2mc7x`. The complete safely retainable package is
[`verified-facts-20261105-d02897a9`](reliability-cohort-20261001-next-five/verified-facts-20261105-d02897a9/)
and its machine-readable inventory is `artifact_manifest.json`.

The command was:

    python -u scripts/quality/run_frozen_reliability_cohort.py \
      --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json \
      --runs-root C:\ml-frozen-five-live-d02897a9-retry-20261105 \
      --sources-root C:\Programing\Market lense \
      --max-duration 7200 \
      --verified-facts-architecture

### Aggregate result

| Measure | Result |
| --- | ---: |
| Reports admitted | 5 / 5 |
| Admission evaluations / admitted / quarantined | 10 / 10 / 0 |
| Terminal outcomes | 1 awaiting review, 4 failed |
| Final HTML artifacts | 1 |
| Provider calls | 1,002 |
| Input / output tokens | 7,846,389 / 1,275,698 |
| Estimated cost | `$1.517342` |
| Wall-clock | 11,224.594 s |
| Automatic targeted repairs | 9 across 3 reports |
| Workflow retries / operator interventions | 0 / 0 |
| Publication attempts / writes | 0 / 0 |

The terminal ledger is mutually exclusive and comes from the authoritative
`cohort_result.json`: Reuters reached `awaiting_review` with validation and
publication readiness passing; Capgemini, Activate, KPMG and Adjust failed
closed during validation. No unsupported retained factual claim was marked
verified, and no unresolved retained claim was promoted. The frozen-five
verdict is **FAIL / NO-GO**; this is not a Step 3 start or a claim of improved
live selection effectiveness.

### Per-report outcome and source review

| Report | Calls | Cost | Duration | Terminal outcome | Root failure / retained output |
| --- | ---: | ---: | ---: | --- | --- |
| Capgemini | 127 | `$0.348167` | 2,377.532 s | failed | `public_editorial_quality.semantic_review`; no HTML |
| Activate | 486 | `$0.423778` | 3,918.371 s | failed | `grounding`, 36 unresolved retained claims; no HTML |
| KPMG | 114 | `$0.217314` | 1,405.377 s | failed | `report_limitations_omitted`; no HTML |
| Reuters Institute | 105 | `$0.202846` | 1,327.291 s | awaiting review | validation/readiness pass; HTML retained |
| Adjust | 170 | `$0.325237` | 2,196.023 s | failed | public semantic review after 3 targeted repairs; no HTML |

All five source PDFs were hash-checked against the frozen identities and their
physical page counts are retained in `source_identity_manifest.json`. Only
Reuters produced final public HTML, so the other four are explicitly marked
unavailable rather than treated as factual passes. Reuters pages 12, 15, 17,
24 and 33 were independently checked against the final wording: the checks
covered the 33% search-referral change for more than 2,500 sites, the 69%
licensing-income relationship, the base-264 content-priority chart, the
base-263 creator comparison and the base-265 newsroom-AI comparison. The
retained HTML is
`reports/cohort-4b763ae2286ca69fe8ac/output/trends-and-predictions-2026-pdf.html`
(57,464 bytes; SHA-256
`eb629ae50af6ad814fa61561a1752c10cce618927e7e99b264d29cbbe4a9f49a`) and
contains no internal evidence identifiers. The Adjust source SHA remains
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`; its
public output was not accepted because the semantic/limitation failures
remained after bounded repair.

### Baseline comparison and limitations

Compared with retained package `verified-facts-20261105-95379` (producer
`95379a8decc5d4f1ca814170619e832c8bacf95f`), provider calls increased from 914
to 1,002, input tokens from 4,168,035 to 7,846,389, output tokens from
840,654 to 1,275,698, cost from `$0.937278` to `$1.517342`, and wall-clock
from 9,202.773 s to 11,224.594 s. Final HTML increased from zero to one, but
four reports still failed. This is an observational comparison: code,
retained runtime state and provider/model variability differ, so the result
does not isolate a causal improvement.

The exporter was run for the aggregate and all five report states. The
per-report Reuters exporter view has a missing terminal row because its local
`reports.sqlite` attempt row has blank terminal fields; the authoritative
`cohort_result.json` records the complete `awaiting_review` outcome and is the
source for the aggregate ledger. Raw workflow databases, provider caches, raw
usage ledgers, local runtime configuration and source PDF bytes were not
committed. The manifest records their hashes and exclusion reasons; 2,471
runtime files were scanned, 852 safe runtime files retained, 1,619 runtime
files excluded, and 1,002 committed package entries retained including
exporter and review projections.

**Frozen-five E2E acceptance: FAIL / NO-GO.** Step 2 remains **PARTIAL / NO-GO**,
E18 remains **Active/PARTIAL**, and Step 3 remains **unstarted/not ready**.
The remaining blockers are the four report-specific terminal validation
failures plus the exporter terminal-row retention gap; no production repair was
made during this acceptance run.

## Transactional editorial handovers and multi-fact regeneration — 2026-11-06

The targeted implementation is recorded in commits `893baf1d` and
`fb38ee04`. The first commit adds transactional verified regeneration,
authoritative-fact and qualifier handover, verified render authority, bounded
grounding diagnostics, and typed theme diagnostics. The second commit fixes a
specific multi-fact source-page validation error: a candidate with evidence
IDs bound to different pages is now checked against the page set for each
evidence ID, rather than against the union of all pages. This preserves
legitimate multi-page claims while rejecting an unrelated page for a single
fact.

The regeneration path now snapshots the exact promoted artifact for each
attempt, restricts provider changes to planner-authorized item paths, restores
complete verified protected fields only for changed items, leaves removed or
unselected families absent, and revalidates before promotion. An `ABSTAIN`
or failed candidate is a no-op. Verified rendering uses authoritative fact
packs for methodology and retains full multi-fact evidence IDs, pages and
spans; discovery DocMap prose is not used as verified public methodology.
Summary/expert/advisory handover includes admitted qualifiers and limitations.

### Focused verification

The focused handover, regeneration, rendering, grounding and editorial
quality suite passed **450 tests**. The direct candidate-lineage regression
passed **75 tests**. Ruff passed on all changed source and test files; mypy
passed for the changed modules. The prompt fixture gate passed with the
existing thresholds and baseline: total tokens **116,412 vs 115,513**
(+899), estimated cost **$0.025294 vs $0.025204** (+$0.000090); publishing
**47,304 vs 46,703** (+601, +$0.000060); validation **12,330 vs 12,134**
(+196, +$0.000020). No prompt or schema contract was weakened.

The full repository mypy command still reports the pre-existing unrelated
error in `src/services/mailbox_acquisition_service.py:2028`
(`anchor.parent` may be `None`); that file is unchanged by this work. The
wheelhouse test also remains environment-dependent on CPython 3.12 while the
available interpreter is CPython 3.14. These are reported limitations, not
silently suppressed failures.

### Corrected Activate replay

One fresh isolated provider-backed Activate run used the retained PDF and
source identity
`source:4d84943bbcfdef81ad8c08f29f6f6b0b|pdf-sha256:5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`.
The run directory is
`C:\ml-activate-handover-20261106\frozen-reliability-k5kgl0m5\members\cohort-cbb6e7df67412186b8bc\ias-first-attempt-gaw_rybd`.

| Measure | Result |
| --- | ---: |
| Verified-fact admission | 10 / 10; 0 quarantined |
| Provider calls | 497 |
| Input / output / cached input tokens | 2,048,713 / 424,849 / 42,381 |
| Estimated cost | `$0.433481` |
| Wall-clock | 4,118.580 s |
| File-search calls | 8 |
| Bounded repair actions | 3 (two provider regeneration attempts and one safe-removal candidate) |
| Workflow retries / operator intervention | 0 / 0 |
| Unsupported / unresolved retained factual claims | 0 / 0 |
| HTML / WordPress writes | 0 / 0 |

The first and second provider candidates were rolled back with empty
`changed_paths`; the third safe-removal candidate passed its narrow candidate
validation but was rolled back by final public-quality checks for missing
expert-comment evidence, incomplete public coverage and a generic watchout.
All three audits retain identical evidence IDs and physical pages between the
original and candidate artifacts. In particular, the previous multi-fact
`regeneration_source_page` errors are absent from audits 1 and 2, and no
candidate was selected using a page union. This demonstrates the provenance
fix and transactional rollback behavior, but not a publication-quality pass.

The terminal validation artifact is
`...\output\d8ca0bf6efb9c703343867f6df0f26a2553aa78f-pdf\report_analysis\validation.json`.
It reports four remaining public-editorial defects: two generic watchouts and
the omission of the source limitation that the creator-share percentages have
no sample size or uncertainty estimate. The final state is `validation_failed`
with no HTML. Because no public HTML was produced, no independent claim of
final-page editorial quality is made for this run. The source/evidence lineage
checks did pass, and no unsupported retained factual claim was marked
verified.

Compared with the retained d028 Activate result (486 calls, `$0.423778`,
3,918.371 s, 36 unresolved grounding claims), the corrected run reached
grounding with zero unresolved retained claims and exposed the remaining
editorial defects. The difference is observational: provider/model and
workflow variability prevent attributing the whole change to the page-bound
fix alone.

### Frozen-five replay attempt

The exact five-report command was started from clean commit `fb38ee04` with
the authoritative frozen cohort and no publication flags. Its run root is
`C:\ml-frozen-five-handover-20261106\frozen-reliability-pq3hizmk`.
The process reached only the Capgemini member before it was stopped cleanly
after a resource-growth stall, so this is **not** a cohort result and must not
be compared as a completed five-report acceptance. At interruption, the
Capgemini member had completed admission, source validation, taxonomy,
evidence generation and category fit; the partial ledger contained 98
completed provider events, 603,690 input tokens, 112,737 output tokens,
1,196 cached input tokens, `$0.126631`, four file-search calls and one
structured-output repair. No final HTML or publication write existed.

The runner's working set grew from approximately 0.7 GB to 1.52 GB without
new report artifacts or provider events after category-fit materialization.
The process was terminated before an uncontrolled resource failure. No
terminal outcome is counted for this partial run, and the remaining four
reports were not executed in this attempt. The partial Capgemini diagnostic
records a final-insight coverage-repair exhaustion, but because the run was
interrupted before a terminal cohort result, it is retained as diagnostic
only.

### Verdict and remaining blockers

The implementation is **PARTIAL / NO-GO** for Step 2 completion. The
multi-fact source-page defect is corrected and covered by a focused regression;
transactional rollback, evidence immutability, qualifier handover and
verified-render authority are covered by the affected suite. The fresh
Activate report still fails public editorial quality, and the exact frozen-five
acceptance remains incomplete because of the runner resource stall. The
earlier Reuters exporter terminal-row discrepancy remains an operational
limitation and was not changed speculatively. E18 remains **Active/PARTIAL**;
Step 2 is not closed and Step 3 remains **unstarted/not ready**. No
publication write or WordPress mutation was performed.

### Hosted CI verification after handover test relocation

The first hosted run on `f23032bd` exposed only a CI-owned formatting failure:
the newly relocated multi-fact regression made
`tests/_test_regeneration_candidate/cases_05_identity_continuity.py` fail the
repository format gate. No production failure was reported. The regression
was kept in the existing identity-continuity module, and commit `9d110738`
applied the repository formatter and shortened only the two affected test
names. The protected `Wordpress/dist/marketlense.zip` change remained
unstaged throughout.

Hosted run `42222882729` on `9d110738` passed all jobs: `ci_start`, the full
tests job, mutation partitions 0 and 1, and `release_evidence`. The tests job
reported 8,495 passed and 1 skipped in 508.89 seconds; coverage was 85.50%
globally, 97.98% for contracts, 87.27% for generators, 86.10% for
orchestrators, 84.26% for services and 90.60% for control-plane code. Both
mutation partitions merged 17 targets with no gate failure. The release
evidence manifest and review passed with zero issues, and the retained
release-evidence bundle is available from
<https://github.com/mbrakker/marketlense/actions/runs/42222882729/artifacts/13505096533>.

This CI result confirms repository and regression-gate integrity only. It does
not convert the provider-backed Activate replay into a publication-quality
pass or complete the interrupted frozen-five replay. The verdict therefore
remains **PARTIAL / NO-GO** for Step 2 completion; E18 remains
**Active/PARTIAL**, and Step 3 remains **unstarted/not ready**.

## Verified-mode handover and repair correction — 2026-11-06

The remaining verified-mode handover defects were corrected with the smallest
cross-stage changes. Verified rendering now checks the serialized
`data_dict["artifacts"]` projection against the independently validated
`analysis.artifacts_payload` snapshot, fails closed on a divergent projection,
and fills a missing projection from that same snapshot before rendering. The
verified render view no longer derives fieldwork dates from discovery DocMap
methodology or summary prose; normal-mode extraction is unchanged.

Public verified advisory statements no longer inherit the report-wide
`decision_brief.evidence_links` union. The artifact producer records optional
exact per-item bindings, the quality review resolves only one unambiguous
binding, and the renderer omits an unbound optional advisory item. Chart review
retains every evidence ID. Existing transactional regeneration and per-fact
page validation remain the authority for candidate changes; mixed-case IDs are
normalized only for internal page lookup, while original evidence IDs are
preserved in outputs. Verified limitations are no longer truncated to the
first seven source-backed items. Artifact selection cache identity advanced
from `evidence_backed_shortlisting:29` to `:30` so stale projections cannot
bypass the change.

Focused regressions cover divergent and missing artifact projections, discovery
fieldwork leakage, exact per-advisory bindings, mixed-case evidence-page
lookup, late source limitations, and the existing transactional/regeneration
contracts. The affected suite passed **76 tests with 7 deselected**. Ruff,
formatting, diff checks, and the canonical type gate passed; the type gate
reported **0 tracked mypy errors across 786 source files**. The default local
suite passed **8,496 tests with 2 skipped and 48 deselected**. It has one
environment-only failure in
`test_build_hash_locked_wheelhouse.py::test_existing_wheelhouse_reports_missing_active_artifact`:
the test requires native CPython 3.12, while this runner is CPython 3.14.2.
No changed module is involved in that failure.

Hosted CI run `42267015274` for commit `47c0613e` passed all required jobs:
`ci_start`, tests, both mutation partitions, and `release_evidence`. The hosted
tests job ran **8,498 tests with 1 skipped**, reported **85.50%** global
coverage, and retained the unchanged coverage and mutation thresholds. The
release-evidence bundle is available at
<https://github.com/mbrakker/marketlense/actions/runs/42267015274/artifacts/13527946780>.

The provider-free exact frozen-five replay used retained artifacts and the
local hash-pinned PDFs without publication or provider calls. It confirmed
**5/5** source SHA-256 matches (Capgemini 82 pages, Activate 140, KPMG 42,
Reuters Institute 47, Adjust 41), **29/29** retained selected insights,
**29/29** editorial-plan theme slots, and the independent Step 0 corpus of
**15 cases / 39 variants**. The generated replay record is
`out/verified_claims_step2_handover_20261106/provider_free_replay_retained_frozen_five.json`.
This is continuity/provenance evidence only; it does not claim fresh live
selection or editorial-quality improvement.

The retained Capgemini partial run was also reclassified from a presumed
resource stall to the terminal evidence actually present: the member reached
`artifact_final_insight_coverage_invalid` after
`semantic_theme_repair_exhausted` (98 provider events, 603,690 input tokens,
112,737 output tokens, 1,196 cached input tokens, `$0.126631`, four
file-search calls, and one structured-output repair). Its two-second terminal
telemetry is incomplete and cannot establish resource exhaustion. No worker or
concurrency change is justified. The existing fresh Activate replay remains a
public-editorial-quality failure with no HTML, and no new provider run was
claimed for this bounded handover correction.

**Current verdict: PARTIAL / NO-GO.** The handover and provenance corrections
are implemented and regression-covered, but Step 2 is not closed: the fresh
editorial-quality failure, live selection effectiveness, and the CPython 3.12
wheelhouse check remain unresolved. E18 remains **Active/PARTIAL** and Step 3
remains **unstarted/not ready**. No canonical artifact, readiness, publication,
or WordPress write occurred.

## Verified editorial handover and scoped regeneration replay — 2026-11-06

Commit `a731f007a38f52d04e82906407f73b40c59ef4b1` closes the remaining
cross-stage contract gaps without adding a validator, model call, or
publication path. Normal validation and prompt-family repair now use the same
validated-candidate promotion helper with atomic artifact/retained-claim/
validation persistence and rollback on partial failure. Verified promotion
requires the current report/source/configuration/policy execution identity.
Prompt-family repairs declare their actual regeneration roots, so unrelated
TOC and sibling roots are not promoted. The renderer and public-quality review
now share the same exact source-backed limitation projection; verified
strategic context is omitted when it has no unambiguous retained provenance.
Multi-fact theme coverage carries every bound canonical fact and its
relationships instead of allowing a first fact to become accidental authority.

Provider-free regressions passed **384 tests**. Scoped Ruff passed; the
canonical type gate reported **0 tracked mypy errors across 786 source files**;
`git diff --check` passed. The full local suite passed **8,502 tests, 2
skipped, 48 deselected, and 24 subtests**, with one unchanged
`test_build_hash_locked_wheelhouse.py::test_existing_wheelhouse_reports_missing_active_artifact`
failure because this host runs CPython 3.14.2 while that test requires native
CPython 3.12. No changed module is involved. A repository-wide Ruff run still
reports pre-existing violations outside this slice; the changed-file Ruff gate
is the result claimed here. Hosted CI for `a731f007` was not yet available at
the time of this report.

The exact provider-backed frozen-five command was started from clean commit
`a731f007` with no publication flags:

```text
python -u scripts/quality/run_frozen_reliability_cohort.py --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json --runs-root C:\ml-p0p1-frozen-five-20261106 --sources-root "C:\Programing\Market lense" --max-duration 7200 --verified-facts-architecture
```

Run root: `C:\ml-p0p1-frozen-five-20261106\frozen-reliability-rfc7a4tw`.
Capgemini reached terminal `artifact_final_insight_coverage_invalid` after
`semantic_theme_repair_exhausted`: **90 provider calls**, **626,940 input /
96,888 output tokens**, **1,196 cached input tokens**, and **$0.136031**.
The repair had ten eligible IDs and selected six, but the semantic coverage
validator still rejected the result. Activate reached the same terminal
failure after selecting seven of ten eligible IDs, with **470 calls**,
**974,622 input / 277,129 output tokens**, **1,196 cached input tokens**, and
**$0.258425**. Both responses were structurally valid; the rejection was the
existing semantic coverage gate, not malformed output or an unsupported
evidence promotion.

The runner then remained in post-terminal draining without new provider
events, and was stopped cleanly; no `cohort_result.json` was produced. KPMG,
Reuters Institute, and Adjust were not executed in this fresh attempt, so this
is **not** a frozen-five result. No report produced final HTML, no canonical or
retained claim was promoted, and no WordPress/publication write occurred. The
provider-free retained replay still confirms **5/5** source hashes, **29/29**
selected IDs, and **29/29** editorial-plan theme slots, but that is continuity
evidence only and does not prove fresh selection effectiveness. The live
semantic-coverage blocker therefore remains genuine and unresolved; no live
quality improvement is claimed.

**Current verdict: PARTIAL / NO-GO.** The handover, provenance, multi-fact
authority, and scoped-regeneration corrections are implemented and regression-
covered. E18 remains **Active/PARTIAL**; Step 2 remains **PARTIAL/NO-GO**; and
Step 3 remains **unstarted/not ready** pending a complete current-SHA
frozen-five run and independent editorial-quality acceptance.

### Hosted CI completion — 2026-11-06

After this evidence entry was written, hosted run
[`42302456690`](https://github.com/mbrakker/marketlense/actions/runs/42302456690)
completed successfully for `d0fa4ac680ddbf0419515c16b675d1637086f77f`.
`ci_start`, the tests/coverage job, both mutation partitions, and
`release_evidence` all passed; the optional WordPress staging REST gate was
skipped by configuration. The retained release bundle is
[`release-evidence-bundle`](https://github.com/mbrakker/marketlense/actions/runs/42302456690/artifacts/13545151927).
This closes the repository CI gate for the correction commit, but does not
change the provider-backed frozen-five result above or the Step 2 verdict.

The final documentation tip `111bdfacfbc0254c82500bab50f7643f6021fa0c` was
also verified by hosted run
[`42303832188`](https://github.com/mbrakker/marketlense/actions/runs/42303832188):
tests/coverage, both mutation partitions, and `release_evidence` passed, with
the optional WordPress staging REST gate skipped by configuration. Its release
bundle is [retained here](https://github.com/mbrakker/marketlense/actions/runs/42303832188/artifacts/13545018973).

### Adaptive verified editorial planning — 2026-11-07

Commit `002ee8143c4ca746ee6373e35832188f3fccec38` implements the adaptive
verified-facts editorial slice. The existing verified editorial-plan family now
retains `essential`/`optional` importance, substantive coverage obligations,
feasible admitted candidate IDs, merge groups, and exact material-limitation
fact IDs. Verified final insight count is derived from essential merge units
with the existing two-insight floor; legacy/normal plans retain the existing
five-insight behavior. Final secondary `evidence_ids` are accepted only when
primary-first, admitted, and source-bound, so mechanical coverage sees the
complete authorized fact set without changing the authoritative metric binding.
The existing final-writer and semantic-coverage families provide the bounded
targeted rewrite and at most one immutable-fact/original-plan replan path.
Selected limitation IDs are filtered through the existing render and expert
projections. Selection and prompt-family identities were advanced (`31`,
`normalize_editorial_plan:4.0`, and the existing prompt-validator identity) so
older cached candidates cannot bypass the new behavior.

Focused verification on the current implementation passed **170 tests**. The
changed-file Ruff check and format check passed; the full-repository type gate
reported **0 tracked mypy errors across 786 source files**. The prompt-fixture
baseline was regenerated with the repository tool and the unchanged regression
gate passed: **117,108 tokens / `$0.025364`**, with report **23,531 / `$0.008638`**,
publishing **48,000 / `$0.009159`**, and validation **12,330 / `$0.002146`**.
These are the intentional current baselines; the gate thresholds and prompt
contracts were not weakened.

The repository-wide local run completed with **8,510 passed, 2 skipped, 48
deselected, 24 subtests, and 22 warnings** after the cache-version expectation
was advanced to `evidence_backed_shortlisting:31`. The only remaining local
failure is the unchanged wheelhouse-audit test, which requires native CPython
3.12 while this host is CPython 3.14.2; no adaptive-planning module is involved.

The exact current-SHA provider-backed Capgemini run used clean SHA
`002ee8143c4ca746ee6373e35832188f3fccec38`, isolated root
`C:\ml-adaptive-step2-20261107\frozen-reliability-5ywodi9g`, and no publication
flags. It matched the retained source identity, admitted **10** eligible
candidates, selected **7**, made **92** provider calls, used **634,653 input /
99,467 output tokens**, cost **`$0.133074`**, and took **1,086.959 seconds**.
There were **8** file-search calls, **3** structured-output recovery calls, and
no automatic repair or operator intervention. The workflow failed closed at
`artifact_final_insight_coverage_invalid` during initial semantic coverage:
the terminal diagnostic retained the seven selected IDs but could not prove
`deal-search-and-cutbacks`, `promotion-effectiveness-comparison`,
`small-indulgences-financial-stress`, `genai-shopping-tools-use-and-plans`,
`assistant-control-and-action-guidance`, `human-interaction-and-loyalty`, and
`structured-product-data-for-ai`, but could not prove the essential planned
roster was represented. No final artifact, HTML,
canonical promotion, readiness pass, or WordPress write occurred. This is not
a live selection-quality improvement over the prior Capgemini failure; it is a
current-SHA failure record.

The requested isolated Activate attempt used run root
`C:\ml-adaptive-step2-20261107-activate\frozen-reliability-3i0ia94x` and was
stopped after **32m46s** because `report_selection.v1` had no heartbeat or
control observation after start. It reached no editorial stage. Its retained
ledger records **376 provider events**, **285,305 input / 148,997 output
tokens**, and **`$0.103033`** in figure-ranking/report-selection work, with no
adaptive-plan, HTML, readiness, or publication result. This is a pre-selection
stall, not a verified editorial verdict, and the post-terminal drain behavior
remains an operational limitation.

The provider-free replay helper was also invoked from this isolated worktree;
the retained frozen-five PDFs and final artifacts are not present there, so it
reported the existing `provider_free_replay` limitation and no source-hash or
selection result. The earlier retained provider-free frozen-five continuity
record remains the only evidence for **5/5 hashes, 29/29 selected IDs, and
29/29 theme slots**; it does not establish current-SHA live selection quality.
No KPMG, Reuters Institute, or Adjust current-SHA live result is claimed.

**Verdict: PARTIAL / NO-GO.** Adaptive planning, authorized secondary-fact
coverage, limitation projection, bounded recovery, and cache invalidation are
implemented and regression-covered. The current live Capgemini semantic
coverage failure and Activate pre-selection stall leave Step 2 open; E18
remains **Active/PARTIAL**, and Step 3 remains **unstarted/not ready**. No
canonical artifact, publication-readiness approval, or WordPress write was
performed.
### Final adaptive editorial and regeneration correction — 2026-11-07

The verified editorial path now classifies semantic coverage failures from the
validated model assessment: model/identity or malformed-contract failures fail
closed, evidence insufficiency quarantines, editorial execution failures use
one targeted rewrite, and an explicitly infeasible or redundant plan receives
one bounded replan. The verified plan boundary requires essential themes,
source-backed feasible admitted candidates, explicit material-limitation IDs,
and a coherent coverage resolution matrix. A replan must retain the original
essential evidence bindings and limitations and must explicitly assess every
original essential obligation after the new roster is reviewed. Verified
payload handover now preserves the exact accepted final roster and stable IDs;
legacy plans retain their five-insight behavior. Explicit empty, absent, and
non-empty limitation selections remain distinct through expert context,
advisory storage, and rendering, with no fixed five-item truncation for an
accepted verified limitation set. Cache identities were advanced to
`evidence_backed_shortlisting:32` and `normalize_editorial_plan:4.1`.

Focused verification on the correction passed **783 tests, 1 skipped, and 8
deselected** across adaptive planning, visual authority, grounding,
regeneration, evidence handover, and publication-readiness suites. The changed
file Ruff lint gate, formatting gate, changed-source type gate (six source
files, zero tracked errors), schema JSON validation, and diff checks passed.
The prompt-fixture gate passed against the existing baseline without threshold
changes: current **117,298 tokens / `$0.025383`** versus baseline **117,108 /
`$0.025364`** (+190 tokens, +`$0.000019`); validation remained **12,330 /
`$0.002146`** and all browser/OCR call counts were unchanged.
The full default pytest run then passed **8,529 tests, 2 skipped, 48
deselected, and 24 subtests**; the only failure was the unrelated native
wheelhouse audit, which requires CPython 3.12 and was run on CPython 3.14.2.

The retained Capgemini run at producer SHA `002ee814` remains useful failure
evidence but is not a post-correction live result: it admitted ten candidates,
selected seven, made 92 provider calls, used 634,653 input and 99,467 output
tokens, cost `$0.133074`, and failed closed at initial semantic theme coverage.
The retained Activate attempt made 376 ranking/crop-refinement provider
events (285,305 input / 148,997 output tokens, `$0.103033`) and never left
`report_selection.v1`; SQLite shows the job still `running` with no heartbeat
or control observation after start. It was externally stopped before any
editorial stage, so it does not demonstrate a verified-mode quality result and
does not justify a selector change. KPMG, Reuters Institute, and Adjust were
not run in that retained attempt. No fresh provider-backed run was performed
on this correction, so no live quality improvement is claimed.

No canonical artifact, readiness approval, publication, or WordPress write was
performed. The provider-free retained replay remains continuity evidence only
(5/5 source hashes, 29/29 selected IDs, and 29/29 theme slots); the current
worktree does not contain the retained PDFs needed for a new source-hash replay.

**Verdict: PARTIAL / NO-GO.** The adaptive planning, bounded recovery,
exact-roster handover, obligation preservation, limitation projection, and
cache invalidation corrections are regression-covered. Current live selection
effectiveness and editorial quality remain unproven; E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**.

### Final local gate correction — 2026-11-07

The final local correction added explicit regressions for bounded verified
replanning failure, classifier quarantine/fail-closed outcomes, conservative
legacy limitation fallback, adaptive payload rejection, and original
limitation preservation. The adaptive/replan contract files pass **62 tests**;
the broader affected cross-stage suite passes **364 tests**. The repository
coverage run (excluding only the documented CPython-3.12-only wheelhouse audit
on this CPython 3.14.2 host) passes **8,565 tests, 2 skipped, 49 deselected**;
coverage is **85.52% global** and **87.19% `src/generators`**, above the
unchanged **87.1763%** generator quality baseline. Coverage and quality
regression gates pass. The final mutation gate passes with the pre-existing
taxonomy partition at **75%**, matching its baseline; all other configured
partitions are fully killed. Ruff, formatting, and full-repository mypy remain
green with zero tracked errors.

This is provider-free engineering evidence only. No new provider-backed run
was performed after the correction, the retained PDFs needed for a new
source-hash replay are absent from the worktree, and the retained Capgemini
semantic-coverage failure plus Activate pre-editorial stall remain the only
current-SHA live evidence. Therefore the correction does not claim improved
live selection or editorial quality. No canonical promotion, readiness
approval, publication, or WordPress write occurred.

**Final verdict: PARTIAL / NO-GO.** The adaptive contracts and bounded
recovery safeguards are implemented and regression-covered; current live
effectiveness remains unverified. E18 is **Active/PARTIAL**, Step 2 is
**PARTIAL/NO-GO**, and Step 3 is **unstarted/not ready**.

### Factual/editorial disposition and recovery correction — 2026-11-07

The semantic handover correction keeps the grounding model's classification
and applicable violation type through retained-claim materialization,
checkpoint reuse, candidate validation, regeneration, and publication
readiness. A single shared disposition policy now distinguishes factual
entailment from defensible analyst interpretation and conditional
MarketLense recommendations. Unsupported empirical premises, protected-fact
contradictions, invented quantities, false attribution, and unsupported
causal or operational outcomes remain blocking. Missing or contradictory
semantic classifications remain unresolved and fail closed.

The public-review and grounding boundaries now use the same rule for unbound
editorial sentences: a purely interpretive or prescriptive sentence may be
accepted without a direct evidence ID only after independent semantic review;
unbound factual assertions still require verified evidence. Atomic soft-copy
sentence identity and hashing now use the canonical contract across grounding,
public review, retained validation, and regeneration. Verified grounding no
longer substitutes pooled whole-artifact evidence when atomic provenance is
missing; the defect is typed and remains eligible only for an exact, approved
repair target. Completeness-only semantic failures can enter the existing
targeted rewrite path, while replanning requires the complete original
essential evidence union. Validator identities were advanced so stale
semantic results cannot bypass the policy; normal/legacy behavior remains
covered by the existing compatibility paths.

The focused affected cross-stage suite passed **305 tests**. The prompt
contract regression and long-test-file ownership regression both pass after
the final correction. Ruff, formatting, full-repository mypy, schema and
prompt-fixture gates passed; the unchanged prompt fixture gate measured
**117,623 tokens / `$0.025415`** versus **117,108 / `$0.025364`** baseline
(+515 tokens / +`$0.000051`), with validation **12,655 / `$0.002178`** versus
**12,330 / `$0.002146`** (+325 / +`$0.000032`). The increase is the measured
semantic-classification, editorial-disposition and complete-verdict wording;
thresholds and factual checks were not weakened.

The repository-wide `pytest -q` run completed with **8,579 passed, 2 skipped,
48 deselected, 24 subtests, and 3 failures**. The failures are outside the
changed path: the native wheelhouse test requires CPython 3.12 (host:
CPython 3.14.2); the browser runtime assertion was order/environment
sensitive and passed in isolation; and the existing oversized-raster chart
heuristic assertion fails at `bbox[0] == 251.58` versus its existing `290.0`
threshold, with no PDF-service file changed by this correction. The exact
prior prompt and file-ownership failures were rerun and passed. No changed
semantic, grounding, regeneration, readiness, or publication-quality test
failed.

No new provider-backed run or retained-PDF replay was available in this
worktree, so this correction makes no live editorial-quality claim. Existing
retained evidence still records the Capgemini semantic-coverage failure and
Activate pre-editorial stall; no canonical promotion, readiness approval,
publication, or WordPress write occurred.

**Verdict: PARTIAL / NO-GO.** The factual/editorial handover, atomic
provenance, bounded editorial repair, completeness recovery, and original
essential-fact protection are implemented and regression-covered. Live
selection/editorial effectiveness remains unverified; E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**.

### Hosted CI final verification — 2026-11-07

The first hosted run for commit `85ef4439` passed tests and both mutation
partitions but correctly stopped at `release_evidence`: `src/generators`
coverage was **87.1719%**, just below the unchanged **87.1763%** quality
baseline. A semantic-disposition-only follow-up (`90aee0a6`) did not cover
the generator-side provenance branch, so the final targeted regression
(`5ce486aa`) exercised verified `run_grounding_check` rejection of missing
atomic provenance. No threshold, baseline, or production behavior was
changed to force the gate.

Hosted run
[`42408146131`](https://github.com/mbrakker/marketlense/actions/runs/42408146131)
for `5ce486aa` then passed `ci_start`, the full tests job (**8,608 tests,
pytest exit 0**), both mutation partitions, and `release_evidence`. The final
quality metrics were global **85.4948%**, `src/generators` **87.1875%**,
`src/orchestrators` **86.0826%**, and `src/services` **84.2709%**; all were at
or above their committed baselines. The retained release bundle is
[`release-evidence-bundle`](https://github.com/mbrakker/marketlense/actions/runs/42408146131/artifacts/13588298901).

This is engineering and contract evidence only. No fresh provider-backed
report, retained-PDF replay, canonical promotion, publication-readiness
approval, or WordPress write was performed. The existing retained Capgemini
semantic-coverage failure and Activate pre-editorial stall remain unresolved
live evidence, so the implementation does not claim improved live editorial
effectiveness.

**Final verdict: PARTIAL / NO-GO.** The code-level factual/editorial
handover correction and release gates are verified; real-report Step 2
quality remains unproven. E18 remains **Active/PARTIAL**, Step 2 remains
**PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**.

### Verified-grounding and atomic editorial-repair correction — 2026-11-07

This correction closes the confirmed cross-stage contract defects without
adding a validator, model stage, service, or publication path. One canonical
classification normalizer now maps persisted `factual` / `interpretive` /
`recommendation` labels to the model-owned semantic vocabulary and rejects
unknown labels. The verified candidate contract carries the existing
deterministic authorization for an explicitly unbound editorial sentence;
validator identities advanced to `retained_claim_validation:v12`,
`grounding_validation_output:2.3`, and the public-review identities advanced
to `public-editorial-quality:v18` / `v26`, so legacy semantic results cannot
bypass the revised handover.

The verified grounding boundary now rejects stale or fabricated no-evidence
semantic inputs while accepting only the current retained authorization. A
factual assertion mislabeled by its producer as interpretive still reaches the
independent model review and remains evidence-required. The shared protected-
fact disposition is used by retained validation, direct public grounding,
reuse, and readiness. Validation issue classification and violation type now
survive the public-review → validation → regeneration plan → repair boundary.

The claim-level repair path now has one explicit `editorial_only` selection.
It is available only for a unique, hash-matched interpretive or recommendation
sentence, an independently classified generic-copy issue, and one exact
allowed path. It carries no arbitrary evidence IDs, preserves immutable
factual/provenance fields, and still re-enters ordinary candidate validation,
grounding, and readiness. Factual and provenance repairs retain their existing
direct/parent/typed evidence requirements. The repair prompt contract records
the same fail-closed rule for the provider.

Focused cross-stage verification passed **335 tests** across classification,
grounding, retained validation, public review, regeneration, promotion,
readiness, cache/reuse, and finalization. The full local default run passed
**8,591 tests, 2 skipped, 48 deselected, and 24 subtests**; its only failure
was the pre-existing native wheelhouse audit, which requires CPython 3.12
(the host is CPython 3.14.2). Full-repository mypy, formatting, Ruff-F,
architecture, I/O, service-boundary, patching, logging, and contract-schema
gates passed. The prompt fixture regression passed after the baseline was
regenerated with the existing tool and unchanged comparator thresholds:

| Family | Previous baseline | Updated baseline | Difference |
| --- | ---: | ---: | ---: |
| Publishing tokens / cost | 48,000 / `$0.009159` | 48,827 / `$0.009244` | +827 / +`$0.000085` |
| Validation tokens / cost | 12,330 / `$0.002146` | 12,655 / `$0.002178` | +325 / +`$0.000032` |
| Total tokens / cost | 117,108 / `$0.025364` | 118,260 / `$0.025481` | +1,152 / +`$0.000117` |

The publishing increase is the bounded editorial-only repair instruction
added to the shared repair contract. The validation increase was already
present in the approved grounding/editorial prompt set at this reviewed HEAD;
regenerating the stale baseline records it rather than weakening the gate.
Other token counts and expected OCR/browser counts are unchanged. No provider-
backed report run or retained-PDF replay was available in this worktree, so no
live editorial-quality improvement is claimed. The retained Capgemini
semantic-coverage failure and Activate pre-editorial stall remain the latest
live evidence; no canonical promotion, readiness approval, publication, or
WordPress write occurred.

**Verdict: PARTIAL / NO-GO.** The code-level factual/editorial handover,
stale-input rejection, and atomic unbound-repair safeguards are implemented
and regression-covered. Current live selection/editorial effectiveness and
fresh source-PDF acceptance remain unverified; E18 remains **Active/PARTIAL**,
Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**.

### Hosted CI correction — 2026-11-13

Hosted run [43361052716](https://github.com/mbrakker/marketlense/actions/runs/43361052716)
passed the repository setup, policy, formatting, Ruff, type, architecture,
hygiene, documentation, contract, and both mutation-partition gates. Its
default pytest job reported 8,735 passed and one skipped, with two failures:
the pre-existing completeness-recovery regression did not provide the now
required source-bound `material_gaps` binding, and the newly added regression
module was 1,423 lines. The release-evidence job correctly stopped because the
tests prerequisite failed.

The test-only correction adds the explicit source-bound gap to the affected
fixture and splits the new regressions into
`test_verified_editorial_first_pass_and_scoped_repair.py` (999 lines) and
`test_verified_editorial_repair_diagnostics.py` (548 lines). Production
selection, prompt, repair, validation, retry, and publication code is
unchanged after `80ae8aef`. The corrected local checks passed 33 focused tests,
the long-file ownership gate (2 tests), Ruff, targeted mypy, and diff-check.
The hosted rerun is required before CI can be called green; no threshold,
allowlist, or quality gate was weakened.

The first test-only follow-up push then stopped at the unchanged format gate
because the new diagnostics module needed the repository formatter. Running
the formatter produced no semantic changes; corrected local verification now
passes 35 tests (including the two long-file ownership checks), Ruff, targeted
mypy, the format gate, and diff-check. A second hosted rerun is required for
the final CI result.

### Evidence update — 2026-11-13 (first-pass editorial completeness and scoped repair replay)

Commit `80ae8aef176e113cc887ba3cb074850e5bc22310` adds the verified
`insights_final` completeness instructions and deterministic focal-fact context
for the existing bounded semantic repair. The full verified writer now receives
the executable editorial obligations (including complete metric objects and
qualifiers); a scoped repair receives only exact material-gap facts, evidence
IDs, authorized candidate IDs, affected final IDs, and the gap explanation.
Normal-mode prompting and the existing validators, schemas, retry limits,
publication gates, and cache contracts are unchanged. The focused module passed
32 tests; the affected integration slice passed 273 tests; the adjacent
editorial/semantic slice passed 127 tests. Ruff, targeted mypy, diff-check, and
the prompt-fixture gate passed. The current fixture totals are 118,635 tokens /
`$0.025519` versus 118,469 / `$0.025502` (an intentional +166-token /
`$0.000017` change); publishing is +162 tokens and report is +58, while
validation is -54. No baseline or threshold was changed.

The mandatory fresh Capgemini run used the exact frozen PDF SHA-256
`612f362e1bff3c307e4db4aed38414f7b3ac85dd5cba4742ef78625cd225ef3e` in
`C:\ml-editorial-first-pass-20261112-capgemini-live\frozen-reliability-k1tkev27`.
Ten verified facts were admitted and ten candidates were retained: the model
returned 15 candidates and deterministic evidence-backed supplementation added
one candidate opportunity. The first final writer returned nine insights; the
price- and brand-priority facts were intentionally represented by one final
stable ID with both authoritative evidence IDs. No semantic repair was needed.
The final HTML, validation, grounding, evidence-fidelity, and publication
readiness all passed with zero unsupported and zero unresolved retained factual
claims. Measured usage was 120 provider calls, 1,123,270 input / 204,165
output tokens, six file-search calls, seven structured-output recovery calls,
`$0.227799`, and 1,370.745 seconds. Direct inspection of source pages 9, 12,
13, 24, 26, 33, 42, and 45 confirmed the final numerical relationships,
populations, periods, qualifiers, and non-causal wording. No WordPress or
canonical publication write occurred.

The subsequent isolated Activate, Reuters Institute, and Adjust replay was run
from the same implementation SHA in
`C:\ml-editorial-first-pass-20261112-editorial-cases\frozen-reliability-pmjt61ja`.
The terminal outcomes are mutually exclusive:

| Report | Terminal result | Facts / final insights | Calls | Input / output tokens | Cost | Repairs | Readiness |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Activate | awaiting review / pass | 10 / 10 | 503 | 2,418,136 / 422,799 | `$0.467561` | 3 targeted | pass |
| Reuters Institute | validation failed at `summary` family confidence | 10 / 9 before terminal repair | 116 | 1,481,884 / 194,012 | `$0.253942` | 3 targeted | fail |
| Adjust | validation failed closed at grounding completeness | 10 / 7 after final safe-removal candidate | 342 | 3,869,207 / 715,401 | `$0.724003` | 3 targeted | fail |

Activate's initial model candidate pool was eight and evidence-backed
supplementation retained ten; its final HTML/readiness passed with zero
unsupported and zero unresolved retained factual claims. Reuters admitted all
ten verified facts but failed the existing `summary` family-confidence gate;
no unsupported fact was promoted. Adjust admitted all ten verified facts and no
unsupported fact was promoted, but every bounded grounding recovery reproduced
an invalid JSON/coverage response: the expected single `now_what` verdict was
not returned as a complete verdict, and the validator failed closed. The
failure moved across source-bound claims during safe removal, so it is not
evidence that the model correction was factually accepted. No publication write
occurred in either failed run. The live replay therefore demonstrates improved
candidate explanation and successful Capgemini/Activate completion, but not a
general live quality improvement across all three reports; the verdict remains
**PARTIAL / NO-GO** pending the frozen-five result.

### Hosted CI verification for the final correction — 2026-11-07

Commit `58ba253ef17394748f23820cecd89d8d52f8f9f5` was verified by hosted run
[`42420228773`](https://github.com/mbrakker/marketlense/actions/runs/42420228773).
The run completed successfully in about 9 minutes 13 seconds: `ci_start`, the
full `tests` job, both mutation partitions, and `release_evidence` all passed.
The existing WordPress staging REST step was skipped because this correction
does not authorize a staging write; the PDF candidate benchmark step in
mutation partition 1 was also skipped by its existing applicability rule.
No hosted gate, threshold, baseline, or pricing assumption was changed.

The hosted run exercised the updated contract schema, validator/cache
identities, prompt-fixture baseline, stale semantic-input rejection,
classification handover, and atomic editorial-only repair tests. It confirms
release-gate compatibility, not live editorial quality: no provider-backed
report run, retained-PDF replay, canonical promotion, readiness approval,
publication, or WordPress write was performed. The retained Capgemini
semantic-coverage failure and Activate pre-editorial stall therefore remain
the latest live limitations.

**Final hosted verdict: PASS for engineering/release gates; PARTIAL / NO-GO
for live Step 2 quality.** E18 remains **Active/PARTIAL**, Step 2 remains
**PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**.

### Final review-to-regeneration contract alignment — 2026-11-08

This correction was implemented against audited base `04826ecaf05718d86333027533e3b16ba9e7324e`.
It closes the confirmed public-review contract gap without adding a validator,
LLM stage, service, or recovery framework:

- `_validate_public_editorial_review_payload()` now permits an empty evidence
  list for a failed or unresolved item only when the independently reviewed
  class is `analyst_interpretation` or `prescriptive_recommendation`, the
  expected item has no direct evidence or verified-fact context, the rule is
  `public_editorial_quality.semantic_*`, the hard-fail class is
  `editorial_quality`, and the reason/status/target contract is valid. Factual,
  provenance, metric, and evidence failures remain evidence-strict.
- Report-level failures may be evidence-free only for a substantive failure in
  `analytical_depth` or `distinctness`; material coverage and limitations remain
  strict. Localized report failures now carry the already validated item's
  independent classification into `_public_editorial_review_issue()`.
- `semantic_claim_disposition()` no longer treats an evidence-only protected
  value as an asserted claim value. Unknown claim-side values and incompatible
  propositions remain blocking.
- The existing public-editorial system/user prompts now describe the same
  editorial-only negative-verdict boundary. The review identity advanced from
  `public-editorial-quality:v26` to `v27`, so incompatible cached verdicts are
  not reused.

Focused cross-stage verification passed **448 tests**, including the actual
schema-valid unbound `semantic_generic_copy` negative verdict, factual and
verified-fact-context negatives, source-only protected-value handling,
localized report classification handover, editorial-only repair provenance,
grounding, regeneration, cache/reuse, candidate validation, promotion and
readiness regressions. The full local run completed with **8,596 passed, 2
skipped, 48 deselected, 24 subtests, and 1 failure**. The sole failure is the
pre-existing native wheelhouse audit, which requires CPython 3.12 while this
host is CPython 3.14.2; no changed test or production module failed.

The prompt fixture baseline was regenerated with the repository tool and the
unchanged regression gate passed. The only content delta is the public-review
validation namespace:

| Scope | Previous | Updated | Difference |
| --- | ---: | ---: | ---: |
| `report_vs/validate/public_editorial_quality` tokens / cost | 2,844 / `$0.000436` | 3,053 / `$0.000457` | +209 / +`$0.000021` |
| Validation family tokens / cost | 12,655 / `$0.002178` | 12,864 / `$0.002199` | +209 / +`$0.000021` |
| Total fixture corpus tokens / cost | 118,260 / `$0.025481` | 118,469 / `$0.025502` | +209 / +`$0.000021` |

Publishing and all other fixture families are unchanged. No threshold, pricing,
schema, or factual-validation requirement was weakened. Changed-file Ruff and
formatting passed; changed-source mypy passed for the two production files.
The repository type-check wrapper exited successfully with zero tracked
baseline errors, while raw `python -m mypy src` also exposed the known
environment/baseline issue at `src/services/mailbox_acquisition_service.py:2028`
(`anchor.parent` may be `None`) and a CPython-3.14 mypy assertion; neither is
in the changed path.

No current-SHA provider-backed report run, retained-PDF replay, full
review-to-promotion HTML run, canonical promotion, readiness approval,
publication, or WordPress write was available in this worktree. Therefore this
correction makes no live editorial-quality claim and does not resolve the
retained Capgemini semantic-coverage failure or Activate pre-editorial stall.

**Verdict: PASS for the corrected code-level contract and local focused gates;
PARTIAL / NO-GO for live Step 2 acceptance.** E18 remains **Active/PARTIAL**,
Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**.

### Hosted verification — 2026-11-08

Hosted run [`42426506979`](https://github.com/mbrakker/marketlense/actions/runs/42426506979)
for commit `fbf884292256b86898a8f424bca672d178249951` passed `ci_start`, the
full tests/coverage job, both mutation partitions, and `release_evidence`.
The tests job completed in 10m16s; mutation partitions completed in 7m52s and
6m23s; release evidence completed in 1m19s. The WordPress staging REST step
and the inapplicable PDF candidate benchmark step were skipped by their
existing applicability/safety rules. No threshold, baseline, pricing, or
publication gate changed. The retained release bundle is available as the
[`release-evidence-bundle`](https://github.com/mbrakker/marketlense/actions/runs/42426506979/artifacts/13596032353).

This confirms the code-level contract correction and release-gate compatibility
only. No provider-backed report, retained-PDF replay, canonical promotion,
readiness approval, publication, or WordPress write was performed; the
Capgemini semantic-coverage failure and Activate pre-editorial stall remain
the latest live limitations.

**Hosted verdict: PASS for engineering/release gates; PARTIAL / NO-GO for live
Step 2 quality.** E18 remains **Active/PARTIAL**, Step 2 remains
**PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**.

### Verified editorial lifecycle correction and retained Adjust acceptance — 2026-11-08

The current correction is `bef48fab` (with the handoff fix in
`e621e6bb6e24e79a3d2d17ae9fd5ac5de8250d10`), building on the verified
lifecycle commits `d8a05b02`, `f15347bb`, and `eb8a923a`.
The final root cause found in the current Adjust run was a cross-stage
checkpoint handoff defect: a render checkpoint serializes `source` and
`selection` beside `analysis`, but the analytics-projection re-entry looked for
them inside `analysis`. The correction reads those existing sibling fields; it
does not add a validator, provider call, schema, or new recovery path. A
regression writes a verified render checkpoint and proves that re-entry accepts
the canonical authority and returns the retained readiness-passing outcome.

The exact Step 0 frozen-five retained pack was replayed provider-free: **5/5
source hashes**, **29/29 selected IDs**, **29/29 theme slots**, **15 reference
cases / 39 variants**, and unchanged evidence IDs, physical pages, spans,
protected fields, metric-spine/key-figure counts, final wording, and fallback
availability. This is a retained-artifact comparison, not fresh candidate
generation evidence.

The retained visual shadow evaluation covered all **29 real shortlisted
insights**: **27 verified first pass, 1 verified after retry, 28 verified, 1
failed verification, 0 unresolved, 0 skipped**. The per-report ledger was:

| Report | First pass | After retry | Failed | Terminal result |
| --- | ---: | ---: | ---: | --- |
| Capgemini | 4 | 0 | 1 | 4 verified; the digital-assistants row failed closed on a physical section-divider page |
| Activate | 6 | 1 | 0 | 7 verified |
| KPMG | 5 | 0 | 0 | 5 verified |
| Reuters Institute | 6 | 0 | 0 | 6 verified |
| Adjust | 6 | 0 | 0 | 6 verified |

The two isolated live visual runs used **62 provider calls**, **1,736,711 input
tokens**, **77,528 output tokens**, **1,814,239 total tokens**, estimated cost
**$0.212438**, and summed wall time **1,044.385 seconds**. The corrected
provider-backed Adjust report run (`eb8a923a`) completed ingestion through HTML
and readiness with **182 calls**, **1,706,014 input tokens**, **278,762 output
tokens**, **$0.321413**, and **1,973.118 seconds**. It admitted **10/10
verified facts**, quarantined **0**, validated **38 newly and 28 by reuse**,
avoided **3 grounding calls**, executed **3 targeted automatic repairs** and
**6 structured-output recovery calls**, used **0 operator intervention**, and
ended `awaiting_review` with validation/readiness **pass**. No canonical
promotion, approval, publication, or WordPress write occurred.

The live Adjust HTML and retained artifacts were independently inspected against
the 41-page PDF with SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`. The
10 verified facts resolve to physical pages 9, 11, 13, 19, 21, 29, 34, 36,
38, and 40; the final three insights retain their evidence IDs and pages. The
HTML contains no internal verified-fact/source identifiers, preserves the
source caveat, and its public-quality and publish-readiness artifacts both pass.
The retained HTML is
`C:\\ml-cross-current-e2e-20261108-3\\out\\e2e-adjust-20261108-3\\frozen-reliability-hf1fxlur\\members\\cohort-b638414df0b1fccea1cd\\ias-first-attempt-xga69gq6\\output\\mobile-app-trends-2026-pdf.html`;
the authoritative artifact snapshot is the adjacent
`report_analysis\\artifacts.json`.

The corrected report run still recorded one historical `analytics_projection`
dead-letter with `report_pipeline_checkpoint_invalid` / “Checkpoint source
state must be an object”. That original workflow database and its
`operator_action_required` remediation row were not rewritten. Instead, the
dead-letter job was requeued in an isolated copy of the retained queue state;
the corrected code completed it successfully on attempt 2, projected the
Adjust report, and left only its existing claim-embedding/signal/briefing
downstream jobs pending. This proves the handoff correction without another
provider-backed report generation, but it does not claim that the original
historical run self-healed or that a fresh current-SHA full E2E has been rerun.

The first two current-SHA Adjust attempts also remain material evidence: the
first stopped on stale `editorial_theme_coverage` checkpoint identity; the
second stopped on a 4,096-token theme-coverage response truncation. The former
was fixed by aligning the stored contract identity; the latter by the existing
theme-coverage policy’s `4096` → `8192` output headroom. The third run completed
the report gates, but normal provider variability means its lower/higher cost
cannot be attributed solely to either correction.

Focused lifecycle/checkpoint/queue/projection tests passed **51**, including the
new verified render-reentry regression. Changed-file Ruff and `git diff --check`
passed. Full local/hosted release-gate results and a current-SHA full rerun are
not yet available in this entry; the local CPython 3.14 wheelhouse limitation
and the existing protected ZIP modification remain unchanged.

**Verdict: PARTIAL / NO-GO.** The report-level Adjust acceptance, retained
visual evidence, and the demonstrated checkpoint fix pass, but the historical
queue dead-letter was not repaired in place, no fresh current-SHA provider run
has exercised the final correction, and fresh Step 1 selection effectiveness and
independent human editorial acceptance remain unproven. E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**.

### Final local verification after lifecycle contract regressions — 2026-11-08

The final affected-set command covered the changed lifecycle, grounding,
checkpoint, regeneration, and editorial-contract paths:
`python -m pytest -q tests/test_verified_editorial_obligation_contract.py
tests/test_report_checkpoint_verified_reentry.py
tests/test_verified_grounding_contract_corrections.py tests/test_pre_e2e_integrity.py
tests/test_report_checkpoint_lineage_validation.py
tests/test_adaptive_verified_editorial_contracts.py` — **172 passed in 16.83s**.
The newly isolated obligation/re-entry regressions are included in that count;
they cover preservation of the original plan and essential obligations, sparse
verified-fact projection, malformed admissions, missing plan metadata, and the
verified render checkpoint's sibling `source`/`selection` handoff.

The final local gates were also run after the last test and formatting changes:

* `run_type_check.py`: **786 source files, 0 tracked errors**.
* `check_coverage.py`: global **85.55%**, contracts **97.99%**, orchestrators
  **86.20%**, generators **87.18%**, services **84.36%**, and control-plane
  **90.60%**; all thresholds passed.
* `run_mutation_gate.py`: passed; all partitions matched their baselines,
  including the existing taxonomy partition at **75%**.
* `check_quality_regression.py`: passed (global 85.5483 vs 83.3816 baseline;
  generators 87.1826 vs 87.1763; orchestrators 86.1968 vs 84.8022; services
  84.3594 vs 82.5763).
* Prompt fixture regression: passed with **118,469 tokens / $0.025502**, equal
  to the regenerated baseline; the validation family is **12,864 tokens /
  $0.002199**.
* Backlog organization/source, documentation, repository hygiene, Ruff, and
  `git diff --check`: passed.

The last complete full-suite run before the final five focused obligation tests
reported **8,606 passed, 2 skipped, 48 deselected, 1 failure**. The sole failure
was the unchanged
`test_build_hash_locked_wheelhouse.py::test_existing_wheelhouse_reports_missing_active_artifact`,
which requires native CPython 3.12 and was run on CPython 3.14.2. The final
focused set passed after those additional tests; this does not convert the
environment-specific full-suite failure into a pass. No release threshold,
fixture content, pricing, or validation requirement was weakened.

The provider-backed evidence remains the retained `eb8a923a` Adjust run and
provider-free frozen-five replay described above. There is still no fresh
current-SHA provider-backed full E2E after the final handoff correction, and the
historical queue dead-letter was only proven in an isolated copied database.
Therefore the implementation remains **PARTIAL / NO-GO** for broader Step 2
acceptance; E18 remains **Active/PARTIAL**, and Step 3 remains
**unstarted/not ready**. No canonical promotion or WordPress write occurred.

The current commit’s hosted CI run
[`42479560293`](https://github.com/mbrakker/marketlense/actions/runs/42479560293)
for `a5a762c2f22ba00d3d01346e5b9b112f7add51aa` passed `ci_start`, the full
tests/coverage job, both mutation partitions, and `release_evidence`. The
configured WordPress staging REST check was skipped by policy. This confirms
the committed engineering and release gates; it does not change the live
provider/E2E limitations or the Step 2/Step 3 verdict above.

### End-to-end integrity and transactional-repair correction — 2026-11-08

This correction is based on reviewed HEAD `27a4da3f` and is limited to
confirmed cross-stage defects. It does not add a validator, service, LLM
stage, or report-specific branch.

Confirmed root causes and fixes:

* `regeneration_plan.py` previously reduced a multi-fact validator issue to
  singular `evidence_id` data and could broaden an unidentified item to
  report-wide evidence. Validator-supplied IDs are now authoritative; all
  exact IDs and their physical pages/spans are retained, and unresolved item
  identity abstains instead of guessing. The existing evidence structures are
  reused, including `source_spans` page lineage for soft-copy failures.
* `validation.py` previously reconciled derived projections after candidate
  persistence, so the saved candidate could differ from the candidate that
  was validated. Reconciliation is now read-only and rejects a precise
  `regeneration_candidate_projection_mismatch`; the existing finalizer remains
  the only projection builder.
* Promotion now snapshots presence and exact bytes for artifacts, retained
  claim validation, validation, and the final candidate audit before the first
  write. Any later write failure restores every prior file or removes newly
  created files. Rollback failure emits the existing
  `regeneration_promotion_inconsistent` terminal error.
* The final promotion audit is written inside that same boundary. A promoted
  attempt is returned only after artifacts, claim package, validation, and
  audit all exist; an audit failure is rolled back and is not reported as a
  promoted attempt.
* `regeneration_candidate.py` now derives verified editorial admission only
  from trusted retained/promoted artifacts. A proposed candidate cannot create
  its own admission pool; sparse trusted projections are reconstructed only
  when their evidence intersects canonical verified facts, otherwise the
  candidate fails closed.
* `report_analysis_orchestrator.py` lets the existing independent public
  editorial review replace the prior review only after an actual candidate
  promotion. A rejected, rolled-back, skipped, or no-op repair cannot turn an
  unchanged failure into a false PASS. No prompt or review stage was added;
  the existing material-coverage and limitations dimensions remain the
  semantic thematic-coverage authority.

Focused cross-stage verification passed **536 tests in 34.91s**. The full
supported Python 3.12 repository suite passed **8,621 tests, 2 skipped, 48
deselected, and 24 subtests in 977.76s**. It includes exact candidate hash
checks, multi-fact grounding handoff, trusted admission, projection mismatch,
all canonical-write fault points, post-write rollback, final-audit failure,
checkpoint/re-entry, cache/reuse, readiness, and legacy paths. Ruff,
formatting, full-repository mypy (786 source files, 0 tracked errors),
architecture/I/O/service-boundary, policy, schema, documentation, hygiene,
quality-ledger, and backlog-source gates passed. Mutation partition 0 passed
sequentially with the existing taxonomy baseline at 3/4 (75%); partition 1
passed 38/38 (100%). A concurrent first attempt at partition 0 reported the
existing harness error `pytest collected 1 tests; expected 24`; it produced no
mutation result and did not recur in the isolated rerun.

The provider-free replay command completed the frozen Step 0 reference corpus
at **15 cases / 39 variants**, but the active worktree has no retained source
PDF bytes: all five source records reported `exists=false` and all 15 cases
were `skipped_provider_free`. The committed retained artifact pack exists
under the reliability-cohort evidence directory, but the replay resolver does
not substitute those derived images for full source PDFs. This is therefore a
coverage/abstention check only, not fresh model-quality or source-hash
evidence. The retained provider-backed Adjust run remains historical
`eb8a923a` evidence and is not current-SHA evidence for this correction.

No provider call, canonical publication mutation, readiness approval, or
WordPress write was made by this correction. The final local evidence proves
the handoff, persistence, rollback, and false-PASS fixes; it does not close
the known live Capgemini semantic-coverage failure, Activate pre-editorial
stall, or the absence of a current-SHA frozen-five report run.

The retained frozen-five result at producer `d02897a9` was also reviewed
report by report: Reuters Institute was the one retained validation/readiness
pass; Capgemini stopped on semantic review of the verified-fact claim
`switch-uncommunicated-reduction`, Activate stopped on an unlocalized
grounding failure, KPMG stopped on the omitted-limitations review for
`ma-buyer-pipeline-outlook`, and Adjust stopped on semantic review of the
`global-ecommerce-finance-install-session-divergence` claim. Those are
historical diagnostics, not evidence that the current code has re-run or
fixed those reports.

Hosted run
[`42494045204`](https://github.com/mbrakker/marketlense/actions/runs/42494045204)
for commit `849c3e15994a3801c9a7d37d748cd1fca8f5e5b6` passed `ci_start`,
tests/coverage, mutation partitions 0 and 1, and `release_evidence`. Job
durations were 7m56s, 7m19s, 7m35s, and 1m16s respectively. The retained
release bundle is
[`release-evidence-bundle`](https://github.com/mbrakker/marketlense/actions/runs/42494045204/artifacts/13622673956).
The WordPress staging check remained disabled by the existing safety policy;
no publication write occurred.

**Verdict: PASS for the confirmed code-level integrity corrections and local
engineering gates; PARTIAL / NO-GO for live Step 2 acceptance.** E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**.

### Multi-fact grounding, regeneration, and semantic-acceptance correction — 2026-11-08

This slice was implemented against reviewed HEAD `a3a3ce1b721205af46217271d85c770ffc2ebc72`.
It addresses confirmed cross-stage defects only; it adds no model stage,
service, validator framework, publication mutation, or report-specific branch.

Confirmed root causes and corrections:

* `regeneration_plan.py` previously retained singular or broad page context for
  composite insight, quote, summary, and figure failures. Exact item evidence
  IDs now drive fact-specific page resolution; canonical verified-fact pages
  take precedence, broad/unqualified summary and quote paths abstain, and
  duplicate stable identities with conflicting bindings fail closed rather
  than pooling unrelated facts. Composite pages remain available when the
  requested IDs exactly match the retained composite binding.
* `report_regeneration_generator.py` previously truncated the canonical
  evidence matches after eight entries. Repair packages now resolve every
  explicitly requested ID, deduplicate equivalent representations while
  merging useful page/span lineage, and retain an exact `missing_evidence_ids`
  list. A missing required fact cannot silently become optional context.
* Multi-fact `REBIND_EVIDENCE` now authorizes the existing item’s
  `evidence_ids` leaf when present, validates every proposed admitted fact,
  rebuilds all spans/pages/text through the existing binder, and rejects
  partial or sibling bindings. Verified-fact evidence packs are opt-in at the
  direct-pack boundary; normal-mode projections remain unchanged.
* The existing independent public-editorial review now has an optional v4
  output field for one semantic assessment per immutable original essential
  obligation. Deterministic checks reject omissions, duplicates, unknown
  themes/items/evidence, unsupported coverage, and a report PASS with a
  partial/uncovered essential obligation. Semantic merging into one genuinely
  multi-theme insight remains allowed. Review cache identity is advanced to
  validator `public-editorial-quality:v28`, schema `3.1`, output identity
  `public_editorial_quality_review_v4`.

The historical KPMG limitation failure was traced to the retained run, not
reclassified as a current success: `ma-buyer-pipeline-outlook` had source
qualifiers on physical page 15, the limitations family abstained, and the old
editorial plan did not retain a `material_limitation_evidence_ids` binding;
the old public review consequently reported `report_limitations_omitted`.
Current code already falls back to verified-fact qualifiers in expert context,
executive/rendered limitation projections, and the public-review scope, while
the current plan prompt requests explicit material-limitation IDs. No further
mechanical qualifier promotion was made without a current source/provider
reproduction; publication remains fail-closed if the current handoff is not
adequately covered.

Verification on this worktree:

* The focused cross-stage command covering multi-fact grounding, regeneration,
  public-editorial obligations, evidence binding, finalization, historical
  residuals, and prompt validation passed **185 tests**.
* Full local pytest was run before the final isolated compatibility correction:
  **8,627 passed, 2 skipped, 48 deselected, 5 failed**. Four failures were
  caused by the two corrected compatibility issues above and then passed in an
  isolated rerun (**3 passed**, including the parameterized full-chain cases).
  The remaining failure is the pre-existing native CPython-3.12 wheelhouse
  audit on this CPython 3.14.2 host.
* Full-repository mypy passed for **786 source files with 0 tracked errors**;
  changed-file Ruff and formatting passed; the public-review schema parses.
  The prompt-fixture gate passed against the unchanged baseline and thresholds:
  total **118,859 tokens / $0.025541** versus **118,469 / $0.025502**;
  validation **13,254 / $0.002238** versus **12,864 / $0.002199**. The
  measured delta is **+390 validation tokens / +$0.000039** (the new
  obligation contract); no fixture content, pricing, threshold, or quality
  requirement was weakened.
* The provider-free replay is retained at
  `out/verified_claims_step2_multifact_20261108/replay.json`. It covers all
  **15 reference cases / 39 variants**, but all five exact source PDFs are
  absent from this worktree and therefore all cases are
  `skipped_provider_free`; it proves retained-input coverage only. No current
  provider-backed report run, canonical promotion, readiness approval,
  publication, or WordPress write occurred.

The implementation therefore earns **PASS for the confirmed code-level
multi-fact handoff and regression gates**, but the required live semantic and
editorial cohort acceptance remains **PARTIAL / NO-GO**. Step 2 remains
**PARTIAL / NO-GO**, E18 remains **Active/PARTIAL**, and Step 3 remains
**unstarted/not ready**. The historical Capgemini, Activate, KPMG, and Adjust
provider outcomes are not claimed as corrected by provider-free replay.

### Final grounding and regeneration integrity correction — 2026-11-09

This update records the final verified-facts integrity slice from reviewed
commit `7bb8576f4f786e9bd1069db53b4dacb5bbac95ea` through producer commit
`1b3dd9cc1e8be6f7a69a09de2f262ad267dbffce`, plus the separately committed
semantic-disposition correction `6e61264a89373caaf5c944ac7c57d5977c22c9bc`.
The changes remain report-agnostic and add no validator stage, service,
database, prompt namespace, publication mutation, or WordPress write.

#### Confirmed code corrections

* Ordinary regeneration now resolves every required canonical evidence ID before
  calling the model. Missing or quarantined required evidence abstains with the
  exact IDs and preserves the existing authorized alternative-evidence path;
  report navigation/context IDs remain optional context rather than being
  misclassified as factual support.
* Verified-fact span registration preserves source identity and exact
  page-specific source-truth notes. A combined fact statement or a first-page
  note is no longer broadcast to every supporting physical page.
* Verified public-editorial review obligations can only be satisfied by retained
  final analytical `insights_final` items, while one insight may cover multiple
  themes. Missing immutable obligation metadata fails closed.
* The multi-fact rebind regression now distinguishes authorized paths from
  actual changed paths, validates a genuinely changed primary evidence ID, and
  exercises full A+B → A+C finalization and candidate validation.
* The live Adjust run exposed one additional integration defect: the semantic
  disposition completeness rule treated the explicit absence marker
  `Not specified` as an asserted unknown attribution. The minimal contract fix
  recognizes only explicit non-assertive absence markers (`not specified`,
  `not stated`, `not identified`, `not available`, `unknown`); all other
  non-empty unknown protected values remain unresolved. A material unknown
  attribution regression remains fail-closed.

#### Focused and repository verification

The focused post-correction grounding/claim-validation set passed **149 tests**.
The fresh full repository suite on the final code passed **8,646 tests, 2
skipped, 48 deselected, and 24 subtests** in **1,046.35 seconds**. Full mypy
passed for **786 source files with 0 tracked errors**; contract schema snapshot
passed; direct Ruff checks on the changed Python files passed; and the prompt
fixture gate passed without changing prompts, schemas, pricing, thresholds or
fixtures: **118,931 tokens / $0.025549** versus **118,469 / $0.025502**
(+462 tokens, +$0.000047, all in validation). The existing coverage, mutation,
quality-regression, architecture, policy, documentation and hygiene gates had
already passed on the producer implementation commit and are not weakened by
the two-line semantic policy correction. The repository wrapper reported no
changed Python files after the correction because the producer files were
already committed; direct Ruff verification was therefore used for the changed
files.

#### Required two-report provider-backed run

Exact invocation:

```text
py -3.12 -u scripts/quality/run_frozen_reliability_cohort.py --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json --sources-root "C:\Programing\Market lense" --runs-root "C:\ml-final-grounding-e2e-20261108-3" --report-ids cohort-cbb6e7df67412186b8bc cohort-b638414df0b1fccea1cd --max-duration 7200 --verified-facts-architecture
```

The source PDFs were independently hash-checked before the run: Activate
`5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`, 140
physical pages; Adjust
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, 41
physical pages. The authoritative terminal ledger and safe projections are
retained at
[`verified-facts-20261108-1b3dd9cc`](reliability-cohort-20261001-next-five/verified-facts-20261108-1b3dd9cc).

| Metric | Activate | Adjust |
| --- | --- | --- |
| Producer SHA | `1b3dd9cc` | `1b3dd9cc` |
| Source SHA verified | Yes | Yes |
| Verified/admitted facts | Not generated; stopped before verified-facts artifact | 10 evaluated / 10 admitted / 0 quarantined |
| Initial validation | Not reached; editorial plan contract failed | Failed at grounding with 1 unresolved retained factual claim, 0 unsupported |
| Repair attempts | 2 bounded editorial-plan recovery attempts; 3 structured-output calls total | 5 structured-output recovery calls in run; 0 automatic repairs |
| Promoted / rolled back repairs | 0 / 0 | 0 / 0 |
| Unresolved claims | Not evaluated | 1 (source-supported claim; false unresolved diagnosed) |
| Original essential coverage | Not generated | 6 essential plan obligations; public review PASS, final readiness blocked by grounding |
| Editorial review | Not generated | `public_editorial_quality_after`: PASS, publishable true, 0 hard fails |
| Final HTML | Not generated: editorial plan invalid | Not generated: validation failed |
| Readiness | Fail | Fail |
| Provider calls | 460 | 171 |
| Input / output tokens | 974,325 / 239,252 | 1,575,902 / 260,809 |
| Duration | 3,185.157 s | 1,844.406 s |
| Cost | $0.234446 | $0.302785 |
| Final outcome | `artifact_structured_output_invalid` | `validation_failed` |

The Adjust factual claim was independently checked against the original PDF:
page 27 states global e-commerce-app installs fell 10% YoY in 2025 while
sessions rose 5%, and page 29 supplies the separate retention observations.
The canonical verified-facts artifact had the exact source identity, pages 27
and 29, and 10 admitted facts. The only unresolved semantic dimension was
attribution with `Not specified` on both claim and evidence; this was not an
unsupported attribution. The report nevertheless failed closed, so no claim
was promoted or published.

Activate was admitted at source preflight but stopped at the first artifact
generation boundary. Provider responses were parseable, yet the editorial-plan
contract remained invalid after the existing two-attempt recovery limit. No
verified-facts artifact, final insight set, validation package, or HTML exists
for that report; it is retained as a provider/editorial-plan contract failure,
not treated as a factual pass.

#### Correction rerun

After the absence-marker fix, a new isolated Adjust run was executed on
`6e61264a89373caaf5c944ac7c57d5977c22c9bc` with the exact source hash. Its
safe evidence is retained at
[`verified-facts-20261109-6e61264a`](reliability-cohort-20261001-next-five/verified-facts-20261109-6e61264a).
It admitted the source but stopped earlier at `editorial_plan_invalid` after
two bounded recovery attempts: **148 provider calls**, **665,199 input / 97,268
output tokens**, **$0.130028**, and **1,285.047 seconds**. It did not reach
grounding, so it cannot be used to claim a live pass or live exercise of the
absence-marker correction. This is a genuine provider/editorial-plan terminal
failure, not a reason to relax the downstream factual gate.

No automatic repair, candidate promotion, rollback, final HTML, readiness
approval, publication attempt, or WordPress write occurred in either run.
The run-level manifests deliberately exclude source PDFs, raw provider caches,
private databases and raw ledgers; the authorized local workspace retains the
PDFs for review. `artifact_manifest.json` in each retained package lists every
committed safe projection with its relative path, size and SHA-256.

#### Verdict and remaining blockers

The code-level integrity corrections and local tests are **PASS**. The required
live two-report acceptance is **PARTIAL / NO-GO**: Activate remains blocked by
the editorial-plan structured-output contract, and the corrected Adjust path
was not reached in the post-fix rerun. The earlier Adjust grounding false
unresolved has a focused regression and a minimal fix, but no fresh live
success can be claimed. The exact source-page, evidence-ID and protected-fact
guards remain fail-closed. E18 remains **Active/PARTIAL**; Step 2 remains
**PARTIAL/NO-GO**; Step 3 remains **unstarted/not ready**.

Hosted CI for the final retained evidence commit passed in run
[`42544581267`](https://github.com/mbrakker/marketlense/actions/runs/42544581267):
`ci_start`, tests/coverage, both mutation partitions, and `release_evidence`
all passed. The WordPress staging REST check was skipped by the existing safety
policy. The release bundle is retained as
[`release-evidence-bundle`](https://github.com/mbrakker/marketlense/actions/runs/42544581267/artifacts/13642988366).

### Verified editorial-planning correction and current two-report E2E — 2026-11-09

This update covers implementation commit
`8c3eb9fe366f0f2c00fb89abb39800dd575d0daf`, based on audited HEAD
`3b04c9061933aa106ab7900528a4395001f86c3c`. The change is report-agnostic:
the verified editorial-plan validator now derives mechanical candidate IDs from
the admitted candidate-to-verified-fact map, while retaining model authority for
thesis, priorities, evidence selection, semantic grouping, essentiality and
material limitations. The normalized plan is persisted at both initial and
replan boundaries, so unsupported model-supplied candidate IDs cannot survive
to downstream writers. The prompt and transform identity were updated to make
the cache boundary explicit. Identifier-only validator diagnostics now carry
the failed rule/field and admissible-ID context through bounded recovery. The
terminal exporter now preserves an available failure stage, and failed
validation with no safe repair is recorded as `no_actionable_repair` rather
than `not_required`.

The retained safe evidence did not include raw rejected model fields, so no
exact invalid response value is guessed here. The deterministic reproduction
was the verified contract path in which model-controlled
`feasible_candidate_ids` was treated as authoritative even though the exact
binding already existed in the admitted fact map. Focused regressions prove
that valid canonical evidence derives the binding, invented IDs are ignored in
authority-map mode, missing exact bindings fail closed with actionable context,
and the normalized plan is retained through replan/finalization. This is the
smallest confirmed correction; no retry or new validation stage was added.

#### Current provider-backed E2E result

The exact frozen Activate + Adjust run was executed in isolated fresh state
with source hashes verified, no application-level artifact reuse, no
publication, and no WordPress writes. Safe projections are retained in
[`verified-facts-20261109-8c3eb9fe`](reliability-cohort-20261001-next-five/verified-facts-20261109-8c3eb9fe).

| Measure | Activate | Adjust | Cohort |
| --- | ---: | ---: | ---: |
| Source SHA verified | Yes | Yes | 2 / 2 |
| Verified facts admitted | 10 / 10 | 10 / 10 | 20 / 20 |
| Provider calls | 482 | 168 | 650 |
| Input / output tokens | 2,173,279 / 419,153 | 1,307,706 / 239,203 | 3,480,985 / 658,356 |
| Estimated cost | $0.446986 | $0.257474 | $0.704460 |
| Duration | 3,548.907 s | 1,688.828 s | 5,237.735 s |
| Structured-output recovery calls | 12 | 6 | 18 |
| Automatic repairs | 0 | 0 | 0 |
| Terminal outcome | failed | failed | 2 failed |

Both reports reached `artifact_generation` and the corrected verified
editorial-plan handoff. Each materialized seven plan themes and seven final
insight items in the isolated artifact projection. This demonstrates an
observed advance over the prior retained failures, which stopped at
`editorial_plan_invalid`; it does not establish downstream readiness.

Both reports then failed closed at `semantic_validation`/grounding with
`validation_grounding_invalid_json` because one public-item verdict was absent
from a grounding batch:

* Activate: `soft_copy:expert_comment:8f99ed4197a3ac39`.
* Adjust: `insight:insight-09:now_what`.

The stage ledger records `grounding_validation` and `semantic_validation` as
failed and `regeneration` as skipped with `no_actionable_repair`. No
unsupported retained factual claim was marked verified: the exporter records
26 unresolved and 0 unsupported retained claims for Activate, and 38
unresolved and 0 unsupported for Adjust. The public-editorial projection also
retains an Activate support mismatch for `insight:finding-05:text` and an
Adjust semantic-redundancy issue in the `insight-09` so-what; these were not
overridden by the grounding failure. Neither isolated output tree contains
HTML, and both publication-readiness outcomes are `fail`.

#### Verification and verdict

The fresh supported Python 3.12 suite passed **8,653 tests, 2 skips, 48
deselected tests and 24 subtests** in **899.38 seconds**. The focused plan,
diagnostic, exporter, obligation and disposition regressions passed; full
mypy, Ruff/formatting, architecture/policy, schema, documentation, hygiene,
backlog and prompt-fixture gates passed before the live run. The prompt fixture
gate remained green without changing thresholds or factual requirements.

The implementation correction is **PASS** at the verified-plan and terminal-
diagnostic boundaries. The required live downstream acceptance is
**PARTIAL / NO-GO**: grounding public-item coverage and independent editorial
quality remain actionable blockers, so Step 2 is not ready to promote and
Step 3 remains **unstarted/not ready**. No factual or readiness improvement is
claimed beyond the observed plan-handoff advance. The exact terminal ledger,
source identities, safe projections and artifact hashes are in the linked
evidence directory. Hosted CI for the implementation and evidence commit
`6fa3dc62dd274b89ab79b7f35ed497743dced487` passed in run
[`42594930022`](https://github.com/mbrakker/marketlense/actions/runs/42594930022):
tests/coverage, both mutation partitions, and `release_evidence` passed; the
configured WordPress staging REST check was skipped by policy. The release
bundle is [`release-evidence-bundle`](https://github.com/mbrakker/marketlense/actions/runs/42594930022/artifacts/13663822068).

### Grounding contract and candidate-identity correction — focused E2E retry — 2026-11-09

This update covers implementation commit
`878a989c83614a719516d398480dcb7ab8dafb1c`. The targeted changes require
`item_id` in every grounding check, enforce exact retained-item identity and
one authoritative public verdict, classify coverage failures without
deterministic semantic rewriting, keep regeneration-candidate validation
read-only, and canonicalize only a valid revised plan before persistence.
Cache/schema identities were advanced for the grounding contract. No new LLM
stage or retry budget was added.

Focused regressions passed before the live run: the latest grounding-contract
set (**37 passed**), the verified-authority/regeneration set (**23 passed**),
and the broader affected regression set (**147 passed**). The exact commit
also passed the full supported Python 3.12 suite (**8,662 passed, 2 skipped,
48 deselected and 24 subtests**), full coverage, mutation, Ruff, mypy,
architecture, schema, prompt-fixture, documentation and release-gate checks.

#### Provider-backed retry

The first fresh two-report attempt at this commit used the correct PDF source
root but failed both reports at the existing initial-selection coverage gate.
Because the repository policy requires isolated confirmation of failed
processes, the same two members were rerun in a new isolated state. The retry
was executed with:

```text
py -3.12 -u scripts/quality/run_frozen_reliability_cohort.py --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json --sources-root "C:\Programing\Market lense" --runs-root "C:\ml-grounding-contract-e2e-20261109-878a989c-retry" --report-ids cohort-cbb6e7df67412186b8bc cohort-b638414df0b1fccea1cd --max-duration 7200 --verified-facts-architecture
```

The run identity is `frozen-reliability-5vvjxo83`. Source identity was
verified before processing: Activate SHA-256
`5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2` (140
physical pages) and Adjust SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` (41
physical pages). No application-level artifact was reused; provider-side
caching was permitted. No publication or WordPress write occurred.

| Measure | Activate | Adjust | Cohort |
| --- | ---: | ---: | ---: |
| Verified facts admitted | 10 / 10 | 10 / 10 | 20 / 20 |
| Provider calls | 442 | 180 | 622 |
| Input / output tokens | 1,044,793 / 240,511 | 1,402,753 / 277,472 | 2,447,546 / 517,983 |
| Estimated cost | $0.242112 | $0.279727 | $0.521839 |
| Duration | 2,844.141 s | 2,104.985 s | 4,949.126 s |
| Structured-output recovery calls | not reached | 2 | 2 |
| Automatic targeted repairs | 0 | 3 | 3 |
| Unsupported retained factual claims | not reached | 0 | not applicable to failed report |
| Unresolved retained factual claims | not reached | 0 | not applicable to failed report |
| Final validation / readiness | not reached / fail | pass / pass | **PARTIAL** |
| Final HTML | absent | present | 1 / 2 |

The first attempt at this commit was 602 calls, 1,778,108 input and 374,226
output tokens, $0.409685, and 4,238.562 seconds, with both reports failing
the same upstream coverage class. The retry was therefore not treated as a
quality improvement merely because its aggregate cost was higher. The
per-report terminal ledger is authoritative and outcomes are mutually
exclusive.

#### Report-level findings

Activate selected 3 of 10 eligible candidates and stopped at
`initial_selection` with `artifact_final_insight_coverage_invalid`. It did
not reach grounding, final HTML, or publication readiness. This reproduces a
provider/editorial-coverage failure also seen in the preceding retained
cohorts; it does not demonstrate a grounding-contract regression or pass.

Adjust completed the full verified-facts path. It admitted 10/10 facts,
entered grounding before and after editorial regeneration, exhausted one
bounded structured-output recovery sequence at its second attempt, and ended
`awaiting_review` with validation and publication-readiness pass. Its final
artifact contains five source-backed insights with stable canonical evidence
IDs and physical-page bindings. The HTML has no `verified-fact:`, `insight:`,
`soft_copy:`, `evidence_id` or `claim_id` strings.

The final Adjust HTML was independently checked against the original PDF:

* page 9 supports the bounded GenAI-maturity and “over 20%” reported-efficiency
  statement, without turning it into a general causal effect;
* page 18 supports the 2025 global hyper-casual install/session shares of
  29.1% and 15.3%, with the distinct action and simulation relationships;
* page 23 supports 6 partners per app in 2024 and 5.3 in 2025 globally;
* page 26 supports global e-commerce downloads rising from 4.36B in 2019 to
  6.35B in 2025 and more than 45% growth;
* page 29 supports the separate e-commerce Day-1 retention movement from
  13.2% to 12.6%;
* page 35 supports the global finance install/session changes of -4% and +21%,
  while page 37 supports finance Day-1 retention moving from 13% to 12%.

The final output preserves these metric/category/period/population
relationships and uses a directional qualification where the plotted
retention evidence is not an exact value. The public-editorial review passed
with 40 checked items and zero hard failures. A warning that quotes were
omitted because quote support was weak remained visible and was not masked.

The two historical IDs that failed in the preceding run—Activate
`soft_copy:expert_comment:8f99ed4197a3ac39` and Adjust
`insight:insight-09:now_what`—were not re-emitted by this retry’s remapped
artifact IDs. Therefore this run does not claim a direct live re-evaluation
of those exact IDs. Their missing-verdict and exact-identity regressions are
covered by the focused tests, and the live Adjust grounding path passed
without a forced semantic verdict.

#### Safe evidence and verdict

The safe run package is
[`verified-facts-20261109-878a989c-retry`](reliability-cohort-20261001-next-five/verified-facts-20261109-878a989c-retry).
It contains the authoritative `cohort_result.json`, source and execution
manifests, exporter projections, terminal outcomes, and inspection notes. It
does not contain source PDFs, raw provider responses, caches, private
databases, or usage ledgers.

The implementation and focused contract verification are **PASS**. The
required two-report live acceptance is **PARTIAL / NO-GO**: Adjust exercises
the corrected grounding/candidate path successfully, but Activate remains
blocked before grounding by provider-dependent insight coverage. No broad live
selection improvement is claimed, and Step 3 remains **unstarted/not ready**.

### Essential-theme selection, recovery and terminal-evidence hardening — 2026-11-09

This implementation checkpoint addresses the next confirmed P0/P1 defects on
the current branch base `64150792bd487a12c3f310e96afd6cb16938090e`. The retained
Activate failure showed ten eligible verified candidates but only three selected
items at `initial_selection`; the existing adaptive target was being interpreted
as an exact ceiling before independent essential-theme review. The final-insight
prompt now expresses the adaptive target as a minimum in verified mode, while
the existing candidate allowlist, deterministic coverage validator and
independent semantic reviewer remain authoritative. No candidate is inserted
automatically and no fixed report-specific insight count was added.

The final-insight coverage validator is now reused at both DAG and non-DAG final
response boundaries, including rewritten/replanned outputs. The verified
semantic-theme contract now requires `report_completeness`, `diagnosis` and
`recovery_action`, with bounded enums and coherent combinations. Malformed
structured responses continue through the existing bounded structured-output
recovery; a genuine incomplete or insufficient-evidence verdict remains
fail-closed. Safe diagnostic projection retains only bounded stage/phase,
target/selected counts, omitted essential IDs, plan hashes, control enums,
recovery path/attempt count and terminal classification.

The isolated frozen-cohort CLI now returns nonzero for failed, incomplete,
validation-failing, readiness-failing or verified-evidence-failing terminal
states while still writing its evidence. Member export reconciliation accepts
the typed authoritative `cohort_result.json` outcome and preserves local stage
detail rather than manufacturing validation attempts. The existing candidate
promotion audit is projected as bounded hashes, statuses, authorized paths and
evidence lineage, and a final `artifact_manifest.json` inventories exported
files without self-hashing or retaining raw source/model content.

Focused verification is green: the adaptive/recovery/exporter suite passed
**117 tests**; selection, artifact, verified-authority and handoff tests passed
**264 tests**; regeneration, grounding, checkpoint and readiness tests passed
**352 tests** with **7 deselected**; and the Adjust-specific selection suite
passed **23 tests**. The prompt-fixture regression gate passes against the
unchanged baseline. Its measured intentional delta is **+810 total tokens / +
$0.000081**, including **+627 validation-family tokens / +$0.000063**; no
baseline, pricing, threshold or fixture manipulation was used. Direct changed-
file Ruff and formatting checks pass. The targeted mypy invocation still
reports the repository's pre-existing dynamic typing errors in the mailbox,
live-canary and exporter/cohort aggregation code; it reports no new error in
the changed generator or validation helpers.

No fresh provider-backed run is claimed in this checkpoint. The latest retained
live evidence remains the isolated retry `verified-facts-20261109-878a989c`: it
had **Activate 3/10 selected and failed before grounding**, while Adjust
completed with five source-backed insights, validation/readiness PASS and zero
unsupported or unresolved retained factual claims. A clean Activate-only run
against the exact frozen source is still required before the two-member
Activate+Adjust acceptance. E18 remains **Active/PARTIAL**, Step 2 remains
**PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**.

### Fresh Activate replay after essential-theme and handoff corrections — 2026-11-10

The required clean Activate-only replay was run at implementation commit
`0a51164d7298620825d6cd28ead2395ef5860ade` in isolated state. The source was
the frozen Activate PDF at
`C:\\Programing\\Market lense\\out\\browser_downloads\\cdn.sanity.io\\b224e6d4d2bc\\d8ca0bf6efb9c703343867f6df0f26a2553aa78f.pdf`,
SHA-256
`5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`.
The run root is
`C:\\ml-essential-theme-e2e-20261110-0a51164d\\frozen-reliability-oro16lls`;
the authoritative terminal ledger is `cohort_result.json` at that root.
No application-level artifacts were reused, no operator intervention occurred,
and no WordPress or publication write was attempted.

| Measure | Previous retained Activate (`878a989c`, before correction) | Fresh Activate (`0a51164d`) |
| --- | ---: | ---: |
| Visual facts admitted | 10 / 10 | 10 / 10 |
| Eligible final candidates | 10 | 10 |
| Final selected candidates at terminal diagnostic | 3 / 10 | 10 / 10 |
| Provider calls | 442 | 462 |
| Input / output tokens | 1,044,793 / 240,511 | 1,172,604 / 267,793 |
| Estimated cost | $0.242112 | $0.278535 |
| Wall-clock duration | 2,844.141 s | 2,854.5 s |
| File-search calls | not retained in prior ledger | 11 |
| Structured-output recovery calls | not reached | 4 |
| Automatic repairs | 0 | 0 |
| Validation / readiness | failed at initial selection / fail | fail / fail |
| HTML | absent | absent |

The earlier failure was `artifact_final_insight_coverage_invalid` at
`initial_selection` after the model returned only three items. The fresh run
cleared that boundary: the final-selection diagnostic records all ten eligible
IDs and all ten selected IDs, with the adaptive target of five treated as a
minimum. It also cleared the previously observed regeneration-scope failure;
no `model_writable_path_not_string` error or automatic regeneration repair was
observed.

The fresh run then failed closed at the independent semantic theme-coverage
boundary. Its authoritative diagnostic is:

* `assessment_phase=semantic_theme_coverage`;
* `diagnosis=material_report_completeness`;
* `report_completeness=incomplete`;
* `recovery_action=targeted_rewrite` and `recovery_path=targeted_rewrite`;
* `recovery_attempt_count=1`;
* `disposition=semantic_theme_repair_exhausted`;
* `terminal_classification=semantic_theme_repair_exhausted`; and
* `terminal_failure_code=artifact_final_insight_coverage_invalid`.

The same current and original editorial-plan identity was retained, and the
ten selected IDs were `insight-01`, `insight-02`, `insight-03`, `insight-06`,
`insight-07`, `finding-13`, `insight-05`, `finding-02`, `insight-04`, and
`insight-08`. Thus the run demonstrates the intended recovery boundary and
bounded rewrite behavior, but it does not demonstrate that the provider's
final prose covered every material report relationship. The gate was not
relaxed and no speculative candidate or evidence binding was inserted.

The run is retained as provider-backed terminal evidence, but the exporter
could not create the verified-facts artifact package because artifact
generation stopped before that package existed (`verified_facts_artifact_unreadable`;
`FileNotFoundError`). Raw final model responses were not retained, so the exact
semantic omission cannot be independently reconstructed from the safe ledger;
this is an evidence limitation, not a reason to infer a successful repair.
Because Activate did not pass, the required Activate+Adjust follow-up was not
started. There is no current-SHA evidence for a two-report acceptance or for
live editorial quality improvement beyond the initial-selection and
regeneration-boundary corrections.

**Verdict:** implementation and terminal-diagnostic correction **PASS**;
current live editorial acceptance **PARTIAL / NO-GO**. E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**. No canonical promotion, readiness approval, HTML
publication, or WordPress write occurred.

### Semantic completeness handoff correction and fresh Activate replay — 2026-11-10

The remaining semantic-completeness contract was corrected in implementation
commits `7832c025` and `60b1fcb8` on
`codex/fix-retained-insight-evidence-validation`. The change is deliberately
bounded: verified adaptive coverage now accepts and validates optional
source-bound `material_gaps`, enforces the complete/incomplete recovery-action
matrix, keeps only safe fact/evidence/insight IDs in diagnostics, versions the
coverage contract (`1.4` / validator `v5`), and requires persisted candidate
artifacts in verified regeneration. The legacy candidate-persistence branch is
unchanged for non-verified generation. No new LLM stage or downstream factual
validator was introduced.

The fresh isolated producer replay used commit `7832c025977b94fba3346bee097eb529f8947404`
and the exact frozen Activate source PDF
`C:\\Programing\\Market lense\\out\\browser_downloads\\cdn.sanity.io\\b224e6d4d2bc\\d8ca0bf6efb9c703343867f6df0f26a2553aa78f.pdf`,
SHA-256
`5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`.
The authoritative run ledger is
`C:\\ml-semantic-completeness-e2e-20261110-7832c025\\frozen-reliability-1rv906ma`.
The run was isolated, used no application-level artifact reuse, had no
operator intervention, and performed no canonical, publication, or WordPress
write.

| Measure | Prior corrected Activate (`0a51164d`) | Fresh handoff replay (`7832c025`) |
| --- | ---: | ---: |
| Visual facts admitted | 10 / 10 | 10 / 10 |
| Eligible/candidate rows | 10 | 10 |
| Final insight rows | 10 at terminal selection diagnostic | 9 |
| Provider calls | 462 | 510 |
| Input / output tokens | 1,172,604 / 267,793 | 2,539,606 / 483,535 |
| Estimated cost | $0.278535 | $0.514447 |
| Wall-clock duration | 2,854.5 s | 4,360.594 s |
| File-search calls | 11 | 15 |
| Structured-output recovery calls | 4 | 8 |
| Automatic repairs | 0 | 3 targeted repairs |
| Validation / readiness | fail / fail | pass / fail |
| HTML | absent | generated, not accepted for publication |

The current run clears the P0 semantic boundary. Its persisted semantic
assessment is `report_completeness=complete`,
`diagnosis=redundant_optional_theme`, `recovery_action=none`, and
`material_gaps=[]`. Seven theme assessments are present: the essential
obligations are covered or validly merged, while the optional news-sharing
theme is explicitly omitted as non-essential. The run also records one
bounded semantic/editorial targeted rewrite that was promoted with its
candidate and audit hashes; the post-repair public editorial-quality check
passed. This is direct provider-backed evidence that the new completeness and
handoff contract works on the previously failing report. The prior omitted
relationship cannot be reconstructed from the old run because raw provider
responses were not retained; no gap was invented.

The remaining failure is downstream and remains fail-closed. Grounding reports
`grounding_claim_check_coverage_invalid` with
`coverage=incomplete_semantic_fields` for the single safe diagnostic identity
`retained_claim:bbde6051888cc605a5581aa46ae933071064286f75be2c1a50b2b50b753ec29a`.
The retained-claim ledger has 42 unresolved and 0 unsupported claims, and
`publish_readiness.retained_claim_grounding` fails; no claim was promoted as
verified. The semantic-grounding rule itself completed, but public-item
coverage was incomplete. The run also records a `quotes_missing` warning.
Because the raw grounding response is unavailable, the exact missing public
item cannot be safely diagnosed beyond this typed identity; changing grounding
or regeneration on speculation would weaken the existing gate, so no such
change is included here.

The generated HTML contains no `verified-fact:`, `evidence_id`, `claim_id`,
`candidate_id`, `soft_copy:` or `insight:` identifiers. It is not a publication
acceptance artifact because readiness failed. Independent source inspection
against the same PDF confirmed the representative bound relationships used by
the final rows: global revenue forecast p.5 (`$1.7T`, `$2.0T`, `$302B`, `4.1%`),
gaming p.18 (`63%` spend and `70%` play time), creator shares p.53, sports
viewing p.91, Internet access and paid-content growth p.6, reality-computing
pages 38/49, retail p.113, and daily attention p.10. Final rows retain the
`verified-fact:<fact_id>` evidence identities and physical-page bindings. This
compact check is not a substitute for a full accepted editorial review while
the grounding-coverage gate remains unresolved.

The final local Python 3.12 suite passed **8,683 tests, 2 skips, 48
deselections, and 24 subtests**. Hosted CI run
[`42779297187`](https://github.com/mbrakker/marketlense/actions/runs/42779297187)
passed `ci_start`, tests, both mutation partitions, and `release_evidence` on
`60b1fcb8`; no release threshold was changed. The unchanged prompt-fixture
gate also passed with the previously measured intentional delta of +1,078
tokens overall / +$0.000108 and +627 validation-family tokens / +$0.000063.

**Verdict:** implementation and hosted engineering gates **PASS**; fresh
semantic-completeness replay **PASS**; live report/publication acceptance
**PARTIAL / NO-GO** because retained-claim grounding coverage remains
incomplete (42 unresolved, 0 unsupported) and readiness fails. E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**.

### P0/P1 grounding, promotion and diagnostic-integrity correction — 2026-11-10

This checkpoint is implemented at commit `b6f6b76da27a32229c13d505ba75838bff17d1cd`.
The smallest demonstrated fixes are:

* verified grounding contract failures now remain blocking errors even when a
  deterministic prerequisite passed; normal-mode warning behavior is unchanged;
* coverage failures retain bounded phase, batch/index, expected/returned counts,
  missing/invalid field paths, protected dimensions, schema/prompt/execution and
  relevant-input identities through the existing structured-error allowlist;
* verified grounding contract failures have no prose-repair target, while
  ordinary structured target routing remains unchanged outside verified mode;
* candidate promotion rematerializes the current retained-claim package against
  the candidate artifact/evidence/source/execution identity, requires zero
  unresolved/unsupported material claims, and rejects missing, unreadable, stale,
  or grounding-contract-failed persisted validation artifacts before writes.

The existing grounding schema and prompts were inspected and were not rewritten:
the authority policy is already system-only, legacy visual/OCR corroboration is
inside the normal-mode policy, and verified mode already supplies canonical facts
with `evidence_json=[]`. No prompt/schema identity or additional LLM stage was
introduced.

Focused regressions passed **67 tests**. The broader affected grounding,
validation, claim-package, verified-editorial, recovery, and transactional
regeneration set passed **455 tests**, with **7 deselected**. Changed-file Ruff,
compile, and `git diff --check` passed. Targeted mypy reported no error in the
changed modules; its four remaining errors are the pre-existing PyMuPDF typing
errors in `src/services/_pdf/_figures/best_figure.py` and
`src/services/_pdf/_crop/refine.py`. The unchanged prompt-fixture gate passed:
119,547 total tokens versus 118,469 baseline (+1,078), validation 13,491 versus
12,864 (+627), and estimated cost `$0.025610` versus `$0.025502` (+`$0.000108`).

The full local suite completed with **8,683 passed, 2 skipped, 48 deselected,
and 3 failures** in 931.29 seconds. The failures are outside this change:
browser runtime discovery compares the vendored parent runtime with the
installed child runtime; the native wheelhouse test requires CPython 3.12 while
this host is CPython 3.14; and the PDF oversized-wrapper heuristic returned
`x=251.58` where the existing test expects at least `290.0`. An isolated rerun
confirmed the browser-runtime test passed, while the CPython-3.12 wheelhouse
and PDF heuristic tests reproduced their two failures. No changed grounding or
promotion test failed.

#### Live verification status

The exact frozen Activate PDF was used (SHA-256
`5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`) with no
publication or WordPress flags. A fresh clean-SHA run was started at the new
commit under
`C:\\ml-p0p1-activate-20261110\\frozen-reliability-mh48b2bi`. Its runner process
ended without writing `cohort_result.json` or `cohort_members.json`; the member
database still records `report_selection.v1` as running. The retained ledger has
**377** successful `figure_ranking` events and **zero provider error codes**, but
no terminal grounding, validation, readiness, HTML, or publication outcome. This
is incomplete live evidence, not a pass or a grounding-quality result. A second
detached launcher initially failed the clean-SHA preflight before provider calls
and is not counted as a run. After temporarily removing only the protected ZIP
from the worktree, a clean detached retry
(`C:\\ml-p0p1-activate-20261110-detached3\\frozen-reliability-fyt1q4wl`)
and an attached PTY retry
(`C:\\ml-p0p1-activate-20261110-pty\\frozen-reliability-1xo7uj0e`) both
reached `source_ingest.v1=succeeded` and `report_selection.v1=running`, then
their runner processes terminated before the first provider ledger event. Both
had zero provider calls/cost, no error code, and no terminal export. They are
retained as runner-lifecycle diagnostics, not live quality results.

The provider-free replay command completed with **15 reference cases / 39
variants** and `fabricated_fixture_substitution=false`, but the current worktree
does not contain the retained frozen PDFs or Step 1 artifacts; therefore all
visual checks were skipped and it reported zero selected retained artifacts.
This limitation is recorded rather than replaced with fabricated fixtures. The
latest retained real Activate run remains the prior comparison: 510 provider
calls, `$0.514447`, 4,360.594 seconds, validation `pass`, readiness `fail`, and
42 unresolved/0 unsupported retained claims. That run's grounding coverage
warning is the direct evidence for the new verified blocking severity, not proof
that the new code improves live selection quality.

Because the current Activate run did not reach a terminal outcome, the required
fresh Adjust and frozen-five provider-backed reruns were not started. No current-
SHA live editorial or readiness improvement is claimed; no canonical claims,
publication artifacts, or WordPress writes were made.

**Verdict:** focused implementation and regression protection **PASS**; live
acceptance **PARTIAL / NO-GO** pending a terminal current-SHA Activate run and
then the required Adjust/frozen-five sequence. Step 3 remains **unstarted/not
ready**.

### Supervised terminal Activate acceptance replay — 2026-11-10

The supervised, provider-backed Activate replay required by the acceptance gate
was run at implementation SHA `7906cc70a024da6583654e273c965bdb2a9e7067`.
The exact frozen source was reused only as input:

* source identity: `source:4d84943bbcfdef81ad8c08f29f6f6b0b`;
* PDF SHA-256:
  `5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`;
* verified-fact digest:
  `c987edeb1011a36d37ac335ad261b0afa1981b054d3fad84d27b42bde9081af2`; and
* isolated run root:
  `C:\ml-p0p1-activate-20261110-acceptance\frozen-reliability-4gomc5qp`.

The runner was kept attached and polled until the workflow reached a typed
terminal result. This resolved the earlier launcher-lifecycle ambiguity: the
run now has a complete `cohort_result.json`, a terminal `report_analysis` job,
and a `report_render` job ending in `dead_letter` with `validation_failed`.
The run was isolated (`isolated_fresh_state=true`), had no operator
intervention, no application-level validation reuse (`prior_package_missing`),
and no WordPress or publication write.

#### Terminal result and failure mechanism

| Measure | Previous retained Activate baseline | Supervised terminal replay |
| --- | ---: | ---: |
| Visual facts admitted | 10 / 10 | 10 / 10 |
| Candidate rows | 10 | 10 |
| Final insight rows | 9 | 9 |
| Provider calls | 510 | 483 |
| Input / output tokens | 2,539,606 / 483,535 | 1,874,661 / 383,848 |
| Cached input tokens | not retained | 20,302 |
| Estimated cost | `$0.514447` | `$0.400066` |
| Wall-clock | 4,360.594 s | 3,832.551 s |
| File-search calls | 15 | 9 |
| Structured repair calls | 8 | 5 repair + 4 regeneration events |
| Transactional automatic repairs | 3 targeted repairs | 0 |
| Workflow retries | not retained | 0 |
| Retained unsupported claims | 0 | 0 |
| Retained unresolved claims | 42 | 41 |
| Validation / readiness | pass / fail | fail / fail |
| HTML | generated but not accepted | absent |

The lower current usage is an observed run difference, not evidence of a
quality improvement: the current run failed earlier in the acceptance gates and
did not produce an accepted HTML artifact. Provider telemetry recorded 483
completed calls, zero provider error codes, nine file-search tool calls, ten
visual-correction calls, ten visual-verification calls, ten grounding calls,
five structured-repair calls, and four structured-regeneration calls. Cache
telemetry recorded 423 enabled, 50 disabled, and 10 provider-hit decisions.
Validation reuse avoided zero grounding calls and reused zero prior results.

The grounding failure is fully typed and fail-closed. The aggregate response
contained 94 checks for 39 retained claims plus 55 public items, but
`returned_unsupported_count=0`; the diagnostic identified
`retained_claim:48504fa8824ff13f36a42d7ebc12e62b3f5eae99c7bb79944cfaf308b11fe1bc`.
The grounding contract treats a non-entailed check without its matching
model-owned unsupported entry as `unsupported_pair_mismatch`, so no retained
semantic result was promoted. The safe diagnostic labels this ID through the
public-coverage path even though it is a retained-claim ID; that naming
imprecision does not bypass the blocking check. Raw provider responses are not
retained by policy, so the exact claim text and the provider's omitted pairing
cannot be reconstructed safely. There is no demonstrated application-side
evidence-authority defect to patch, and no prompt/model relaxation was made.

Independent public-editorial review also failed closed after its bounded
sequence: primary `support_mismatch`, model repair `incomplete`, and
regeneration `support_mismatch`. The three attempts did not yield a complete
support-consistent review. The persisted validation issues include the
grounding contract failure, the public-review failure, and a non-blocking
`quotes_missing` warning. The `render_complete.json` checkpoint records
`status=error`, `outcome.error=validation_failed`, and an empty `html_path`;
there are no `.html`, `.htm`, or `.docx` files in the run root. This is why the
run cannot be counted as an accepted HTML or readiness result.

#### Candidate generation and selection evidence

The prior empty-candidate concern was exercised and explained by the retained
`artifacts.json` cache metadata:

* the provider returned eight candidates with
  `model_output_status=accepted_non_empty`;
* no structured-output recovery was needed for that call and no candidate was
  rejected for invalid evidence;
* the existing fidelity-approved fallback was invoked for
  `fallback_reason=primary_incomplete`, adding two candidates;
* `selected_candidate_source=model_and_fallback`, `selected_candidate_count=10`,
  and `candidate_pool_bound=10`; and
* the two fallback additions closed the one missing theme opportunity, leaving
  `supplementation_unresolved_themes=[]`.

The final IDs were:
`global-internet-media-revenue-outlook`,
`us-daily-tech-media-time-forecast`, `web-video-platform-composition`,
`sports-viewer-motivation`, `news-source-trust-canada-us`,
`global-retail-and-ecommerce-forecast`, `s11-podcast-genre-mix`,
`reality-computing-platform-and-forecast`, and
`svod-previsit-title-selection-likelihood`. The tenth candidate,
`s01-growth-by-segment`, was merged into the global-revenue insight. The
persisted selection metadata reports all seven planned themes selected, with no
omitted essential or central theme. Candidate generation therefore did not
silently lose the report's material coverage.

#### Independent source and editorial inspection

The nine final insight texts were inspected against the original PDF and the
authoritative verified-fact spans. The checks covered the full set of material
numeric and qualified assertions:

| Final insight | Physical source pages | Inspection result |
| --- | --- | --- |
| `global-internet-media-revenue-outlook` | 5–6 | Total forecast, segment dollars/CAGRs, scope, access definition, and GDP comparator remain separated and correctly qualified. |
| `us-daily-tech-media-time-forecast` | 11 | 12:28 to 12:46, U.S. adults 18+, daily basis, seven-day averaging, and forecast status match. |
| `web-video-platform-composition` | 54 | Platform-specific 83/17 and 52/48 shares, top-creator cohort, residual brand shares, and category definitions match. |
| `sports-viewer-motivation` | 82 | 90/10 motivations, weekly sports-viewer cohort, U.S. adults 18+, 2017, and sample-size limitation match. |
| `news-source-trust-canada-us` | 101 | Country/category pairings 51/24 and 38/20, 2017, and news-reader population match. |
| `global-retail-and-ecommerce-forecast` | 113 | Total/channel endpoints, `$2.9T` vs `$2.2T`, 18% vs 3%, exclusion, and forecast period match. |
| `s11-podcast-genre-mix` | 128 | The physical page's right-hand chart visually shows 14%, 11%, and 10%; its printed footer is 127 and was not used for binding. |
| `reality-computing-platform-and-forecast` | 36, 38 | Qualitative platform description and separate `$71B` VR/AR chart total with exclusions match; the prose does not conflate the chart with the broader platform headline. |
| `svod-previsit-title-selection-likelihood` | 79 | 26/27/35 likelihood categories, U.S. 2017 scope, 88% displayed sum, and unstated subgroup denominator match. |

No independently confirmed unsupported material assertion was found in the
structured final insights. That observation is not a validation or publication
pass: 41 retained claims remain unresolved because grounding contract coverage
failed, and the public semantic review did not complete.

#### Retained artifacts and decision

The primary retained files are:

* `C:\ml-p0p1-activate-20261110-acceptance\frozen-reliability-4gomc5qp\cohort_result.json`;
* `...\report_analysis\artifacts.json` (10 candidates, 9 finals, 10 verified facts);
* `...\report_analysis\validation.json`;
* `...\report_analysis\validation_retained_claim_validation_candidate.json`;
* `...\report_analysis\analysis_vector_store.json`;
* `...\output\.checkpoints\report_generation\...\render_complete.json`; and
* `...\state\llm_usage.sqlite` and `...\state\workflow.sqlite`.

The implementation and regression gates remain **PASS**, and the supervised
runner/lifecycle investigation is **PASS**. The genuine real-report
acceptance result is **PARTIAL / NO-GO**: Activate reached a terminal,
source-preserving pipeline outcome, but validation/readiness and HTML acceptance
failed closed. Adjust and the remaining frozen-five members were not started,
because the required first report did not reach readiness PASS. E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**. No canonical promotion or publication was performed.

### Grounding-batch, semantic-identity, editorial-handover, and regeneration-integrity correction — 2026-11-11

The implementation correction is recorded in commits `fcba011d6008ca298f9aaa633dee1dba184650cd` and `1cece18445bbdd7aa107fcc57526178c62e18206` on `codex/fix-retained-insight-evidence-validation`. The change is bounded to existing contracts and recovery paths:

* Grounding schema/processing identity advanced to `1.7`/`validation_rule_v7`. Retained non-entailed checks now require one matching model-owned unsupported entry in the same aggregate, with a valid violation type and substantive reason; entailed checks cannot carry a contradictory unsupported entry. Public and retained coverage are checked separately and the existing fail-closed rules remain authoritative.
* Reused grounding results are bound to each claim's actual successful primary, recovery, or split batch execution context: prompt hash, execution identity, provider, model, and configuration policy. A first-batch identity cannot be assigned to all claims, and a missing per-claim context cannot be reused.
* Grounding issue routing uses the canonical retained/public inventory rather than the model's non-authoritative section label. Unknown or ambiguous item identities continue to fail closed.
* Public-editorial review scope carries the final insight roster, public item IDs, evidence IDs, and verified-fact IDs. Obligation/review diagnostics expose missing, duplicate, unknown, unbound, or unauthorized evidence and supporting IDs through the existing structured-output recovery channel. Final-lineage diagnostics are bounded lists, not raw unbounded maps.
* Verified mode is propagated explicitly into regeneration planning and strict promotion loading. Required source, candidate-artifact, and evidence-pack context cannot be omitted or cause a verified run to fall back to a legacy repair target.

The focused cross-module regression suite passed **238 tests**. Changed-file Ruff and formatting passed; the full repository mypy gate passed with zero tracked errors; prompt-fixture regression passed; contract-schema, architecture-import, role-I/O, service-boundary, backlog-source, documentation, and repository-hygiene gates passed. A direct all-repository Ruff/format invocation remains non-green on inherited baseline findings (4,262 Ruff findings and 160 files that would be reformatted); no unrelated files were changed to manufacture a green result.

#### Provider-backed evidence

The exact frozen source manifest and existing retained PDFs were used. No WordPress, canonical-claim, or publication write occurred.

| Run | Terminal result | Calls | Input / output tokens | Cost | Repairs | Readiness / validation |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Isolated Activate, commit `1cece184`, `live2` | `awaiting_review`; source-verified architecture passed | 522 | 2,638,956 / 534,895 | `$0.546897` | 9 structured, 3 automatic | pass / pass |
| Adjust attempt 1, `live4` | failed `artifact_final_insight_coverage_invalid` | 153 | 953,460 / 158,758 | `$0.197224` | 3 structured | fail / fail |
| Adjust attempt 2, `live5` | failed `validation_failed` | 356 | 4,585,392 / 850,579 | `$0.851874` | 45 structured, 3 automatic | fail / fail |

The isolated Activate result admitted **10/10** verified source facts, had zero unsupported and zero unresolved retained factual claims, and produced the accepted HTML artifact:

`C:\ml-e18-current-20261111-live2\frozen-reliability-cnwk09k1\members\cohort-cbb6e7df67412186b8bc\ias-first-attempt-ztwzo0c2\output\d8ca0bf6efb9c703343867f6df0f26a2553aa78f-pdf.html`

The HTML is 62,373 bytes and contains no `verified-fact:`, `soft_copy:`, or insight evidence identifiers. The accepted run still had a non-blocking `quotes_missing` abstention; its validation and readiness result is therefore not evidence that every optional family was populated.

Adjust attempt 1 failed after the final roster contained seven rows but the independent semantic coverage review judged `cross-platform-satisfaction` materially undeveloped, even after one targeted rewrite. The deterministic coverage gate correctly rejected the report. Attempt 2 reached rendering but failed validation with **44 unresolved** and **0 unsupported** retained claims. Its grounding response first returned two checks for one expected public item (`soft_copy:linkedin_post:cf85ed213d1ca1d4`) and no matching unsupported entry, with `violation_type` missing; a later response similarly omitted `violation_type` for `insight:mobile-tech-gdp-projection:so_what`. These are malformed/incomplete model-owned verdicts and remain fail-closed; no prompt or validator relaxation was made.

The exact frozen-five replay was started from fresh isolated state at `C:\ml-e18-current-20261111-live6-frozen-five\frozen-reliability-ezg9or2q`. It did not complete the five-report cohort and must not be represented as a five-report pass. Terminal member records were:

| Report | Terminal result | Calls | Input / output tokens | Cost | Root cause |
| --- | --- | ---: | ---: | ---: | --- |
| Capgemini | failed `artifact_structured_output_invalid` | 95 | 614,943 / 111,725 | `$0.137232` | `theme_coverage` schema enum mismatch after two bounded repair attempts |
| KPMG | failed `validation_failed` | 130 | 1,463,449 / 270,525 | `$0.338331` | material coverage omitted source qualifications for buyer expectations, qualitative AI diligence, and execution capability |
| Activate | failed `artifact_structured_output_invalid` | 460 | 1,137,811 / 260,194 | `$0.261259` | `theme_coverage` schema enum mismatch after two bounded repair attempts; the in-flight regeneration was stopped after exceeding the run's intended duration |
| Reuters Institute | not started | — | — | — | controlled stop before member dispatch |
| Adjust | not started | — | — | — | controlled stop before member dispatch |

The partial cohort therefore demonstrates real late-stage provider/schema and semantic-quality failures, not a corrected five-report outcome. The current implementation has deterministic contract coverage and a successful isolated Activate run, but Adjust is not stable across fresh provider attempts and the frozen-five replay is incomplete. The measured verdict is **implementation PASS / live acceptance PARTIAL / Step 3 NO-GO**. E18 remains **Active/PARTIAL**; Step 3 must not begin until a fresh, complete cohort establishes terminal grounding, editorial-review, and readiness outcomes without weakening these guards.

### Semantic contract simplification and current-SHA reliability replay — 2026-11-12

The implementation at `5c88111c` (with the focused raw-contract regression
added after the replay) makes the provider boundary authoritative for the
semantic contracts:

* `grounding_validation_output` now accepts exactly one model-owned `checks`
  verdict per canonical item. The adapter validates exact IDs and protected
  fields, restores canonical text/section/evidence IDs, and derives the legacy
  internal `unsupported` projection only after the raw response has passed.
  Non-entailed verdicts still require a model-owned valid violation type; an
  entailed verdict still requires an explicit no-violation value.
* Editorial theme coverage now has the reduced raw schema (`status`, supporting
  IDs, explanation, report completeness, diagnosis, material gaps and original
  obligation assessments). Existing `resolution` and `recovery_action` values
  are deterministic internal projections. The complete normalized assessment is
  retained in the existing family-output cache and revalidated on reuse.
* Grounding and theme prompt/cache identities advanced (`v6`/`1.8` and
  `v6`/`validation_rule_v8` paths), so incompatible prior provider outputs are
  not reused. No new service, validator, LLM stage, publication path or
  WordPress write was introduced.

Focused verification after the implementation passed **155 tests** (grounding
contract, raw single-verdict adaptation, protected dimensions, recovery,
schema and prompt regressions). Changed-file Ruff and `git diff --check` passed.
The prior complete Python 3.12 repository run at the same production commits
passed **8,699 tests, 2 skipped, 48 deselected and 24 subtests**; full mypy,
schema, architecture, prompt-fixture and repository hygiene gates passed before
this test-only addition. The prompt fixture gate remained unchanged at
**118,375 tokens / `$0.025493`** total and **12,810 / `$0.002194`** for
validation, versus **118,469 / `$0.025502`** and **12,864 / `$0.002199`**
baselines.

#### Current-SHA provider-backed frozen-five attempts

The retained PDFs were processed with isolated fresh state, provider-side
caching only, no publication flags, and no WordPress writes. The five reports
were attempted across the retained cohort roots below; this is not a single
successful five-report cohort and is not reported as one.

| Report / attempt | Terminal result | Calls | Input / output tokens | Cost | Search / structured / automatic repairs | Readiness |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Capgemini | `artifact_final_insight_coverage_invalid` after semantic repair exhaustion | 98 | 655,827 / 118,237 | `$0.137079` | 5 / 3 / 0 | fail |
| Activate | `artifact_final_insight_coverage_invalid` after semantic repair exhaustion | 465 | 1,196,095 / 281,579 | `$0.287787` | 11 / 2 / 0 | fail |
| KPMG | `validation_failed` at grounding | 179 | 2,344,266 / 390,325 | `$0.426876` | 14 / 14 / 3 | fail |
| Reuters Institute | `artifact_final_insight_coverage_invalid` after semantic repair exhaustion | 105 | 826,803 / 123,339 | `$0.156728` | 5 / 4 / 0 | fail |
| Adjust | `artifact_final_insight_coverage_invalid` after semantic repair exhaustion | 147 | 862,762 / 146,712 | `$0.176881` | 7 / 3 / 0 | fail |

Additional controlled attempts were retained for Reuters (`96` calls,
`$0.158314`, `artifact_structured_output_invalid` in `insights_final`) and
Adjust (`144` calls, `$0.136906`, `artifact_structured_output_invalid` in the
verified editorial-plan limitation-evidence binding). They are separate
attempts, not extra successful cohort members. The runner's partial duration
fields are not used as latency measurements because the controlled stops did
not emit reliable terminal wall-clock values.

The per-report root causes are distinct and fail closed:

* Capgemini's semantic assessment retained nine final rows but did not develop
  the admitted `impulse-purchases-change` fact after one bounded targeted
  rewrite.
* Activate's semantic assessment retained eight rows and still left the
  `global-media-revenue-growth`, `revenue-model-mix-forecast` and
  `top-creator-platform-view-shares` relationships materially incomplete after
  one targeted rewrite.
* KPMG reached grounding with 10/10 visual facts admitted. Its failure was an
  entailed protected-fact conflict/incomplete model verdict for the public
  LinkedIn item, followed by a report-wide semantic-redundancy review failure;
  no unsupported factual claim was promoted.
* Reuters' first terminal attempt left `social-platform-friend-family-time`
  materially undeveloped; the separate attempt exhausted `insights_final`
  structured recovery on the same class of final-roster failure.
* Adjust's first attempt left
  `cross-platform-measurement-approaches` materially undeveloped; the separate
  attempt failed closed earlier at the verified editorial-plan
  `material_limitation_evidence_ids` binding.

These outcomes demonstrate that malformed or semantically conflicting model
responses remain blocked and that the new raw contract is exercised by local
regression. They do **not** demonstrate improved live editorial quality: none
of these current-SHA attempts reached accepted readiness, and the raw provider
responses are not retained for retrospective reinterpretation. The complete
current-SHA frozen-five acceptance verdict is therefore **PARTIAL / NO-GO**;
Step 3 remains unstarted/not ready. Remaining limitations are provider
variability in semantic theme coverage, the KPMG protected-fact conflict, and
the absence of a terminal accepted current-SHA five-report HTML cohort.

### Hosted CI confirmation for the semantic-contract slice — 2026-11-12

The final regression-test commit is `c8189f10` on
`codex/fix-retained-insight-evidence-validation`. It adds only focused
provider-boundary and batch-scope regressions; production code, prompt text,
schemas, thresholds, caches, and release gates were unchanged after the
implementation commits. The focused affected slice passed **160 tests**.

Hosted CI run [43156874113](https://github.com/mbrakker/marketlense/actions/runs/43156874113)
passed on CPython 3.12.16: the full tests/coverage job, both mutation
partitions, quality non-regression, PDF benchmark, public-render, routing,
workflow-queue, accounting, prompt-fixture, manifest, and release-evidence
gates all passed. The generator coverage gate passed without changing the
baseline or threshold. The prompt-fixture gate remained **118,375 total
tokens / `$0.025493`** and **12,810 validation tokens / `$0.002194`**, versus
baselines of **118,469 / `$0.025502`** and **12,864 / `$0.002199`**.

The local Python 3.14 full run is not treated as the authoritative result: it
recorded 8,702 passed and 2 skipped, with one pre-existing wheelhouse test
failure because that test requires CPython 3.12. The hosted supported-runtime
run is green. No provider-backed report run, canonical promotion, or
WordPress write was performed for this test-only correction. The deterministic
implementation verdict remains **PASS**; current-SHA live editorial
acceptance remains **PARTIAL / NO-GO**, and Step 3 remains unstarted/not ready
because the retained five-report attempts documented above did not form an
accepted cohort.

### Verified editorial completeness and scoped repair correction — 2026-11-12 (`b91b9c1b`)

Commit `b91b9c1b0ead812b278650c0c469c01c9403aa0a` implements the first-pass
editorial-completeness and targeted-repair slice. The existing accepted
editorial-plan bindings, admitted candidates, and canonical verified facts are
materialized into transient executable obligations for `insights_final`:
theme, coverage obligation, evidence IDs, feasible candidate IDs, merge group,
verified-fact IDs, and complete authoritative metric/qualifier objects. The
prompt asks the model to develop those relationships and qualifications, but
does not impose a one-insight-per-theme or minimum-count quota. Local semantic
repair now receives a bounded patch scope derived from the semantic assessment
and those obligations; it may replace authorized rows or add feasible
candidate-backed rows, while preserving the existing roster and order. The
partial patch is not persisted or reused as canonical `insights_final` output.
Full lineage, protected-field, reference, count, and semantic validation still
runs after the merge. No new service, validator, LLM stage, persisted contract,
or publication path was introduced.

The focused new regression module passed **12 tests**. The combined prompt,
obligation, semantic, and editorial-contract slice passed **188 tests**; the
affected artifact, evidence-binding, checkpoint, and regeneration slice passed
**309 tests**. The type gate passed with zero tracked errors; changed-file
Ruff, formatting, diff-check, architecture, role-I/O, service-boundary,
forbidden-patching, repository-hygiene, backlog, documentation, and contract
schema gates passed. The prompt fixture baseline was intentionally unchanged:

| Fixture family | Old tokens | Current tokens | Delta | Old cost | Current cost | Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Total | 118,469 | 118,497 | +28 (+0.02%) | `$0.025502` | `$0.025505` | +`$0.000003` |
| Publishing | 48,827 | 48,909 | +82 (+0.17%) | `$0.009244` | `$0.009252` | +`$0.000008` |
| Validation | 12,864 | 12,810 | -54 (-0.42%) | `$0.002199` | `$0.002194` | -`$0.000005` |

The unchanged fixture gate passed. The small publishing increase is the
intentional obligation/prose-completeness wording; validation decreased. No
threshold, pricing, schema, or baseline was changed.

#### Isolated provider-backed evidence

One fresh isolated member of the exact frozen-five manifest was run at the
implementation SHA with provider-side calls allowed and no publication flags:

| Report | Source identity / PDF | Terminal result | Calls | Input / output tokens | Cost | Repairs | Readiness / HTML |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Capgemini | `source:f584854bc13cdca0b0d86327c85f71ff`; MD5 `81af3890cd84ece81ef16e1aabda8027`; SHA-256 `612f362e1bff3c307e4db4aed38414f7b3ac85dd5cba4742ef78625cd225ef3e` | `artifact_structured_output_invalid` / `artifact_final_insight_repair_invalid` | 99 | 924,764 / 104,336 | `$0.164519` | 3 structured, 0 automatic | fail / none |

Run root: `C:\ml-editorial-completeness-20261112-live\frozen-reliability-u36ej66a`.
The source and analysis PDFs matched the frozen MD5, and the selection
checkpoint completed with **79** figure candidates. Its five `insights` values
were source-selection placeholders, not a final insight roster; there is no
evidence of an unexplained empty final-candidate checkpoint. The first
`insights_final` provider response was recorded as parsed, followed by the
semantic repair path and exactly two bounded structured recovery attempts. The
terminal record identifies the failure as final-insight repair/contract
rejection after the third recovery call; the retained terminal artifact does
not include the raw invalid field, so a more specific model-error diagnosis
would be speculative. No final `artifacts.json`, validation result, readiness
pass, or HTML was emitted. The run made 8 file-search calls, required no
operator intervention, performed no automatic workflow repair, and made no
canonical or WordPress write.

Against the latest retained Capgemini current-SHA comparison (`5c88111c`),
the run changed from 98 calls / 655,827 input and 118,237 output tokens /
`$0.137079` / `artifact_final_insight_coverage_invalid` to 99 calls /
924,764 input and 104,336 output tokens / `$0.164519` /
`artifact_structured_output_invalid`. This is **not** evidence of live quality
improvement: the input/cost increase is provider-run variability plus the
larger executable obligation context, and the report still failed closed
before editorial inspection. It does show that the new first-pass prompt and
scoped-repair path were exercised and that malformed/incomplete final output
was not promoted.

The exact frozen five was not rerun after this member failed before readiness;
therefore no current-SHA results are claimed for Activate, KPMG, Reuters
Institute, or Adjust, and no five-report editorial-quality comparison is
available. The deterministic implementation verdict is **PASS**; live
editorial acceptance for this correction is **PARTIAL / NO-GO**. E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**. The retained run artifacts and `cohort_result.json`
are the evidence for this bounded result; no fabricated or cached final report
was substituted.

### Follow-up scoped-repair correction and hosted CI — 2026-11-12 (`9ea73416`)

Commit `9ea73416c7d83184f541d17b3cdf6e3119e9af72` closes the remaining
localized-repair authorization gap. An essential theme with
`supporting_insight_ids=[]` now authorizes both revision of a feasible existing
entry and addition of feasible admitted candidates; previously, the presence
of any current roster entry could suppress those additions even when the
semantic assessment supplied no supporting ID. The existing scope validator
and merge rules still decide which returned patch entries are accepted, so
this change does not select a candidate deterministically, broaden evidence
authority, or alter full-roster validation. Regression doubles were also
changed to the required patch-only response shape, and the long snapshot test
was split without changing production behavior.

The final focused checks passed: **15** directly affected regressions,
**192** combined prompt/obligation/editorial semantic tests, **309** affected
artifact/evidence/regeneration tests, and **2** test-file ownership checks.
Ruff, formatting, diff-check, and the repository type gate passed (786 source
files, zero tracked errors). The full local Python 3.14 run recorded **8,715
passed, 2 skipped, 88 warnings and 24 subtests**, with one pre-existing
`test_build_hash_locked_wheelhouse` failure because the active wheelhouse gate
requires CPython 3.12. The supported-runtime hosted run is authoritative.

Hosted CI [43192923454](https://github.com/mbrakker/marketlense/actions/runs/43192923454)
passed: tests/coverage, both mutation partitions, release-evidence gates,
prompt-fixture regression, PDF benchmarks, public-render and routing/accounting
gates. The WordPress staging REST gate was skipped by its existing prerequisite;
no publication was attempted. The prompt fixture remained unchanged and green
at **118,497 tokens / `$0.025505`** total and **12,810 / `$0.002194`** for
validation against **118,469 / `$0.025502`** and **12,864 / `$0.002199`**
baselines. No new prompt family, LLM call, schema, service, retry count, or
release threshold was introduced.

The provider-backed Capgemini attempt retained above ran at `b91b9c1b`, before
this follow-up authorization correction. It failed closed at final-insight
structured repair and produced no accepted final roster, HTML, readiness pass,
or canonical/publication write. Consequently, the follow-up edge case is
demonstrated by focused regressions only; no live quality improvement is
claimed for `9ea73416`, and Activate, KPMG, Reuters Institute, and Adjust were
not rerun at this SHA. The implementation verdict is **PASS**; live editorial
acceptance remains **PARTIAL / NO-GO**, E18 remains **Active/PARTIAL**, Step 2
remains **PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready** pending
an accepted provider-backed cohort.

### Scoped repair follow-up and corrected Capgemini replay — 2026-11-12 (`97849c8f`)

Commit `9b895cda699b295d9f80ecde1c2f08220d74bebe` implements the scoped repair
contract. A semantic material gap now produces a bounded repair scope containing
only the affected admitted candidate/fact/evidence identities, theme obligations,
and authoritative metric/qualifier context. The existing patch validator and
full post-merge semantic coverage check remain authoritative; the scoped result
is neither persisted as a canonical roster nor reused as an unrestricted full
generation. The prompt has mutually exclusive full-roster and localized-patch
branches, so a repair cannot silently replace unrelated insights or relax the
existing publication-quality gates.

The first isolated Capgemini replay at that implementation SHA reached the
scoped path but failed closed on a structured contract violation: the provider
returned `evidence_ids: null` for an optional array. This was not converted into
a usable artifact. The follow-up prompt-only correction in
`97849c8f5b33c165c0a9f8aa86933d504c0e5633` states that unavailable optional
fields must be omitted and optional arrays must be JSON arrays, and carries the
same rule into the existing structured-output recovery/regeneration prompts.
No schema, validator, retry limit, or quality threshold was changed.

| Run | Terminal result | Calls | Input / output tokens | Cost | Duration | Repair / output |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `9b895cda` — `C:\ml-scoped-repair-20261112-capgemini-live2\frozen-reliability-j5xt3cr7` | `schema_type_mismatch` (`evidence_ids` null) | 136 | 1,843,445 / 255,417 | `$0.327141` | 1,909.953 s | 11 structured; no final artifact/readiness/HTML |
| `97849c8f` — `C:\ml-scoped-repair-20261112-capgemini-live3\frozen-reliability-k3y9oail` | `artifact_final_insight_coverage_invalid` / `semantic_theme_repair_exhausted` | 94 | 770,906 / 109,563 | `$0.146749` | 1,190.781 s | 1 scoped rewrite; no final artifact/readiness/HTML |

The second run used the exact Capgemini source identity and PDF SHA-256
`612f362e1bff3c307e4db4aed38414f7b3ac85dd5cba4742ef78625cd225ef3e`.
Its terminal diagnostic identified one material gap,
`verified-fact:insight-04`, with a ten-row final roster and ten eligible
candidate IDs. The repair was authorized and bounded, but the merged result
still failed the existing semantic-theme completeness check. The report-level
fidelity artifact contained 36 supported rows whose semantic outcomes were
`entailed`; this confirms that the failure was not caused by loss of the source
evidence pack. It is a provider semantic-completeness miss, and the pipeline
correctly abstained instead of manufacturing a claim or adding an unbounded
third attempt. The runner could not collect the verified-facts architecture
artifact after this early terminal failure (`FileNotFoundError`), so no current
run admission or readiness pass is claimed.

The prompt/recovery correction is demonstrated by the changed terminal stage:
the known optional-array contract failure did not recur, while the remaining
semantic gap stayed fail-closed. The lower call/cost totals versus the prior
Capgemini attempt are not attributed as an optimization because the runs have
different provider paths and output volumes. No HTML, canonical artifact,
publication-readiness pass, WordPress write, or operator intervention occurred;
Activate, KPMG, Reuters Institute, and Adjust were not run after Capgemini
failed, so there is no current-SHA frozen-five result.

The post-correction focused suite passed **159 tests** and the prompt-fixture
gate remained green without baseline or threshold changes:

| Fixture family | Old tokens | Current tokens | Delta | Old cost | Current cost | Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Total | 118,469 | 118,634 | +165 (+0.14%) | `$0.025502` | `$0.025519` | +`$0.000017` |
| Publishing | 48,827 | 48,988 | +161 (+0.33%) | `$0.009244` | `$0.009260` | +`$0.000016` |
| Report | 23,531 | 23,589 | +58 (+0.25%) | `$0.008638` | `$0.008644` | +`$0.000006` |
| Validation | 12,864 | 12,810 | -54 (-0.42%) | `$0.002199` | `$0.002194` | -`$0.000005` |

The implementation and malformed-output correction are **PASS** against their
focused deterministic regressions. Live editorial acceptance is **PARTIAL /
NO-GO**: the fresh Capgemini report still lacks an accepted final roster and
HTML, and no five-report cohort was completed. E18 remains **Active/PARTIAL**,
Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**.

### Exact frozen-five replay — 2026-11-13 (`80ae8aef`)

The required provider-backed replay was completed from an isolated fresh state
at `C:\ml-editorial-first-pass-20261113-frozen-five\frozen-reliability-tufi12k9`
using commit `80ae8aef176e113cc887ba3cb074850e5bc22310`. All five reports were
admitted to verified-facts processing, and each admitted all 10 evaluated facts
(50/50 facts; 0 quarantined). No WordPress authentication/readback, publication
write, operator intervention, or canonical promotion occurred. The cohort was
not publication-ready: **0/5** reports passed final validation/readiness.

| Report | Terminal result | Final roster / candidates | Calls | Input / output tokens | Cost | Duration | Structured repair / material result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Capgemini | `validation_failed` (grounding) | 5 / 10 | 117 | 1,150,451 / 178,168 | `$0.219837` | 1,370.272 s | 3; summary combined the supported private-label shift with unsupported Gen-AI figures; 1 unsupported retained claim |
| Activate | `artifact_final_insight_coverage_invalid` | 6 / 10 | 460 | 1,176,854 / 273,491 | `$0.279309` | 3,280.936 s | 3; three exact material gaps remained after bounded semantic repair |
| KPMG | `artifact_final_insight_coverage_invalid` | 8 / 10 | 108 | 820,191 / 99,552 | `$0.161551` | 1,004.876 s | 5; `verified-fact:insight-ai-diligence` remained an uncovered material gap |
| Reuters Institute | `validation_failed` (grounding) | 7 / 10 | 132 | 1,523,677 / 224,260 | `$0.282147` | 1,524.196 s | 9; 40 unresolved retained factual claims; grounding response completeness failed |
| Adjust | `validation_failed` (grounding) | 10 / 10 | 173 | 1,801,698 / 253,940 | `$0.317403` | 1,958.371 s | 10; 47 unresolved retained factual claims; grounding response completeness failed |
| **Total** | **0/5 readiness** | — | **990** | **6,472,871 / 1,029,411** | **`$1.260247`** | **9,138.651 s** | failure Pareto: 2 completeness, 3 validation |

The frozen-five terminal JSON is the source for the counts above. The three
reports that emitted `artifacts.json` retained 5 Capgemini, 7 Reuters, and 10
Adjust final insights; Activate and KPMG stopped at the existing material
coverage gate. The corresponding retained artifact paths are:

- `C:\ml-editorial-first-pass-20261113-frozen-five\frozen-reliability-tufi12k9\members\cohort-81af3890cd84ece81ef1\ias-first-attempt-tsseiyn0\output\final-web-version-report-consu-1d9e64dd7425\report_analysis\artifacts.json`
- `C:\ml-editorial-first-pass-20261113-frozen-five\frozen-reliability-tufi12k9\members\cohort-4b763ae2286ca69fe8ac\ias-first-attempt-7grdodni\output\trends-and-predictions-2026-pdf\report_analysis\artifacts.json`
- `C:\ml-editorial-first-pass-20261113-frozen-five\frozen-reliability-tufi12k9\members\cohort-b638414df0b1fccea1cd\ias-first-attempt-8hhl75oz\output\mobile-app-trends-2026-pdf\report_analysis\artifacts.json`

The mandatory Capgemini source SHA was verified as
`612f362e1bff3c307e4db4aed38414f7b3ac85dd5cba4742ef78625cd225ef3e`. A
separate fresh Capgemini run of the same implementation (outside the exact
five-member replay) passed readiness with 9 final insights, 120 calls,
1,123,270 / 204,165 tokens, `$0.227799`, 1,370.745 seconds, 0 unsupported
claims, 0 unresolved claims, and no automatic repair. The exact frozen-five
Capgemini member instead failed on a mixed unsupported executive-summary
proposition. This is direct evidence of provider-run variability and of the
grounding gate rejecting an unsupported rewrite; it is not evidence that the
implementation improved live selection quality. The earlier isolated
Activate/Reuters/Adjust run likewise had Activate pass and Reuters/Adjust fail,
so the differing terminal outcomes are recorded rather than averaged away.

The exact replay therefore leaves the implementation regressions **PASS** but
live editorial acceptance **PARTIAL / NO-GO**. The remaining blockers are
observed failures, not hypothetical edge cases: first-pass material coverage
can still remain incomplete after the bounded repair; grounding responses can
be malformed/incomplete or reject mixed evidence; and provider variability can
change which report-level gap is exposed. No validator, retry limit, evidence
binding, or publication gate was weakened. E18 remains **Active/PARTIAL**, Step
2 remains **PARTIAL/NO-GO**, and Step 3 remains **unstarted/not ready**.

### Fresh exact frozen-five replay for first-pass recovery — 2026-11-13 (`f848dba9`)

The requested fresh provider-backed replay ran from isolated state with the
canonical runner and the frozen manifest:

```text
python scripts/quality/run_frozen_reliability_cohort.py \
  --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json \
  --sources-root "C:\\Programing\\Market lense" \
  --runs-root "C:\\ml-first-pass-next-live-runs" \
  --max-duration 7200 --verified-facts-architecture
```

Run directory: `C:\ml-first-pass-next-live-runs\frozen-reliability-iwdh_qgp`.
The terminal result is `C:\ml-first-pass-next-live-runs\frozen-reliability-iwdh_qgp\cohort_result.json`.
The run used commit `f848dba9aac149902585dea67b477aab0c7276d7`, no operator
intervention, and no WordPress or other publication writes.

#### Terminal ledger

Counts below are mutually exclusive terminal outcomes. “Grounding batches”
counts root initial batches; split counts are recursive subdivisions recorded in
the usage ledger. A report that stopped before validation is shown as N/A; it
is not counted as a grounding pass.

| Report | Editorial / repair outcome | Grounding outcome | Final artifact / readiness | Calls | Input / output tokens | Cost | Wall-clock |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| Capgemini | Final roster retained after 3 targeted repairs; validation passed; downstream `card_tldr_compact_invalid` because the report-card manifest was missing | Pass; 16 root batches, 8 subdivisions, 8 structured-output repairs | `artifacts.json` and HTML retained; readiness **FAIL** | 156 | 1,569,905 / 259,756 | $0.301967 | 1,763.261 s |
| Activate | `insights_final` protected-metric contract remained invalid at repair attempt 2 | N/A; stopped before an accepted final artifact | No final artifact; readiness **FAIL** | 467 | 1,516,537 / 278,248 | $0.310660 | 3,420.540 s |
| KPMG | 7-insight artifact retained; public-editorial semantic review remained unresolved after primary, model repair, and regeneration paths | Pass; 20 root batches, no subdivisions | `artifacts.json` retained; readiness **FAIL** | 124 | 1,091,348 / 170,888 | $0.216975 | 1,340.385 s |
| Reuters Institute | Semantic theme repair exhausted for `ai-response-video-audio-priorities`; final roster remained incomplete | N/A; stopped before an accepted final artifact | No final artifact; readiness **FAIL** | 98 | 916,800 / 135,384 | $0.179129 | 1,338.404 s |
| Adjust | Final artifact reached validation, but safe removal found no replacement; 47 retained claims unresolved | Fail; 23 root batches, 5 subdivisions, 16 structured-output repairs | `artifacts.json` retained; no HTML/readiness | 246 | 2,708,723 / 365,998 | $0.446571 | 2,478.170 s |
| **Total** | **0/5 accepted for publication** | — | **0/5 readiness** | **1,091** | **7,803,313 / 1,210,274** | **$1.455302** | **10,340.760 s** |

The cohort-level report records report admission 5/5, typed terminal outcomes
5/5, bounded automatic-repair rate 0.4, and publication readiness 0/5. The
per-report `automatic_repair_count` is 3 for Capgemini and 0 for the other
four; Adjust is marked as having entered the bounded-repair path even though
its counter is zero. This is why the aggregate rate is not the same as the
sum of the per-report counter. The exact structured-output recovery counts are
8, 4, 3, 4, and 16 respectively.

The grounding-batch policy change is observable in the usage ledger: verified
validation used the smaller batch policy and preserved recursive subdivision;
legacy tests retained the 4-claim/8-public-item policy. Activate and Reuters
have no grounding result because they terminated earlier. No new retry stage or
repair attempt was introduced.

#### Source and editorial inspection

- Capgemini used the required PDF SHA
  `612f362e1bff3c307e4db4aed38414f7b3ac85dd5cba4742ef78625cd225ef3e`.
  Its 10 final insight IDs all matched their `verified-fact:<id>` primary
  evidence IDs and canonical physical pages; the numeric terms in all 10
  final texts were present on the cited PDF pages. The retained HTML is
  `C:\ml-first-pass-next-live-runs\frozen-reliability-iwdh_qgp\members\cohort-81af3890cd84ece81ef1\ias-first-attempt-b1vdz_q7\output\final-web-version-report-consumer-trends-2026-pdf.html`.
  It is 62,180 bytes and contains no `verified-fact:`, `candidate_id`,
  `evidence_id`, `primary_evidence_id`, or `fact_id` tokens. The independent
  public-quality review passed and retained factual validation reported zero
  unsupported and zero unresolved claims. This is a useful artifact-level
  result, but it is not a publication pass because the report-card manifest
  gate failed.
- Adjust used the required PDF SHA
  `ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`.
  The 10 retained final IDs and primary evidence IDs were source-authoritative
  and all 10 had numeric terms on their cited PDF pages. Independent review of
  the actual PDF pages found a rejected failure in the retained, non-published
  artifact: `gaming-partners-per-app` included the complete page-19
  subvertical-growth series even though its authoritative fact is the page-23
  partners-per-app observation. The validator reported this as semantic
  distinctness/analytical-depth failure and the pipeline stopped with 47
  unresolved claims; no HTML or public output was produced. This demonstrates
  why the final artifact cannot be treated as an accepted report merely because
  its numeric tokens are source-present.
- KPMG’s retained facts also passed the source-authoritative validation path
  (10/10 admitted, zero quarantined), but its public-editorial semantic review
  failed closed. Activate and Reuters were admitted to the workflow but
  stopped before their architecture evidence artifact was written, so their
  missing evidence files are recorded as unavailable rather than inferred as
  passes.

#### Comparison with the retained exact-five baseline

The previous exact-five baseline at `80ae8ef` recorded 990 calls,
6,472,871 input / 1,029,411 output tokens, `$1.260247`, and 9,138.651 seconds,
with readiness 0/5. The fresh run recorded 1,091 calls (+10.20%),
7,803,313 input (+20.55%), 1,210,274 output (+17.57%), `$1.455302`
(+$0.195055, +15.48%), and 10,340.760 seconds (+13.15%); readiness remained
0/5. Failure modes changed rather than improving: the current run exposed
downstream card-manifest, protected-metric, semantic-review, theme-repair, and
safe-removal failures. The difference cannot be attributed solely to the
implementation because both runs use provider-backed generation and the
retained evidence shows model/provider variability. The deterministic tests
below demonstrate the intended behavior; this replay does not demonstrate
improved live selection or first-pass acceptance.

The implementation slice is therefore **PASS** for the specified local
contracts and regression coverage, while the provider-backed acceptance is
**PARTIAL / NO-GO**. The remaining observed blockers are incomplete first-pass
material coverage, protected-metric recovery failure, public semantic-review
failure, and rejected cross-insight content before publication. E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**.

### First-pass editorial handover correction and bounded two-report replay — 2026-11-13 (`44acf2d3`)

This follow-up closes the remaining deterministic handover defects found by
the first-pass editorial work. The summary path now recovers an exact direct
binding before abstention, but a regeneration that leaves a required summary
field incomplete fails closed. The post-assembly atomic merge preserves that
abstained family status instead of restoring `generated` from the promoted
baseline. Verified summary prompts receive only canonical evidence packs for
accepted final-insight fact IDs; scoped semantic repairs receive only affected
entries and authorized admitted alternatives, while omitting metric objects so
the authoritative candidate restores protected facts. Normal-mode summary
policy and existing public-quality gates remain unchanged. No new LLM call,
validator, retry, schema, publication, or cache policy was introduced.

The deterministic verification after the correction passed:

- 318 affected artifact/render/regeneration/verified-authority tests;
- 107 focused first-pass, summary, prompt, source-fidelity, and ownership tests;
- 2 long-test-file ownership checks;
- Ruff on changed production/tests, formatting, `git diff --check`, and mypy
  on the four affected generator modules;
- the unchanged prompt-fixture gate: 118,841 tokens versus 118,469 baseline
  (+372, +0.31%), estimated `$0.025539` versus `$0.025502` (+`$0.000037`).

The fresh provider-backed replay was intentionally stopped after the first
blocker report, as required by the acceptance procedure. It used the exact
frozen Capgemini and Activate source inputs, no WordPress or publication
writes, and no operator intervention:

```text
python scripts/quality/run_frozen_reliability_cohort.py \
  --sources-manifest C:\ml-first-pass-next-live-runs\frozen-reliability-iwdh_qgp\frozen_cohort.json \
  --sources-root "C:\Programing\Market lense" \
  --runs-root C:\\ml-first-pass-editorial-live-44acf2d3-r1 \
  --report-ids cohort-81af3890cd84ece81ef1 cohort-cbb6e7df67412186b8bc \
  --verified-facts-architecture
```

Run root: `C:\ml-first-pass-editorial-live-44acf2d3-r1\frozen-reliability-1jniefox`.
The cohort terminal record is at
`C:\ml-first-pass-editorial-live-44acf2d3-r1\frozen-reliability-1jniefox\cohort_result.json`.
The run made 756 provider calls, used 4,958,786 input and 899,352 output
tokens, cost `$0.954202`, and took 6,777.652 seconds. These measurements are
reported as observed; they are not attributed to a cost or quality
improvement because the prior retained baseline used different provider
paths.

| Report | Candidate/admission | Final editorial and validation | Readiness | Calls | Input / output tokens | Cost | Duration |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| Capgemini | 10 evaluated, 10 admitted, 0 quarantined; final 10 | 10 verified; unsupported 0, unresolved 0; validation pass | **PASS** | 136 | 1,305,511 / 212,413 | `$0.258157` | 1,484.984 s |
| Activate | 10 evaluated, 10 admitted, 0 quarantined; final 10 | grounding failed closed after bounded repairs: 48 unresolved retained claims, 0 unsupported | **FAIL** | 620 | 3,653,275 / 686,939 | `$0.696045` | 5,292.668 s |

Capgemini’s retained artifacts are:

- HTML: `C:\ml-first-pass-editorial-live-44acf2d3-r1\frozen-reliability-1jniefox\members\cohort-81af3890cd84ece81ef1\ias-first-attempt-9r50mzpg\output\final-web-version-report-consumer-trends-2026-pdf.html`;
- artifacts: `C:\ml-first-pass-editorial-live-44acf2d3-r1\frozen-reliability-1jniefox\members\cohort-81af3890cd84ece81ef1\ias-first-attempt-9r50mzpg\output\final-web-version-report-consumer-1d9e64dd7425\report_analysis\artifacts.json`;
- validation/readiness: the corresponding `validation.json` and
  `publish_readiness.json` both report pass; the report-card manifest is
  retained in the `final-web-version-report-consumer-trends-2026-pdf` output
  directory.

The HTML is 62,110 bytes and contains zero `verified-fact:`, `candidate_id`,
`evidence_id`, `primary_evidence_id`, or `fact_id` strings. Its ten final
insights retain source-backed wording and the accepted secondary-fact compact
TLDR. Independent inspection found no unsupported material factual assertion
in the retained public output. Compared with the prior retained Capgemini
`f848dba9` run, this replay used 20 fewer calls (-12.82%), 16.84% fewer input
tokens, 18.23% fewer output tokens, `$0.043810` lower cost (-14.51%), and
278.277 seconds less wall time (-15.79%), while moving from missing-card/readiness
failure to validation/readiness pass. This is a useful report-level observed
difference, but not a cohort-wide attribution.

Activate’s final artifact retained ten source-bound insights and the compact
TLDR used an accepted secondary fact. The source-cached correction for
`insight-02` preserves the page-6 `$128B/5.7%`, `$108B/4.7%`, and `$66B/2.3%`
forecast relationship with its global 2017E–2021E scope and footnote. The
run nevertheless failed closed in grounding after three bounded repair paths:
malformed/incomplete semantic fields and a protected-fact conflict remained,
and the later public review also identified redundancy/material-coverage gaps.
No HTML, report-card manifest, readiness pass, or public artifact was
accepted. This is a corrected terminal location, not a successful acceptance.

The requested exact five-report extension was not run: Activate failed the
first two-report blocker gate, so Reuters Institute, KPMG, and Adjust were not
reprocessed at this SHA. The live run therefore does not establish 29-insight
or frozen-five readiness improvement, and no live selection-effectiveness
claim is made. The final two-report result is **implementation PASS / live
editorial acceptance PARTIAL / Step 2 PARTIAL-NO-GO / Step 3 unstarted-not
ready**. Remaining material blockers are provider-dependent first-pass
semantic completeness, bounded repair stability, and the absence of a fresh
accepted five-report cohort.

### Non-destructive repair correction and isolated Activate replay — 2026-11-13 (`bff8b75a`)

Commit `bff8b75ae7c5b1d98db17611ac0c7d8063906947` implements the three
requested root-cause corrections on top of `a6dd15c6`:

- scoped insight repairs retain the raw patch and overlay only explicitly
  supplied fields on the existing insight, so omitted `so_what`, `now_what`,
  metric copy, coverage metadata, report lens, and scores survive; explicit
  empty values remain explicit patch operations;
- the localized one-insight regeneration prompt no longer contains
  full-roster, theme-fill, or compact-card instructions, while the existing
  multi-insight prompt branch retains those requirements; and
- atomic summary reconciliation now fails closed with existing typed contract
  errors when an abstained summary has public copy/provenance or a generated
  summary lacks exact public-copy provenance.

Focused regressions cover raw text-only and explicit-field patches, localized
versus full-roster prompt rendering, protected-field restoration, valid and
conflicting summary claim-map repair, and summary abstention consistency. The
affected suites passed **182 tests**, the larger artifact/regeneration suite
passed **357 tests**, and the prompt/grounding fixture subset passed **80
tests**. The unchanged fixture gate passed at **118,841 tokens / `$0.025539`**
versus **118,469 / `$0.025502`** (`+372`, `+$0.000037`); formatting, Ruff,
targeted mypy, and diff checks passed. No schema, retry, publication, or
WordPress gate was weakened.

#### Fresh Activate replay

The required fresh isolated run used the exact Activate PDF and source hash
`5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`, from
clean commit `bff8b75a`, with no publication writes:

```text
python scripts/quality/run_frozen_reliability_cohort.py \
  --sources-manifest scripts/quality/frozen_reliability_cohort_20.json \
  --sources-root "C:\\Programing\\Market lense" \
  --runs-root "C:\\ml-non-destructive-repair-live-20261113\\activate-clean" \
  --max-duration 7200 --report-ids cohort-cbb6e7df67412186b8bc \
  --verified-facts-architecture
```

Run root: `C:\ml-non-destructive-repair-live-20261113\activate-clean\frozen-reliability-ffcfnv9u`.
The terminal record is in `cohort_result.json`; the member report-analysis
artifacts are under
`members\cohort-cbb6e7df67412186b8bc\ias-first-attempt-4qhmeqnr\output\d8ca0bf6efb9c7033438-d460f8aa84f6\report_analysis`.

| Measure | Fresh Activate | Prior retained Activate (`44acf2d3`) | Difference |
| --- | ---: | ---: | ---: |
| Provider calls | 488 | 620 | -132 (-21.29%) |
| Input tokens | 1,954,249 | 3,653,275 | -1,699,026 (-46.51%) |
| Output tokens | 353,689 | 686,939 | -333,250 (-48.51%) |
| Cached input tokens | 22,036 | not retained in the prior summary | not comparable |
| Estimated cost | `$0.382780` | `$0.696045` | -`$0.313265` (-45.01%) |
| Wall-clock | 3,582.970 s | 5,292.668 s | -1,709.698 s (-32.30%) |
| Structured-output repair calls | 7 | not retained in the prior summary | not comparable |
| Automatic repairs | 0 | 3 targeted repairs | not a quality comparison |

Verified-fact admission passed **10/10 evaluated, 10/10 admitted, 0
quarantined**, with complete coverage and the required PDF/source identity.
The candidate checkpoint was not empty: `artifacts.json` retained **10
candidate IDs** and **6 final IDs**. The `insights_candidates` provider event
was a valid completed call, so this run demonstrates provider-supplied
candidate output rather than a source-order empty-list fallback. The retained
artifacts do not expose a separate fallback-origin audit, so no stronger claim
about fallback invocation is made.

The first editorial pass produced a six-insight draft. Public semantic review
failed closed on `s03-video-spend-top-users` because it stated the 61% time,
34% spend, and 25% user shares without the required comparison that both
measured shares exceeded the cohort's user share. This is a first-pass FAIL,
not a verified-output success. The exact localized repair targeted only
`insights_final[item=s03-video-spend-top-users].text`. The retained repair
candidate added the missing comparison, preserved the two authoritative fact
IDs and physical page 15, and did not change the protected metric binding or
unlisted fields. Its audit records the authorized text-only path.

That repaired candidate was not promoted: candidate validation still reported
the existing derived-projection and family-status scope violations, after
which the workflow terminated with the typed `schema_type_mismatch` error
`root.insights_final[1].evidence_ids None is not of type 'array'`. The terminal
record reports one workflow attempt, zero automatic repairs, seven structured
output recovery calls, and no accepted HTML/readiness artifact. The persisted
draft's zero unsupported/unresolved counters are therefore not a readiness
result. The existing prompts already require omission rather than `null` for
unavailable optional arrays; this live provider-contract failure is recorded
fail-closed and was not “fixed” by weakening the schema.

The retained evidence is sufficient to classify the observed categories for
this run as: nonempty provider candidate generation; first-pass material
coverage failure; semantically correct but unpromoted localized text repair;
derived/scope validation failure; and terminal malformed optional-array
schema output. The previous replay's aggregate **48 unresolved Activate
claims** cannot be broken down into missing IDs, incomplete fields, protected
dimensions, `not_established`, and other categories from the retained
artifacts because raw provider responses were not retained. No breakdown is
inferred. Capgemini was not rerun: the acceptance procedure stops the wider
replay after the first failing report, so its earlier accepted run remains the
only non-regression evidence.

The implementation/regression verdict is **PASS**. The provider-backed
first-pass/repair acceptance verdict is **PARTIAL / NO-GO**: the intended
repair behavior is demonstrated in retained artifacts and local regressions,
but the fresh report did not reach final readiness. E18 remains
**Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**, and Step 3 remains
**unstarted/not ready**.

### Scoped projection correction and fresh Activate replay — 2026-11-13 (`f66e68ad`)

The prior `bff8b75a` repair failure was reproduced: assembly reapplied
transient abstained family statuses after atomic finalization, changing an
unrelated accepted summary status and causing the canonical derived-projection
and scope checks to reject a text-only insight repair. Commit `f66e68ad`
limits that reapplication to an authorized family; the existing consistency,
projection and scope guards remain in force. A regression reproduces the
unchanged abstained summary, verifies the corrected projection, and confirms
that an altered summary status is still rejected. A prior summary consistency
test was corrected to identify a real repair target. The affected suite passed
291 tests, targeted mypy and Ruff passed, and hosted CI run
[43497007454](https://github.com/mbrakker/marketlense/actions/runs/43497007454)
passed tests, coverage, both mutation partitions and release evidence.

The fresh isolated Activate run at `f66e68ad` is retained at
`C:\ml-repair-acceptance-live-20261113\activate\frozen-reliability-df6pu1kw`.
The source PDF SHA-256 was
`5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2`.
Ten facts were evaluated and admitted, none quarantined. First-pass review
failed because primary insight `i19` omitted the distinction between U.S.
adult news discovery and the separate active-news-reader search population.
The first targeted candidate added that distinction, retained its fact ID and
physical page 98, passed grounding and scope/projection validation, and reached
independent editorial review. Visual inspection of page 98 confirms the 40%
and 38% adult-discovery values and the separately labeled right-hand panel
and sample. Candidate 1 was rolled back: the review found weak, repetitive
primary analysis in unchanged `i06` and `i12` and a report-level distinctness
failure. Those weaknesses are visible in the retained text; they were not
treated as mere validator noise. Candidate 2 was rolled back after grounding
returned an incomplete `violation_type` verdict for `i23`; candidate 3 was
rolled back because removing `i19` violated an essential editorial obligation.
No candidate was promoted, readiness failed, and no report was published.

The run used 568 provider calls, 2,695,383 input and 535,565 output tokens,
15 structured-output recovery calls, 11 file-search calls, three targeted
repairs, `$0.546875`, and 4,292.331 seconds. Its zero retained unsupported and
unresolved factual counters are not an independently reviewed readiness pass.
The previous null-array failure was an assembled-artifact schema error; the
retained audit cannot establish whether the provider or a transformation
introduced the null. The newly discovered editorial findings cannot safely be
reused as baseline verdicts: the review sees the complete report and does not
record every dependency, while the existing review identity binds its whole
input. E18 remains **Active/PARTIAL** and Step 2 **PARTIAL/NO-GO**.

#### Capgemini non-regression replay at `f66e68ad`

The isolated run at
`C:\ml-repair-acceptance-live-20261113\capgemini\frozen-reliability-n6p1lrdg`
used source SHA-256
`612f362e1bff3c307e4db4aed38414f7b3ac85dd5cba4742ef78625cd225ef3e`.
It admitted 10/10 verified facts without quarantine, but first-pass grounding
failed closed on an inconsistent `now_what` verdict. Candidate 1 was rolled
back after another inconsistent grounding verdict and an incomplete independent
editorial review. Candidate 2 was rolled back because the editorial review
still failed its obligation-support contract. A subsequent safe-removal path
terminated with `insight_safe_removal_no_replacement`: no distinct supported
retained insight could fill the slot. No candidate was promoted and readiness
was not achieved. The cohort reports 49 unresolved retained factual claims;
these are unresolved validations, not independently confirmed false claims.
The editorial plan required both `verified-fact:ai-assistant-user-satisfaction`
and `verified-fact:weekly-shopping-assistant-use-and-satisfaction`, while the
retained reviewable insight carried only the latter. The similar candidate
texts do not by themselves justify merging identities or adding a binding.
Visual inspection of physical page 33 confirms 52% weekly use, 46%
satisfaction among those weekly users, and the report's separate qualitative
expectation that satisfaction will rise; it does not settle the identity or
editorial-plan binding contract.
The cohort summary reports zero automatic repairs; the two
persisted, rolled-back candidate audits are reported separately here.

The run used 248 provider calls, 3,423,913 input and 503,053 output tokens,
25 structured-output recovery calls, six file-search calls, `$0.576648`, and
2,837.701 seconds. The earlier accepted Capgemini run at `44acf2d3` used 136
calls, `$0.258157`, and 1,484.984 seconds. This is an observed regression, not
proof that the projection change caused it: provider outputs and run inputs can
vary. No accepted HTML was available for independent final-output review.

Commit `90410c20` subsequently made the existing accepted grounding violation
vocabulary visible in the provider output schema and recovery context while
retaining the validator and its aliases. A focused recovery regression and the
unchanged fixture gate passed (118,847 tokens and `$0.025540` against the
118,469-token, `$0.025502` baseline); hosted CI at `2401088f` passed tests,
coverage, both mutation partitions and release evidence. This schema/prompt
clarification addresses a proven contract gap, but the retained failed
response does not show whether that gap caused the specific `i23` failure.
Live effectiveness requires a fresh run at the revised producer version.

#### Activate replay at `90410c20`

The fresh isolated run is retained at
`C:\ml-repair-acceptance-live-20261113\activate-90410c20\frozen-reliability-l7w5sz09`.
It evaluated ten visual candidates, admitted eight, and quarantined
`insight_07` and `insight_08` with `outcome_unresolved`; the retained admission
audit does not establish whether those were factual rejections or response
failures. It produced eight candidate insights and five final draft insights.
Grounding retained an informational warning on a LinkedIn recommendation,
but independent editorial review failed closed after three response attempts
with `public_editorial_quality_obligation_review_support_mismatch`: the
essential revenue obligation required `verified-fact:01c`, which was not bound
to its supporting reviewable insight. No automatic repair was attempted and
the terminal outcome was `validation_failed`, with one unresolved retained
claim and zero recorded unsupported claims. These counters do not establish a
publication-ready report.

The run used 503 provider calls, 1,735,925 input and 349,782 output tokens,
nine structured-output recovery calls, ten file-search calls, `$0.369917`,
and 3,583.882 seconds. The fixed grounding vocabulary was present in this
producer version, but this failure occurred at editorial obligation binding;
the run does not establish improved grounding-recovery reliability. Visual
inspection of the five draft insight texts against physical PDF pages 5, 6,
11, 15, 38, and 52 found the reported figures and their stated populations,
forecast labels, and exclusions on those pages. The video insight reports
61%, 34%, and a 25% cohort but leaves the comparison to the cohort's share
implicit, the same kind of omission the earlier public review rejected.
No final HTML was accepted, and this targeted page check is not a full
independent review of every public assertion. The five-report cohort was not
started because the targeted acceptance cases did not pass. E18 remains
**Active/PARTIAL** and Step 2 remains **PARTIAL/NO-GO**.

The repeated mismatch exposes an unresolved contract conflict: generation's
theme-coverage check accepts any selected planned evidence ID, while the
public-review validator requires every original obligation ID to be bound to
supporting final insights. The published editorial contract and final-writing
prompt do not clearly establish whether redundant plan IDs are mandatory
lineage or alternative support. In this run `01c` covers an advertising
forecast already represented by `insight_02`; this overlap does not establish
a general equivalence rule. No evidence ID was automatically added, no
review gate was relaxed, and no selection contract was changed without a
resolved interpretation.

### Explicit fact obligations and failed live replay — 2026-11-14

The verified editorial plan now declares indispensable fact IDs and groups of
alternative support; selection, semantic review, public review and repair
retain and enforce that decision. Newly generated verified plans must supply
the declaration; legacy retained plans remain compatible. The model owns the
semantic decision and no evidence ID is added to satisfy a gate. Focused
regressions covered required facts, alternatives, exact IDs, bounded selection,
replanning and regeneration. Hosted CI for `6e7bde5b` passed tests, both
mutation partitions and release evidence.

A fresh isolated two-report run of production revision `4848a13e` is retained
at `C:\ml-contract-acceptance-20261114\live-4848a13e\frozen-reliability-v1p1vmug`.
Both reports failed closed at the artifact schema: Activate had
`insights_final[0].evidence_ids` equal to null; Capgemini had the same type
failure for index 1. Activate used 529 calls, 3,028,409 input tokens, 495,075
output tokens and $0.561863; Capgemini used 130 calls, 1,393,673 input tokens,
203,313 output tokens and $0.255303. Cohort wall time was 6,071.230 seconds.
Neither report passed readiness and no publication write occurred.

The null failure is reproducible in candidate factual restoration when a
final rewrite supplies null and the authoritative candidate has only its
primary evidence ID. The correction omits that optional field in this case,
and preserves a genuine multi-fact candidate binding when present. Retained
diagnostics do not prove the exact origin of either failing in-memory null.
Earlier repair candidates were separately rolled back: Activate had missing
metric public copy and unresolved editorial review; Capgemini had a material
limitations omission. They are not resolved merely by the null correction.
E18 remains **Active/PARTIAL** and Step 2 **PARTIAL/NO-GO** pending fresh
provider-backed first-pass, repair, factual and editorial acceptance.

The corrected `508d0f23` Activate replay admitted 10/10 visual candidates but
failed at `artifact_structured_output_invalid` for `insights_final` after a
rolled-back repair. It used 539 provider calls, 3,045,462 input tokens,
471,164 output tokens, eight structured-output repair calls, ten file-search
calls and $0.559395. The retained ledger does not identify the terminal
schema field; the earlier null failure must not be asserted as its cause.
The first candidate corrected a news-reader qualification, but retained an
unsupported revenue distinction and introduced an unsupported inference from
views to unique audience reach; independent grounding correctly rejected it.

The same `508d0f23` two-report run ended with Capgemini failing closed at
`regeneration_evidence_rebind_unresolved`, after 145 provider calls, 1,564,245
input tokens, 213,697 output tokens, ten structured-output repair calls and
$0.272062. The cohort total was 684 calls, $0.831457 and 6,315.621 seconds.
Neither report passed readiness, and no publication write occurred. The null
type error from the preceding run was not the terminal error in either report;
this does not prove the correction fixed every possible source of null values.

The repair planner had quarantined the validated canonical fact supporting
the revenue insight and its derived key figure after a wording-level
`not_established` verdict. A targeted correction now keeps that fact available
only when the exact issue binding agrees with the retained item and the
complete verified-fact snapshot validates; malformed or mismatched bindings
remain quarantined. Provider-free replay of the retained failure changes the
planned target from quarantined to the exact selected verified fact. This is
planning evidence only: the disputed wording remains blocked and neither
successful model repair nor publication readiness has been demonstrated.

The subsequent fresh isolated Activate-only run at `f88da8ab` is retained at
`C:\ml-contract-acceptance-20261114\live-f88da8ab-activate\frozen-reliability-zf32i0ue`.
It admitted 10/10 visual candidates, then failed validation after three
bounded repair attempts; all three candidates were rolled back. The terminal
report recorded two unsupported and zero unresolved retained factual claims.
It used 517 provider calls, 2,151,907 input and 448,913 output tokens, eleven
structured-output repair calls, $0.456671 and 4,082.625 seconds. The first
repair candidate had grounding and editorial failures and a soft-copy
provenance scope violation; the second still had grounding and editorial
redundancy failures; the third also violated the original verified editorial
obligations. None demonstrates a successful atomic repair or first-pass
readiness. The different admitted facts and output are normal model-run
variability and are not evidence of a causal quality improvement.

Independent inspection of the original Activate PDF confirmed that physical
page 7 labels the $165B subscription-growth chart “ACTIVATE FORECAST”; the
grounding rejection of that attribution reflects missing usable attribution in
the canonical fact context, not a demonstrated error in the PDF-based claim.
Page 38 separately distinguishes the forecast AR spending mix from expected
adoption sequence. The disputed recommendation was explicitly MarketLense's
own, which the existing grounding policy permits; the retained model verdict
nevertheless rejected it. Page 69 shows 50%, 19%, and less than 1% churn and
separate virtual-pay-TV and SVOD periods. The insight named those periods;
explicitly noting the lack of a narrower Pay TV period would improve clarity.
These observations do not establish that any repair candidate or report passed.

For Capgemini, the retained diagnostics do not identify the rejected insight,
evidence ID, or failing condition of the rebind guard. The guard and remediation
ledger now retain bounded identifiers and a reason category for future runs;
this is diagnostic only and does not establish the cause or relax eligibility.
First-pass and successful transactional repair acceptance remain **PARTIAL**.

An additional component-level scope reproduction found that whole-root
authorization of otherwise valid soft-copy provenance can permit an unscoped
sibling claim's evidence binding to change during a LinkedIn-only repair. The
reproduction did not establish promotion through downstream semantic checks.
Conversely, an invalid sibling claim can cause misleading scope errors for a
legitimately rewritten LinkedIn claim; the invalid candidate still fails closed.
These boundaries require claim-level authorization, not blanket root exemption.
Scope and audit now authorize individually verified provenance rows only when
their unique text hashes correspond to explicitly scoped sentence changes.
Component regressions reject unrelated same-family and cross-family binding
changes and duplicate identities. The existing whole-root verification
prerequisite remains: when a sibling claim has invalid provenance, the
candidate is rejected and secondary scope diagnostics may still be reported.
No live repair success follows from these component results.
