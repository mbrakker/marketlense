# Workflow Control

> **Documentation type:** Architectural
> **Canonical topic:** Workflow control
> **Update trigger:** Preflight, retry, checkpoint, state-machine, or idempotency changes.

Orchestrators are the control plane. They sequence services and generators, create run/task/span context, apply bounded retry policy, own state transitions, and enforce idempotency boundaries.

Before side effects, workflow control can build a typed execution plan and perform preflight checks. The CLI exposes this plan with `python -m src.cli plan <intent>`; the command is side-effect free. Configuration for preflight profiles, workflow contracts, retry policy, concurrency, and operational memory is under `workflow_control` in `src/config/app.yaml`.

Report processing supports controlled checkpoint resume, including `latest_safe` when a validated retained checkpoint is available. Generators do not retry provider failures; typed retryable failures propagate to the orchestrator. For operator actions, see [recovery](../ops/recovery.md) and [troubleshooting](../ops/troubleshooting.md).
