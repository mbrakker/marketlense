# Cross-Report Architecture Contracts Scope Fence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. This archived plan records step order only; active backlog tracking belongs in `CONSOLIDATED_TODO.md`.

**Goal:** Establish the cross-report analysis feature as a bounded modular-monolith extension with versioned contracts and explicit generation limits.

**Architecture:** Cross-report analysis remains inside the existing `src/` deployable and reuses current service boundaries for SQLite projections, prompt rendering, model calls, artifact writes, idempotency, and publication. The feature adds one contract module, one input-builder generator, one synthesis generator, one orchestrator, one prompt namespace, and one CLI command without creating a new top-level package, worker, database boundary, WordPress client, or deployable component.

**Tech Stack:** Python dataclasses, YAML config, SQLite through existing analytics store service, existing prompt/LLM/file/idempotency/publish services, pytest, contract schema snapshot gate, architecture import gate.

---

### Task 1: Architecture Scope Fence

**Files:**
- Create: `docs/superpowers/plans/2026-05-21-cross-report-architecture-contracts-scope-fence.md`
- Modify: `README.md`
- Modify: `crossreport.md`

**Step 1: Document exact role boundaries**

Add this plan and a README scope section naming the planned files:

```text
Contracts: src/contracts/cross_report_analysis.py
Services reused: src/services/analytics_store_service.py, src/services/prompt_service.py, src/services/llm_service.py, src/services/file_service.py, src/services/idempotency_service.py
Generators: src/generators/cross_report_analysis_input_generator.py, src/generators/cross_report_analysis_generator.py
Orchestrator: src/orchestrators/cross_report_analysis_orchestrator.py
Prompt namespace: src/prompts/cross_report_analysis/synthesis/
CLI command: python -m src.cli generate-cross-report-analysis
Tests: tests/test_cross_report_analysis_contracts.py, tests/test_config_service.py additions, tests/test_cross_report_analysis_input_generator.py, tests/test_cross_report_analysis_generator.py, tests/test_cross_report_analysis_orchestrator.py, tests/integration/test_analytics_store_cross_report_reads.py
```

**Step 2: Document non-goals**

Add README language stating that the first release does not include metric normalization, new WordPress plugin/post-type dependency, new deployable worker/service/package, a peer analytics database boundary, or global vector retrieval over `vector_projection_queue`.

**Step 3: Remove completed report item**

Remove only `Lock cross-report analysis into the existing modular monolith` from `crossreport.md` after the README and plan are in place.

**Step 4: Verify architecture safety**

Run:

```bash
python scripts/ci/check_architecture_imports.py
python -m src.cli --help
```

Expected: both commands pass. The CLI help run is the live runtime smoke for this documentation-only scope-fence item.

### Task 2: Versioned Contracts

**Files:**
- Create: `src/contracts/cross_report_analysis.py`
- Create: `tests/test_cross_report_analysis_contracts.py`
- Modify: `docs/quality/contract_schemas.json`
- Modify: `README.md`
- Modify: `crossreport.md`

**Step 1: Write failing contract tests**

Add tests that instantiate every cross-report dataclass, assert required fields are populated, round-trip through `dataclasses.asdict`, and assert invalid contract input raises `AppError(code="cross_report_contract_invalid", retryable=False, severity="error")`.

**Step 2: Verify RED**

Run:

```bash
pytest tests/test_cross_report_analysis_contracts.py -q
```

Expected: fail because `src.contracts.cross_report_analysis` is missing.

**Step 3: Add contracts**

Create `src/contracts/cross_report_analysis.py` with versioned dataclasses for:

```text
CrossReportAnalysisRequest
CrossReportThemeCandidate
CrossReportSelectedTheme
CrossReportSourceReportCandidate
CrossReportSelectedSourceReport
CrossReportEvidenceReference
CrossReportSignalScore
CrossReportRawMetricReference
CrossReportAnalysisSection
CrossReportGeneratedAnalysisResult
CrossReportValidationResult
CrossReportPublishRequestSummary
CrossReportPublishResultSummary
CrossReportOrchestratorOutcome
```

Each field must be typed and documented with `field(metadata={"doc": ...})`. Add validation functions that fail closed with typed `AppError` for missing required semantic values.

**Step 4: Verify GREEN**

Run:

```bash
pytest tests/test_cross_report_analysis_contracts.py tests/contracts/test_contract_roundtrip.py -q
python scripts/ci/check_contract_schemas.py --update
python scripts/ci/check_contract_schemas.py
```

Expected: tests pass and the schema snapshot is current.

### Task 3: Bounded Generation YAML Config

**Files:**
- Modify: `src/config/app.yaml`
- Modify: `src/contracts/config.py`
- Modify: `src/services/_config_service/common.py`
- Modify: `src/services/_config_service/app_settings.py`
- Modify: `src/services/_config_service/settings_resolvers.py`
- Create: `src/services/_config_service/cross_report_analysis.py`
- Modify: `tests/test_config_service.py`
- Modify: `README.md`
- Modify: `crossreport.md`

**Step 1: Write failing config tests**

Add tests proving `load_settings` reads `cross_report_analysis` defaults and rejects invalid limits with `AppError(code="cross_report_analysis_config_invalid", retryable=False, severity="error")`.

**Step 2: Verify RED**

Run:

```bash
pytest tests/test_config_service.py -q
```

Expected: fail because the settings fields/resolver do not exist.

**Step 3: Add config contract fields and resolver**

Add `AppSettings` fields for:

```text
cross_report_analysis_enabled
cross_report_analysis_max_source_reports
cross_report_analysis_max_evidence_items
cross_report_analysis_max_prompt_chars
cross_report_analysis_prompt_namespace
cross_report_analysis_model
cross_report_analysis_temperature
cross_report_analysis_timeout_seconds
cross_report_analysis_cache_enabled
cross_report_analysis_auto_theme_enabled
cross_report_analysis_theme_rotation_window_days
cross_report_analysis_min_theme_source_publishers
cross_report_analysis_publish_enabled
cross_report_analysis_publish_requires_validation_pass
```

Load them from `src/config/app.yaml` section `cross_report_analysis`. Invalid positive limits must raise typed non-retryable `AppError` during config loading.

**Step 4: Verify GREEN and live config load**

Run:

```bash
pytest tests/test_config_service.py -q
python -m src.cli config-show
```

Expected: config tests pass and the live CLI config read shows the app config can still be loaded without runtime errors.
