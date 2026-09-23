# GPT-6 Luna migration evaluation — 2026-09-23

## Method

The comparison uses the same five retained PDFs from P6 Batch 1, including the
previously difficult IAB revenue report and the 250-page Activate outlook. The
source manifest is
`out/p6_editorial_acceptance/batch_01_payload_fix_crop_path_20260830/cohort_manifest.json`.
Each clean commit runs through the canonical isolated frozen-cohort production
queue, from admitted source ingestion through analysis, render, and publication
readiness. The run makes no public WordPress write. The frozen sources preserve
acquisition provenance but do not repeat live discovery or browser acquisition.

The fresh GPT-5.6 baseline uses `0a85fc118637705c71e9ce4b7602b7b9536d3aea`.
The first checkpoint-correct GPT-6 candidate uses
`8f9d47a5bee21b5b54e114014095e5abd446a65e`. The final current-code run
uses `32a3e0b7a36e9018a15bfe6f3c2a6ca9d30d4de1`. Each uses one immutable
cohort submission with five admitted sources and no operator intervention. Local
run artifacts remain under `out/gpt6_compare/baseline_fresh`,
`out/gpt6_compare/candidate_fixed`, and `out/gpt6_compare/release_candidate`.

Per-report cost comes from the usage ledger's retained `report_id` context.
The figures use each run's configured rate card and provider token counts;
they are estimates rather than a provider invoice. GPT-6 reasoning tokens are
included in reported output tokens, so they must not be added a second time.
Per-report elapsed time runs from first queued source job to the latest terminal
job update or provider usage event; reports run concurrently, so these times do
not add to cohort duration. The runner's `validation` field evaluates the whole
output directory and reads `fail` for every member when any member fails. The
table uses each report's terminal job and publication-readiness artifact instead.

## Fresh baseline and first GPT-6 cohort

| Report | GPT-5.6 outcome | GPT-6 outcome | Cost, GPT-5.6 → GPT-6 | Elapsed seconds, GPT-5.6 → GPT-6 |
| --- | --- | --- | ---: | ---: |
| Omnisend email, SMS, push | Review ready | Held: rendered untrusted evidence | $0.082705 → $0.039279 | 1903 → 2455 |
| Activate eCommerce 2025 | Review ready | Held: raw provider citation marker | $0.094809 → $0.044426 | 1900 → 1321 |
| IAB internet ad revenue 2024 | Held: provenance coverage | Held: numeric validation | $0.135926 → $0.087093 | 1327 → 795 |
| YouGov AI in media | Held: provenance bindings | Held: provenance coverage | $0.094417 → $0.051297 | 1727 → 2223 |
| Activate T&M outlook 2026 | Held: grounding and duplicate insight | Held: duplicate insight | $0.176641 → $0.078830 | 1009 → 1850 |

The GPT-5.6 cohort reached review readiness on **2/5** reports; the first GPT-6
cohort reached **0/5**. Total provider calls were 179 versus 173, estimated API
cost was **$0.584498 versus $0.300925** (48.5% lower), and cohort wall time was
**1909 versus 2462 seconds** (29.0% longer). GPT-6 reported 182,063 reasoning
tokens within 277,412 output tokens; the GPT-5.6 ledger did not report
reasoning tokens. Lower cost alone does not meet the quality acceptance gate.

## Artifact review and investigation

- **Omnisend:** The first GPT-6 report rendered an insight using
  `email-automation-performance`, whose retained evidence-fidelity artifact
  marked the referenced finding unsupported. Publication readiness held it.
- **Activate eCommerce:** The first GPT-6 output placed raw OpenAI file-search
  citation markers in public limitations, and its document map misread 29%
  retail share as an eCommerce growth rate. PDF page 2 labels eCommerce CAGR
  as 10%, physical-retail CAGR as 4%, and 2028 eCommerce retail share as 29%.
  Normalization now strips only provider citation markers from limitations.
  Document mapping uses high reasoning effort. A separate clean one-report run
  at `2ec509c0306545b54319725db760a7330bba6d67` passed validation and
  publication readiness, with no incorrect 29% growth claim or raw citation
  marker. It cost $0.047178 over 467 seconds with 26 model calls.
- **IAB:** The first GPT-6 report's “top 10 companies” claim is present in its
  evidence and on source PDF page 15, but the numeric gate treated `10` as an
  unsupported measured value. The GPT-5.6 baseline failed earlier at soft-copy
  provenance, so neither report was released. The gate was not changed.
- **YouGov:** Both models failed retained provenance checks. Neither has a
  publishable report in this comparison.
- **Activate 2026:** The GPT-5.6 output had an unsupported geographic claim
  and duplicate insights; the first GPT-6 output had duplicate B2B-buying
  insights. Both were held. A later high-document-map run had a different
  source-contradicted combined-growth claim, also held.

The GPT-6 ledger also recorded calls where all 8,192 allowed output tokens
were reasoning tokens, with no visible answer. This occurred in insight
candidate and final-insight routes; a high-effort document-map call reached the
same cap and needed structured repair. The three affected routes now allow
16,384 output tokens. LinkedIn generation and regeneration were separately
tested at high effort; regeneration was also tested at `xhigh` in one isolated
Omnisend run. Both trials still failed provenance bindings, so the production
LinkedIn allocation returned to medium. These are operator-policy changes;
prompts, schemas, validators, retrieval, and retry ownership were unchanged.

