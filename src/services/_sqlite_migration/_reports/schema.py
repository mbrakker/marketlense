from __future__ import annotations

"""Schema ownership for reports database migrations."""


_REPORTS_CORE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reports (
  file_id TEXT PRIMARY KEY,
  file_name TEXT,
  title TEXT NOT NULL,
  publisher TEXT,
  taxonomy_json TEXT NOT NULL DEFAULT '[]',
  categories_json TEXT NOT NULL DEFAULT '[]',
  region TEXT,
  time_period TEXT,
  source_url TEXT,
  html_path TEXT,
  md5 TEXT,
  page_count INTEGER,
  contents_page INTEGER,
  pdf_metadata_json TEXT,
  analysis_mode TEXT,
  vector_store_id TEXT,
  evidence_packs_json TEXT,
  report_id TEXT,
  publisher_id TEXT,
  source_md5 TEXT,
  ingest_run_id TEXT,
  analysis_run_id TEXT,
  validation_status TEXT,
  validation_severity TEXT,
  text_density REAL,
  text_not_available INTEGER,
  projection_schema_version TEXT,
  projection_version TEXT,
  projection_status TEXT NOT NULL DEFAULT 'not_projected' CHECK(projection_status IN ('not_projected','projected','failed')),
  projection_attempt_count INTEGER NOT NULL DEFAULT 0,
  projection_error_code TEXT,
  projection_error_message TEXT,
  projection_error_retryable INTEGER,
  projection_generated_at_utc TEXT,
  projection_updated_at_utc TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_REPORTS_REQUIRED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("publisher", "TEXT"),
    ("taxonomy_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("file_name", "TEXT"),
    ("source_url", "TEXT"),
    ("html_path", "TEXT"),
    ("md5", "TEXT"),
    ("categories_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("region", "TEXT"),
    ("time_period", "TEXT"),
    ("page_count", "INTEGER"),
    ("contents_page", "INTEGER"),
    ("pdf_metadata_json", "TEXT"),
    ("analysis_mode", "TEXT"),
    ("vector_store_id", "TEXT"),
    ("evidence_packs_json", "TEXT"),
    ("report_id", "TEXT"),
    ("publisher_id", "TEXT"),
    ("source_md5", "TEXT"),
    ("ingest_run_id", "TEXT"),
    ("analysis_run_id", "TEXT"),
    ("validation_status", "TEXT"),
    ("validation_severity", "TEXT"),
    ("text_density", "REAL"),
    ("text_not_available", "INTEGER"),
    ("projection_schema_version", "TEXT"),
    ("projection_version", "TEXT"),
    (
        "projection_status",
        "TEXT NOT NULL DEFAULT 'not_projected' CHECK(projection_status IN ('not_projected','projected','failed'))",
    ),
    ("projection_attempt_count", "INTEGER NOT NULL DEFAULT 0"),
    ("projection_error_code", "TEXT"),
    ("projection_error_message", "TEXT"),
    ("projection_error_retryable", "INTEGER"),
    ("projection_generated_at_utc", "TEXT"),
    ("projection_updated_at_utc", "TEXT"),
)

_REPORT_SOURCES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_domain TEXT NOT NULL,
  report_name TEXT NOT NULL,
  landing_page_url TEXT NOT NULL,
  normalized_landing_page_url TEXT NOT NULL,
  source_status TEXT NOT NULL,
  source_page_url TEXT,
  publisher_name TEXT,
  discovered_at_utc TEXT,
  discovered_on_page_number INTEGER,
  downloaded_at_utc TEXT,
  md5 TEXT,
  report_value_score REAL,
  report_value_band TEXT,
  report_value_score_json TEXT,
  report_value_scored_at_utc TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_PUBLISHERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publishers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  homepage TEXT NOT NULL,
  self_presentation TEXT NOT NULL,
  insights_url TEXT NOT NULL,
  normalized_insights_url TEXT NOT NULL DEFAULT '',
  google_folder TEXT,
  discovery_test_status TEXT,
  download_route_kind TEXT,
  download_route_summary TEXT,
  download_route_outcome TEXT,
  download_route_last_downloaded_file_path TEXT,
  download_route_last_final_page_url TEXT,
  download_route_updated_at INTEGER,
  inventory_route_kind TEXT,
  inventory_route_summary TEXT,
  inventory_route_trace_json TEXT,
  inventory_scenario_summary_json TEXT,
  inventory_route_last_final_page_url TEXT,
  inventory_route_updated_at INTEGER,
  inventory_snapshot_drive_file_id TEXT,
  inventory_snapshot_drive_file_name TEXT,
  inventory_snapshot_sha256 TEXT,
  inventory_snapshot_updated_at INTEGER,
  inventory_run_quality_json TEXT,
  inventory_run_quality_updated_at INTEGER
);
"""

_DOWNLOAD_ROUTE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publisher_download_route_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  normalized_url TEXT NOT NULL,
  source_url TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  route_summary TEXT NOT NULL,
  outcome TEXT NOT NULL,
  route_family TEXT NOT NULL,
  route_status TEXT NOT NULL,
  resolved_target_url TEXT NOT NULL,
  route_steps_json TEXT NOT NULL,
  confirmation_evidence_json TEXT NOT NULL,
  terminal_evidence_json TEXT NOT NULL DEFAULT '{}',
  browser_had_structured_result INTEGER NOT NULL,
  used_candidate_pdf_url INTEGER NOT NULL,
  used_candidate_source_page INTEGER NOT NULL,
  candidate_pdf_url TEXT,
  candidate_source_page_urls_json TEXT NOT NULL,
  candidate_discovery_provenances_json TEXT NOT NULL,
  publisher_discovery_route_kind TEXT,
  publisher_recommended_discovery_route_kind TEXT,
  blocked_reason TEXT,
  blocked_reason_detail TEXT,
  last_downloaded_file_path TEXT,
  last_final_page_url TEXT,
  onsite_capture_path TEXT,
  onsite_capture_format TEXT,
  onsite_page_count INTEGER,
  onsite_completeness_status TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  verified_successes INTEGER NOT NULL DEFAULT 0,
  last_n_outcomes_json TEXT NOT NULL DEFAULT '[]',
  confidence_score REAL NOT NULL DEFAULT 0.0,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_PRIVATE_API_CANDIDATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publisher_private_api_candidates (
  fingerprint TEXT PRIMARY KEY,
  publisher_host TEXT NOT NULL,
  endpoint_pattern TEXT NOT NULL,
  method TEXT NOT NULL,
  request_shape_summary TEXT NOT NULL,
  response_pdf_url_json_pointer TEXT NOT NULL,
  expected_status_codes_json TEXT NOT NULL,
  required_response_markers_json TEXT NOT NULL,
  fallback_route_family TEXT NOT NULL,
  route_family TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  evidence_labels_json TEXT NOT NULL,
  source_urls_json TEXT NOT NULL,
  success_count INTEGER NOT NULL DEFAULT 0,
  promoted_playbook_id TEXT NOT NULL DEFAULT '',
  promoted_at_utc TEXT NOT NULL DEFAULT '',
  first_observed_at_utc TEXT NOT NULL,
  last_observed_at_utc TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_ACQUISITION_ATTEMPT_RESOURCES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS acquisition_attempt_resources (
  attempt_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  publisher_id TEXT NOT NULL,
  source_identity_id TEXT NOT NULL,
  source_identity_status TEXT NOT NULL,
  normalized_url TEXT NOT NULL,
  route_family TEXT NOT NULL,
  route_policy_version TEXT NOT NULL,
  source_policy_compatibility_hash TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  completed_at_utc TEXT NOT NULL,
  elapsed_ms INTEGER NOT NULL,
  browser_launches INTEGER NOT NULL,
  browser_steps INTEGER NOT NULL,
  page_navigations INTEGER NOT NULL,
  screenshots INTEGER NOT NULL,
  browser_model_calls INTEGER NOT NULL,
  input_tokens INTEGER NOT NULL,
  cached_input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  drive_reads INTEGER NOT NULL,
  drive_writes INTEGER NOT NULL,
  mailbox_reads INTEGER NOT NULL,
  retry_count INTEGER NOT NULL,
  terminal_outcome TEXT NOT NULL,
  terminal_reason TEXT NOT NULL,
  verified_artifact_hash TEXT NOT NULL,
  estimated_cost_usd REAL NOT NULL,
  avoided_operations_json TEXT NOT NULL,
  incomplete_fields_json TEXT NOT NULL,
  revalidation_override INTEGER NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_ACQUISITION_ROUTE_SUPPRESSIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS acquisition_route_suppressions (
  decision_id TEXT PRIMARY KEY,
  normalized_url TEXT NOT NULL,
  publisher_id TEXT NOT NULL,
  route_family TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  source_policy_compatibility_hash TEXT NOT NULL,
  reason TEXT NOT NULL,
  sample_size INTEGER NOT NULL,
  terminal_failure_count INTEGER NOT NULL,
  terminal_failure_rate REAL NOT NULL,
  activated_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  status TEXT NOT NULL,
  superseded_at_utc TEXT NOT NULL DEFAULT '',
  revalidation_attempt_id TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_INVENTORY_RECOVERY_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publisher_inventory_candidate_recovery_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  normalized_url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  source_surface_class TEXT NOT NULL,
  verification_class TEXT NOT NULL,
  recovery_action TEXT NOT NULL,
  last_outcome TEXT NOT NULL,
  last_http_status INTEGER,
  last_error_marker TEXT,
  updated_at_utc TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_INVENTORY_ROUTE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publisher_inventory_route_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  normalized_url TEXT NOT NULL,
  source_host TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  outcome TEXT NOT NULL,
  status TEXT NOT NULL,
  quality_band TEXT NOT NULL,
  recommended_route_kind TEXT NOT NULL,
  used_memory_route INTEGER NOT NULL,
  page_count INTEGER NOT NULL,
  raw_candidate_count INTEGER NOT NULL,
  current_report_count INTEGER NOT NULL,
  raw_new_report_count INTEGER NOT NULL,
  screened_new_report_count INTEGER NOT NULL,
  qualified_new_report_count INTEGER NOT NULL,
  snapshot_changed INTEGER NOT NULL,
  requires_review INTEGER NOT NULL,
  scenario_class TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_REPORT_SECTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_sections (
  section_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  key_points_json TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);
"""

_REPORT_FINDINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_findings (
  finding_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  finding_id TEXT NOT NULL,
  text TEXT NOT NULL,
  evidence TEXT NOT NULL,
  confidence TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);
"""

_REPORT_METRICS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_metrics (
  metric_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  metric_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  value TEXT NOT NULL,
  unit TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);
"""

_REPORT_QUOTES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_quotes (
  quote_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  quote_id TEXT NOT NULL,
  text TEXT NOT NULL,
  speaker TEXT NOT NULL,
  citation TEXT NOT NULL,
  page INTEGER,
  evidence_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);
"""

_REPORT_CLAIMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_claims (
  claim_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  claim TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  evidence TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);
"""

_REPORT_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_tags (
  tag_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  tag_type TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);
"""

_REPORT_CATEGORIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_categories (
  category_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  category_id TEXT NOT NULL,
  label TEXT NOT NULL,
  fit_score REAL NOT NULL,
  decision TEXT NOT NULL,
  selected INTEGER NOT NULL,
  evidence_sections_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);
"""

_REPORT_FIGURES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_figures (
  figure_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  image_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  page INTEGER NOT NULL,
  is_primary INTEGER NOT NULL,
  detected_caption TEXT NOT NULL,
  generated_caption TEXT NOT NULL,
  display_caption TEXT NOT NULL,
  caption_source TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);
"""

_VECTOR_PROJECTION_QUEUE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vector_projection_queue (
  entity_uid TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  report_id TEXT NOT NULL,
  text_payload TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  content_class TEXT NOT NULL,
  embedding_status TEXT NOT NULL CHECK(embedding_status IN ('pending','embedded','failed')),
  embedding_version TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);
"""

_CLAIM_EMBEDDINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS claim_embeddings (
  embedding_uid TEXT PRIMARY KEY,
  claim_uid TEXT NOT NULL,
  entity_uid TEXT NOT NULL,
  report_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  embedding_version TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dimensions INTEGER,
  vector_json TEXT,
  external_vector_id TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('embedded','failed')),
  generated_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  attempt_count INTEGER NOT NULL,
  error_code TEXT NOT NULL,
  error_message TEXT NOT NULL,
  error_retryable INTEGER NOT NULL,
  error_severity TEXT NOT NULL
);
"""

_ARTIFACT_LINEAGE_RECORDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS artifact_lineage_records (
  artifact_id TEXT PRIMARY KEY,
  artifact_kind TEXT NOT NULL,
  report_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  storage_ref TEXT NOT NULL,
  producer TEXT NOT NULL,
  schema_version_used TEXT NOT NULL,
  processing_version TEXT NOT NULL,
  prompt_hash TEXT NOT NULL,
  model_provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  model_parameters_hash TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL
);
"""

