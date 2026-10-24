# A20 Automatic Readiness and Execution Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every selected MarketLense workflow consume one redacted, configuration-bound capability proof before it can claim or dispatch costly or external work, while preserving independent queue progress and existing budget, approval, retry, lease, checkpoint, and idempotency gates.

**Architecture:** Extend the existing pipeline capability preflight contracts with a typed execution-readiness decision and a versioned proof identity. Derive queue requirements from the canonical queue registry, queue policy, preflight profile, and declared handler effects; persist the proof through the existing file service. The supervisor evaluates one decision per invocation and passes it to workers; standalone workers require their own decision. CLI and Streamlit render the same report contract.

**Tech Stack:** Python 3.12+, frozen dataclasses, existing `file_service`, `sqlite_migration_service`, `config_service`, queue registry, Typer, Streamlit, pytest.

## Global Constraints

- Reuse the existing pipeline preflight and provider service boundaries; do not add a health-check service, scheduler, database, dependency manager, or per-job provider probe.
- Required `blocked` and `not_checked` capabilities are non-executable; degraded execution is denied unless an explicit supported policy allows the affected workflow.
- Use one resolved config profile, queue policy set, runtime identity, and proof for checking and execution; preserve `MARKET_LENSE_CONFIG_PROFILE` behavior.
- Persist only redacted identities, hashes, stable reason codes, remediation, and bounded telemetry; never persist credentials, authorization headers, source content, prompts, or raw provider responses.
- Keep local probes UUID-scoped and clean them in `finally`; cleanup failure is an explicit failed capability.
- Keep provider checks read-only and opt-in; skip a live provider check when its local prerequisites fail.
- Leave affected queue jobs pending/deferred when readiness is unavailable; never repeatedly claim and fail them for infrastructure unavailability.
- Do not weaken publication approval, factual validation, budgets, retry policy, lease handling, idempotency, or recovery gates.

---

### Task 1: Add typed readiness and proof contracts

**Files:**
- Modify: `src/contracts/pipeline_preflight.py`
- Modify: `src/contracts/workflow_control.py`
- Test: `tests/test_capability_workflow_scope.py`
- Test: `tests/test_capability_preflight_orchestrator.py`

**Interfaces:**
- Produce `CapabilityWorkflowDecision`, `CapabilityReadinessProof`, and `CapabilityExecutionReadiness` frozen dataclasses.
- Produce `build_execution_readiness(report, request, ctx, ...)` and `validate_execution_readiness(readiness, expected_workflows, ...)` from `pipeline_preflight_orchestrator.py`.
- Extend `CapabilityPreflightReport` with the decision/proof fields using compatible defaults so existing serialized reports remain readable.
- Extend `PipelineExecutionAuthorizationRequest` with optional `capability_readiness`; authorization rejects a missing or invalid decision whenever the plan has executable side effects.

- [x] **Step 1: Write failing contract tests** for exact workflow scope, `not_checked` preservation, blocked/deferred reason maps, and rejection of a missing/stale/mismatched proof.
- [x] **Step 2: Run the focused tests** with `python -m pytest -q tests/test_capability_workflow_scope.py tests/test_capability_preflight_orchestrator.py -x` and confirm failure is caused by missing contracts/behavior.
- [x] **Step 3: Implement the frozen dataclasses** with schema version `2.0`, deterministic lists/maps, explicit `executable` flags, proof validity timestamps, and identity fields for configuration, policy, build, dependencies, assets, SQLite, providers, and tools.
- [x] **Step 4: Implement deterministic status reduction**: `blocked` is never executable; `not_checked` remains `not_checked`; `degraded` is non-executable by default and can only be executable through an explicit allowlist in the decision request; `not_required` is executable only when the workflow itself is not requiring the capability.
- [x] **Step 5: Add authorization validation** so missing, expired, mismatched, incomplete, or non-executable readiness raises canonical `AppError` before a side effect.
- [x] **Step 6: Run the focused tests** and confirm the new contract tests pass without changing unrelated plan behavior.

