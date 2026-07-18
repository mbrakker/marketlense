# Generated Capability Manifest

Generated from CLI registrations, configuration example, architecture policy, orchestrator modules, and JSON schemas. It is a factual inventory, not product or architecture prose. Regenerate with `python scripts/docs/generate_references.py`.

## Source inputs

- [`src/_cli`](../../src/_cli)
- [`src/config/app.example.yaml`](../../src/config/app.example.yaml)
- [`docs/quality/architecture_policy.yaml`](../../docs/quality/architecture_policy.yaml) (schema version `1.0`)
- [`src/orchestrators`](../../src/orchestrators)
- [`src/schemas`](../../src/schemas)

## External-system ownership

| System | Canonical service |
| --- | --- |
| `browser_runtime` | `src/services/browser_report_download_service.py` |
| `email_imap` | `src/services/mailbox_acquisition_service.py` |
| `filesystem` | `src/services/file_service.py` |
| `google_drive` | `src/services/drive_service.py` |
| `http_network` | `src/services/_http_acquisition.py` |
| `llm_providers` | `src/services/llm_service.py` |
| `pdf_ocr_stack` | `src/services/pdf_service.py` |
| `sqlite` | `src/services/state_service.py` |
| `vector_store` | `src/services/llm_service.py` |
| `wordpress` | `src/services/wordpress_service.py` |

## Public orchestrator modules

- `src/orchestrators/acquisition_audit_orchestrator.py`
- `src/orchestrators/analytics_projection_orchestrator.py`
- `src/orchestrators/candidate_extraction_orchestrator.py`
- `src/orchestrators/claim_embedding_orchestrator.py`
- `src/orchestrators/cost_reporting_orchestrator.py`
- `src/orchestrators/cover_image_orchestrator.py`
- `src/orchestrators/cross_report_analysis_orchestrator.py`
- `src/orchestrators/deferred_work_orchestrator.py`
- `src/orchestrators/ingest_file_orchestrator.py`
- `src/orchestrators/ingest_orchestrator.py`
- `src/orchestrators/mail_report_acquisition_orchestrator.py`
- `src/orchestrators/ops_dashboard_orchestrator.py`
- `src/orchestrators/pipeline_preflight_orchestrator.py`
- `src/orchestrators/publish_orchestrator.py`
- `src/orchestrators/publish_queue_orchestrator.py`
- `src/orchestrators/publisher_inventory_orchestrator.py`
- `src/orchestrators/publisher_sync_orchestrator.py`
- `src/orchestrators/recategorize_orchestrator.py`
- `src/orchestrators/remediation_orchestrator.py`
- `src/orchestrators/report_analysis_orchestrator.py`
- `src/orchestrators/report_card_date_remediation_orchestrator.py`
- `src/orchestrators/report_download_orchestrator.py`
- `src/orchestrators/report_generation_orchestrator.py`
- `src/orchestrators/report_pipeline_orchestrator.py`
- `src/orchestrators/retry_orchestrator.py`
- `src/orchestrators/retry_telemetry_orchestrator.py`
- `src/orchestrators/signal_candidate_orchestrator.py`
- `src/orchestrators/signal_post_orchestrator.py`
- `src/orchestrators/ui_run_control_orchestrator.py`
- `src/orchestrators/ui_run_execution_orchestrator.py`
- `src/orchestrators/ui_run_replay_orchestrator.py`
- `src/orchestrators/vector_store_retention_orchestrator.py`
- `src/orchestrators/wordpress_intelligence_projection_orchestrator.py`
- `src/orchestrators/workflow_control_orchestrator.py`
- `src/orchestrators/workflow_queue_orchestrator.py`
- `src/orchestrators/workflow_worker_orchestrator.py`
- `src/orchestrators/wp_category_update_orchestrator.py`

## Registered CLI commands

- `audit-acquisition-paths`
- `backfill-artifact-lineage`
- `browser-doctor`
- `cost-report`
- `deferred-work`
- `deferred-work-reap`
- `discover-publisher-inventory`
- `download-report`
- `drive-oauth-login`
- `embedding-queue-failures`
- `embedding-queue-health`
- `embedding-queue-reconcile`
- `embedding-queue-run`
- `extract-candidates`
- `generate-covers`
- `generate-cross-report-analysis`
- `ingest`
- `plan`
- `poll-mail-report`
- `promote-private-api-playbook`
- `publish-wp`
- `queue-approve-publication`
- `queue-cancel`
- `queue-drain`
- `queue-health`
- `queue-inspect-job`
- `queue-list`
- `queue-materialize-outbox`
- `queue-migrate-deferred-work`
- `queue-pause`
- `queue-reconcile`
- `queue-release-expired-leases`
- `queue-requeue`
- `queue-resume`
- `queue-submit-acquisition`
- `queue-submit-discovery`
- `queue-submit-source-ingest`
- `reap-ui-dead-letters`
- `recategorize`
- `remediation-soak`
- `remediations`
- `replay-run`
- `sync-publishers`
- `sync-wordpress-intelligence`
- `trace-run`
- `ui-run-worker`
- `update-wp-categories`
- `workflow-worker`

## JSON schemas

- `src/schemas/artifacts.schema.json`
- `src/schemas/context_category_fit.schema.json`
- `src/schemas/contradictions_pack.schema.json`
- `src/schemas/doc_map.schema.json`
- `src/schemas/evidence_pack.schema.json`
- `src/schemas/findings_pack.schema.json`
- `src/schemas/key_metrics_pack.schema.json`
- `src/schemas/limitations_pack.schema.json`
- `src/schemas/methods_pack.schema.json`
- `src/schemas/quote_candidates_pack.schema.json`
- `src/schemas/recommendations_pack.schema.json`
- `src/schemas/risk_register_pack.schema.json`
- `src/schemas/scope_pack.schema.json`
- `src/schemas/taxonomy.schema.json`
- `src/schemas/validation_report.schema.json`