_CLAIM_EMBEDDING_QUEUE_TRANSITIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS claim_embedding_queue_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_uid TEXT NOT NULL,
  report_id TEXT NOT NULL,
  prior_status TEXT NOT NULL,
  new_status TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  actor TEXT NOT NULL,
  run_id TEXT NOT NULL,
  timestamp_utc TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  embedding_version TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  details_json TEXT NOT NULL
);
"""

_ARTIFACT_LINEAGE_DEPENDENCIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS artifact_lineage_dependencies (
  artifact_id TEXT NOT NULL REFERENCES artifact_lineage_records(artifact_id),
  dependency_artifact_id TEXT NOT NULL REFERENCES artifact_lineage_records(artifact_id),
  PRIMARY KEY(artifact_id, dependency_artifact_id)
);
"""

_ARTIFACT_LINEAGE_STATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS artifact_lineage_states (
  artifact_id TEXT PRIMARY KEY REFERENCES artifact_lineage_records(artifact_id),
  state TEXT NOT NULL CHECK(state IN ('active','invalidated','superseded')),
  invalidation_reason TEXT NOT NULL,
  superseded_by TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);
"""

_ARTIFACT_EXECUTION_PLAN_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS artifact_execution_plan_runs (
  plan_hash TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  execution_intent TEXT NOT NULL,
  execution_mode TEXT NOT NULL,
  planned_stages_json TEXT NOT NULL,
  planned_external_calls_json TEXT NOT NULL,
  planned_side_effects_json TEXT NOT NULL DEFAULT '[]',
  planned_prompt_families_json TEXT NOT NULL DEFAULT '[]',
  reusable_artifact_ids_json TEXT NOT NULL DEFAULT '[]',
  actual_stages_json TEXT NOT NULL DEFAULT '[]',
  actual_external_calls_json TEXT NOT NULL DEFAULT '[]',
  actual_side_effects_json TEXT NOT NULL DEFAULT '[]',
  actual_prompt_families_json TEXT NOT NULL DEFAULT '[]',
  duration_ms INTEGER NOT NULL DEFAULT 0,
  actual_cost_usd REAL,
  estimated_avoided_cost_usd REAL,
  execution_status TEXT NOT NULL DEFAULT 'planned',
  divergence_json TEXT NOT NULL DEFAULT '{}',
  created_at_utc TEXT NOT NULL,
  completed_at_utc TEXT NOT NULL DEFAULT ''
);
"""

