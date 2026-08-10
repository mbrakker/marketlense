# End-to-End Performance Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist authoritative, bounded performance telemetry for every pipeline stage and make comparable test, CI, and live-run baselines prove speed improvements without a quality or cost regression.

**Architecture:** Add one typed performance-telemetry boundary backed by the existing canonical state database; it records scalar spans and capacity samples, never prompts, source text, browser payloads, or raw provider responses. Queue workers, validation-manifest stages, LLM calls, browser routes, cache decisions, and SQLite transaction boundaries contribute to the same span ID. Deterministic rollups create immutable run artifacts and compare only compatible cohorts, configurations, policies, code revisions, and measurement profiles.

**Tech Stack:** Python 3.12, SQLite, typed frozen dataclass contracts, canonical state/report stores, LLM usage ledger, browser acquisition service, pytest, GitHub Actions, JSON artifacts.

## Global Constraints

- Persist scalar timing/resource facts in the canonical state database; do not introduce a second telemetry database, metrics daemon, queue, or external observability provider.
- Measure in-process elapsed durations with `time.monotonic_ns()`. Calculate cross-process queue wait and whole-run duration from persisted, millisecond-precision UTC timestamps; reject invalid ordering rather than producing a negative duration.
- A missing measurement is `unavailable`, never `0`; a measurement that does not apply is `not_applicable`, never omitted or inferred.
- Standard logs and retained artifacts contain only bounded IDs, hashes, counters, durations, configuration/policy/build identities, and status; they must not retain credentials, URLs with secrets, prompts, source text, DOMs, screenshots, model responses, or SQL values.
- A stage is the existing named workflow/validation stage; do not create new orchestration stages solely for telemetry.
- Services own timing around their external I/O and database transactions. Orchestrators own only stage/attempt lifecycle correlation and must not reimplement service timing.
- Cache data comes from the cache-owning service at the hit/miss decision. Do not reconstruct cache rates by parsing logs.
- A baseline comparison is valid only when `measurement_profile_hash`, fixture/cohort hash, configuration hash, policy hash, producer build identity, stage name, and applicable platform/runtime dimensions match. Incompatible runs are reported as incomparable.
- A claimed speed improvement requires: a lower total p50 or required-stage p50 than the matched baseline, no exceeded performance tolerance, no quality-gate regression, and no cost regression. A partial or unavailable metric cannot prove an improvement.
- Tests use injected clocks and public service boundaries; pytest monkeypatching and private-helper replacement remain forbidden.
- Every code task updates its corresponding tests and the canonical documentation pack in the same change.

---

## Measurement Contract

The implementation uses the following exact terms and units.

| Field | Meaning | Source of truth |
| --- | --- | --- |
| `queue_wait_ms` | UTC elapsed time from the latest durable enqueue/availability timestamp to successful claim; records `not_applicable` for direct runs. Retry wait is represented by the next attempt’s queue wait, not added to an earlier attempt. | Workflow queue timestamps plus claim-time UTC capture. |
| `wall_time_ms` | Monotonic time from stage start to terminal success/failure. It includes all child work and does not double-count queue wait. | Worker and direct-stage lifecycle. |
| `db_wait_ms` | Time blocked acquiring a SQLite transaction/connection, including `BEGIN IMMEDIATE`, accumulated per span and database role. It excludes SQL execution time after the transaction begins. | Canonical state/report/usage-store transaction wrappers. |
| `llm_latency_ms` | Monotonic duration from immediately before a provider request to response/error receipt, excluding prompt rendering and ledger persistence. | Canonical LLM service. |
| `browser_latency_ms` | Monotonic duration of a browser-runtime or browser HTTP operation, including browser launch only when that operation launches it. | Browser acquisition service/runtime. |
| `cache_hits` / `cache_misses` | Explicit counts emitted by cache-owning code, scoped by cache family. `unknown` is retained when the current route does not expose a decision. | Cache-owning service or deterministic cache helper. |
| `worker_utilisation` | For a queue/window, the union of successful running-attempt intervals divided by `configured_worker_concurrency × window_duration`; reported as `0.0`–`1.0` and `unavailable` if either denominator is unknown. It is capacity utilisation, not CPU usage. | Durable queue attempts and queue control snapshot. |
| `total_run_duration_ms` | UTC elapsed time from immutable run-manifest creation to final terminal closure. It is not the sum of stage times and therefore remains correct under parallelism. | Run lifecycle span. |

