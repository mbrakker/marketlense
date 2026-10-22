# Source-grounded editorial audit — frozen ten-report cohort

**Audit date:** 2026-10-22
**Implementation HEAD audited:** `d6f85e5a35ec0f2f02c068a69609cfb0a997b129`
**Source cohort:** DoubleVerify, KPMG, Reuters Institute, Adjust, Algolia, Bain & Company, Criteo, Deloitte, Emplifi, and StackAdapt Inc.
**Source integrity:** 10/10 expected PDF SHA-256 values matched; all ten PDFs and retained artifacts were readable.

## Verdict

**PARTIAL — no new selector or evidence-binding production change is justified by this audit.**

The audit inspected every accessible Step 2 final-editorial row against its original PDF, using physical PDF pages and the retained evidence/fidelity records. The 59 rows rate **33 HIGH, 22 MEDIUM, 4 LOW, and 0 INVALID** as source-grounded editorial findings. “LOW” means source-supported but weak as a standalone MarketLense insight; it is not a factual failure. The one Criteo row rated HIGH as a source finding is **not verified**: it failed closed after two malformed verification responses.

The audit found no independently confirmed unsupported material claim marked verified. It did find four traceability/selection limitations that remain open: a final-stage roster substitution in Emplifi, a source-supported but inherited evidence identity in the Algolia shadow correction, three provisional page recoveries, and high-value alternatives omitted inside already-covered themes. These findings do not support an arbitrary keyword score, new ranking framework, or a selector-only patch.

## What was audited

The trace was performed as:

`source PDF → findings/DocMap/evidence packs → raw candidate response → evidence-fidelity admission → deterministic shortlist → final editorial roster → Step 2 correction/verification`

- The audit used the exact retained first isolated run at `tmp/ten-full/frozen-reliability-9kx4zae9`, the explicit Step 2 ledger at `tmp/step2-ten-live/result.json`, and the hash-pinned PDFs in the cohort manifest.
- It inspected the full physical pages named by each retained binding. Page numbers below are physical PDF pages, not printed page labels.
- It did not use stable candidate IDs as a quality proxy. Stable IDs are reported only to join the retained artifact, final wording, source binding, and terminal outcome.
- The Step 2 replay evaluates `artifacts.insights_final`, the final editorial roster. The Step 1 selection ledger records `artifacts.insights_candidates`. Those rosters match for 9/10 reports; Emplifi has one source-supported final-stage replacement. Therefore Step 2 coverage is not, by itself, a recall assessment of the raw candidate pool.

**Verification hygiene note:** the audit itself was local and provider-free. A separate explicit-replay command was mistakenly started with a flag combination that the helper does not treat as provider-free; it was interrupted after 14 bounded correction/verification calls (DoubleVerify 10, KPMG 4), 95,499 input tokens, 4,930 output tokens, `$0.012016` estimated cost, and about 84 seconds. It produced no accepted result and made no canonical, publication, or WordPress write. Those calls are excluded from every result below and are not evidence of ten-report live quality.

## Selected-finding matrix

The complete wording, protected fields, evidence IDs, spans, and attempts remain in `step1-selection-ledger.json` and `step2-verification-ledger.json`. This matrix records the independent source/importance assessment for every accessible final row.