_SOURCE_PUBLICATION_METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS source_publication_metadata (
  source_record_id INTEGER PRIMARY KEY REFERENCES report_sources(id),
  schema_version TEXT NOT NULL,
  publication_date TEXT NOT NULL DEFAULT '',
  publication_date_precision TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  retrieved_at_utc TEXT NOT NULL DEFAULT '',
  evidence_kind TEXT NOT NULL DEFAULT '',
  evidence_locator TEXT NOT NULL DEFAULT '',
  evidence_value_hash TEXT NOT NULL DEFAULT '',
  evidence_status TEXT NOT NULL,
  contradiction_status TEXT NOT NULL,
  observed_values_json TEXT NOT NULL DEFAULT '[]',
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);
"""

_SOURCE_IDENTITY_OBSERVATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS source_identity_observations (
  observation_id TEXT PRIMARY KEY,
  source_record_id INTEGER NOT NULL REFERENCES report_sources(id),
  schema_version TEXT NOT NULL,
  canonical_title TEXT NOT NULL DEFAULT '',
  title_evidence_locator TEXT NOT NULL DEFAULT '',
  publisher_id TEXT NOT NULL DEFAULT '',
  publisher_name TEXT NOT NULL DEFAULT '',
  canonical_landing_page_url TEXT NOT NULL DEFAULT '',
  acquired_artifact_url TEXT NOT NULL DEFAULT '',
  source_page_url TEXT NOT NULL DEFAULT '',
  publication_date TEXT NOT NULL DEFAULT '',
  publication_date_status TEXT NOT NULL DEFAULT 'unknown',
  publication_date_evidence_locator TEXT NOT NULL DEFAULT '',
  discovered_at_utc TEXT NOT NULL DEFAULT '',
  retrieved_at_utc TEXT NOT NULL DEFAULT '',
  acquisition_route TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL DEFAULT '',
  resolution_method TEXT NOT NULL DEFAULT '',
  identity_confidence TEXT NOT NULL DEFAULT 'unknown',
  identity_issues_json TEXT NOT NULL DEFAULT '[]',
  supersedes_source_identity_id TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL
);
"""

