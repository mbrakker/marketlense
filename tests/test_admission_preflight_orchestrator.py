from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.contracts.drive import DriveFile
from src.contracts.report_store import ReportSourceRecordRequest
from src.orchestrators.admission_preflight_orchestrator import (
    AdmissionPreflightDependencies,
    AdmissionPreflightRequest,
    run_admission_preflight,
)
from src.services.report_store_service import (
    get_report_source_identity,
    record_report_source,
    record_source_identity_observation,
)


def _file(*, file_id: str = "source-1", md5: str = "source-md5") -> DriveFile:
    return DriveFile(
        schema_version="1.0",
        file_id=file_id,
        name="Publisher outlook 2026.pdf",
        modified_time=None,
        md5_checksum=md5,
        mime_type="application/pdf",
    )


def _dependencies(*, quarantine=None, budget_decision: str = "allow"):
    return AdmissionPreflightDependencies(
        check_pdf_integrity=lambda _request, _ctx: SimpleNamespace(
            failure_code="",
            page_count=12,
            size_bytes=24_000,
            md5="source-md5",
        ),
        extract_pdf_text=lambda _request, _ctx: SimpleNamespace(
            char_count=2_000,
            pages_extracted=3,
            text_density=666.0,
        ),
        get_source_quarantine=lambda _request, _ctx: SimpleNamespace(record=quarantine),
        evaluate_budget_request=lambda _request, _ctx: SimpleNamespace(
            decision=budget_decision
        ),
        get_source_identity=lambda _request, _ctx: SimpleNamespace(
            resolution=SimpleNamespace(
                source_identity_id="source:fixture",
                publisher_id="publisher:fixture",
                publisher_name="Publisher Example",
                canonical_landing_page_url="",
                identity_status="resolved",
            )
        ),
    )


def _request(ingest_settings, **overrides) -> AdmissionPreflightRequest:
    values = {
        "file": _file(),
        "source_artifact_path": "cache/source-1.pdf",
        "settings": ingest_settings,
        "runtime_preflight_passed": True,
        "runtime_preflight_hash": "runtime-hash",
        "configuration_hash": "configuration-hash",
        "policy_hash": "policy-hash",
        "known_source_identities": {},
        "known_title_keys": {},
    }
    values.update(overrides)
    return AdmissionPreflightRequest(**values)


def test_admission_is_reproducible_and_does_not_require_model_or_vector_work(
    ingest_settings, run_context
) -> None:
    request = _request(ingest_settings)
    dependencies = _dependencies()

    first = run_admission_preflight(request, run_context, dependencies=dependencies)
    second = run_admission_preflight(request, run_context, dependencies=dependencies)

    assert first.admitted is True
    assert first.decision.outcome == "admitted"
    assert first.decision.decision_hash == second.decision.decision_hash
    assert first.decision.required_artifact_families == ("doc_map",)
    assert first.decision.source_url_classification == "drive_artifact_nonpublic"
    assert first.decision.estimated_provider_calls == 1


def test_admission_rejects_unsupported_corrupt_and_insufficient_sources(
    ingest_settings, run_context
) -> None:
    unsupported = run_admission_preflight(
        _request(
            ingest_settings,
            file=replace(_file(), mime_type="text/html"),
        ),
        run_context,
        dependencies=_dependencies(),
    )
    corrupt = run_admission_preflight(
        _request(ingest_settings),
        run_context,
        dependencies=replace(
            _dependencies(),
            check_pdf_integrity=lambda _request, _ctx: SimpleNamespace(
                failure_code="pdf_parser_open_failed",
                page_count=0,
                size_bytes=0,
                md5="",
            ),
        ),
    )
    insufficient = run_admission_preflight(
        _request(ingest_settings),
        run_context,
        dependencies=replace(
            _dependencies(),
            extract_pdf_text=lambda _request, _ctx: SimpleNamespace(
                char_count=10,
                pages_extracted=1,
                text_density=10.0,
            ),
        ),
    )

    assert unsupported.decision.outcome == "unsupported_document"
    assert corrupt.decision.outcome == "corrupt_source"
    assert insufficient.decision.outcome == "insufficient_content"


