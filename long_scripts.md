# Long-File Audit and Refactor Targets

Generated: 2026-05-26

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
| First-party `src` | 94 | 36 |
| First-party `tests` | 43 | 24 |
| First-party `scripts` | 1 | 0 |
| WordPress integration | 5 | 3 |

- Total first-party source-like files scanned: `642`.
- Skipped paths/files: `45` (`40` top-level runtime/temp directories, `4` outside first-party analysis roots, `1` vendored dependency tree).
- The previous February inventory is obsolete: the large public `pdf_service`, `config_service`, `openai_service`, `artifact_generator`, `report_store_service`, and Streamlit page boundaries have already been decomposed or converted into facades.
- Since the previous scan, browser artifact finalization has been decomposed internally: `src/services/_browser_report_download/artifact.py` is now `703` lines, while the extracted `src/services/_browser_report_download/_artifact/classification.py` is `1,153` lines.
- Browser runtime execution has now been decomposed internally: `src/services/_browser_report_download/browser.py` is `671` lines, with remaining focused hotspots in `_browser_runtime/terminal_assets.py` (`1,319`) and `_browser_runtime/session_lifecycle.py` (`1,102`).

## Largest Runtime Files

### `src` Files >=1,000 Lines

| Lines | Path | Assessment |
| ---: | --- | --- |
| 3,390 | `src/services/_pdf/table_heuristics.py` | Active PDF heuristic hotspot |
| 2,637 | `src/services/_pdf/_visual_heuristics/panel_detection.py` | Active PDF heuristic hotspot |
| 2,554 | `src/orchestrators/_report_download_orchestrator/workflow.py` | Active orchestrator hotspot |
| 2,301 | `src/services/_publisher_inventory_service/workflow.py` | Active service-family hotspot |
| 2,263 | `src/services/_pdf/visual_candidates.py` | Active PDF heuristic hotspot |
| 2,066 | `src/services/_browser_report_download/http.py` | Active service-family hotspot |
| 1,994 | `src/orchestrators/publisher_inventory_orchestrator.py` | Active orchestrator hotspot |
| 1,926 | `src/cli.py` | Review after workflow work |
| 1,892 | `src/services/_browser_report_download/helpers.py` | Active service-family hotspot |
| 1,877 | `src/generators/cross_report_analysis_input_generator.py` | New feature surface; stabilize first |
| 1,689 | `src/services/_pdf/crop.py` | PDF family follow-up |
| 1,682 | `src/generators/publisher_inventory_candidate_screening_generator.py` | Discovery quality family |
| 1,650 | `src/orchestrators/report_analysis_orchestrator.py` | Existing workflow surface |
| 1,650 | `src/services/_pdf/figures.py` | PDF family follow-up |
| 1,625 | `src/services/sqlite_migration_service.py` | Persistence boundary; split only by migration ownership |
| 1,610 | `src/generators/publisher_inventory_candidate_quality_generator.py` | Discovery quality family |
| 1,593 | `src/services/_browser_report_download/cdp.py` | Browser terminal-evidence family |
| 1,563 | `src/services/_publisher_inventory_service/fetch_service.py` | Discovery acquisition family |
| 1,534 | `src/services/analytics_store_service.py` | Analytics store boundary |
| 1,506 | `src/orchestrators/publish_orchestrator.py` | Publication workflow boundary |
| 1,431 | `src/ui/app_pages/publisher_operations.py` | UI-only page family |
| 1,329 | `src/services/_pdf/_visual_heuristics/chart_layout.py` | PDF heuristic family |
| 1,328 | `src/generators/report_source_generator.py` | Report-source domain family |
| 1,319 | `src/services/_browser_report_download/_browser_runtime/terminal_assets.py` | Focused browser terminal-evidence capability |
| 1,301 | `src/orchestrators/_report_download_orchestrator/route_planner.py` | Route-planning family |
| 1,300 | `src/services/drive_service.py` | External-system boundary |
| 1,216 | `src/services/_pdf/visual_heuristics.py` | PDF heuristic family |
| 1,207 | `src/services/wordpress_service.py` | External-system boundary |
| 1,153 | `src/services/_browser_report_download/_artifact/classification.py` | Extracted artifact-classification capability |
| 1,102 | `src/services/_browser_report_download/_browser_runtime/session_lifecycle.py` | Focused browser lifecycle capability |
| 1,082 | `src/services/_report_store_service/download_routes.py` | Report-store capability family |
| 1,076 | `src/services/_publisher_inventory_service/discovery_activity.py` | Discovery parsing/activity family |
| 1,059 | `src/contracts/cross_report_analysis.py` | Contract surface; do not split mechanically |
| 1,052 | `src/services/render_service.py` | Rendering boundary |
| 1,032 | `src/generators/_report_selection_generator/crop_refine.py` | Local performance candidate |
| 1,009 | `src/generators/analytics_projection_generator.py` | Analytics projection family |

