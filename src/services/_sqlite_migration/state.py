from __future__ import annotations

import sqlite3

from .runner import _add_column_if_missing, _MigrationSpec

_STATE_PROCESSED_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS processed (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  processed_at INTEGER NOT NULL,
  openai_file_id TEXT,
  vector_store_id TEXT,
  vector_store_status TEXT,
  indexed_at_utc TEXT,
  last_error TEXT,
  text_validation_status TEXT,
  text_validation_reason TEXT,
  text_validation_pages_json TEXT,
  doc_map_summary_json TEXT,
  ocr_fallback_used INTEGER NOT NULL DEFAULT 0,
  ocr_pdf_path TEXT
);
"""

_STATE_INGEST_STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ingest_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at INTEGER NOT NULL
);
"""

_STATE_PUBLISHED_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS published (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  published_at INTEGER NOT NULL,
  wp_post_id INTEGER NOT NULL,
  wp_post_url TEXT NOT NULL,
  post_type TEXT NOT NULL DEFAULT ''
);
"""

_STATE_DOWNLOAD_ROUTES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_download_routes (
  normalized_url TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  route_summary TEXT NOT NULL,
  outcome TEXT NOT NULL,
  last_downloaded_file_path TEXT,
  last_final_page_url TEXT,
  updated_at INTEGER NOT NULL
);
"""

_STATE_WORKFLOW_CONTROL_OBSERVATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_control_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  observed_at_utc TEXT NOT NULL,
  run_id TEXT NOT NULL,
  workflow TEXT NOT NULL,
  step_name TEXT NOT NULL,
  route TEXT NOT NULL,
  publisher TEXT NOT NULL DEFAULT '',
  report_key TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL,
  error_code TEXT NOT NULL DEFAULT '',
  error_retryable INTEGER NOT NULL DEFAULT 0,
  error_severity TEXT NOT NULL DEFAULT '',
  latency_ms INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0.0,
  retry_count INTEGER NOT NULL DEFAULT 0,
  resource_pressure_json TEXT NOT NULL DEFAULT '{}'
);
"""

_STATE_MAIL_DELIVERY_REQUESTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mail_delivery_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key TEXT NOT NULL UNIQUE,
  source_url TEXT NOT NULL,
  report_title TEXT NOT NULL DEFAULT '',
  publisher_name TEXT NOT NULL DEFAULT '',
  delivery_email TEXT NOT NULL DEFAULT '',
  requested_after_utc TEXT NOT NULL,
  route_family TEXT NOT NULL DEFAULT '',
  route_history_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  next_attempt_after_utc TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  provider_cursor TEXT NOT NULL DEFAULT '',
  seen_provider_message_ids_json TEXT NOT NULL DEFAULT '[]',
  outcome TEXT NOT NULL DEFAULT '',
  selected_message_id TEXT NOT NULL DEFAULT '',
  downloaded_file_path TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);
"""

_STATE_MAILBOX_CANDIDATE_REJECTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mailbox_candidate_rejections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id INTEGER NOT NULL,
  provider_message_id TEXT NOT NULL,
  sender TEXT NOT NULL DEFAULT '',
  source_host TEXT NOT NULL DEFAULT '',
  link_host TEXT NOT NULL DEFAULT '',
  publisher_affinity TEXT NOT NULL DEFAULT '',
  title_token_overlap REAL NOT NULL DEFAULT 0.0,
  reason_code TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE(request_id, provider_message_id, link_host, reason_code)
);
"""

_STATE_ARTIFACT_ACQUISITION_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS artifact_acquisition_cache (
  cache_key TEXT PRIMARY KEY,
  normalized_url TEXT NOT NULL,
  publisher_scope TEXT NOT NULL,
  report_title TEXT NOT NULL,
  final_artifact_url TEXT NOT NULL,
  artifact_path TEXT NOT NULL,
  artifact_md5 TEXT NOT NULL,
  artifact_sha256 TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  route_family TEXT NOT NULL,
  outcome TEXT NOT NULL,
  downloaded_mime_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  cache_version TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
"""

