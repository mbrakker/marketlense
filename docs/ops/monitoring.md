# Monitoring and Diagnostics

> **Documentation type:** Operational procedure
> **Canonical topic:** Monitoring and diagnostics
> **Update trigger:** Log schema, diagnostic command, run registry, or monitoring procedure changes.

Structured logs are the primary diagnostic surface. Meaningful events carry run, task, and span context plus module, role, and event name; redaction occurs before log emission. Text-bearing fields (for example prompts, report text, evidence, excerpts, editorial commentary, and responses) are represented only by a redaction marker, SHA-256, and character count. Other long text is treated the same. Use retained access-controlled artifacts, not standard logs, when full content is needed for an investigation.

Use the CLI trace view to reconstruct a run:

```powershell
python -m src.cli trace-run --run-id <run_id> --log-path logs/market_lense_YYYY-MM-DD.log
```

Use `--trace-id` for a trace-scoped view. Start with the run ID before narrowing to a task so parent-span context is retained. The Streamlit cockpit exposes run registry, dead-letter, log, storage, and cost views for operator workflows.

## Performance telemetry

Stage performance is persisted in the canonical state database. Queue-backed
stages currently record wall time and queue wait. The shared artifact also
accepts database wait, LLM/browser latency, cache counts, worker-capacity
utilisation, and total duration as their owning boundaries emit them. A metric
marked `unavailable` was not measured; it is not zero and cannot support a
speed-improvement claim.

Compare retained before/after JSON artifacts only when their measurement-profile
hashes match:

```powershell
python scripts/quality/performance_telemetry_baseline.py --baseline <before.json> --candidate <after.json> --output-json out/performance-comparison.json
```

The comparator rejects a claimed improvement when the candidate is not faster,
quality did not pass, cost increased, or either run is incompatible.

For CI, inspect `out/ci_performance_benchmark.json` together with
`out/test_telemetry_ci.json` and `out/quality_command_telemetry_ci.json`. The
combined artifact contains the pytest session and the standalone deterministic
quality/regression gates; it deliberately excludes setup, dependency install,
and opt-in staging checks.

Quality evidence and release bundles are described in [evidence](../quality/evidence.md). For failure handling, continue to [recovery](recovery.md).

## Validation-run LLM attribution

For a frozen validation cohort, each LLM ledger event inherits the validation
run, cohort, workflow run, report/source and publisher identity, workflow
stage, artifact family, repair attempt, configuration/policy hashes and
producer revision from `RunContext` when an individual provider request does
not repeat them. Missing attribution is a runtime ledger error. Pipeline
preflight also writes a non-sensitive resolved namespace/provider/model/policy
matrix under the run output's `preflight/` directory before provider I/O.

## Provenance, remediation, and budget authority

Source-publication events retain only source record IDs, statuses, locators,
and value hashes; use the retained controlled snapshot when the underlying
publisher page must be inspected. The extraction and render policy is
[source publication metadata](source-publication-metadata.md).

The generated [remediation workflow matrix](remediation_workflow_coverage.md)
lists each production workflow's terminal boundary and explicit exemptions.
The generated [budget-authority matrix](budget_authority_coverage.md) lists
every metered or mutating resource family, preflight gate, actual-use source,
reconciliation path, and blocking decision. Regenerate both before an
operational review:

```powershell
python scripts/quality/generate_remediation_coverage.py
python scripts/quality/generate_budget_authority_coverage.py
```

Use `python -m src.cli deferred-work` to inspect the durable budget-deferred
backlog without leasing it. The Cockpit also shows queue depth, oldest age,
due count, active lease count, completion rate, repeated-deferral count, and
terminal/remediation count, followed by redacted item state. These are scalar
operational signals; they do not expose source content or model responses.