Every scalar uses integer milliseconds or an integer count except cost (`decimal-string USD in contracts, rounded only for presentation`) and utilisation (`decimal fraction`). The retained detail identifies the measurement status for each metric: `observed`, `not_applicable`, or `unavailable`.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/contracts/performance_telemetry.py` | Versioned span, resource-counter, utilisation, rollup, baseline, and comparison contracts. |
| `src/services/performance_telemetry_service.py` | Canonical public persistence/query/rollup facade for telemetry stored in the state database. |
| `src/services/_performance_telemetry_service/schema.py` | Bounded SQLite schema, migrations, invariant validation, and aggregate queries behind the facade. |
| `src/services/_state_service/common.py` | Optional public, dependency-injected transaction timing hook used by existing state-store clients without changing their business semantics. |
| `src/services/_report_store_service/connection.py` | Equivalent report-store transaction timing hook. |
| `src/services/llm_usage_ledger_service.py` | Retains `telemetry_span_id`, provider latency, and usage-cache outcome beside the existing LLM accounting event. |
| `src/services/_llm_service/` | Captures provider-request latency at the canonical LLM boundary and forwards it to existing accounting. |
| `src/services/browser_report_download_service.py` and `src/services/_browser_report_download/` | Emits browser-operation latency and cache decisions through the telemetry service. |
| `src/orchestrators/workflow_worker_orchestrator.py` | Opens/closes a queue-attempt stage span and records claim/worker-control context. |
| `src/services/_workflow_queue_service/submission.py` | Persists the precise queued/available timestamp and establishes the queued stage-span correlation. |
| `src/orchestrators/ingest_orchestrator.py`, `src/orchestrators/publish_orchestrator.py`, `src/orchestrators/_report_analysis_orchestrator/manifest.py` | Correlate existing direct validation-manifest stage records to stage spans; no new workflow branches. |
| `src/services/validation_reliability_service.py` and `src/contracts/validation_reliability.py` | Build the performance section of the existing immutable validation-run artifact from persisted spans and current reliability/accounting data. |
| `scripts/quality/performance_telemetry_baseline.py` | Creates and compares deterministic baseline artifacts; rejects incomparable inputs and quality/cost regression. |
| `scripts/ci/check_performance_telemetry_regression.py` | Runs the retained fixture comparison and writes a CI artifact without modifying a committed baseline. |
| `.github/workflows/ci.yml` | Runs and uploads the performance telemetry gate after existing quality and prompt-fixture gates. |
| `docs/quality/benchmarks.md`, `docs/quality/non-regression-policy.md`, `docs/ops/monitoring.md`, `docs/quality/evidence.md` | Define baseline/gate semantics, operators’ live-run procedure, and retained evidence surface. |
| `tests/test_performance_telemetry_service.py`, `tests/test_workflow_worker_performance_telemetry.py`, `tests/test_llm_performance_telemetry.py`, `tests/test_browser_performance_telemetry.py`, `tests/test_validation_reliability_performance.py`, `tests/test_performance_telemetry_baseline.py` | Observable persistence, aggregation, attribution, comparison, and redaction behavior. |

### Task 1: Define the typed, bounded telemetry contract

**Files:**

- Create: `src/contracts/performance_telemetry.py`
- Modify: `src/contracts/llm_usage.py`
- Test: `tests/test_performance_telemetry_service.py`
- Test: `tests/test_llm_usage_ledger_service.py`

**Interfaces:**

- Consumes: `RunContext`, existing LLM usage entries, queue attempt IDs, validation-run IDs, and existing semantic identifiers.
- Produces: `PerformanceTelemetrySpan`, `PerformanceTelemetryMeasurement`, `PerformanceTelemetryRunArtifact`, and `PerformanceBaselineComparison` with schema version `1.0`.

- [ ] **Step 1: Write failing contract and validation tests.**

```python
def test_span_rejects_content_and_accepts_only_bounded_scalar_attributes() -> None:
    span = PerformanceTelemetrySpan(
        schema_version="1.0",
        span_id="span-1",
        run_id="run-1",
        stage="report_analysis",
        status="running",
        measurement_profile_hash="profile-hash",
    )
    assert span.stage == "report_analysis"

    with pytest.raises(AppError, match="performance_telemetry_attribute_invalid"):
        PerformanceTelemetryMeasurement(
            schema_version="1.0", span_id="span-1", metric="llm_latency_ms",
            status="observed", integer_value=10, attributes={"prompt": "secret text"},
        )
