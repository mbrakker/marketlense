# Analytics Projection Foundation

## What Was Added

Market Lense now has an additive post-analysis projection layer for cross-report analytics and durable claim embedding reuse.

The layer keeps the existing per-report JSON packs, artifacts, validation outputs, vector-store analysis path, and rendered HTML behavior intact. It projects the already assembled report analysis state into normalized SQLite tables and a vector-ready queue.

Added boundaries:

- `src/contracts/analytics_projection.py`: versioned dataclass contracts for projected report rows, entity rows, vector queue rows, claim embedding records, upsert requests, read requests, and failure requests.
- `src/generators/analytics_projection_generator.py`: deterministic mapping from existing analysis packs and artifacts into normalized projection rows.
- `src/services/analytics_store_service.py`: SQLite schema creation, migrations, idempotent upserts, scoped stale-row cleanup, claim embedding persistence/readback, and projection failure persistence.
- `src/orchestrators/analytics_projection_orchestrator.py`: sequencing for build, upsert, and typed failure recording.
- `src/orchestrators/claim_embedding_orchestrator.py`: sequencing for pending claim embedding reads, LLM-service embedding calls, durable record writes, failed-attempt recording, and queue status updates.

## Trigger Point

Projection runs from `src/orchestrators/report_generation_orchestrator.py` after the rendered report outcome has been successfully assembled.

Projection failures are logged with `analytics_projection_failed_nonblocking` and persisted to the `reports` row, but they do not block the existing processed HTML outcome.

## Data Model

The existing `reports` table now carries canonical projection metadata:

- `report_id`, `publisher_id`, `source_md5`
- `ingest_run_id`, `analysis_run_id`
- `validation_status`, `validation_severity`
- `text_density`, `text_not_available`
- `projection_schema_version`, `projection_version`
- `projection_status`, `projection_attempt_count`
- `projection_error_code`, `projection_error_message`, `projection_error_retryable`
- `projection_generated_at_utc`, `projection_updated_at_utc`

Projection-owned tables:

- `report_sections`
- `report_findings`
- `report_metrics`
- `report_quotes`
- `report_claims`
- `report_tags`
- `report_categories`
- `report_figures`
- `vector_projection_queue`
- `claim_embeddings`
- `claim_embedding_queue_transitions`

`report_id` is the existing Drive file ID. `source_file_id` is intentionally not stored as a separate projected field when it would equal `report_id`.

Stale-row cleanup is scoped strictly to the current `report_id` and each projection-owned table independently.

## Claim Embedding Persistence

`vector_projection_queue` stages embedding work and `claim_embeddings` stores durable claim-level embedding attempts.

Queued rows include:

- `entity_uid`, `entity_type`, `report_id`
- `text_payload`, `content_hash`, `metadata_json`
- `content_class`
- `embedding_status`, `embedding_version`
- `created_at_utc`, `updated_at_utc`

Allowed `embedding_status` values are `pending`, `embedded`, and `failed`. New projection rows are written as `pending`. `content_hash` is computed from canonical serialized text plus embedding-relevant metadata, so the claim embedding workflow can detect unchanged content and avoid unnecessary re-embedding.

`content_class` separates `evidence`, `derived_evidence`, and `editorial` content so future retrieval can filter presentation-only material.

Embedding records include:

- `embedding_uid`, `claim_uid`, `entity_uid`, `report_id`
- `content_hash`, `embedding_version`, `provider`, `model`
- `dimensions`, `vector_json`, `external_vector_id`, `metadata_json`
- `status`, `generated_at_utc`, `updated_at_utc`, `attempt_count`
- `error_code`, `error_message`, `error_retryable`, `error_severity`

`run_claim_embedding_workflow` reads claim rows whose queue status is pending/failed, whose queue embedding version differs from the requested version, or whose current content/model/provider/version combination has no successful durable record. Successful runs persist vectors and update the queue to `embedded`; provider failures persist failed records with the typed `AppError` taxonomy and update the queue to `failed`.

