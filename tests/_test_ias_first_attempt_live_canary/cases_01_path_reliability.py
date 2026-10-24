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


def test_ias_repair_evidence_ignores_unrelated_external_references(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    audit_path = output_dir / "report_analysis" / "regeneration_candidate_audit_1.json"
    audit_path.parent.mkdir(parents=True)
    audit_path.write_text("{}", encoding="utf-8")
    unrelated_path = tmp_path / "unrelated.json"
    unrelated_path.write_text("{}", encoding="utf-8")
    reports_db = tmp_path / "reports.sqlite"
    ctx = new_runtime_context(task_id="ias-unrelated-external-reference")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=str(reports_db),
            file_id="report-1",
            title="Report with unrelated reference",
            evidence_pack_paths={
                "artifacts": str(unrelated_path),
                "regeneration_candidate_audit_1": str(audit_path),
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


def test_ias_repair_evidence_returns_false_for_unrelated_external_reference(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    unrelated_path = tmp_path / "unrelated.json"
    unrelated_path.write_text("{}", encoding="utf-8")
    reports_db = tmp_path / "reports.sqlite"
    ctx = new_runtime_context(task_id="ias-no-audit-unrelated-reference")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=str(reports_db),
            file_id="report-1",
            title="Report without audit",
            evidence_pack_paths={"artifacts": str(unrelated_path)},
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
        is False
    )


def test_ias_repair_evidence_does_not_scan_sibling_report_audit(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    sibling_audit = (
        output_dir
        / "sibling-report"
        / "report_analysis"
        / "regeneration_candidate_audit_1.json"
    )
    sibling_audit.parent.mkdir(parents=True)
    sibling_audit.write_text("{}", encoding="utf-8")
    reports_db = tmp_path / "reports.sqlite"
    ctx = new_runtime_context(task_id="ias-sibling-report-audit")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=str(reports_db),
            file_id="sibling-report",
            title="Sibling report",
            evidence_pack_paths={"regeneration_candidate_audit_1": str(sibling_audit)},
        ),
        ctx,
    )

    assert (
        canary_runner._read_authoritative_repair_evidence(
            reports_db=str(reports_db),
            output_dir=output_dir,
            report_id="current-report",
            ctx=ctx,
        )
        is False
    )


def test_ias_repair_evidence_accepts_persisted_compacted_audit_path(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    compacted_audit = (
        output_dir
        / ("a" * 12)
        / "report_analysis"
        / "regeneration_candidate_audit_1.json"
    )
    compacted_audit.parent.mkdir(parents=True)
    compacted_audit.write_text("{}", encoding="utf-8")
    reports_db = tmp_path / "reports.sqlite"
    ctx = new_runtime_context(task_id="ias-compacted-audit-path")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=str(reports_db),
            file_id="report-1",
            title="Compacted audit report",
            evidence_pack_paths={
                "regeneration_candidate_audit_1": str(compacted_audit)
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


def test_ias_repair_evidence_does_not_hide_invalid_matching_audit(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "output"
    valid_audit = output_dir / "report_analysis" / "regeneration_candidate_audit_1.json"
    valid_audit.parent.mkdir(parents=True)
    valid_audit.write_text("{}", encoding="utf-8")
    invalid_audit = tmp_path / "outside-audit.json"
    invalid_audit.write_text("{}", encoding="utf-8")
    reports_db = tmp_path / "reports.sqlite"
    ctx = new_runtime_context(task_id="ias-invalid-matching-audit")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=str(reports_db),
            file_id="report-1",
            title="Report with invalid matching audit",
            evidence_pack_paths={
                "regeneration_candidate_audit_1": str(valid_audit),
                "regeneration_candidate_audit_2": str(invalid_audit),
            },
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
