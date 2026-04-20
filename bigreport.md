# Bug Search Report

## Findings

1. High: `pack_name` is used as a raw filename in the analysis-pack store path, so `../` escapes `report_analysis/`.
   Files:
   [src/services/report_analysis_store_service.py](/C:/Programing/Market%20lense/src/services/report_analysis_store_service.py:71)
   [src/services/report_analysis_store_service.py](/C:/Programing/Market%20lense/src/services/report_analysis_store_service.py:149)
   Repro:
   `pack_name="../escaped"` wrote to `<tmp>/report-slug/escaped.json`, outside the intended pack directory.

2. High: prompt namespaces are concatenated onto `PROMPTS_ROOT` without a containment check, so `..` traversal can load prompts from outside `src/prompts/`.
   Files:
   [src/services/prompt_service.py](/C:/Programing/Market%20lense/src/services/prompt_service.py:45)
   [src/services/prompt_service.py](/C:/Programing/Market%20lense/src/services/prompt_service.py:94)
   Repro:
   A namespace like `..\..\..\..\Users\...\Temp\...` successfully loaded external `system.yaml` and `user.yaml`.

3. High: failed streamed Drive downloads leave partial files on disk.
   Files:
   [src/services/drive_service.py](/C:/Programing/Market%20lense/src/services/drive_service.py:577)
   [src/services/drive_service.py](/C:/Programing/Market%20lense/src/services/drive_service.py:591)
   [src/services/drive_service.py](/C:/Programing/Market%20lense/src/services/drive_service.py:608)
   Repro:
   Forcing a chunk failure raised `drive_download_failed` but left a 12-byte `%PDF-partial` file at the target path.

4. Medium: missing or bad service-account paths escape `drive_service` as raw exceptions instead of typed `AppError`s.
   File:
   [src/services/drive_service.py](/C:/Programing/Market%20lense/src/services/drive_service.py:173)
   Repro:
   `list_pdfs(... service_account_path='missing-service-account.json')` raised raw `FileNotFoundError`, which breaks orchestrator retry/error handling.

5. Medium: the legacy OpenAI fallback leaks timeout state between requests because it mutates `openai_legacy.timeout` globally and never clears it.
   File:
   [src/services/openai_service.py](/C:/Programing/Market%20lense/src/services/openai_service.py:535)
   Repro:
   One call with `timeout_seconds=1.5` followed by one with `None` still left the module timeout at `1.5`.

6. Medium: OpenAI Responses-path calls do not enforce the required `api_key` contract at the boundary.
   Files:
   [src/services/openai_service.py](/C:/Programing/Market%20lense/src/services/openai_service.py:987)
   [src/services/openai_service.py](/C:/Programing/Market%20lense/src/services/openai_service.py:1332)
   Repro:
   With a stubbed client, `api_key=""` completed successfully instead of failing fast, so these paths can silently depend on ambient credentials or fail later with the wrong error class.

7. High: the PDF crop pipeline is vulnerable to path traversal through raw `report_name` and `subdir` values.
   Files:
   [src/services/_pdf/crop.py](/C:/Programing/Market%20lense/src/services/_pdf/crop.py:728)
   [src/services/_pdf/crop.py](/C:/Programing/Market%20lense/src/services/_pdf/crop.py:782)
   [src/services/_pdf/crop.py](/C:/Programing/Market%20lense/src/services/_pdf/crop.py:886)
   [src/services/_pdf/crop.py](/C:/Programing/Market%20lense/src/services/_pdf/crop.py:923)
   Repro:
   Calling `crop_regions(... report_name="../escape")` wrote a PNG outside the intended output tree at `<tmp>/escape/escape-1.png`, and the returned relative path was also corrupted as `../escape/slices/../escape-1.png`.

8. Medium: launched UI runs remain stuck in `queued` state even while the worker PID is alive.
   Files:
   [src/orchestrators/ui_run_control_orchestrator.py](/C:/Programing/Market%20lense/src/orchestrators/ui_run_control_orchestrator.py:182)
   [src/orchestrators/ui_run_control_orchestrator.py](/C:/Programing/Market%20lense/src/orchestrators/ui_run_control_orchestrator.py:239)
   Repro:
   With a successful fake launch returning `pid=1234` and `poll_process(... running=True)`, both `launch_ui_run()` and the next `poll_ui_run()` still reported `status="queued"` instead of transitioning to `running`.

9. Medium: Windows process termination can report success even when `taskkill` fails.
   Files:
   [src/services/process_service.py](/C:/Programing/Market%20lense/src/services/process_service.py:187)
   [src/services/process_service.py](/C:/Programing/Market%20lense/src/services/process_service.py:207)
   Repro:
   Mocking `taskkill` to return a non-zero exit code with `Access is denied.` still produced `ProcessTerminateResponse(terminated=True)` instead of raising a typed failure.