_STATE_REMEDIATION_RECORDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS remediation_records (
  remediation_id TEXT PRIMARY KEY,
  dedupe_key TEXT NOT NULL UNIQUE,
  schema_version TEXT NOT NULL,
  workflow TEXT NOT NULL,
  run_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  span_id TEXT NOT NULL,
  report_id TEXT NOT NULL DEFAULT '',
  source_id TEXT NOT NULL DEFAULT '',
  publisher_id TEXT NOT NULL DEFAULT '',
  input_checksum TEXT NOT NULL DEFAULT '',
  failed_stage TEXT NOT NULL DEFAULT '',
  operation TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  error_classification TEXT NOT NULL DEFAULT 'unknown',
  retry_decision_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL,
  checkpoint_json TEXT NOT NULL DEFAULT '{}',
  reusable_artifacts_json TEXT NOT NULL DEFAULT '[]',
  committed_side_effects_json TEXT NOT NULL DEFAULT '[]',
  idempotency_keys_json TEXT NOT NULL DEFAULT '[]',
  budget_json TEXT NOT NULL DEFAULT '{}',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 1,
  cooldown_seconds INTEGER NOT NULL DEFAULT 0,
  next_eligible_at_utc TEXT NOT NULL DEFAULT '',
  action_code TEXT NOT NULL,
  operator_next_action TEXT NOT NULL DEFAULT '',
  runbook_ref TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  resolved_at_utc TEXT NOT NULL DEFAULT '',
  lease_owner TEXT NOT NULL DEFAULT '',
  lease_expires_at_utc TEXT NOT NULL DEFAULT '',
  diagnostics_json TEXT NOT NULL DEFAULT '{}',
  CHECK(
    status IN (
      'pending','leased','retrying','deferred','operator_action_required',
      'terminal','resolved','superseded'
    )
  )
);
"""

_STATE_REMEDIATION_TRANSITIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS remediation_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  remediation_id TEXT NOT NULL,
  from_status TEXT NOT NULL,
  to_status TEXT NOT NULL,
  reason TEXT NOT NULL,
  actor TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  FOREIGN KEY(remediation_id) REFERENCES remediation_records(remediation_id)
);
"""

_STATE_WORKFLOW_JOBS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_jobs (
  job_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  queue_name TEXT NOT NULL,
  job_type TEXT NOT NULL,
  job_schema_version TEXT NOT NULL,
  workflow_version TEXT NOT NULL,
  root_workflow_id TEXT NOT NULL,
  parent_job_id TEXT NOT NULL DEFAULT '',
  trigger_event_id TEXT NOT NULL DEFAULT '',
  correlation_id TEXT NOT NULL DEFAULT '',
  entity_type TEXT NOT NULL DEFAULT '',
  entity_id TEXT NOT NULL DEFAULT '',
  publisher_id TEXT NOT NULL DEFAULT '',
  source_identity_id TEXT NOT NULL DEFAULT '',
  report_id TEXT NOT NULL DEFAULT '',
  input_reference TEXT NOT NULL DEFAULT '',
  input_content_hash TEXT NOT NULL DEFAULT '',
  required_artifact_references_json TEXT NOT NULL DEFAULT '[]',
  payload_json TEXT NOT NULL DEFAULT '{}',
  output_reference TEXT NOT NULL DEFAULT '',
  output_content_hash TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT NOT NULL,
  deduplication_scope TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  available_at_utc TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL,
  lease_owner TEXT NOT NULL DEFAULT '',
  lease_expires_at_utc TEXT NOT NULL DEFAULT '',
  heartbeat_at_utc TEXT NOT NULL DEFAULT '',
  budget_profile TEXT NOT NULL DEFAULT '',
  execution_plan_hash TEXT NOT NULL DEFAULT '',
  prompt_policy_version TEXT NOT NULL DEFAULT '',
  processing_version TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  started_at_utc TEXT NOT NULL DEFAULT '',
  completed_at_utc TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  error_message_summary TEXT NOT NULL DEFAULT '',
  error_retryable INTEGER NOT NULL DEFAULT 0,
  terminal_reason TEXT NOT NULL DEFAULT '',
  remediation_id TEXT NOT NULL DEFAULT '',
  CHECK(status IN (
    'pending','leased','running','succeeded','retry_wait','budget_deferred',
    'blocked','dead_letter','cancelled'
  )),
  UNIQUE(deduplication_scope, idempotency_key)
);
"""

_STATE_WORKFLOW_JOB_ATTEMPTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_job_attempts (
  attempt_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  worker_id TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  completed_at_utc TEXT NOT NULL DEFAULT '',
  input_content_hash TEXT NOT NULL DEFAULT '',
  output_content_hash TEXT NOT NULL DEFAULT '',
  execution_plan_hash TEXT NOT NULL DEFAULT '',
  budget_decision TEXT NOT NULL DEFAULT '',
  provider_usage_json TEXT NOT NULL DEFAULT '{}',
  external_effects_json TEXT NOT NULL DEFAULT '[]',
  outcome TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(job_id) REFERENCES workflow_jobs(job_id),
  UNIQUE(job_id, attempt_number)
);
"""