The baseline Omnisend summary and commentary retain the 2023 merchant cohort,
automation-versus-campaign contrast, and quantitative SMS comparison. The
first GPT-6 copy is shorter and loses some of that comparison; its five
insights remain specific but one rendered claim has an untrusted evidence ID.
The baseline eCommerce summary and expert commentary cover the same main
report themes as GPT-6, but the first GPT-6 insight incorrectly promoted the
chart's 29% retail-share figure to a CAGR. The high-effort single-report run
avoided that error. IAB's GPT-6 summary and insights were specific and numeric,
while the baseline had no final analysis artifact to compare. YouGov had no
final analysis artifact on either run. Both Activate 2026 versions produced
summaries, insights, and commentary, but source-validation errors prevented
editorial acceptance.

## High-document-map five-report run

At `2ec509c0306545b54319725db760a7330bba6d67`, the clean cohort still
reached **0/5** review-ready reports. It made 175 provider calls, cost
**$0.296979** (49.2% below GPT-5.6), and took **2408 seconds** (26.1% longer
than GPT-5.6). Its ledger recorded 170,943 reasoning tokens within 267,805
output tokens.

| Report | Terminal outcome | API cost | Enqueue-to-terminal/provider seconds |
| --- | --- | ---: | ---: |
| Omnisend | Soft-copy provenance bindings incomplete | $0.036902 | 469 |
| Activate eCommerce 2025 | Soft-copy provenance coverage invalid | $0.073144 | 1602 |
| IAB revenue 2024 | Soft-copy provenance coverage invalid | $0.062708 | 2066 |
| YouGov AI in media | Soft-copy provenance bindings incomplete | $0.045326 | 2405 |
| Activate outlook 2026 | Validation failed: source-contradicted growth claim | $0.078899 | 1071 |

The eCommerce document map and public insights in this cohort avoided the
incorrect 29% CAGR, but a later provenance check held the report. The isolated
`xhigh` LinkedIn-regeneration Omnisend trial also ended with
`soft_copy_claim_provenance_bindings_incomplete`, so higher effort did not solve
that failure.

The current-code cohort has also produced a source-faithful eCommerce document
map and limitations without raw citation markers. Its grounding check rejected
a LinkedIn claim attributing a recommendation to MarketLense without support;
bounded LinkedIn regeneration then failed soft-copy provenance binding. The
same unsupported-attribution pattern explains why correcting the chart and
citation issues alone did not make this report publishable.

The GPT-5.6 baseline used 10 structured-output repair calls and 9 artifact
regeneration calls across the five reports. This GPT-6 run used 14 and 18,
respectively. The eCommerce report accounts for the largest increase: one
repair and no regeneration on GPT-5.6 versus five repairs and eight
regenerations on GPT-6. The baseline queue recorded three bounded retry waits
in later projection jobs; this GPT-6 run recorded none. Terminal attempt codes
were provenance or validation failures, with no terminal provider API error
code in either run.

## Final current-code five-report run

The clean run at `32a3e0b7a36e9018a15bfe6f3c2a6ca9d30d4de1` reached
**1/5** review-ready reports. It made 175 provider calls, cost **$0.310657**
(46.9% below the GPT-5.6 baseline), and took **2360 seconds** (23.6% longer
than baseline). Its ledger recorded 172,943 reasoning tokens within 275,584
output tokens. The 16,384-token caps allowed an IAB insight-candidate response
to consume 9,538 output tokens, including 6,998 reasoning tokens, without
truncation at the old 8,192-token cap.

| Report | Terminal outcome | API cost | Enqueue-to-terminal/provider seconds |
| --- | --- | ---: | ---: |
| Omnisend | Review ready; editorial quality, material-claim evidence, and evidence fidelity passed | $0.038758 | 1840 |
| Activate eCommerce 2025 | Soft-copy provenance bindings incomplete | $0.048535 | 1840 |
| IAB revenue 2024 | Soft-copy provenance coverage invalid | $0.075681 | 2355 |
| YouGov AI in media | Validation failed: numeric 15-market reference absent from retained evidence span | $0.092137 | 1505 |
| Activate outlook 2026 | Soft-copy provenance bindings incomplete | $0.055546 | 797 |

Omnisend passed publication readiness, then its separate analytics projection
job reached `workflow_queue_projection_source_missing`; the baseline also
recorded this projection error in bounded retry waits. The isolated runner's
cohort-wide `validation` field reads `fail` for all five members because four
reports failed. Omnisend's own readiness artifact and terminal report state
show that it is awaiting review. Its evidence-fidelity artifact reports zero
rendered untrusted evidence IDs. The IAB analysis also had numeric and
grounding issues before provenance coverage held it. The source PDF does
include the YouGov 15-market footnote, but that footnote was absent from the
retained evidence span the validator checked; the gate was not changed.

## Release decision

Four complete GPT-6 five-report cohorts did not match the baseline's two ready
reports; the current-code result is one ready report. The estimated cost saving
does not offset the readiness regression or longer cohort time. Do not push
this migration to `origin/main` or publish these reports. The frozen-cohort
workflow validates retained acquisition through publication readiness, but it
does not rerun live discovery and browser acquisition, so the repository's
full discovery-to-publish validation requirement is also unverified. The
focused eCommerce pass does not establish cohort acceptance.
