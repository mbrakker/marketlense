# Report Analysis Orchestrator Decomposition Review

Date: 2026-05-29

## Decision

`src/orchestrators/report_analysis_orchestrator.py` remains the public report-analysis coordinator and compatibility surface. Stable helper responsibilities moved into private modules under `src/orchestrators/_report_analysis_orchestrator/`.

This preserves the modular monolith and does not introduce a new orchestration entrypoint, service boundary, prompt namespace, provider path, schema, retry policy, or cost behavior.

## Boundary Rationale

The previous module combined several stable orchestration sub-responsibilities behind the same public workflow:

- bounded artifact-step scheduling
- vector-store readiness polling
- report payload metadata and completeness validation
- validation fallback and regeneration-loop execution
- deterministic regeneration-plan and grounding mapping

These are semantic owner modules, not line-count buckets. `run_report_analysis()` still sequences the workflow from one public module, while private owners contain deterministic helper logic that can be tested and audited independently.

The split creates more than three private peer modules, so this review is required.

## Verification Evidence

- Pre-refactor focused suite: `python -m pytest tests/test_report_analysis_generator.py tests/test_report_pipeline_orchestrator.py tests/test_report_generation_entrypoint_cleanup.py tests/test_report_generation_dependency_contracts.py tests/test_artifact_generator.py tests/test_validation_generator.py tests/test_cli.py -q` passed with `95 passed`.
- Pre-refactor deterministic baseline: `C:\Users\8FEE~1\AppData\Local\Temp\report_analysis_orchestrator_baseline_pre_lbx3l17f\baseline.json`
- Red ownership test before movement: `python -m pytest tests/test_report_analysis_orchestrator_decomposition.py -q` failed because `_report_analysis_orchestrator/` modules did not exist.
- Post-refactor affected suite: `python -m pytest tests/test_report_analysis_orchestrator_decomposition.py tests/test_report_analysis_generator.py tests/test_report_pipeline_orchestrator.py tests/test_report_generation_entrypoint_cleanup.py tests/test_report_generation_dependency_contracts.py tests/test_artifact_generator.py tests/test_validation_generator.py tests/test_cli.py -q` passed with `97 passed`.
- Post-refactor deterministic baseline: `C:\Users\8FEE~1\AppData\Local\Temp\report_analysis_orchestrator_baseline_pre_ch16jcx7\baseline.json`
- Pre/post deterministic baseline comparison, excluding temp root and elapsed wall time, was exact: validation status `pass`, evidence path keys `analysis_vector_store, artifacts, context_category_fit, doc_map, findings, methods, report_context, validation`, and snapshot keys `analysis_vector_store, context_category_fit, report_context`.
- CI-equivalent gates passed: formatting, risk policy, split-symbol links, type check, architecture imports, forbidden patching, repository hygiene, quality ledger, remediation runbooks, backlog source, contract schemas, WordPress subproject, full pytest coverage, coverage threshold, mutation gate, quality regression, and prompt fixture corpus regression.
- Full pytest coverage gate: `2660 passed, 17 deselected`; coverage XML generated at `coverage.xml`.
- Coverage gate: global `82.77%`, orchestrators `84.74%`, generators `86.64%`, services `82.15%`.
- Prompt fixture corpus regression was initially blocked on runtime-only measurements. The blocker was fixed in `src/services/prompt_service.py` by caching compiled Jinja templates by prompt path, prompt hash, and prompt text, preserving rendered prompt output while avoiding repeated template recompilation during dry-run validation. Re-run command: `python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3`; result passed with unchanged total tokens (`44184`), expected OCR calls (`1`), expected browser attempts (`2`), and estimated cost (`0.059246`).
- Live provider gate: `.env` was loaded into the canary process without printing secrets. `RUN_OPENAI_SMOKE_TEST=1 python -m pytest -m integration tests/integration/test_openai_smoke.py -q -rs` passed with `1 passed`. A prompt-service live canary rendered the same Jinja prompt twice through `prompt_service.render_prompt()`, verified byte-identical output, then completed a real `openai_service.openai_chat_json()` call with `gpt-4.1-mini`; the temp cost ledger was written under `C:\Users\8FEE~1\AppData\Local\Temp\marketlense_prompt_live_fot4ceah`.

## Movement Audit

The AST movement audit compared moved definitions/constants against `HEAD:src/orchestrators/report_analysis_orchestrator.py`.

- Moved symbols audited: 29
- AST-identical moved symbols: 29
- Changed moved symbols: 0
- Facade-owned definitions after split: `run_report_analysis`
