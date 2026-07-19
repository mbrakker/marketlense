# Long-File Audit and Refactor Targets

> **Documentation type:** Historical audit record
> **Canonical topic:** Long-file audit history
> **Update trigger:** Replace this snapshot only after a new documented audit review.

Generated: 2026-06-13. The counts below are historical; run the documented scan command for current inventory.

## Purpose

This note tracks remaining first-party long-file concentration after the facade and implementation-family refactors already landed in the repository. It is an audit input, not an instruction to split files merely because they are large.

Canonical scan command:

```powershell
python scripts/count_long_files.py --min-lines 500
```

The command uses `scripts/repository_analysis_exclusions.py` to exclude generated, vendored, cache, and local reproduction trees. The complete current `>500` inventory is reproducible from the command; the tables below highlight the files requiring first review because they exceed 1,000 physical lines.

## Current Scan Summary

| Section | Files >500 lines | Files >=1,000 lines |
| --- | ---: | ---: |
| First-party `src` | 115 | 2 |
| First-party `tests` | 81 | 1 |
| First-party `scripts` | 1 | 0 |
| WordPress integration | 6 | 3 |

- Total first-party source-like files scanned: `1067`.
- Skipped paths/files: `21` (`13` top-level runtime/temp directories, `7` outside first-party analysis roots, `1` vendored dependency tree).
- The previous February inventory is obsolete: the large public `pdf_service`, `config_service`, canonical `llm_service`, `artifact_generator`, `report_store_service`, and Streamlit page boundaries have already been decomposed or converted into facades.
- Long first-party test files have generally been decomposed behind their original pytest entrypoint facades. `tests/test_long_test_file_ownership.py` enforces the 1,000-line first-party test-file threshold, but the current canonical scan reports `tests/test_publish_generator.py` at `1,003` lines.
- Since the previous scan, browser artifact finalization has been decomposed internally: `src/services/_browser_report_download/artifact.py` is `703` lines, while classification is a compatibility surface over `_artifact/_classification/*`; its largest reported owner is `_artifact/_classification/evidence.py` at `792` lines.
- Browser runtime execution has now been decomposed internally: `src/services/_browser_report_download/browser.py` is `671` lines, terminal asset capture is split behind `_browser_runtime/terminal_assets.py` into `_terminal_assets/{artifacts,capture,network,page_state}.py`, and session lifecycle is split behind `_browser_runtime/session_lifecycle.py` into `_session_lifecycle/{history,partial_history,cleanup,shutdown}.py`.
- Report-download orchestration has now been decomposed internally: `src/orchestrators/_report_download_orchestrator/workflow.py` is `536` physical lines and focused idempotent persistence lives in `persistence.py` (`646`); route planning is split behind `route_planner.py` into `_route_planner/{planning,policy,recovery,url_rules}.py`.
- Browser-report HTTP acquisition has now been decomposed internally: `src/services/_browser_report_download/http.py` is a `47`-line compatibility surface; focused remaining `>500` owners are `_http/gate_probe.py` (`607`), `_http/onsite_capture.py` (`573`), and `_http/pdf_transfer.py` (`522`).
- Browser-report helper inspection has now been decomposed internally: `src/services/_browser_report_download/helpers.py` is a compatibility facade, with page state/real-tab diagnostics in `_helpers/state.py` (`304`), JavaScript and bounded HTTP inspection in `_helpers/inspection.py` (`430`), and screenshot/coordinate/autocomplete interaction in `_helpers/interaction.py` (`546`).
- PDF table interpretation has now been decomposed internally: `src/services/_pdf/table_heuristics.py` is a compatibility surface; `_table_heuristics/regions.py` and `_table_heuristics/screening.py` are now compatibility surfaces over `_regions/{ranked,context,compose}.py` and `_screening/{metrics,rejections,deduplication}.py`. The largest remaining table-family owner is `_table_heuristics/layout.py` (`775`), with rejection policy in `_screening/rejections.py` (`744`).
- PDF panel interpretation has now been decomposed internally: `src/services/_pdf/_visual_heuristics/panel_detection.py` is a compatibility surface over `_panel_detection/{shadowing,candidates}.py`, with focused text interpretation in `panel_text.py` (`957`) and geometry construction in `panel_geometry.py` (`988`); `src/services/_pdf/visual_heuristics.py` is a `773`-line compatibility facade.
- PDF visual-candidate extraction has now been decomposed internally: `src/services/_pdf/visual_candidates.py` is a compatibility surface; focused owners include `_visual_candidates/extraction.py` over `_extraction/{context,sequential,workflow}.py`, `_visual_candidates/screening.py` (`684`), and `_visual_candidates/raster.py` (`579`).
- PDF figure extraction has now been decomposed internally: `src/services/_pdf/figures.py` is a `700`-line compatibility surface; focused owners are `_figures/triage.py` (`346`), `_figures/pruning.py` (`372`), `_figures/candidates.py` (`458`), and `_figures/best_figure.py` (`216`).
- PDF crop rendering has now been decomposed internally: `src/services/_pdf/crop.py` is a compatibility facade, with crop geometry in `_crop/geometry.py` (`582`), image operations, table-continuation stitching, crop-region artifact writing, crop-refine rendering, and preview rendering in focused `_crop/` owner modules.
- Publisher-inventory workflow coordination has now been decomposed internally: `src/services/_publisher_inventory_service/workflow.py` is a `563`-line coordinator and compatibility surface, with deterministic browser traversal behind the `browser_flow.py` compatibility surface and preflight scenario classification in `preflight.py`.
- Publisher-inventory browser traversal has now been decomposed internally: `browser_flow.py` is a compatibility surface over `_browser_flow/{interactions,collection,supplement,traversal}.py`, preserving the workflow entrypoint and browser/HTTP behavior.
- Publisher-inventory HTTP acquisition has now been decomposed internally: `fetch_service.py` is a compatibility surface over `_fetch/{parsing,discovery,classification,inspection}.py`.
- Publisher-inventory candidate quality has now been decomposed internally: `publisher_inventory_candidate_quality_generator.py` is a compatibility facade over `_publisher_inventory_candidate_quality/{classification,evaluation,workflow}.py`.
- Browser-report CDP access has now been decomposed internally: `_browser_report_download/cdp.py` is a compatibility surface over `_cdp/{models,transport,session,dialogs,operations}.py`.
- SQLite migrations have now been decomposed by schema ownership: `sqlite_migration_service.py` retains the canonical public entrypoints over `_sqlite_migration/{runner,reports,state,ui_runs}.py`.
- Reports-database migrations have now been decomposed internally: `_sqlite_migration/reports.py` is a `117`-line ordered compatibility registry over `_reports/{schema,core,routing,projections}.py`.
- Analytics persistence has now been decomposed internally: `analytics_store_service.py` is the canonical facade over `_analytics_store/{common,projection_write,cross_report_read,signals}.py`.
- Publication orchestration uses `_publish_orchestrator/{models,routing,preflight,idempotency,cross_report}.py`, but `publish_orchestrator.py` has grown to `1,066` lines and is again a threshold hotspot requiring responsibility review.
- Publisher-inventory orchestration has now been decomposed internally: `src/orchestrators/publisher_inventory_orchestrator.py` is an `811`-line public coordinator and compatibility surface, while dependency wiring, idempotency, snapshot I/O, candidate-flow helpers, and runtime budget/retry helpers live in `src/orchestrators/_publisher_inventory_orchestrator/`.
- Publisher-inventory candidate screening has now been decomposed internally: `src/generators/publisher_inventory_candidate_screening_generator.py` is a compatibility facade, with shared marker normalization in `_publisher_inventory_candidate_screening/shared.py` (`560`) and focused deterministic screening, response-policy, and LLM-batch owners in the same private family.
- Cross-report analysis input preparation has now been decomposed internally: `src/generators/cross_report_analysis_input_generator.py` is a compatibility facade, with theme selection in `_cross_report_analysis_input/theme_selection.py` (`762`), evidence and signal preparation in `evidence_signals.py` (`703`), source selection in `source_selection.py`, and shared deterministic helpers in `shared.py`.
- Report-analysis orchestration has now been decomposed internally: `src/orchestrators/report_analysis_orchestrator.py` is a `622`-line public coordinator and compatibility surface, while artifact scheduling, vector-store readiness polling, payload checks, validation/regeneration execution, and regeneration-plan mapping live in `src/orchestrators/_report_analysis_orchestrator/`.
- The requested Drive/UI/PDF-heuristic/report-source runtime long-file set has now been decomposed behind existing public boundaries: `src/services/drive_service.py`, `src/ui/app_pages/publisher_operations.py`, `src/services/_pdf/visual_heuristics.py`, `src/orchestrators/ui_run_execution_orchestrator.py`, `src/services/_pdf/_visual_heuristics/chart_layout.py`, and `src/generators/report_source_generator.py` are compatibility facades over focused private owner modules.
- The requested browser-download/report-generation/publishing/rendering/PDF-candidate runtime long-file set has now been decomposed behind existing boundaries: `_browser_runtime/terminal_assets.py`, `_report_download_orchestrator/route_planner.py`, `report_generation_orchestrator.py`, `wordpress_service.py`, `render_service.py`, `_visual_candidates/extraction.py`, and `_artifact/classification.py` are compatibility facades over focused private owner modules. The AST movement audit recorded `229` moved top-level symbols, `229` unchanged moved symbols, `0` changed moved symbols, `0` facade-owned definitions, and `0` missing symbols across those seven files.
- The requested cross-report/table/browser-session/report-route runtime long-file set has now been decomposed behind existing boundaries: `cross_report_analysis.py`, `_table_heuristics/{regions,screening}.py`, `_browser_runtime/session_lifecycle.py`, and `_report_store_service/download_routes.py` are compatibility facades over focused private owner modules. The AST movement audit recorded `143` moved top-level symbols, `142` unchanged moved symbols, `1` changed moved symbol, `0` facade-owned definitions, and `0` missing symbols; the changed symbol is the cross-report contract validator accepting the new private contract module namespace.
- The requested analytics-projection/crop-refine/PDF-panel/publisher-discovery runtime long-file set has now been decomposed behind existing boundaries: `analytics_projection_generator.py`, `_report_selection_generator/crop_refine.py`, `_visual_heuristics/panel_detection.py`, and `_publisher_inventory_service/discovery_activity.py` are compatibility facades over focused private owner modules. The AST movement audit recorded `102` moved top-level symbols, `102` unchanged moved symbols, `0` changed moved symbols, `0` facade-owned definitions, and `0` missing symbols.
- `src/cli.py` has now been decomposed behind the existing canonical CLI boundary: `src.cli` remains the `python -m src.cli` facade and private command-family owners live under `src/_cli/`. The AST movement audit recorded `40` moved top-level symbols, `18` unchanged moved symbols, `22` changed moved symbols, `0` facade-owned definitions, and `0` missing symbols; changed symbols gained runtime patch-point synchronization for existing `src.cli` compatibility or a lazy default-callback lookup to avoid an import cycle.
- Workflow-queue persistence and handler ownership have now been decomposed behind their existing public facades. `workflow_queue_service.py` delegates to `_workflow_queue_service/{schema,controls,submission,leasing,completion,outbox,health,approvals,opportunities}.py`; `workflow_queue_orchestrator.py` delegates to `_workflow_queue_handlers/{acquisition,report_pipeline,analytics,signals,briefings,publishing,registry}.py`. The AST movement audit recorded `72` moved top-level symbols, `70` unchanged moved symbols, `2` changed moved symbols from the already-authorized acquisition handoff, and no facade-owned definitions.

