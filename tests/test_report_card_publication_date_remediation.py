from __future__ import annotations

import pytest

from src.contracts.report_artifacts import ArtifactRef, ArtifactRegistry
from src.contracts.report_card_remediation import (
    ReportCardPublicationDateRemediationRequest,
)
from src.generators.report_card_date_remediation_generator import (
    remediate_report_card_publication_date,
)
from src.utils.errors import AppError


def _registry(*, omit: str = "") -> ArtifactRegistry:
    refs = []
    for artifact_id, path in {
        "doc_map": "out/report/report_analysis/doc_map.json",
        "artifacts": "out/report/report_analysis/artifacts.json",
        "validation": "out/report/report_analysis/validation.json",
        "rendered_html": "out/report.html",
    }.items():
        if artifact_id == omit:
            continue
        refs.append(
            ArtifactRef(
                schema_version="1.0",
                artifact_id=artifact_id,
                kind=artifact_id,
                path=path,
                content_hash="hash-" + artifact_id,
                producer_step="analysis_complete",
                required=True,
                created_at_utc="2026-07-01T00:00:00+00:00",
            )
        )
    return ArtifactRegistry(schema_version="1.0", refs=refs)


def _request(**overrides) -> ReportCardPublicationDateRemediationRequest:
    data = {
        "schema_version": "1.0",
        "file_id": "file-1",
        "artifact_registry": _registry(),
        "artifacts_payload": {"summary": {"published_date": "2026-06-09"}},
        "doc_map_payload": {"title": "Report"},
        "validation_payload": {"status": "pass"},
        "rendered_html_path": "out/report.html",
        "operator_date": "",
        "operator_id": "",
        "operator_reason": "",
        "resume_stage": "analysis_complete",
    }
    data.update(overrides)
    return ReportCardPublicationDateRemediationRequest(**data)


def test_remediates_publication_date_from_source_artifacts() -> None:
    result = remediate_report_card_publication_date(_request())

    assert result.publication_date == "2026-06-09"
    assert result.date_source == "artifacts.summary.published_date"
    assert result.audit_fields["repair_source"] == result.date_source
    assert result.resume_stage == "analysis_complete"


def test_remediates_before_rendered_html_exists() -> None:
    result = remediate_report_card_publication_date(
        _request(
            artifact_registry=_registry(omit="rendered_html"),
            rendered_html_path="",
        )
    )

    assert result.publication_date == "2026-06-09"


def test_absent_source_date_fails_closed_without_operator_override() -> None:
    with pytest.raises(AppError) as exc_info:
        remediate_report_card_publication_date(
            _request(artifacts_payload={}, doc_map_payload={})
        )

    assert exc_info.value.code == "report_card_publication_date_absent"
    assert exc_info.value.retryable is False


def test_operator_override_requires_and_records_audit_fields() -> None:
    result = remediate_report_card_publication_date(
        _request(
            artifacts_payload={},
            doc_map_payload={},
            operator_date="2026-06-11",
            operator_id="editor@example.com",
            operator_reason="Publisher landing page shows the report date.",
        )
    )

    assert result.publication_date == "2026-06-11"
    assert result.date_source == "operator_override"
    assert result.audit_fields == {
        "repair_source": "operator_override",
        "operator_id": "editor@example.com",
        "operator_reason": "Publisher landing page shows the report date.",
    }


def test_registry_missing_required_artifact_ref_fails() -> None:
    with pytest.raises(AppError) as exc_info:
        remediate_report_card_publication_date(
            _request(artifact_registry=_registry(omit="doc_map"))
        )

    assert exc_info.value.code == "report_card_publication_date_registry_missing"
    assert exc_info.value.context["missing_refs"] == ["doc_map"]


def test_remediation_idempotency_key_is_deterministic() -> None:
    first = remediate_report_card_publication_date(_request())
    second = remediate_report_card_publication_date(_request())

    assert first.idempotency_key == second.idempotency_key
