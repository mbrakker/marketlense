# Configuration

> **Documentation type:** Operational procedure
> **Canonical topic:** Runtime configuration
> **Update trigger:** Configuration resolution, operator-facing setting, or configuration asset changes.

`src/config/app.yaml` holds committed, environment-neutral defaults. `src/config/app.example.yaml` is the starter overlay for environment-specific settings. Do not place secrets in either file.

Configuration resolves in this order:

1. `src/config/app.yaml`, unless `MARKET_LENSE_CONFIG_PATH` selects another base file.
2. `app.<profile>.yaml` next to the selected `app.yaml` when `MARKET_LENSE_CONFIG_PROFILE` is set.
3. `app.local.yaml` next to the selected `app.yaml`, when present.
4. Environment variables where the configuration loader supports an override.

The important operator sections are `paths`, `ingest`, `publish`, `browser_download`, `mailbox_acquisition`, `publisher_discovery`, and `workflow_control`. `workflow_control.remediation_reaper.execution_enabled` remains `false` until record creation and read-only projections have been verified; `max_records_per_run` and `lease_seconds` bound each explicit reaper invocation. `workflow_control.deferred_work_reaper.execution_enabled` is the independent rollback gate for budget-deferred recovery; it is also `false` by default, while its record limit, lease duration, and retry delay bound each external worker invocation. `openai_models`, `llm_routing`, `llm_execution_policies`, and `cost` govern model routing and accounting. `llm_execution_policies` is the versioned namespace policy for provider/model, sampling, output limits, timeout, structured-output mode, compaction, pricing key, and same-provider fallback. It resolves exact namespace then longest prefix and forbids provider-owned retries; workflow retry policy remains orchestrator-owned. The compatibility adapter preserves historical non-report namespaces until they are explicitly migrated. `workflow_control.supervisor` is disabled by default and bounds one lease-protected `supervise-workflows --once` pass; an external scheduler owns recurrence.

`ingest.validation.public_editorial_quality.disabled_rule_waivers` is the temporary staged-rollout escape hatch for the deterministic public-editorial release gate. Each mapping key is a stable rule ID and each value must be a concrete non-empty release-waiver reason. An empty or malformed entry has no effect; do not use this setting to suppress an unresolved reader-facing defect.

Use the generated [configuration reference](../generated/configuration-reference.md) for the current section inventory. It is generated from `src/config/app.example.yaml`; use the YAML and typed contracts as the final authority for values and validation.

## Side-effect budget authority

`cost.budget_authority` configures the single SQLite-backed authority used before provider calls, browser launches and Browser Use model calls, material Drive reads and writes, WordPress writes, PDF processing, retry attempts, and mailbox polls. Its `run`, `day`, and `publisher` sections accept the typed limits in `RunBudgetLimits`, including spend, calls, runtime, retries, browser launches, Drive reads/writes, WordPress writes, PDFs, and mailbox reads.

`cost.pricing_path` points to the versioned operator rate card. Each active
model entry records its provider, exact model key, effective date, pricing
version, source note, input/cached-input/output rates, and any fixed tool
charge. The `__policy__` record holds unpriced configured routes before
provider I/O; do not use a zero rate as a substitute. Usage events retain the
selected pricing version and explicit report, workflow, prompt, publisher, and
artifact-family context when the caller has it. Historical events remain in an
`unknown` attribution bucket.

`enabled_effect_kinds` is an independent additive feature gate for each effect category. Removing a kind rolls back its pre-effect enforcement while retaining all earlier reservations, decisions, and actual-use records. Reservations expire after `reservation_ttl_seconds` (one hour maximum); completed effects finalize observed non-monetary use and release unused capacity. Provider monetary actuals remain in the existing LLM usage events and only reconcile their reservation.

`ingest.run_budget` sets the report-generation PDF, retry, and elapsed-runtime ceilings. `browser_download.run_budget` and `publish.run_budget` remain the scoped acquisition and publication controls; all use the same `cost.usage_db_path` authority. `browser_download.route_suppression` is independently reversible: it requires a minimum of three compatible typed terminal failures, records a policy-compatibility hash and TTL, and can always be bypassed with the explicit acquisition revalidation option. It never permanently blacklists a publisher.

Opening the canonical usage database applies additive migration `003`: it extends the existing deferred-work audit rows with bounded lease, deadline, plan, artifact, idempotency, and terminal-remediation state. It is safe to rerun after interruption; no accounting rows are rewritten or discarded.

The Cost & Usage operator page displays the authority's allowed, prevented, avoided, expired-reservation, and override totals. Expiry-bound overrides require a typed actor, reason, scope, expiry, and policy version at the request boundary; they are not stored as reusable credentials or YAML bypasses.
