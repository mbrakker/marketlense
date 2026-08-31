from types import SimpleNamespace

from src.contracts.drive import DriveFile
from src.contracts.run_context import RunContext
from src.orchestrators._report_generation_orchestrator.workflow import (
    _admission_context_identity,
    _resolve_runtime_source_identity,
)
from src.utils.errors import AppError


def test_runtime_source_identity_uses_verified_admission_context_when_store_is_empty(
    ingest_settings,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="drive-file",
        name="market-report.pdf",
        mime_type="application/pdf",
        md5_checksum="a" * 32,
        modified_time="2026-08-31T00:00:00Z",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run",
        task_id="task",
        span_id="span",
        source_identity_id="source:admitted-report",
        publisher_id="Verified Publisher",
        admission_decision_hash="admission-hash",
    )
    unresolved = SimpleNamespace(
        publisher_name="",
        report_name="",
        source_url="",
    )
    dependencies = SimpleNamespace(
        render=SimpleNamespace(
            resolve_report_source_identity=lambda request, context: unresolved,
            get_report_source_identity=lambda request, context: SimpleNamespace(
                resolution=SimpleNamespace(
                    publisher_name="",
                    canonical_title="",
                    canonical_landing_page_url="",
                    identity_status="unknown",
                    source_metadata_hash="",
                )
            ),
            get_report_publication_metadata=lambda request, context: SimpleNamespace(
                metadata=SimpleNamespace(evidence_status="unknown"),
                resolution_source="unresolved",
            ),
        )
    )

    publisher, source_report_name, source_url, _, identity = (
        _resolve_runtime_source_identity(
            file=file,
            settings=ingest_settings,
            md5=file.md5_checksum,
            ctx=ctx,
            deps=dependencies,
        )
    )

    assert publisher == "Verified Publisher"
    assert source_report_name == "market-report.pdf"
    assert source_url == ""
    assert identity.source_identity_id == "source:admitted-report"
    assert identity.publisher_name == "Verified Publisher"
    assert identity.identity_status == "resolved"


def test_admission_context_identity_does_not_accept_unattributed_publishers() -> None:
    identity = _admission_context_identity(
        RunContext(
            schema_version="1.0",
            run_id="run",
            task_id="task",
            span_id="span",
            source_identity_id="source:md5-only",
            publisher_id="drive_unattributed",
            admission_decision_hash="admission-hash",
        ),
        fallback_report_name="market-report.pdf",
    )

    assert identity is None


def test_runtime_source_identity_uses_admission_context_when_store_lookup_errors(
    ingest_settings,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="drive-file",
        name="market-report.pdf",
        mime_type="application/pdf",
        md5_checksum="a" * 32,
        modified_time="2026-08-31T00:00:00Z",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run",
        task_id="task",
        span_id="span",
        source_identity_id="source:admitted-report",
        publisher_id="Verified Publisher",
        admission_decision_hash="admission-hash",
    )

    def _store_unavailable(request, context):
        del request, context
        raise AppError(
            code="report_store_unavailable",
            message="temporary store failure",
            retryable=True,
        )

    dependencies = SimpleNamespace(
        render=SimpleNamespace(
            resolve_report_source_identity=_store_unavailable,
            get_report_source_identity=_store_unavailable,
            get_report_publication_metadata=_store_unavailable,
        )
    )

    publisher, _, _, publication_metadata, identity = _resolve_runtime_source_identity(
        file=file,
        settings=ingest_settings,
        md5=file.md5_checksum,
        ctx=ctx,
        deps=dependencies,
    )

    assert publisher == "Verified Publisher"
    assert publication_metadata.evidence_status == "unknown"
    assert identity.source_identity_id == "source:admitted-report"
