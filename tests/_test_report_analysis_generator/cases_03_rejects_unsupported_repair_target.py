# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


def test_load_retained_claim_candidate_binds_to_promoted_artifacts(tmp_path):
    runtime = _runtime(tmp_path)
    candidate_artifacts = {"summary": {"tldr": "Promoted copy."}}
    artifact_hash = sha256_json(candidate_artifacts)
    candidate_package = {
        "schema_version": "1.4",
        "artifact_hash": artifact_hash,
        "package_hash": "promoted-package-hash",
    }
    read_requests = []

    def _analysis_pack_path(request, _ctx):
        return SimpleNamespace(output_path=f"candidate/{request.pack_name}.json")

    def _read_json(request, _ctx):
        read_requests.append(request)
        return SimpleNamespace(payload=candidate_package)

    dependencies = _deps(
        analysis_pack_path=_analysis_pack_path,
        read_json=_read_json,
    )

    loaded_package = _load_candidate_claim_validation_for_promotion(
        runtime=runtime,
        dependencies=dependencies,
        candidate_validation_pack_name="validation_regen_candidate_2",
        expected_artifact_hash=artifact_hash,
        ctx=runtime.ctx,
    )

    assert loaded_package == candidate_package
    assert len(read_requests) == 1
    assert read_requests[0].path.endswith(
        "validation_regen_candidate_2_retained_claim_validation_candidate.json"
    )


def test_store_promoted_retained_claim_candidate_to_report_scoped_pack(tmp_path):
    runtime = _runtime(tmp_path)
    stored_requests = []
    dependencies = _deps(
        analysis_store_pack=lambda request, _ctx: (
            stored_requests.append(request)
            or SimpleNamespace(output_path=f"promoted/{request.pack_name}.json")
        )
    )
    payload = {"schema_version": "1.4", "artifact_hash": "current"}

    stored_path = _store_promoted_candidate_claim_validation(
        runtime=runtime,
        dependencies=dependencies,
        candidate_package=payload,
        ctx=runtime.ctx,
    )

    assert len(stored_requests) == 1
    assert stored_requests[0].pack_name == (
        "validation_retained_claim_validation_candidate"
    )
    assert stored_requests[0].payload == payload
    assert stored_path.endswith("validation_retained_claim_validation_candidate.json")


def test_long_validation_candidate_pack_stores_and_loads_after_path_compaction(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    pack_name = "validation_regen_candidate_3_retained_claim_validation_candidate"
    report_slug = "very-long-report-slug-for-a-frozen-reliability-cohort-member"
    output_dir = tmp_path / "isolated-cohort"
    pre_compaction_path = (
        output_dir / ("a" * 12) / "report_analysis" / f"{pack_name}.json"
    )
    padding_length = 260 - len(str(pre_compaction_path.resolve()))
    output_dir = output_dir / ("x" * padding_length)
    old_slug_only_path = (
        output_dir / ("a" * 12) / "report_analysis" / f"{pack_name}.json"
    )
    assert len(str(old_slug_only_path.resolve())) == 261
    runtime = replace(
        runtime,
        settings=replace(runtime.settings, output_dir=str(output_dir)),
        report_name=report_slug,
    )
    candidate_artifacts = {"summary": {"tldr": "Promoted copy."}}
    artifact_hash = sha256_json(candidate_artifacts)
    candidate_package = {
        "schema_version": "1.4",
        "artifact_hash": artifact_hash,
        "package_hash": "b" * 64,
        "results": [],
        "readiness_status": "awaiting_review",
        "unsupported_factual_count": 0,
        "unresolved_factual_count": 0,
        "deterministic_pass_count": 0,
        "semantic_validation_count": 0,
        "semantic_execution_identities": [],
        "validation_identity": None,
        "lineage": None,
    }
    dependencies = _deps(
        analysis_pack_path=report_analysis_store_service.pack_path,
        analysis_store_pack=report_analysis_store_service.store_pack,
        read_json=file_service.read_json,
    )
    stored_path = report_analysis_store_service.store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            pack_name=pack_name,
            payload=candidate_package,
            report_slug=report_slug,
        ),
        runtime.ctx,
    ).output_path

    loaded_package = _load_candidate_claim_validation_for_promotion(
        runtime=runtime,
        dependencies=dependencies,
        candidate_validation_pack_name="validation_regen_candidate_3",
        expected_artifact_hash=artifact_hash,
        ctx=runtime.ctx,
    )

    resolved_path = report_analysis_store_service.pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            pack_name=pack_name,
            report_slug=report_slug,
        ),
        runtime.ctx,
    ).output_path
    assert loaded_package == candidate_package
    assert stored_path == resolved_path
    assert len(str(Path(resolved_path).resolve())) < 260


def test_promote_retained_claim_candidate_rejects_artifact_mismatch(tmp_path):
    runtime = _runtime(tmp_path)
    stored_requests = []
    dependencies = _deps(
        analysis_pack_path=lambda request, _ctx: SimpleNamespace(
            output_path=f"candidate/{request.pack_name}.json"
        ),
        read_json=lambda _request, _ctx: SimpleNamespace(
            payload={"schema_version": "1.4", "artifact_hash": "stale"}
        ),
        analysis_store_pack=lambda request, _ctx: stored_requests.append(request),
    )

    with pytest.raises(AppError) as excinfo:
        _load_candidate_claim_validation_for_promotion(
            runtime=runtime,
            dependencies=dependencies,
            candidate_validation_pack_name="validation_regen_candidate_1",
            expected_artifact_hash="current",
            ctx=runtime.ctx,
        )

    assert excinfo.value.code == "retained_claim_candidate_artifact_mismatch"
    assert stored_requests == []
