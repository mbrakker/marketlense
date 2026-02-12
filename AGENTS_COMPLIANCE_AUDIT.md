# AGENTS.md Compliance Audit

Date: 2026-02-11
Scope: `src/` and `tests/` repository structure and representative module checks.

## Verdict

The codebase is **partially compliant**, but **not fully compliant** with the AGENTS.md architecture constitution.

## What is compliant

- Canonical role folders exist under `src/` (`contracts`, `services`, `generators`, `orchestrators`, `utils`, `prompts`).
- Prompt templates are stored in namespaced directories under `src/prompts/` (not centralized in code).
- Most service entry points follow `request dataclass + RunContext` signatures.
- Structured logging helper usage (`log_event`) is widespread across services/generators/orchestrators.

## Violations found

### 1) Service consolidation rule violation (PDF stack split across multiple service modules)

AGENTS.md requires one external system per service module and explicitly warns against splitting PDF handling across multiple service files.

Evidence of PDF external-system logic in multiple services:
- `src/services/pdf_service.py` imports and uses PDF libraries (`pymupdf`, `pypdf`).
- `src/services/candidate_extraction_service.py` imports and uses PDF libraries (`pymupdf`, `pdfplumber`).
- `src/services/crop_service.py` imports and uses `pymupdf`.
- `src/services/preview_service.py` imports and uses `pymupdf`.

Result: **Non-compliant** with strict service consolidation.

### 2) Service I/O contract rule violation (non-request/dataclass public service APIs)

AGENTS.md requires service inputs/outputs as dataclass contracts. Several public service functions accept primitives/non-request arguments instead of `*Request` contracts:

- `src/services/logging_service.py::setup_logging(level: int) -> None`
- `src/services/report_analysis_store_service.py::pack_path(output_dir: str, report_id: str, pack_name: str, ...) -> Path`
- `src/services/report_analysis_store_service.py::store_pack(output_dir: str, report_id: str, pack_name: str, payload: dict, ...) -> str`
- `src/services/schema_validator_service.py::validate_schema(payload: Any, schema_name: str, ...) -> None`
- `src/services/config_service.py::to_ingest_settings(app_settings: AppSettings) -> IngestSettings`

Result: **Non-compliant** with strict service contract policy.

## Commands used for this audit

- `rg --files -g 'AGENTS.md'`
- `rg --files | head -n 200`
- `python - <<'PY' ... (AST scan of service function signatures) ... PY`
- `rg -n "Path\(|open\(|read_text\(|requests\.|http|os\.environ|yaml\.safe_load" src/generators src/orchestrators src/services | head -n 120`
- `sed -n` inspections for representative files:
  - `src/services/report_analysis_store_service.py`
  - `src/services/pdf_service.py`
  - `src/services/candidate_extraction_service.py`
  - `src/services/crop_service.py`
  - `src/services/preview_service.py`
  - `src/services/openai_service.py`
  - `src/generators/taxonomy_generator.py`

## Recommended remediation plan

1. Consolidate PDF external-system operations into a single `pdf_service.py` boundary.
2. Convert non-contract public service APIs to request/response dataclasses.
3. Move helper-only functions that are pure (e.g., path composition) to `utils/` if they are not service boundaries.
4. Add a CI audit check to enforce:
   - public service signatures (`request: *Request, ctx: RunContext`),
   - one-module-per-external-system constraints (at minimum for PDF/OpenAI/VectorStore/WordPress).
