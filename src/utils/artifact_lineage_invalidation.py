"""Pure policy deciding which artifact records root a selective invalidation."""

from __future__ import annotations

from src.contracts.artifact_lineage import ArtifactLineageRecord
from src.utils.errors import AppError

_SUPPORTED_CHANGE_KINDS = {"source", "prompt", "template", "crop", "validator"}


def select_invalidation_roots(
    records: list[ArtifactLineageRecord],
    *,
    change_kind: str,
    changed_value: str,
    report_id: str,
) -> list[str]:
    normalized_kind = str(change_kind).strip().lower()
    value = str(changed_value).strip()
    scope = str(report_id).strip()
    if normalized_kind not in _SUPPORTED_CHANGE_KINDS or not value:
        raise AppError(
            code="artifact_invalidation_request_invalid",
            message="Invalidation requires a supported change kind and changed value",
            retryable=False,
        )
    scoped = [record for record in records if not scope or record.report_id == scope]
    if normalized_kind == "source":
        matches = [
            record
            for record in scoped
            if record.source_id == value and record.artifact_kind == "source_pdf"
        ]
    elif normalized_kind == "prompt":
        matches = [record for record in scoped if record.prompt_hash == value]
    elif normalized_kind == "template":
        matches = [
            record for record in scoped if record.metadata.get("template_hash") == value
        ]
    elif normalized_kind == "crop":
        matches = [
            record for record in scoped if record.metadata.get("crop_hash") == value
        ]
    else:
        matches = [
            record
            for record in scoped
            if record.metadata.get("validator_hash") == value
        ]
    return sorted(record.artifact_id for record in matches if record.state == "active")
