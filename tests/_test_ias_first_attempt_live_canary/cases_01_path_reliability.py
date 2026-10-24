from __future__ import annotations

from pathlib import Path

import pytest

import scripts.quality.ias_live_canary_runner as canary_runner
from scripts.quality.ias_live_canary_runner import prepare_isolated_canary_run
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.services.config_service import new_runtime_context
from src.services.report_store_service import upsert_metadata
from src.utils.errors import AppError


def test_prepare_isolated_canary_run_rejects_nested_root_without_creating_it(
    tmp_path: Path,
    assert_app_error,
) -> None:
    runs_root = tmp_path / ("isolated-cohort-" + "r" * 190)

    with pytest.raises(AppError) as err:
        prepare_isolated_canary_run(runs_root=runs_root)

    assert_app_error(err.value, code="ias_canary_run_root_invalid", retryable=False)
    assert not runs_root.exists()


def test_ias_repair_evidence_uses_exact_persisted_metadata_path(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    authoritative_path = output_dir / "hashed-report" / "authoritative-audit.json"
    authoritative_path.parent.mkdir(parents=True)
    authoritative_path.write_text("{}", encoding="utf-8")
    reports_db = tmp_path / "reports.sqlite"
    ctx = new_runtime_context(task_id="ias-authoritative-repair-evidence")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=str(reports_db),
            file_id="report-1",
            title="Authoritative report",
            file_name="source-with-a-different-name.pdf",
            evidence_pack_paths={
                "regeneration_candidate_audit_1": str(authoritative_path)
            },
        ),
        ctx,
    )

    assert (
        canary_runner._read_authoritative_repair_evidence(
            reports_db=str(reports_db),
            output_dir=output_dir,
            report_id="report-1",
            ctx=ctx,
        )
        is True
    )


def test_ias_repair_evidence_rejects_persisted_path_outside_output_root(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    outside_path = tmp_path / "outside-audit.json"
    outside_path.write_text("{}", encoding="utf-8")
    reports_db = tmp_path / "reports.sqlite"
    ctx = new_runtime_context(task_id="ias-outside-repair-evidence")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=str(reports_db),
            file_id="report-1",
            title="Outside reference report",
            evidence_pack_paths={"regeneration_candidate_audit_1": str(outside_path)},
        ),
        ctx,
    )

    with pytest.raises(AppError) as err:
        canary_runner._read_authoritative_repair_evidence(
            reports_db=str(reports_db),
            output_dir=output_dir,
            report_id="report-1",
            ctx=ctx,
        )

    assert err.value.code == "ias_canary_evidence_path_invalid"
    assert err.value.retryable is False