## Largest Runtime Files

### `src` Files >=1,000 Lines

| Lines | File | Review reason |
| ---: | --- | --- |
| 1,066 | `src/orchestrators/publish_orchestrator.py` | Three public publishing workflows remain in one coordinator despite the existing private capability family. |
| 1,065 | `src/orchestrators/ingest_orchestrator.py` | Batch filtering, locking, cursor management, worker coordination, retry routing, and run finalization require semantic ownership review. |

### Large Test Concentration >=1,000 Lines

`tests/test_publish_generator.py` is `1,003` lines. It contains a local WordPress HTTP boundary fixture plus publish-generator behavior cases and should be split by observable behavior behind the existing test entrypoint pattern. Current enforcement lives in `tests/test_long_test_file_ownership.py`; other original long test entrypoints remain thin facades over adjacent private case packages such as `tests/_test_report_download_orchestrator/`, `tests/test_browser_report_download_service/_test_prompt_and_probe/`, and `tests/test_pdf_figures_service/_builders/`.

## Completed Boundary Work

Do not recreate the obsolete February split plan. These public boundaries already use the approved facade-plus-internal-family pattern:

- `src/services/pdf_service.py` over `src/services/_pdf/*`.
- `src/services/config_service.py` over `src/services/_config_service/*`.
- `src/services/llm_service.py` over `src/services/_llm_service/*`.
- `src/services/report_store_service.py` over `src/services/_report_store_service/*`.
- `src/services/state_service.py` over `src/services/_state_service/*`.
- `src/services/publisher_inventory_service.py` over `src/services/_publisher_inventory_service/*`.
- `src/services/browser_report_download_service.py` over `src/services/_browser_report_download/*`, including the internal `src/services/_browser_report_download/_artifact/*`, `src/services/_browser_report_download/_browser_runtime/*`, `src/services/_browser_report_download/_helpers/*`, and `src/services/_browser_report_download/_http/*` capability families.
- `src/orchestrators/publisher_inventory_orchestrator.py` over `src/orchestrators/_publisher_inventory_orchestrator/*`.
- `src/generators/artifact_generator.py` over `src/generators/_artifact_generator/*`.
- `src/generators/cross_report_analysis_input_generator.py` over `src/generators/_cross_report_analysis_input/*`.
- `src/generators/report_generation_dependencies.py` over `src/generators/_report_generation_dependencies/*`.
- `src/orchestrators/report_download_orchestrator.py` over `src/orchestrators/_report_download_orchestrator/*`, including focused dependency, readiness, forensics, promotion, persistence, and Drive-archive capabilities behind the smaller `workflow.py` coordinator.
- `src/services/drive_service.py` over `src/services/_drive_service/*`, preserving one canonical Google Drive service boundary.
- `src/ui/app_pages/publisher_operations.py` over `src/ui/app_pages/_publisher_operations/*`.
- `src/orchestrators/ui_run_execution_orchestrator.py` over `src/orchestrators/_ui_run_execution_orchestrator/*`.
- `src/generators/report_source_generator.py` over `src/generators/_report_source_generator/*`.
- `src/services/_pdf/visual_heuristics.py` over shared and focused `_visual_heuristics/*` owners, including `chart_layout.py` over `_visual_heuristics/_chart_layout/*`.
- `src/services/_browser_report_download/_browser_runtime/terminal_assets.py` over `_browser_runtime/_terminal_assets/*`.
- `src/orchestrators/_report_download_orchestrator/route_planner.py` over `_report_download_orchestrator/_route_planner/*`.
- `src/orchestrators/report_generation_orchestrator.py` over `src/orchestrators/_report_generation_orchestrator/*`.
- `src/services/wordpress_service.py` over `src/services/_wordpress_service/*`, preserving one canonical WordPress service boundary.
- `src/services/render_service.py` over `src/services/_render_service/*`, preserving one canonical rendering service boundary.
- `src/services/_pdf/_visual_candidates/extraction.py` over `_visual_candidates/_extraction/*`.
- `src/services/_browser_report_download/_artifact/classification.py` over `_artifact/_classification/*`.
- `src/generators/analytics_projection_generator.py` over `src/generators/_analytics_projection/*`.
- `src/generators/_report_selection_generator/crop_refine.py` over `src/generators/_report_selection_generator/_crop_refine/*`.
- `src/services/_pdf/_visual_heuristics/panel_detection.py` over `_visual_heuristics/_panel_detection/*`.
- `src/services/_publisher_inventory_service/discovery_activity.py` over `_publisher_inventory_service/_discovery_activity/*`.
- `src/cli.py` over `src/_cli/*`, preserving one canonical CLI boundary for command registration and imports.
- `src/ui/streamlit_pages.py` over `src/ui/app_pages/*` and `src/ui/_streamlit_pages/*`.
- Long first-party behavior tests over adjacent private test packages while preserving original pytest entrypoints, documented in `docs/architecture/test-long-file-decomposition-review.md`.

