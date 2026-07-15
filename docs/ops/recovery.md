# Recovery

> **Documentation type:** Operational procedure
> **Canonical topic:** Workflow recovery
> **Update trigger:** Failure taxonomy, checkpoint/resume behavior, or remediation runbook changes.

1. Identify the failing `run_id`, `task_id`, error code, and retained artifacts from structured logs.
2. Confirm the failure category and whether it is retryable; do not repeat permanent failures without fixing the prerequisite.
3. Inspect the execution plan, preflight output, and relevant retained checkpoint before launching another side effect.
4. Use the smallest safe restart or explicit workflow command after correcting the cause.
5. Record or escalate unresolved failures through the active operational process.

The [top failure runbooks](top_failure_runbooks.md) contain typed failure-specific checks and bounded remediation commands. `docs/ops/failure_remediation.yaml` is the machine-validated runbook registry.

For report processing, checkpoint resume is orchestrator-owned and validates retained artifacts and lineage. Do not manually edit checkpoint state to bypass validation. For publication recovery or rollback, use [WordPress operations](wordpress.md).