```

- [ ] **Step 2: Run the focused tests and confirm that the contracts do not yet exist.**

Run: `python -m pytest tests/test_performance_telemetry_service.py tests/test_llm_usage_ledger_service.py -q`

Expected: FAIL because `src.contracts.performance_telemetry` is absent and `LLMUsageLedgerEntry` lacks the telemetry fields.

- [ ] **Step 3: Add frozen contracts with explicit statuses and bounded fields.**

```python
MeasurementStatus = Literal["observed", "not_applicable", "unavailable"]

@dataclass(frozen=True)
class PerformanceTelemetryMeasurement:
    schema_version: str
    span_id: str
    metric: str
    status: MeasurementStatus
    integer_value: int | None = None
    decimal_value: str = ""
    cache_family: str = ""
    database_role: str = ""
```

Require exactly one numeric value only when `status == "observed"`; reject negative values, unregistered metric names, and attributes that exceed a small scalar allowlist. Add `telemetry_span_id: str = ""` and `provider_latency_ms: int | None = None` to `LLMUsageLedgerEntry`, preserving blank/`None` for historical events.

- [ ] **Step 4: Run the focused tests and schema generation gate.**

Run: `python -m pytest tests/test_performance_telemetry_service.py tests/test_llm_usage_ledger_service.py -q`

Expected: PASS with tests for `observed`, `not_applicable`, `unavailable`, invalid values, bounded attributes, and legacy blank ledger compatibility.

Run: `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json`

Expected: FAIL only because the committed snapshot needs an intentional refresh in Task 6.

- [ ] **Step 5: Commit the contract slice.**

```powershell
git add src/contracts/performance_telemetry.py src/contracts/llm_usage.py tests/test_performance_telemetry_service.py tests/test_llm_usage_ledger_service.py
git commit -m "feat: define bounded performance telemetry contracts"
```

### Task 2: Persist idempotent spans and derive utilisation

**Files:**

- Create: `src/services/performance_telemetry_service.py`
- Create: `src/services/_performance_telemetry_service/__init__.py`
- Create: `src/services/_performance_telemetry_service/schema.py`
- Modify: `src/services/_sqlite_migration/state.py`
- Test: `tests/test_performance_telemetry_service.py`

**Interfaces:**

- Consumes: `RecordPerformanceTelemetrySpanRequest`, `RecordPerformanceTelemetryMeasurementRequest`, `RunContext`, and the configured state database path.
- Produces: `record_performance_span(request, ctx)`, `record_performance_measurement(request, ctx)`, and `build_performance_run_artifact(request, ctx)` public service functions.

- [ ] **Step 1: Write failing persistence and aggregation tests using a temporary state database.**

```python
def test_rollup_uses_union_of_worker_attempt_intervals(tmp_path) -> None:
    # Two overlapping attempts on a queue with concurrency two occupy 1000 ms of
    # total slot capacity during a 1000 ms window, not 2000 ms of one slot.
    artifact = build_performance_run_artifact(_request(tmp_path, "run-1"), _ctx())
    queue = artifact.queue_summaries[0]
    assert queue.worker_utilisation == "1.000000"
    assert artifact.total_run_duration_ms == 1000