_STATE_WORKFLOW_JOB_TRANSITIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_job_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  from_status TEXT NOT NULL,
  to_status TEXT NOT NULL,
  reason TEXT NOT NULL,
  actor TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(job_id) REFERENCES workflow_jobs(job_id)
);
"""

_STATE_WORKFLOW_OUTBOX_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_outbox (
  event_id TEXT PRIMARY KEY,
  event_key TEXT NOT NULL UNIQUE,
  parent_job_id TEXT NOT NULL,
  root_workflow_id TEXT NOT NULL,
  queue_name TEXT NOT NULL,
  job_type TEXT NOT NULL,
  submission_json TEXT NOT NULL,
  available_at_utc TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 20,
  status TEXT NOT NULL DEFAULT 'pending',
  lease_owner TEXT NOT NULL DEFAULT '',
  lease_expires_at_utc TEXT NOT NULL DEFAULT '',
  materialised_job_id TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  remediation_id TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  CHECK(status IN ('pending','leased','materialised','retry_wait','dead_letter'))
);
"""

_STATE_WORKFLOW_QUEUE_CONTROLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_queue_controls (
  queue_name TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'active',
  enabled INTEGER NOT NULL DEFAULT 1,
  worker_concurrency_limit INTEGER NOT NULL DEFAULT 1,
  maximum_pending INTEGER NOT NULL DEFAULT 100,
  maximum_fanout INTEGER NOT NULL DEFAULT 10,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  lease_seconds INTEGER NOT NULL DEFAULT 900,
  budget_profile TEXT NOT NULL DEFAULT '',
  retry_delay_seconds INTEGER NOT NULL DEFAULT 60,
  emergency_stop_reason TEXT NOT NULL DEFAULT '',
  updated_at_utc TEXT NOT NULL,
  updated_by TEXT NOT NULL DEFAULT ''
);
"""


def _state_db_001_create_base_tables(conn: sqlite3.Connection) -> None:
    conn.execute(_STATE_PROCESSED_TABLE_SQL)
    conn.execute(_STATE_INGEST_STATE_TABLE_SQL)
    conn.execute(_STATE_PUBLISHED_TABLE_SQL)
    conn.execute(_STATE_DOWNLOAD_ROUTES_TABLE_SQL)


def _state_db_002_add_processed_vector_columns(conn: sqlite3.Connection) -> None:
    required = {
        "openai_file_id": "TEXT",
        "vector_store_id": "TEXT",
        "vector_store_status": "TEXT",
        "indexed_at_utc": "TEXT",
        "last_error": "TEXT",
        "text_validation_status": "TEXT",
        "text_validation_reason": "TEXT",
        "text_validation_pages_json": "TEXT",
        "doc_map_summary_json": "TEXT",
    }
    for column_name, column_type in required.items():
        _add_column_if_missing(
            conn,
            table_name="processed",
            column_name=column_name,
            column_type=column_type,
        )


def _state_db_003_add_processed_ocr_columns(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        table_name="processed",
        column_name="ocr_fallback_used",
        column_type="INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        conn,
        table_name="processed",
        column_name="ocr_pdf_path",
        column_type="TEXT",
    )


def _state_db_004_add_published_post_type(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        table_name="published",
        column_name="post_type",
        column_type="TEXT NOT NULL DEFAULT ''",
    )


def _state_db_005_add_report_download_final_page_url(
    conn: sqlite3.Connection,
) -> None:
    _add_column_if_missing(
        conn,
        table_name="report_download_routes",
        column_name="last_final_page_url",
        column_type="TEXT",
    )


def _state_db_006_create_workflow_control_observations(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_STATE_WORKFLOW_CONTROL_OBSERVATIONS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_control_observations_workflow_time "
        "ON workflow_control_observations(workflow, observed_at_utc DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_control_observations_publisher "
        "ON workflow_control_observations(publisher, observed_at_utc DESC)"
    )


def _state_db_007_create_mail_delivery_requests(conn: sqlite3.Connection) -> None:
    conn.execute(_STATE_MAIL_DELIVERY_REQUESTS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mail_delivery_requests_due "
        "ON mail_delivery_requests(status, next_attempt_after_utc, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mail_delivery_requests_source "
        "ON mail_delivery_requests(source_url, delivery_email)"
    )


def _state_db_008_create_mailbox_candidate_rejections(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_STATE_MAILBOX_CANDIDATE_REJECTIONS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mailbox_candidate_rejections_request "
        "ON mailbox_candidate_rejections(request_id, expires_at_utc)"
    )


def _state_db_009_create_artifact_acquisition_cache(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_STATE_ARTIFACT_ACQUISITION_CACHE_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_acquisition_cache_url "
        "ON artifact_acquisition_cache(normalized_url, publisher_scope, report_title)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_acquisition_cache_expiry "
        "ON artifact_acquisition_cache(expires_at_utc)"
    )


def _state_db_010_create_remediation_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(_STATE_REMEDIATION_RECORDS_TABLE_SQL)
    conn.execute(_STATE_REMEDIATION_TRANSITIONS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_remediation_records_eligible "
        "ON remediation_records(status, next_eligible_at_utc, lease_expires_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_remediation_records_workflow_updated "
        "ON remediation_records(workflow, updated_at_utc DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_remediation_transitions_record_time "
        "ON remediation_transitions(remediation_id, id DESC)"
    )


def _state_db_011_create_workflow_queue(conn: sqlite3.Connection) -> None:
    """Create the single durable queue platform beside existing state truth."""
    conn.execute(_STATE_WORKFLOW_JOBS_TABLE_SQL)
    conn.execute(_STATE_WORKFLOW_JOB_ATTEMPTS_TABLE_SQL)
    conn.execute(_STATE_WORKFLOW_JOB_TRANSITIONS_TABLE_SQL)
    conn.execute(_STATE_WORKFLOW_OUTBOX_TABLE_SQL)
    conn.execute(_STATE_WORKFLOW_QUEUE_CONTROLS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_jobs_queue_due "
        "ON workflow_jobs("
        "queue_name, status, available_at_utc, priority DESC, created_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_jobs_lease_expiry "
        "ON workflow_jobs(status, lease_expires_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_jobs_entity "
        "ON workflow_jobs(entity_type, entity_id, updated_at_utc DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_jobs_root "
        "ON workflow_jobs(root_workflow_id, correlation_id, created_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_outbox_due "
        "ON workflow_outbox(status, available_at_utc, created_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_transitions_job "
        "ON workflow_job_transitions(job_id, id DESC)"
    )


def _state_db_012_create_queue_publication_and_briefing_state(
    conn: sqlite3.Connection,
) -> None:
    """Keep queue-owned approval and Briefing aggregation state out of job rows."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_publication_readiness (
          package_checksum TEXT PRIMARY KEY,
          entity_type TEXT NOT NULL,
          package_reference TEXT NOT NULL,
          validation_reference TEXT NOT NULL DEFAULT '',
          lineage_reference TEXT NOT NULL DEFAULT '',
          required_asset_status TEXT NOT NULL DEFAULT '',
          readiness_status TEXT NOT NULL,
          reason TEXT NOT NULL DEFAULT '',
          created_at_utc TEXT NOT NULL,
          updated_at_utc TEXT NOT NULL,
          CHECK(readiness_status IN (
            'awaiting_review','approved','rejected','repair_required','not_publishable'
          ))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_publication_approvals (
          approval_id TEXT PRIMARY KEY,
          package_checksum TEXT NOT NULL,
          actor_id TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '',
          action TEXT NOT NULL,
          created_at_utc TEXT NOT NULL,
          FOREIGN KEY(package_checksum)
            REFERENCES workflow_publication_readiness(package_checksum),
          UNIQUE(package_checksum, action, actor_id, created_at_utc)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_briefing_opportunities (
          opportunity_id TEXT PRIMARY KEY,
          opportunity_key TEXT NOT NULL UNIQUE,
          topic TEXT NOT NULL,
          geography TEXT NOT NULL DEFAULT '',
          rolling_window TEXT NOT NULL,
          briefing_policy_version TEXT NOT NULL,
          source_hashes_json TEXT NOT NULL DEFAULT '[]',
          publisher_ids_json TEXT NOT NULL DEFAULT '[]',
          frozen_source_manifest TEXT NOT NULL DEFAULT '',
          frozen_source_hashes_json TEXT NOT NULL DEFAULT '[]',
          status TEXT NOT NULL,
          generation_job_id TEXT NOT NULL DEFAULT '',
          last_generated_at_utc TEXT NOT NULL DEFAULT '',
          created_at_utc TEXT NOT NULL,
          updated_at_utc TEXT NOT NULL,
          CHECK(status IN ('collecting','eligible','frozen','generated','blocked'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_readiness_status "
        "ON workflow_publication_readiness(readiness_status, updated_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_briefing_status "
        "ON workflow_briefing_opportunities(status, updated_at_utc)"
    )


_STATE_DB_MIGRATIONS: tuple[_MigrationSpec, ...] = (
    _MigrationSpec(
        migration_id="state_db_001_create_base_tables",
        version=1,
        apply_fn=_state_db_001_create_base_tables,
    ),
    _MigrationSpec(
        migration_id="state_db_002_add_processed_vector_columns",
        version=2,
        apply_fn=_state_db_002_add_processed_vector_columns,
    ),
    _MigrationSpec(
        migration_id="state_db_003_add_processed_ocr_columns",
        version=3,
        apply_fn=_state_db_003_add_processed_ocr_columns,
    ),
    _MigrationSpec(
        migration_id="state_db_004_add_published_post_type",
        version=4,
        apply_fn=_state_db_004_add_published_post_type,
    ),
    _MigrationSpec(
        migration_id="state_db_005_add_report_download_final_page_url",
        version=5,
        apply_fn=_state_db_005_add_report_download_final_page_url,
    ),
    _MigrationSpec(
        migration_id="state_db_006_create_workflow_control_observations",
        version=6,
        apply_fn=_state_db_006_create_workflow_control_observations,
    ),
    _MigrationSpec(
        migration_id="state_db_007_create_mail_delivery_requests",
        version=7,
        apply_fn=_state_db_007_create_mail_delivery_requests,
    ),
    _MigrationSpec(
        migration_id="state_db_008_create_mailbox_candidate_rejections",
        version=8,
        apply_fn=_state_db_008_create_mailbox_candidate_rejections,
    ),
    _MigrationSpec(
        migration_id="state_db_009_create_artifact_acquisition_cache",
        version=9,
        apply_fn=_state_db_009_create_artifact_acquisition_cache,
    ),
    _MigrationSpec(
        migration_id="state_db_010_create_remediation_ledger",
        version=10,
        apply_fn=_state_db_010_create_remediation_ledger,
    ),
    _MigrationSpec(
        migration_id="state_db_011_create_workflow_queue",
        version=11,
        apply_fn=_state_db_011_create_workflow_queue,
    ),
    _MigrationSpec(
        migration_id="state_db_012_create_queue_publication_and_briefing_state",
        version=12,
        apply_fn=_state_db_012_create_queue_publication_and_briefing_state,
    ),
)
