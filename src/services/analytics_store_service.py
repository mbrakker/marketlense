from __future__ import annotations

"""Canonical analytics store service facade."""

from src.services._analytics_store.common import (
    DDL,
    DEFAULT_BUSY_TIMEOUT_SECONDS,
    _CONN_LOCK,
    _CROSS_REPORT_READ_CONTENT_CLASSES,
    _EMBEDDING_STATUSES,
    _REPORT_PROJECTION_COLUMNS,
    _analytics_conn,
    _configure,
    _ensure_reports_projection_columns,
    _json,
    _lineage_values,
    _table_exists,
    _uid_set,
)

from src.services._analytics_store.projection_write import (
    _delete_stale,
    _report_source_url_from_store,
    _upsert_categories,
    _upsert_claims,
    _upsert_figures,
    _upsert_findings,
    _upsert_metrics,
    _upsert_quotes,
    _upsert_report,
    _upsert_sections,
    _upsert_tags,
    _upsert_vector_queue,
    _validate_queue_row,
    record_projection_failure,
    upsert_projection,
)

from src.services._analytics_store.cross_report_read import (
    _aggregate_content_hash,
    _claim_evidence,
    _fetch_grouped_rows,
    _fetch_vector_hashes,
    _finding_evidence,
    _json_list,
    _normalized_filter_values,
    _quote_evidence,
    _raw_metric,
    _report_date,
    _report_passes_filters,
    _report_period,
    _report_publisher,
    _requested_content_classes,
    _row_text,
    _scoped_row_id,
    _source_candidate,
    _stable_row_id,
    _status_floor_values,
    read_cross_report_projected_data,
)

from src.services._analytics_store.claim_embeddings import (
    _embedding_uid,
    _matches_topics,
    _metadata_from_json,
    _record_from_row,
    _queue_item_from_row,
    _validate_embedding_record,
    claim_embedding_uid,
    persist_claim_embedding,
    read_claim_embeddings,
    read_pending_claim_embedding_rows,
)

from src.services._analytics_store.signals import (
    _candidate_from_row,
    _candidate_matches_read_request,
    _candidate_source_ref_from_dict,
    _delete_stale_signal_rows,
    _group_from_row,
    _upsert_signal_candidate,
    _upsert_signal_group,
    read_signal_candidates,
    upsert_signal_candidates,
)

__all__ = [name for name in globals() if not name.startswith("__")]
