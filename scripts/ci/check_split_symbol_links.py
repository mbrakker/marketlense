from __future__ import annotations

import ast
import builtins
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"

BOUNDARY_EXPORT_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "src/services/_config_service/common.py": (
        "Any",
        "AppSettings",
        "ConfigLoadRequest",
        "RunContext",
        "Path",
        "load_dotenv",
        "find_dotenv",
        "logger",
        "log_event",
        "_SettingSpec",
        "_ConfigResolver",
        "_default_config_value",
        "_env_value",
        "_is_missing",
        "_load_html_tag_acronyms",
        "_resolve_bootstrap_config_path",
        "_resolve_optional_path",
        "_resolve_scalar_settings",
        "_resolve_setting_raw",
        "_to_bool",
        "_to_config_bool",
        "_to_float",
        "_to_int",
        "_to_str",
    ),
    "src/services/_config_service/settings_resolvers.py": (
        "_resolve_analysis_settings",
        "_resolve_artifact_settings",
        "_resolve_contents_settings",
        "_resolve_drive_auth_settings",
        "_resolve_drive_settings",
        "_resolve_evidence_pack_settings",
        "_resolve_figure_caption_settings",
        "_resolve_ingest_runtime_settings",
        "_resolve_llm_runtime_settings",
        "_resolve_paths_settings",
        "_resolve_pdf_text_settings",
        "_resolve_rank_settings",
        "_resolve_validation_settings",
    ),
    "src/services/_pdf/visual_heuristics.py": (
        "_ChartRect",
        "_adjust_rect_for_text_margins",
        "_caption_blocks",
        "_collect_chart_rects",
        "_drawing_rects",
        "_extend_panel_with_adjacent_text_blocks",
        "_panel_caption_looks_top_band",
        "_panel_chart_has_data_signal",
        "_panel_chart_is_label_dense_not_prose",
        "_panel_chart_rects",
    ),
    "src/services/_pdf/table_heuristics.py": (
        "TABLE_SETTINGS_LATTICE",
        "TABLE_SETTINGS_STREAM",
        "_TableCandidate",
        "_compose_table_bbox",
        "_dedupe_table_candidates",
        "_detect_ranked_table_candidates",
        "_expand_table_bbox",
        "_extract_text_in_bbox",
        "_resolve_candidate_parallel_workers",
        "_suppress_pdfminer_warnings",
        "_table_page_text_blocks",
        "_table_preview",
        "_table_text_bands",
        "_text_stats",
        "_validate_table_candidate",
    ),
    "src/services/_pdf/visual_candidates.py": (
        "_RasterProbeCache",
        "_render_visual_probe_image",
        "_visual_probe_profile",
        "_page_has_chart_caption_blocks",
        "_visual_candidate_looks_table_like",
        "_visual_text_dense_recovery_allowed",
        "_extract_visuals_sequential",
        "extract_visual_candidates",
    ),
    "src/services/_pdf/crop.py": (
        "_dominant_border_color",
        "_legacy_chart_border_trim",
        "_tighten_chart_crop_rect",
        "_tighten_table_crop_rect",
        "_build_table_continuation_augments",
        "_crop_regions",
        "crop_regions",
        "render_page_for_crop_refine",
        "apply_crop_refine_bbox",
        "render_preview",
    ),
    "src/services/_pdf/_crop/image_ops.py": (
        "PDF_CROP_EXCEPTIONS",
        "PREVIEW_RENDER_EXCEPTIONS",
        "_dominant_border_color",
        "_trim_uniform_border",
        "_stack_crop_images",
        "_render_clip_image",
    ),
    "src/services/_pdf/_crop/geometry.py": (
        "_legacy_chart_border_trim",
        "_tighten_chart_crop_rect",
        "_tighten_table_crop_rect",
        "_crop_refine_edge_guard_rect",
    ),
    "src/services/_pdf/_crop/table_continuation.py": (
        "_TableContinuationAugment",
        "_table_title_strip_rect",
        "_table_note_strip_rect",
        "_build_table_continuation_augments",
    ),
    "src/services/_pdf/_crop/regions.py": (
        "_ResolvedCropRegion",
        "_crop_output_filename",
        "_crop_regions",
        "crop_regions",
    ),
    "src/services/_pdf/_crop/refine.py": (
        "render_page_for_crop_refine",
        "apply_crop_refine_bbox",
    ),
    "src/services/_pdf/_crop/preview.py": (
        "render_preview",
        "_page_png",
    ),
    "src/services/_pdf/_visual_candidates/raster.py": (
        "_RasterProbeCache",
        "_render_visual_probe_image",
        "_visual_probe_profile",
        "_embedded_visual_looks_chart_like",
    ),
    "src/services/_pdf/_visual_candidates/screening.py": (
        "_page_has_chart_caption_blocks",
        "_visual_candidate_looks_table_like",
        "_visual_candidate_looks_reference_or_prose",
        "_visual_text_dense_recovery_allowed",
    ),
    "src/services/_pdf/_visual_candidates/extraction.py": (
        "_extract_visuals_sequential",
        "extract_visual_candidates",
    ),
    "src/services/_pdf/_table_heuristics/policy.py": (
        "TABLE_SETTINGS_LATTICE",
        "TABLE_SETTINGS_STREAM",
        "TABLE_DEDUP_IOU",
    ),
    "src/services/_pdf/_table_heuristics/models.py": (
        "_TableCandidate",
        "_PageTextBlock",
        "_PageTextLine",
        "_TableTextBand",
        "_RankedTableRegion",
    ),
    "src/services/_pdf/_table_heuristics/layout.py": (
        "_table_page_text_blocks",
        "_table_text_bands",
        "_table_preview",
        "_extract_text_in_bbox",
        "_text_stats",
    ),
    "src/services/_pdf/_table_heuristics/regions.py": (
        "_detect_ranked_table_candidates",
        "_compose_table_bbox",
        "_expand_table_bbox",
    ),
    "src/services/_pdf/_table_heuristics/screening.py": (
        "_validate_table_candidate",
        "_dedupe_table_candidates",
        "_table_quality",
    ),
    "src/services/_pdf/_visual_heuristics/chart_layout.py": (
        "_caption_blocks",
        "_drawing_caption_rects",
        "_drawing_rects",
        "_heading_chart_rects",
        "_image_block_rects",
    ),
    "src/services/_pdf/_visual_heuristics/panel_text.py": (
        "_panel_caption_looks_metric_stub",
        "_panel_chart_has_data_signal",
        "_panel_caption_looks_top_band",
    ),
    "src/services/_pdf/_visual_heuristics/panel_geometry.py": (
        "_extend_panel_rect_with_nearby_label_blocks",
        "_clamp_panel_rect_to_dominant_fill_rect",
        "_extend_panel_with_adjacent_text_blocks",
    ),
    "src/services/_pdf/_visual_heuristics/panel_detection.py": ("_panel_chart_rects",),
    "src/services/_pdf/_visual_heuristics/collectors.py": ("_collect_chart_rects",),
    "src/services/_publisher_inventory_service/workflow.py": (
        "discover_publisher_inventory",
        "inspect_publisher_inventory_landing_pages",
        "_build_scenario_summary",
        "_classify_preflight_scenario",
        "_run_browser_traversal_with_timeout",
        "_extract_browser_http_supplement_candidates",
        "_discover_with_browser",
    ),
    "src/services/_publisher_inventory_service/preflight.py": (
        "_build_scenario_summary",
        "_classify_preflight_scenario",
        "_looks_like_preflight_filter_route",
        "_looks_like_preflight_direct_detail_path",
    ),
    "src/services/_publisher_inventory_service/browser_flow.py": (
        "_run_browser_traversal",
        "_run_browser_traversal_with_timeout",
        "_collect_browser_inventory_pages",
        "_wait_for_inventory_growth_probe",
        "_extract_browser_http_supplement_candidates",
    ),
    "src/orchestrators/publisher_inventory_orchestrator.py": (
        "PublisherInventoryDependencies",
        "run_publisher_inventory_discovery",
        "_record_run_quality_if_needed",
        "_load_previous_snapshot",
        "_run_discovery_attempt",
        "_candidate_provenance_counts",
    ),
    "src/orchestrators/_publisher_inventory_orchestrator/dependencies.py": (
        "PublisherInventoryDependencies",
    ),
    "src/orchestrators/_publisher_inventory_orchestrator/idempotency.py": (
        "_RUN_QUALITY_IDEMPOTENCY_SCOPE",
        "_RECOVERY_CACHE_IDEMPOTENCY_SCOPE",
        "_SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE",
        "_REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE",
        "_STATE_RECORD_IDEMPOTENCY_SCOPE",
        "_TEST_STATUS_IDEMPOTENCY_SCOPE",
        "_lookup_idempotency_record",
        "_record_idempotency_outcome",
        "_idempotency_key_with_checksum",
        "_optional_dataclass_payload",
        "_run_quality_record_checksum",
        "_state_record_checksum",
        "_test_status_record_checksum",
        "_recovery_cache_record_checksum",
        "_record_run_quality_if_needed",
        "_record_state_if_needed",
        "_record_test_status_if_needed",
        "_record_recovery_cache_if_needed",
        "_restore_drive_file",
        "_payload_optional_str",
        "_restore_upload_bytes_response",
        "_restore_report_source_record",
    ),
    "src/orchestrators/_publisher_inventory_orchestrator/snapshot_io.py": (
        "_SNAPSHOT_PREFIX",
        "_SNAPSHOT_LOOKBACK_LIMIT",
        "_load_previous_snapshot",
        "_snapshot_file_name",
    ),
    "src/orchestrators/_publisher_inventory_orchestrator/candidate_flow.py": (
        "_rank_qualified_items_by_resource_quality",
        "_candidate_provenance_counts",
        "_record_deferred_candidate_recovery_cache",
        "_log_rollout_guardrails",
        "_source_domain_for_url",
    ),
    "src/orchestrators/_publisher_inventory_orchestrator/runtime.py": (
        "_record_discovery_test_status_on_failure",
        "_discovery_test_status_for_error_code",
        "_run_discovery_attempt",
        "_remaining_time_budget_seconds",
        "_assert_time_budget_remaining",
        "_settings_with_time_budget",
        "_utc_now_iso",
    ),
    "src/services/_browser_report_download/helpers.py": (
        "get_browser_helper_surface",
        "browser_helper_page_info",
        "browser_helper_capture_screenshot",
        "browser_helper_coordinate_fallback_click",
        "browser_helper_js",
        "browser_helper_form_autocomplete",
        "browser_helper_js_async",
        "browser_helper_wait_for_load",
        "browser_helper_ensure_real_tab",
        "browser_helper_http_get",
    ),
    "src/services/_browser_report_download/_helpers/state.py": (
        "browser_helper_page_info",
        "browser_helper_wait_for_load",
        "browser_helper_ensure_real_tab",
        "_find_real_tab_via_cdp",
        "_maybe_await",
        "_excerpt",
    ),
    "src/services/_browser_report_download/_helpers/inspection.py": (
        "_JavaScriptEvaluationError",
        "browser_helper_js",
        "browser_helper_js_async",
        "browser_helper_http_get",
        "_wrap_js_expression",
        "_adapt_js_result_value",
    ),
    "src/services/_browser_report_download/_helpers/interaction.py": (
        "browser_helper_capture_screenshot",
        "browser_helper_coordinate_fallback_click",
        "browser_helper_form_autocomplete",
        "_coordinate_fallback_policy",
        "_try_screenshot_call",
    ),
    "src/generators/cross_report_analysis_input_generator.py": (
        "select_cross_report_source_reports",
        "select_cross_report_theme",
        "validate_cross_report_publishability",
        "assemble_cross_report_analysis_inputs",
        "score_cross_report_signals",
        "group_cross_report_evidence_agreement",
    ),
    "src/generators/_cross_report_analysis_input/shared.py": (
        "_DEFAULT_THEME_SCORE_WEIGHTS",
        "_DEFAULT_SIGNAL_SCORE_WEIGHTS",
        "_RAW_METRIC_POLICY",
        "_clean_values",
        "_slug",
        "_source_recency_scores",
    ),
    "src/generators/_cross_report_analysis_input/source_selection.py": (
        "_cleaned_filters",
        "_score_candidates",
        "_select_diverse_sources",
        "select_cross_report_source_reports",
    ),
    "src/generators/_cross_report_analysis_input/theme_selection.py": (
        "_load_recent_theme_metadata",
        "_explicit_theme_candidate",
        "select_cross_report_theme",
        "validate_cross_report_publishability",
    ),
    "src/generators/_cross_report_analysis_input/evidence_signals.py": (
        "assemble_cross_report_analysis_inputs",
        "score_cross_report_signals",
        "group_cross_report_evidence_agreement",
        "_agreement_type_and_reasons",
    ),
    "src/services/_openai_service/base.py": (
        "AppError",
        "OpenAIAnalyzeRequest",
        "OpenAIResponseResult",
        "RunContext",
        "_VectorStoreOperationSpec",
        "_adapt_chat_completion_metadata",
        "_build_response_metadata",
        "_classify_openai_request_error",
        "_record_usage_accounting",
    ),
    "src/services/_openai_service/client.py": (
        "_build_openai_client",
        "_log_vector_store_event",
        "_require_openai_id",
        "_run_vector_store_request",
        "_value_from_response",
    ),
}

