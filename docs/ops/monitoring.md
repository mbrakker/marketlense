# Monitoring and Diagnostics

> **Documentation type:** Operational procedure
> **Canonical topic:** Monitoring and diagnostics
> **Update trigger:** Log schema, diagnostic command, run registry, or monitoring procedure changes.

Structured logs are the primary diagnostic surface. Meaningful events carry run, task, and span context plus module, role, and event name; redaction occurs before log emission.

Use the CLI trace view to reconstruct a run:

```powershell
python -m src.cli trace-run --run-id <run_id> --log-path logs/market_lense_YYYY-MM-DD.log
```

Use `--trace-id` for a trace-scoped view. Start with the run ID before narrowing to a task so parent-span context is retained. The Streamlit cockpit exposes run registry, dead-letter, log, storage, and cost views for operator workflows.

Quality evidence and release bundles are described in [evidence](../quality/evidence.md). For failure handling, continue to [recovery](recovery.md).
