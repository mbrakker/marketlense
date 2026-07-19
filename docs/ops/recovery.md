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

## Read-only remediation soak and activation gate

The remediation ledger is the canonical workflow-wide failure backlog. UI
dead-letter rows remain compatibility data until an explicit migration is
approved. A soak observes the ledger only: it does not claim a lease, release
a lease, execute a repair, or alter historical transitions.

Before considering execution, generate the coverage inventory and runbook
validation, then retain the command output for each normal production
execution window under review:

```powershell
python scripts/quality/generate_remediation_coverage.py
python scripts/quality/generate_budget_authority_coverage.py
python scripts/ci/check_remediation_runbooks.py
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
python -m src.cli remediation-soak | Tee-Object "out/ops/remediation-soak-$stamp.txt"
python -m src.cli remediation-opportunities | Tee-Object "out/ops/remediation-opportunities-$stamp.json"
```

The retained evidence must identify the repository revision, observed state
database, UTC observation time, and coverage report. It must demonstrate all
of the following before an operator approves any execution-enabled change:

1. The generated coverage report lists every production workflow as covered or
   explicitly exempted.
2. Current remediation IDs are unique. A nonzero `deduplicated records` count
   is evidence that repeated observations converged on an existing record, not
   that duplicate current records exist.
3. There are no stale leases, no missing runbook mappings, and every eligible
   record is understood. Records outside the exact automatic allowlist remain
   `operator_action_required`. A legacy `pending` record carrying
   `mark_terminal_blocker` is projected as held by the read-only soak; it is
   never reported as lease-eligible.
4. A representative sample proves checkpoint validity, lineage presence,
   attempt/cooldown enforcement, and idempotency proof for every external
   side-effect class. Public publishing, mail submission, and other external
   writes remain held without proof.
5. The activation decision, exact allowlisted workflow/error/action triples,
   review date, and rollback owner are retained with the soak output.

`workflow_control.remediation_reaper.execution_enabled` remains `false` by
default. Turning it on requires an explicit, reviewed configuration change
after this gate; it authorizes only the documented allowlist. Roll back by
setting it back to `false`, which leaves recording and operator visibility
active.

## Budget-deferred work recovery

Budget deferrals are visible through `python -m src.cli deferred-work`. New
queue-worker deferrals use the canonical `budget_deferred` job state; the
legacy ledger is retained only for historical records and compatibility.
Hand off supported legacy report-generation rows explicitly before running
workers:

```powershell
python -m src.cli queue-migrate-deferred-work --yes
```

The handoff verifies the retained PDF, creates a deterministic `source_ingest`
job with the original due time, remaining attempt budget, plan hash and lineage
key, and leaves the old ledger row readable. Repeating the command returns the
same effective job. Rows for an unsupported legacy workflow, missing retained
artifact, or exhausted legacy attempt budget remain visible as `unresolved` in
the command output; they are never silently discarded or guessed into another
workflow.

The old `deferred-work-reap` command remains an emergency compatibility path
while legacy rows are being handed off. Do not enable it alongside normal queue
workers for a migrated record; use the canonical queue controls, retry state,
and remediation flow for all new work.

Every invocation first rechecks the canonical budget, then rebuilds the
minimal plan and validates reusable artifacts. It preserves the original
idempotency key and uses a SQLite lease, so a second worker cannot execute the
same record. A continued `defer` is rescheduled after the configured delay;
`pause` and `stop` always enter actionable remediation rather than becoming a
new pending retry. Set the feature flag back to `false` for rollback: queued
records remain intact for inspection and manual recovery.

For report processing, checkpoint resume is orchestrator-owned and validates retained artifacts and lineage. Do not manually edit checkpoint state to bypass validation. For publication recovery or rollback, use [WordPress operations](wordpress.md).

## Durable workflow queue recovery

Use the queue control plane for accepted asynchronous work. It is separate from
the remediation ledger: the queue owns normal due work, retries, leases, and
outbox materialisation; remediation remains the terminal/operator boundary.

```powershell
python -m src.cli queue-health
python -m src.cli queue-inspect-job <job-id>
python -m src.cli queue-release-expired-leases
python -m src.cli queue-reconcile
python -m src.cli queue-materialize-outbox
```

Pause a queue with a reason before an incident investigation. Drain mode stops
new claims while preserving durable work. `queue-requeue --yes` is only for a
blocked or dead-letter job after its retained input and idempotency proof have
been checked; it never resets product-domain state. See [asynchronous workflow
queue](../architecture/asynchronous-workflow-queue.md) for the state machine
and approval-to-publication rules.
