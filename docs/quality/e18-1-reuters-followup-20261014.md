# E18.1 Reuters follow-up — canonical source and safety replay

**Date:** 2026-10-14  
**Current main:** `ec47b7b88a86253a5609b2493fabdb8da832dba6`  
**Retained run producer:** `705c57aa24684afad99a7f7f131564c38617fc56`  
**Disposition:** NO-GO for a production patch. GO for one deterministic, page-scoped relationship-binding experiment. No production code, prompts, publication behavior, or tests were changed. No LLM/API calls or external writes were made.

## Source and artifact identity

The frozen manifest is `docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json` (SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`). Reuters PDF `out/browser_downloads/reutersinstitute.politics.ox.ac.uk/b0e410340498/Trends_and_Predictions_2026.pdf` matches its manifest identity: MD5 `4b763ae2286ca69fe8acb63b17508dfb`, SHA-256 `f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52`. The retained `cohort/source.json` (SHA-256 `0910a0c5a06df2a882b792403c541a1263e1a226bd9635481578ad1b18654463`) names the same source identity, `source:79cb8c886c55b49bfdec2128d5b25e0b`, and MD5.

Retained attempt: `tmp/e18_1_reuters_current_head_20261013/attempt3/frozen-reliability-m5wdwg7u/members/cohort-4b763ae2286ca69fe8ac/ias-first-attempt-nr9yd9lw`. The relevant artifact hashes match the prior audit:

| Artifact | SHA-256 |
| --- | --- |
| `report_analysis/doc_map.json` | `3928a474d6afc9c774ce5c2cfe24a72535ac7864e00f5863f820058563cf6d8f` |
| `report_analysis/findings.json` | `c50bc21b8df473c3fd359f235f94d78bcd65c448858a42f48c632890987a9bb0` |
| `report_analysis/evidence_fidelity.json` | `c2e0795f147457bdb3621ecb3681e297ad1ab3f601d5849001c880872b463583` |

I recovered the cited pages through the current public `extract_pdf_text()` service (`src/services/pdf_service.py`, implementation `src/services/_pdf/text.py`) and compared the validator’s canonical hash, `_hash(page.text.strip())`, with each retained evidence reference. All nine match; the prior raw PyMuPDF page-hash comparison was not comparable to the validator’s canonical extraction/hash procedure.

| Physical page | Retained and recovered page hash |
| ---: | --- |
| 13 | `a09131e38ffa9bbb6016590b4f47c2faaec09451db130d1e3e25c335e4e40625` |
| 17 | `18934dfc678c9155f1183c01c9c0c3fabd43af89832549446c2fa69a9900d1ca` |
| 18 | `0857657ebb5cea8d35933eb7dc7fbf6c4793d5aa5610617f6992a342e93cc18a` |
| 21 | `a64bf8085d2b3da8e5b343b2264768c2f1e4b172b19ef73b1ee4c892d7cff4f3` |
| 25 | `e6b646360563ebda59a2c03e4de4272854e02252ad7e870834900ded163b9586` |
| 30 | `4ab8da5e210c0dfbb84e53d0b47cd75eafc2ab17228dc3f558048f0333732067` |
| 33 | `c28364aec95d7a0bedc7d825c3fcafec5b561ce7d915ed8de1d79a1384886cb6` |
| 38 | `ed3c568138e58fd420c160c66ca8d4b50b162ccd07cdc502d01790400eda53db` |
| 41 | `b6a02b1d637d631853943224967189638a10cf7b9042677ea97dc1cdb5fd9afe` |

The cached `text_13d98fab6372.json` contains only the initial context pages. Its absence of these later pages was a missing cache artifact, not a source or pipeline identity failure: deterministic extraction from the matching frozen PDF recovered all cited page hashes exactly. Current main differs from the retained producer only by the earlier audit documentation; the source extraction, fidelity and quantity code has no diff between those commits.

## Candidate replay and source reference

I reconstructed the 16 unchanged candidate texts and page references from the retained fidelity ledger, then called the unchanged public `validate_evidence_fidelity()` with the recovered canonical page spans. The replay reproduced all 16 decisions exactly: 16 unsupported, all solely `quote_not_matched`. Each candidate’s quoted chart heading independently matches its cited page after removing only the syntactic trailing comma/semicolon/colon carried inside the quote delimiters; changing a substantive word in a heading (`needs` → `must`) remains rejected as `quote_not_matched`.

| Page / candidate IDs | Canonical source proposition | Proposition-only replay |
| --- | --- | --- |
| 13: `google-search-global-referrals`, `google-search-us-referrals`, `google-search-europe-referrals` | Google Search referral changes: global −33%, U.S. −38%, Europe −17%, year-on-year Nov. 2024–Nov. 2025. The page has the regional column labels and the corresponding signed table values. | All three fail `quantity_not_entailed`: `down 33%` is parsed as positive `+33%` against source `−33%`. |
| 17: `content-original-reporting-priority`, `content-contextual-analysis-priority` | Q13 net priorities: +91 original investigations/on-the-ground reporting; +82 contextual analysis. | Both supported. |
| 18: `content-video-priority`, `content-audio-priority` | 79% prioritize more video; 71% prioritize more audio. | Both supported. |
| 21: `platform-priorities-2026` | +74 YouTube, +61 AI platforms, +56 TikTok. | Supported. |
| 21: `platform-effort-reductions-2026` | −52 X, −25 Google Search (old style), −23 Facebook under the chart’s “net difference” measure. | Unresolved (`quantity_not_established`); keep excluded because the extracted span does not type/bind these bare values as a numeric unit. This is not counted as a confirmed validator false rejection. |
| 25: `creator-journalist-initiatives` | 76% creator-like journalist behavior, 50% creator distribution partnerships, 31% hiring creators, 28% joint ventures/studios. | Supported; the 76/50/31/28 distribution is already present in the retained summary. |
| 30: `misinformation-perception` | Strengthen: 52% vs 41% last year; weaken: 27% vs 41% last year. | Supported. |
| 33: `newsroom-ai-impact-assessments`, `newsroom-ai-jobs` | AI impact 44/42/13%; job effects 67/16/9%. | Both supported. |
| 38: `commercial-revenue-priorities-2026`, `platform-funding-revenue-2026` | Commercial publishers: subscriptions 76%, display 68%, native 64%, events 54%, platform funding 37% in the chart. | Both supported. The page prose also reports 36% platform funding; retain the 37% as a chart-specific value and preserve the intra-report discrepancy. |
| 41: `agentic-browsers-impact-forecast` | 75% expect large/very large impact in the next three years, comprising 15% very large and 60% large. | Supported. |

For a bounded eligibility check, I split each original compound statement in memory into (a) the quoted title and (b) its factual proposition, required both results to be supported, then passed the combined statuses through the existing `exclude_untrusted_evidence()` filter. Twelve candidates remained in the findings pack; the three p. 13 items remained rejected and the p. 21 negative-value item remained unresolved. This demonstrates eligibility for later editorial processing only. No insight was forced or selected; retained artifacts do not carry candidate scores for these absent insights.

## Safety counterfactuals and first-loss attribution

The candidate-kind decision is exclusive: `_claim_kind()` returns `quotation` as soon as it sees quote marks (`src/generators/claim_validation_generator.py:187`), and `_checks()` uses mutually exclusive numeric-versus-quote branches (`:572–657`). The trailing comma inside each quoted heading also makes the current quote substring longer than the source heading. This is the first loss for the 16: evidence fidelity rejects them, then `exclude_untrusted_evidence()` removes them before editorial input (`:2546`; called from `src/generators/evidence_pack_generator.py:1272`).

Direction is a separate defect. `extract_quantities()` treats `down 33%` and `up 33%` alike as positive 33 (`src/utils/quantity.py:264`); `_numeric_evidence_status()` then matches values/units anywhere in the cited page (`src/generators/claim_validation_generator.py:2432`). In an in-memory signed-form counterfactual, the correct global −33% claim becomes supported, but so do unsupported variants: global Google Search −38% (the U.S. value), global Facebook −33% (the Google Search value), and a November 2023–November 2025 timeframe. Wrong units remain unresolved and a wrong amount (−31%) remains rejected. Independently, the current validator accepts “Facebook referrals were down 9%” against a source value of +9%, because the direction word is ignored.

Simply making quote and quantity checks conjunctive is unsafe too. With the exact quoted heading valid, both the title and number-only checks pass for these unsupported same-page swaps:

- p. 17: +82 assigned to original reporting and +91 to contextual analysis;
- p. 18: 71% assigned to more video and 79% to more audio;
- p. 21: +61 assigned to YouTube and +74 to TikTok;
- p. 33: 67% assigned to small job cuts and 16% to no jobs cut;
- p. 38: 68% assigned to subscriptions and 76% to display;
- p. 41: 60% assigned to very large impact and 15% to large impact.

The current semantic batch fallback in `evidence_pack_generator.py:1248` runs only when deterministic fidelity is unresolved. A numeric match on a page with all values can therefore be treated as supported before any semantic relationship check. The specialized `_chart_relationship_fidelity_check()` in `claim_validation_generator.py` does not bind these table rows/categories. Existing tests for wrong geography, timeframe, unit, direction and cohort relationships pass, but their prose fixtures do not cover these same-page chart/value swaps.

**First-loss classification:** the 16 rejected originals are a current evidence-fidelity false rejection; the p. 21 negative row is an unresolved safeguard and remains excluded; the p. 25 candidate is a supported alternative already in final copy; other retained editorial choices are legitimate alternatives, not losses. Direction-only or quote-only fixes would create current false acceptances, so the demonstrated problem is not safely repairable by changing candidate readiness or loosening quote checks.

## Verification and recommendation

Focused deterministic regression selection (no live/provider tests):

```text
pytest -q tests/test_claim_validation_generator.py::test_numeric_and_quote_claims_pass_without_semantic_call tests/test_claim_validation_generator.py::test_evidence_fidelity_rejects_a_generated_finding_with_the_wrong_number tests/test_claim_validation_generator.py::test_evidence_fidelity_treats_year_over_year_endpoint_as_timeframe tests/test_claim_validation_generator.py::test_evidence_fidelity_rejects_wrong_year_over_year_endpoint tests/test_claim_validation_generator.py::test_evidence_fidelity_excludes_an_unsupported_finding_from_editorial_input tests/test_claim_validation_generator.py::test_evidence_fidelity_rejects_a_matching_value_with_the_wrong_period tests/test_claim_validation_generator.py::test_evidence_fidelity_rejects_a_matching_value_with_the_wrong_geography tests/test_claim_validation_generator.py::test_evidence_fidelity_rejects_wrong_unit_and_recovers_exact_page_provenance tests/test_claim_validation_generator.py::test_evidence_fidelity_does_not_rebind_to_same_values_for_another_subject tests/test_claim_validation_generator.py::test_evidence_fidelity_rejects_subject_rank_and_comparison_inversions tests/test_claim_validation_generator.py::test_evidence_fidelity_rejects_direction_and_attribution_inversions tests/test_claim_validation_generator.py::test_actual_activate_video_insight_matches_validated_finding_relationship tests/test_claim_validation_generator.py::test_activate_video_insight_rejects_numeric_values_absent_from_finding
```

Result: **13 passed in 1.63s**. These are baseline safeguards, not evidence that the proposed change is safe; the Reuters same-page counterfactuals above expose gaps they do not cover. The offline page extraction and replay used no provider and cost `$0.00`.

**Recommendation: NO-GO for production implementation now.** Do not change `_claim_kind()`, `_checks()`, or `extract_quantities()` in isolation. **GO for one no-provider deterministic experiment** that binds candidate metric, region/category, sign, unit and timeframe to row/cell-level source evidence on the cited pages, then replays all 16 candidates plus the counterexamples above through both fidelity and `exclude_untrusted_evidence()`. Keep direct quotation validation as an independent conjunct. Promote a production diff only if the correct candidates become eligible while every swapped relation remains unsupported or unresolved; leave the p. 21 negative values excluded until their unit is source-bound. No production change is justified by the present evidence.

The tempting minimal diff—make `_checks()` run both quote and numeric checks and ignore a trailing delimiter, then make `extract_quantities()` sign `down N%`—is specifically rejected: the offline probes show that it would accept same-page value/category and region/metric/timeframe swaps. Any later production diff must pair independent quote and numeric checks in `_checks()` with a source-bound relationship guard; only then should direction parsing in `extract_quantities()` be considered. The evidence filter and provenance requirements need no relaxation.
