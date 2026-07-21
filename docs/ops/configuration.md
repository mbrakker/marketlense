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

All runtime data paths in `paths`, acquisition, analysis, cost, publication,
mailbox, and browser sections are resolved once to absolute paths. A profile
inside the repository is relative to the repository workspace even when it is
nested below another directory; an intentionally external configuration file
uses its containing directory as its portable workspace. Provider rate-card
paths remain relative to their configuration file so an external profile can
ship its matching rate card together.

The important operator sections are `paths`, `ingest`, `publish`, `browser_download`, `mailbox_acquisition`, `publisher_discovery`, and `workflow_control`. `workflow_control.remediation_reaper.execution_enabled` remains `false` until record creation and read-only projections have been verified; `max_records_per_run` and `lease_seconds` bound each explicit reaper invocation. `workflow_control.deferred_work_reaper.execution_enabled` is the independent rollback gate for budget-deferred recovery; it is also `false` by default, while its record limit, lease duration, and retry delay bound each external worker invocation. `openai_models`, `llm_routing`, `llm_execution_policies`, and `cost` govern model routing and accounting. `llm_execution_policies` is the versioned namespace policy for provider/model, sampling, output limits, timeout, structured-output mode, compaction, pricing key, and same-provider fallback. It resolves exact namespace then longest prefix and forbids provider-owned retries; workflow retry policy remains orchestrator-owned. The compatibility adapter preserves historical non-report namespaces until they are explicitly migrated. `workflow_control.supervisor` is disabled by default and bounds one lease-protected `supervise-workflows --once` pass; an external scheduler owns recurrence.

The `publisher_inventory/meaningful_candidate_screen` namespace is deliberately
routed and priced as `gpt-5-nano`, matching the bounded candidate-screening
configuration. Namespace policy and workflow-specific settings must agree;
the policy preflight rejects unknown or incompatible routes before provider I/O.

`ingest.validation.public_editorial_quality.disabled_rule_waivers` is the temporary staged-rollout escape hatch for the deterministic public-editorial release gate. Each mapping key is a stable rule ID and each value must be a concrete non-empty release-waiver reason. An empty or malformed entry has no effect; do not use this setting to suppress an unresolved reader-facing defect.

`ingest.source_quarantine.enabled` is the single rollback switch for the deterministic source-PDF integrity gate. When enabled (the default), a source that fails the header, EOF, parser-open, or page-count check is recorded in the canonical state database and an unchanged upstream checksum is skipped before extraction, OCR, or model work. It does not delete source or cache bytes. Operators can review records with `source-quarantines` and revalidate a retained file with `revalidate-source-pdf`; successful validation clears the matching record and supersedes an earlier active checksum for the same source. Disable the switch only for a time-bounded incident rollback, because malformed inputs then follow the ordinary typed failure path and may consume repeated acquisition work.

Corpus rehabilitation has no automatic switch: planning is read-only and campaign execution is explicit. `corpus-rehabilitation-create` persists a bounded retained-evidence plan; `corpus-rehabilitation-approve --yes` records a bounded operator approval; and `corpus-rehabilitation-submit --yes` queues only reusable, checksum-bound candidates through the existing maintenance queue. The submitter rechecks retained classification and lineage before handoff, while incomplete candidates remain operator-held. It has no public-write path.

Use the generated [configuration reference](../generated/configuration-reference.md) for the current section inventory. It is generated from `src/config/app.example.yaml`; use the YAML and typed contracts as the final authority for values and validation.

## Typed operational run profiles

`workflow_control.run_profiles` is the single typed selector for operating outcomes. It composes existing preflight profiles, queue budget-profile references, concurrency resources, and already-approved model-policy tiers; it does not create budgets, routing rules, or mutable configuration. The available profiles are `safe_default`, `fast_cached`, `repair_failed`, `publish_ready`, `browser_acquisition`, `cost_saver`, and `high_quality`.

Use `python -m src.cli plan <intent> --profile <name>` to inspect a selection before execution. Plan output includes the profile name, deterministic hash, bounded effective selections, and a separate recommendation; a recommendation never changes the selected profile. CLI and UI resolve through the same typed resolver. A profile is resolved after the existing base-and-overlay configuration load: an explicit CLI/UI profile wins, otherwise the legacy-safe `safe_default` is selected; the environment/local overlays only determine the available profile definitions. Explicit bounded per-run overrides win over profile values. Unknown profiles, unknown queue-budget references, secret-like fields, unsupported override keys, incompatible workflows, and unbounded `repair_failed` targets fail before provider I/O.

Profiles cannot disable validation, evidence checks, human publication approval, the supervisor, remediation reaping, or deferred-work reaping. Roll back selection by omitting `--profile` or the UI profile field; retained hashes remain readable in plans and run records.

## Side-effect budget authority

`cost.budget_authority` configures the single SQLite-backed authority used before provider calls, browser launches and Browser Use model calls, material Drive reads and writes, WordPress writes, PDF processing, retry attempts, and mailbox polls. Its `run`, `day`, and `publisher` sections accept the typed limits in `RunBudgetLimits`, including spend, calls, runtime, retries, browser launches, Drive reads/writes, WordPress writes, and mailbox reads. PDF processing remains an auditable effect, but it has no count-based admission limit in the committed configuration: processing admission is governed by the configured spend forecast and spend limit.

Limits are inclusive: a prospective side effect that brings a metric exactly to its configured maximum is admitted and warned; the next prospective side effect is stopped. This keeps a configured one-PDF run capable of processing one PDF while retaining a hard bound.

`cost.pricing_path` points to the versioned operator rate card. Each active
model entry records its provider, exact model key, effective date, pricing
version, source note, input/cached-input/output rates, and any fixed tool
charge. The `__policy__` record holds unpriced configured routes before
provider I/O; do not use a zero rate as a substitute. Usage events retain the
selected pricing version and explicit report, workflow, prompt, publisher, and
artifact-family context when the caller has it. Historical events remain in an
`unknown` attribution bucket.

`enabled_effect_kinds` is an independent additive feature gate for each effect category. Removing a kind rolls back its pre-effect enforcement while retaining all earlier reservations, decisions, and actual-use records. Reservations expire after `reservation_ttl_seconds` (one hour maximum); completed effects finalize observed non-monetary use and release unused capacity. Provider monetary actuals remain in the existing LLM usage events and only reconcile their reservation.

`ingest.run_budget` sets retry and elapsed-runtime safeguards; it does not cap the number of PDFs. `browser_download.run_budget` and `publish.run_budget` remain the scoped acquisition and publication controls; all use the same `cost.usage_db_path` authority. Vector-store requests inherit the active report runtime's `RunBudget`, so their forecasts and actual usage are written to that same isolated ledger rather than a process-default ledger. `browser_download.route_suppression` is independently reversible: it requires a minimum of three compatible typed terminal failures, records a policy-compatibility hash and TTL, and can always be bypassed with the explicit acquisition revalidation option. It never permanently blacklists a publisher.

Opening the canonical usage database applies additive migration `003`: it extends the existing deferred-work audit rows with bounded lease, deadline, plan, artifact, idempotency, and terminal-remediation state. It is safe to rerun after interruption; no accounting rows are rewritten or discarded.

The Cost & Usage operator page displays the authority's allowed, prevented, avoided, expired-reservation, and override totals. Expiry-bound overrides require a typed actor, reason, scope, expiry, and policy version at the request boundary; they are not stored as reusable credentials or YAML bypasses.
