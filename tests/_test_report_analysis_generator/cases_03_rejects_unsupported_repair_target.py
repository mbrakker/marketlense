# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_run_report_analysis_rejects_unsupported_repair_target(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)

    def _run_validation(req, settings, ctx, *, pack_name, report_name, md5):
        del req, settings, ctx, pack_name, report_name, md5
        return ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message="[custom_rule] Unsupported custom repair target",
                    severity="error",
                    affected_section="custom_pack",
                    rule_id="custom_rule",
                    repair_target="custom_pack",
                )
            ],
            severity="error",
            source_path=str(tmp_path / "out" / "validation.json"),
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {"doc_map": {}},
        generate_artifacts=lambda **kwargs: _artifacts(
            summary={
                "tldr": "x",
                "executive_summary": "x",
                "claim_evidence_map": [],
            }
        ),
        run_validation=_run_validation,
        regenerate_artifacts=lambda request: (_ for _ in ()).throw(
            AssertionError("unsupported repair target should fail before regeneration")
        ),
    )

    with pytest.raises(AppError) as excinfo:
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

    assert excinfo.value.code == "regeneration_repair_target_unsupported"
    assert excinfo.value.retryable is False

def test_run_report_analysis_snapshot_preserves_internal_payload_metadata(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    source.payload._text_density = 100.0
    source.payload._text_pages_sampled = 3
    source.payload._text_char_count = 100
    source.payload._text_not_available = False
    selection = _selection(runtime, source)
    stored_payloads: dict[str, dict] = {}

    def _analysis_pack_path(req, ctx):
        del ctx
        return SimpleNamespace(
            output_path=str(tmp_path / "out" / f"{req.pack_name}.json")
        )

    def _analysis_store_pack(req, ctx):
        del ctx
        stored_payloads[req.pack_name] = req.payload
        return SimpleNamespace(
            output_path=str(tmp_path / "out" / f"{req.pack_name}.json")
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "title": "Doc Title",
                "publisher": "Doc Publisher",
            },
            "findings": {"schema_version": "1.0", "findings": []},
        },
        generate_artifacts=lambda **kwargs: _artifacts(),
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
            source_path=str(tmp_path / "out" / "validation.json"),
        ),
        analysis_pack_path=_analysis_pack_path,
        analysis_store_pack=_analysis_store_pack,
    )

    state = run_report_analysis(
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

    snapshot = stored_payloads["analysis_vector_store"]
    assert state.normalized_payload._vector_store_id == "vs_1"
    assert state.normalized_payload._text_density == 100.0
    assert state.normalized_payload._text_pages_sampled == 3
    assert state.normalized_payload._text_char_count == 100
    assert snapshot["_vector_store_id"] == "vs_1"
    assert snapshot["_text_density"] == 100.0
    assert snapshot["_text_pages_sampled"] == 3
    assert snapshot["_text_char_count"] == 100
    assert snapshot["_evidence_packs"]["doc_map"].endswith("doc_map.json")
    assert snapshot["_evidence_packs"]["validation"].endswith("validation.json")

__all__ = [
    "test_run_report_analysis_rejects_unsupported_repair_target",
    "test_run_report_analysis_snapshot_preserves_internal_payload_metadata",
]