`read_claim_embeddings` returns local durable records filtered by claim IDs, report IDs, topic taxonomy/category metadata, and status. This is reusable claim grounding inside the existing reports DB; it does not introduce a new deployable worker, peer analytics database, external vector database, or semantic-search product UI.

## Bounded Queue Remediation

The queue is operated through explicit commands, not a daemon or scheduler. `embedding-queue-health` classifies every retained queue row without provider calls. Claim rows are classified as ready, already satisfied, stale, obsolete, terminal/retryable failures, invalid, orphaned, budget-blocked, or review-required. Non-claim projection rows remain visible as `unknown_requires_review`; they are never submitted to the claim embedding provider.

The reports migration `reports_db_016_add_claim_embedding_queue_controls` adds retry eligibility, attempt, lease, actor, reason, and projection-schema fields to `vector_projection_queue`, plus the append-only `claim_embedding_queue_transitions` audit table. It also adds the queue-age, report-scope, durable-embedding identity, and audit indexes used by the bounded paths. Historical rows are retained.

Reconciliation is provider-free. It marks a durable match as embedded, records stale content for deterministic reprojection, terminalizes obsolete versions, and terminalizes orphaned reports. Each state transition records the previous and new status, typed reason, actor, run ID, timestamp, content hash, version, provider/model, and compact details.

The bounded execution path is intentionally sequential (`max_concurrent_provider_calls=1`) and supports row/report/token/spend/runtime/retry/fairness limits plus optional report/publisher filters. It checks current text/hash state, looks for a successful durable identity, and acquires a SQLite execution lease before each provider call. Retryable failures receive exponential-backoff metadata; terminal, invalid, stale, obsolete, orphaned, and already-satisfied rows do not call the provider. The canonical LLM usage ledger remains the source of provider accounting.

Operator commands (all defaults are conservative):

```powershell
# Read-only health artifact
python -m src.cli embedding-queue-health --output out/claim-embedding-queue-health.json

# Provider-free reconciliation preview, then explicit apply
python -m src.cli embedding-queue-reconcile --dry-run
python -m src.cli embedding-queue-reconcile --apply

# Bounded batch preview, then an explicitly scoped provider run
python -m src.cli embedding-queue-run --dry-run --max-rows 25 --max-reports 5
python -m src.cli embedding-queue-run --apply --max-rows 25 --max-estimated-tokens 8000 --max-estimated-cost-usd 1.0 --max-runtime-seconds 120

# Report-scoped retry and failed-row inspection
python -m src.cli embedding-queue-run --apply --report-id <report-id> --max-rows 10
python -m src.cli embedding-queue-failures --output out/claim-embedding-queue-failures.json
```

The health and command artifacts contain operational identifiers and aggregate metrics, not queue text or retrieval metadata. They expose pending age, class/status counts, processed/embedded/failed/skipped rows, avoided calls and estimated spend, actual usage estimates, call latency, and queue burn-down. Existing report publication remains non-blocking when the queue fails, and Briefings/Signals retain their deterministic fallback when no fresh embedding is available.

## Briefing and Signal Evidence Preselection

`run_cross_report_analysis` and `run_signal_candidate_extraction` read embedded claims through `analytics_store_service.read_claim_embeddings` after source/theme selection and before evidence assembly.

`assemble_cross_report_analysis_inputs` stays a pure generator step. When fresh claim embeddings are supplied, it excludes records whose `content_hash` no longer matches the selected projection, ranks embedded claim evidence by deterministic vector similarity, and applies that bounded claim set before prompt input assembly. When no fresh embeddings are available, it preserves the existing deterministic report/class/evidence ordering.

The returned `CrossReportEvidenceInputResult.semantic_preselection` summary records the mode, candidate claim count, supplied/fresh/stale embedding counts, selected embedding UIDs, fallback reason, and approximate prompt characters before and after selection. Cross-report idempotency material includes this summary so embedding-backed evidence changes cannot reuse a stale generated Briefing.

## Future Cross-Report Analytics

Future analytics can build on this foundation by querying the projection tables for relational reporting and by benchmarking/tuning embedding-backed evidence preselection. The current implementation deliberately does not add dashboards, clustering, external vector search, or a new product UI.
