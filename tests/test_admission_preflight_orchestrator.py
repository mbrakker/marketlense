from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.contracts.drive import DriveFile
from src.orchestrators.admission_preflight_orchestrator import (
    AdmissionPreflightDependencies,
    AdmissionPreflightRequest,
    run_admission_preflight,
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
