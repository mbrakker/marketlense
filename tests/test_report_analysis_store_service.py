from __future__ import annotations

import json
from pathlib import Path

from src.contracts.report_analysis import AnalysisStorePackRequest
from src.services.report_analysis_store_service import store_pack


def test_store_pack_writes_only_report_scoped_path_when_slug_present(run_context, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    response = store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id="file123",
            pack_name="doc_map",
            payload={"title": "Retail Trends"},
            report_slug="report",
        ),
        run_context,
    )

    primary_path = Path(response.output_path)
    legacy_root_path = output_dir / "report_analysis" / "file123" / "doc_map.json"

    assert primary_path == output_dir / "report" / "report_analysis" / "doc_map.json"
    assert primary_path.exists()
    assert not legacy_root_path.exists()
    assert json.loads(primary_path.read_text(encoding="utf-8"))["title"] == "Retail Trends"


def test_store_pack_falls_back_to_report_id_slug_when_slug_missing(run_context, tmp_path: Path) -> None:
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
