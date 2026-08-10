from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from src.contracts.admission_preflight import (
    AdmissionOutcome,
    AdmissionPreflightDecision,
    AdmissionPreflightResult,
)
from src.contracts.drive import DriveFile
from src.contracts.files import WriteBytesRequest
from src.contracts.pdf_text import PdfTextExtractRequest
from src.contracts.pdf_utils import PdfIntegrityCheckRequest
from src.contracts.report_store import (
    ReportSourceIdentityGetRequest,
    SourceIdentityObservation,
    SourceIdentityObservationRecordRequest,
)
from src.contracts.run_budget import BudgetRequest, RunBudget
from src.contracts.run_context import RunContext
from src.contracts.state import SourceQuarantineGetRequest
from src.services.document_identity_service import extract_publisher_imprint
from src.services.file_service import write_bytes
from src.services.llm_usage_ledger_service import evaluate_budget_request
from src.services.pdf_service import check_pdf_integrity, extract_pdf_text
from src.services.report_store_service import (
    get_report_source_identity,
    record_source_identity_observation,
)
from src.services.state_service import get_source_quarantine
from src.utils.costing import estimate_cost_usd
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.model_resolver import (
    execution_policies_from_config,
    resolve_execution_policy,
)

logger = logging.getLogger("market_lense.admission_preflight_orchestrator")
ADMISSION_PREFLIGHT_VERSION = "2.0"
_SUPPORTED_PDF_TYPES = {"application/pdf", "application/x-pdf"}