Any additional work must reduce responsibility or algorithmic complexity inside those existing capability families. Adding peer public entrypoints would be architecture regression.

## Remaining Priority Targets

### 1. Orchestrator Threshold Regressions

Primary evidence:

- `src/orchestrators/publish_orchestrator.py`: `1,066` lines.
- `src/orchestrators/ingest_orchestrator.py`: `1,065` lines.

Direction:

- Preserve `publish_orchestrator.py` and `ingest_orchestrator.py` as canonical public workflow boundaries.
- Review whether each stable responsibility already has a semantic owner in the existing private orchestrator families before adding modules.
- For publishing, keep the three public workflows and compatibility patch points stable while moving only substantial owned behavior into `_publish_orchestrator/*`.
- For ingest, separate only stable control-plane capabilities such as batch readiness/filtering, lock and preflight lifecycle, worker coordination, cursor persistence, and finalization when the split reduces coupling.
- Do not move domain generation into orchestrators or external I/O into new orchestrator helpers.

Verification required:

- Add the ownership/decomposition red test before movement.
- Preserve public imports, retry counts, idempotency, ordering, state transitions, logs, and external side effects.
- Run focused publish and ingest pipeline tests plus the AST movement audit required by `AGENTS.md`.

### 2. Browser Report Download Internals