| Report | Finding identity | Physical source page | Terminal outcome | Rating | Independent assessment |
|---|---|---:|---|---|---|
| DoubleVerify | `q1-2026-attention-index-normalization` | 9 | verified | HIGH | Exact 100 baseline, 28-day rolling window, and vertical comparison are source-grounded and useful for interpreting the index. |
| DoubleVerify | `q1-2026-brand-suitability-regional-rates` | 3 | verified | HIGH | Exact regional violation rates and source scope; a distinct brand-safety benchmark. |
| DoubleVerify | `q1-2026-apac-device-format-attention` | 10 | verified | HIGH | Device/format values and the final “highest in-app” comparison are supported by the regional table. |
| DoubleVerify | `authentic-attention-solution` | 8 | verified | LOW | Accurate product-definition/proof-point language, but largely vendor-described capability context rather than a differentiated benchmark. |
| DoubleVerify | `q1-2026-display-viewability-regional-rates` | 3 | verified | MEDIUM | Exact and useful, but overlaps the selected regional quality-benchmark theme. |
| KPMG | `carveout-activity-expectations` | 6 | verified | HIGH | Central executive-summary outlook; structural/forward-looking qualifier is preserved. |
| KPMG | `ai-expands-analytical-scope` | 6 | verified | HIGH | Directly supports the report’s AI diligence/modeling thesis and its concrete analytical implications. |
| KPMG | `execution-capability-and-value-capture` | 6 | verified | HIGH | Central commercial conclusion about execution as a structural differentiator. |
| KPMG | `carveouts-proactive-portfolio-action` | 6 | verified | MEDIUM | Source-supported action finding, but materially overlaps the carve-out outlook row. |
| KPMG | `execution-risk-focus-areas` | 35 (recovered; original binding empty) | verified | MEDIUM | Page 35 directly supports talent, IP-separation, and systems-integration risks; provenance is provisional because the retained artifact had no original physical page. |
| KPMG | `ai-adoption-across-deal-stages` | 6 | verified | MEDIUM | Source-supported lifecycle adoption finding, but adjacent to `ai-expands-analytical-scope`; distinct enough not to merge safely. |
| Reuters Institute | `focus-original-reporting` | 17 | verified | HIGH | Exact +91 net difference and Q13 base; distinctive response to AI commoditisation. |
| Reuters Institute | `search-traffic-forecast` | 12 | verified | HIGH | −43% is correctly retained as a respondent expectation over three years, not an observed decline. |
| Reuters Institute | `social-referral-decline-facebook-x` | 20 | verified | HIGH | Exact Chartbeat referral declines and period; commercially material distribution signal. |
| Reuters Institute | `creator-response-plans` | 25 | verified | MEDIUM | Exact 76% publisher response; useful but less decision-specific than the strongest distribution findings. |
| Reuters Institute | `newsroom-ai-initiatives-assessment` | 33 | verified | MEDIUM | Correctly preserves the mixed 44%/42% assessment; valuable counter-signal but primarily descriptive. |
| Reuters Institute | `commercial-revenue-priorities` | 38 | verified | MEDIUM | Correct commercial-publisher population and 2026 period; one revenue priority rather than a broad commercial model. |
| Reuters Institute | `publisher-view-ai-misinformation` | 30 | verified | HIGH | Source-grounded counter-signal with population, comparison year, and all response categories retained. |
| Adjust | `multiplatform-measurement` | 11 | verified | HIGH | Directly connects 31% satisfaction with cross-platform attribution and a commercially meaningful measurement problem. |
| Adjust | `ai-operational-uses` | 9 | verified | MEDIUM | Source-supported utility-phase description; partly generic and dependent on a qualitative maturity framing. |
| Adjust | `gaming-casual-growth` | 19 | verified | HIGH | Exact global install/session growth and 2024–2025 period. |
| Adjust | `gaming-retention-all` | 21 | verified | MEDIUM | Exact baseline rates, but mostly context and less distinctive than the selected growth/CPI findings. |
| Adjust | `ecommerce-installs-sessions-2025` | 27 | verified | HIGH | Exact opposing install/session directions and period; strong commercial signal. |
| Adjust | `ecommerce-cpi-deal-discovery` | 29 | verified | HIGH | Exact $1.44→$2.26 CPI change and category binding. |
| Adjust | `finance-latam-installs` | 35 | verified | HIGH | Exact regional leader and paired install/session growth; source table supports the comparison. |
| Algolia | `revenue-incentive-58` | 5 | verified | MEDIUM* | The Step 2 corrected claim (53%/39% search investment) is supported by page 5, but the shadow result inherited the candidate’s `ch2-revenue-incentive` identity and 58% metric binding. Source fact is supported; lineage continuity is not clean for canonical promotion. |
| Algolia | `search-capability-development-approaches` | 22 | verified | HIGH | Exact 49/27/23 development split and third-party rationale; commercially actionable. |
| Algolia | `ai-search-purchase-agreement-regional-range` | 12 | verified | HIGH | Full-page visual inspection confirms total n=1,100, USA n=300, Australia/NZ n=200, and the 68%/57% values. |
| Algolia | `agentic-search-deployment-and-plans` | 26 (recovered; original binding empty) | verified | MEDIUM† | Full page supports 17% implemented and 61% planned, including the n=1,100 chart; original artifact page binding was empty and recovery remains provisional. |
| Algolia | `agentic-adoption-considerations` | 27 | verified | HIGH | Correctly distinguishes the 90% Top 2 from the 47% “very influential” component and preserves comparison metrics. |
| Algolia | `search-investment-and-adoption-activity` | 23 | verified | MEDIUM | Source-supported 2024/2025 investment comparison, but it is close to the corrected 53%/39% proposition on `revenue-incentive-58`; not merged because the period/category bindings differ. |
| Bain & Company | `born_tech_top_gainers_share` | 1 | verified | HIGH | Exact 52% share, top-20-per-sector population, and 2015–2020 dates. |
| Bain & Company | `tech_growth_mix_2015_20` | 1 | verified | HIGH | Exact 52/20/28 composition with dates and population preserved. |
| Bain & Company | `asset_light_scaling` | 1 | verified | MEDIUM | Source-supported action, but generic when separated from the four-action frame. |
| Bain & Company | `tech_strategy_value_creators` | 1 | verified | LOW | Broad “technology companies/tech-led strategy” conclusion is accurate but weakly specific as a standalone insight. |
| Bain & Company | `cloud_platform_action_frame` | 1 (recovered; original binding empty) | verified | MEDIUM† | Full page supports all four actions and the cloud/platform framing; original artifact page binding was empty and recovery remains provisional. |
| Criteo | `incrementality-metrics-retail-media` | 7 | verified | HIGH | Exact 50% relationship and “North Star” interpretation on the measurement page. |
| Criteo | `newer-channels-perceived-roi` | 5 | failed_verification | HIGH‡ | The original 61% proposition is printed on page 5, but both verification attempts were malformed/insufficient and the claim was correctly not marked verified. |
| Criteo | `agency-recommendations-performance-retention` | 8 | verified | MEDIUM | Exact 51/45 and 47/40 recommendations; useful but descriptive. |
| Criteo | `omnichannel-management-next-year-focus` | 8 | verified | MEDIUM | Exact US 54% focus and next-year qualifier; commercially relevant but narrow. |
| Criteo | `ctv-smaller-brand-access-concern` | 6 | verified | HIGH | Exact 47% concern plus source-supported launch inventory context; distinctive access risk. |
| Deloitte | `trust-in-ai-ordering` | 3 | verified | HIGH | Exact 14% trust statistic and gating-factor interpretation. |
| Deloitte | `brand-data-control-versus-reach` | 3 | verified | HIGH | Central strategic trade-off stated in the introduction; qualitative interpretation remains defensible. |
| Deloitte | `ai-visibility-data-interpretation` | 5 | verified | HIGH | Directly supports GEO/data-readiness implications without adding unsupported causality. |
| Deloitte | `ai-shopping-default-plan-2026` | 7 | verified | MEDIUM | Exact 24% forecast, but partly overlaps the 64% use-plan row. |
| Deloitte | `ai-shopping-use-plan-2026` | 8 | verified | MEDIUM | Exact 64% forecast and strategic conclusion; related to, but not equivalent to, default use. |
| Deloitte | `genai-retail-traffic-2025-holiday` | 5 | verified | HIGH | Exact 693% cited traffic increase and holiday comparison; source attribution is preserved. |
| Emplifi | `ai-marketing-disclosure-expectation` | 13 | verified | HIGH | Exact 91% expectation and transparency context. |
| Emplifi | `strategy-consistency` | 19 | verified | MEDIUM | Source-supported operating-model conclusion, commercially useful but qualitative and broad. |
| Emplifi | `behavior-high-value-research` | 4 | verified | HIGH‡‡ | Final-stage roster replacement is directly supported: >$ / £500 purchases, 3+ sites, and >1 hour. It is not present under the same ID in Step 1 `insights_candidates`; this is a roster-lineage exception, not a factual error. |
| Emplifi | `trust-reviews-2026` | 10 | verified | HIGH | Exact 79%/77% review comparison and purchase-stage behavior. |
| Emplifi | `service-response-time-expectation` | 15 | verified | MEDIUM | Exact 84% expectation and service implication; useful but narrower than the positive-resolution outcome omitted from the candidate shortlist. |
| StackAdapt Inc | `retail-2026-values-misalignment-shopping` | 15 | verified | HIGH | Exact 51% values-misalignment behavior and clear purchase relevance. |
| StackAdapt Inc | `retail-2026-prepurchase-brand-engagement` | 11 | verified | MEDIUM | Source-attributed 3+ engagement statistic; useful context but not a differentiated mechanism. |
| StackAdapt Inc | `finding-21` | 20 | verified | MEDIUM | Source conclusion supports the integrated programmatic thesis, but is broad and partly promotional. |
| StackAdapt Inc | `retail-2026-consumer-data-relevance-expectation` | 13 | verified | HIGH | Exact 68% expectation and privacy-era data relevance; distinct from the spend mix. |
| StackAdapt Inc | `finding-20` | 19 | verified | LOW | Source-supported capability list, but generic without a measured outcome. |
| StackAdapt Inc | `retail-2026-display-ctv-spend` | 7 | verified | HIGH | Exact 45.85%/30.83% split and 76.68% combined spend from internal platform data. |
| StackAdapt Inc | `retail-2026-daily-marketer-ai-use` | 14 | verified | LOW | Exact 88% third-party statistic, but generic and less central than the privacy/data and spend findings. |

