from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

import pytest

from src.contracts.files import ReadJsonRequest
from src.contracts.report_analysis import (
    AnalysisGenerationByIdReadRequest,
    AnalysisGenerationCommitRequest,
    AnalysisGenerationReadRequest,
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.validation import ValidationReport
from src.generators.claim_validation_generator import claim_validation_package_hash
from src.generators.validation.regeneration_candidate import CandidateIntegrityResult
from src.orchestrators._report_analysis_orchestrator.validation import (
    _candidate_audit,
    _load_promoted_claim_validation_for_reuse,
    _promote_validated_regeneration_candidate,
)
from src.services import file_service, report_analysis_store_service
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from tests._test_report_analysis_generator._shared import (
    _artifacts_without_retained_claims,
    _deps,
    _runtime,
)


def test_real_promotion_commits_one_generation_with_immutable_pack_paths(tmp_path):
    _promotion_worker(tmp_path, "never")
    runtime = _runtime(tmp_path)
    generation = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    artifacts = json.loads(
        Path(generation.pack_paths["artifacts"]).read_text(encoding="utf-8")
    )
    claim = json.loads(
        Path(
            generation.pack_paths["validation_retained_claim_validation_candidate"]
        ).read_text(encoding="utf-8")
    )
    assert artifacts["summary"]["tldr"] == "New"
    assert claim["artifact_hash"] == sha256_json(artifacts)
    assert Path(generation.pack_paths["validation"]).is_file()
    validation = json.loads(
        Path(generation.pack_paths["validation"]).read_text(encoding="utf-8")
    )
    assert validation["source_path"] == generation.pack_paths["validation"]


def test_stale_real_promotion_cannot_replace_committed_generation(tmp_path):
    _promotion_worker(tmp_path, "never")
    runtime = _runtime(tmp_path)
    request = AnalysisGenerationReadRequest(
        schema_version="1.0",
        output_dir=runtime.settings.output_dir,
        report_id=runtime.file.file_id,
        report_slug=runtime.report_name,
    )
    before = report_analysis_store_service.read_generation(request, runtime.ctx)
    with pytest.raises(AppError) as exc:
        _promotion_worker(tmp_path, "never")
    assert exc.value.code == "analysis_generation_conflict"
    assert report_analysis_store_service.read_generation(request, runtime.ctx) == before


def _promotion_worker(
    root: Path,
    stop_pack: str,
    *,
    new_analysis: bool = False,
    include_evidence: bool = False,
) -> None:
    runtime = _runtime(root)
    old = _artifacts_without_retained_claims(
        summary={
            "tldr": "Old",
            "card_tldr_compact": "Old",
            "executive_summary": "Old",
            "claim_evidence_map": [],
        }
    )
    new = deepcopy(old)
    new["summary"]["tldr"] = "New"
    claim = {
        "schema_version": "1.4",
        "artifact_hash": sha256_json(old),
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
    claim["package_hash"] = claim_validation_package_hash(claim)
    validation = ValidationReport(
        schema_version="1.1", status="pass", severity="pass", issues=[]
    )

    def store(name, payload):
        return report_analysis_store_service.store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                pack_name=name,
                payload=payload,
            ),
            runtime.ctx,
        ).output_path

    artifact_path = store("artifacts", old)
    private_artifact_path = artifact_path
    claim_path = store("validation_retained_claim_validation_candidate", claim)
    validation_path = store("validation", validation.to_dict())
    candidate_claim = dict(claim, artifact_hash=sha256_json(new))
    candidate_claim["package_hash"] = claim_validation_package_hash(candidate_claim)
    store(
        "validation_regen_candidate_1_retained_claim_validation_candidate",
        candidate_claim,
    )
    prior_baseline = root / "baseline.json"
    if prior_baseline.exists():
        prior_path = json.loads(prior_baseline.read_text(encoding="utf-8"))["path"]
        initial = report_analysis_store_service.read_generation_by_id(
            AnalysisGenerationByIdReadRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                generation=Path(prior_path).parent.name,
            ),
            runtime.ctx,
        )
    else:
        initial = report_analysis_store_service.commit_generation(
            AnalysisGenerationCommitRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                packs={
                    "artifacts": old,
                    "validation": validation.to_dict(),
                    "validation_retained_claim_validation_candidate": claim,
                },
            ),
            runtime.ctx,
        )
    artifact_path = initial.pack_paths["artifacts"]
    claim_path = initial.pack_paths["validation_retained_claim_validation_candidate"]
    validation_path = initial.pack_paths["validation"]
    audit = _candidate_audit(
        runtime=runtime,
        attempt_index=1,
        transformation_scope=["summary"],
        current_artifacts=old,
        candidate_artifacts=new,
        current_artifacts_path=artifact_path,
        candidate_artifacts_path=str(root / "candidate.json"),
        candidate_result=CandidateIntegrityResult(issues=[], evidence_lineage=[]),
        validation_report=validation,
        promotion_outcome="promoted",
    )
    (root / "baseline.json").write_text(
        json.dumps(
            {
                "path": artifact_path,
                "old": old,
                "files": {
                    artifact_path: Path(artifact_path).read_text(encoding="utf-8"),
                    claim_path: Path(claim_path).read_text(encoding="utf-8"),
                    validation_path: Path(validation_path).read_text(encoding="utf-8"),
                },
            }
        ),
        encoding="utf-8",
    )
    base = _deps()

    def stop_after_artifacts(request, ctx):
        result = base.write_bytes(request, ctx)
        target = hashlib.sha256(stop_pack.encode("utf-8")).hexdigest()[:16] + ".json"
        if Path(request.path).name == target or (
            stop_pack == "manifest"
            and Path(request.path).name == ".generation-manifest.json"
        ):
            (root / "ready").write_text("ready", encoding="utf-8")
            while not (root / "resume").exists():
                time.sleep(0.05)
        return result

    _promote_validated_regeneration_candidate(
        runtime=runtime,
        dependencies=_deps(write_bytes=stop_after_artifacts),
        candidate_artifacts=new,
        candidate_validation_report=validation,
        candidate_validation_pack_name="validation_regen_candidate_1",
        promoted_artifacts=old,
        promoted_validation_report=validation,
        promoted_claim_validation_package=claim,
        current_artifacts_path=private_artifact_path if new_analysis else artifact_path,
        expected_generation=initial.generation if new_analysis else None,
        evidence_packs={"findings": {"findings": []}} if include_evidence else None,
        promotion_audit=audit,
        ctx=runtime.ctx,
    )