```

- [ ] **Step 2: Run the focused test and confirm it fails.**

Run: `python -m pytest tests/test_performance_telemetry_service.py -q`

Expected: FAIL because the public telemetry service and state migration do not exist.

- [ ] **Step 3: Add one state-database migration and idempotent scalar persistence.**

Create `performance_telemetry_spans`, `performance_telemetry_measurements`, and `performance_worker_capacity_samples` in the canonical state schema. Index by `(run_id, stage, completed_at_utc)`, `(span_id, metric)`, and `(queue_name, observed_at_utc)`. Use `(span_id, metric, cache_family, database_role)` as the measurement uniqueness key, make duplicate writes converge only when all values match, and reject conflicting retries with `performance_telemetry_conflict`.

```python
def record_performance_measurement(
    request: RecordPerformanceTelemetryMeasurementRequest, ctx: RunContext
) -> PerformanceTelemetryMeasurementResponse:
    """Persist one scalar, idempotent metric for a known telemetry span."""
```

The rollup must calculate p50/p95 from complete observed spans only, retain sample counts and measurement statuses, and calculate utilisation from clipped interval union—not a sum that can exceed one.

- [ ] **Step 4: Run service tests.**

Run: `python -m pytest tests/test_performance_telemetry_service.py -q`

Expected: PASS for idempotent retry, conflicting retry, missing-value status, percentile/sample-count behavior, interval-union utilisation, and no retained content fields.

- [ ] **Step 5: Commit the persistence slice.**

```powershell
git add src/services/performance_telemetry_service.py src/services/_performance_telemetry_service src/services/_sqlite_migration/state.py tests/test_performance_telemetry_service.py
git commit -m "feat: persist canonical performance telemetry"
```

### Task 3: Instrument stage lifecycle, queue wait, and database wait

**Files:**

- Modify: `src/orchestrators/workflow_worker_orchestrator.py`
- Modify: `src/services/_workflow_queue_service/submission.py`
- Modify: `src/services/_workflow_queue_service/leasing.py`
- Modify: `src/services/_state_service/common.py`
- Modify: `src/services/_report_store_service/connection.py`
- Modify: `src/orchestrators/ingest_orchestrator.py`
- Modify: `src/orchestrators/publish_orchestrator.py`
- Modify: `src/orchestrators/_report_analysis_orchestrator/manifest.py`
- Test: `tests/test_workflow_worker_performance_telemetry.py`
- Test: `tests/test_validation_run_manifest.py`

**Interfaces:**

- Consumes: durable queue timestamps, `WorkflowJobAttempt`, direct-stage validation records, and a span ID propagated in `RunContext` metadata.
- Produces: one `wall_time_ms` span per queue/direct stage attempt, queue wait on queued attempts, database wait measurements by database role, and a stage-record-to-span reference.

- [ ] **Step 1: Write failing worker and direct-manifest tests.**

```python
def test_worker_persists_queue_wait_and_wall_time_without_including_wait(tmp_path) -> None:
    result = run_workflow_worker_once(
        state_db=str(tmp_path / "state.sqlite"), queue_name="report_analysis",
        worker_id="worker-a", ctx=_ctx(), now_utc="2026-08-10T10:00:05+00:00",
    )
    span = _only_span(tmp_path, result.claimed_job_id)
    assert span.measurement("queue_wait_ms").integer_value == 5000
    assert span.measurement("wall_time_ms").integer_value >= 0
