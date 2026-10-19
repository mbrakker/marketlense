# Verified Claims pre-merge acceptance — additional frozen-five reports

Date: 2026-10-19
Branch: `codex/fix-retained-insight-evidence-validation`
Historical implementation SHA: `d9823f5a69cd8934df90c663f94714d98c22f377`
Latest correction SHA: `410f186b26f372c6b8eb5a82af16dc5b8740c4af`
Latest verdict: **NOT READY TO MERGE; Step 3 remains blocked**

This is an acceptance record, not a production change. The replay used the
original 20-report manifest, selected the next five members in manifest order
after excluding Capgemini, Activate, KPMG, Reuters Institute, and Adjust, and
ran the existing isolated cohort runner with publication disabled. No
canonical artifact, readiness, WordPress, or publication write was performed.

## Cohort and source integrity

Selected manifest positions were 3, 6, 8, 9, and 10. Every source existed and
matched both the frozen MD5 and the independently computed SHA-256:

| Report | Stable cohort ID | Frozen MD5 | SHA-256 | Physical pages |
| --- | --- | --- | --- | ---: |
| DoubleVerify | `cohort-e854b71d6fb10333b47f` | `e854b71d6fb10333b47f518a6e51cf9` | `99f0cc4f7787cac52b7f89eefa7659053b3703ea100b9e0522fa500c64463d7e` | 12 |
| Merchant Risk Council | `cohort-11b0b55157f7d0636815` | `11b0b55157f7d0636815ad72435e1cf5` | `29c01d042b7020b3e43de3c6eb12c84e1fd7b960be6c73b877170fdec12932e6` | 4 |
| Algolia | `cohort-86858bdcb370266f26c2` | `86858bdcb370266f26c29b40316a4db0` | `d00f64fbeed9f004ca391f3195bf7f8d43804c08040da3ca3ec3a19e4771ab50` | 29 |
| Bain & Company | `cohort-77bc67b2bc98187d9d58` | `77bc67b2bc98187d9d589a4e69fd85f7` | `07541f3433b72007010ff604a93d0c560b6c6709ffd7bb5a58fefa81908f86c7` | 1 |
| Bigcommerce | `cohort-0a019f840c3f89ad0a96` | `0a019f840c3f89ad0a9672e058d1ff83` | `29ffb53b9818460066c86e8d954bdd904bd0e11d2360d90dac040a5d33b9e7c3` | 10 |

Source paths are the frozen paths in
`docs/quality/reliability-cohort-20260919-a21-final/frozen_cohort.json`.

## Full production replay

Command:

```powershell
py scripts/quality/run_frozen_reliability_cohort.py --sources-manifest docs/quality/reliability-cohort-20260919-a21-final/frozen_cohort.json --runs-root tmp/verified-claims-premerge-20261019 --report-ids cohort-e854b71d6fb10333b47f cohort-11b0b55157f7d0636815 cohort-86858bdcb370266f26c2 cohort-77bc67b2bc98187d9d58 cohort-0a019f840c3f89ad0a96 --max-duration 7200
```

The runner used fresh per-report state and the normal application/provider
configuration. Its default isolated execution was sequential; no shared
batch or cache substitution was used.

| Report | Final state | Selected | Topics / key figures | Validation / readiness | Calls | Input / output tokens | Cost | Duration | Terminal issue |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |
| DoubleVerify | `awaiting_review` | 5 | 7 / 3 | pass / pass | 42 | 390,740 / 90,048 | $0.090687 | 598.574s | none |
| Merchant Risk Council | `awaiting_review` | 5 | 5 / 2 | pass / pass | 39 | 320,693 / 97,867 | $0.091095 | 487.779s | none |
| Algolia | failed | 0 | unavailable | fail / fail | 63 | 46,863 / 33,276 | $0.021328 | 1,129.685s | `report_pipeline_artifact_missing` after two retries |
| Bain & Company | failed | 5 | 4 / 2 | fail / fail | 42 | 289,075 / 96,550 | $0.087068 | 564.639s | `validation_failed` at key-figure grounding |
| Bigcommerce | failed | 5 | 9 / 2 | pass / fail | 49 | 586,074 / 117,218 | $0.125589 | 793.574s | `cover_render_failed` |
| **Total** | 2 pass-ready / 3 failed | **20** | — | — | **235** | **1,633,445 / 434,959** | **$0.415767** | **3,574.251s** | 0 operator interventions |