def test_private_analysis_promotes_against_pinned_generation(tmp_path):
    _promotion_worker(tmp_path, "never", new_analysis=True, include_evidence=True)
    runtime = _runtime(tmp_path)
    current = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    assert current.packs["artifacts"]["summary"]["tldr"] == "New"
    assert current.packs["authoritative_evidence"] == {"findings": {"findings": []}}
    with pytest.raises(AppError) as exc:
        _promotion_worker(tmp_path, "never", new_analysis=True)
    assert exc.value.code == "analysis_generation_conflict"


@pytest.mark.parametrize(
    "stop_pack",
    [
        "artifacts",
        "validation_retained_claim_validation_candidate",
        "validation",
        "regeneration_candidate_audit_1",
        "authoritative_evidence",
    ],
)
def test_killed_promotion_blocks_or_recovers_retained_claim_reuse(tmp_path, stop_pack):
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.test_promotion_process_recovery",
            str(tmp_path),
            stop_pack,
        ]
    )
    try:
        deadline = time.monotonic() + 30
        while (
            not (tmp_path / "ready").exists()
            and worker.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert (tmp_path / "ready").exists()
    finally:
        worker.kill()
        worker.wait(timeout=10)

    baseline = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    runtime = _runtime(tmp_path)
    try:
        reused = _load_promoted_claim_validation_for_reuse(
            runtime=runtime,
            dependencies=_deps(),
            expected_artifact_hash=sha256_json(baseline["old"]),
            ctx=runtime.ctx,
        )
    except AppError as exc:
        assert exc.code == "regeneration_promotion_recovery_failed"
    else:
        assert reused is not None
        assert (
            json.loads(Path(baseline["path"]).read_text(encoding="utf-8"))
            == baseline["old"]
        )
        assert reused["artifact_hash"] == sha256_json(baseline["old"])


def test_live_promotion_reuses_previous_committed_claim(tmp_path):
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.test_promotion_process_recovery",
            str(tmp_path),
            "artifacts",
        ]
    )
    try:
        deadline = time.monotonic() + 30
        while (
            not (tmp_path / "ready").exists()
            and worker.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert (tmp_path / "ready").exists()
        runtime = _runtime(tmp_path)
        baseline = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
        claim = _load_promoted_claim_validation_for_reuse(
            runtime=runtime, dependencies=_deps(), ctx=runtime.ctx
        )
        assert claim["artifact_hash"] == sha256_json(baseline["old"])
    finally:
        worker.kill()
        worker.wait(timeout=10)


def test_killed_promotion_recovers_before_canonical_artifact_read(tmp_path):
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.test_promotion_process_recovery",
            str(tmp_path),
            "artifacts",
        ]
    )
    try:
        deadline = time.monotonic() + 30
        while (
            not (tmp_path / "ready").exists()
            and worker.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert (tmp_path / "ready").exists()
    finally:
        worker.kill()
        worker.wait(timeout=10)
    baseline = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    try:
        observed = file_service.read_json(
            ReadJsonRequest(schema_version="1.0", path=baseline["path"]),
            _runtime(tmp_path).ctx,
        ).payload
    except AppError as exc:
        assert exc.code == "regeneration_promotion_recovery_failed"
        return
    runtime = _runtime(tmp_path)
    claim_path = (
        _deps()
        .analysis_pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                pack_name="validation_retained_claim_validation_candidate",
            ),
            runtime.ctx,
        )
        .output_path
    )
    claim = file_service.read_json(
        ReadJsonRequest(schema_version="1.0", path=claim_path), runtime.ctx
    ).payload
    assert claim["artifact_hash"] == sha256_json(observed)