**Matrix count:** 33 HIGH, 22 MEDIUM, 4 LOW, 0 INVALID. The asterisk/dagger markers are provenance or terminal-outcome qualifiers, not evidence of an unsupported verified fact.

## Material omitted alternatives

These are source-supported candidates present in the retained raw candidate/finding inventory but not retained at the candidate stage. They are not all errors: the selector has bounded capacity, uses editorial-plan themes, and does not have a source-recall oracle. Where a final-stage row covers the same source finding, that is recorded rather than counted as a final omission.

| Report | Omitted candidate | Page | Rating | What the source shows / why it matters | Observed disposition |
|---|---|---:|---|---|---|
| DoubleVerify | `q1-2026-ad-interaction-index-regions` | 10 | MEDIUM | Distinct regional Ad Interaction Index: EMEA 139, APAC 109, North America 99, LATAM 84. | Same attention theme already occupied by APAC device/format values; omission is editorial, not unsupported evidence. |
| DoubleVerify | `q1-2026-fraud-sivt-regional-rates` / `q1-2026-video-viewability-regional-rates` | 3 | LOW | Valid regional quality metrics, but repetitive with the retained brand-suitability/display rows. | No safe reason to force another same-page benchmark into a five-slot payload. |
| DoubleVerify | `q1-2026-monthly-attention-impression-volume` | 9 | LOW | 100+ billion impressions per month is scale context, not a differentiated finding. | Correctly treated as supporting context. |
| KPMG | `tools-perform-production-and-verification-tasks` | 24 | HIGH | The AI execution section says tools read documents, execute analysis, write deliverables, and verify outputs against standards. | Candidate pool contained it; it lost within a bounded six-item roster to other AI/execution findings. It is a genuine recall opportunity, not a factual defect. |
| Reuters Institute | `ai-browser-agentic-app-impact` | 41 | HIGH | 75% of respondents expect AI browsers/agentic apps to have a large or very large publisher impact over three years (60% large, 15% very large; base 265). | Raw candidate was source-supported but shared the highest-priority search/AI-interface theme with the stronger −43% forecast; no selector patch is justified without a recall objective. |
| Reuters Institute | `innovation-barriers` | 40 | MEDIUM | Resources (62%) and cross-group alignment (48%) are the leading innovation barriers. | Same commercial/innovation theme as the retained revenue priority; editorial omission. |
| Criteo | `us-digital-campaign-cost-estimate` | 7 | HIGH | US agencies estimate digital campaign costs will rise 22% in 2023. | Lost within the measurement theme to incrementality; material alternative for a cost-focused story. |
| Criteo | `agency-channel-choice-strategy-factor` | 4 | MEDIUM | New digital-channel choice (59%) outranks privacy regulation (45%) and economic conditions (32%) in strategy formation. | Lost within the new-channel theme to the 61% perceived-ROI finding. |
| Criteo | `retail-media-point-of-sale-roas` | 6 | LOW | Retail media’s point-of-sale position makes ROAS easy to prove. | Accurate but generic/promo-like; omission is appropriate. |
| Deloitte | `genai-discovery-and-shopping-speed` | 6 | HIGH | 23% already use generative AI for product discovery; among those users, 35% use it to speed shopping. | Same journey theme as the selected 693% traffic finding; source-supported alternative not selected. |
| Deloitte | `ai-shopper-conversion-study` | 6 | MEDIUM | The report attributes a 9× conversion result to one study. | Requires explicit external-study attribution and is less safe as a standalone report finding. |
| Emplifi | `high-value-research-time-shift` | 4 | HIGH | +24 percentage points in consumers spending over an hour researching high-value purchases. | Covered by final-stage `behavior-high-value-research`; not a final content omission, but it demonstrates candidate/final roster substitution. |
| Emplifi | `repeat-buying-after-positive-resolution` | 18 | HIGH | 59% of total respondents bought from the brand again after a positive resolution (62% US, 57% UK). | Genuine high-value candidate omission inside the service theme; service-response expectation was retained instead. |
| Emplifi | `more-business-after-positive-resolution-by-country` | 18 | MEDIUM | 40% US versus 26% UK gave more business after a positive resolution. | Distinct commercial follow-through, but narrower than the total repeat-purchase finding. |
| Emplifi | `ai-content-trust-by-country` | 13 | MEDIUM | US trust in AI content 35% versus UK 28%. | Same transparency theme as disclosure expectation; omitted comparison remains source-supported. |
| StackAdapt Inc | `retail-2026-first-party-contextual-data` | 12 | HIGH | First-party/contextual data are presented as foundations for privacy-first targeting, personalization, and measurement as signals decline. | Candidate-stage omission within the data theme; the selected 68% relevance expectation covers only part of this mechanism. |
| StackAdapt Inc | `retail-2026-social-content-discovery` | 10 | MEDIUM | 82% use social/content platforms to research or discover products. | Same discovery theme as 3+ brand engagements; omission is editorial. |
| StackAdapt Inc | `retail-2026-personalized-interaction-expectations` | 14 | MEDIUM | 71% expect personalized interactions. | Same AI-creative theme as the selected 88% daily-AI-use signal; omission is not a binding failure. |