Primary evidence:

- `src/orchestrators/_report_download_orchestrator/_route_planner/planning.py`: `691` lines.
- `src/services/_browser_report_download/_cdp/operations.py`: `620` lines; focused CDP operation owner behind the `cdp.py` compatibility surface.
- `src/services/_browser_report_download/_browser_runtime/_terminal_assets/*`: focused terminal-artifact, capture, network, and page-state owners behind the `terminal_assets.py` compatibility surface.
- `src/services/_browser_report_download/_artifact/_classification/evidence.py`: `792` lines.
- `src/services/_browser_report_download/_browser_runtime/session_lifecycle.py`: `44`-line compatibility surface over `_session_lifecycle/{history,partial_history,cleanup,shutdown}.py`; no child currently exceeds `500` lines.

Direction:

- Keep `src/services/browser_report_download_service.py` as the sole public browser-download service boundary.
- Retain the new `_artifact/*` internal capability family; `artifact.py` is now a smaller coordination module rather than the top hotspot.
- Retain the new `_browser_runtime/*` internal capability family; `browser.py` is now a smaller runtime coordinator rather than the top hotspot.
- Retain the new `_http/*` internal capability family; `http.py` is now a stable compatibility surface for focused HTTP acquisition implementations.
- Retain the new `_report_download_orchestrator/*` capability split; `workflow.py` is now a smaller sequencing coordinator and route-planning internals live behind the `route_planner.py` compatibility surface.
- Continue extracting only coherent internal capabilities where responsibility or measured complexity remains high, such as deterministic HTTP acquisition/classification and route-history persistence.
- Keep route ordering, retry/backoff, idempotency, and state transitions in the orchestrator family.
- Keep prompt selection/rendering in the prompt service boundary; do not place prompt text in extracted modules.

