from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataUpsertRequest,
)
from src.orchestrators.cover_image_orchestrator import _load_cover_fingerprint
from src.services.report_analysis_store_service import store_pack
from src.services.report_store_service import get_metadata, upsert_metadata
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import new_run_context
from src.utils.cover_path_utils import (
    build_report_card_asset_path,
    validate_cover_asset_output_path,
)
from src.generators.report_card_projection import stable_cover_seed


def _artifact_payload(*, shape: str, direction: str) -> dict[str, object]:
    return {
        "schema_version": "3.0",
        "toc_topics": [],
        "editorial_plan": {
            "report_thesis": "The retained evidence supports the report thesis.",
            "themes": [
                {"theme": "Trend", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Implication", "priority": 2, "evidence_ids": ["f2"]},
            ],
        },
        "summary": {
            "tldr": "Complete standard TLDR.",
            "card_tldr_compact": "Complete compact TLDR.",
            "executive_summary": "Summary",
            "claim_evidence_map": [],
        },
        "cover_semantics": {
            "evidence_shape": shape,
            "direction": direction,
            "geography_scope": "global",
            "evidence_density": "balanced",
            "domain_layer": "grid",
            "selection_reason": "The persisted evidence supports the cover.",
        },
        "insights_candidates": [],
        "insights_final": [],
        "quotes_final": [],
        "expert_comment": "",
        "linkedin_post": "",
    }


def _metadata(*, file_id: str, output_dir: Path, reference: str, stale: bool = False):
    return SimpleNamespace(
        file_id=file_id,
        title="Report",
        publisher="Publisher",
        region="Global",
        html_path=str(output_dir / "report.html"),
        file_name="report.pdf",
        categories=[],
        time_period="2026",
        evidence_pack_paths={"artifacts": reference} if reference else {},
        artifacts_stale=stale,
    )


def test_metadata_source_replacement_invalidates_and_reauthorizes_cover_artifacts(
    tmp_path: Path,
) -> None:
    ctx = new_run_context(task_id="test_path05_source_lifecycle")
    db_path = tmp_path / "reports.sqlite"
    output_dir = tmp_path / "out"
    payload_a = _artifact_payload(shape="comparison", direction="diverging")
    payload_b = _artifact_payload(shape="trend", direction="rising")
    artifact_a = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file-x",
            pack_name="artifacts",
            payload=payload_a,
            report_slug="source-a",
        ),
        ctx,
    )

    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="file-x",
            title="Report",
            md5="md5-a",
            source_identity_id="source:a",
            evidence_pack_paths={"artifacts": artifact_a.output_path},
            html_path=str(output_dir / "report.html"),
        ),
        ctx,
    )
    metadata = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0", db_path=str(db_path), file_id="file-x"
        ),
        ctx,
    )
    assert metadata is not None
    assert metadata.md5 == "md5-a"
    assert metadata.evidence_pack_paths["artifacts"] == artifact_a.output_path
    assert metadata.artifacts_stale is False

    # Metadata-only and same-content updates retain the authoritative reference.
    for request in (
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="file-x",
            title="Updated report",
        ),
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="file-x",
            title="Updated report again",
            md5="md5-a",
        ),
    ):
        upsert_metadata(request, ctx)
        metadata = get_metadata(
            ReportMetadataGetRequest(
                schema_version="1.0", db_path=str(db_path), file_id="file-x"
            ),
            ctx,
        )
        assert metadata is not None
        assert metadata.md5 == "md5-a"
        assert metadata.source_identity_id == "source:a"
        assert metadata.evidence_pack_paths["artifacts"] == artifact_a.output_path
        assert metadata.artifacts_stale is False

    # The old file deliberately remains on disk, but source B invalidates it.
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="file-x",
            title="Replacement report",
            md5="md5-b",
            source_identity_id="source:b",
        ),
        ctx,
    )
    metadata = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0", db_path=str(db_path), file_id="file-x"
        ),
        ctx,
    )
    assert metadata is not None
    assert metadata.md5 == "md5-b"
    assert metadata.source_identity_id == "source:b"
    assert metadata.evidence_pack_paths == {}
    assert metadata.artifacts_stale is True
    assert Path(artifact_a.output_path).is_file()
    with pytest.raises(AppError) as stale_error:
        _load_cover_fingerprint(metadata, str(output_dir), ctx)
    assert stale_error.value.code == "cover_artifacts_stale"
    assert stale_error.value.retryable is False

    # The invalidation state survives another metadata-only update.
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="file-x",
            title="Replacement report with metadata",
        ),
        ctx,
    )
    metadata = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0", db_path=str(db_path), file_id="file-x"
        ),
        ctx,
    )
    assert metadata is not None and metadata.artifacts_stale is True

    artifact_b = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file-x",
            pack_name="artifacts",
            payload=payload_b,
            report_slug="source-b",
        ),
        ctx,
    )
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="file-x",
            title="Replacement report",
            md5="md5-b",
            source_identity_id="source:b",
            evidence_pack_paths={"artifacts": artifact_b.output_path},
        ),
        ctx,
    )
    metadata = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0", db_path=str(db_path), file_id="file-x"
        ),
        ctx,
    )
    assert metadata is not None
    assert metadata.artifacts_stale is False
    assert metadata.evidence_pack_paths["artifacts"] == artifact_b.output_path
    fingerprint = _load_cover_fingerprint(metadata, str(output_dir), ctx)
    assert fingerprint.geometry_family == "ascending_trajectory"
    assert fingerprint.seed == stable_cover_seed("file-x", sha256_json(payload_b))
    assert fingerprint.seed != stable_cover_seed("file-x", sha256_json(payload_a))


