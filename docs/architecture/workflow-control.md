# Workflow Control

> **Documentation type:** Architectural
> **Canonical topic:** Workflow control
> **Update trigger:** Preflight, retry, checkpoint, state-machine, or idempotency changes.

Orchestrators are the control plane. They sequence services and generators, create run/task/span context, apply bounded retry policy, own state transitions, and enforce idempotency boundaries.

Before side effects, workflow control can build a typed execution plan and perform preflight checks. The CLI exposes this plan with `python -m src.cli plan <intent> [--profile <name>]`; the command is side-effect free. Configuration for preflight profiles, workflow contracts, retry policy, concurrency, operational memory, and typed operational run profiles is under `workflow_control` in `src/config/app.yaml`.

Run profiles select approved existing controls instead of copying their definitions. The resolver receives the canonical loaded configuration in CLI and UI paths, validates profile/workflow and budget-reference compatibility, preserves explicit bounded overrides, and records the selected profile plus deterministic hash in the execution plan and UI-run payload. Profile recommendations remain advisory. A profile cannot turn on recovery gates, skip validation, bypass a publication approval, or choose an unapproved provider.

The retained-corpus rehabilitation plan command (`corpus-rehabilitation-plan`) is deliberately read-only. It classifies persisted reports into provenance review, targeted repair, reusable-artifact recompute, or abstention using the canonical reports database and immutable lineage IDs. Unknown cost or provider-call estimates remain explicitly unavailable; the command never silently treats them as zero, re-ingests source PDFs, or submits a provider job. `corpus-rehabilitation-create` persists a content-addressed bounded campaign; `corpus-rehabilitation-approve --yes` records an operator/reason approval hash; and `corpus-rehabilitation-submit --yes` rechecks the retained classification, checksum, reference, and lineage IDs immediately before an idempotent handoff to the existing `artifact_repair` queue. Only proof-complete reusable-artifact recompute rows are queueable. Others remain operator-held, and campaign planned/actual provider calls and costs remain reconciled at zero until a governed worker performs later work. No command can publish content.

Report processing supports controlled checkpoint resume, including `latest_safe` when a validated retained checkpoint is available. Generators do not retry provider failures; typed retryable failures propagate to the orchestrator.

The frozen reliability cohort runner executes each selected report through the production workflow in its own fresh isolated state. Its `--max-duration` value is a per-report deadline, so one slow member does not consume another member's time budget. `--report-ids` selects members by the stable `cohort-<source-md5-prefix>` report ID while the retained run records both the full frozen manifest and the selected subset. Provider calls, tokens, cost, and elapsed runtime are attributed to each independent report run and then summed at cohort scope. For a measured rerun, set the deadline from twice the mean active wall time per completed report in retained telemetry for `source_ingest`, `report_selection`, `report_analysis`, `report_render`, and `publication_readiness`.

The state database owns the canonical durable remediation ledger. It deduplicates a failure by deterministic workflow identity, keeps checkpoint, lineage, artifact, committed-side-effect, budget, and idempotency context together, and records every state transition. The bounded reaper is an explicit orchestrator invocation, never a scheduler: its base-config gate is false, while the reviewed `autonomous_mvp` overlay enables only the finite allowlist. It leases at most one record per worker, honors cooldown and attempt limits, fails closed on checkpoints or idempotency proof, and never retries unknown errors. UI-run failures are projected into the canonical ledger while existing dead-letter rows remain compatibility records; the canonical operator backlog is the remediation ledger.

Budget `defer` decisions are durable recovery work in the canonical usage-ledger SQLite database, not terminal failures. The decision transaction records the original run, workflow/stage, report/source identity, affected limit, plan hash, reusable artifact references, original idempotency key, earliest retry time, deadline, and bounded attempt count. An external supervisor may invoke `python -m src.cli deferred-work-reap`; there is no embedded scheduler or polling loop. The base configuration remains disabled, and the reviewed `autonomous_mvp` overlay enables at most two records per pass. The reaper atomically leases due rows, re-evaluates the original canonical budget request without reserving capacity, rebuilds and validates a minimal plan, and resumes only an approved workflow handler. Report generation resumes only from a proof-validated `latest_safe` checkpoint/family with an enforced fresh plan and retained local PDF: a stale, missing, or incompatible checkpoint is handed to remediation and never starts a fresh PDF, OCR, extraction, or model run. Report-download and publisher-inventory adapters rebuild only a typed canonical queue submission from a retained URL, original idempotency key, and fresh budget decision; normal queue execution retains browser, mailbox, Drive, route-policy, and publication gates. Continued budget deferral is delayed; pause/stop, missing artifacts, expired deadlines, exhausted attempts, unknown workflows, and plan failures hand off to the remediation ledger. A lease owner is required for every completion or state change, so a restart can reclaim only expired work and concurrent workers cannot perform two effective resumes.

## One-shot workflow supervisor

`python -m src.cli supervise-workflows --once` composes existing queue operations; it is not a scheduler and never loops. A durable singleton lease prevents concurrent supervisors from duplicating supervisory work. With its feature gates enabled, one pass runs in this order: outbox materialisation, expired worker-lease recovery, registered deferred-work recovery, registered remediation recovery, bounded queue-worker candidates in round-robin queue order, reconciliation, then queue-health collection. `max_parallel_workers` is the global worker cap, `max_jobs_per_queue` bounds candidates for each queue, and `max_total_jobs` bounds non-idle work for the pass. Durable queue controls remain authoritative for per-queue concurrency and prevent claims while disabled, paused, or emergency-stopped. The default configuration remains disabled. The `autonomous_mvp` overlay enables normal queue-worker batches and the two bounded recovery reapers through this supervisor, so a pass can advance ordinary queue work and recovery handoffs through the existing durable workers and handlers. The overlay does not bypass workflow budgets, validation, queue leases, or publication approval; the external host still owns cadence. See the [autonomous-MVP runbook](../ops/autonomous-mvp.md) for invocation and status interpretation.

In the parallel worker path, `max_jobs_per_queue` bounds active candidate slots;
successful workers return their slot to the same queue so queued work can
continue within the pass, subject to global worker, total-job, runtime, and
durable queue limits. Newly materialized downstream work reopens the fair queue
scan, while a fully idle queue is skipped until useful work completes. Queue
preference is applied within round-robin queue order, so a preferred queue is
offered first without taking every global worker slot ahead of other queues.

Use an external timer only after observing queue health and recovery evidence:

```cron
*/5 * * * * cd /srv/marketlense && /usr/bin/python -m src.cli supervise-workflows --once
```

```ini
# systemd service ExecStart
/srv/marketlense/.venv/bin/python -m src.cli supervise-workflows --once
```

The exit status is `0` for healthy, `3` for a bounded partial deferral, `1` for an isolated failed capability, `4` when another supervisor holds the lease, and `2` when the feature remains disabled. Roll back by setting `workflow_control.supervisor.enabled: false`; queue records, checkpoints, leases, and idempotency keys remain intact for the existing manual worker commands.

Deferred-work transitions are restricted to the typed lifecycle statuses `pending`, `leased`, `completed`, `remediation`, and `terminal`.

For operator actions, see [recovery](../ops/recovery.md) and [troubleshooting](../ops/troubleshooting.md).
