from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.drive import DriveFile, DriveFileMetadataResponse
from src.contracts.ingest import IngestOutcome
from src.contracts.semantic_ids import ValidationRunId
from src.contracts.validation_run_manifest import ValidationRunManifestAuditRequest
from src.orchestrators import ingest_orchestrator as orch
from src.orchestrators.admission_preflight_orchestrator import (
    admission_configuration_hash,
    admission_policy_hash,
)
from src.services.report_store_service import audit_validation_run_manifest
from src.utils.errors import AppError


def _batch_dependencies(**overrides):
    defaults = {
        "get_source_identity": lambda request, _ctx: SimpleNamespace(
            resolution=SimpleNamespace(
                source_identity_id=f"source:{request.md5}",
                publisher_id="publisher:fixture",
                publisher_name="Publisher Example",
                canonical_landing_page_url="",
                identity_status="resolved",
            )
        )
    }
    defaults.update(overrides)
    return replace(orch.IngestBatchDependencies.default(), **defaults)


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

    results = orch.run_ingest(settings, attempt_limit=1, dependencies=deps)

    assert attempted == ["file_bad"]
    assert [row.file_id for row in results] == ["file_bad"]
    assert [row.status for row in results] == ["error"]


def test_drive_discovery_request_uses_the_resolved_ingest_budget(
    ingest_settings,
    run_context,
) -> None:
    request = orch._build_drive_list_request(
        ingest_settings,
        folder_id=None,
        limit=20,
        modified_after=None,
        ctx=run_context,
    )

    assert request.run_budget is not None
    assert request.run_budget.run_id == run_context.run_id
    assert request.run_budget.usage_db_path == ingest_settings.usage_db_path
    assert request.run_budget.max_pdfs == ingest_settings.run_budget_max_pdfs


def test_missing_file_name_metadata_lookup_uses_the_resolved_ingest_budget(
    ingest_settings,
    run_context,
) -> None:
    source = DriveFile(
        schema_version="1.0",
        file_id="file-without-name",
        name=None,
        modified_time=None,
        md5_checksum="source-md5",
    )
    captured = {}

    def _get_metadata(request, _ctx):
        captured["request"] = request
        return DriveFileMetadataResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=source.file_id,
                name="Resolved report.pdf",
                modified_time="2026-07-22T00:00:00Z",
                md5_checksum="resolved-md5",
            ),
        )

    resolved = orch._ensure_file_name(
        source,
        ingest_settings,
        run_context,
        get_file_metadata_fn=_get_metadata,
    )

    assert resolved.name == "Resolved report.pdf"
    assert captured["request"].run_budget is not None
    assert captured["request"].run_budget.run_id == run_context.run_id
    assert captured["request"].run_budget.usage_db_path == ingest_settings.usage_db_path


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
    payload = json.loads(stored["cohorts/release.json"])
    assert payload["schema_version"] == "1.1"
    assert payload["members"] == [
        {
            "schema_version": "1.0",
            "file_id": "file-a",
            "name": "A.pdf",
            "modified_time": "2026-01-01",
            "md5_checksum": "md5-a",
            "mime_type": None,
            "report_id": "file-a",
            "source_identity_id": "md5-a",
            "publisher_id": "unattributed",
            "selection_reason": "deterministic_admission_preflight",
        },
        {
            "schema_version": "1.0",
            "file_id": "file-b",
            "name": "B.pdf",
            "modified_time": "2026-01-02",
            "md5_checksum": "md5-b",
            "mime_type": None,
            "report_id": "file-b",
            "source_identity_id": "md5-b",
            "publisher_id": "unattributed",
            "selection_reason": "deterministic_admission_preflight",
        },
    ]
    assert payload["validation_run_id"] == str(
        orch._validation_run_id_for_cohort(
            cohort_id=payload["cohort_id"],
            configuration_hash=payload["configuration_hash"],
            policy_hash=payload["policy_hash"],
            producer_build_identity=payload["producer_build_identity"],
        )
    )
    payload["members"][1]["file_id"] = "file-replaced"
    payload["members"][1]["report_id"] = "file-replaced"
    stored["cohorts/release.json"] = json.dumps(payload).encode("utf-8")

    with pytest.raises(AppError, match="immutable ingest cohort"):
        orch._frozen_cohort(
            cohort_size=2,
            cohort_manifest="cohorts/release.json",
            selected_files=[],
            settings=ingest_settings,
            deps=deps,
            root_ctx=run_context,
        )


