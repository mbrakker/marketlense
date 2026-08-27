# P15 Publish-Readiness Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert retained canonical publish-readiness decisions into deterministic, fail-closed minimum refresh plans that reuse all proven upstream work.

**Architecture:** Keep `publish_readiness.json` as the readiness authority. Add a typed pure classification/refresh-plan contract beside that artifact, translate its invalidation into the existing `MinimalExecutionPlan` and execution-plan audit, and consume the enforced result through the existing report-pipeline checkpoint resume path. No scheduler, provider, browser, or alternate recovery service is introduced.

**Tech Stack:** Python 3, frozen dataclass contracts, JSON Schema, pytest, existing report-store SQLite lineage, report-generation checkpoints.

## Global Constraints

- Use the retained signed `publish_readiness.json` as the only readiness decision source.
- Identical retained inputs and an explicit evaluation timestamp produce an identical refresh plan.
- Missing or unverifiable readiness/lineage must fail closed before reuse or provider construction.
- A readiness-only refresh must run only `render_complete`, with zero acquisition, PDF/OCR, selection, extraction, analysis, model, or browser calls.
- Preserve explicit/manual resume behavior and route all automatic recovery through the existing minimum-execution planner and report pipeline.
- Persist a typed, bounded refresh telemetry JSON artifact and reconcile its execution outcome with the existing execution-plan audit.
- Update the canonical workflow documentation and mark P15 closed only after focused and no-regression verification plus a retained-fixture measurement.

---

### Task 1: Define deterministic readiness classification and refresh telemetry

**Files:**
- Modify: `src/contracts/publish_readiness.py`
- Modify: `src/generators/publish_readiness_generator.py`
- Create: `src/schemas/publish_readiness_refresh_plan.schema.json`
- Test: `tests/test_publish_readiness_refresh.py`

**Interfaces:**
- Consumes: `PublishReadinessArtifact`, current report HTML, current configuration/policy/producer identities, and explicit `evaluated_at_utc`.
- Produces: `PublishReadinessRefreshPlan` with `ready|expiring|stale|failed|incompatible|missing_unverifiable`, reason, invalidated check/artifact, selected resume stage, reuse/regeneration evidence, identities, avoided-work estimates, and execution result.

- [ ] **Step 1: Write failing classifier tests**

```python
def test_expired_passing_readiness_is_stale_and_requests_render_only() -> None:
    plan = plan_publish_readiness_refresh(..., evaluated_at_utc="2026-08-27T12:00:00Z")
    assert plan.previous_readiness_state == "stale"
    assert plan.selected_resume_stage == "analysis_complete"
    assert plan.invalidated_artifact_or_check == "publish_readiness.expired"
```

- [ ] **Step 2: Run classifier tests to verify they fail**

Run: `python -m pytest tests/test_publish_readiness_refresh.py -q`
Expected: FAIL because the refresh planning contract/function does not exist.

- [ ] **Step 3: Implement the pure contract, parser-safe classifier, canonical payload, and schema**

```python
@dataclass(frozen=True)
class PublishReadinessRefreshPlan:
    report_id: str
    previous_readiness_state: str
    reason: str
    invalidated_artifact_or_check: str
    selected_resume_stage: str | None
    reused_stages: list[str]
    regenerated_stages: list[str]
    configuration_hash: str
    policy_hash: str
    producer_revision: str
    execution_result: str = "planned"
```

Classify verified current passing readiness as `ready`; a nearing expiry as `expiring`; expiry or retained staleness conditions as `stale`; failed signed decisions as `failed`; validly parsed but identity/hash/schema/validator mismatches as `incompatible`; and unreadable, absent, malformed, or unverifiable data as `missing_unverifiable`.

- [ ] **Step 4: Run classifier tests to verify they pass**

Run: `python -m pytest tests/test_publish_readiness_refresh.py -q`
Expected: PASS.

### Task 2: Bind non-ready readiness classification to the canonical minimum-execution planner

**Files:**
- Modify: `src/contracts/minimal_execution_plan.py`
- Modify: `src/utils/minimal_execution_planner.py`
- Test: `tests/test_minimal_execution_planner.py`
- Test: `tests/test_publish_readiness_refresh.py`

**Interfaces:**
- Consumes: a classified refresh plan and the observed retained graph.
- Produces: an enforceable existing `MinimalExecutionPlan` whose required stages are render-only when analysis proof is current; otherwise its earliest graph-proven stage; blockers remain terminal/fail-closed.

- [ ] **Step 1: Write failing planner integration tests**

```python
def test_readiness_only_forced_invalidation_reuses_analysis_and_never_requests_models() -> None:
    plan = plan_minimal_execution(replace(_input(intent="render_repair"), forced_invalidations={"rendered_html": "publish_readiness_expired"}))
    assert plan.required_stages == ["render_complete"]
    assert plan.required_external_calls == ["html_render"]
```

- [ ] **Step 2: Run planner tests to verify they fail**

