# Autonomous MVP Runbook

> **Documentation type:** Operational procedure
> **Canonical topic:** Autonomous MVP supervisor
> **Update trigger:** Autonomous profile, supervisor pass, recovery gates, exit status, or operator follow-up changes.

The autonomous MVP uses the existing durable workflow supervisor and registered
queue workers. The host controls cadence. Each invocation is one bounded pass;
the command does not schedule itself or keep a worker loop running.

## Invoke one pass

Select the profile in the process that runs the command, then invoke the
supervisor once:

```powershell
$env:MARKET_LENSE_CONFIG_PROFILE = "autonomous_mvp"
python -m src.cli supervise-workflows --once
```

An external timer, service manager, or host job decides when to invoke that
command again. Do not add an in-process scheduler. The base/default profile
keeps `workflow_control.supervisor.enabled` and
`workflow_control.supervisor.worker_batches_enabled` false. Unset the profile
to return to the base configuration, after confirming no `app.local.yaml`
override re-enables these gates.

## What one pass can do

The supervisor takes its durable singleton lease, then runs the existing
operations in order: materialize outbox events, recover expired worker leases,
run the bounded deferred-work and remediation reapers, dispatch normal queue
workers, reconcile queue state, and collect queue health. Recovery handoffs are
durable queue or ledger records. Normal work uses the registered production
handlers and the existing worker lifecycle.

The autonomous overlay enables both normal worker batches and the finite
recovery adapters. Its recovery reapers each process at most two records per
pass with their existing 60-second record leases. Normal queue work retains
durable queue enable/pause/emergency-stop controls, attempt limits, workflow
budgets, leases, round-robin fairness, idempotency, and validation. Publication
still requires the existing checksum-bound human approval.

The overlay does not retune supervisor limits. With committed base values,
one pass allows at most three global workers and up to three active worker slots
per queue, with a 60-job total cap. The 1,200-second runtime limit stops new
dispatch; the supervisor waits for already active workers to finish, so total
wall-clock time can exceed that cutoff. The supervisor lease is 180 seconds
and is renewed while the pass runs. The effective application configuration
remains authoritative if an operator has changed those base values. A
successful worker can expose downstream work to the same pass while job,
runtime, and durable queue limits allow it.

## Interpret the result and check health

The command prints a structured result and exits with one of these codes:

| Exit | Supervisor status | Meaning and next action |
| --- | --- | --- |
| `0` | `healthy` | The pass finished without a reported worker error or deferred outcome. Work may remain because a queue is paused, a pass bound was reached exactly, or work is not due. Check queue health to confirm backlog state. |
| `3` | `partially_deferred` | A worker reported `budget_deferred`, `retry_wait`, or `blocked`, or the runtime bound left work for another pass. Inspect the job and the corresponding budget or recovery record. |
| `1` | `failed` | A recovery adapter was unavailable, a worker returned an error terminal state, a supervisor lease was lost, or reconciliation reported an anomaly. Read `error_codes` and inspect the durable records before retrying. |
| `4` | `busy` | Another supervisor owns the singleton lease. No second pass was started. Check the active invocation before taking action. |
| `2` | `disabled` | The selected configuration has the supervisor gate off. Check `MARKET_LENSE_CONFIG_PROFILE` and the resolved configuration. |

`healthy` describes this bounded invocation; it does not mean every queue is
empty or every item succeeded. Compare the durable queue and recovery views:

```powershell
python -m src.cli queue-health
python -m src.cli deferred-work
python -m src.cli remediations
```

Use `queue-inspect-job <job-id>` for a specific queue record. Keep blocked,
dead-letter, remediation-held, and unresolved deferred records visible for
operator review. Do not manually edit checkpoints, leases, attempt history,
or idempotency records to force progress. See [recovery](recovery.md) for
approved repair actions.

## Isolated smoke evidence

Before enabling a host cadence, retain the tested commit, isolated state
location, selected profile, each invocation's exit code and supervisor counts,
queue state before and after, job terminal outcomes, and operator-intervention
count. Do not include credentials, source content, prompts, or model responses.
