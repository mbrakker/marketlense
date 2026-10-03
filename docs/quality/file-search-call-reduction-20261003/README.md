# OpenAI File Search call reduction (2026-10-03)

## Result

On the frozen next-five cohort, actual Responses API File Search executions fell from **49 to 33** (**16 fewer; 32.7%**). All five reports were admitted, passed final validation and publication readiness, ended in `awaiting_review`, and required no operator intervention. No publication attempt occurred.

The 40% target was not reached. The change removed independent File Search from taxonomy, scope, methods, and limitations. The remaining searches serve doc-map extraction, findings, and verbatim quote discovery. Removing those would need a separate quality-equivalence result; this benchmark does not establish that it is safe.

## Frozen runs

| Run | Commit | Cohort result SHA-256 |
| --- | --- | --- |
| Baseline | `f70871ace4ec36827192955334217649496f4ed7` | `c3586f5b3504d6c029acd4da8a8ed2625b12d737afda104ef4e6fcf58f43f86f` |
| Candidate | `be70355a28b8f58d517768420024fd3baf92dde0` | `0d529f363b31ce2753a8cd810026210cb4ce9372fb00f31eaf5149d4916190fb` |

Both runs used the same five frozen report IDs and source identities from `reliability-cohort-20261001-next-five/frozen_cohort.json` (SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`). Each report used fresh isolated state. Only the five-report cohort was run. Publication was disabled in each generated run configuration.

The machine-readable comparison, including per-report source identities, actual call attribution by workflow, stage, family, prompt namespace, vector-store ID, and repair attempt, quality counts, and output artifact hashes, is in [evidence.json](evidence.json). The attributed call counts reconcile to 49 baseline and 33 candidate executions. It contains no prompts or retrieved source excerpts.

## File Search attribution

Counts are actual `file_search_call` output items, grouped by artifact family across the five reports. They are not inferred from Responses request count.

| Artifact family | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| `doc_map` | 16 | 19 | +3 |
| `taxonomy` | 6 | 0 | -6 |
| `scope` | 6 | 0 | -6 |
| `methods` | 5 | 0 | -5 |
| `limitations` | 5 | 0 | -5 |
| `findings` | 6 | 9 | +3 |
| `quote_candidates` | 5 | 5 | 0 |
| **Total** | **49** | **33** | **-16** |

The four bounded families made no hosted File Search calls in the candidate. The additional three doc-map and three findings calls reflect runtime search counts in the retained high-value families; the measured saving is therefore lower than the 22 calls removed from taxonomy/scope/methods/limitations.

| Report | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| Capgemini Research Institute — *What matters to today’s consumer 2026* | 12 | 8 | -4 |
| Activate — *Tech & Media Outlook 2018* | 11 | 8 | -3 |
| KPMG — *2026 Global M&A Outlook* | 9 | 6 | -3 |
| Reuters Institute — *Journalism and Technology Trends and Predictions 2026* | 9 | 6 | -3 |
| Adjust — *Mobile app trends: 2026 edition* | 8 | 5 | -3 |

## Cost, provider usage, and time

| Metric | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| Model provider calls | 206 | 187 | -9.2% |
| Input tokens | 1,837,877 | 1,873,502 | +1.9% |
| Output tokens | 369,596 | 309,163 | -16.4% |
| Estimated File Search cost | $0.122500 | $0.082500 | -$0.040000 |
| Estimated model-token cost | $0.354575 | $0.337258 | -4.9% |
| Estimated total cost | $0.477075 | $0.419758 | -12.0% |
| Elapsed time | 2,818.888 s | 2,583.722 s | -8.3% |

File Search was priced at $0.0025 per actual call in both runs. Model and tool costs use the existing usage ledger and pricing configuration.

## Implementation

- The usage ledger now counts each `file_search_call` item in `response.output`, including multiple calls in one response, while keeping unrelated tool accounting intact.
- The doc-map response includes File Search results. The adapter reads the SDK’s direct result `text` and filename fields and records those results in the typed response contract.
- Shared retrieval is keyed by prompt and verified vector-store content identity, retained in the configured cache directory for seven days, and tested for restart reuse and source-hash invalidation.
- Taxonomy and the bounded evidence packs consume a shared, relevance-ranked excerpt bundle in separate generation calls. Repeated query metadata is grouped, excerpts are balanced across search groups, and the serialized bundle is capped at 72,000 characters. Schema recovery reuses the original evidence.
- Findings, doc map, and quote candidates retain hosted File Search. The cohort does not justify removing it from these high-value discovery tasks.

## Quality and artifact review

Baseline and candidate both had **5/5** admitted reports, **5/5** final validation passes, **5/5** readiness passes, and **0/5** unsupported or unresolved retained factual claims. Every report ended in `awaiting_review`; workflow attempts remained one per report. Bounded automatic regeneration occurred for two baseline reports and none in the candidate. The one report with two structured model-repair events had two in each run; no recovery added a File Search call.

All 16 publication-readiness rules passed in all ten report runs, with no failed rule IDs:

`build_traceability`, `category_consistency`, `editorial_quality`, `evidence_fidelity`, `figure_linkage`, `material_claim_evidence`, `public_identifier_leak`, `public_source_provenance`, `public_title_quality`, `regeneration_promotion`, `rendered_scaffolding`, `repeated_boilerplate`, `report_card_manifest`, `retained_claim_grounding`, `semantic_grounding`, `source_fidelity`.

I inspected the final HTML and the doc-map, findings, quote-candidate, readiness, and retained-claim artifacts for each report. Candidate HTML files are 59.8–63.1 KB, with 27–31 headings and 54–60 paragraphs. Doc maps contain 12–17 sections; findings contain 8–16 report-specific claims. The outputs continue to cover consumer value and shopping, technology/media outlook, M&A, journalism and answer engines, and mobile-app performance. Candidate copy varies from baseline, as expected for model-backed generation; the changed summaries and findings remain grounded and every retained-claim and editorial readiness rule passes. Per-output hashes and counts are retained in `evidence.json`.

Publication safety was checked from each isolated run: `publish_enabled` was false, with **0 published records, 0 publication approvals, and 0 publish/WordPress outbox jobs**. Readiness calculation is present; no publication write was attempted.

## Verification

- `python -m pytest -q tests/test_openai_chat_service.py tests/test_openai_vector_store.py tests/test_openai_accounting_service.py tests/test_cost_ledger_service.py tests/test_llm_usage_ledger_service.py` — **104 passed**.
- `python -m pytest -q tests/test_structured_output_execution.py tests/test_taxonomy_generator.py tests/test_evidence_pack_generator.py tests/test_report_generation_contracts.py` — **54 passed**.
- `python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py tests/test_llm_service.py tests/test_llm_routing_policy.py` — **96 passed**.
- `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py` — **66 passed**.
- `python -m pytest -q tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py` — **35 passed**.
- `python scripts/ci/check_contract_schemas.py` — passed.
- `python scripts/ci/check_public_report_quality.py` — passed.
- Targeted Ruff checks on changed Python files (ignoring the repository’s existing `E501` and `C408` findings) and `git diff --check` — passed.

## Decision

Stop at 33 calls for this change. The benchmark proves reuse for taxonomy, scope, methods, and limitations, with lower total cost and elapsed time and no material input-token increase. Further reduction would require changing the high-value doc-map/findings/quote retrieval paths; that is outside the proven safe boundary of this comparison.