Adjust had no persisted rejected/omitted candidate inventory in the package; its seven retained rows came through the fallback path. This is an artifact-availability limitation, not evidence that Adjust has no omitted source findings.

## Root-cause findings

### Candidate count and construction

The candidate prompt asks for 6–8 items. The retained raw candidate outputs were 8 for DoubleVerify, Reuters, Criteo, Deloitte, Emplifi, and StackAdapt; 7 for KPMG; 6 for Algolia; and 0 for Adjust because that artifact used the fallback path. The deterministic candidate roster retained 5–7 rows per report. No raw output exceeded the prompt bound, and no prompt-only change is supported.

The most important omissions were already present in the candidate pool (Reuters AI-browser impact, KPMG execution tooling, Criteo campaign-cost increase, Deloitte discovery-speed, Emplifi positive-resolution purchase, StackAdapt contextual data). This locates those omissions at bounded editorial selection/final generation, not at PDF extraction. The retained package does not persist a selector rejection reason for each candidate, so a more precise sub-stage attribution would be fabricated.

### Deterministic shortlisting and fallback

`evidence_backed_shortlisting:5` uses direct evidence strength, retained relevance/metric/novelty scores, editorial-plan priorities, and theme coverage. It does not use arbitrary business keywords. The ten-report replay shows broad coverage without forcing every weak alternative: 49 of 55 plan themes have an exact selected evidence-ID match; the remaining six are qualitative/ID-mapping cases where exact ID matching is not a reliable coverage oracle. All selected rows retain evidence IDs, spans, pages, and protected fields.

