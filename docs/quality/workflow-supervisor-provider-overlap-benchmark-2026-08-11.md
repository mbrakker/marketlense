# Workflow Supervisor Provider-Overlap Benchmark — 2026-08-11

> **Documentation type:** Retained benchmark evidence
> **Scope:** Bounded supervisor worker concurrency only

## Decision

`workflow_control.supervisor.max_parallel_workers` is set to the tested cap of
three when the existing supervisor and worker-batch gates are enabled. The
runtime default remains one worker, and configuration values above three are
clamped to three.

This change preserves the queue's leases, retry states, idempotency keys,
outbox processing, result validation, and publication approval controls. It
does not change a prompt, model, cache policy, quality threshold, or cost
policy.

## Method

Each comparison used two warmups followed by seven alternating serial and
three-worker measured samples. Each sample contained three independent jobs.
The worker cap was the only experimental variable.

| Validation | Serial median | Three-worker median | Speedup | Quality and cost result |
| --- | ---: | ---: | ---: | --- |
| Deterministic 3.2-second provider wait | 9.604 s | 3.203 s | 2.999x | All jobs succeeded; $0 incremental cost in both profiles |
| Controlled live `gpt-5-mini` JSON provider canary | 9.647 s | 3.580 s | 2.695x | All 42 measured outputs exactly matched the requested JSON; median estimated sample cost fell from $0.000987 to $0.000859 |

The live canary made one preflight call and 54 bounded sample calls (55 maximum
calls), used 512 output tokens per request at most, disabled response-cache
reuse, and kept each request below the configured 30-second provider timeout.
It recorded no raw prompts, responses, or credentials.

## Durable queue validation

`tests/test_workflow_supervisor_parallelism.py` additionally submits one typed
job to each of the first three durable SQLite queues and processes them through
the production worker lifecycle using typed, in-process provider-wait handlers.
A bounded barrier proves all three handlers overlap before their successful
completion is released. This verifies that concurrency does not bypass
claim/start/complete transitions or persisted worker telemetry.

## Interpretation and bounds

The result proves a material improvement for independent work dominated by
provider wait. It is not a claim that CPU-bound processing or a single report's
strictly dependent stages will become three times faster. The live canary uses
the production supervisor and provider boundary but a controlled worker seam;
it does not publish, mutate a live queue, or make a public WordPress write.

Raw, redacted scalar artifacts are retained at:

- `outputs/workflow-supervisor-parallelism.json`
- `outputs/workflow-supervisor-live-provider-overlap.json`

## Validation record

The focused supervisor, durable-queue, safe discovery/acquisition/ingest/publish,
and PDF sidecar-concurrency checks passed. Documentation, contract-schema,
WordPress-subproject, coverage-threshold, and mutation gates also passed.

The Windows eight-worker full suite remains an independent baseline issue: its
failures vary across report-card title limits, browser-accounting SQLite
contention, asynchronous usage-ledger rebuild timing, and PDF temporary-path
contention. The scheduler tests themselves pass under eight workers. These
existing failures prevent a claim that the whole repository suite is green;
they do not exercise the changed supervisor paths.