STAR_LINK_TARGETS = (
    "src/services/_config_service/*.py",
    "src/services/_pdf/_visual_heuristics/*.py",
    "src/services/_openai_service/*.py",
)

ORDERED_SUBMODULE_EXPORTS: dict[str, dict[str, str]] = {
    "src/services/_pdf/visual_heuristics.py": {
        "_CHART_LAYOUT_EXPORTS": "src/services/_pdf/_visual_heuristics/chart_layout.py",
        "_PANEL_TEXT_EXPORTS": "src/services/_pdf/_visual_heuristics/panel_text.py",
        "_PANEL_GEOMETRY_EXPORTS": "src/services/_pdf/_visual_heuristics/panel_geometry.py",
        "_PANEL_DETECTION_EXPORTS": "src/services/_pdf/_visual_heuristics/panel_detection.py",
        "_COLLECTOR_EXPORTS": "src/services/_pdf/_visual_heuristics/collectors.py",
    }
}

IGNORED_GLOBAL_NAMES = {
    *dir(builtins),
    "TYPE_CHECKING",
    "annotations",
    "__file__",
}


@dataclass(frozen=True)
class ModuleInfo:
    path: Path
    exports: frozenset[str]
    load_names: frozenset[str]
    bound_names: frozenset[str]
    star_imports: tuple[Path, ...]
    star_import_lines: dict[Path, int]
    all_augment_lines: dict[str, int]