def admission_configuration_hash(settings: Any) -> str:
    """Return a non-secret configuration identity for one admission decision."""

    encoded = json.dumps(
        _redact_hash_values(asdict(settings)),
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def admission_policy_hash(settings: Any) -> str:
    """Return the subset of rules that can change source admission."""

    policy = {
        "admission_max_pages": getattr(settings, "admission_max_pages", None),
        "admission_max_source_bytes": getattr(
            settings, "admission_max_source_bytes", None
        ),
        "admission_min_text_chars": getattr(settings, "admission_min_text_chars", None),
        "admission_required_evidence_families": getattr(
            settings, "admission_required_evidence_families", ()
        ),
        "evidence_pack_registry": getattr(settings, "evidence_pack_registry", ()),
        "llm_execution_policies": getattr(settings, "llm_execution_policies", {}),
        "pdf_text_min_density": getattr(settings, "pdf_text_min_density", None),
        "run_budget_limit_decision": getattr(
            settings, "run_budget_limit_decision", None
        ),
        "run_budget_max_pdfs": getattr(settings, "run_budget_max_pdfs", None),
        "run_budget_max_runtime_seconds": getattr(
            settings, "run_budget_max_runtime_seconds", None
        ),
        "run_budget_max_spend_usd": getattr(settings, "run_budget_max_spend_usd", None),
        "source_quarantine_enabled": getattr(
            settings, "source_quarantine_enabled", None
        ),
    }
    encoded = json.dumps(policy, default=str, separators=(",", ":"), sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def pipeline_preflight_decision_hash(report: Any) -> str:
    """Hash stable runtime/preflight results without paths or operator messages."""

    checks = [
        {
            "check_name": str(getattr(check, "check_name", "")),
            "status": str(getattr(check, "status", "")),
            "code": str(getattr(check, "code", "")),
        }
        for check in getattr(report, "checks", ())
    ]
    return sha256(
        json.dumps(checks, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def persist_admission_funnel(
    decisions: list[AdmissionPreflightDecision],
    *,
    settings: Any,
    ctx: RunContext,
    configuration_hash: str,
    policy_hash: str,
    write_bytes_fn: Callable[[WriteBytesRequest, RunContext], Any] = write_bytes,
) -> str:
    """Retain all admission outcomes independently from ingest reliability."""

    rows = [admission_decision_payload(decision) for decision in decisions]
    decision_set_hash = sha256(
        json.dumps(
            rows, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    path = (
        Path(str(settings.output_dir))
        / "admission"
        / f"{ctx.run_id}-{decision_set_hash[:16]}.json"
    )
    payload = {
        "schema_version": "1.0",
        "run_id": str(ctx.run_id),
        "configuration_hash": configuration_hash,
        "policy_hash": policy_hash,
        "decision_set_hash": decision_set_hash,
        "decisions": rows,
    }
    write_bytes_fn(
        WriteBytesRequest(
            schema_version="1.0",
            path=str(path),
            content=json.dumps(
                payload,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ).encode("utf-8"),
            make_parents=True,
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ingest_admission_funnel_persisted",
            module=logger.name,
            fields={
                "decision_count": len(rows),
                "admitted_count": sum(
                    1 for decision in rows if decision["outcome"] == "admitted"
                ),
                "rejected_count": sum(
                    1 for decision in rows if decision["outcome"] != "admitted"
                ),
                "decision_set_hash": decision_set_hash,
            },
        )
    )
    return str(path)


@dataclass(frozen=True)
class AdmissionPreflightDependencies:
    """Canonical service seams used by deterministic source admission."""

    check_pdf_integrity: Callable[[PdfIntegrityCheckRequest, RunContext], Any] = (
        check_pdf_integrity
    )
    extract_pdf_text: Callable[[PdfTextExtractRequest, RunContext], Any] = (
        extract_pdf_text
    )
    get_source_quarantine: Callable[[SourceQuarantineGetRequest, RunContext], Any] = (
        get_source_quarantine
    )
    evaluate_budget_request: Callable[[BudgetRequest, RunContext], Any] = (
        evaluate_budget_request
    )
    get_source_identity: Callable[[ReportSourceIdentityGetRequest, RunContext], Any] = (
        get_report_source_identity
    )
    record_source_identity_observation: Callable[
        [SourceIdentityObservationRecordRequest, RunContext], Any
    ] = record_source_identity_observation


@dataclass(frozen=True)
class AdmissionPreflightRequest:
    """One source artifact and the already-validated run-level prerequisites."""

    file: DriveFile
    source_artifact_path: str
    settings: Any
    runtime_preflight_passed: bool
    runtime_preflight_hash: str
    configuration_hash: str
    policy_hash: str
    known_source_identities: dict[str, str]
    known_title_keys: dict[str, str]


def run_admission_preflight(
    request: AdmissionPreflightRequest,
    ctx: RunContext,
    *,
    dependencies: AdmissionPreflightDependencies | None = None,
) -> AdmissionPreflightResult:
    """Decide source admission without vector-store or editorial-model work.

    The bounded structural and text inspections intentionally occur after
    acquisition because a local checksum, page count, and text sample are the
    retained deterministic evidence needed to make the decision reproducible.
    """

    deps = dependencies or AdmissionPreflightDependencies()
    file = request.file
    media_type = _normalized_media_type(file)
    title = _stable_title(file)
    title_key = _title_key(title)
    source_identity = str(file.md5_checksum or "").strip()
    source_exists = False
    structure_readable = False
    page_count = 0
    size_bytes = 0
    sample_char_count = 0
    sample_density = 0.0
    duplicate_identity_match = ""
    near_duplicate_title_match = ""
    required_families = _required_artifact_families(request.settings)
    evidence_potential = "not_admitted"
    outcome: AdmissionOutcome = "admitted"
    budget_decision = "not_configured"
    estimated_calls = 0
    estimated_tokens = 0
    estimated_cost = 0.0
    publisher_id = "drive_unattributed"
    source_url = f"drive://{file.file_id}"
    identity_resolved = False

    if not str(file.file_id or "").strip():
        outcome = "missing_source_identity"
    elif media_type not in _SUPPORTED_PDF_TYPES:
        outcome = "unsupported_document"
    else:
        try:
            integrity = deps.check_pdf_integrity(
                PdfIntegrityCheckRequest(
                    schema_version="1.0", path=request.source_artifact_path
                ),
                ctx,
            )
        except AppError as exc:
            outcome = (
                "corrupt_source"
                if exc.code
                in {
                    "pdf_not_found",
                    "pdf_read_failed",
                }
                else "policy_blocked"
            )
        else:
            source_exists = True
            structure_readable = not bool(getattr(integrity, "failure_code", ""))
            # The production integrity contract returns zero only alongside a
            # failure code. The fallback keeps narrow legacy service fakes
            # compatible without weakening real structural validation.
            page_count = max(0, int(getattr(integrity, "page_count", 1) or 1))
            size_bytes = max(0, int(getattr(integrity, "size_bytes", 0) or 0))
            observed_md5 = str(getattr(integrity, "md5", "") or "").strip()
            if source_identity and observed_md5 and source_identity != observed_md5:
                outcome = "corrupt_source"
            elif not source_identity:
                source_identity = observed_md5
            if outcome == "admitted" and (
                not source_identity or not structure_readable or page_count < 1
            ):
                outcome = (
                    "corrupt_source"
                    if structure_readable is False
                    else "missing_source_identity"
                )
            if outcome == "admitted" and _threshold_exceeded(
                page_count,
                size_bytes,
                request.settings,
            ):
                outcome = "unsupported_document"

    if outcome == "admitted":
        duplicate_identity_match = request.known_source_identities.get(
            source_identity, ""
        )
        near_duplicate_title_match = request.known_title_keys.get(title_key, "")
        if duplicate_identity_match:
            outcome = "duplicate"

    if outcome == "admitted" and bool(
        getattr(request.settings, "source_quarantine_enabled", True)
    ):
        quarantine = deps.get_source_quarantine(
            SourceQuarantineGetRequest(
                schema_version="1.0",
                state_db=str(request.settings.state_db),
                source_file_id=file.file_id,
                content_checksum=source_identity,
                validator_version="pdf-integrity-v1",
            ),
            ctx,
        ).record
        if quarantine is not None and str(quarantine.status) == "active":
            outcome = "quarantined"

    if outcome == "admitted":
        try:
            text = deps.extract_pdf_text(
                PdfTextExtractRequest(
                    schema_version="1.0",
                    path=request.source_artifact_path,
                    max_pages=max(1, int(request.settings.pdf_text_sample_pages)),
                    max_chars=max(1, int(request.settings.pdf_text_max_chars)),
                ),
                ctx,
            )
        except AppError:
            outcome = "corrupt_source"
        else:
            sample_char_count = max(0, int(getattr(text, "char_count", 0) or 0))
            sampled_pages = max(
                1,
                int(
                    getattr(text, "pages_extracted", 0)
                    or getattr(request.settings, "pdf_text_sample_pages", 1)
                    or 1
                ),
            )
            sample_density = float(
                getattr(text, "text_density", 0.0) or sample_char_count / sampled_pages
            )
            if not _has_minimum_content(
                sample_char_count, sample_density, request.settings
            ):
                outcome = "insufficient_content"
            elif not _has_evidence_potential(required_families, request.settings):
                outcome = "policy_blocked"
                evidence_potential = "policy_blocked"
            else:
                evidence_potential = "sufficient"
                try:
                    source_response = deps.get_source_identity(
                        ReportSourceIdentityGetRequest(
                            schema_version="1.0",
                            db_path=str(request.settings.reports_db),
                            report_title=title,
                            md5=source_identity,
                        ),
                        ctx,
                    )
                    resolved = source_response.resolution
                    publisher = str(
                        getattr(resolved, "publisher_name", "") or ""
                    ).strip()
                    source_record_id = int(
                        getattr(resolved, "source_record_id", 0) or 0
                    )
                    if (
                        publisher
                        and str(getattr(source_response, "resolution_source", "") or "")
                        == "md5"
                        and str(getattr(resolved, "identity_status", "") or "")
                        != "resolved"
                        and source_record_id > 0
                    ):
                        resolved = deps.record_source_identity_observation(
                            SourceIdentityObservationRecordRequest(
                                schema_version="1.0",
                                db_path=str(request.settings.reports_db),
                                observation=SourceIdentityObservation(
                                    schema_version="1.0",
                                    source_record_id=source_record_id,
                                    canonical_title=str(
                                        getattr(resolved, "canonical_title", "")
                                        or title
                                    ),
                                    title_evidence_locator="legacy_report_sources.report_name",
                                    publisher_id=str(
                                        getattr(resolved, "publisher_id", "") or ""
                                    ),
                                    publisher_name=publisher,
                                    canonical_landing_page_url=str(
                                        getattr(
                                            resolved,
                                            "canonical_landing_page_url",
                                            "",
                                        )
                                        or ""
                                    ),
                                    source_page_url=str(
                                        getattr(resolved, "source_page_url", "") or ""
                                    ),
                                    content_hash=f"md5:{source_identity}",
                                    resolution_method="exact_md5_database_record",
                                    identity_confidence="medium",
                                ),
                            ),
                            ctx,
                        ).resolution
                        publisher = str(
                            getattr(resolved, "publisher_name", "") or ""
                        ).strip()
                    if not publisher:
                        imprint = extract_publisher_imprint(
                            str(getattr(text, "text", "") or "")
                        )
                        if imprint is not None and source_record_id > 0:
                            resolved = deps.record_source_identity_observation(
                                SourceIdentityObservationRecordRequest(
                                    schema_version="1.0",
                                    db_path=str(request.settings.reports_db),
                                    observation=SourceIdentityObservation(
                                        schema_version="1.0",
                                        source_record_id=source_record_id,
                                        canonical_title=title,
                                        title_evidence_locator=imprint.evidence_locator,
                                        publisher_name=imprint.publisher_name,
                                        canonical_landing_page_url=str(
                                            getattr(
                                                resolved,
                                                "canonical_landing_page_url",
                                                "",
                                            )
                                            or ""
                                        ),
                                        source_page_url=str(
                                            getattr(resolved, "source_page_url", "")
                                            or ""
                                        ),
                                        content_hash=f"md5:{source_identity}",
                                        resolution_method=imprint.resolution_method,
                                        identity_confidence="medium",
                                    ),
                                ),
                                ctx,
                            ).resolution
                            publisher = str(
                                getattr(resolved, "publisher_name", "") or ""
                            ).strip()
                    if (
                        str(getattr(resolved, "identity_status", "") or "")
                        == "resolved"
                        and publisher
                    ):
                        identity_resolved = True
                        source_identity = str(
                            getattr(resolved, "source_identity_id", "")
                            or source_identity
                        )
                        publisher_id = str(
                            getattr(resolved, "publisher_id", "") or publisher
                        )
                        source_url = str(
                            getattr(resolved, "canonical_landing_page_url", "") or ""
                        )
                except (AppError, AttributeError, TypeError, ValueError):
                    pass
                if not identity_resolved:
                    outcome = "missing_source_identity"
                else:
                    duplicate_identity_match = request.known_source_identities.get(
                        source_identity, duplicate_identity_match
                    )
                    if duplicate_identity_match:
                        outcome = "duplicate"

    if outcome == "admitted" and not request.runtime_preflight_passed:
        outcome = "policy_blocked"
        evidence_potential = "policy_blocked"

    if outcome == "admitted":
        try:
            estimated_calls, estimated_tokens, estimated_cost = _forecast_required_work(
                settings=request.settings,
                sample_char_count=sample_char_count,
                required_families=required_families,
            )
            budget_decision = _forecast_budget_decision(
                request=request,
                source_identity=source_identity,
                estimated_calls=estimated_calls,
                estimated_tokens=estimated_tokens,
                estimated_cost=estimated_cost,
                dependencies=deps,
                ctx=ctx,
            )
        except AppError:
            outcome = "policy_blocked"
            evidence_potential = "policy_blocked"
        else:
            if budget_decision in {"defer", "pause", "stop"}:
                outcome = "budget_blocked"
                evidence_potential = "budget_blocked"

    decision = _decision(
        outcome=outcome,
        file=file,
        source_identity=source_identity,
        publisher_id=publisher_id,
        source_url=source_url,
        title=title,
        media_type=media_type,
        source_artifact_path=request.source_artifact_path,
        source_exists=source_exists,
        structure_readable=structure_readable,
        page_count=page_count,
        size_bytes=size_bytes,
        sample_char_count=sample_char_count,
        sample_density=sample_density,
        duplicate_identity_match=duplicate_identity_match,
        near_duplicate_title_match=near_duplicate_title_match,
        required_families=required_families,
        evidence_potential=evidence_potential,
        runtime_preflight_hash=request.runtime_preflight_hash,
        runtime_dependencies_ready=request.runtime_preflight_passed,
        estimated_calls=estimated_calls,
        estimated_tokens=estimated_tokens,
        estimated_cost=estimated_cost,
        budget_decision=budget_decision,
        configuration_hash=request.configuration_hash,
        policy_hash=request.policy_hash,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="source_admission_preflight_complete",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "source_identity_id": decision.source_identity_id,
                "outcome": decision.outcome,
                "admission_preflight_version": decision.preflight_version,
                "admission_decision_hash": decision.decision_hash,
                "estimated_provider_calls": decision.estimated_provider_calls,
                "estimated_cost_usd": decision.estimated_cost_usd,
            },
        )
    )
    return AdmissionPreflightResult(
        schema_version="1.0", admitted=outcome == "admitted", decision=decision
    )


def _normalized_media_type(file: DriveFile) -> str:
    declared = str(file.mime_type or "").strip().casefold()
    if declared:
        return declared
    name = str(file.name or "").strip().casefold()
    # The canonical Drive listing itself is PDF-scoped, so metadata-only rows
    # remain valid without manufacturing an external MIME assertion.
    return "application/pdf" if not name or name.endswith(".pdf") else ""


def _stable_title(file: DriveFile) -> str:
    stem = Path(str(file.name or "")).stem.strip()
    return stem or f"source-{str(file.file_id).strip()}"


def _title_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _redact_hash_values(value: Any) -> Any:
    """Exclude credentials while retaining all admission-relevant settings."""

    if isinstance(value, dict):
        return {
            key: _redact_hash_values(item)
            for key, item in value.items()
            if not any(
                marker in key.casefold()
                for marker in ("api_key", "secret", "password", "token", "auth_header")
            )
        }
    if isinstance(value, list):
        return [_redact_hash_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_hash_values(item) for item in value)
    return value


def _required_artifact_families(settings: Any) -> tuple[str, ...]:
    configured = tuple(
        str(family).strip()
        for family in getattr(settings, "admission_required_evidence_families", ())
        if str(family).strip()
    )
    return configured or ("doc_map",)


def _threshold_exceeded(page_count: int, size_bytes: int, settings: Any) -> bool:
    max_pages = getattr(settings, "admission_max_pages", None)
    max_source_bytes = getattr(settings, "admission_max_source_bytes", None)
    return bool(
        (max_pages is not None and page_count > int(max_pages))
        or (max_source_bytes is not None and size_bytes > int(max_source_bytes))
    )


def _has_minimum_content(char_count: int, density: float, settings: Any) -> bool:
    min_chars = max(1, int(getattr(settings, "admission_min_text_chars", 500)))
    min_density = float(getattr(settings, "pdf_text_min_density", 0.0) or 0.0)
    return char_count >= min_chars and density >= min_density


def _has_evidence_potential(required_families: tuple[str, ...], settings: Any) -> bool:
    configured = {
        str(family).strip()
        for family in getattr(settings, "evidence_pack_registry", ())
        if str(family).strip()
    }
    return bool(configured) and set(required_families).issubset(configured)


def _forecast_required_work(
    *, settings: Any, sample_char_count: int, required_families: tuple[str, ...]
) -> tuple[int, int, float]:
    raw_policies = getattr(settings, "llm_execution_policies", {})
    input_tokens = max(
        1, min(int(sample_char_count / 4), int(settings.pdf_text_max_chars / 4))
    )
    if not isinstance(raw_policies, dict) or not raw_policies:
        calls = len(required_families)
        return calls, input_tokens * calls, 0.0
    policies = execution_policies_from_config(
        raw_policies,
        model_overrides=getattr(settings, "openai_models", {}),
        legacy_routing=getattr(settings, "llm_routing", {}),
        default_model=str(settings.openai_model),
        default_temperature=float(settings.temperature),
        default_seed=getattr(settings, "openai_seed", None),
        default_timeout_seconds=getattr(settings, "openai_timeout_seconds", None),
    )
    total_tokens = 0
    total_cost = 0.0
    for family in required_families:
        namespace = (
            "report_vs/doc_map"
            if family == "doc_map"
            else f"report_vs/evidence_packs/{family}"
        )
        decision = resolve_execution_policy(
            namespace,
            policies,
            default_model=str(settings.openai_model),
            default_temperature=float(settings.temperature),
            default_seed=getattr(settings, "openai_seed", None),
            default_timeout_seconds=getattr(settings, "openai_timeout_seconds", None),
            require_registered_namespace=True,
        )
        policy = decision.policy
        family_input = min(
            input_tokens,
            int(policy.max_input_tokens) if policy.max_input_tokens else input_tokens,
        )
        family_output = int(policy.max_output_tokens or 0)
        total_tokens += family_input + family_output
        total_cost += estimate_cost_usd(
            policy.pricing_key or policy.model,
            family_input,
            family_output,
            0,
            getattr(settings, "model_pricing", {}),
        )
    return len(required_families), total_tokens, round(total_cost, 6)


def _forecast_budget_decision(
    *,
    request: AdmissionPreflightRequest,
    source_identity: str,
    estimated_calls: int,
    estimated_tokens: int,
    estimated_cost: float,
    dependencies: AdmissionPreflightDependencies,
    ctx: RunContext,
) -> str:
    settings = request.settings
    if not any(
        getattr(settings, name, None) is not None
        for name in (
            "run_budget_max_spend_usd",
            "run_budget_max_pdfs",
            "run_budget_max_retries",
            "run_budget_max_runtime_seconds",
        )
    ):
        return "not_configured"
    decision = dependencies.evaluate_budget_request(
        BudgetRequest(
            schema_version="1.0",
            budget=RunBudget(
                schema_version="1.0",
                run_id=ctx.run_id,
                publisher_name="drive_unattributed",
                usage_db_path=str(settings.usage_db_path),
                max_spend_usd=getattr(settings, "run_budget_max_spend_usd", None),
                max_pdfs=getattr(settings, "run_budget_max_pdfs", None),
                max_retries=getattr(settings, "run_budget_max_retries", None),
                max_runtime_seconds=getattr(
                    settings, "run_budget_max_runtime_seconds", None
                ),
                limit_decision=str(
                    getattr(settings, "run_budget_limit_decision", "stop")
                ),
                enabled_effect_kinds=getattr(
                    settings, "run_budget_enabled_effect_kinds", ()
                ),
            ),
            run_id=ctx.run_id,
            workflow_id="report_generation",
            resource_type="pdf_process",
            operation="admission_preflight_forecast",
            publisher_id="drive_unattributed",
            report_id=request.file.file_id,
            source_id=source_identity,
            stage="admission_preflight",
            estimated_cost_usd=estimated_cost,
            estimated_tokens=estimated_tokens,
            estimated_calls=estimated_calls,
            estimated_pdfs=1,
            forecast_method="explicit",
            forecast_confidence=1.0,
            idempotency_key=(
                f"admission-forecast:{ctx.run_id}:{request.file.file_id}:{source_identity}"
            ),
            reserve_in_flight=False,
        ),
        ctx,
    )
    return str(decision.decision)


def _decision(
    *,
    outcome: AdmissionOutcome,
    file: DriveFile,
    source_identity: str,
    publisher_id: str,
    source_url: str,
    title: str,
    media_type: str,
    source_artifact_path: str,
    source_exists: bool,
    structure_readable: bool,
    page_count: int,
    size_bytes: int,
    sample_char_count: int,
    sample_density: float,
    duplicate_identity_match: str,
    near_duplicate_title_match: str,
    required_families: tuple[str, ...],
    evidence_potential: str,
    runtime_preflight_hash: str,
    runtime_dependencies_ready: bool,
    estimated_calls: int,
    estimated_tokens: int,
    estimated_cost: float,
    budget_decision: str,
    configuration_hash: str,
    policy_hash: str,
) -> AdmissionPreflightDecision:
    decision = AdmissionPreflightDecision(
        schema_version="1.0",
        preflight_version=ADMISSION_PREFLIGHT_VERSION,
        outcome=outcome,
        file_id=file.file_id,
        source_identity_id=source_identity,
        report_title=title,
        publisher_id=publisher_id,
        source_url=source_url,
        source_url_classification="drive_artifact_nonpublic",
        media_type=media_type,
        source_artifact_path=source_artifact_path,
        source_artifact_exists=source_exists,
        structure_readable=structure_readable,
        page_count=page_count,
        size_bytes=size_bytes,
        sample_char_count=sample_char_count,
        sample_text_density=round(sample_density, 6),
        duplicate_identity_match=duplicate_identity_match,
        near_duplicate_title_match=near_duplicate_title_match,
        required_artifact_families=required_families,
        evidence_potential=evidence_potential,
        runtime_preflight_hash=runtime_preflight_hash,
        runtime_dependencies_ready=runtime_dependencies_ready,
        model_policy_covered=runtime_dependencies_ready,
        estimated_provider_calls=estimated_calls,
        estimated_provider_tokens=estimated_tokens,
        estimated_cost_usd=estimated_cost,
        budget_decision=budget_decision,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
        decision_hash="",
    )
    payload = asdict(decision)
    del payload["decision_hash"]
    decision_hash = sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return replace(decision, decision_hash=decision_hash)


def admission_decision_payload(decision: AdmissionPreflightDecision) -> dict[str, Any]:
    """Return the contract as a JSON-safe retained admission-funnel row."""

    return asdict(decision)