The raw result is retained at
`tmp/verified-claims-premerge-20261019/frozen-reliability-rwum7m8u/cohort_result.json`.
All five reports were admitted. No report was published.

## Superseding corrected rerun

The production runner was rerun from a clean isolated state at correction SHA
`259cbaf18616497334d3d71c6988a7408d4bedc5`, using the same five source
manifest members, unchanged source PDFs, the normal provider policy, and
publication disabled. The complete result is
`tmp/verified-claims-premerge-20261019/frozen-reliability-i20737yc/cohort_result.json`.
All five source identities remained hash-matched. No WordPress, canonical
verified-claim, readiness-approval, or publication write occurred.

| Report | Selected identities in final artifact | Terminal state | Validation / readiness | Repairs / workflow retries | Calls | Input / output tokens | Cost | Duration | Terminal issue |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| DoubleVerify | `attention_index_normalization_reference`, `q1_2026_regional_fraud_sivt_rates`, `q1_2026_north_america_video_attention_by_device`, `q1_2026_regional_ad_interaction_index`, `q1_2026_regional_quality_tradeoff` | `awaiting_review` | pass / pass | 3 / 0 | 44 | 456,085 / 87,626 | $0.093173 | 548.187s | none |
| Merchant Risk Council | `realtime-payment-acceptance`, `post-purchase-fraud-coverage`, `survey-merchant-sample`, `survey-country-coverage`, `survey-business-size-coverage` | `awaiting_review` | pass / pass | 0 / 0 | 25 | 174,572 / 40,654 | $0.052024 | 296.730s | none |
| Algolia | `agentic-search-implemented`, `ai-search-purchase-likelihood-by-market`, `search-sourcing-approaches`, `agentic-search-integration-factor`, `agentic-search-roi-factor`, `agentic-search-retailer-control-factor` | `awaiting_review` | pass / pass | 0 / 0 | 33 | 351,917 / 63,508 | $0.081023 | 665.176s | none |
| Bain & Company | `born-tech-growth-share`, `tech-value-creators-cross-sector`, `market-value-growth-share-breakdown`, `cloud-platform-guidance`, `sector-market-value-technology-materials` | `failed` | fail / fail | 3 / 0 | 41 | 407,023 / 99,380 | $0.102652 | 568.343s | `validation_failed`: `metadata.title` grounding after bounded targeted repair |
| Bigcommerce | `preferred-wallet-cart-abandonment`, `contact-details-discount-walkaway`, `scroll-set-experience-friction`, `ai-relevance-and-discovery`, `guest-checkout-abandonment` | `awaiting_review` | pass / pass | 3 / 0 | 36 | 440,898 / 77,980 | $0.096723 | 523.088s | none |
| **Total** | **26 selected identities** | **4 pass-ready / 1 failed** | — | **9 / 0** | **179** | **1,830,495 / 369,148** | **$0.425595** | **2,601.524s** | **one independent semantic-validation failure** |

The Algolia failure chain is now resolved at its originating filesystem
boundaries. The first correction bounded the crop-refine report component
before fingerprint sidecars were written; the second correction makes the
shared atomic writer use a shorter unique temporary token only when the
normal sibling would exceed Windows `MAX_PATH`. The final Algolia artifact,
six selected insights, three cover PNGs, and report-card manifest were all
written and readiness passed. The manifest path was 252 characters on the
corrected run.

Bain's protected metric content is present in the corrected artifact: the
52% metric spine and Key Figure retain the `top 20 gainers across sectors`
cohort and `total market-value growth for the top 20 gainers across sectors`
denominator. Its terminal failure is instead a provider-produced
`metadata.title` grounding failure after three bounded targeted repairs; it
did not promote unsupported retained factual claims. This is a live
generation/readiness limitation, not evidence that the denominator fix
regressed.

Bigcommerce produced and reopened all three required cover sizes. The
report-card manifest references `assets/report-card-small.png`,
`assets/report-card-medium.png`, and `assets/report-card-large.png`; all three
files exist and their SHA-256 values match the manifest. The final artifact
retains the preferred-wallet 40% finding on physical page 4. The separate
real-report recovery regression still proves that an irrelevant methodology
page 2 cannot displace independently supported page 4 evidence.