### Task 2: Derive queue capability requirements from canonical registry inputs

**Files:**
- Modify: `src/orchestrators/pipeline_preflight_orchestrator.py`
- Modify: `src/orchestrators/_workflow_queue_handlers/shared.py`
- Modify: `src/orchestrators/_workflow_queue_handlers/registry.py`
- Modify: `tests/test_capability_workflow_scope.py`
- Test: `tests/test_workflow_queue_registry.py`

**Interfaces:**
- Produce `derive_queue_capability_requirements(queue_name, policy, registration, workflow_control)` returning the resolved profile, side effects, and required capability families.
- Produce `validate_capability_registry_coverage(...)` for deterministic drift checks.

- [x] **Step 1: Add a failing registry drift test** that iterates every `WORKFLOW_QUEUE_NAMES` entry, resolves its handler registration, and proves every required capability has a derivation or a small explicit exception.
- [x] **Step 2: Run the registry/scope tests** and capture the current manually maintained mapping failures.
- [x] **Step 3: Add capability metadata to the existing handler registration** only where the existing `expected_external_effects` and configured profile cannot distinguish a real requirement; keep the exception list bounded and code-owned.
- [x] **Step 4: Replace direct workflow decisions based on `_QUEUE_PREFLIGHT_PROFILES` with the derived requirements, preserving the manual `report_generation` profile and failing closed for unknown queues, missing registrations, missing profiles, and unrecognized effects.
- [x] **Step 5: Attribute checks only to workflows that require them.** In particular, make vector-store checks depend on vector-enabled handlers/settings, make browser/Drive/mailbox requirements route-specific, make OCR provider-backed, and keep local-only maintenance queues free of irrelevant model checks.
- [x] **Step 6: Run `python -m pytest -q tests/test_capability_workflow_scope.py tests/test_workflow_queue_registry.py tests/test_capability_preflight_orchestrator.py`.

### Task 3: Complete deterministic local probes and proof identity

**Files:**
- Modify: `src/contracts/config.py`
- Modify: `src/contracts/ingest.py`
- Modify: `src/services/_config_service/ingest.py`
- Modify: `src/services/_config_service/app_settings.py`
- Modify: `src/config/app.yaml`
- Modify: `src/config/app.example.yaml`
- Modify: `src/orchestrators/pipeline_preflight_orchestrator.py`
- Modify: `src/services/file_service.py` only if a missing canonical seam is required
- Test: `tests/test_capability_preflight_resource_checks.py`
- Test: `tests/test_file_service.py`
- Test: `tests/test_sqlite_capability_preflight.py`

**Interfaces:**
- Add one operator setting, `ingest.preflight.min_free_space_bytes`, exposed as `preflight_min_free_space_bytes` with a safe default.
- Extend capability dependencies with a canonical free-space probe and proof identity inputs without bypassing `file_service` or `sqlite_migration_service`.

- [x] **Step 1: Write failing tests** for write failure cleanup, delete/cleanup failure reporting, concurrent probes with unique names, insufficient free space, missing configured assets, and all configured SQLite stores including separate Signal and usage paths.
- [x] **Step 2: Run those tests** and confirm the current fixed-name probe/cleanup paths fail.
- [x] **Step 3: Change both `_probe_storage_path` and `_probe_writable_path`** to generate UUID-scoped paths, track ownership, and attempt deletion in `finally`; if deletion fails return a distinct blocking reason and never delete a path not created by the invocation.
- [x] **Step 4: Add free-space inspection** using the filesystem containing each required path and compare it to the one resolved minimum; report only bytes/counts and stable reason codes.
- [x] **Step 5: Expand deterministic local checks** for supported Python/locked dependency evidence, required imports, configured executable tools, fonts/templates/prompt namespaces/JSON schemas, and canonical SQLite migration/integrity/foreign-key/writer-lock results. Keep default SQLite inspection non-destructive and expose explicit initialization through the existing migration service only.
- [x] **Step 6: Compute normalized semantic identities** with `stable_json_dumps`/`sha256_json`: effective profile/scope/policy, non-secret configuration, dependency/package/runtime, asset hashes, SQLite schema identities, tool identities, provider capability results, and build commit. Keep elapsed/provider-call counts outside identity material.
- [x] **Step 7: Persist one uniquely named redacted proof** under the existing output/preflight path through `file_service`; reject write failure rather than silently authorizing an unretained proof.
- [x] **Step 8: Run the focused resource, file, and SQLite suites and inspect retained JSON for secret/source/prompt/provider-response absence.

