import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.report_analysis import (
    AnalysisGenerationCommitRequest,
    AnalysisGenerationReadRequest,
    AnalysisStorePackRequest,
)
from src.contracts.validation import ValidationReport
from src.generators.claim_validation_generator import claim_validation_package_hash
from src.generators.report_analysis_generator import VectorStoreIndexingState
from src.generators.verified_claims_canary import VisualAuthorityCanaryConfig
from src.orchestrators import report_analysis_orchestrator as orchestrator
from src.orchestrators._report_analysis_orchestrator.validation import (
    _load_promoted_claim_validation_for_reuse,
    _run_validation_regeneration_loop,
)
from src.services import report_analysis_store_service as store
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from tests._test_report_analysis_generator._shared import (
    _deps,
    _payload,
    _runtime,
    _selection,
    _source,
    run_report_analysis,
)


def _commit(runtime, packs, expected=""):
    return store.commit_generation(
        AnalysisGenerationCommitRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
            expected_generation=expected,
            packs=packs,
        ),
        runtime.ctx,
    )


def test_generation_without_claim_candidate_does_not_reuse_legacy_claim(tmp_path):
    runtime = _runtime(tmp_path)
    _commit(runtime, {"other": {"new": True}})
    assert (
        _load_promoted_claim_validation_for_reuse(
            runtime=runtime, dependencies=_deps(), ctx=runtime.ctx
        )
        is None
    )


def test_private_new_analysis_can_start_repair_against_pinned_prior_generation(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    artifacts = json.loads(
        (
            Path(__file__).parent
            / "fixtures/docpacks/golden/morningstar-2026-outlook-acig-pdf"
            / "report_analysis/artifacts.json"
        ).read_text(encoding="utf-8")
    )
    previous = _commit(runtime, {"artifacts": artifacts})
    private = dict(artifacts, summary={**artifacts["summary"], "tldr": "New analysis"})
    result = _run_validation_regeneration_loop(
        runtime=runtime,
        mode_ctx=runtime.ctx,
        base_payload=_payload(),
        current_artifacts=private,
        current_validation_report=ValidationReport(
            schema_version="1.1", status="pass", severity="pass", issues=[]
        ),
        evidence_packs={},
        source_status=private["source_status"],
        category_labels=[],
        vector_store_id=None,
        dependencies=_deps(),
        expected_generation=previous.generation,
    )
    assert result[0] == private
    _commit(runtime, {"other": {"concurrent": True}}, previous.generation)
    with pytest.raises(AppError) as exc:
        _run_validation_regeneration_loop(
            runtime=runtime,
            mode_ctx=runtime.ctx,
            base_payload=_payload(),
            current_artifacts=private,
            current_validation_report=ValidationReport(
                schema_version="1.1", status="pass", severity="pass", issues=[]
            ),
            evidence_packs={},
            source_status=private["source_status"],
            category_labels=[],
            vector_store_id=None,
            dependencies=_deps(),
            expected_generation=previous.generation,
        )
    assert exc.value.code == "analysis_generation_conflict"


def test_final_validation_commits_complete_generation_and_remaps_paths(tmp_path):
    runtime = _runtime(tmp_path)
    before = ValidationReport(
        schema_version="1.1", status="pass", issues=[], severity="pass"
    )
    first = _commit(runtime, {"validation": before.to_dict(), "other": {"value": 1}})
    reviewed = replace(
        before,
        status="fail",
        severity="error",
        source_path=first.pack_paths["validation"],
    )
    paths = {
        "validation": first.pack_paths["validation"],
        "alias": first.pack_paths["other"],
        "historical": "old.json",
    }

    finalize = getattr(orchestrator, "_commit_final_validation_generation", None)
    assert finalize is not None, "final review must commit a new generation"
    final, remapped, replacements = finalize(runtime, runtime.ctx, reviewed, paths)

    assert final.status == "fail"
    assert final.source_path == remapped["validation"]
    assert remapped["alias"] != paths["alias"]
    assert replacements[first.pack_paths["other"]] == remapped["alias"]
    assert remapped["historical"] == "old.json"
    assert (
        Path(remapped["alias"]).read_bytes()
        == Path(first.pack_paths["other"]).read_bytes()
    )
    assert (
        json.loads(Path(final.source_path).read_text(encoding="utf-8"))["status"]
        == "fail"
    )
    selected = store.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    assert selected.pack_paths["validation"] == final.source_path
    assert selected.packs["validation"] == final.to_dict()
    assert selected.pack_paths["other"] == remapped["alias"]


def test_final_validation_rejects_changed_parent(tmp_path):
    runtime = _runtime(tmp_path)
    report = ValidationReport(
        schema_version="1.1", status="pass", issues=[], severity="pass"
    )
    first = _commit(runtime, {"validation": report.to_dict(), "other": {"value": 1}})
    second = _commit(
        runtime,
        {"validation": report.to_dict(), "other": {"value": 2}},
        first.generation,
    )
    finalize = getattr(orchestrator, "_commit_final_validation_generation", None)
    assert finalize is not None, "final review must commit a new generation"
    with pytest.raises(AppError) as exc:
        finalize(
            runtime,
            runtime.ctx,
            replace(report, source_path=first.pack_paths["validation"]),
            {"validation": first.pack_paths["validation"]},
        )
    assert exc.value.code == "analysis_generation_conflict"
    assert Path(second.pack_paths["other"]).exists()


def test_no_promotion_commits_and_subsequent_analysis_advances_generation(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    selection = _selection(runtime, source)
    calls = []
    artifacts = json.loads(
        (
            Path(__file__).parent
            / "fixtures/docpacks/golden/morningstar-2026-outlook-acig-pdf"
            / "report_analysis/artifacts.json"
        ).read_text(encoding="utf-8")
    )
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: (
            calls.append("evidence") or {"doc_map": {"docMap": {"title": "Doc Title"}}}
        ),
        generate_artifacts=lambda **kwargs: artifacts,
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1", status="pass", issues=[], severity="pass"
        ),
    )
    indexing = VectorStoreIndexingState(
        vector_store_id="vs_1",
        openai_file_id="file_1",
        vector_store_status="completed",
        indexed_at_utc="2026-01-01T00:00:00Z",
        last_error=None,
    )
    state = run_report_analysis(runtime, source, selection, indexing, deps)
    selected = store.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    assert selected.packs["artifacts"] == state.artifacts_payload
    assert selected.packs["validation"] == state.validation_report.to_dict()
    assert selected.packs["authoritative_evidence"] == state.evidence_packs
    assert state.evidence_paths["artifacts"] == selected.pack_paths["artifacts"]
    assert state.evidence_paths["validation"] == selected.pack_paths["validation"]
    again = run_report_analysis(runtime, source, selection, indexing, deps)
    newest = store.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    assert newest.parent_generation == selected.generation
    assert newest.packs["artifacts"] == again.artifacts_payload
    assert newest.packs["validation"] == again.validation_report.to_dict()
    assert calls == ["evidence", "evidence"]


