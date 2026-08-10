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

`MARKET_LENSE_PRODUCER_COMMIT` is an optional, non-secret 40-character commit SHA. The canonical configuration service reads it when CLI or UI code creates a runtime context, so retained manifest and log provenance identify the producing build without giving utilities environment access.

Loading general application settings is credential-free: an absent Drive folder ID or OpenAI credential is represented as an empty setting so dry runs, planning, and operator inspection work in a clean checkout. The workflow preflight and provider boundaries then fail closed immediately before the affected external operation, with the typed missing-credential code and corrective action. Browser-acquisition settings keep their existing stricter provider-key check because they configure the model-backed browser runtime itself. Live ingestion, browser acquisition, and model calls therefore still require their real `.env` values; no credential default is introduced.

All runtime data paths in `paths`, acquisition, analysis, cost, publication,
mailbox, and browser sections are resolved once to absolute paths. A profile
inside the repository is relative to the repository workspace even when it is
nested below another directory; an intentionally external configuration file
uses its containing directory as its portable workspace. Provider rate-card
paths remain relative to their configuration file so an external profile can
ship its matching rate card together.

The important operator sections are `paths`, `ingest`, `publish`, `browser_download`, `mailbox_acquisition`, `publisher_discovery`, and `workflow_control`. The committed base leaves both recovery reapers and the supervisor disabled. The reviewed `MARKET_LENSE_CONFIG_PROFILE=autonomous_mvp` overlay enables the lease-protected supervisor plus remediation and deferred-work reapers with a two-record limit each; normal queue-worker batches remain disabled so the existing durable workers retain execution ownership. `workflow_control.remediation_reaper.execution_enabled` and `workflow_control.deferred_work_reaper.execution_enabled` remain independent rollback gates, while their record limits, lease duration, and retry delay bound each invocation. `openai_models`, `llm_routing`, `llm_execution_policies`, and `cost` govern model routing and accounting. `llm_execution_policies` is the versioned namespace policy for provider/model, sampling, output limits, timeout, structured-output mode, compaction, pricing key, and same-provider fallback. Settings startup resolves the complete finite production namespace inventory before any provider client can be used; an unknown or uncovered reachable namespace rejects configuration. The workflow preflight then retains the exact resolved namespace/provider/model/full-policy matrix and policy hashes with the run-owned artifacts. Provider-owned retries remain forbidden and workflow retry policy remains orchestrator-owned. The compatibility adapter preserves historical non-report namespaces until they are explicitly migrated. An external host owns recurrence for `workflow_control.supervisor`; the command itself is one-shot.

The `publisher_inventory/meaningful_candidate_screen` namespace is deliberately
routed and priced as `gpt-5-nano`, matching the bounded candidate-screening
configuration. Namespace policy and workflow-specific settings must agree;
the policy preflight rejects unknown or incompatible routes before provider I/O.

`ingest.validation.public_editorial_quality.disabled_rule_waivers` is the temporary staged-rollout escape hatch for the deterministic public-editorial release gate. Each mapping key is a stable rule ID and each value must be a concrete non-empty release-waiver reason. An empty or malformed entry has no effect; do not use this setting to suppress an unresolved reader-facing defect.

`ingest.source_quarantine.enabled` is the single rollback switch for the deterministic source-PDF integrity gate. When enabled (the default), a source that fails the header, EOF, parser-open, or page-count check is recorded in the canonical state database and an unchanged upstream checksum is skipped before extraction, OCR, or model work. It does not delete source or cache bytes. Operators can review records with `source-quarantines` and revalidate a retained file with `revalidate-source-pdf`; successful validation clears the matching record and supersedes an earlier active checksum for the same source. Disable the switch only for a time-bounded incident rollback, because malformed inputs then follow the ordinary typed failure path and may consume repeated acquisition work.

`ingest.admission` controls the deterministic source-admission limits applied
to every retained Drive source before vector-store creation or any model call.
`min_text_chars` is evaluated with the existing bounded native-text sample;
`max_pages` and `max_source_bytes` reject sources above the configured
per-report limits (`null` disables either maximum); and
`required_evidence_families` must be a subset of the configured
`evidence_packs.registry`. `doc_map` is the required default because it is the
first evidence-family hard gate. The preflight does not infer a public source
URL or publisher from the Drive artifact: it records the explicit
`drive_artifact_nonpublic` classification and `drive_unattributed` sentinel
until later source-backed extraction can establish public metadata. Its
retained decision hash includes only bounded inspection values, identities,
and configuration/policy hashes, never source text or a rendered prompt. The
same runtime preflight also write-probes the configured usage-ledger path,
because the admission budget forecast and later provider reservations share
that canonical SQLite authority.

`src/config/category-mappings.yaml` owns the category-fit semantic policy.
Its `high_confidence_fit_threshold` must be strictly between zero and one and
defaults to `0.85` only when absent from an older mapping. A rejected model
candidate above that threshold is reconciled against the category's explicit
`semantic_concepts` (or its `core_tags` fallback), inclusion rules, central
report context, and evidenced exclusions. Explicit inclusion support in a
central context field selects the category even when the provider assigned a
low score or rejected it; an evidenced exclusion remains authoritative. Keep
semantic concepts specific and reviewable; they are the deterministic basis for
closure, while prose rules remain the editorial guidance sent to the provider.

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

`ingest.run_budget` sets retry and elapsed-runtime safeguards; it does not cap the number of PDFs. `browser_download.run_budget` and `publish.run_budget` remain the scoped acquisition and publication controls; all use the same `cost.usage_db_path` authority. Vector-store requests, including readiness-status polling and metadata updates, inherit the active report runtime's `RunBudget`, so their forecasts and actual usage are written to that same isolated ledger rather than a process-default ledger. `browser_download.route_suppression` is independently reversible: it requires a minimum of three compatible typed terminal failures, records a policy-compatibility hash and TTL, and can always be bypassed with the explicit acquisition revalidation option. It never permanently blacklists a publisher.

Opening the canonical usage database applies additive migration `003`: it extends the existing deferred-work audit rows with bounded lease, deadline, plan, artifact, idempotency, and terminal-remediation state. It is safe to rerun after interruption; no accounting rows are rewritten or discarded.

The Cost & Usage operator page displays the authority's allowed, prevented, avoided, expired-reservation, and override totals. Expiry-bound overrides require a typed actor, reason, scope, expiry, and policy version at the request boundary; they are not stored as reusable credentials or YAML bypasses.