### Task 4: Correct provider capability checks and skip semantics

**Files:**
- Modify: `src/orchestrators/pipeline_preflight_orchestrator.py`
- Modify: `src/services/llm_service.py` or its existing preflight module only when the canonical service contract needs a typed result
- Modify: `src/services/browser_report_download_service.py` only for safe existing doctor invocation seams
- Modify: existing Drive/mailbox/WordPress service preflight modules only when their public contract is incomplete
- Test: `tests/test_capability_preflight_provider_paths.py`
- Test: `tests/test_mailbox_preflight_call_count.py`
- Test: `tests/test_drive_capability_preflight_errors.py`
- Test: `tests/test_wordpress_preflight_service.py`

- [x] **Step 1: Add failing tests** for primary OpenAI `accessible=False`, local-prerequisite skip preventing provider calls, vector-enabled workflow requirements, and independent workflow continuation.
- [x] **Step 2: Run the provider-focused tests** and record the current incorrect ready result/call counts.
- [x] **Step 3: Make the primary `llm_model` path inspect `accessible`** and map denied, invalid credential, timeout/TLS/clock, and transient failures to bounded stable codes; keep structured-output/policy/pricing checks separate and reuse configuration-ingress policy validation.
- [x] **Step 4: Add bounded read-only vector capability checks** only for handlers/settings that actually use vector stores; do not use chat-model metadata as a vector authorization result.
- [x] **Step 5: Preserve existing read-only Drive/mailbox/WordPress checks** and ensure exact enabled target operations are included. Do not invoke legacy Drive write-preflight by default.
- [x] **Step 6: Keep browser executable/runtime checks separate from provider metadata; use the existing browser doctor only behind explicit live policy with isolated profile/download paths and cleanup.
- [x] **Step 7: Run provider-focused tests and verify no live call occurs after a required local blocker.

### Task 5: Enforce readiness at supervisor, worker, and workflow-control boundaries

**Files:**
- Modify: `src/contracts/workflow_control.py`
- Modify: `src/orchestrators/workflow_supervisor_orchestrator.py`
- Modify: `src/orchestrators/workflow_worker_orchestrator.py`
- Modify: `src/orchestrators/workflow_control_orchestrator.py`
- Modify: `src/_cli/workflow_queue.py`
- Modify: `src/services/_workflow_queue_service/leasing.py` or the canonical claim seam only if needed to pass the decision before claim
- Test: `tests/test_workflow_supervisor_orchestrator.py`
- Test: `tests/test_workflow_queue_worker_failures.py`
- Test: `tests/test_workflow_control_supervisor.py`

**Interfaces:**
- `SupervisorRunRequest.capability_readiness: CapabilityExecutionReadiness` is required for enabled worker dispatch.
- `run_workflow_worker_once(..., capability_readiness=...)` validates the exact queue before `claim_next_workflow_job`.
- The supervisor validates once, filters only blocked/deferred queues, and passes the same decision object to every worker in the invocation.