```

- [ ] **Step 2: Run the focused tests and confirm they fail.**

Run: `python -m pytest tests/test_workflow_worker_performance_telemetry.py tests/test_validation_run_manifest.py -q`

Expected: FAIL because queue/direct lifecycle telemetry is absent.

- [ ] **Step 3: Add one explicit lifecycle correlation path.**

At submission, persist a queued-span correlation with millisecond-precision `queued_at_utc` and `available_at_utc`. At successful claim, calculate `queue_wait_ms` as `claim_at_utc - max(queued_at_utc, available_at_utc)` only when the timestamps are valid; otherwise write `unavailable`. Immediately before handler execution capture `started_monotonic_ns`; close the same span in every success and failure path using paired monotonic readings for `wall_time_ms`. Write the bounded span ID into the existing queue attempt metadata and add `telemetry_span_id` to `ValidationRunManifestStageRecord` through an additive reports migration.

Inject an optional `TelemetryTransactionObserver` into canonical state/report connection helpers. It measures only acquisition of a connection/transaction and reports a `db_wait_ms` measurement using the current context span. It must be a no-op when a context has no telemetry span, must not alter transaction/retry behavior, and must not time individual SQL statements.

- [ ] **Step 4: Run focused tests.**

Run: `python -m pytest tests/test_workflow_worker_performance_telemetry.py tests/test_validation_run_manifest.py tests/test_workflow_queue_service.py -q`

Expected: PASS, including success/failure closure, direct-stage correlation, one queue-wait metric per queued attempt, direct-run `not_applicable`, and explicit database-wait unavailability where no observer is supplied.

- [ ] **Step 5: Commit the lifecycle slice.**

```powershell
git add src/orchestrators/workflow_worker_orchestrator.py src/services/_workflow_queue_service/submission.py src/services/_workflow_queue_service/leasing.py src/services/_state_service/common.py src/services/_report_store_service/connection.py src/orchestrators/ingest_orchestrator.py src/orchestrators/publish_orchestrator.py src/orchestrators/_report_analysis_orchestrator/manifest.py tests/test_workflow_worker_performance_telemetry.py tests/test_validation_run_manifest.py
git commit -m "feat: record stage, queue, and database timing"
```

### Task 4: Instrument LLM, browser, and cache-owned boundaries

**Files:**

- Modify: `src/services/_llm_service/`
- Modify: `src/services/llm_usage_ledger_service.py`
- Modify: `src/services/browser_report_download_service.py`
- Modify: `src/services/_browser_report_download/`
- Modify: `src/orchestrators/_report_download_orchestrator/resource_telemetry.py`
- Test: `tests/test_llm_performance_telemetry.py`
- Test: `tests/test_browser_performance_telemetry.py`
- Test: `tests/test_acquisition_resource_telemetry.py`

**Interfaces:**

- Consumes: current telemetry span from `RunContext`, existing provider accounting request, browser route result, and existing cache-decision locations.
- Produces: per-call `llm_latency_ms`, per-operation `browser_latency_ms`, cache hit/miss counters by family, and existing ledger/acquisition records with compatible additive fields.

- [ ] **Step 1: Write failing public-boundary tests with deterministic fake providers/runtime.**

```python
def test_llm_latency_excludes_ledger_write_and_keeps_cache_decision(tmp_path) -> None:
    response = invoke_llm_with_fake_provider(_request(tmp_path, span_id="span-1"))
    event = _only_usage_event(tmp_path)
    assert event.telemetry_span_id == "span-1"
    assert event.provider_latency_ms == 17
    assert event.cache_decision == "semantic_hit"
```

```python
def test_browser_cache_hit_records_no_browser_latency_as_not_applicable(tmp_path) -> None:
    result = download_report(_cached_request(tmp_path, span_id="span-1"))
    assert result.cache_hit is True
    assert _measurement(tmp_path, "span-1", "browser_latency_ms").status == "not_applicable"