The recurring pattern is one or more candidates competing within an already-covered theme. The selector/final stage then preserves a bounded roster rather than adding every high-scoring alternative. That is an editorial trade-off, not a factual-integrity failure. Merging the KPMG AI rows, Algolia investment rows, or Deloitte 24%/64% rows would risk removing distinct periods, populations, or propositions. Conversely, adding a keyword score or increasing the minimum would manufacture redundancy and weaken the existing fail-closed behavior.

Fallback behavior was not shown to promote an unsupported or source-order-only finding in this cohort. Adjust’s fallback rows are page-bound and source-supported; the existing fallback theme-coverage and fidelity regressions pass. No fallback or cache-version change is justified.

### Final-stage lineage and Step 2

The final editorial generator is allowed to preserve final wording and select a source-supported final roster. Emplifi demonstrates why final IDs must not be used as a quality proxy: `behavior-cross-check` in `insights_candidates` is replaced by source-supported `behavior-high-value-research` in `insights_final`.

The Algolia Step 2 correction is source-grounded on physical page 5, but the shadow evaluator retains the input evidence ID and protected candidate metric from the original 58% revenue proposition. That inherited binding is not safe evidence for canonical promotion of the corrected 53%/39% proposition. Step 2 is shadow-only, so no canonical artifact was mutated; the issue remains a provenance-completeness limitation.