def test_verified_analysis_rejects_missing_provisional_handover(tmp_path):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    calls = []
    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title"}},
            "findings": {"findings": []},
        },
        generate_artifacts=lambda **kwargs: calls.append("artifacts"),
    )
    indexing = VectorStoreIndexingState(
        vector_store_id="vs_1",
        openai_file_id="file_1",
        vector_store_status="completed",
        indexed_at_utc="2026-01-01T00:00:00Z",
        last_error=None,
    )
    with pytest.raises(AppError) as exc:
        run_report_analysis(
            runtime,
            source,
            _selection(runtime, source),
            indexing,
            deps,
            visual_authority_canary=VisualAuthorityCanaryConfig(
                source_identity="report|pdf-sha256:" + "a" * 64
            ),
        )
    assert exc.value.code == "provisional_evidence_handover_missing"
    assert not calls


@pytest.mark.parametrize("existing", [False, True])
def test_no_promotion_rejects_generation_committed_during_analysis(tmp_path, existing):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    artifacts = json.loads(
        (
            Path(__file__).parent
            / "fixtures/docpacks/golden/morningstar-2026-outlook-acig-pdf"
            / "report_analysis/artifacts.json"
        ).read_text(encoding="utf-8")
    )
    parent = (
        _commit(runtime, {"other": {"value": "old"}}).generation if existing else ""
    )

    def evidence(**kwargs):
        _commit(runtime, {"other": {"value": "concurrent"}}, parent)
        return {"doc_map": {"docMap": {"title": "Doc Title"}}}

    deps = _deps(
        generate_evidence_packs=evidence,
        generate_artifacts=lambda **kwargs: artifacts,
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1", status="pass", issues=[], severity="pass"
        ),
    )
    indexing = VectorStoreIndexingState(
        vector_store_id="vs_1",
        openai_file_id="file_1",
        vector_store_status="completed",
        indexed_at_utc="2026-01-01T00:00:00Z",
        last_error=None,
    )
    with pytest.raises(AppError) as exc:
        run_report_analysis(
            runtime, source, _selection(runtime, source), indexing, deps
        )
    assert exc.value.code == "analysis_generation_conflict"
    selected = store.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    assert selected.packs == {"other": {"value": "concurrent"}}


@pytest.mark.parametrize("mismatch", [False, True])
def test_no_promotion_retains_only_matching_claim_candidate(tmp_path, mismatch):
    runtime = _runtime(tmp_path)
    source = _source(runtime)
    artifacts = json.loads(
        (
            Path(__file__).parent
            / "fixtures/docpacks/golden/morningstar-2026-outlook-acig-pdf"
            / "report_analysis/artifacts.json"
        ).read_text(encoding="utf-8")
    )
    package = {
        "schema_version": "1.4",
        "artifact_hash": "0" * 64 if mismatch else sha256_json(artifacts),
        "package_hash": "",
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
    package["package_hash"] = claim_validation_package_hash(package)

    def validate(*args, **kwargs):
        store.store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                pack_name="validation_retained_claim_validation_candidate",
                payload=package,
            ),
            runtime.ctx,
        )
        return ValidationReport(
            schema_version="1.1", status="pass", issues=[], severity="pass"
        )

    deps = _deps(
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title"}}
        },
        generate_artifacts=lambda **kwargs: artifacts,
        run_validation=validate,
    )
    indexing = VectorStoreIndexingState(
        vector_store_id="vs_1",
        openai_file_id="file_1",
        vector_store_status="completed",
        indexed_at_utc="2026-01-01T00:00:00Z",
        last_error=None,
    )
    if mismatch:
        with pytest.raises(AppError) as exc:
            run_report_analysis(
                runtime, source, _selection(runtime, source), indexing, deps
            )
        assert exc.value.code == "retained_claim_candidate_artifact_mismatch"
    else:
        state = run_report_analysis(
            runtime, source, _selection(runtime, source), indexing, deps
        )
        selected = store.read_generation(
            AnalysisGenerationReadRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                report_slug=runtime.report_name,
            ),
            runtime.ctx,
        )
        name = "validation_retained_claim_validation_candidate"
        assert selected.packs[name] == package
        assert state.evidence_paths[name] == selected.pack_paths[name]