```

- [ ] **Step 2: Run the focused tests and confirm they fail.**

Run: `python -m pytest tests/test_llm_performance_telemetry.py tests/test_browser_performance_telemetry.py tests/test_acquisition_resource_telemetry.py -q`

Expected: FAIL because latency and cache counters are not persisted at their owning boundaries.

- [ ] **Step 3: Capture measurements at the canonical ownership point.**

Wrap only the outbound provider request in paired monotonic reads, then persist the resulting duration with the existing ledger event. At every existing semantic/PDF/artifact/browser cache decision, send one hit/miss increment with the established cache-family name; do not add duplicate events at callers. Wrap browser launch/navigation/route execution in the browser service and record separate scalar browser latencies; direct HTTP acquisition remains `not_applicable` for browser latency. Extend acquisition summaries only with aggregate references/counts that are already observed, leaving their `incomplete_fields` semantics intact.

- [ ] **Step 4: Run focused boundary tests.**

Run: `python -m pytest tests/test_llm_performance_telemetry.py tests/test_browser_performance_telemetry.py tests/test_acquisition_resource_telemetry.py tests/test_llm_usage_ledger_service.py -q`

Expected: PASS for success/error provider timing, semantic and provider cache decisions, browser launch/navigation timing, direct/cache-hit non-applicability, and bounded records.

- [ ] **Step 5: Commit the external-boundary slice.**

```powershell
git add src/services/_llm_service src/services/llm_usage_ledger_service.py src/services/browser_report_download_service.py src/services/_browser_report_download src/orchestrators/_report_download_orchestrator/resource_telemetry.py tests/test_llm_performance_telemetry.py tests/test_browser_performance_telemetry.py tests/test_acquisition_resource_telemetry.py
git commit -m "feat: capture LLM browser and cache telemetry"
```

### Task 5: Build immutable run artifacts and enforce baseline comparison

**Files:**

- Modify: `src/contracts/validation_reliability.py`
- Modify: `src/services/validation_reliability_service.py`
- Create: `scripts/quality/performance_telemetry_baseline.py`
- Create: `scripts/ci/check_performance_telemetry_regression.py`
- Create: `docs/quality/performance_telemetry_baseline.json`
- Test: `tests/test_validation_reliability_performance.py`
- Test: `tests/test_performance_telemetry_baseline.py`

**Interfaces:**

- Consumes: immutable validation manifest, canonical LLM ledger, persisted telemetry spans, existing quality artifacts, and a committed fixture baseline.
- Produces: `performance` in `reliability_telemetry.json`, a versioned CI fixture baseline, and a non-zero exit code for comparable performance, quality, or cost regression.

- [ ] **Step 1: Write failing artifact and comparator tests.**

```python
def test_comparator_rejects_faster_run_when_quality_or_cost_regresses() -> None:
    comparison = compare_baseline(
        baseline=_artifact(total_ms=1000, quality_passed=True, cost="0.10"),
        candidate=_artifact(total_ms=800, quality_passed=False, cost="0.11"),
    )
    assert comparison.speed_improvement_proven is False
    assert set(comparison.blocking_reasons) == {"quality_regression", "cost_regression"}