def test_admission_checks_exact_identity_and_retains_near_title_as_a_signal(
    ingest_settings, run_context
) -> None:
    duplicate = run_admission_preflight(
        _request(ingest_settings, known_source_identities={"source-md5": "first"}),
        run_context,
        dependencies=_dependencies(),
    )
    near_duplicate = run_admission_preflight(
        _request(
            ingest_settings,
            file=replace(_file(), file_id="source-2", md5_checksum="other-md5"),
            known_title_keys={"publisheroutlook2026": "first-title"},
        ),
        run_context,
        dependencies=replace(
            _dependencies(),
            check_pdf_integrity=lambda _request, _ctx: SimpleNamespace(
                failure_code="",
                page_count=12,
                size_bytes=24_000,
                md5="other-md5",
            ),
        ),
    )

    assert duplicate.decision.outcome == "duplicate"
    assert near_duplicate.admitted is True
    assert near_duplicate.decision.near_duplicate_title_match == "first-title"


def test_admission_uses_document_imprint_to_complete_exact_checksum_identity(
    ingest_settings, run_context
) -> None:
    resolved = SimpleNamespace(
        source_record_id=9,
        source_identity_id="source:existing",
        publisher_id="",
        publisher_name="",
        canonical_landing_page_url="https://publisher.example/report",
        identity_status="legacy_unverified",
    )
    dependencies = replace(
        _dependencies(),
        get_source_identity=lambda _request, _ctx: SimpleNamespace(
            resolution=resolved, resolution_source="md5"
        ),
        record_source_identity_observation=lambda _request, _ctx: SimpleNamespace(
            resolution=SimpleNamespace(
                source_record_id=9,
                source_identity_id="source:document-imprint",
                publisher_id="Acme Research",
                publisher_name="Acme Research",
                identity_status="resolved",
                canonical_landing_page_url="https://publisher.example/report",
            )
        ),
        extract_pdf_text=lambda _request, _ctx: SimpleNamespace(
            text="Published by: Acme Research",
            char_count=2_000,
            pages_extracted=3,
            text_density=666.0,
        ),
    )

    result = run_admission_preflight(
        _request(ingest_settings), run_context, dependencies=dependencies
    )

    assert result.admitted is True
    assert result.decision.source_identity_id == "source:document-imprint"
    assert result.decision.publisher_id == "Acme Research"


def test_admission_promotes_exact_checksum_database_publisher(
    ingest_settings, run_context
) -> None:
    legacy_resolution = SimpleNamespace(
        source_record_id=9,
        source_identity_id="source:legacy-checksum",
        publisher_id="",
        publisher_name="Acme Research",
        canonical_landing_page_url="",
        source_page_url="",
        identity_status="legacy_unverified",
    )
    recorded_observations = []
    dependencies = replace(
        _dependencies(),
        get_source_identity=lambda _request, _ctx: SimpleNamespace(
            resolution=legacy_resolution, resolution_source="md5"
        ),
        record_source_identity_observation=lambda request, _ctx: (
            recorded_observations.append(request.observation)
            or SimpleNamespace(
                resolution=SimpleNamespace(
                    source_record_id=9,
                    source_identity_id="source:exact-md5",
                    publisher_id="Acme Research",
                    publisher_name="Acme Research",
                    canonical_landing_page_url="",
                    identity_status="resolved",
                )
            )
        ),
    )

    result = run_admission_preflight(
        _request(ingest_settings), run_context, dependencies=dependencies
    )

    assert result.admitted is True
    assert result.decision.source_identity_id == "source:exact-md5"
    assert result.decision.publisher_id == "Acme Research"
    assert recorded_observations[0].resolution_method == "exact_md5_database_record"