_SOURCE_IDENTITY_RESOLUTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS source_identity_resolutions (
  source_record_id INTEGER PRIMARY KEY REFERENCES report_sources(id),
  schema_version TEXT NOT NULL,
  source_identity_id TEXT NOT NULL,
  canonical_title TEXT NOT NULL DEFAULT '',
  title_evidence_locator TEXT NOT NULL DEFAULT '',
  publisher_id TEXT NOT NULL DEFAULT '',
  publisher_name TEXT NOT NULL DEFAULT '',
  canonical_landing_page_url TEXT NOT NULL DEFAULT '',
  acquired_artifact_url TEXT NOT NULL DEFAULT '',
  source_page_url TEXT NOT NULL DEFAULT '',
  publication_date TEXT NOT NULL DEFAULT '',
  publication_date_status TEXT NOT NULL DEFAULT 'unknown',
  publication_date_evidence_locator TEXT NOT NULL DEFAULT '',
  discovered_at_utc TEXT NOT NULL DEFAULT '',
  retrieved_at_utc TEXT NOT NULL DEFAULT '',
  acquisition_route TEXT NOT NULL DEFAULT '',
  content_hash TEXT NOT NULL DEFAULT '',
  resolution_method TEXT NOT NULL DEFAULT '',
  identity_confidence TEXT NOT NULL DEFAULT 'unknown',
  identity_issues_json TEXT NOT NULL DEFAULT '[]',
  supersedes_source_identity_id TEXT NOT NULL DEFAULT '',
  identity_status TEXT NOT NULL DEFAULT 'unknown',
  source_metadata_hash TEXT NOT NULL DEFAULT '',
  observation_count INTEGER NOT NULL DEFAULT 0,
  resolved_at_utc TEXT NOT NULL
);
"""

_REPORT_SOURCE_REUSE_TELEMETRY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_source_reuse_telemetry (
  decision_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  incoming_file_id TEXT NOT NULL,
  incoming_source_reference_hash TEXT NOT NULL,
  canonical_source_identity TEXT NOT NULL DEFAULT '',
  source_content_hash TEXT NOT NULL DEFAULT '',
  matched_report_id TEXT NOT NULL DEFAULT '',
  matched_source_metadata_hash TEXT NOT NULL DEFAULT '',
  decision TEXT NOT NULL,
  decision_reason TEXT NOT NULL,
  highest_reused_checkpoint TEXT NOT NULL DEFAULT '',
  reused_stages_json TEXT NOT NULL DEFAULT '[]',
  regenerated_stages_json TEXT NOT NULL DEFAULT '[]',
  acquisition_actions_avoided INTEGER NOT NULL DEFAULT 0,
  browser_launches_avoided INTEGER NOT NULL DEFAULT 0,
  pdf_parse_avoided INTEGER NOT NULL DEFAULT 0,
  ocr_avoided INTEGER NOT NULL DEFAULT 0,
  extraction_avoided INTEGER NOT NULL DEFAULT 0,
  vector_work_avoided INTEGER NOT NULL DEFAULT 0,
  model_calls_avoided_status TEXT NOT NULL DEFAULT 'unavailable',
  model_calls_avoided INTEGER NOT NULL DEFAULT 0,
  tokens_avoided_status TEXT NOT NULL DEFAULT 'unavailable',
  input_tokens_avoided INTEGER NOT NULL DEFAULT 0,
  output_tokens_avoided INTEGER NOT NULL DEFAULT 0,
  estimated_cost_avoided_status TEXT NOT NULL DEFAULT 'unavailable',
  estimated_cost_avoided_usd REAL NOT NULL DEFAULT 0,
  created_at_utc TEXT NOT NULL
);
"""