Run: `python -m pytest tests/test_minimal_execution_planner.py tests/test_publish_readiness_refresh.py -q`
Expected: FAIL because readiness invalidations are not yet recognized as render-only.

- [ ] **Step 3: Add the narrow readiness invalidation mapping**

Map proven freshness-only failures to `rendered_html`/`render_repair`; do not map missing evidence to a synthetic safe resume. Preserve dependency propagation so source/crop/analysis incompatibility moves the required stage earlier or produces a blocker.

- [ ] **Step 4: Run planner tests to verify they pass**

Run: `python -m pytest tests/test_minimal_execution_planner.py tests/test_publish_readiness_refresh.py -q`
Expected: PASS.

### Task 3: Consume and persist the automatic plan in the existing ingestion/recovery route

**Files:**
- Modify: `src/orchestrators/ingest_file_orchestrator.py`
- Modify: `src/orchestrators/report_pipeline_orchestrator.py`
- Modify: `src/services/_report_store_service/execution_plan.py`
- Test: `tests/test_report_pipeline_auto_resume.py`
- Test: `tests/test_minimal_execution_enforcement.py`
- Test: `tests/test_publish_readiness_refresh.py`

**Interfaces:**
- Consumes: the retained readiness file, normal report store/lineage observations, and the ordinary ingest dependencies.
- Produces: `<report_analysis>/publish_readiness_refresh_plan.json`, a matched execution-plan audit result, and a refreshed canonical readiness decision; ready packages return without refresh work.

- [ ] **Step 1: Write failing end-to-end unit tests**

```python
def test_stale_readiness_auto_refresh_uses_analysis_checkpoint_without_model_clients(tmp_path) -> None:
    outcome, calls = run_retained_refresh_fixture(tmp_path, readiness="expired")
    assert outcome.publish_readiness_status == "pass"
    assert calls == {"acquisition": 0, "pdf_ocr": 0, "analysis": 0, "model": 0}
```

- [ ] **Step 2: Run the focused integration tests to verify they fail**

Run: `python -m pytest tests/test_report_pipeline_auto_resume.py tests/test_minimal_execution_enforcement.py tests/test_publish_readiness_refresh.py -q`
Expected: FAIL because ingest still hard-codes `analysis_complete` and does not persist refresh telemetry.

- [ ] **Step 3: Implement automatic planning and outcome persistence**

Replace `_existing_publish_readiness_status`'s string-only branch with a read-only typed plan. For `ready`, retain the existing skip. For non-ready, build and record the existing minimum plan in enforce mode; refuse resume when its graph has blockers or its shape lacks an approved checkpoint mapping. Pass the enforced stage and plan to the existing pipeline, then atomically update the refresh telemetry result using measured actual calls/stages/duration and known-or-unpriced avoided cost.

- [ ] **Step 4: Run the focused integration tests to verify they pass**

Run: `python -m pytest tests/test_report_pipeline_auto_resume.py tests/test_minimal_execution_enforcement.py tests/test_publish_readiness_refresh.py -q`
Expected: PASS.

### Task 4: Measure, document, and verify convergence/no-regression

**Files:**
- Create: `tests/test_publish_readiness_refresh_measurement.py`
- Modify: `docs/workflows/validation-and-regeneration.md`
- Modify: `docs/workflows/publishing.md`
- Modify: `docs/architecture/lineage-minimum-regeneration-planner.md`
- Modify: `CONSOLIDATED_TODO.md`

**Interfaces:**
- Consumes: representative retained/fixture readiness cases and their plan telemetry.
- Produces: reproducible before/after counters for calls, tokens, cost, elapsed work, stages, full-regeneration count, successful minimum refreshes, and documented operational behavior.

- [ ] **Step 1: Write a failing measurement/convergence test**

```python
def test_readiness_only_refresh_eliminates_full_regeneration_and_converges() -> None:
    before, after = compare_refresh_fixture()
    assert after.provider_calls == 0
    assert after.full_pipeline_regenerations == 0
    assert after.successful_minimum_refreshes == 1
    assert after.replay_refreshes == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_publish_readiness_refresh_measurement.py -q`
Expected: FAIL until the final telemetry exposes the measured plan result.

- [ ] **Step 3: Complete documentation and P15 evidence**

Document each state, fail-closed condition, resume mapping, artifact path, identity fields, and measurement semantics. Update P15 only with exact successful command/output evidence and remove obsolete descriptions of the untyped readiness retry.

- [ ] **Step 4: Run focused, no-regression, and quality checks**

Run: `python -m pytest tests/test_publish_readiness_refresh.py tests/test_publish_readiness_refresh_measurement.py tests/test_publish_readiness_gate.py tests/test_minimal_execution_planner.py tests/test_minimal_execution_enforcement.py tests/test_report_pipeline_auto_resume.py tests/test_publish_orchestrator.py -q`

Run: `python -m pytest tests/test_ingest_file_orchestrator.py tests/test_publish_readiness_gate.py tests/test_publish_orchestrator.py -q`

Expected: PASS, with no provider/browser calls from fixture cases and a second successful refresh producing no work.
