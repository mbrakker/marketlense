# Recovery

> **Documentation type:** Operational procedure
> **Canonical topic:** Workflow recovery
> **Update trigger:** Failure taxonomy, checkpoint/resume behavior, or remediation runbook changes.

1. Start with `python -m src.cli remediations` and identify the remediation ID, state, typed error code, next action, attempt budget, checkpoint, and runbook. Raw diagnostics are operator-only ledger data, not a required starting point.
2. Confirm the failure category and whether it is retryable; do not repeat permanent failures without fixing the prerequisite.
3. Inspect the execution plan, preflight output, and relevant retained checkpoint before launching another side effect. A missing, stale, corrupt, or lineage-free checkpoint is a blocker, not a resume target.
4. Confirm idempotency evidence before publication, Drive-family, email-request, or any other external write. If proof is missing, keep the record in `operator_action_required`.
5. Use the smallest safe restart or explicit workflow command after correcting the cause. The reaper is feature-gated off by default; enabling it does not authorize unbounded retries or unknown-error recovery.
6. Resolve or supersede the durable remediation record when the operator action is complete; do not delete historical retry logs.

The [top failure runbooks](top_failure_runbooks.md) contain typed failure-specific checks and bounded remediation commands. `docs/ops/failure_remediation.yaml` is the machine-validated runbook registry.

For report processing, checkpoint resume is orchestrator-owned and validates retained artifacts and lineage. Do not manually edit checkpoint state to bypass validation. For publication recovery or rollback, use [WordPress operations](wordpress.md).
