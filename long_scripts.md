# Long-File Audit and Refactor Targets

Generated: 2026-06-11

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
| First-party `src` | 118 | 17 |
| First-party `tests` | 80 | 0 |
| First-party `scripts` | 1 | 0 |
| WordPress integration | 5 | 3 |

- Total first-party source-like files scanned: `966`.
- Skipped paths/files: `21` (`13` top-level runtime/temp directories, `7` outside first-party analysis roots, `1` vendored dependency tree).
- The previous February inventory is obsolete: the large public `pdf_service`, `config_service`, `openai_service`, `artifact_generator`, `report_store_service`, and Streamlit page boundaries have already been decomposed or converted into facades.
- Long first-party test files have now been decomposed behind their original pytest entrypoint facades. `tests/test_long_test_file_ownership.py` enforces the 1,000-line first-party test-file threshold; the current canonical scan reports no first-party test files above 1,000 lines.
- Since the previous scan, browser artifact finalization has been decomposed internally: `src/services/_browser_report_download/artifact.py` is now `703` lines, while the extracted `src/services/_browser_report_download/_artifact/classification.py` is `1,153` lines.
- Browser runtime execution has now been decomposed internally: `src/services/_browser_report_download/browser.py` is `671` lines, with remaining focused hotspots in `_browser_runtime/terminal_assets.py` (`1,319`) and `_browser_runtime/session_lifecycle.py` (`1,102`).
- Report-download orchestration has now been decomposed internally: `src/orchestrators/_report_download_orchestrator/workflow.py` is `528` physical lines and focused idempotent persistence lives in `persistence.py` (`646`); `route_planner.py` (`1,301`) remains the family's only `>=1,000`-line hotspot.
- Browser-report HTTP acquisition has now been decomposed internally: `src/services/_browser_report_download/http.py` is a `47`-line compatibility surface; focused remaining `>500` owners are `_http/gate_probe.py` (`607`), `_http/onsite_capture.py` (`573`), and `_http/pdf_transfer.py` (`522`).
- Browser-report helper inspection has now been decomposed internally: `src/services/_browser_report_download/helpers.py` is a compatibility facade, with page state/real-tab diagnostics in `_helpers/state.py` (`555`), JavaScript and bounded HTTP inspection in `_helpers/inspection.py` (`550`), and screenshot/coordinate/autocomplete interaction in `_helpers/interaction.py` (`895`).
- PDF table interpretation has now been decomposed internally: `src/services/_pdf/table_heuristics.py` is a `407`-line compatibility surface; focused remaining `>500` owners are `_table_heuristics/regions.py` (`1,085`), `_table_heuristics/screening.py` (`1,038`), and `_table_heuristics/layout.py` (`774`).
- PDF panel interpretation has now been decomposed internally: `src/services/_pdf/_visual_heuristics/panel_detection.py` is a `1,054`-line detector coordinator, with focused text interpretation in `panel_text.py` (`952`) and geometry construction in `panel_geometry.py` (`988`); `src/services/_pdf/visual_heuristics.py` is a `773`-line compatibility facade.
- PDF visual-candidate extraction has now been decomposed internally: `src/services/_pdf/visual_candidates.py` is a `164`-line compatibility surface; focused owners are `_visual_candidates/extraction.py` (`1,176`), `_visual_candidates/screening.py` (`684`), and `_visual_candidates/raster.py` (`558`).
- PDF figure extraction has now been decomposed internally: `src/services/_pdf/figures.py` is a `700`-line compatibility surface; focused owners are `_figures/triage.py` (`346`), `_figures/pruning.py` (`372`), `_figures/candidates.py` (`458`), and `_figures/best_figure.py` (`216`).
- PDF crop rendering has now been decomposed internally: `src/services/_pdf/crop.py` is a compatibility facade, with crop geometry in `_crop/geometry.py` (`550`), image operations, table-continuation stitching, crop-region artifact writing, crop-refine rendering, and preview rendering in focused `_crop/` owner modules.
- Publisher-inventory workflow coordination has now been decomposed internally: `src/services/_publisher_inventory_service/workflow.py` is a `563`-line coordinator and compatibility surface, with deterministic browser traversal behind the `browser_flow.py` compatibility surface and preflight scenario classification in `preflight.py`.
- Publisher-inventory browser traversal has now been decomposed internally: `browser_flow.py` is a compatibility surface over `_browser_flow/{interactions,collection,supplement,traversal}.py`, preserving the workflow entrypoint and browser/HTTP behavior.
- Publisher-inventory HTTP acquisition has now been decomposed internally: `fetch_service.py` is a compatibility surface over `_fetch/{parsing,discovery,classification,inspection}.py`.
- Publisher-inventory candidate quality has now been decomposed internally: `publisher_inventory_candidate_quality_generator.py` is a compatibility facade over `_publisher_inventory_candidate_quality/{classification,evaluation,workflow}.py`.
- Browser-report CDP access has now been decomposed internally: `_browser_report_download/cdp.py` is a compatibility surface over `_cdp/{models,transport,session,dialogs,operations}.py`.
- SQLite migrations have now been decomposed by schema ownership: `sqlite_migration_service.py` retains the canonical public entrypoints over `_sqlite_migration/{runner,reports,state,ui_runs}.py`; `reports.py` remains cohesive despite exceeding 1,000 lines because it owns one ordered reports-schema migration sequence.
- Reports-database migrations have now been decomposed internally: `_sqlite_migration/reports.py` is the ordered compatibility registry over `_reports/{schema,core,routing,projections}.py`.
- Analytics persistence has now been decomposed internally: `analytics_store_service.py` is the canonical facade over `_analytics_store/{common,projection_write,cross_report_read,signals}.py`.
- Publication orchestration has now been decomposed internally: `publish_orchestrator.py` retains the three public workflow functions and external-boundary patch points over `_publish_orchestrator/{models,routing,preflight,idempotency,cross_report}.py`.
- Publisher-inventory orchestration has now been decomposed internally: `src/orchestrators/publisher_inventory_orchestrator.py` is an `889`-line public coordinator and compatibility surface, while dependency wiring, idempotency, snapshot I/O, candidate-flow helpers, and runtime budget/retry helpers live in `src/orchestrators/_publisher_inventory_orchestrator/`.
- Publisher-inventory candidate screening has now been decomposed internally: `src/generators/publisher_inventory_candidate_screening_generator.py` is a compatibility facade, with shared marker normalization in `_publisher_inventory_candidate_screening/shared.py` (`534`) and focused deterministic screening, response-policy, and LLM-batch owners in the same private family.
- Cross-report analysis input preparation has now been decomposed internally: `src/generators/cross_report_analysis_input_generator.py` is a compatibility facade, with theme selection in `_cross_report_analysis_input/theme_selection.py` (`762`), evidence and signal preparation in `evidence_signals.py` (`703`), source selection in `source_selection.py`, and shared deterministic helpers in `shared.py`.
- Report-analysis orchestration has now been decomposed internally: `src/orchestrators/report_analysis_orchestrator.py` is a `588`-line public coordinator and compatibility surface, while artifact scheduling, vector-store readiness polling, payload checks, validation/regeneration execution, and regeneration-plan mapping live in `src/orchestrators/_report_analysis_orchestrator/`.
- The requested runtime long-file set has now been decomposed behind existing public boundaries: `src/services/drive_service.py`, `src/ui/app_pages/publisher_operations.py`, `src/services/_pdf/visual_heuristics.py`, `src/orchestrators/ui_run_execution_orchestrator.py`, `src/services/_pdf/_visual_heuristics/chart_layout.py`, and `src/generators/report_source_generator.py` are compatibility facades over focused private owner modules.

