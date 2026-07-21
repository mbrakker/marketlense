from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome
from src.orchestrators import ingest_orchestrator as orch
from src.utils.errors import AppError


def _batch_dependencies(**overrides):
    return replace(orch.IngestBatchDependencies.default(), **overrides)


def test_attempt_limited_ingest_keeps_failed_candidate_in_the_result(
    ingest_settings,
) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    bad_file = DriveFile(
        schema_version="1.0",
        file_id="file_bad",
        name="bad.pdf",
        modified_time=None,
        md5_checksum="md5-bad",
    )
    good_file = DriveFile(
        schema_version="1.0",
        file_id="file_good",
        name="good.pdf",
        modified_time=None,
        md5_checksum="md5-good",
    )
    attempted: list[str] = []

    def _fake_process_file(file, index, settings, root_ctx, force_report_cards):
        del settings, root_ctx, force_report_cards
        attempted.append(file.file_id)
        if file.file_id == bad_file.file_id:
            return orch._FileProcessResult(
                index=index,
                outcome=IngestOutcome(
                    schema_version="1.0",
                    file_id=file.file_id,
                    name=file.name or file.file_id,
                    md5=file.md5_checksum,
                    html_path=None,
                    status="error",
                    error="source failed",
                ),
                processed=0,
                had_error=True,
            )
        return orch._FileProcessResult(
            index=index,
            outcome=IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=f"out/{file.file_id}.html",
                status="processed",
            ),
            processed=1,
            had_error=False,
        )

    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: [bad_file, good_file],
        process_file=_fake_process_file,
    )

    results = orch.run_ingest(settings, limit=1, dependencies=deps)

    assert attempted == ["file_bad"]
    assert [row.file_id for row in results] == ["file_bad"]
    assert [row.status for row in results] == ["error"]


def test_frozen_cohort_persists_and_replays_the_same_drive_members(
    ingest_settings, run_context
) -> None:
    files = [
        DriveFile("1.0", "file-a", "A.pdf", "2026-01-01", "md5-a"),
        DriveFile("1.0", "file-b", "B.pdf", "2026-01-02", "md5-b"),
    ]
    stored: dict[str, bytes] = {}
    deps = replace(
        orch.IngestBatchDependencies.default(),
        file_exists=lambda request, _ctx: SimpleNamespace(
            exists=request.path in stored
        ),
        read_text=lambda request, _ctx: SimpleNamespace(
            content=stored[request.path].decode("utf-8")
        ),
        write_bytes=lambda request, _ctx: (
            stored.__setitem__(request.path, request.content)
            or SimpleNamespace(bytes_written=len(request.content))
        ),
    )

    created = orch._frozen_cohort(
        cohort_size=2,
        cohort_manifest="cohorts/release.json",
        selected_files=files,
        settings=ingest_settings,
        deps=deps,
        root_ctx=run_context,
    )
    replayed = orch._frozen_cohort(
        cohort_size=2,
        cohort_manifest="cohorts/release.json",
        selected_files=[],
        settings=ingest_settings,
        deps=deps,
        root_ctx=run_context,
    )

    assert [item.file_id for item in created] == ["file-a", "file-b"]
    assert [item.file_id for item in replayed] == ["file-a", "file-b"]
    assert json.loads(stored["cohorts/release.json"])["cohort_size"] == 2
    assert (
        json.loads(stored["cohorts/release.json"])["selection_reason"]
        == "deterministic_admission_preflight"
    )


