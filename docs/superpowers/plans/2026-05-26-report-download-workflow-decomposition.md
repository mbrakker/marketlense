# Report Download Workflow Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 2,554-line private report-download workflow into focused orchestration capability modules while preserving the public facade, behavior, speed, and provider/Drive cost profile.

**Architecture:** `workflow.py` remains the sole private coordinator behind `report_download_orchestrator.py`. Existing behavior is extracted into private sibling modules for dependencies, candidate readiness, failure forensics, promotion, idempotent persistence, and Drive archival; each module keeps the existing log/event, error, and service-call semantics.

**Tech Stack:** Python dataclasses, pytest, SQLite-backed idempotency/report stores, browser-download service, OpenRouter-backed guarded integration, Ruff/mypy/coverage/mutation CI scripts.

---

### Task 1: Lock Capability Ownership With A Red Structure Test

**Files:**
- Create: `tests/test_report_download_workflow_decomposition.py`
- Verify: `src/orchestrators/_report_download_orchestrator/workflow.py`

- [x] **Step 1: Write the failing ownership test**

```python
from __future__ import annotations

import ast
from pathlib import Path


CAPABILITY_FUNCTIONS = {
    "candidate_readiness.py": {"assert_candidate_download_ready", "evaluate_candidate_download_readiness"},
    "failure_forensics.py": {"persist_failed_attempt_forensics_pack", "with_failure_forensics_context"},
    "promotions.py": {"evaluate_route_playbook_promotion", "evaluate_private_api_playbook_auto_promotion"},
    "persistence.py": {"record_route_outcome", "record_downloaded_source", "record_identity_update"},
    "drive_archive.py": {"archive_successful_report_artifacts", "archive_single_artifact"},
}


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_report_download_workflow_delegates_focused_capabilities() -> None:
    package = Path("src/orchestrators/_report_download_orchestrator")
    coordinator_functions = _function_names(package / "workflow.py")
    assert "run_report_download" in coordinator_functions
    for module_name, expected in CAPABILITY_FUNCTIONS.items():
        owned = _function_names(package / module_name)
        assert expected <= owned
        assert not expected & coordinator_functions
```

- [x] **Step 2: Prove the test is red before extraction**

Run:

```powershell
python -m pytest tests/test_report_download_workflow_decomposition.py -q
```

Expected: failure because the new capability modules do not exist.

### Task 2: Extract Stateless Policy And Evidence Capabilities

**Files:**
- Create: `src/orchestrators/_report_download_orchestrator/dependencies.py`
- Create: `src/orchestrators/_report_download_orchestrator/candidate_readiness.py`
- Create: `src/orchestrators/_report_download_orchestrator/failure_forensics.py`
- Create: `src/orchestrators/_report_download_orchestrator/promotions.py`
- Modify: `src/orchestrators/_report_download_orchestrator/workflow.py`

- [x] **Step 1: Move dependency injection ownership**

Move `ReportDownloadDependencies` and its `default()` construction unchanged
to `dependencies.py`, then re-export it through `workflow.py`:

```python
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
```

- [x] **Step 2: Move candidate readiness**

Move the candidate marker constants and candidate screening functions to
`candidate_readiness.py`, preserving their complete current implementations,
then invoke the extracted operation from `workflow.py`:

```python
from src.orchestrators._report_download_orchestrator.candidate_readiness import (
    assert_candidate_download_ready,
)

assert_candidate_download_ready(
    request=request,
    normalized_url=normalized_url,
    ctx=ctx,
)
```

Replace the coordinator invocation with the explicit
`assert_candidate_download_ready(request=request, normalized_url=normalized_url, ctx=ctx)`
call shown above.

- [x] **Step 3: Move failure forensics**

Move forensic metadata/evidence/package helpers to `failure_forensics.py`
without changing artifact paths, event fields, error codes, or settings:

```python
from src.orchestrators._report_download_orchestrator.failure_forensics import (
    persist_failed_attempt_forensics_pack,
    terminal_evidence_from_error_context,
    with_failure_forensics_context,
)

pack = persist_failed_attempt_forensics_pack(
    exc=exc,
    request=request,
    planned_step=planned_step,
    ctx=ctx,
    dependencies=dependencies,
)
```

- [x] **Step 4: Move browser-route promotions**

Move route-playbook and private-API promotion evaluation to `promotions.py`
without changing skip rules or service invocation conditions:

```python
evaluate_route_playbook_promotion(
    request=request,
    result=result,
    ctx=ctx,
    dependencies=deps,
    route_record_reused=route_record_reused,
)
evaluate_private_api_playbook_auto_promotion(
    request=request,
    result=result,
    ctx=ctx,
    dependencies=deps,
    route_record_reused=route_record_reused,
)
```

- [x] **Step 5: Run the orchestrator tests during extraction**

Run:

```powershell
python -m pytest tests/test_report_download_route_planner.py tests/test_report_download_orchestrator.py -q
```

Expected: all selected tests pass with unchanged behavior.

### Task 3: Extract Idempotent Persistence And Drive Archival

**Files:**
- Create: `src/orchestrators/_report_download_orchestrator/persistence.py`
- Create: `src/orchestrators/_report_download_orchestrator/drive_archive.py`
- Modify: `src/orchestrators/_report_download_orchestrator/workflow.py`

- [x] **Step 1: Extract persistence stages**

Create high-level package-private operations that contain the existing route,
source/value, and identity recording logic:

```python
route_record_reused = record_route_outcome(
    request=request,
    result=result,
    ctx=ctx,
    dependencies=deps,
)
record_downloaded_source(
    request=request,
    result=result,
    policy=policy,
    ctx=ctx,
    dependencies=deps,
)
identity_update = record_identity_update(
    request=request,
    result=result,
    ctx=ctx,
    dependencies=deps,
)
```

`record_route_outcome` returns whether the route record was reused so the
coordinator supplies that same condition to promotion evaluation.

- [x] **Step 2: Extract optional Drive archival**

Move archive behavior and its helper operations unchanged to
`drive_archive.py`, and retain its existing coordinator invocation:

```python
drive_uploads = archive_successful_report_artifacts(
    request=request,
    result=result,
    normalized_url=normalized_url,
    policy=policy,
    ctx=ctx,
    dependencies=deps,
)
```

The module continues to call Drive only when
`request.settings.drive_upload_enabled` is true.

- [x] **Step 3: Reduce coordinator to sequencing**

After route acquisition, call the extracted stages in the existing order:

```python
route_record_reused = record_route_outcome(
    request=request, result=result, ctx=ctx, dependencies=deps
)
evaluate_route_playbook_promotion(
    request=request,
    result=result,
    ctx=ctx,
    dependencies=deps,
    route_record_reused=route_record_reused,
)
evaluate_private_api_playbook_auto_promotion(
    request=request,
    result=result,
    ctx=ctx,
    dependencies=deps,
    route_record_reused=route_record_reused,
)
record_downloaded_source(
    request=request, result=result, policy=policy, ctx=ctx, dependencies=deps
)
identity_update = record_identity_update(
    request=request, result=result, ctx=ctx, dependencies=deps
)
drive_uploads = archive_successful_report_artifacts(
    request=request,
    result=result,
    normalized_url=normalized_url,
    policy=policy,
    ctx=ctx,
    dependencies=deps,
)
```

- [x] **Step 4: Prove structure and behavior are green**

Run:

```powershell
python -m pytest tests/test_report_download_workflow_decomposition.py tests/test_report_download_route_planner.py tests/test_report_download_orchestrator.py -q
```

Expected: all selected tests pass.

### Task 4: Add The Bounded Live Orchestrator Gate

**Files:**
- Create: `tests/integration/test_report_download_orchestrator.py`

- [x] **Step 1: Add a guarded local browser acquisition test**

Implement an integration fixture serving HTML with a JavaScript download
button whose target path does not contain `.pdf`, then invoke
`run_report_download(request, ctx=ctx)` using temporary `reports_db`, state/output paths,
`drive_upload_enabled=False`, and the real default browser service dependency.
Guard it with:

```python
if os.getenv("RUN_REPORT_DOWNLOAD_ORCHESTRATOR_INTEGRATION") != "1":
    pytest.skip("Set RUN_REPORT_DOWNLOAD_ORCHESTRATOR_INTEGRATION=1 to run the live local orchestration integration.")
if not os.getenv("OPENROUTER_API_KEY", "").strip():
    pytest.skip("OPENROUTER_API_KEY is required.")
```

Assert:

```python
assert response.outcome == "downloaded"
assert response.route_kind == "pdf_download"
assert Path(str(response.downloaded_file_path)).exists()
assert response.drive_uploads == []
assert "report_download_start" in event_names
assert "report_download_complete" in event_names
assert_logs_have_required_fields(events)
```

- [x] **Step 2: Keep default CI synthetic**

Run without the live guard:

```powershell
python -m pytest tests/integration/test_report_download_orchestrator.py -q -rs
```

Expected: one skipped guarded live integration test.

### Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `long_scripts.md`
- Modify: `docs/architecture/report-download-workflow-decomposition-review.md`

- [x] **Step 1: Refresh architecture documentation and line audit**

Document the new private orchestrator capability package in `README.md`,
refresh `long_scripts.md` from the existing counting workflow, and add
execution evidence to the architecture review.

- [x] **Step 2: Run affected and full synthetic verification**

Run:

```powershell
python -m pytest tests/test_report_download_workflow_decomposition.py tests/test_report_download_route_planner.py tests/test_report_download_orchestrator.py tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_report_download_service tests/test_browser_report_download_cdp.py -q
python -m pytest -q
```

Expected: all synthetic tests pass; guarded integrations remain deselected or
skipped by default configuration.

- [x] **Step 3: Run repository gates**

Run:

```powershell
python scripts/ci/check_formatting.py
python scripts/ci/check_split_symbol_links.py
python scripts/ci/check_forbidden_patching.py
python scripts/ci/check_repository_hygiene.py
python scripts/ci/run_type_check.py
python -m pytest --cov=src --cov-report=xml --cov-report=term-missing -q
python scripts/ci/check_coverage.py --coverage-xml coverage.xml
python scripts/ci/run_mutation_gate.py --json-out mutation_results.json
python scripts/ci/check_quality_regression.py --baseline docs/quality/baseline_2026-02-21.json --coverage-xml coverage.xml --mutation-json mutation_results.json --docpack-root tests/fixtures/docpacks/golden --candidate-root tests/fixtures/candidate_extraction/golden
```

Expected: all configured gates pass.

- [x] **Step 4: Run the approved bounded live verification**

Load `OPENROUTER_API_KEY`, optional `BROWSER_DOWNLOAD_MODEL`, and optional
`OPENROUTER_HTTP_REFERER` from the local environment without printing their
values, then run:

```powershell
$env:RUN_REPORT_DOWNLOAD_ORCHESTRATOR_INTEGRATION='1'
python -m pytest -m integration tests/integration/test_report_download_orchestrator.py -q -rs
```

Expected: one live integration test passes with a verified downloaded local
PDF and no Drive uploads.
