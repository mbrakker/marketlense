# Step 10C Canary State Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the Step 10C/A21 live canary from reading or writing mutable state outside its explicit isolated run root.

**Architecture:** Add an explicit optional isolation-root setting to the typed application and ingest settings. The pipeline preflight will validate every mutable run-store path against that root before any provider client is constructed. The A21 profile will bind all mutable databases and accounting ledgers to its one run root while leaving immutable source fixtures and static configuration outside it.

**Tech Stack:** Python 3, dataclasses, PyYAML configuration, pytest, SQLite.

## Global Constraints

- Do not run a live canary until this change is verified.
- Do not modify or delete historical P6/P7 usage ledgers.
- Preserve reusable immutable source fixtures; do not reuse derived canary state.
- Reject out-of-root mutable state during preflight before provider I/O.
- Keep the 20-report cohort out of scope.

---

### Task 1: Define and prove the isolation contract

**Files:**

- Modify: `tests/test_config_runtime_path_resolution.py`
- Modify: `src/contracts/config.py`
- Modify: `src/contracts/ingest.py`
- Modify: `src/services/_config_service/paths.py`
- Modify: `src/services/_config_service/app_settings.py`

**Interfaces:**

- Consumes: `paths.canary_state_root` from an operator profile.
- Produces: `AppSettings.canary_state_root` and `IngestSettings.canary_state_root`, both absolute paths or empty strings.

- [ ] **Step 1: Write the failing profile-resolution test**

```python
def test_a21_profile_resolves_every_mutable_store_beneath_canary_state_root() -> None:
    # Load base app.yaml with MARKET_LENSE_CONFIG_PROFILE=a21canary in a subprocess.
    # Assert usage_db_path, state_db, reports_db, signal_store_db, ingest_lock_path,
    # cost ledger/daily paths, and output/cache paths are below canary_state_root.
    ...
```

- [ ] **Step 2: Run the test to verify the current profile fails**

Run: `python -m pytest -q tests/test_config_runtime_path_resolution.py -k a21_profile`

Expected: FAIL because `usage_db_path` resolves to the retained shared P6 ledger.

- [ ] **Step 3: Add the smallest typed configuration plumbing**

```python
# paths resolver
resolved["canary_state_root"] = _resolve_optional_path(
    paths_cfg.get("canary_state_root"), base_path=runtime_base_path
)
```

Add the same field to `AppSettings` and `IngestSettings`; `build_ingest_settings`
already copies shared dataclass fields by name.

- [ ] **Step 4: Run the profile-resolution test**

Run: `python -m pytest -q tests/test_config_runtime_path_resolution.py -k a21_profile`

Expected: PASS after the A21 profile is updated in Task 3.

### Task 2: Fail preflight before provider construction

**Files:**

- Modify: `tests/test_pipeline_preflight_orchestrator.py`
- Modify: `src/orchestrators/pipeline_preflight_orchestrator.py`

**Interfaces:**

- Consumes: `settings.canary_state_root` and the resolved mutable paths.
- Produces: a blocking `PipelinePreflightCheck` with code `canary_mutable_state_outside_root` when any mutable path escapes the root.

- [ ] **Step 1: Write the failing preflight test**

```python
def test_pipeline_preflight_blocks_canary_usage_ledger_outside_isolation_root(...) -> None:
    settings = replace(
        ingest_settings,
        canary_state_root=str(tmp_path / "canary"),
        usage_db_path=str(tmp_path / "historical" / "llm_usage.sqlite"),
    )
    report = run_pipeline_preflight(...)
    assert report.blockers[0].code == "canary_mutable_state_outside_root"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests/test_pipeline_preflight_orchestrator.py -k canary_usage_ledger_outside_isolation_root`

Expected: FAIL because the existing preflight checks only writability.

- [ ] **Step 3: Add a deterministic root-containment check**

```python
def _check_canary_mutable_state_root(request: PipelinePreflightRequest) -> list[PipelinePreflightCheck]:
    # For a non-empty root, resolve every configured mutable path and reject
    # the first path that is not relative to the resolved root.
    ...
```

Run it before LLM checks, prompt loading, or any optional live endpoint probe.

- [ ] **Step 4: Run the focused preflight tests**

Run: `python -m pytest -q tests/test_pipeline_preflight_orchestrator.py -k "canary_usage_ledger_outside_isolation_root or blocks_missing_credential_before_side_effects"`

Expected: PASS.

### Task 3: Bind the A21 profile and operator documentation

**Files:**

- Modify: `src/config/app.a21canary.yaml`
- Modify: `docs/ops/configuration.md`

**Interfaces:**

- Consumes: the typed root-containment preflight from Task 2.
- Produces: an A21 profile whose mutable run state is entirely under `tmp/a21_canary_isolated4_af16661c`.

- [ ] **Step 1: Set the explicit A21 root and all mutable paths**

```yaml
paths:
  canary_state_root: "./tmp/a21_canary_isolated4_af16661c"
cost:
  usage_db_path: "./tmp/a21_canary_isolated4_af16661c/llm_usage.sqlite"
```

Also bind cost daily/ledger, analysis ledger, and publication-projection ledgers to
the same root. Preserve the profile's existing output/cache/database paths.

- [ ] **Step 2: Document the fail-closed constraint**

State that an isolated canary profile must declare `paths.canary_state_root` and
place all mutable state stores below it; fixtures and static mappings remain
immutable external inputs.

- [ ] **Step 3: Validate YAML and configuration loading**

Run: `python -m pytest -q tests/test_config_runtime_path_resolution.py -k a21_profile`

Expected: PASS, with a fresh, empty usage-ledger path below the A21 root.

### Task 4: Verify the safety gate without live execution

**Files:**

- Test: `tests/test_config_runtime_path_resolution.py`
- Test: `tests/test_pipeline_preflight_orchestrator.py`
- Test: `tests/test_validation_queue_lineage.py`

- [ ] **Step 1: Run the new focused tests**

Run: `python -m pytest -q tests/test_config_runtime_path_resolution.py tests/test_pipeline_preflight_orchestrator.py -k "a21_profile or canary_usage_ledger_outside_isolation_root"`

Expected: PASS.

- [ ] **Step 2: Run the mandatory deterministic A21 full-chain gate**

Run: `python -m pytest -q tests/test_validation_queue_lineage.py -k "a21_full_chain"`

Expected: PASS with no live provider or publication call.

- [ ] **Step 3: Run the applicable fast CI gate and inspect the diff**

Run: `python -m pytest -q tests/test_config_runtime_path_resolution.py tests/test_pipeline_preflight_orchestrator.py tests/test_validation_queue_lineage.py`

Expected: PASS. Inspect `git diff --check` and `git diff --name-only` for only the files above.

## Self-Review

- Spec coverage: Tasks 1 and 3 isolate profile paths; Task 2 blocks an escaped path before provider I/O; Task 4 proves deterministic A21 compatibility without starting the live canary or cohort.
- Placeholder scan: no deferred implementation steps or unspecified interfaces remain.
- Type consistency: `canary_state_root` is named identically in configuration, `AppSettings`, `IngestSettings`, profile tests, and preflight.