## Largest Runtime Files

### `src` Files >=1,000 Lines

| Lines | Path | Assessment |
| ---: | --- | --- |
| 1,979 | `src/cli.py` | Review after workflow work |
| 1,319 | `src/services/_browser_report_download/_browser_runtime/terminal_assets.py` | Focused browser terminal-evidence capability |
| 1,301 | `src/orchestrators/_report_download_orchestrator/route_planner.py` | Route-planning family |
| 1,282 | `src/orchestrators/report_generation_orchestrator.py` | Report-generation orchestration |
| 1,273 | `src/services/wordpress_service.py` | External-system boundary |
| 1,259 | `src/services/render_service.py` | Rendering boundary |
| 1,198 | `src/services/_pdf/_visual_candidates/extraction.py` | Focused visual extraction coordinator |
| 1,153 | `src/services/_browser_report_download/_artifact/classification.py` | Extracted artifact-classification capability |
| 1,121 | `src/contracts/cross_report_analysis.py` | Contract surface; do not split mechanically |
| 1,116 | `src/services/_pdf/_table_heuristics/screening.py` | Focused table screening capability |
| 1,102 | `src/services/_browser_report_download/_browser_runtime/session_lifecycle.py` | Focused browser lifecycle capability |
| 1,085 | `src/services/_pdf/_table_heuristics/regions.py` | Focused table-region geometry capability |
| 1,082 | `src/services/_report_store_service/download_routes.py` | Report-store capability family |
| 1,077 | `src/services/_publisher_inventory_service/discovery_activity.py` | Discovery parsing/activity family |
| 1,054 | `src/services/_pdf/_visual_heuristics/panel_detection.py` | Focused panel detector coordinator |
| 1,025 | `src/generators/_report_selection_generator/crop_refine.py` | Local performance candidate |
| 1,010 | `src/generators/analytics_projection_generator.py` | Analytics projection family |