def test_killed_promotion_preserves_production_artifact_read(tmp_path):
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.test_promotion_process_recovery",
            str(tmp_path),
            "artifacts",
        ]
    )
    try:
        deadline = time.monotonic() + 30
        while (
            not (tmp_path / "ready").exists()
            and worker.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert (tmp_path / "ready").exists()
    finally:
        worker.kill()
        worker.wait(timeout=10)
    baseline = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    observed = file_service.read_json(
        ReadJsonRequest(schema_version="1.0", path=baseline["path"]),
        _runtime(tmp_path).ctx,
    ).payload
    assert observed == baseline["old"]


def test_existing_marker_is_not_replaced_by_another_promotion(tmp_path):
    runtime = _runtime(tmp_path)
    artifact_path = (
        _deps()
        .analysis_pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=runtime.file.file_id,
                report_slug=runtime.report_name,
                pack_name="artifacts",
            ),
            runtime.ctx,
        )
        .output_path
    )
    marker = Path(artifact_path).parent / ".promotion-pending"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(b"previous-owner")
    with pytest.raises(AppError) as exc:
        _promotion_worker(tmp_path, "never")
    assert exc.value.code == "regeneration_promotion_recovery_failed"
    assert marker.read_bytes() == b"previous-owner"


def test_killed_promoter_after_manifest_replacement_keeps_new_generation(tmp_path):
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.test_promotion_process_recovery",
            str(tmp_path),
            "manifest",
        ]
    )
    try:
        deadline = time.monotonic() + 30
        while (
            not (tmp_path / "ready").exists()
            and worker.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert (tmp_path / "ready").exists()
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=10)
    runtime = _runtime(tmp_path)
    generation = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    assert generation.packs["artifacts"]["summary"]["tldr"] == "New"
    assert generation.packs["validation_retained_claim_validation_candidate"][
        "artifact_hash"
    ] == sha256_json(generation.packs["artifacts"])


def test_successful_promotion_keeps_new_artifact_after_restart(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.test_promotion_process_recovery",
            str(tmp_path),
            "never",
        ],
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    runtime = _runtime(tmp_path)
    generation = report_analysis_store_service.read_generation(
        AnalysisGenerationReadRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=runtime.file.file_id,
            report_slug=runtime.report_name,
        ),
        runtime.ctx,
    )
    artifact = Path(generation.pack_paths["artifacts"])
    observed = file_service.read_json(
        ReadJsonRequest(schema_version="1.0", path=str(artifact)),
        _runtime(tmp_path).ctx,
    ).payload
    assert observed["summary"]["tldr"] == "New"
    assert not (artifact.parent / ".promotion-pending").exists()
    runtime = _runtime(tmp_path)
    reused = _load_promoted_claim_validation_for_reuse(
        runtime=runtime,
        dependencies=_deps(),
        expected_artifact_hash=sha256_json(observed),
        ctx=runtime.ctx,
    )
    assert reused is not None
    assert reused["artifact_hash"] == sha256_json(observed)


if __name__ == "__main__":
    root = Path(sys.argv[1])
    if sys.argv[2] == "read":
        baseline = json.loads((root / "baseline.json").read_text(encoding="utf-8"))
        (root / "reading").write_text("reading", encoding="utf-8")
        try:
            payload = file_service.read_json(
                ReadJsonRequest(schema_version="1.0", path=baseline["path"]),
                _runtime(root).ctx,
            ).payload
        except AppError as exc:
            payload = {"error": exc.code}
        (root / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    else:
        _promotion_worker(
            root, sys.argv[2], include_evidence=sys.argv[2] == "authoritative_evidence"
        )
