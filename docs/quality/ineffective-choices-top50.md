# Repository Analysis: Top 50 Ineffective Choices (Low Effort, High Impact)

Status: merged into `CONSOLIDATED_TODO.md` on 2026-03-08. Treat the consolidated todo as the actionable backlog; keep this file as the detailed source analysis behind those tasks.

Method: static repository scan focused on maintainability, reliability, and architecture drift. Prioritized by expected impact/effort ratio.

## A) Monolithic modules (split-first wins)

1. `src/services/pdf_service.py` is 3698 lines (monolith risk; hard to test and reason about). **Low effort win:** split by capability (extract text, extract figures, crop, contents).  
2. `src/generators/report_generator.py` is 3468 lines and centralizes too many report responsibilities. **Low effort win:** extract candidate ranking/refinement/finalization sub-generators.  
3. `src/ui/streamlit_pages.py` is 2967 lines, creating high UI change risk. **Low effort win:** split by page/section modules.  
4. `src/generators/validation_generator.py` is 2500 lines; validations are bundled in one place. **Low effort win:** split checks into composable validators.  
5. `src/generators/evidence_pack_generator.py` is 1778 lines. **Low effort win:** split pack-specific logic into per-pack modules.  
6. `src/generators/artifact_generator.py` is 1598 lines. **Low effort win:** separate schema loading, model call handling, and post-processing.  
7. `src/services/openai_service.py` is 1474 lines and combines many OpenAI interaction patterns. **Low effort win:** split request-types into submodules while keeping one service facade.  
8. `src/services/config_service.py` is 968 lines with large inline normalization logic. **Low effort win:** move section-normalizers into private helpers.  
9. `src/orchestrators/ingest_orchestrator.py` is 755 lines. **Low effort win:** extract retry/state transition helpers.  
10. `src/services/state_service.py` is 693 lines. **Low effort win:** separate read/write/query concerns into smaller units.

## B) Oversized functions (highest refactor ROI)

11. `generate_report` spans ~1637 lines in `src/generators/report_generator.py` (starts around line 1832). **Low effort win:** split by phase with typed intermediate contracts.  
12. `_render_structured_config_form` spans ~641 lines in `src/ui/streamlit_pages.py` (starts around line 1901). **Low effort win:** section-level render helpers.  
13. `_select_refined_candidate_items` spans ~630 lines in `src/generators/report_generator.py`. **Low effort win:** isolate ranking, filtering, and crop-refine decision trees.  
14. `load_settings` spans ~500 lines in `src/services/config_service.py` (starts at line 341). **Low effort win:** table-driven field mapping with validators.  
15. `generate_artifacts` spans ~451 lines in `src/generators/artifact_generator.py`. **Low effort win:** split per artifact type.  
16. `run_publish` spans ~378 lines in `src/orchestrators/publish_orchestrator.py`. **Low effort win:** extract state transition pipeline.  
17. `run_ingest` spans ~373 lines in `src/orchestrators/ingest_orchestrator.py`. **Low effort win:** extract per-file execution function with retry wrapper.  
18. `run_ingest_file` spans ~372 lines in `src/orchestrators/ingest_file_orchestrator.py`. **Low effort win:** factor out setup/teardown/error mapping.  
19. `_generate_pack` spans ~341 lines in `src/generators/evidence_pack_generator.py`. **Low effort win:** split prompt-call/normalize/validate steps.  
20. `validate_report` spans ~319 lines in `src/generators/validation_generator.py`. **Low effort win:** compose validators via registry.  
21. `extract_taxonomy` spans ~259 lines in `src/generators/taxonomy_generator.py`. **Low effort win:** isolate extraction, cleanup, and validation passes.  
22. `_inject_theme` spans ~232 lines in `src/ui/streamlit_pages.py`. **Low effort win:** move CSS/template assets out of function body.  
23. `_run_grounding_check` spans ~231 lines in `src/generators/validation_generator.py`. **Low effort win:** split I/O from semantic scoring.  
24. `_render_settings_and_prompts` spans ~229 lines in `src/ui/streamlit_pages.py`. **Low effort win:** separate settings and prompt tabs into dedicated modules.  
25. `analyze_report` spans ~225 lines in `src/services/openai_service.py`. **Low effort win:** split request prep, API call, and response adaptation.

## C) Broad exception usage and hidden failure modes