### Large Test Concentration >=1,000 Lines

None. Current enforcement lives in `tests/test_long_test_file_ownership.py`; original long test entrypoints now remain thin facades over adjacent private case packages such as `tests/_test_report_download_orchestrator/`, `tests/test_browser_report_download_service/_test_prompt_and_probe/`, and `tests/test_pdf_figures_service/_builders/`.

## Completed Boundary Work

Do not recreate the obsolete February split plan. These public boundaries already use the approved facade-plus-internal-family pattern:

- `src/services/pdf_service.py` over `src/services/_pdf/*`.
- `src/services/config_service.py` over `src/services/_config_service/*`.
- `src/services/openai_service.py` over `src/services/_openai_service/*`.
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
- `src/ui/streamlit_pages.py` over `src/ui/app_pages/*` and `src/ui/_streamlit_pages/*`.
- Long first-party behavior tests over adjacent private test packages while preserving original pytest entrypoints, documented in `docs/architecture/test-long-file-decomposition-review.md`.

Any additional work must reduce responsibility or algorithmic complexity inside those existing capability families. Adding peer public entrypoints would be architecture regression.

## Remaining Priority Targets

### 1. Browser Report Download Internals

Primary evidence:

- `src/orchestrators/_report_download_orchestrator/route_planner.py`: `1,301` lines.
- `src/services/_browser_report_download/_cdp/operations.py`: focused CDP operation owner behind the `cdp.py` compatibility surface.
- `src/services/_browser_report_download/_browser_runtime/terminal_assets.py`: `1,319` lines.
- `src/services/_browser_report_download/_artifact/classification.py`: `1,153` lines.
- `src/services/_browser_report_download/_browser_runtime/session_lifecycle.py`: `1,102` lines.

Direction:

- Keep `src/services/browser_report_download_service.py` as the sole public browser-download service boundary.
- Retain the new `_artifact/*` internal capability family; `artifact.py` is now a smaller coordination module rather than the top hotspot.
- Retain the new `_browser_runtime/*` internal capability family; `browser.py` is now a smaller runtime coordinator rather than the top hotspot.
- Retain the new `_http/*` internal capability family; `http.py` is now a stable compatibility surface for focused HTTP acquisition implementations.
- Retain the new `_report_download_orchestrator/*` capability split; `workflow.py` is now a smaller sequencing coordinator and `route_planner.py` is the remaining orchestrator-family long-file review target.
- Continue extracting only coherent internal capabilities where responsibility or measured complexity remains high, such as deterministic HTTP acquisition/classification and route-history persistence.
- Keep route ordering, retry/backoff, idempotency, and state transitions in the orchestrator family.
- Keep prompt selection/rendering in the prompt service boundary; do not place prompt text in extracted modules.

Verification required:

- Existing browser-download, route-planner, and report-download orchestrator behavior tests.
- Failure paths asserting typed `AppError` fields, attempt count, terminal result classification, idempotency, and required structured log fields.
- No tests that preserve behavior by patching private/internal logic.

### 2. PDF Extraction Hot Paths

Primary evidence:

- `src/services/_pdf/_table_heuristics/regions.py`: `1,085` lines; focused region formation and bbox adjustment owner.
- `src/services/_pdf/_table_heuristics/screening.py`: `1,038` lines; focused rejection, scoring, and deduplication owner.
- `src/services/_pdf/_table_heuristics/layout.py`: `774` lines; focused page-layout and text interpretation owner.
- `src/services/_pdf/table_heuristics.py`: `407` lines; stable compatibility surface.
- `src/services/_pdf/_visual_heuristics/panel_detection.py`: `1,054` lines; detector-level decisions and candidate coordination.
- `src/services/_pdf/_visual_heuristics/panel_geometry.py`: `988` lines; deterministic panel geometry construction and adjustment.
- `src/services/_pdf/_visual_heuristics/panel_text.py`: `952` lines; deterministic title, caption, metric, and component-text interpretation.
- `src/services/_pdf/visual_candidates.py`: `164` lines; stable compatibility surface.
- `src/services/_pdf/_visual_candidates/extraction.py`: `1,176` lines; candidate construction, ordering, overlap handling, and worker coordination.
- `src/services/_pdf/_visual_candidates/screening.py`: `684` lines; deterministic textual and false-positive screening.
- `src/services/_pdf/_visual_candidates/raster.py`: `558` lines; raster qualification and probe caching.
- `src/services/_pdf/crop.py`: compatibility facade for focused `_crop/*` owners; `_crop/geometry.py` is now the largest crop-family owner at `550` lines.

