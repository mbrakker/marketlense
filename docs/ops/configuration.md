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

The important operator sections are `paths`, `ingest`, `publish`, `browser_download`, `mailbox_acquisition`, `publisher_discovery`, and `workflow_control`. `workflow_control.remediation_reaper.execution_enabled` remains `false` until record creation and read-only projections have been verified; `max_records_per_run` and `lease_seconds` bound each explicit reaper invocation. `openai_models`, `llm_routing`, and `cost` govern model routing and accounting; edit them only with the associated quality and operational implications understood.

`ingest.validation.public_editorial_quality.disabled_rule_waivers` is the temporary staged-rollout escape hatch for the deterministic public-editorial release gate. Each mapping key is a stable rule ID and each value must be a concrete non-empty release-waiver reason. An empty or malformed entry has no effect; do not use this setting to suppress an unresolved reader-facing defect.

Use the generated [configuration reference](../generated/configuration-reference.md) for the current section inventory. It is generated from `src/config/app.example.yaml`; use the YAML and typed contracts as the final authority for values and validation.

## Side-effect budget authority

`cost.budget_authority` configures the single SQLite-backed authority used before provider calls, browser launches and Browser Use model calls, material Drive reads and writes, WordPress writes, PDF processing, retry attempts, and mailbox polls. Its `run`, `day`, and `publisher` sections accept the typed limits in `RunBudgetLimits`, including spend, calls, runtime, retries, browser launches, Drive reads/writes, WordPress writes, PDFs, and mailbox reads.

`enabled_effect_kinds` is an independent additive feature gate for each effect category. Removing a kind rolls back its pre-effect enforcement while retaining all earlier reservations, decisions, and actual-use records. Reservations expire after `reservation_ttl_seconds` (one hour maximum); completed effects finalize observed non-monetary use and release unused capacity. Provider monetary actuals remain in the existing LLM usage events and only reconcile their reservation.

`ingest.run_budget` sets the report-generation PDF, retry, and elapsed-runtime ceilings. `browser_download.run_budget` and `publish.run_budget` remain the scoped acquisition and publication controls; all use the same `cost.usage_db_path` authority.

Opening the canonical usage database applies additive migration `002`: it adds forecast columns to existing reservations and creates idempotent actual-use and deferred-work tables. It is safe to rerun after interruption; no accounting rows are rewritten or discarded.

The Cost & Usage operator page displays the authority's allowed, prevented, avoided, expired-reservation, and override totals. Expiry-bound overrides require a typed actor, reason, scope, expiry, and policy version at the request boundary; they are not stored as reusable credentials or YAML bypasses.