def test_admission_promotes_database_publisher_from_incomplete_resolution(
    ingest_settings, run_context
) -> None:
    resolution = SimpleNamespace(
        source_record_id=9,
        source_identity_id="source:existing",
        publisher_id="",
        publisher_name="Acme Research",
        canonical_landing_page_url="",
        source_page_url="",
        identity_status="resolved",
        resolution_method="legacy_report_sources_publisher_fallback",
    )
    recorded_observations = []
    result = run_admission_preflight(
        _request(ingest_settings),
        run_context,
        dependencies=replace(
            _dependencies(),
            get_source_identity=lambda _request, _ctx: SimpleNamespace(
                resolution=resolution, resolution_source="md5"
            ),
            record_source_identity_observation=lambda request, _ctx: (
                recorded_observations.append(request.observation)
                or SimpleNamespace(resolution=resolution)
            ),
        ),
    )

    assert result.admitted is True
    assert recorded_observations[0].resolution_method == "exact_md5_database_record"


def test_admission_validation_run_promotes_retained_checksum_publisher(
    ingest_settings, run_context, tmp_path
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=reports_db,
            source_domain="publisher.example",
            report_name="Publisher outlook 2026",
            landing_page_url="https://publisher.example/reports/outlook-2026",
            downloaded_at_utc="2026-08-10T12:00:00Z",
            md5="source-md5",
            publisher_name="Acme Research",
        ),
        run_context,
    )
    result = run_admission_preflight(
        _request(replace(ingest_settings, reports_db=reports_db)),
        run_context,
        dependencies=replace(
            _dependencies(), get_source_identity=get_report_source_identity
        ),
    )

    assert result.admitted is True
    assert result.decision.publisher_id == "Acme Research"
    assert result.decision.source_identity_id.startswith("source:")


def test_admission_records_new_drive_source_from_repeated_document_imprint(
    ingest_settings, run_context, tmp_path
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    result = run_admission_preflight(
        _request(replace(ingest_settings, reports_db=reports_db)),
        run_context,
        dependencies=replace(
            _dependencies(),
            get_source_identity=get_report_source_identity,
            record_report_source=record_report_source,
            record_source_identity_observation=record_source_identity_observation,
            extract_pdf_text=lambda _request, _ctx: SimpleNamespace(
                text=(
                    "www.activate.com\n"
                    "Technology & Media Outlook\n"
                    "www.activate.com\n"
                    "www.activate.com\n"
                ),
                char_count=2_000,
                pages_extracted=3,
                text_density=666.0,
            ),
        ),
    )

    assert result.admitted is True
    assert result.decision.outcome == "admitted"
    assert result.decision.publisher_id == "activate.com"
    assert result.decision.source_identity_id.startswith("source:")
    assert result.decision.source_url == "drive://source-1"


def test_admission_rejects_unresolved_publisher_before_cohort_freeze(
    ingest_settings, run_context
) -> None:
    result = run_admission_preflight(
        _request(ingest_settings),
        run_context,
        dependencies=replace(
            _dependencies(),
            get_source_identity=lambda _request, _ctx: SimpleNamespace(
                resolution=SimpleNamespace(
                    source_identity_id="",
                    publisher_name="",
                    identity_status="unknown",
                )
            ),
        ),
    )

    assert result.admitted is False
    assert result.decision.outcome == "missing_source_identity"


def test_admission_blocks_quarantine_policy_and_budget_before_generation(
    ingest_settings, run_context
) -> None:
    quarantined = run_admission_preflight(
        _request(ingest_settings),
        run_context,
        dependencies=_dependencies(
            quarantine=SimpleNamespace(status="active", failure_code="pdf_missing_eof")
        ),
    )
    policy_blocked = run_admission_preflight(
        _request(ingest_settings, runtime_preflight_passed=False),
        run_context,
        dependencies=_dependencies(),
    )
    budget_blocked = run_admission_preflight(
        _request(
            replace(ingest_settings, run_budget_max_spend_usd=0.01),
        ),
        run_context,
        dependencies=_dependencies(budget_decision="stop"),
    )

    assert quarantined.decision.outcome == "quarantined"
    assert policy_blocked.decision.outcome == "policy_blocked"
    assert budget_blocked.decision.outcome == "budget_blocked"