def test_persisted_prefixed_relative_reference_does_not_try_root_joined_alternative(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    ctx = new_run_context(task_id="test_path05_relative_resolution")
    external_boundary_mocks_only.chdir(tmp_path)
    output_dir = Path("output")
    alternative = tmp_path / "output" / "output" / "report" / "report_analysis"
    alternative.mkdir(parents=True)
    alternative_payload = _artifact_payload(shape="comparison", direction="diverging")
    (alternative / "artifacts.json").write_text(
        json.dumps(alternative_payload), encoding="utf-8"
    )
    metadata = _metadata(
        file_id="file-relative",
        output_dir=tmp_path / "output",
        reference="output/report/report_analysis/artifacts.json",
    )

    with pytest.raises(AppError) as exc_info:
        _load_cover_fingerprint(metadata, str(output_dir), ctx)

    assert exc_info.value.code == "cover_artifacts_missing"
    assert exc_info.value.retryable is False


@pytest.mark.parametrize(
    ("stored_md5", "stored_identity", "incoming_md5", "incoming_identity", "stale"),
    [
        ("md5-a", "source:a", "", "", False),
        ("md5-a", "source:a", "md5-a", "", False),
        ("md5-a", "source:a", "md5-b", "", True),
        ("", "", "md5-b", "", True),
        ("md5-a", "source:a", "", "source:b", True),
        ("md5-a", "source:a", "md5-a", "source:b", False),
    ],
)
def test_metadata_source_comparison_matrix_is_persisted_atomically(
    tmp_path: Path,
    stored_md5: str,
    stored_identity: str,
    incoming_md5: str,
    incoming_identity: str,
    stale: bool,
) -> None:
    ctx = new_run_context(task_id="test_path05_source_matrix")
    db_path = tmp_path / "reports.sqlite"
    artifact_reference = str(tmp_path / "out" / "source-a" / "artifacts.json")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="matrix-file",
            title="Matrix report",
            md5=stored_md5 or None,
            source_identity_id=stored_identity,
            evidence_pack_paths={"artifacts": artifact_reference},
        ),
        ctx,
    )
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.0",
            db_path=str(db_path),
            file_id="matrix-file",
            title="Matrix report updated",
            md5=incoming_md5 or None,
            source_identity_id=incoming_identity,
        ),
        ctx,
    )

    metadata = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0", db_path=str(db_path), file_id="matrix-file"
        ),
        ctx,
    )
    assert metadata is not None
    assert metadata.md5 == (
        incoming_md5
        or (
            stored_md5 if not (incoming_identity and not incoming_md5 and stale) else ""
        )
        or None
    )
    if incoming_identity:
        assert metadata.source_identity_id == incoming_identity
    else:
        assert metadata.source_identity_id == (stored_identity if not stale else "")
    if stale:
        assert metadata.evidence_pack_paths == {}
        assert metadata.artifacts_stale is True
    else:
        assert metadata.evidence_pack_paths["artifacts"] == artifact_reference
        assert metadata.artifacts_stale is False