### Large Test Concentration >=1,000 Lines

| Lines | Path |
| ---: | --- |
| 3,509 | `tests/test_browser_report_download_service/test_onsite_and_terminal.py` |
| 3,213 | `tests/test_report_download_orchestrator.py` |
| 2,926 | `tests/test_publisher_inventory_candidate_quality_generator.py` |
| 2,826 | `tests/test_report_store_service.py` |
| 2,523 | `tests/test_browser_report_download_service/test_prompt_and_probe.py` |
| 2,503 | `tests/test_pdf_figures_service/builders.py` |
| 2,311 | `tests/test_cross_report_analysis_input_generator.py` |
| 2,199 | `tests/test_publisher_inventory_service/test_browser_traversal.py` |
| 2,020 | `tests/test_publisher_inventory_orchestrator.py` |
| 1,862 | `tests/test_artifact_generator.py` |
| 1,607 | `tests/test_validation_generator.py` |
| 1,599 | `tests/test_browser_report_download_service/test_worker_and_recovery.py` |
| 1,577 | `tests/test_report_analysis_generator.py` |
| 1,550 | `tests/test_candidate_refine_selection.py` |
| 1,520 | `tests/test_cli.py` |
| 1,378 | `tests/test_publisher_inventory_candidate_screening_generator.py` |
| 1,378 | `tests/test_vector_pipeline_wiring.py` |
| 1,341 | `tests/test_pdf_figures_service/test_panel_heuristics.py` |
| 1,252 | `tests/test_config_service.py` |
| 1,223 | `tests/test_report_source_generator.py` |
| 1,206 | `tests/test_pdf_figures_service/test_table_heuristics.py` |
| 1,166 | `tests/test_pdf_crop_service.py` |
| 1,109 | `tests/test_cross_report_analysis_generator.py` |
| 1,094 | `tests/test_evidence_pack_generator.py` |

### Other First-Party Sections

| Lines | Path |
| ---: | --- |
| 551 | `scripts/ci/check_split_symbol_links.py` |
| 7,026 | `Wordpress/wp-content/themes/marketlense/assets/css/theme.css` |
| 1,762 | `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php` |
| 1,009 | `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-taxonomies.php` |
| 837 | `Wordpress/config/publisher-profiles.json` |
| 534 | `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-intelligence-stats.php` |

## Completed Boundary Work

Do not recreate the obsolete February split plan. These public boundaries already use the approved facade-plus-internal-family pattern:

- `src/services/pdf_service.py` over `src/services/_pdf/*`.
- `src/services/config_service.py` over `src/services/_config_service/*`.
- `src/services/openai_service.py` over `src/services/_openai_service/*`.
- `src/services/report_store_service.py` over `src/services/_report_store_service/*`.
- `src/services/state_service.py` over `src/services/_state_service/*`.
- `src/services/publisher_inventory_service.py` over `src/services/_publisher_inventory_service/*`.
- `src/services/browser_report_download_service.py` over `src/services/_browser_report_download/*`, including the internal `src/services/_browser_report_download/_artifact/*` and `src/services/_browser_report_download/_browser_runtime/*` capability families.
- `src/generators/artifact_generator.py` over `src/generators/_artifact_generator/*`.
- `src/generators/report_generation_dependencies.py` over `src/generators/_report_generation_dependencies/*`.
- `src/orchestrators/report_download_orchestrator.py` over `src/orchestrators/_report_download_orchestrator/*`.
- `src/ui/streamlit_pages.py` over `src/ui/app_pages/*` and `src/ui/_streamlit_pages/*`.

Any additional work must reduce responsibility or algorithmic complexity inside those existing capability families. Adding peer public entrypoints would be architecture regression.

## Remaining Priority Targets

### 1. Browser Report Download Internals

Primary evidence:

- `src/orchestrators/_report_download_orchestrator/workflow.py`: `2,554` lines.
- `src/services/_browser_report_download/http.py`: `2,066` lines.
- `src/services/_browser_report_download/helpers.py`: `1,892` lines.
- `src/services/_browser_report_download/cdp.py`: `1,593` lines.
- `src/services/_browser_report_download/_browser_runtime/terminal_assets.py`: `1,319` lines.
- `src/services/_browser_report_download/_artifact/classification.py`: `1,153` lines.
- `src/services/_browser_report_download/_browser_runtime/session_lifecycle.py`: `1,102` lines.

Direction:

- Keep `src/services/browser_report_download_service.py` as the sole public browser-download service boundary.
- Retain the new `_artifact/*` internal capability family; `artifact.py` is now a smaller coordination module rather than the top hotspot.
- Retain the new `_browser_runtime/*` internal capability family; `browser.py` is now a smaller runtime coordinator rather than the top hotspot.
- Continue extracting only coherent internal capabilities where responsibility or measured complexity remains high, such as deterministic HTTP acquisition/classification and route-history persistence.
- Keep route ordering, retry/backoff, idempotency, and state transitions in the orchestrator family.
- Keep prompt selection/rendering in the prompt service boundary; do not place prompt text in extracted modules.

Verification required:

- Existing browser-download, route-planner, and report-download orchestrator behavior tests.
- Failure paths asserting typed `AppError` fields, attempt count, terminal result classification, idempotency, and required structured log fields.
- No tests that preserve behavior by patching private/internal logic.

### 2. PDF Extraction Hot Paths

Primary evidence:

- `src/services/_pdf/table_heuristics.py`: `3,390` lines.
- `src/services/_pdf/_visual_heuristics/panel_detection.py`: `2,637` lines.
- `src/services/_pdf/visual_candidates.py`: `2,263` lines.
- `src/services/_pdf/crop.py`: `1,689` lines.

Direction:

- Retain `src/services/pdf_service.py` as the canonical PDF boundary.
- Prioritize measured algorithm changes already recorded in `CONSOLIDATED_TODO.md`: indexed table deduplication and precomputed per-page visual candidate relationships.
- Extract internal modules only when an algorithm or stable heuristic family gains independent testability; do not create forwarding-only layers.

Verification required:

- Correctness fixtures for near-duplicate/distinct tables, dense panels, multi-chart layouts, decorative images, wrappers, and crop boundaries.
- Before/after runtime benchmark evidence on large or visually dense fixtures.
- Candidate output and validation behavior must remain semantically equivalent unless a separately documented quality change is intended.

### 3. Publisher Discovery and Report-Download Workflows

Primary evidence:

- `src/services/_publisher_inventory_service/workflow.py`: `2,301` lines.
- `src/orchestrators/publisher_inventory_orchestrator.py`: `1,994` lines.
- `src/generators/publisher_inventory_candidate_screening_generator.py`: `1,682` lines.
- `src/generators/publisher_inventory_candidate_quality_generator.py`: `1,610` lines.

Direction:

- Preserve one publisher-inventory service boundary and one orchestration path.
- Separate only stable behavior families such as acquisition adaptation, candidate qualification, snapshot/state recording, and recovery/route-memory decisions.
- Keep service modules free of workflow retry choices and keep generators free of direct I/O.

Verification required:

- Existing publisher inventory service/orchestrator and candidate screening/quality tests.
- Pipeline tests for remembered-route reuse, snapshot preservation, retry decisions, and no duplicate side effects.
- Structured logging assertions for each public service and orchestrator boundary affected.

### 4. Track, Do Not Mechanically Split

These files need responsibility review or performance evidence before any decomposition proposal:

- Cross-report analysis files are new active feature surfaces. Stabilize output contracts, publication flow, and regression coverage before splitting by line count.
- `src/cli.py` is large because it owns command registration and argument wiring; split only if command families can remain discoverable through one CLI boundary without duplicated routing.
- Contract modules may be large without role-mixing. Split `src/contracts/cross_report_analysis.py` only along independently versioned semantic contracts, never for cosmetics.
- External boundary modules such as Drive and WordPress services must retain one canonical namespace if internal capability extraction becomes justified.

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

Refresh this audit after a remaining priority family is materially changed, or when the canonical scan shows a new `src` file above 1,000 lines. A new top-level package, external service boundary, three-or-more peer-module split, or second path for the same external interaction requires the architecture review specified in `AGENTS.md`.
