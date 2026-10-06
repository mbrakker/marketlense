# ruff: noqa: F401,F403,F405
from __future__ import annotations

from dataclasses import replace

from ._shared import *  # noqa: F401,F403

__all__ = [
    "test_evidence_pack_family_reuses_retained_output_before_model_call",
    "test_generate_evidence_packs_success",
    "test_scope_reuses_doc_map_search_results_without_file_search",
    "test_scope_schema_repair_reuses_shared_retrieval_without_file_search",
    "test_doc_map_schema_repair_reuses_original_search_results",
    "test_evidence_pack_outcome_records_caller_prompt_family",
    "test_generate_evidence_packs_creates_context_when_missing",
    "test_generate_evidence_packs_marks_optional_empty_pack_as_abstained",
    "test_generate_evidence_packs_passes_doc_map_sections_to_findings_and_retains_links",
    "test_findings_context_retains_counterbalancing_major_docmap_sections",
    "test_generate_evidence_packs_logs_prompt_observability_and_response_metadata",
    "test_generate_evidence_packs_handles_missing_json",
    "test_generate_evidence_packs_propagates_retryable_app_error",
    "test_generate_evidence_packs_rejects_doc_map_with_only_doc_id",
    "test_generate_evidence_packs_recovers_identifier_only_doc_map",
    "test_generate_evidence_packs_recovers_doc_map_once_inside_shared_service",
    "test_generate_evidence_packs_parses_doc_map_json_from_text_fallback",
    "test_generate_evidence_packs_normalizes_docmap_wrapper",
    "test_generate_evidence_packs_normalizes_docmap_camelcase_wrapper",
    "test_generate_evidence_packs_normalizes_document_structure_shape",
    "test_generate_evidence_packs_normalizes_document_level_aliases",
    "test_generate_evidence_packs_normalizes_docmap_brief_aliases",
    "test_generate_evidence_packs_derives_docmap_publisher_from_document_title",
    "test_generate_evidence_packs_coerces_docmap_object_fields_to_schema_types",
    "test_generate_evidence_packs_warns_on_doc_map_sections_missing_summary",
    "test_generate_evidence_packs_normalizes_legacy_findings_shape",
    "test_generate_evidence_packs_persists_untrusted_findings_exclusion",
    "test_legacy_unfiltered_prompt_family_cannot_restore_findings",
    "test_generate_evidence_packs_parses_limitations_json_array_from_text",
    "test_generate_evidence_packs_normalizes_quote_candidates_shape",
    "test_generate_evidence_packs_uses_registry_subset",
]


__all__ = [name for name in globals() if not name.startswith("__")]