def test_frozen_cohort_rejects_stale_admission_provenance(
    ingest_settings, run_context
) -> None:
    file = DriveFile("1.0", "file-a", "A.pdf", "2026-01-01", "md5-a")
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
    orch._frozen_cohort(
        cohort_size=1,
        cohort_manifest="cohorts/provenance.json",
        selected_files=[file],
        settings=ingest_settings,
        deps=deps,
        root_ctx=run_context,
    )

    with pytest.raises(AppError, match="Cohort manifest provenance differs"):
        orch._frozen_cohort(
            cohort_size=1,
            cohort_manifest="cohorts/provenance.json",
            selected_files=[],
            settings=replace(
                ingest_settings,
                run_budget_max_pdfs=(ingest_settings.run_budget_max_pdfs or 0) + 1,
            ),
            deps=deps,
            root_ctx=run_context,
        )


def test_provenance_recovery_creates_linked_manifest_with_identical_members(
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
    orch._frozen_cohort(
        cohort_size=2,
        cohort_manifest="cohorts/original.json",
        selected_files=files,
        settings=ingest_settings,
        deps=deps,
        root_ctx=run_context,
    )
    original = json.loads(stored["cohorts/original.json"])
    recovered = orch.recover_frozen_cohort_provenance(
        source_manifest="cohorts/original.json",
        recovery_manifest="cohorts/recovery.json",
        recovery_reason="operator context lost after interrupted process",
        settings=replace(
            ingest_settings,
            gdrive_folder_id="recovery-folder",
        ),
        deps=deps,
        root_ctx=run_context,
    )
    payload = json.loads(stored["cohorts/recovery.json"])

    assert [item.file_id for item in recovered] == ["file-a", "file-b"]
    assert payload["members"] == original["members"]
    assert payload["cohort_id"] == original["cohort_id"]
    assert payload["configuration_hash"] != original["configuration_hash"]
    assert payload["policy_hash"] == original["policy_hash"]
    assert payload["producer_build_identity"] == original["producer_build_identity"]
    assert payload["validation_run_id"] != original["validation_run_id"]
    assert payload["configuration_snapshot"]["gdrive_folder_id"] == "recovery-folder"
    assert "openai_api_key" not in payload["configuration_snapshot"]
    assert payload["provenance_recovery"]["source_manifest"] == "cohorts/original.json"
    assert payload["provenance_recovery"]["source_validation_run_id"] == original[
        "validation_run_id"
    ]
    assert payload["provenance_recovery"]["source_configuration_hash"] == original[
        "configuration_hash"
    ]
    assert payload["provenance_recovery"]["reason"] == (
        "operator context lost after interrupted process"
    )


def test_provenance_recovery_rejects_policy_drift(
    ingest_settings, run_context
) -> None:
    file = DriveFile("1.0", "file-a", "A.pdf", "2026-01-01", "md5-a")
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
    orch._frozen_cohort(
        cohort_size=1,
        cohort_manifest="cohorts/original.json",
        selected_files=[file],
        settings=ingest_settings,
        deps=deps,
        root_ctx=run_context,
    )

    with pytest.raises(AppError, match="policy or producer identity differs"):
        orch.recover_frozen_cohort_provenance(
            source_manifest="cohorts/original.json",
            recovery_manifest="cohorts/recovery.json",
            recovery_reason="operator context lost after interrupted process",
            settings=replace(
                ingest_settings,
                admission_min_text_chars=ingest_settings.admission_min_text_chars + 1,
            ),
            deps=deps,
            root_ctx=run_context,
        )


def test_provenance_recovery_records_explicit_producer_transition(
    ingest_settings, run_context
) -> None:
    file = DriveFile("1.0", "file-a", "A.pdf", "2026-01-01", "md5-a")
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
    orch._frozen_cohort(
        cohort_size=1,
        cohort_manifest="cohorts/original.json",
        selected_files=[file],
        settings=ingest_settings,
        deps=deps,
        root_ctx=run_context,
    )
    recovery_ctx = replace(run_context, producer_commit_sha="producer-after-fix")
    orch.recover_frozen_cohort_provenance(
        source_manifest="cohorts/original.json",
        recovery_manifest="cohorts/recovery.json",
        recovery_reason="reviewed run-blocking recovery fix",
        allow_producer_transition=True,
        settings=replace(ingest_settings, gdrive_folder_id="recovery-folder"),
        deps=deps,
        root_ctx=recovery_ctx,
    )
    payload = json.loads(stored["cohorts/recovery.json"])

    assert payload["producer_build_identity"] == "producer-after-fix"
    assert payload["provenance_recovery"]["source_producer_build_identity"] == (
        "workspace"
    )
    assert payload["provenance_recovery"]["producer_identity_changed"] is True


def test_validation_run_identity_changes_with_cohort_provenance() -> None:
    first = orch._validation_run_id_for_cohort(
        cohort_id="cohort",
        configuration_hash="configuration-one",
        policy_hash="policy",
        producer_build_identity="workspace",
    )
    changed_policy = orch._validation_run_id_for_cohort(
        cohort_id="cohort",
        configuration_hash="configuration-one",
        policy_hash="policy-two",
        producer_build_identity="workspace",
    )

    assert first != changed_policy


def test_cohort_identity_changes_with_immutable_member_set() -> None:
    first = DriveFile("1.0", "file-a", "A.pdf", "2026-01-01", "md5-a")
    second = DriveFile("1.0", "file-b", "B.pdf", "2026-01-02", "md5-b")

    assert orch._cohort_id([first]) != orch._cohort_id([second])
    assert orch._cohort_id([first]) != orch._cohort_id([first, second])


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

    def _integrity(request, _ctx):
        if "corrupt" in request.path:
            raise AppError(
                code="pdf_not_found",
                message="prefetch rejected the corrupt source",
                retryable=False,
            )
        return SimpleNamespace(failure_code="")

    deps = _batch_dependencies(
        list_pdfs=lambda _request, _ctx: files,
        process_file=_process,
        file_exists=lambda _request, _ctx: SimpleNamespace(exists=False),
        get_source_quarantine=lambda _request, _ctx: SimpleNamespace(record=None),
        check_pdf_integrity=_integrity,
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


def test_fixed_cohort_fills_only_pre_manifest_admission_slots(
    ingest_settings,
) -> None:
    settings = replace(ingest_settings, ingest_worker_limit=1)
    files = [
        DriveFile("1.0", "valid-a", "valid-a.pdf", None, "md5-valid-a"),
        DriveFile("1.0", "corrupt", "corrupt.pdf", None, "md5-corrupt"),
        DriveFile("1.0", "valid-b", "valid-b.pdf", None, "md5-valid-b"),
    ]
    generated: list[str] = []
    persisted: dict[str, bytes] = {}

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
        file_exists=lambda request, _ctx: SimpleNamespace(
            exists=request.path in persisted
        ),
        write_bytes=lambda request, _ctx: (
            persisted.__setitem__(request.path, request.content)
            or SimpleNamespace(bytes_written=len(request.content))
        ),
        get_source_quarantine=lambda _request, _ctx: SimpleNamespace(record=None),
        check_pdf_integrity=lambda request, _ctx: SimpleNamespace(
            failure_code=("pdf_parser_open_failed" if "corrupt" in request.path else "")
        ),
        extract_pdf_text=lambda _request, _ctx: SimpleNamespace(char_count=1_000),
    )

    outcomes = orch.run_ingest(
        settings,
        cohort_size=2,
        cohort_manifest="cohorts/admission-fill.json",
        dependencies=deps,
    )

    assert [outcome.file_id for outcome in outcomes] == ["valid-a", "valid-b"]
    assert generated == ["valid-a", "valid-b"]
    members = json.loads(persisted["cohorts/admission-fill.json"])["members"]
    assert [member["file_id"] for member in members] == ["valid-a", "valid-b"]
    decisions = json.loads(persisted["cohorts/admission-fill.json"])[
        "admission_decisions"
    ]
    assert [decision["outcome"] for decision in decisions] == [
        "admitted",
        "corrupt_source",
        "admitted",
    ]
    assert all(
        decision["runtime_dependency_status"] == "validated_pre_freeze"
        for decision in decisions
    )
    funnel_payloads = [
        json.loads(content)
        for path, content in persisted.items()
        if "/admission/" in path.replace("\\", "/")
    ]
    assert len(funnel_payloads) == 1
    assert [decision["outcome"] for decision in funnel_payloads[0]["decisions"]] == [
        "admitted",
        "corrupt_source",
        "admitted",
    ]


def test_frozen_cohort_preserves_admitted_publisher_in_manifest_and_stage_records(
    ingest_settings,
    run_context,
) -> None:
    file = DriveFile(
        "1.0", "publisher-owned", "Publisher-owned.pdf", None, "md5-owned"
    )
    stored: dict[str, bytes] = {}

    deps = _batch_dependencies(
        list_pdfs=lambda _request, _ctx: [file],
        process_file=lambda current, index, _settings, _ctx, _force: (
            orch._FileProcessResult(
                index=index,
                outcome=IngestOutcome(
                    schema_version="1.0",
                    file_id=current.file_id,
                    name=current.name or current.file_id,
                    md5=current.md5_checksum,
                    html_path=f"out/{current.file_id}.html",
                    status="processed",
                ),
                processed=1,
                had_error=False,
            )
        ),
        file_exists=lambda request, _ctx: SimpleNamespace(
            exists=request.path in stored
        ),
        write_bytes=lambda request, _ctx: (
            stored.__setitem__(request.path, request.content)
            or SimpleNamespace(bytes_written=len(request.content))
        ),
        get_source_quarantine=lambda _request, _ctx: SimpleNamespace(record=None),
        check_pdf_integrity=lambda _request, _ctx: SimpleNamespace(
            failure_code="", page_count=8, md5="md5-owned"
        ),
        extract_pdf_text=lambda _request, _ctx: SimpleNamespace(
            char_count=2_000, pages_extracted=3, text_density=666.0
        ),
    )

    orch.run_ingest(
        ingest_settings,
        cohort_size=1,
        cohort_manifest="cohorts/publisher-owned.json",
        dependencies=deps,
        ctx=run_context,
    )

    manifest = json.loads(stored["cohorts/publisher-owned.json"])
    assert manifest["members"][0]["publisher_id"] == "publisher:fixture"
    with sqlite3.connect(ingest_settings.reports_db) as connection:
        publisher_ids = connection.execute(
            "SELECT DISTINCT publisher_id FROM validation_run_cohort_members "
            "WHERE validation_run_id=?",
            (manifest["validation_run_id"],),
        ).fetchall()
    assert publisher_ids == [("publisher:fixture",)]


def test_admission_preflight_rejects_duplicate_source_identity_before_freeze(
    ingest_settings,
    run_context,
) -> None:
    files = [
        DriveFile("1.0", "first", "First Report.pdf", None, "same-md5"),
        DriveFile("1.0", "second", "Second Report.pdf", None, "same-md5"),
    ]
    decisions = orch._cohort_admission_preflight(
        files,
        settings=ingest_settings,
        deps=_batch_dependencies(
            get_source_quarantine=lambda _request, _ctx: SimpleNamespace(record=None),
            check_pdf_integrity=lambda _request, _ctx: SimpleNamespace(
                failure_code="", page_count=8, md5="same-md5"
            ),
            extract_pdf_text=lambda _request, _ctx: SimpleNamespace(
                char_count=2_000, pages_extracted=3, text_density=666.0
            ),
        ),
        root_ctx=run_context,
    )

    assert [item.file_id for item in decisions] == ["first"]


def test_admission_preflight_accepts_metadata_only_file_with_content_identity(
    ingest_settings,
    run_context,
) -> None:
    metadata_only_file = DriveFile(
        "1.0", "metadata-only", None, None, "verified-content-md5"
    )

    admitted = orch._cohort_admission_preflight(
        [metadata_only_file],
        settings=ingest_settings,
        deps=_batch_dependencies(
            get_source_quarantine=lambda _request, _ctx: SimpleNamespace(record=None),
            check_pdf_integrity=lambda _request, _ctx: SimpleNamespace(
                failure_code="", page_count=8, md5="verified-content-md5"
            ),
            extract_pdf_text=lambda _request, _ctx: SimpleNamespace(
                char_count=2_000, pages_extracted=3, text_density=666.0
            ),
        ),
        root_ctx=run_context,
    )

    assert admitted == [metadata_only_file]


def test_failed_fixed_cohort_member_records_blocked_remaining_stages(
    ingest_settings,
    run_context,
) -> None:
    file = DriveFile("1.0", "failed", "Failed.pdf", None, "md5-failed")
    validation_run_id = ValidationRunId(f"validation:{orch._cohort_id([file])}")

    orch._record_cohort_ingest_manifest(
        validation_run_id=validation_run_id,
        settings=ingest_settings,
        root_ctx=run_context,
        files=[file],
    )
    orch._record_cohort_ingest_manifest(
        validation_run_id=validation_run_id,
        settings=ingest_settings,
        root_ctx=run_context,
        files=[file],
        outcomes=[
            IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=None,
                status="error",
                error="typed_source_failure",
            )
        ],
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0",
            db_path=ingest_settings.reports_db,
            validation_run_id=validation_run_id,
            require_full_workflow=True,
        ),
        run_context,
    )

    assert audit.complete is True
    assert audit.missing_required_stage_entity_ids == ()