The clean rerun's final states are mutually exclusive and contain zero
report-level workflow retries. Automatic repair counts are reported per
report and are not double-counted as retries. The aggregate cost, token, call,
and duration values come directly from the runner's terminal ledger.

The provider-free frozen-five regression was rerun at this correction SHA:

```powershell
python scripts/quality/replay_verified_claims_step2.py --provider-free --output tmp/verified-claims-premerge-20261019/step2-provider-free-259cbaf1.json
```

It again confirmed all 15 cases / 39 variants, all five PDF hashes, 29
retained frozen-five insights, and no fabricated fixture substitution. It
performed zero correction or verification calls by design, so it does not
claim live Step 2 quality or fresh selection effectiveness.

## Final Bain title correction replay (`410f186b`)

The latest `main` changes, including PDF page reconciliation, were integrated
at merge commit `727cef03` before this correction. The failing Bain source is
the retained PDF
`out/browser_downloads/www.bain.com/9e6d7f717c38/tech-tonic-shifts.pdf`:

| Source check | Recorded value |
| --- | --- |
| MD5 | `77BC67B2BC98187D9D589A4E69FD85F7` |
| SHA-256 | `07541F3433B72007010FF604A93D0C560B6C6709FFD7BB5A58FEFA81908F86C7` |
| Size | `274071` bytes |
| PDF metadata title | `Tech-tonic-shifts` |
| Independently visible cover title | `Technology isn't just` / `an industry anymore.` / `It's everything` |

The source-title resolver was previously selecting `tech tonic shifts` from
the filename, with `candidate_source=filename`, empty
`explicit_source_title`, and medium confidence. The corrected resolver selects
`Technology isn't just an industry anymore. It's everything` from
`candidate_source=cover_title_page`, with the same explicit source title and
high confidence. The bounded cover-title rule preserves the visible sentence-
case title while continuing to reject filename-only and generic candidates.

| Identity boundary | Before correction | After correction |
| --- | --- | --- |
| Selection / normalization | `tech tonic shifts` | `Technology isn't just an industry anymore. It's everything` |
| DocMap top-level title | inconsistent/short filename identity | `Technology isn't just an industry anymore. It's everything` |
| DocMap section 0 title | not used as an authoritative source identity | `Technology isn't just an industry anymore. It's everything` |
| Final HTML/report-card metadata | failed `metadata.title` grounding | same source-backed title in heading, title tag, meta description, JSON-LD, and manifest |

The current DocMap has no conflicting document aliases. The deterministic
identity-repair path was not invoked in the green Bain-only replay; the title
was already consistent before validation. Validation now receives the exact
source-title resolution established during ingestion instead of reconstructing
a different identity from empty filename/metadata inputs. Filename and
ambiguous alias fallbacks remain non-authoritative.

The Bain-only live replay used the normal GPT-6 Luna High configuration with
publication disabled. It completed at
`tmp/verified-claims-premerge-20261019/frozen-reliability-lng3rd_y/` with
`awaiting_review`, validation pass, readiness pass, `published=false`, zero
unsupported or unresolved retained factual claims, zero automatic repairs, and
zero workflow retries. It made 24 provider calls, used 190,897 input and
45,991 output tokens, cost `$0.056590`, and took 335.06 seconds. The final
HTML and report-card manifest both carry the corrected title. The selected
identities were `born-tech-growth-share`, `tech-value-creators-types`,
`market-growth-share-breakdown`, `asset-light-scaling-recommendation`, and
`cloud-platform-catalysts`.

The same additional-five cohort was then rerun at this SHA:
`tmp/verified-claims-premerge-20261019/frozen-reliability-28p518bm/cohort_result.json`.
Outcomes and measured usage were:

| Report | Selected identities | Terminal state | Validation / readiness | Calls | Input / output tokens | Cost | Duration | Terminal issue |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| DoubleVerify | `attention-index-normalization-q1-2026`, `quality-brand-suitability-regional-q1-2026`, `regional-inapp-video-attention-q1-2026`, `quality-fraud-sivt-regional-q1-2026`, `global-video-benchmarks-ctv-scope-q1-2026` | failed | fail / fail | 47 | 432,564 / 104,260 | $0.100399 | 645.155s | `validation_failed`: `public_editorial_quality.metric_label_relationship` |
| Merchant Risk Council | `realtime-payments-merchant-acceptance`, `post-purchase-fraud-section-scope`, `agentic-ai-payments-exploration-plans`, `annual-survey-merchant-base`, `realtime-payments-growth-characterization` | `awaiting_review` | pass / pass | 25 | 175,256 / 43,291 | $0.053412 | 327.222s | none |
| Algolia | `ai-intent-revenue-link-perception`, `revenue-investment-incentive`, `regional-ai-purchase-likelihood-agreement`, `agentic-search-integration-consideration`, `agentic-search-deployment-and-plans` | `awaiting_review` | pass / pass | 34 | 353,185 / 68,300 | $0.083546 | 666.694s | none |
| Bain & Company | `born-tech-growth-share`, `tech-value-creators-types`, `market-growth-share-breakdown`, `asset-light-scaling-recommendation`, `cloud-platform-catalysts` | `awaiting_review` | pass / pass | 25 | 174,283 / 63,864 | $0.061100 | 369.326s | none; one structured-output repair call |
| Bigcommerce | `preferred-wallet-abandonment`, `discount-message-opt-in-out`, `shopping-discovery-apps`, `reviews-validate-purchase-decisions`, `guest-checkout-abandonment` | `awaiting_review` | pass / pass | 29 | 325,836 / 55,169 | $0.071746 | 501.673s | none |
| **Total** | **25 slots** | **4 awaiting review / 1 failed** | — | **160** | **1,461,124 / 334,884** | **$0.370203** | **2,510.07s** | **no operator intervention** |

The Bain title defect is therefore resolved in the real source-backed path.
The aggregate remains non-green: the failure moved from Bain's title grounding
to an unrelated DoubleVerify editorial-quality validation failure. The current
fresh Bain run also materialized `metric_spine=[]` and `key_figures=[]`, versus
one of each in the retained corrected baseline, although the source-backed
52%/20% and asset-light content remains in findings and final text. This is
run-dependent generation variance; no unsupported numeric enrichment is safe,
so the limitation is recorded rather than repaired speculatively.

The final provider-free replay at this SHA is
`tmp/verified-claims-premerge-20261019/step2-provider-free-410f186b.json`.
It confirms **15 reference cases / 39 variants**, all five expected PDF hashes,
29 retained report insights, and complete page availability without fabricated
fixtures. As designed, it made zero correction or verification calls and does
not claim live visual quality or fresh Step 1 selection effectiveness.

The full local quality command completed with **7,782 passed, 37 failed,
1 skipped, and 31 deselected**. The failures include the CPython 3.14
wheelhouse guard, known grounding/retained-claim and report-analysis suites,
and the long-test-file threshold; the focused Bain/title/validation suites,
formatting, Ruff, type, architecture, contract-schema, documentation, and
backlog gates passed. No canonical artifact, readiness approval, publication,
or WordPress write was performed.

**Verdict:** Bain correction **PASS**; branch aggregate **NOT READY TO MERGE**.
Step 3 remains blocked. The aggregate result is not evidence of improved live
selection quality, and the unrelated DoubleVerify failure plus the observed
metric-spine/key-figure variance must remain visible to reviewers.

## Independent source and editorial review

The review used the original PDFs, current DocMap/findings/evidence-fidelity
artifacts where available, the selected `insights_final`, executive summary,
key figures, Expert View, and rendered HTML. The following high-value source
findings were checked against physical pages:

