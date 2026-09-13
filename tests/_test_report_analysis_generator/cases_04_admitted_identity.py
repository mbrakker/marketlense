# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_admitted_analysis_rejects_unattributed_publisher_before_provider_work(
    tmp_path,
):
    runtime = replace(
        _runtime(tmp_path),
        ctx=RunContext(
            schema_version="1.0",
            run_id="run",
            task_id="task",
            span_id="span",
            source_identity_id="source:canonical-report",
            publisher_id="drive_unattributed",
            admission_decision_hash="admission-hash",
        ),
    )

    with pytest.raises(AppError) as exc_info:
        run_report_analysis(
            runtime,
            None,
            None,
            None,
            SimpleNamespace(
                vector_store_create=lambda *args: pytest.fail("provider called")
            ),
        )

    assert exc_info.value.code == "report_canonical_identity_missing"
    assert exc_info.value.retryable is False
    assert exc_info.value.context["invalid_fields"] == ["publisher_id"]


def test_admitted_analysis_preserves_canonical_identity_when_publisher_id_is_display_name(
    tmp_path,
):
    runtime = replace(
        _runtime(tmp_path),
        ctx=replace(
            _runtime(tmp_path).ctx,
            source_identity_id="source:canonical-report",
            publisher_id="Mintel",
            admission_decision_hash="admission-hash",
        ),
        md5="content-md5-that-is-not-the-source-id",
        publisher_name="Mintel",
    )
    source = _source(runtime)
    selection = _selection(runtime, source)
    taxonomy_requests = []
    category_requests = []
    evidence_contexts = []
    artifact_contexts = []
    validation_requests = []

    deps = _deps(
        extract_taxonomy=lambda request, ctx: (
            taxonomy_requests.append(request)
            or TaxonomyExtractResponse(
                schema_version="1.0", taxonomy=["tag"], region="US", time_period="2026"
            )
        ),
        fit_report_categories_from_context=lambda request, ctx: (
            category_requests.append(request) or _fit_response()
        ),
        generate_evidence_packs=lambda **kwargs: (
            evidence_contexts.append(kwargs["ctx"])
            or {"doc_map": {"docMap": {"title": "Doc Title", "publisher": "Publisher"}}}
        ),
        generate_artifacts=lambda **kwargs: (
            artifact_contexts.append(kwargs["ctx"]) or _artifacts()
        ),
        run_validation=lambda request, *args, **kwargs: (
            validation_requests.append(request)
            or ValidationReport(
                schema_version="1.1",
                status="pass",
                issues=[],
                severity="pass",
                source_path=str(tmp_path / "out" / "validation.json"),
            )
        ),
    )

    run_report_analysis(
        runtime,
        source,
        selection,
        VectorStoreIndexingState(
            vector_store_id="vs_1",
            openai_file_id="file_1",
            vector_store_status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        deps,
    )

    assert taxonomy_requests[0].publisher_id == "Mintel"
    assert category_requests[0].source_id == "source:canonical-report"
    assert evidence_contexts[0].source_identity_id == "source:canonical-report"
    assert evidence_contexts[0].publisher_id == "Mintel"
    assert artifact_contexts[0].source_identity_id == "source:canonical-report"
    assert artifact_contexts[0].publisher_id == "Mintel"
    assert validation_requests[0].source_id == "source:canonical-report"