KPMG `execution-risk-focus-areas`, Algolia `agentic-search-deployment-and-plans`, and Bain `cloud_platform_action_frame` were verified against recovered physical pages 35, 26, and 1 respectively. The pages support the final claims, but the original retained page bindings were empty; these remain provisional recoveries rather than clean original bindings.

Criteo `newer-channels-perceived-roi` is the reliability negative case: the original page supports 61%, but both verification attempts were malformed/insufficient. The terminal outcome is `failed_verification`, not verified, and the failure did not block subsequent claims.

## Before/after acceptance ledger

| Measure | Existing retained baseline | Independent audit result | Change / interpretation |
|---|---:|---:|---|
| Source PDFs hash-matched | 10/10 | 10/10 | No source identity regression. |
| Step 1 candidate-stage rows | 59 | 59 | No production selection change. |
| Step 2 final-editorial rows | 59 | 59 | All accessible; one Emplifi final-stage identity substitution. |
| Step 2 verified first pass | 58 | 58 | Unchanged. |
| Verified after retry | 0 | 0 | Unchanged; no double-counting. |
| Failed verification | 1 | 1 | Criteo remains correctly fail-closed. |
| Independently source-invalid verified rows | not established | 0 found | Audit is source-grounded, not P6 human acceptance. |
| Source-rating HIGH / MEDIUM / LOW / INVALID | not measured | 33 / 22 / 4 / 0 | New independent quality matrix; LOW is editorial weakness, not factual invalidity. |
| Original empty-page rows later recovered | not separated | 3 | KPMG, Algolia, Bain; source-supported but provisional. |
| Exact candidate/final ID overlap | not reported | 58/59 | IDs are lineage metadata, not a quality score. |
| Clean independent Step 1 repetitions | 5 reports only | 5 reports only | No fresh recall or repeatability claim. |
| Canonical/publication/WordPress writes | 0 | 0 | Shadow-only boundary preserved. |

## Remaining limitations and decision

- The package has no independent source-recall oracle or blind human P6 review. Omitted-finding judgments are an engineering audit, not a measured recall percentage.
- Only five reports have a clean supplemental isolated Step 1 run; the shared-batch repetition is invalid because it reused a run directory and failed all ten reports.
- Candidate/final roster provenance is recorded in separate artifacts but not yet emitted as a single typed stage field in the Step 2 report. The replay helper’s documentation now explicitly distinguishes `insights_final` from the raw candidate pool; no behavioral schema change was made.
- The Algolia corrected-claim binding and three recovered page bindings remain shadow-only limitations. They must not be treated as canonical verified-claim evidence.
- The report has no evidence that raising the minimum count, changing theme weighting, or adding a business-keyword score would improve quality without weakening diversity or factual safeguards.

The evidence therefore supports **PARTIAL**, with Step 1/E18 and Step 2 shadow verification still open. It does not support closing P6, claiming live selection improvement, promoting canonical verified claims, or starting Step 3.

## Source-recall acceptance oracle — 2026-10-22

The compact [source-recall reference set](source-recall-reference-set.json) records six materially important source findings against the exact hash-matched PDFs. Each row includes the physical page, bounded source quotation, metric/population/timeframe/status where applicable, commercial importance, and an essential-versus-alternative classification. Semantic credit is intentionally strict: a related topic or adjacent commercial implication does not count as the same finding.

Against the retained ten-report final roster, **0/6 reference findings received semantic recall credit**. Emplifi's repeat-buying result is the one `essential` omission; the Reuters, KPMG, Criteo, Deloitte, and StackAdapt rows are `valuable_alternative` omissions. The selected rows remain source-grounded; this is an editorial-recall result, not a factual-error count. KPMG is further qualified because its page-24 quote is source-verified in the audit inventory but has no supported `quote-2` row in the retained evidence-fidelity ledger, so its exact selector eligibility cannot be reconstructed.

The five supported non-KPMG rows were present in the retained candidate/finding inventory and absent from the selected candidate roster. The artifacts do not persist per-candidate rejection reasons, so the evidence supports a bounded candidate-stage selection/final editorial trade-off but not a deterministic ranking defect. No keyword score, minimum-count increase, or forced replacement is justified by this post-selection oracle alone. The oracle does not claim fresh live selection effectiveness; the clean repeatability and new-run results are recorded separately.