def test_fixed_cohort_replay_supersedes_a_failure_with_validated_reuse(
    ingest_settings,
    run_context,
) -> None:
    file = DriveFile("1.0", "replayed", "Replayed.pdf", None, "md5-replayed")
    validation_run_id = ValidationRunId(f"validation:{orch._cohort_id([file])}")

    orch._record_cohort_ingest_manifest(
        validation_run_id=validation_run_id,
        settings=ingest_settings,
        root_ctx=run_context,
        files=[file],
    )
    orch._record_cohort_ingest_manifest(
        validation_run_id=validation_run_id,
        settings=ingest_settings,
        root_ctx=run_context,
        files=[file],
        outcomes=[
            IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=None,
                status="error",
                error="typed_source_failure",
            )
        ],
    )
    replay_ctx = replace(
        run_context,
        validation_attempt_number=2,
        validation_parent_attempt_number=1,
    )
    orch._record_cohort_ingest_manifest(
        validation_run_id=validation_run_id,
        settings=ingest_settings,
        root_ctx=replay_ctx,
        files=[file],
    )
    orch._record_cohort_ingest_manifest(
        validation_run_id=validation_run_id,
        settings=ingest_settings,
        root_ctx=replay_ctx,
        files=[file],
        outcomes=[
            IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path="out/replayed.html",
                status="skipped",
                error="html_exists",
            )
        ],
    )

    audit = audit_validation_run_manifest(
        ValidationRunManifestAuditRequest(
            schema_version="1.0",
            db_path=ingest_settings.reports_db,
            validation_run_id=validation_run_id,
        ),
        replay_ctx,
    )

    assert audit.complete is True
    assert audit.missing_required_stage_entity_ids == ()
    with sqlite3.connect(ingest_settings.reports_db) as conn:
        current = conn.execute(
            "SELECT attempt_number, terminal_outcome FROM validation_run_entity_attempts "
            "WHERE validation_run_id=? AND is_current=1",
            (str(validation_run_id),),
        ).fetchone()
    assert current == (2, "publish_ready")