```

- [ ] **Step 2: Run the focused tests and confirm they fail.**

Run: `python -m pytest tests/test_validation_reliability_performance.py tests/test_performance_telemetry_baseline.py -q`

Expected: FAIL because the reliability artifact and comparator have no performance section.

- [ ] **Step 3: Derive a deterministic artifact without duplicating runtime state.**

Add a `performance` section to `ValidationReliabilityArtifact` that carries run identity, compatibility dimensions, total duration, per-stage p50/p95/sample count/statuses, queue summaries, LLM/browser totals, cache counts, worker utilisation, total tokens, estimated cost, and references/hashes for the existing quality artifacts. Build it from persisted state and ledger records only; retain `partial`/`unavailable` rather than substituting zero. Hash the final artifact as existing reliability telemetry does.

Create a comparator that requires exact compatibility dimensions, uses the existing prompt-fixture jitter tolerance for deterministic CI timing, sets explicit required stage thresholds in `performance_telemetry_baseline.json`, and requires candidate quality/cost values to be no worse than the baseline. The committed baseline contains only fixture data and scalar metrics; it is never a live-production baseline.

- [ ] **Step 4: Run artifact and comparator tests.**

Run: `python -m pytest tests/test_validation_reliability_performance.py tests/test_performance_telemetry_baseline.py -q`

Expected: PASS for full/partial artifacts, incompatible cohorts, unavailable metrics, lower p50 proof, non-regression quality/cost requirements, and bounded baseline serialization.

- [ ] **Step 5: Commit the comparison slice.**

```powershell
git add src/contracts/validation_reliability.py src/services/validation_reliability_service.py scripts/quality/performance_telemetry_baseline.py scripts/ci/check_performance_telemetry_regression.py docs/quality/performance_telemetry_baseline.json tests/test_validation_reliability_performance.py tests/test_performance_telemetry_baseline.py
git commit -m "feat: compare end-to-end performance baselines"
```

### Task 6: Add CI evidence, documentation, and contract inventory

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `docs/quality/benchmarks.md`
- Modify: `docs/quality/non-regression-policy.md`
- Modify: `docs/ops/monitoring.md`
- Modify: `docs/quality/evidence.md`
- Modify: `docs/quality/contract_schemas.json`
- Test: `tests/test_performance_telemetry_baseline.py`

**Interfaces:**

- Consumes: current fixture corpus, committed baseline, existing prompt-fixture quality/cost results, and generated telemetry artifact.
- Produces: a CI comparison artifact uploaded with release evidence and an operator procedure for matched live before/after runs.

- [ ] **Step 1: Write failing CLI/gate tests.**

```python
def test_ci_gate_writes_comparison_and_rejects_incomparable_inputs(tmp_path) -> None:
    exit_code = main([
        "--baseline", str(tmp_path / "baseline.json"),
        "--current", str(tmp_path / "current.json"),
        "--output-json", str(tmp_path / "comparison.json"),
    ])
    assert exit_code == 1
    assert json.loads((tmp_path / "comparison.json").read_text())["status"] == "incomparable"
```

- [ ] **Step 2: Run the gate test and confirm it fails.**

Run: `python -m pytest tests/test_performance_telemetry_baseline.py -q`

Expected: FAIL until the CI command and comparison artifact are implemented.

- [ ] **Step 3: Wire the CI gate after its source quality/cost evidence exists.**

Run the performance gate after the prompt fixture corpus regression gate and pass the same fixed iteration count/profile. Upload `out/performance_telemetry_ci.json` and `out/performance_telemetry_comparison_ci.json` beside the existing release-evidence artifacts. Do not make a live provider call or write to WordPress in CI.

Document these operator commands, replacing the placeholders only at execution time:

```powershell
python scripts/quality/performance_telemetry_baseline.py build `
  --validation-run-id <baseline-run-id> --state-db state/market_lense_state.sqlite `
  --reports-db state/reports.sqlite --usage-db state/llm_usage.sqlite `
  --output-json out/performance-baseline.json
python scripts/quality/performance_telemetry_baseline.py compare `
  --baseline-json out/performance-baseline.json --candidate-json out/performance-after.json `
  --output-json out/performance-comparison.json
```

The documentation must state that a live comparison requires one frozen cohort, the same profile and identities, a completed validation-manifest audit, current quality gate artifacts, and no live publication unless separately authorized.

- [ ] **Step 4: Regenerate and verify documentation/contract inventories.**

Run: `python scripts/docs/generate_references.py`

Run: `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json`

Run: `python scripts/ci/check_documentation.py --check-generated`

Expected: PASS with the schema snapshot and generated references deliberately refreshed.