@dataclass(frozen=True)
class SplitSymbolViolation:
    path: Path
    category: str
    message: str
    symbol: str = ""
    provider: Path | None = None


def _repo_path(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _module_name_for_path(path: Path, *, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _path_for_module(module_name: str, *, root: Path) -> Path:
    return root / Path(*module_name.split(".")).with_suffix(".py")


def _resolve_import_from_path(
    *, current_path: Path, node: ast.ImportFrom, root: Path
) -> Path | None:
    if node.level == 0:
        if not node.module:
            return None
        module_name = node.module
    else:
        current_module = _module_name_for_path(current_path, root=root)
        package_parts = current_module.split(".")[:-1]
        if node.level > 1:
            package_parts = package_parts[: -(node.level - 1)]
        suffix = node.module.split(".") if node.module else []
        module_name = ".".join([*package_parts, *suffix])
    path = _path_for_module(module_name, root=root)
    if path.exists():
        return path
    package_init = path.with_suffix("") / "__init__.py"
    return package_init if package_init.exists() else None


def _literal_string_list(node: ast.AST) -> tuple[str, ...] | None:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    values: list[str] = []
    for item in node.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return None
        values.append(item.value)
    return tuple(values)


def _string_exports_from_expr(
    node: ast.AST, *, list_bindings: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    literal_values = _literal_string_list(node)
    if literal_values is not None:
        return literal_values
    if isinstance(node, ast.Name):
        return list_bindings.get(node.id, ())
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return (
            *_string_exports_from_expr(node.left, list_bindings=list_bindings),
            *_string_exports_from_expr(node.right, list_bindings=list_bindings),
        )
    return ()


def _store_names(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _store_names(item)


def _function_arg_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterable[str]:
    args = node.args
    for arg in (
        *args.posonlyargs,
        *args.args,
        *args.kwonlyargs,
    ):
        yield arg.arg
    if args.vararg is not None:
        yield args.vararg.arg
    if args.kwarg is not None:
        yield args.kwarg.arg


def parse_module(path: Path, *, root: Path) -> ModuleInfo:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    list_bindings: dict[str, tuple[str, ...]] = {}
    exports: set[str] = set()
    load_names: set[str] = set()
    bound_names: set[str] = set()
    star_imports: list[Path] = []
    star_import_lines: dict[Path, int] = {}
    all_augment_lines: dict[str, int] = {}
    top_level_bound_names: set[str] = set()
    exports_all_globals = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                load_names.add(node.id)
            elif isinstance(node.ctx, (ast.Store, ast.Param)):
                bound_names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound_names.add(node.name)
            bound_names.update(_function_arg_names(node))
        elif isinstance(node, ast.ClassDef):
            bound_names.add(node.name)
        elif isinstance(node, ast.Lambda):
            args = node.args
            for arg in (
                *args.posonlyargs,
                *args.args,
                *args.kwonlyargs,
            ):
                bound_names.add(arg.arg)
            if args.vararg is not None:
                bound_names.add(args.vararg.arg)
            if args.kwarg is not None:
                bound_names.add(args.kwarg.arg)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if not any(alias.name == "*" for alias in node.names):
                for alias in node.names:
                    bound_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound_names.add(node.name)

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                bound_names.add(name)
                top_level_bound_names.add(name)
        elif isinstance(node, ast.ImportFrom):
            is_star = any(alias.name == "*" for alias in node.names)
            if is_star:
                source_path = _resolve_import_from_path(
                    current_path=path, node=node, root=root
                )
                if source_path is not None:
                    star_imports.append(source_path)
                    star_import_lines[source_path] = node.lineno
            else:
                for alias in node.names:
                    name = alias.asname or alias.name
                    bound_names.add(name)
                    top_level_bound_names.add(name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound_names.add(node.name)
            top_level_bound_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in _store_names(target):
                    bound_names.add(name)
                    top_level_bound_names.add(name)
                    literal_values = _literal_string_list(node.value)
                    if literal_values is not None:
                        list_bindings[name] = literal_values
                    if name == "__all__":
                        explicit_exports = _string_exports_from_expr(
                            node.value, list_bindings=list_bindings
                        )
                        if explicit_exports:
                            exports.update(explicit_exports)
                        elif _is_globals_all_comprehension(node.value):
                            exports_all_globals = True
        elif isinstance(node, ast.AnnAssign):
            for name in _store_names(node.target):
                bound_names.add(name)
                top_level_bound_names.add(name)
        elif isinstance(node, ast.AugAssign):
            for name in _store_names(node.target):
                bound_names.add(name)
                if name == "__all__":
                    for exported_name in _string_exports_from_expr(
                        node.value, list_bindings=list_bindings
                    ):
                        exports.add(exported_name)
                    for group_name in _all_export_group_names(node.value):
                        all_augment_lines.setdefault(group_name, node.lineno)
    if exports_all_globals:
        exports.update(
            name
            for name in top_level_bound_names
            if not name.startswith("__") and name not in IGNORED_GLOBAL_NAMES
        )

    return ModuleInfo(
        path=path,
        exports=frozenset(exports),
        load_names=frozenset(load_names),
        bound_names=frozenset(bound_names),
        star_imports=tuple(star_imports),
        star_import_lines=star_import_lines,
        all_augment_lines=all_augment_lines,
    )


def _all_export_group_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return (
            *_all_export_group_names(node.left),
            *_all_export_group_names(node.right),
        )
    return ()


def _is_globals_all_comprehension(node: ast.AST) -> bool:
    if not isinstance(node, ast.ListComp):
        return False
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "globals"
        ):
            return True
    return False


def _target_paths(patterns: Iterable[str], *, root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(sorted(root.glob(pattern)))
    return tuple(path for path in paths if path.is_file())


def _provider_exports(
    provider: Path, *, root: Path, cache: dict[Path, ModuleInfo]
) -> frozenset[str]:
    if provider not in cache:
        cache[provider] = parse_module(provider, root=root)
    return cache[provider].exports


def scan_symbol_links(
    *,
    root: Path,
    boundary_export_requirements: dict[str, tuple[str, ...]],
    star_link_targets: tuple[str, ...],
    ordered_submodule_exports: dict[str, dict[str, str]],
) -> tuple[SplitSymbolViolation, ...]:
    cache: dict[Path, ModuleInfo] = {}
    violations: list[SplitSymbolViolation] = []

    for rel_path, required_symbols in boundary_export_requirements.items():
        path = root / rel_path
        if not path.exists():
            violations.append(
                SplitSymbolViolation(
                    path=path,
                    category="missing_module",
                    message="Configured split-symbol module does not exist.",
                )
            )
            continue
        info = parse_module(path, root=root)
        cache[path] = info
        for symbol in required_symbols:
            if symbol not in info.exports:
                violations.append(
                    SplitSymbolViolation(
                        path=path,
                        category="missing_required_export",
                        symbol=symbol,
                        message=(
                            "Required split-boundary symbol is not listed in "
                            "`__all__`; star-import consumers will not receive it."
                        ),
                    )
                )

    for path in _target_paths(star_link_targets, root=root):
        info = cache.get(path) or parse_module(path, root=root)
        cache[path] = info
        if not info.star_imports:
            continue
        exported_by_star_imports: set[str] = set()
        providers_with_missing_all: list[Path] = []
        for provider in info.star_imports:
            exports = _provider_exports(provider, root=root, cache=cache)
            if not exports:
                providers_with_missing_all.append(provider)
            exported_by_star_imports.update(exports)
        unresolved = sorted(
            info.load_names
            - info.bound_names
            - exported_by_star_imports
            - IGNORED_GLOBAL_NAMES
        )
        for provider in providers_with_missing_all:
            violations.append(
                SplitSymbolViolation(
                    path=path,
                    provider=provider,
                    category="missing_provider_exports",
                    message=(
                        "Star-import provider has no statically declared `__all__`; "
                        "split private helpers may not be linked deterministically."
                    ),
                )
            )
        for symbol in unresolved:
            violations.append(
                SplitSymbolViolation(
                    path=path,
                    category="unlinked_star_import_symbol",
                    symbol=symbol,
                    message=(
                        "Symbol is referenced but is neither locally bound nor "
                        "exported by any star-import provider."
                    ),
                )
            )

    for rel_path, export_groups in ordered_submodule_exports.items():
        path = root / rel_path
        if path not in cache and path.exists():
            cache[path] = parse_module(path, root=root)
        info = cache.get(path)
        if info is None:
            continue
        for export_group, import_rel_path in export_groups.items():
            import_path = root / import_rel_path
            augment_line = info.all_augment_lines.get(export_group)
            import_line = info.star_import_lines.get(import_path)
            if augment_line is None or import_line is None:
                continue
            if augment_line <= import_line:
                violations.append(
                    SplitSymbolViolation(
                        path=path,
                        provider=import_path,
                        category="unsafe_export_order",
                        symbol=export_group,
                        message=(
                            "Submodule export group is added to `__all__` before "
                            "the star import loads the provider; this can create "
                            "partial-initialization import failures."
                        ),
                    )
                )

    return tuple(violations)


def scan_repository(root: Path = ROOT) -> tuple[SplitSymbolViolation, ...]:
    return scan_symbol_links(
        root=root,
        boundary_export_requirements=BOUNDARY_EXPORT_REQUIREMENTS,
        star_link_targets=STAR_LINK_TARGETS,
        ordered_submodule_exports=ORDERED_SUBMODULE_EXPORTS,
    )


def _print_grouped_diagnostics(
    violations: Iterable[SplitSymbolViolation], *, root: Path
) -> None:
    by_category: dict[str, list[SplitSymbolViolation]] = {}
    for violation in violations:
        by_category.setdefault(violation.category, []).append(violation)
    for category in sorted(by_category):
        print(f"\n{category}:")
        for item in sorted(
            by_category[category],
            key=lambda violation: (
                _repo_path(violation.path, root=root),
                violation.symbol,
                _repo_path(violation.provider, root=root)
                if violation.provider is not None
                else "",
            ),
        ):
            provider = (
                f"; provider={_repo_path(item.provider, root=root)}"
                if item.provider is not None
                else ""
            )
            symbol = f"; symbol={item.symbol}" if item.symbol else ""
            print(
                f"  - {_repo_path(item.path, root=root)}{symbol}{provider}: "
                f"{item.message}"
            )


def main() -> int:
    violations = scan_repository(ROOT)
    if not violations:
        print("Split symbol-linking gate passed.")
        return 0

    print("Split symbol-linking gate failed:")
    _print_grouped_diagnostics(violations, root=ROOT)
    print(
        "\nRepair the split boundary by adding the missing symbol to the owning "
        "`__all__`, importing it explicitly, or moving the symbol to the correct "
        "owner module before running mypy."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
