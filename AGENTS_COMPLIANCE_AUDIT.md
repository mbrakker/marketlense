# AGENTS.md Compliance Audit

Date: 2026-02-12  
Scope: `src/` and `tests/` repository architecture and service boundaries.

## Verdict

The codebase is **fully compliant** with the enforced AGENTS.md rules covered by this audit.

## Remediations Completed

1. Service consolidation (PDF stack)
- Consolidated PDF external-system access into a single service module: `src/services/pdf_service.py`.
- Removed split PDF service modules:
  - `src/services/candidate_extraction_service.py`
  - `src/services/crop_service.py`
  - `src/services/preview_service.py`
  - `src/services/figure_service.py`
- Updated generators to consume PDF operations from `pdf_service` only.

2. Service I/O contract enforcement
- Converted non-contract public service APIs to request/response dataclass boundaries:
  - `src/services/logging_service.py::setup_logging(request, ctx) -> LoggingSetupResponse`
  - `src/services/report_analysis_store_service.py::pack_path(request, ctx) -> AnalysisPackPathResponse`
  - `src/services/report_analysis_store_service.py::store_pack(request, ctx) -> AnalysisStorePackResponse`
  - `src/services/schema_validator_service.py::validate_schema(request, ctx) -> SchemaValidateResponse`
  - `src/services/config_service.py::build_ingest_settings(request, ctx) -> IngestSettings`
- Added new contracts:
  - `src/contracts/logging.py`
  - `src/contracts/report_analysis.py`
  - `src/contracts/schema_validation.py`
  - `src/contracts/config.py` (`IngestSettingsBuildRequest`)

3. Call-site migration
- Updated CLI and Streamlit wiring to contract-based logging/config APIs.
- Updated generators/tests to contract-based schema validation and report-analysis store APIs.
- Kept compatibility adapters in generators for injected test doubles while preserving strict service API shape.

## Verification Commands and Results

1. Public service signature audit (request-contract check)
- Command: AST scan over `src/services/*.py` requiring first argument `request` with `*Request` annotation.
- Result: `0` violations.

2. PDF consolidation audit
- Command: `rg -n "import pymupdf as fitz|import pdfplumber|from pypdf" src/services`
- Result: PDF libraries are imported only in `src/services/pdf_service.py`.

3. Compile checks
- Commands:
  - `compileall.compile_dir('src', quiet=1)`
  - `compileall.compile_dir('tests', quiet=1)`
- Result: both passed.

4. Test suite
- Command: `pytest -q`
- Result: `90 passed, 1 deselected` (integration test deselected by `pytest.ini`), no failures.

## Notes

- This audit focuses on the hard architecture/service-boundary violations previously identified and verifies they are now resolved in code and tests.