def test_fixed_cohort_does_not_treat_state_only_skip_as_publish_ready(
    ingest_settings,
    run_context,
) -> None:
    file = DriveFile("1.0", "state-skip", "State Skip.pdf", None, "md5-state")
    validation_run_id = ValidationRunId(f"validation:{orch._cohort_id([file])}")

    orch._record_cohort_ingest_manifest(
        validation_run_id=validation_run_id,
        settings=ingest_settings,
        root_ctx=run_context,
        files=[file],
    )
    orch._record_cohort_ingest_manifest(
        validation_run_id=validation_run_id,
        settings=ingest_settings,
        root_ctx=run_context,
        files=[file],
        outcomes=[
            IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=None,
                status="skipped",
                error="already_processed",
            )
        ],
    )

    with sqlite3.connect(ingest_settings.reports_db) as conn:
        current = conn.execute(
            "SELECT terminal_outcome, failure_code FROM validation_run_entity_attempts "
            "WHERE validation_run_id=? AND is_current=1",
            (str(validation_run_id),),
        ).fetchone()
    assert current == ("permanent_failure", "already_processed")


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
    assert admission_configuration_hash(ingest_settings) != admission_policy_hash(
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


def test_fixed_cohort_keeps_a_failed_member_without_selecting_a_replacement(
    ingest_settings,
) -> None:
    settings = replace(ingest_settings, ingest_worker_limit=1)
    files = [
        DriveFile("1.0", "failed", "Failed.pdf", None, "md5-failed"),
        DriveFile("1.0", "replacement", "Replacement.pdf", None, "md5-good"),
    ]
    persisted: dict[str, bytes] = {}
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
                html_path=None,
                status="error",
                error="typed_processing_failure",
            ),
            processed=0,
            had_error=True,
        )

    outcomes = orch.run_ingest(
        settings,
        cohort_size=1,
        cohort_manifest="cohorts/failure-is-not-replaced.json",
        dependencies=_batch_dependencies(
            list_pdfs=lambda _request, _ctx: files,
            process_file=_process,
            file_exists=lambda request, _ctx: SimpleNamespace(
                exists=request.path in persisted
            ),
            write_bytes=lambda request, _ctx: (
                persisted.__setitem__(request.path, request.content)
                or SimpleNamespace(bytes_written=len(request.content))
            ),
            get_source_quarantine=lambda _request, _ctx: SimpleNamespace(record=None),
            check_pdf_integrity=lambda _request, _ctx: SimpleNamespace(
                failure_code="", page_count=8, md5="md5-failed"
            ),
            extract_pdf_text=lambda _request, _ctx: SimpleNamespace(
                char_count=2_000, pages_extracted=3, text_density=666.0
            ),
        ),
    )

    assert attempted == ["failed"]
    assert [(outcome.file_id, outcome.status) for outcome in outcomes] == [
        ("failed", "error")
    ]
    manifest = json.loads(persisted["cohorts/failure-is-not-replaced.json"])
    assert [member["report_id"] for member in manifest["members"]] == ["failed"]


def test_attempt_limit_rejects_ambiguous_or_nonpositive_values(ingest_settings) -> None:
    with pytest.raises(AppError, match="either attempt_limit"):
        orch.run_ingest(ingest_settings, attempt_limit=1, limit=1)

    with pytest.raises(AppError, match="Attempt limit must be positive"):
        orch.run_ingest(ingest_settings, attempt_limit=0)
