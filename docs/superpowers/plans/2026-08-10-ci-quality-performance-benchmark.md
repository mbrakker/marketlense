# CI Quality Performance Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retain wall-time telemetry for standalone CI quality and regression commands and build one comparable CI benchmark artifact.

**Architecture:** A small command wrapper measures exactly one existing command with a monotonic clock, appending a bounded record to a JSON artifact even on failure. A deterministic builder combines that artifact with the pytest telemetry artifact into one CI benchmark; it marks quality failed when any measured command failed and records zero estimated provider cost because CI uses no live provider calls.

**Tech Stack:** Python standard library, pytest, GitHub Actions YAML.

## Global Constraints

- Do not run any quality gate twice just to measure it.
- Retain only stage name, wall time, exit status, and scalar outcome; never command arguments, provider payloads, or secrets.
- The benchmark must not claim live quality, cost, LLM, or browser measurements that CI did not observe.
- Preserve existing gates and run them in their current order.

---

### Task 1: Standalone-command timing wrapper

**Files:**
- Create: `tests/test_quality_command_telemetry.py`
- Create: `scripts/quality/run_command_with_telemetry.py`

**Interfaces:**
- Produces `main(argv: list[str] | None = None) -> int`.
- CLI: `--output-json <path> --stage <name> -- <command...>`.
- Artifact record: `stage`, `wall_time_ms`, `exit_code`, `outcome`, and `resource_status`.

- [x] **Step 1: Write a failing test** asserting that a successful child Python process produces one bounded timing record and returns zero.
- [x] **Step 2: Run the test** with `python -m pytest tests/test_quality_command_telemetry.py -q`; it failed because the module did not exist.
- [x] **Step 3: Implement the minimal wrapper** using `subprocess.run`, `time.monotonic_ns`, and atomic bounded JSON replacement.
- [x] **Step 4: Rerun the test** and confirm it passes.

### Task 2: Combined CI benchmark builder

**Files:**
- Create: `tests/test_ci_performance_benchmark.py`
- Create: `scripts/quality/build_ci_performance_benchmark.py`
- Modify: `scripts/quality/run_pytest_with_telemetry.py`
- Modify: `tests/test_test_run_telemetry.py`

**Interfaces:**
- Pytest artifact adds `total_run_duration_ms` measured around `pytest.main`.
- Builder CLI: `--test-telemetry <path> --command-telemetry <path> --output-json <path>`.
- Output includes compatible profile hash, total duration, `quality_passed`, zero estimated CI provider cost, test summary, and standalone-stage summaries.

- [x] **Step 1: Write failing tests** for suite wall time and deterministic aggregation of passed command stages.
- [x] **Step 2: Run those tests** and confirm the builder import failed and the old pytest artifact lacked total duration.
- [x] **Step 3: Implement only the required aggregation and wall-time fields.**
- [x] **Step 4: Rerun the tests** and confirm they pass.

### Task 3: CI and documentation wiring

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/quality/benchmarks.md`
- Modify: `docs/ops/monitoring.md`

- [x] **Step 1: Wrap the existing post-pytest quality/regression commands**, preserving their arguments and outputs.
- [x] **Step 2: Build `out/ci_performance_benchmark.json` after the final wrapped command.**
- [x] **Step 3: Upload both command telemetry and the combined benchmark in the existing evidence artifact.**
- [x] **Step 4: Run focused tests, type/lint checks, documentation validation, and a local representative benchmark command.**