Verification required:

- Existing browser-download, route-planner, and report-download orchestrator behavior tests.
- Failure paths asserting typed `AppError` fields, attempt count, terminal result classification, idempotency, and required structured log fields.
- No tests that preserve behavior by patching private/internal logic.

### 3. PDF Extraction Hot Paths

Primary evidence:

- `src/services/_pdf/_table_heuristics/layout.py`: `775` lines; focused page-layout and text interpretation owner.
- `src/services/_pdf/table_heuristics.py`: `407` lines; stable compatibility surface.
- `src/services/_pdf/_table_heuristics/_screening/rejections.py`: `744` lines; focused rejection-policy owner behind the screening compatibility surface.
- `src/services/_pdf/_visual_heuristics/_panel_detection/candidates.py`: `722` lines; detector candidate assembly owner behind the panel-detection compatibility surface.
- `src/services/_pdf/_visual_heuristics/panel_geometry.py`: `988` lines; deterministic panel geometry construction and adjustment.
- `src/services/_pdf/_visual_heuristics/panel_text.py`: `957` lines; deterministic title, caption, metric, and component-text interpretation.
- `src/services/_pdf/visual_candidates.py`: stable compatibility surface.
- `src/services/_pdf/_visual_candidates/_extraction/sequential.py`: `975` lines; candidate construction, ordering, overlap handling, and worker coordination.
- `src/services/_pdf/_visual_candidates/screening.py`: `684` lines; deterministic textual and false-positive screening.
- `src/services/_pdf/_visual_candidates/raster.py`: `579` lines; raster qualification and probe caching.
- `src/services/_pdf/crop.py`: compatibility facade for focused `_crop/*` owners; `_crop/geometry.py` is now the largest crop-family owner at `582` lines.

Direction:

- Retain `src/services/pdf_service.py` as the canonical PDF boundary.
- Prioritize measured algorithm changes already recorded in `CONSOLIDATED_TODO.md`: indexed table deduplication and precomputed per-page visual candidate relationships.
- Retain the `_table_heuristics/*` capability split; `regions.py` and `screening.py` are compatibility surfaces, and further extraction requires a semantic boundary rather than line-count slicing.
- Retain the `_visual_heuristics/{panel_text,panel_geometry,panel_detection}.py` semantic split behind `visual_heuristics.py`; `panel_detection.py` is now a compatibility surface over `_panel_detection/*`, and optimization of precomputed visual relationships remains separate from the decomposition evidence.
- Retain the `_visual_candidates/{raster,screening,extraction}.py` semantic split behind `visual_candidates.py`; `extraction.py` is now a compatibility surface over `_extraction/{context,sequential,workflow}.py`, and the deferred relationship-scan optimization is still a separate change.
- Retain the `_crop/*` semantic split behind `crop.py`; future crop-family work should target measured geometry or artifact-cache behavior, not additional facade layers.

Verification required:

- Correctness fixtures for near-duplicate/distinct tables, dense panels, multi-chart layouts, decorative images, wrappers, and crop boundaries.
- Before/after runtime benchmark evidence on large or visually dense fixtures.
- Candidate output and validation behavior must remain semantically equivalent unless a separately documented quality change is intended.

### 4. Publisher Discovery and Report-Download Workflows

Primary evidence:

- `src/services/_publisher_inventory_service/_browser_flow/collection.py`: focused rendered-page collection owner behind the `browser_flow.py` compatibility surface.
- `src/services/_publisher_inventory_service/workflow.py`: `563` lines; stable coordinator and compatibility surface.
- `src/services/_publisher_inventory_service/preflight.py`: focused preflight classification owner.
- `src/orchestrators/publisher_inventory_orchestrator.py`: `811` lines; public coordinator and compatibility surface.
- `src/generators/publisher_inventory_candidate_screening_generator.py`: compatibility facade for `_publisher_inventory_candidate_screening/*`; shared marker normalization is the largest owner at `560` lines.
- `src/generators/_publisher_inventory_candidate_quality/classification.py`: `921` lines; focused deterministic quality-classification owner behind the generator facade.

Direction:

- Preserve one publisher-inventory service boundary and one orchestration path.
- Retain the `_publisher_inventory_service/{preflight,browser_flow,workflow}.py` semantic split and the private `_browser_flow/*` and `_fetch/*` capability owners; `workflow.py` remains the service coordinator, route selector, runtime loader, and compatibility surface.
- Separate only stable behavior families such as acquisition adaptation, candidate qualification, snapshot/state recording, and recovery/route-memory decisions; retain the candidate-screening semantic split behind the generator facade.
- Keep service modules free of workflow retry choices and keep generators free of direct I/O.

Verification required:

- Existing publisher inventory service/orchestrator and candidate screening/quality tests.
- Pipeline tests for remembered-route reuse, snapshot preservation, retry decisions, and no duplicate side effects.
- Structured logging assertions for each public service and orchestrator boundary affected.

### 5. Track, Do Not Mechanically Split

These files need responsibility review or performance evidence before any decomposition proposal:

- Cross-report analysis synthesis, publishing, orchestrator, and contract files are active feature surfaces. The input generator now uses a private semantic split; any further work must preserve output contracts, publication flow, and regression coverage rather than splitting by line count.
- Contract modules may be large without role-mixing. Split `src/contracts/cross_report_analysis.py` only along independently versioned semantic contracts, never for cosmetics.
- External boundary modules such as Drive and WordPress services must retain one canonical namespace; Drive now uses internal capability modules behind `src/services/drive_service.py`.

## Refactor Rules

All future long-file remediation must satisfy these controls:

1. Preserve the modular monolith and one canonical public boundary per external system or workflow.
2. Extract semantic capability families, not pass-through wrappers or arbitrary smaller files.
3. Keep I/O in services, domain assembly/validation in generators, and sequencing/retries/idempotency in orchestrators.
4. Use fully populated, versioned dataclass contracts and typed `AppError` failures.
5. Preserve prompt namespaces and prompt-service ownership of prompt rendering.
6. Add positive and negative behavior tests at public boundaries; do not patch private helpers or primary logic paths.
7. Measure performance-targeted changes before and after implementation.
8. Update the canonical documentation for any landed architecture or behavior change.

## Next Review Trigger

Refresh this audit after either current `src` threshold hotspot is remediated or justified, after `tests/test_publish_generator.py` returns below the enforced threshold, or whenever a remaining priority family is materially changed. A new top-level package, external service boundary, three-or-more peer-module split, or second path for the same external interaction requires the architecture review specified in `AGENTS.md`.