_SIGNAL_CANDIDATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signal_candidates (
  candidate_id TEXT PRIMARY KEY,
  extraction_request_id TEXT NOT NULL,
  candidate_type TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  confidence REAL NOT NULL,
  strength REAL NOT NULL,
  support_level TEXT NOT NULL,
  caveats_json TEXT NOT NULL,
  source_report_ids_json TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL,
  source_refs_json TEXT NOT NULL,
  raw_source_context_json TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  validation_notes_json TEXT NOT NULL,
  group_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  generated_at_utc TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_SIGNAL_CANDIDATE_GROUPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signal_candidate_groups (
  group_id TEXT PRIMARY KEY,
  extraction_request_id TEXT NOT NULL,
  stable_key TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  support_level TEXT NOT NULL,
  candidate_ids_json TEXT NOT NULL,
  source_report_ids_json TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL,
  caveats_json TEXT NOT NULL,
  raw_group_context_json TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  generated_at_utc TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_CORPUS_REHABILITATION_CAMPAIGNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS corpus_rehabilitation_campaigns (
  campaign_id TEXT PRIMARY KEY,
  plan_hash TEXT NOT NULL UNIQUE,
  approval_hash TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('planned','approved','submitted','completed','held')),
  batch_size INTEGER NOT NULL,
  planned_provider_calls INTEGER NOT NULL DEFAULT 0,
  actual_provider_calls INTEGER NOT NULL DEFAULT 0,
  planned_cost_usd REAL,
  actual_cost_usd REAL,
  created_at_utc TEXT NOT NULL,
  approved_at_utc TEXT NOT NULL DEFAULT '',
  submitted_at_utc TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL
);
"""

_CORPUS_REHABILITATION_CAMPAIGN_ITEMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS corpus_rehabilitation_campaign_items (
  campaign_id TEXT NOT NULL REFERENCES corpus_rehabilitation_campaigns(campaign_id),
  report_id TEXT NOT NULL,
  classification TEXT NOT NULL,
  disposition TEXT NOT NULL,
  source_checksum TEXT NOT NULL,
  retained_reference TEXT NOT NULL,
  reusable_artifact_ids_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('ready_for_approval','queued','completed','operator_held')),
  reason TEXT NOT NULL,
  queue_job_id TEXT NOT NULL DEFAULT '',
  actual_provider_calls INTEGER NOT NULL DEFAULT 0,
  actual_cost_usd REAL,
  PRIMARY KEY(campaign_id, report_id)
);
"""

_VALIDATION_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS validation_runs (
  validation_run_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  cohort_id TEXT NOT NULL,
  workflow_run_id TEXT NOT NULL,
  configuration_hash TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  producer_build_identity TEXT NOT NULL,
  created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS validation_run_cohort_members (
  validation_run_id TEXT NOT NULL REFERENCES validation_runs(validation_run_id),
  cohort_id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  publisher_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  source_identity_id TEXT NOT NULL,
  discovered_at_utc TEXT NOT NULL,
  PRIMARY KEY(validation_run_id, report_id)
);
CREATE TABLE IF NOT EXISTS validation_run_entity_attempts (
  attempt_id TEXT PRIMARY KEY,
  validation_run_id TEXT NOT NULL REFERENCES validation_runs(validation_run_id),
  cohort_id TEXT NOT NULL,
  entity_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  publisher_id TEXT NOT NULL,
  report_id TEXT NOT NULL,
  source_identity_id TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  parent_attempt_number INTEGER NOT NULL DEFAULT 0,
  cohort_disposition TEXT NOT NULL,
  is_current INTEGER NOT NULL,
  terminal_outcome TEXT NOT NULL DEFAULT '',
  terminal_stage TEXT NOT NULL DEFAULT '',
  failure_code TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL,
  completed_at_utc TEXT NOT NULL DEFAULT '',
  UNIQUE(validation_run_id, entity_key, attempt_number)
);
CREATE TABLE IF NOT EXISTS validation_run_stage_records (
  stage_record_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL REFERENCES validation_run_entity_attempts(attempt_id),
  validation_run_id TEXT NOT NULL REFERENCES validation_runs(validation_run_id),
  cohort_id TEXT NOT NULL,
  workflow_run_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  input_artifact_ids_json TEXT NOT NULL,
  output_artifact_ids_json TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  completed_at_utc TEXT NOT NULL,
  terminal_outcome TEXT NOT NULL,
  failure_code TEXT NOT NULL,
  retryable INTEGER NOT NULL,
  repair_disposition TEXT NOT NULL,
  duplicate_disposition TEXT NOT NULL,
  supersession_state TEXT NOT NULL,
  idempotency_state TEXT NOT NULL,
  configuration_hash TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  producer_build_identity TEXT NOT NULL,
  entity_terminal INTEGER NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE(attempt_id, stage)
);
"""