10. Medium: the OpenAI Responses adapter only reads the first content block, so valid multi-block responses can be misclassified as empty.
    Files:
    [src/services/openai_service.py](/C:/Programing/Market%20lense/src/services/openai_service.py:292)
    [src/services/openai_service.py](/C:/Programing/Market%20lense/src/services/openai_service.py:1393)
    Repro:
    A stubbed Responses payload whose first content block was non-text (`reasoning`) and second block contained valid JSON triggered `openai_response_empty` in `openai_respond_with_vector_store()` even though usable output was present.

11. Medium: `run_registry_service` leaks raw SQLite open failures instead of raising a typed `AppError`.
    Files:
    [src/services/run_registry_service.py](/C:/Programing/Market%20lense/src/services/run_registry_service.py:59)
    [src/services/run_registry_service.py](/C:/Programing/Market%20lense/src/services/run_registry_service.py:196)
    Repro:
    Calling `get_ui_run_record(... registry_path=<directory>)` raised raw `sqlite3.OperationalError: unable to open database file` with no `code`, which bypasses the app error taxonomy.

12. Medium: `cover_style_service` crashes with a raw `AttributeError` when the YAML root is not a mapping.
    Files:
    [src/services/cover_style_service.py](/C:/Programing/Market%20lense/src/services/cover_style_service.py:63)
    [src/services/cover_style_service.py](/C:/Programing/Market%20lense/src/services/cover_style_service.py:125)
    Repro:
    A config file containing `- not-a-mapping` caused `load_cover_styles()` to raise `'list' object has no attribute 'get'` instead of a typed validation error.

13. Medium: `prompt_service` crashes with a raw `AttributeError` when a prompt YAML file has a non-mapping root.
    Files:
    [src/services/prompt_service.py](/C:/Programing/Market%20lense/src/services/prompt_service.py:45)
    [src/services/prompt_service.py](/C:/Programing/Market%20lense/src/services/prompt_service.py:224)
    Repro:
    A `system.yaml` file containing `- not-a-mapping` caused `load_prompt_set()` to raise `'list' object has no attribute 'get'` instead of `prompt_yaml_invalid` or another typed `AppError`.

14. Medium: `category_mapping_service` crashes with a raw `AttributeError` when the category YAML root is not a mapping.
    Files:
    [src/services/category_mapping_service.py](/C:/Programing/Market%20lense/src/services/category_mapping_service.py:199)
    [src/services/category_mapping_service.py](/C:/Programing/Market%20lense/src/services/category_mapping_service.py:667)
    Repro:
    A category mapping file containing `- not-a-mapping` caused `load_mappings()` to raise `'list' object has no attribute 'get'` instead of a typed config error.

15. Medium: `config_service.load_settings()` crashes with a raw `AttributeError` when the app config YAML root is not a mapping.
    Files:
    [src/services/config_service.py](/C:/Programing/Market%20lense/src/services/config_service.py:198)
    [src/services/config_service.py](/C:/Programing/Market%20lense/src/services/config_service.py:424)
    [src/services/config_service.py](/C:/Programing/Market%20lense/src/services/config_service.py:1329)
    Repro:
    An `app.yaml` file containing `- not-a-mapping` caused `load_settings()` to raise `'list' object has no attribute 'get'` before the service translated the problem into a typed `AppError`.

16. Medium: `report_store_service` leaks raw SQLite open failures through metadata reads.
    Files:
    [src/services/report_store_service.py](/C:/Programing/Market%20lense/src/services/report_store_service.py:1034)
    [src/services/report_store_service.py](/C:/Programing/Market%20lense/src/services/report_store_service.py:1439)
    Repro:
    Calling `get_metadata(... db_path=<directory>)` raised raw `sqlite3.OperationalError: unable to open database file` instead of a typed metadata DB error.

17. Medium: `state_service` leaks raw SQLite open failures through normal state reads.
    Files:
    [src/services/_state_common.py](/C:/Programing/Market%20lense/src/services/_state_common.py:69)
    [src/services/_state_processed.py](/C:/Programing/Market%20lense/src/services/_state_processed.py:33)
    Repro:
    Calling `get_ingest_cursor(... state_db=<directory>)` raised raw `sqlite3.OperationalError: unable to open database file` instead of a typed state DB error.

18. High: `candidate_extraction_generator` writes `candidates.json` using raw `report_name`/`subdir` path segments, so `../` escapes the requested output root.
    Files:
    [src/generators/candidate_extraction_generator.py](/C:/Programing/Market%20lense/src/generators/candidate_extraction_generator.py:40)
    [src/generators/candidate_extraction_generator.py](/C:/Programing/Market%20lense/src/generators/candidate_extraction_generator.py:45)
    [src/generators/candidate_extraction_generator.py](/C:/Programing/Market%20lense/src/generators/candidate_extraction_generator.py:152)
    Repro:
    With PDF collection stubbed and `report_name="../escape"`, `generate_candidate_pack()` wrote `candidates.json` to `<tmp>/escape/candidates/candidates.json`, outside the intended `<tmp>/out/` tree.