def test_persisted_prefixed_relative_reference_selects_cwd_candidate_when_both_exist(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    ctx = new_run_context(task_id="test_path05_relative_both_exist")
    external_boundary_mocks_only.chdir(tmp_path)
    output_dir = Path("output")
    direct = tmp_path / "output" / "report" / "report_analysis"
    rooted = tmp_path / "output" / "output" / "report" / "report_analysis"
    direct.mkdir(parents=True)
    rooted.mkdir(parents=True)
    direct_payload = _artifact_payload(shape="trend", direction="rising")
    rooted_payload = _artifact_payload(shape="comparison", direction="diverging")
    (direct / "artifacts.json").write_text(json.dumps(direct_payload), encoding="utf-8")
    (rooted / "artifacts.json").write_text(json.dumps(rooted_payload), encoding="utf-8")
    metadata = _metadata(
        file_id="file-relative-both",
        output_dir=tmp_path / "output",
        reference="output/report/report_analysis/artifacts.json",
    )

    fingerprint = _load_cover_fingerprint(metadata, str(output_dir), ctx)

    assert fingerprint.geometry_family == "ascending_trajectory"
    assert fingerprint.seed == stable_cover_seed(
        "file-relative-both", sha256_json(direct_payload)
    )


def test_persisted_artifact_symlink_escape_is_rejected(tmp_path: Path) -> None:
    ctx = new_run_context(task_id="test_path05_symlink_escape")
    output_dir = tmp_path / "out"
    outside = tmp_path / "outside-artifacts.json"
    outside.write_text(
        json.dumps(_artifact_payload(shape="comparison", direction="diverging")),
        encoding="utf-8",
    )
    link = output_dir / "report" / "report_analysis" / "artifacts.json"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    metadata = _metadata(
        file_id="file-symlink",
        output_dir=output_dir,
        reference="report/report_analysis/artifacts.json",
    )

    with pytest.raises(AppError) as exc_info:
        _load_cover_fingerprint(metadata, str(output_dir), ctx)

    assert exc_info.value.code == "cover_artifacts_invalid"
    assert exc_info.value.retryable is False


def test_cover_asset_preflight_rejects_existing_file_root_without_output_mutation(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output-file"
    output_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(AppError) as exc_info:
        build_report_card_asset_path(
            str(output_root), "file-1", "Title", "report", "small"
        )

    assert exc_info.value.code == "cover_asset_path_invalid"
    assert exc_info.value.retryable is False
    assert output_root.read_text(encoding="utf-8") == "not a directory"


def test_cover_asset_output_preflight_accepts_existing_directory(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    destination, temporary = validate_cover_asset_output_path(
        output_root / "report" / "assets" / "cover.png"
    )

    assert destination == output_root / "report" / "assets" / "cover.png"
    assert temporary == destination.with_suffix(".png.tmp")
    assert not destination.exists()


def test_cover_asset_preflight_translates_unresolvable_root(tmp_path: Path) -> None:
    cycle = tmp_path / "cycle"
    try:
        cycle.symlink_to(cycle, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(AppError) as exc_info:
        build_report_card_asset_path(str(cycle), "file-1", "Title", "report", "small")

    assert exc_info.value.code == "cover_asset_path_invalid"
    assert exc_info.value.retryable is False
    assert "output root" in exc_info.value.message.lower()