def test_fixed_cohort_rejects_invalid_source_before_manifest_or_generation(
    ingest_settings,
) -> None:
    settings = replace(ingest_settings, ingest_worker_limit=1)
    files = [
        DriveFile("1.0", "valid", "valid.pdf", None, "md5-valid"),
        DriveFile("1.0", "corrupt", "corrupt.pdf", None, "md5-corrupt"),
    ]
    generated: list[str] = []

    def _process(file, index, _settings, _ctx, _force):
        generated.append(file.file_id)
        return orch._FileProcessResult(
            index=index,
            outcome=IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=f"out/{file.file_id}.html",
                status="processed",
            ),
            processed=1,
            had_error=False,
        )

    deps = _batch_dependencies(
        list_pdfs=lambda _request, _ctx: files,
        process_file=_process,
        file_exists=lambda _request, _ctx: SimpleNamespace(exists=False),
        get_source_quarantine=lambda _request, _ctx: SimpleNamespace(record=None),
        check_pdf_integrity=lambda request, _ctx: SimpleNamespace(
            failure_code=("pdf_parser_open_failed" if "corrupt" in request.path else "")
        ),
        extract_pdf_text=lambda _request, _ctx: SimpleNamespace(char_count=1_000),
    )

    with pytest.raises(AppError, match="Insufficient eligible reports"):
        orch.run_ingest(
            settings,
            cohort_size=2,
            cohort_manifest="cohorts/admission.json",
            dependencies=deps,
        )

    assert generated == []


def test_manifest_replay_does_not_reselect_or_replace_cohort_members(
    ingest_settings, run_context
) -> None:
    settings = replace(ingest_settings, ingest_worker_limit=1)
    files = [
        DriveFile("1.0", "file-a", "A.pdf", "2026-01-01", "md5-a"),
        DriveFile("1.0", "file-b", "B.pdf", "2026-01-02", "md5-b"),
    ]
    stored: dict[str, bytes] = {}
    created_deps = replace(
        orch.IngestBatchDependencies.default(),
        file_exists=lambda request, _ctx: SimpleNamespace(
            exists=request.path in stored
        ),
        read_text=lambda request, _ctx: SimpleNamespace(
            content=stored[request.path].decode("utf-8")
        ),
        write_bytes=lambda request, _ctx: (
            stored.__setitem__(request.path, request.content)
            or SimpleNamespace(bytes_written=len(request.content))
        ),
    )
    orch._frozen_cohort(
        cohort_size=2,
        cohort_manifest="cohorts/replay.json",
        selected_files=files,
        settings=settings,
        deps=created_deps,
        root_ctx=run_context,
    )
    attempted: list[str] = []

    def _process(file, index, _settings, _ctx, _force):
        attempted.append(file.file_id)
        return orch._FileProcessResult(
            index=index,
            outcome=IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=f"out/{file.file_id}.html",
                status="processed",
            ),
            processed=1,
            had_error=False,
        )

    replay_deps = replace(
        _batch_dependencies(
            list_pdfs=lambda _request, _ctx: (_ for _ in ()).throw(
                AssertionError("a replayed manifest must not reselect Drive files")
            ),
            process_file=_process,
        ),
        file_exists=lambda request, _ctx: SimpleNamespace(
            exists=request.path in stored
        ),
        read_text=lambda request, _ctx: SimpleNamespace(
            content=stored[request.path].decode("utf-8")
        ),
    )

    outcomes = orch.run_ingest(
        settings,
        cohort_manifest="cohorts/replay.json",
        dependencies=replay_deps,
        ctx=run_context,
    )

    assert attempted == ["file-a", "file-b"]
    assert [outcome.file_id for outcome in outcomes] == ["file-a", "file-b"]


def test_cohort_configuration_and_policy_hashes_are_independent(
    ingest_settings,
) -> None:
    assert orch._cohort_configuration_hash(ingest_settings) != orch._cohort_policy_hash(
        ingest_settings
    )


def test_success_target_is_the_only_mode_that_selects_a_replacement(
    ingest_settings,
) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    files = [
        DriveFile("1.0", "bad", "bad.pdf", None, "md5-bad"),
        DriveFile("1.0", "good", "good.pdf", None, "md5-good"),
    ]

    def _process(file, index, _settings, _ctx, _force):
        return orch._FileProcessResult(
            index=index,
            outcome=IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=None if file.file_id == "bad" else "out/good.html",
                status="error" if file.file_id == "bad" else "processed",
            ),
            processed=int(file.file_id == "good"),
            had_error=file.file_id == "bad",
        )

    outcomes = orch.run_ingest(
        settings,
        success_target=1,
        dependencies=_batch_dependencies(
            list_pdfs=lambda _request, _ctx: files,
            process_file=_process,
        ),
    )

    assert [outcome.file_id for outcome in outcomes] == ["bad", "good"]
