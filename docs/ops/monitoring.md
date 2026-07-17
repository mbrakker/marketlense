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

Quality evidence and release bundles are described in [evidence](../quality/evidence.md). For failure handling, continue to [recovery](recovery.md).

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