19. High: other PDF asset entrypoints still use raw `report_name` in write paths, so `../` escapes the output tree outside the already-found crop pipeline bug.
    Files:
    [src/services/_pdf/figures.py](/C:/Programing/Market%20lense/src/services/_pdf/figures.py:7554)
    [src/services/_pdf/figures.py](/C:/Programing/Market%20lense/src/services/_pdf/figures.py:7676)
    [src/services/_pdf/figures.py](/C:/Programing/Market%20lense/src/services/_pdf/figures.py:7685)
    [src/services/_pdf/figures.py](/C:/Programing/Market%20lense/src/services/_pdf/figures.py:7747)
    [src/services/_pdf/crop.py](/C:/Programing/Market%20lense/src/services/_pdf/crop.py:1117)
    [src/services/_pdf/crop.py](/C:/Programing/Market%20lense/src/services/_pdf/crop.py:1164)
    [src/services/_pdf/crop.py](/C:/Programing/Market%20lense/src/services/_pdf/crop.py:1176)
    [src/services/_pdf/crop.py](/C:/Programing/Market%20lense/src/services/_pdf/crop.py:1181)
    Repro:
    `extract_best_figure(... report_name="../escape")` wrote `<tmp>/escape/escape.png`, and `render_preview(... report_name="../escape", variant="x")` wrote `<tmp>/escape/escape-x.png`, both outside the intended output directory.

20. Medium: `render_service.render_report()` does not create `out_dir` and leaks a raw `FileNotFoundError` on first write.
    Files:
    [src/services/render_service.py](/C:/Programing/Market%20lense/src/services/render_service.py:30)
    [src/services/render_service.py](/C:/Programing/Market%20lense/src/services/render_service.py:54)
    [src/services/render_service.py](/C:/Programing/Market%20lense/src/services/render_service.py:55)
    Repro:
    Calling `render_report(... out_dir='<tmp>/missing/nested')` raised raw `FileNotFoundError` for `doc.html` instead of creating the directory or raising a typed `AppError`.

21. Medium: `cost_ledger_service.generate_cost_report()` raises raw `ValueError` for ordinary request validation failures instead of typed `AppError`s.
    Files:
    [src/services/cost_ledger_service.py](/C:/Programing/Market%20lense/src/services/cost_ledger_service.py:453)
    [src/services/cost_ledger_service.py](/C:/Programing/Market%20lense/src/services/cost_ledger_service.py:457)
    [src/services/cost_ledger_service.py](/C:/Programing/Market%20lense/src/services/cost_ledger_service.py:459)
    [src/services/cost_ledger_service.py](/C:/Programing/Market%20lense/src/services/cost_ledger_service.py:482)
    Repro:
    Requests with both `date_utc` and `run_id`, `top_n=0`, or `date_utc='bad-date'` all raised raw `ValueError` with no `code`.

22. High: `lock_service.acquire_lock()` lets a new requester steal a live lock by choosing a tiny `ttl_seconds`.
    Files:
    [src/services/lock_service.py](/C:/Programing/Market%20lense/src/services/lock_service.py:69)
    [src/services/lock_service.py](/C:/Programing/Market%20lense/src/services/lock_service.py:84)
    [src/services/lock_service.py](/C:/Programing/Market%20lense/src/services/lock_service.py:88)
    Repro:
    After acquiring a lock as `owner-a`, a second caller 20ms later using `ttl_seconds=0.001` got `acquired=True` as `owner-b` and replaced the still-live lock owner.

23. Medium: `cover_image_orchestrator` crashes with raw `AttributeError` when `file_id` is requested but no report metadata row exists.
    Files:
    [src/orchestrators/cover_image_orchestrator.py](/C:/Programing/Market%20lense/src/orchestrators/cover_image_orchestrator.py:50)
    [src/orchestrators/cover_image_orchestrator.py](/C:/Programing/Market%20lense/src/orchestrators/cover_image_orchestrator.py:73)
    [src/orchestrators/cover_image_orchestrator.py](/C:/Programing/Market%20lense/src/orchestrators/cover_image_orchestrator.py:77)
    Repro:
    Calling `run_cover_image_generation(... file_id='missing-file')` against a new empty `reports.sqlite` raised `'NoneType' object has no attribute 'file_id'` instead of a typed not-found failure.

## Notes

- Scope: first-party code under `src/` plus a quick WordPress syntax sweep. Vendored `tools/browser-use` was not treated as project-owned audit scope.
- Verification: targeted tests for OpenAI, Drive, prompt, and report-analysis-store paths passed. The full `python -m pytest -q` run timed out after about 15 minutes, so this is a targeted audit rather than a full-suite certification.
- WordPress: `php -l` passed on the plugin PHP files; no immediate syntax blocker was found there.
