# Requested Runtime Decomposition Review

This review covers the movement-only split of the requested long runtime modules:

- `src/contracts/cross_report_analysis.py`
- `src/services/_pdf/_table_heuristics/screening.py`
- `src/services/_pdf/_table_heuristics/regions.py`
- `src/services/_browser_report_download/_browser_runtime/session_lifecycle.py`
- `src/services/_report_store_service/download_routes.py`

## Boundary Review

The change preserves the modular monolith. No new public service boundary, process, package, queue, or external-system entrypoint was introduced.

The new boundaries are semantic private owners:

- Cross-report contracts: `_cross_report_analysis/{common,requests,selection,generation,publication,artifact,validation}.py`.
- PDF table screening: `_table_heuristics/_screening/{metrics,rejections,deduplication}.py`.
- PDF table regions: `_table_heuristics/_regions/{ranked,context,compose}.py`.
- Browser session lifecycle: `_browser_runtime/_session_lifecycle/{history,partial_history,cleanup,shutdown}.py`.
- Report-store download routes: `_report_store_service/_download_routes/{private_api,route_lookup,route_recording}.py`.

The original modules remain compatibility facades. Callers still import through the same canonical paths, including `src.contracts.cross_report_analysis`, `src.services._pdf._table_heuristics.screening`, `src.services._pdf._table_heuristics.regions`, `src.services._browser_report_download._browser_runtime.session_lifecycle`, and `src.services._report_store_service.download_routes`.

This reduces cognitive load for the next engineer by separating independently testable responsibilities without adding alternate workflow paths or pass-through service boundaries.

## Movement Audit

AST audit against `HEAD`:

- Moved top-level symbols/constants: `143`
- AST-identical moved symbols/constants: `142`
- Changed moved symbols/constants: `1`
- Missing moved symbols/constants: `0`
- Facade-owned definitions after split: `0`

The single changed symbol is `validate_cross_report_contract`, which now accepts cross-report dataclasses from the private `_cross_report_analysis` module namespace after the movement. Error taxonomy, schema-version checks, required-field checks, and list-null validation are unchanged.

## Verification

Red structural guard before movement:

```powershell
python -m pytest tests/test_requested_long_runtime_decomposition.py -q
```

Failed because all five requested files exceeded the facade threshold.

Targeted verification after movement:

```powershell
python -m pytest tests/test_requested_long_runtime_decomposition.py tests/test_cross_report_analysis_contracts.py tests/test_cross_report_analysis_input_generator.py tests/test_cross_report_analysis_generator.py tests/test_report_analysis_orchestrator_decomposition.py -q
python -m pytest tests/test_pdf_table_heuristics_decomposition.py tests/test_pdf_figures_service/test_table_heuristics.py tests/test_pdf_figures_service/test_pipeline_and_cache.py tests/test_pdf_crop_service.py -q
python -m pytest tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_report_download_service tests/test_browser_report_download_cdp.py tests/test_browser_report_download_http_decomposition.py -q
python -m pytest tests/test_report_store_service.py tests/test_private_api_auto_promotion.py tests/test_report_download_orchestrator.py tests/test_report_download_workflow_decomposition.py -q
python -m ruff check src/contracts/cross_report_analysis.py src/contracts/_cross_report_analysis src/services/_pdf/_table_heuristics src/services/_browser_report_download/_browser_runtime/session_lifecycle.py src/services/_browser_report_download/_browser_runtime/_session_lifecycle src/services/_report_store_service/download_routes.py src/services/_report_store_service/_download_routes tests/test_requested_long_runtime_decomposition.py tests/test_pdf_table_heuristics_decomposition.py tests/test_browser_report_download_runtime_decomposition.py
python -m compileall -q src/contracts/_cross_report_analysis src/services/_pdf/_table_heuristics src/services/_browser_report_download/_browser_runtime/_session_lifecycle src/services/_report_store_service/_download_routes
python scripts/count_long_files.py --min-lines 500
```
