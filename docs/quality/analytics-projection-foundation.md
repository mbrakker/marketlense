# Analytics Projection Foundation

## What Was Added

Market Lense now has an additive post-analysis projection layer for future cross-report analytics.

The layer keeps the existing per-report JSON packs, artifacts, validation outputs, vector-store analysis path, and rendered HTML behavior intact. It projects the already assembled report analysis state into normalized SQLite tables and a vector-ready queue.

Added boundaries:

- `src/contracts/analytics_projection.py`: versioned dataclass contracts for projected report rows, entity rows, vector queue rows, upsert requests, and failure requests.
- `src/generators/analytics_projection_generator.py`: deterministic mapping from existing analysis packs and artifacts into normalized projection rows.
- `src/services/analytics_store_service.py`: SQLite schema creation, migrations, idempotent upserts, scoped stale-row cleanup, and projection failure persistence.
- `src/orchestrators/analytics_projection_orchestrator.py`: sequencing for build, upsert, and typed failure recording.

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

`report_id` is the existing Drive file ID. `source_file_id` is intentionally not stored as a separate projected field when it would equal `report_id`.

Stale-row cleanup is scoped strictly to the current `report_id` and each projection-owned table independently.

## Vector Readiness

`vector_projection_queue` stages future embedding work without implementing global retrieval.

Queued rows include:

- `entity_uid`, `entity_type`, `report_id`
- `text_payload`, `content_hash`, `metadata_json`
- `content_class`
- `embedding_status`, `embedding_version`
- `created_at_utc`, `updated_at_utc`

Allowed `embedding_status` values are `pending`, `embedded`, and `failed`. New projection rows are written as `pending`. `content_hash` is computed from canonical serialized text plus embedding-relevant metadata, so future embedding workers can detect unchanged content and avoid unnecessary re-embedding.

`content_class` separates `evidence`, `derived_evidence`, and `editorial` content so future retrieval can filter presentation-only material.

## Future Cross-Report Analytics

Future analytics can build on this foundation by querying the projection tables for relational reporting and by consuming `vector_projection_queue` for global embedding jobs. The current implementation deliberately does not add dashboards, clustering, global vector search, or product workflows.