- [ ] **Step 5: Commit the CI and documentation slice.**

```powershell
git add .github/workflows/ci.yml docs/quality/benchmarks.md docs/quality/non-regression-policy.md docs/ops/monitoring.md docs/quality/evidence.md docs/quality/contract_schemas.json docs/generated tests/test_performance_telemetry_baseline.py
git commit -m "ci: enforce performance telemetry regression evidence"
```

### Task 7: Verify end-to-end behavior and establish the first baseline

**Files:**

- Create: `out/performance_telemetry_ci.json` (CI artifact; do not commit)
- Create: `out/performance_telemetry_comparison_ci.json` (CI artifact; do not commit)
- Create: `out/validation-runs/<run-id>/reliability_telemetry.json` (runtime artifact; do not commit)
- Modify: `docs/quality/performance_telemetry_baseline.json` only through the approved fixture-baseline command.
- Test: affected focused tests and required pipeline validation workflow.

**Interfaces:**

- Consumes: canonical discovery, acquisition, ingest, publish-safe validation profile, persisted telemetry, baseline comparator, and existing quality/cost gates.
- Produces: reproducible fixture baseline evidence and a safe live-run artifact whose comparison result is explicit.

- [ ] **Step 1: Run focused telemetry tests.**

Run: `python -m pytest tests/test_performance_telemetry_service.py tests/test_workflow_worker_performance_telemetry.py tests/test_llm_performance_telemetry.py tests/test_browser_performance_telemetry.py tests/test_validation_reliability_performance.py tests/test_performance_telemetry_baseline.py -q`

Expected: PASS.

- [ ] **Step 2: Run the existing deterministic quality and performance evidence gates.**

Run: `python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3`

Run: `python scripts/ci/check_performance_telemetry_regression.py --baseline docs/quality/performance_telemetry_baseline.json --output-json out/performance_telemetry_comparison_ci.json`

Expected: both PASS; the comparison artifact reports its profile, compatibility result, per-stage deltas, quality result, cost result, and proof status.

- [ ] **Step 3: Run the required safe pipeline validation in order.**

Run the repository-approved isolated profile through discovery, acquisition, ingest, and publish in that order. Keep real external calls credential/opt-in guarded, publication dry-run/read-only, and all output paths isolated. For any unavailable provider/browser metric, retain `unavailable`; do not claim a full live proof from that run.

- [ ] **Step 4: Inspect the final diff and artifacts.**

Run: `git diff --check`

Run: `git status --short`

Expected: no whitespace errors, no committed runtime output, no secret-bearing artifacts, and only intended source/test/document/configuration changes.

- [ ] **Step 5: Commit the approved fixture baseline only after its gate passes.**

```powershell
git add docs/quality/performance_telemetry_baseline.json
git commit -m "test: establish performance telemetry fixture baseline"
```

## Self-Review

- [ ] Every requested metric has one precise definition, unit, owning boundary, persistence path, and explicit unavailable/not-applicable behavior.
- [ ] Queue wait, stage wall time, database wait, LLM latency, browser latency, cache counts, worker capacity utilisation, and total duration each map to a task and an observable test.
- [ ] The plan extends the canonical state database, validation manifest, LLM ledger, and reliability artifact rather than adding a parallel telemetry system or using logs as a data source.
- [ ] The comparator rejects incompatible runs and prevents a speed claim when quality/cost regresses or a required metric is partial/unavailable.
- [ ] CI remains deterministic and does not add live provider, browser, or publication calls; live validation remains credential-gated, isolated, and non-publishing.
- [ ] The plan contains no source-content, prompt, provider-response, credential, or sensitive payload retention path.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-10-end-to-end-performance-telemetry.md`. Two execution options:

1. Subagent-Driven (recommended) — dispatch a fresh subagent per task and review between tasks.
2. Inline Execution — execute tasks in this session using `executing-plans`, with checkpoints for review.