Direction:

- Retain `src/services/pdf_service.py` as the canonical PDF boundary.
- Prioritize measured algorithm changes already recorded in `CONSOLIDATED_TODO.md`: indexed table deduplication and precomputed per-page visual candidate relationships.
- Retain the `_table_heuristics/*` capability split; `regions.py` and `screening.py` are the remaining table-family `>=1,000`-line review targets, and further extraction requires a semantic boundary rather than line-count slicing.
- Retain the `_visual_heuristics/{panel_text,panel_geometry,panel_detection}.py` semantic split behind `visual_heuristics.py`; optimization of precomputed visual relationships remains separate from the decomposition evidence.
- Retain the `_visual_candidates/{raster,screening,extraction}.py` semantic split behind `visual_candidates.py`; `extraction.py` is the remaining visual-candidate `>=1,000`-line coordinator and the deferred relationship-scan optimization is still a separate change.
- Retain the `_crop/*` semantic split behind `crop.py`; future crop-family work should target measured geometry or artifact-cache behavior, not additional facade layers.

Verification required:

- Correctness fixtures for near-duplicate/distinct tables, dense panels, multi-chart layouts, decorative images, wrappers, and crop boundaries.
- Before/after runtime benchmark evidence on large or visually dense fixtures.
- Candidate output and validation behavior must remain semantically equivalent unless a separately documented quality change is intended.

### 3. Publisher Discovery and Report-Download Workflows

Primary evidence:

- `src/services/_publisher_inventory_service/_browser_flow/collection.py`: focused rendered-page collection owner behind the `browser_flow.py` compatibility surface.
- `src/services/_publisher_inventory_service/workflow.py`: `563` lines; stable coordinator and compatibility surface.
- `src/services/_publisher_inventory_service/preflight.py`: focused preflight classification owner.
- `src/orchestrators/publisher_inventory_orchestrator.py`: `888` lines; public coordinator and compatibility surface.
- `src/generators/publisher_inventory_candidate_screening_generator.py`: compatibility facade for `_publisher_inventory_candidate_screening/*`; shared marker normalization is the largest owner at `534` lines.
- `src/generators/_publisher_inventory_candidate_quality/classification.py`: focused deterministic quality-classification owner behind the generator facade.

Direction:

- Preserve one publisher-inventory service boundary and one orchestration path.
- Retain the `_publisher_inventory_service/{preflight,browser_flow,workflow}.py` semantic split and the private `_browser_flow/*` and `_fetch/*` capability owners; `workflow.py` remains the service coordinator, route selector, runtime loader, and compatibility surface.
- Separate only stable behavior families such as acquisition adaptation, candidate qualification, snapshot/state recording, and recovery/route-memory decisions; retain the candidate-screening semantic split behind the generator facade.
- Keep service modules free of workflow retry choices and keep generators free of direct I/O.

Verification required:

- Existing publisher inventory service/orchestrator and candidate screening/quality tests.
- Pipeline tests for remembered-route reuse, snapshot preservation, retry decisions, and no duplicate side effects.
- Structured logging assertions for each public service and orchestrator boundary affected.

### 4. Track, Do Not Mechanically Split

These files need responsibility review or performance evidence before any decomposition proposal:

- Cross-report analysis synthesis, publishing, orchestrator, and contract files are active feature surfaces. The input generator now uses a private semantic split; any further work must preserve output contracts, publication flow, and regression coverage rather than splitting by line count.
- `src/cli.py` is large because it owns command registration and argument wiring; split only if command families can remain discoverable through one CLI boundary without duplicated routing.
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
8. Update `README.md` for any landed architecture or behavior change.

## Next Review Trigger

Refresh this audit after a remaining priority family is materially changed, when the canonical scan shows a new `src` file above 1,000 lines, or when `tests/test_long_test_file_ownership.py` reports a new first-party test file above 1,000 lines. A new top-level package, external service boundary, three-or-more peer-module split, or second path for the same external interaction requires the architecture review specified in `AGENTS.md`.