| Report | Source findings checked | Shortlist result and assessment |
| --- | --- | --- |
| DoubleVerify | p.3 APAC Brand Suitability Violation Rate 8.0% and Fraud/SIVT 0.4%; p.10 APAC In-App Attention Index 109/131; p.4 Global Video Benchmarks exclude CTV and AVOC is 29% global mobile app versus 7% desktop and 4% mobile web. | All three themes survived. The five selected claims are source-backed and commercially interpretable, although the set is heavily concentrated on APAC benchmark metrics. Final editorial quality, validation, and readiness passed. |
| Merchant Risk Council | p.2 43% accept real-time payments; p.2 63% explore or plan agentic AI payments; p.2 survey of 1,200+ merchants across 35+ countries and five analysis areas. | All checked findings survived. The adoption claims are useful; survey-size and analysis-area items are more contextual/generic. Final validation and readiness passed, with a non-blocking artifact-quality warning on the survey-size opening. |
| Algolia | p.9 61% plan to implement agentic search within 12 months; p.11 89% rate generative AI important to hyperpersonalization; p.15 89% rate complex product search effective (p.20 also reports 70%+ satisfaction with AI search/discovery revenue). | None reached selection: source ingestion succeeded, but artifact generation ended `report_pipeline_artifact_missing` before a final artifact existed. This is an upstream pipeline omission, not evidence that the findings were weak or unsupported. |
| Bain & Company | p.1 born-tech companies account for 52% of market-value growth for the top 20 gainers per sector; tech-led strategy contributes 20%; p.1 recommends data/analytics, asset-light scaling, partnerships, and tech talent. | The 52%, 20%, tech-linked value-creator, and asset-light findings survived selection. A fifth quote was selected without physical pages and was therefore unavailable to Step 2. Analysis was source-grounded, but the run failed later because a key-figure explanation omitted the source denominator. |
| Bigcommerce | p.4 40% abandoned a cart when the preferred wallet was unavailable and younger shoppers show greater UX-friction sensitivity; p.7 74% opted in and out of brand messages for a discount; p.9 AI/omnimodal contextual-relevance takeaway. | All five selected insights retain useful numeric or operational content and appear in the rendered HTML. Validation passed, but cover rendering failed. Step 2 independently found a false negative for the p.4 wallet claim (see below). |

The current selection preserves stable IDs, evidence IDs, physical pages, and
protected metric bindings in the available artifacts. The main observed
selection limitation is not unsupported promotion: Algolia never produced a
shortlist, and the Bain quote lacked a physical page binding.

## Historical comparison

The exact same reports were present in the historical 20-report run at
implementation SHA `89b4fc4c1159499806ed16993d76f3684fe3412e`, retained under
`C:\Programing\Market lense\tmp\a21-final-20260920-live\frozen-reliability-jkjbdjg4`.
The source identities and PDFs are unchanged, but the implementation SHA and
model run differ, so selection differences cannot be attributed to determinism
alone.

| Report | Historical selection | Current selection | Material stage difference |
| --- | --- | --- | --- |
| DoubleVerify | Section-level benchmark/context IDs, including attention normalization and DV methodology. | APAC metric claims, device attention, CTV boundary, and three page-3 rates. | Step 1/artifact selection changed the proposition mix; current physical bindings are more specific. |
| Merchant Risk Council | 63% agentic-AI claim plus generic acceptance/fraud-methodology context. | 43%, 63%, survey scope, and five analysis areas. | Step 1/artifact selection changed identity and specificity; source support remains p.2. |
| Algolia | Five selected insights, including 39%/53% investment and 47% integration considerations. | No final artifact. | New run failed in artifact generation before selection; this is not editorial omission. |
| Bain & Company | Five page-unbound section/finding IDs. | Five IDs with four physical p.1 bindings and one page-less quote. | Step 1/artifact generation preserved the numeric findings but did not bind the quote to a physical page; later validation failed on a key-figure denominator. |
| Bigcommerce | Five section-level insights on omnimodal discovery, apps, personalization, privacy, and UX. | Five more specific p.4/p.7/p.9 numeric and operational claims. | Step 1/artifact selection changed from broad sections to measurable findings; later cover rendering failed. |

These are measured output differences, not a claim of live selection
improvement. The current run establishes that source-backed findings can
survive selection for four reports, but not that candidate recall or repeated
run stability is improved across the cohort.

## Step 2 shadow against the new cohort

The existing evaluator was run shadow-only against the current artifact paths
and hash-matched PDFs with reference fixtures disabled. The evaluator's legacy
`expected_claim_count: 29` field is frozen-five-specific; the independent
count for this additional cohort is 20 available shortlist slots (19
evaluable: five each for DoubleVerify, Merchant Risk Council, and Bigcommerce,
and four page-bound Bain claims). Algolia had no shortlist, and the page-less
Bain quote was unavailable.

The raw ledger is
`tmp/verified-claims-premerge-20261019/step2-new-cohort-shadow-rerun/step2_shadow_report.json`:

