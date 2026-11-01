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

The bounded execution path is intentionally sequential (`max_concurrent_provider_calls=1`) and supports row/report/token/spend/runtime/retry/fairness limits plus optional report/publisher filters. The runtime clock starts before queue-health reads and item selection, so the limit covers orchestration overhead as well as provider work. It checks current text/hash state, looks for a successful durable identity, and acquires a SQLite execution lease before each provider call. Retryable failures receive exponential-backoff metadata; terminal, invalid, stale, obsolete, orphaned, and already-satisfied rows do not call the provider. The canonical LLM usage ledger remains the source of provider accounting.

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

## Verified-fact authority and cross-report eligibility — 2026-11-01

The verified-mode projection path now treats the retained
`VerifiedAuthorityContext` as the only source of findings, metrics, evidence
lineage, and source eligibility. Before projection, the authority is rebuilt
from the retained artifacts and checked against the retained source identity,
PDF SHA-256, verified-fact digest, and canonical evidence packs. Discovery
findings, quote candidates, and legacy metric projections are not used as
verified authority; normal-mode projection remains unchanged. Full metric
objects are carried through `metric_context`, so report-specific qualifiers
and unknown fields are not discarded.

Cross-report reads retain ineligible or stale rows for diagnostics, but source
selection and theme publishability reject them under verified policy. A
verified selected source must carry the canonical source identity, PDF hash,
fact digest, authority mode, and source-validation eligibility. An
`expected_verified_sources` request automatically requires that lineage, so a
successful database write or diagnostic read cannot authorize a legacy or
stale row. The additive reports schema migration is v32; it preserves the
existing report-scoped IDs and adds the authority/lineage fields to reports,
findings, metrics, and cross-report contracts.

Checkpoint reentry applies the same authority and snapshot checks before
rendering, and qualified source identities use exact base/qualified matching
(with case-insensitive comparison only for the SHA-256 hex digest). The
provider-free regressions are in `tests/test_authority_contract_regressions.py`,
`tests/test_analytics_projection_foundation.py`,
`tests/integration/test_analytics_store_cross_report_reads.py`, and
`tests/test_report_checkpoint_lineage_validation.py`; live report processing
and publication were not run for this slice.

## Cross-report authority and publication safety — 2026-11-01

Cross-report publication now requires an explicit, machine-readable
publishability result bound to the exact selected report IDs, selected theme,
source authority snapshots, and final bounded evidence assembly. Diagnostic
results, missing authorization, stale or ineligible source snapshots, and
failed validation cannot authorize a WordPress lookup or publication step;
dry-run packages are reported as blocked instead. The package also carries
the same authority snapshot and `publish_eligible` contract used by the
publisher, so a package cannot be rebound to a different source set after
generation.

Normal and verified projections both require a passing source-validation
result. Verified rows additionally require consistent report, source identity,
PDF SHA-256, fact digest, canonical evidence IDs, page/span provenance, and
complete metric context. Unbound verified claims and quotes remain retained
storage context for diagnostics but are not promoted to canonical evidence or
the vector evidence class. Briefing source freezing filters projected source
candidates by the same eligibility flag.

The provider-free regressions cover missing and diagnostic authorization,
stale source snapshots, normal and verified eligibility, malformed and
unbound verified rows, cross-row provenance conflicts, complete metric
contexts, package binding, publisher ordering, signal compatibility, and
briefing source freezing. The focused projection/read cases are retained in
`tests/test_analytics_projection_authority.py` and
`tests/integration/test_analytics_store_cross_report_authority.py`. No
provider call, PDF acquisition, canonical artifact mutation, publication, or
WordPress write was performed.

### Cross-report publication authority and evidence-integrity correction — 2026-11-01

The follow-up correction closes the remaining publication-authority paths at
their existing boundaries. A deterministic Signal projection fallback remains
reviewable, but is now `blocked`; only an approved frozen candidate group with
the matching lowercase manifest SHA-256, projected source rows, eligible
current sources, and unchanged evidence can produce an approved Signal
projection. The optional `candidate_manifest_sha256` field is additive in the
Signal projection contract and its schema snapshot; legacy payloads remain
readable but cannot authorize publication.

Briefing publication now requires a passed final validation result regardless
of the retained compatibility setting. Failed or absent validation remains
available for generate-only and diagnostic artifacts but blocks dry-run/live
publication before WordPress work. Cross-report idempotency material version
2.2 includes the live-publication flag, validation-policy flag, and minimum
publisher policy, and cached live outcomes recheck the current live-enable
setting. Final publisher diversity is counted from the reports represented by
the bounded evidence set, while inventory counts remain preliminary screening
only.

Verified cross-report reads now reject unknown authority modes and non-exact
qualified source identities. Verified analyst claim/quote pages must be
positive and belong to the canonical finding page binding; invalid rows remain
diagnostic with precise exclusion reasons. Provider-free unit and integration
regressions exercise Signal denial, frozen-source eligibility, failed Briefing
validation, policy fingerprints, evidence-contributor coverage, malformed
authority identity, and valid/invalid page bindings. No provider call, PDF
acquisition, canonical artifact mutation, publication, or WordPress write was
performed. E18 remains **Active/PARTIAL**, Step 2 remains **PARTIAL/NO-GO**,
and Step 3 remains **unstarted/not ready** pending current-SHA real-report
editorial evidence.