26. `src/services/pdf_service.py` contains very high `except Exception` usage (56 matches), which can mask root causes. **Low effort win:** replace with typed AppError mapping per boundary.  
27. `src/services/openai_service.py` has 16 broad exception catches. **Low effort win:** isolate provider/parse/cost-ledger errors with specific codes.  
28. `src/ui/streamlit_pages.py` has 14 broad catches. **Low effort win:** centralize UI error rendering and preserve error taxonomy.  
29. `src/generators/report_generator.py` has 10 broad catches. **Low effort win:** narrow catches around only recoverable branches.  
30. `src/services/file_service.py` has 8 broad catches. **Low effort win:** map file-not-found/permission/encoding separately.  
31. `src/services/lock_service.py` has 5 broad catches. **Low effort win:** split lock contention vs filesystem failure paths.  
32. `src/services/drive_service.py` has 5 broad catches. **Low effort win:** preserve upstream API error details instead of generic exceptions.  
33. `src/orchestrators/ingest_orchestrator.py` has 5 broad catches. **Low effort win:** explicitly retry only retryable AppError types.  
34. `src/services/wordpress_service.py` includes broad catches around response parsing. **Low effort win:** strict response schema validation and typed errors.  
35. `src/services/report_store_service.py` has broad catches for DB edges. **Low effort win:** map sqlite operational/integrity errors explicitly.

## D) Test integrity and brittleness hotspots

36. Tests currently use `monkeypatch.setattr` heavily (189 total), increasing risk of mocked narratives over behavior validation. **Low effort win:** replace top mocked flows with boundary fakes + integration assertions.  
37. `tests/test_vector_pipeline_wiring.py` alone has 60 monkeypatches. **Low effort win:** introduce fixture-driven in-memory boundary adapters.  
38. `tests/test_ingest_parallel.py` has 15 monkeypatches. **Low effort win:** keep one true pipeline path and patch only network/time boundaries.  
39. `tests/test_candidate_extraction_orchestrator.py` has 14 monkeypatches. **Low effort win:** move repeated patches to reusable boundary fixtures.  
40. `tests/test_publish_orchestrator.py` has 11 monkeypatches. **Low effort win:** assert state transitions and retry counts on real orchestration path.  
41. `tests/test_openai_vector_store.py` has 10 monkeypatches. **Low effort win:** test with service-level fake transport instead of patching internals.  
42. `tests/test_candidate_refine_selection.py` has 10 monkeypatches. **Low effort win:** push deterministic inputs through real selection logic.  
43. `tests/test_wordpress_service.py` has 8 monkeypatches. **Low effort win:** replace with requests mock adapter fixture at HTTP boundary.  
44. `tests/test_publish_generator.py` has 8 monkeypatches. **Low effort win:** assert generated contract completeness plus one side effect.  
45. `tests/test_vector_pipeline_wiring.py` mutates import path via `sys.path.append(...)` (line 9), which is fragile and environment-dependent. **Low effort win:** rely on project packaging/pytest config only.

## E) Cross-role coupling and maintainability quick wins

46. `src/services/openai_service.py` performs cost-ledger writes (`append_cost_entry`, `rollup_daily`) inside model-call service path, coupling OpenAI and accounting concerns. **Low effort win:** emit cost event and let orchestrator/service subscriber persist ledger.  
47. `src/cli.py` includes 33 direct `console.print(...)` calls, causing duplicated status formatting logic. **Low effort win:** centralize console rendering utilities.  
48. `src/services/config_service.py` contains many hardcoded defaults inline (e.g., rank thresholds and content keywords), making behavior drift from YAML likely. **Low effort win:** keep defaults in config schema constants and generate docs from source.  
49. `src/ui/streamlit_pages.py` and `src/generators/report_generator.py` both contain very large control-flow branches, making onboarding and defect localization expensive. **Low effort win:** extract branch strategies into named policy helpers.  
50. Repository includes committed operational log artifacts under `logs/` (`long_events_30s.csv/json`), which are usually generated outputs and add noise/churn. **Low effort win:** move to ignored artifacts or docs snapshots with retention rationale.

---

## Notes on prioritization

- **Do first (highest return):** items 11, 14, 26, 36, 46.
- **Do next:** items 1–10 (module split plan), then 37–45 (test hardening).
- **Expected outcome:** lower defect rate, faster PR review, better CI trust, and easier role-boundary enforcement.