- [x] **Step 1: Add failing boundary tests** proving blocked/not-checked queues are not claimed, ready independent queues run, stale/mismatched proof fails closed, and affected jobs remain pending.
- [x] **Step 2: Run the boundary tests** and confirm current supervisor/worker claim without readiness.
- [x] **Step 3: Add the readiness field and validation call** before supervisor lease dispatch and before standalone worker lease/claim. Disabled supervisors may return disabled without a readiness proof; enabled dispatch cannot.
- [x] **Step 4: Make supervisor use one decision** for the invocation, skip affected queues without consuming job allowance, and distinguish partial queue unavailability from supervisor failure. Preserve materialization, recovery, leases, queue controls, retries, idempotency, and reconciliation.
- [x] **Step 5: Update CLI worker/supervisor commands** to resolve one effective profile/config/policies/identity, run one capability preflight, build the decision, and pass it to the worker/supervisor. Preserve explicit `--profile`/environment profile selection and do not add a second selector.
- [x] **Step 6: Ensure direct workflow-control authorization consumes readiness** in `authorize_pipeline_execution` and any queue admission path with planned external/costly effects.
- [x] **Step 7: Run supervisor/worker/control tests and verify no affected job transitions to leased/running/retry/dead-letter.

### Task 6: Share the report through CLI and System & Storage UI

**Files:**
- Modify: `src/_cli/pipeline.py`
- Modify: `src/ui/app_pages/observability.py`
- Modify: shared UI/runtime helper only if needed to resolve the same report contract
- Test: `tests/test_capability_preflight_cli.py`
- Test: `tests/test_ui_workflow_control.py`

- [x] **Step 1: Add failing tests** for retained proof reference, per-workflow authorization, stable codes/remediation/rerun command, redaction, and no implicit live calls during page rendering.
- [x] **Step 2: Run the CLI/UI focused tests** and confirm the current CLI emits only the diagnostic report and the UI has no capability section.
- [x] **Step 3: Make the CLI persist and emit the same typed report/decision** with bounded diagnostics and exit codes that keep `not_checked`/degraded non-green.
- [x] **Step 4: Add a read-only System & Storage capability section** that invokes no live probe during render, displays the latest retained report/proof reference, and offers an explicit rerun action that uses the CLI/orchestrator boundary.
- [x] **Step 5: Run CLI/UI tests and inspect JSON/text output for credentials, source content, prompts, or raw provider responses.

### Task 7: Documentation, clean-room evidence, and final verification

**Files:**
- Modify: `docs/backlog/A-autonomy.md`
- Modify: `CONSOLIDATED_TODO.md`
- Modify: canonical configuration/troubleshooting owner under `docs/ops/` selected from `docs/README.md`
- Test/record: focused capability, queue, provider, UI, and relevant end-to-end gates

- [x] **Step 1: Run the complete focused A20 command set** and then the relevant aggregate quality gate; record exact exit codes, counts, warnings, and pre-existing failures.
- [x] **Step 2: Run clean local initialization/migration against fresh empty stores and isolated output paths using the supported local environment; inspect proof identity and cleanup.
- [x] **Step 3: Run any available offline/guarded live checks only with explicit flags and sandbox/read-only credentials. Record Windows/Ubuntu/provider criteria as verified only when actually executed; leave unavailable criteria open.
- [x] **Step 4: Inspect final diff and retained artifacts for scope, secret exposure, source/prompt/response leakage, and unintended queue side effects.
- [x] **Step 5: Update A20 evidence and `CONSOLIDATED_TODO.md`; keep A20 Active if any acceptance criterion lacks evidence.
- [x] **Step 6: Commit the scoped implementation, run the final verification again at the commit SHA, push only to the authorized branch, and record the commit SHA/CI URL or explicitly state when CI/provider access is unavailable.

**Execution record (2026-10-24):** Implementation commit `ae4be3587d285ac86d6616f27a787341a23c2101` and evidence commit `c36089d2` were verified and pushed to `origin/codex/r8-final-closure`. The affected A20 suite passed `2,555`; repository-wide pytest retained the documented CPython 3.14 wheelhouse limitation; the bounded live canary passed with no publication. No CI URL was available from this environment. Clean-room Windows/Ubuntu installation and the complete provider/capability matrix remain open; A20 stays Active.
