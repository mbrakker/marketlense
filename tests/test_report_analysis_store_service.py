from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.report_analysis import AnalysisStorePackRequest
from src.services.report_analysis_store_service import store_pack
from src.utils.errors import AppError


def _valid_doc_map_payload() -> dict:
    return {
        "schema_version": "1.0",
        "doc_id": "doc-1",
        "title": "Retail Trends",
        "summary": "Short summary",
        "sections": [
            {
                "id": "section-1",
                "title": "Executive Summary",
                "summary": "Section summary",
                "key_points": ["Point 1"],
                "pages": [1],
                "references": [],
            }
        ],
    }


def _valid_artifacts_payload() -> dict:
    return {
        "schema_version": "1.0",
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
            "evidence_shape": "trend",
            "direction": "rising",
            "geography_scope": "global",
            "evidence_density": "balanced",
            "domain_layer": "grid",
            "selection_reason": "The report is organized around a rising trend.",
        },
        "insights_candidates": [],
        "insights_final": [],
        "quotes_final": [],
        "expert_comment": "",
        "linkedin_post": "",
    }


def _valid_candidate_audit_payload() -> dict:
    return {
        "schema_version": "1.0",
        "attempt_index": 1,
        "transformation_scope": ["summary"],
        "before_sha256": "a" * 64,
        "after_sha256": "b" * 64,
        "current_artifacts_path": "artifacts.json",
        "candidate_artifacts_path": "artifacts_regen_candidate_1.json",
        "validation_status": "pass",
        "promotion_outcome": "promoted",
        "validation_issues": [],
        "evidence_lineage": [],
    }


def test_store_pack_writes_only_report_scoped_path_when_slug_present(
    run_context, tmp_path: Path
) -> None:
    output_dir = tmp_path / "out"
    response = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file123",
            pack_name="doc_map",
            payload=_valid_doc_map_payload(),
            report_slug="report",
        ),
        run_context,
    )

    primary_path = Path(response.output_path)
    legacy_root_path = output_dir / "report_analysis" / "file123" / "doc_map.json"

    assert primary_path == output_dir / "report" / "report_analysis" / "doc_map.json"
    assert primary_path.exists()
    assert not legacy_root_path.exists()
    assert (
        json.loads(primary_path.read_text(encoding="utf-8"))["title"] == "Retail Trends"
    )


def test_store_pack_falls_back_to_report_id_slug_when_slug_missing(
    run_context, tmp_path: Path
) -> None:
    output_dir = tmp_path / "out"
    response = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file123",
            pack_name="scope",
            payload={"scope": "global"},
            report_slug=None,
        ),
        run_context,
    )

    expected_path = output_dir / "file123" / "report_analysis" / "scope.json"
    assert Path(response.output_path) == expected_path
    assert expected_path.exists()


def test_store_pack_rejects_invalid_schema_backed_payload_before_write(
    run_context, tmp_path: Path, assert_app_error
) -> None:
    output_dir = tmp_path / "out"
    expected_path = output_dir / "report" / "report_analysis" / "doc_map.json"

    with pytest.raises(AppError) as err:
        store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=str(output_dir),
                report_id="file123",
                pack_name="doc_map",
                payload={"schema_version": "1.0", "title": "Retail Trends"},
                report_slug="report",
            ),
            run_context,
        )

    assert_app_error(
        err.value,
        code="schema_missing_required",
        retryable=False,
        severity="error",
    )
    assert not expected_path.exists()


def test_store_pack_validates_schema_backed_snapshot_pack_names(
    run_context, tmp_path: Path
) -> None:
    output_dir = tmp_path / "out"
    response = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file123",
            pack_name="artifacts_regen_attempt_1",
            payload=_valid_artifacts_payload(),
            report_slug="report",
        ),
        run_context,
    )

    assert Path(response.output_path).exists()


def test_store_pack_validates_schema_backed_candidate_packs(
    run_context, tmp_path: Path
) -> None:
    output_dir = tmp_path / "out"
    artifact_response = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file123",
            pack_name="artifacts_regen_candidate_1",
            payload=_valid_artifacts_payload(),
            report_slug="report",
        ),
        run_context,
    )
    audit_response = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file123",
            pack_name="regeneration_candidate_audit_1",
            payload=_valid_candidate_audit_payload(),
            report_slug="report",
        ),
        run_context,
    )

    assert Path(artifact_response.output_path).exists()
    assert Path(audit_response.output_path).exists()


def test_store_pack_rejects_pack_name_path_traversal(
    run_context, tmp_path: Path, assert_app_error
) -> None:
    output_dir = tmp_path / "out"

    with pytest.raises(AppError) as err:
        store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=str(output_dir),
                report_id="file123",
                pack_name="../escaped",
                payload={"schema_version": "1.0"},
                report_slug="report",
            ),
            run_context,
        )

    assert_app_error(
        err.value,
        code="analysis_pack_name_invalid",
        retryable=False,
    )
    assert not (output_dir / "report" / "report_analysis" / "escaped.json").exists()


def test_store_pack_overwrites_existing_pack_atomically(
    run_context,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    first = _valid_doc_map_payload()
    second = {**_valid_doc_map_payload(), "title": "Updated Title"}

    response = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file123",
            pack_name="doc_map",
            payload=first,
            report_slug="report",
        ),
        run_context,
    )
    store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file123",
            pack_name="doc_map",
            payload=second,
            report_slug="report",
        ),
        run_context,
    )

    stored = json.loads(Path(response.output_path).read_text(encoding="utf-8"))
    assert stored["title"] == "Updated Title"