| Report | Evaluable | First pass | After retry | Failed | Unresolved / skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| DoubleVerify | 5 | 5 | 0 | 0 | 0 / 0 |
| Merchant Risk Council | 5 | 5 | 0 | 0 | 0 / 0 |
| Algolia | 0 | 0 | 0 | 0 | unavailable / unavailable |
| Bain & Company | 4 | 3 | 1 | 0 | 0 / 0 |
| Bigcommerce | 5 | 4 | 0 | 1 | 0 / 0 |
| **Total** | **19** | **17** | **1** | **1** | **0 / 0** |

Measured Step 2 usage was 42 provider calls, 576,010 input tokens, 23,673
output tokens, 599,683 total tokens, estimated cost `$0.069443`, nine full-page
renders, and 443.307 seconds. The run used two correction attempts and two
verification attempts only where needed; no canonical approval or publication
write occurred.

The one failed claim was `Bigcommerce/mobile-wallet-cart-abandonment`. Full
physical page 4 visibly states that 40% abandoned a cart when their preferred
wallet method was unavailable. The recovery path nevertheless replaced the
retained page with page 2, which only describes survey methodology, and then
failed closed. This is a recovery/provenance false negative, not an
unsupported factual promotion. The other accepted corrections added
source-supported comparisons or context, including DoubleVerify's page-4 AVOC
breakdown and Bain's 52%/20%/28% cohort denominator and period.

The provider-free regression gate was also run:

```powershell
py scripts/quality/replay_verified_claims_step2.py --provider-free --output tmp/verified-claims-premerge-20261019/step2-reference-provider-free.json
```

It confirmed all 15 reference cases / 39 variants, all five frozen reference
PDF hashes, and physical page availability. It did not make a source-quality
claim because provider calls were intentionally skipped.

## Verification and merge decision

Passed:

- `pytest -q tests/test_artifact_insight_shortlisting.py tests/test_artifact_normalization.py tests/test_artifact_normalization_source_fidelity.py tests/test_artifact_evidence_binding.py tests/test_verified_claims_step2_replay.py tests/test_verified_claims_visual_generator.py tests/test_public_editorial_quality_generator.py tests/test_public_editorial_quality_provenance.py tests/test_regeneration_contracts.py tests/test_report_regeneration_identity_and_failures.py` — **266 passed**.
- Formatting gate and Ruff lint gate — passed.
- Provider-free 15-case / 39-variant source/hash/page gate — passed.
- No publication, canonical-claim, or WordPress writes — confirmed by cohort and shadow ledgers.

Known blocker:

- `python scripts/ci/run_type_check.py` fails with 11 existing unbaselined
  mypy errors, all in `src/generators/verified_claims_visual_generator.py`,
  which was untouched by this acceptance task.
  This acceptance task made no production-code change to mask or reclassify
  those errors.

**Recommendation: NO-GO.** The branch is not ready to merge as a fully
accepted cohort result and Step 3 must not begin: three of five fresh
production replays failed readiness, one selected insight lacks a physical
page binding, the Step 2 recovery path has a confirmed source-supported false
negative, and the repository type gate remains red. Step 1 and Step 2 remain
**PARTIAL**. This report records the evidence and limitations; it does not
claim improved live selection effectiveness from post-selection replay.

The recommendation above is historical for the superseded run. The latest
corrected rerun changes the measured result to four of five pass-ready reports
and one independently diagnosed Bain semantic-validation failure; it does not
justify a merge or Step 3 start. The current verdict remains **NOT READY TO
MERGE** until that failure is resolved or explicitly accepted by the release
owner. The full repository type gate and focused checks are green on the
correction SHA, and the known Algolia, Bain-denominator, Bigcommerce-cover,
and Bigcommerce-wallet defects have regression evidence.

The repository aggregate command
`python scripts/ci/run_quality_gate.py` was also executed. Its full pytest
stage selected 7,755 tests and completed with **7,717 passed, 1 skipped, 37
failed, and 31 deselected**. The failures were outside the changed production
boundary: one native wheelhouse test requires CPython 3.12 while this runner
is CPython 3.14; the grounding/retained-claim and two report-analysis failures
are in untouched suites; and the long-test-file ownership check still reports
existing oversized test modules. The crop regression was split so this change
does not add a new long-file violation. The aggregate therefore remains
non-green, despite the changed-boundary suite, type, format, Ruff,
documentation, backlog, architecture, and contract gates passing.
