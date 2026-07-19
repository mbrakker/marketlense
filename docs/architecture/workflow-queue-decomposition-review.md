# Workflow Queue Decomposition Review

> **Documentation type:** Architecture review record
> **Canonical topic:** Workflow queue module ownership
> **Update trigger:** Queue facade or private capability ownership changes.

## Scope and decision

The durable queue’s existing public entrypoints remain
`src.services.workflow_queue_service` and
`src.orchestrators.workflow_queue_orchestrator`. Their former mixed
implementations were moved, without SQL or workflow behavior changes, into
private capability families:

- persistence: schema/control, submission, leasing, completion, outbox,
  health, approvals, and briefing opportunities;
- orchestration: acquisition, report checkpoints, analytics, signals,
  briefings, publishing, and fixed-graph registry.

No queue/job type, registration order, transition, transaction boundary,
event, idempotency key, outbox identity, retry policy, database schema, or
external behavior changed as part of the split. The separately authorized
acquisition-to-ingest handoff accounts for the two changed handler symbols.

## Dependency direction

Service capability modules depend on queue schema helpers and the canonical
state connection. Orchestrator handler families depend on canonical service
and generator/orchestrator boundaries; only `registry.py` composes them into
the fixed graph. There is no second queue, service locator, generic handler
framework, or new deployable unit.

## Movement evidence

The machine-readable record is
[`refactor_movement_evidence.json`](../quality/refactor_movement_evidence.json).
Against `HEAD`, the service moved 41 symbols unchanged. The orchestrator moved
31 symbols: 29 unchanged and two with prior authorized handoff changes. The
old source-ingest helper and generic local hash helper were removed because the
typed verified-acquisition handoff is now their single canonical replacement.

## Verification

Focused tests prove facade imports, exact registration/downstream sets,
queue persistence transitions, outbox materialisation, approval atomicity, and
worker error classification. The controlled live queue proof is recorded with
the release evidence; it makes no provider or WordPress write.
