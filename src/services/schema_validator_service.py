from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable

from jsonschema import Draft202012Validator, ValidationError

from src.contracts.run_context import RunContext
from src.contracts.schema_validation import (
    SchemaValidateRequest,
    SchemaValidateResponse,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.schema_validator_service")
SCHEMAS_ROOT = Path(__file__).resolve().parents[1] / "schemas"
_SCHEMA_CACHE: Dict[str, dict] = {}
_VALIDATOR_CACHE: Dict[str, Draft202012Validator] = {}


def _load_schema(name: str) -> dict:
    if name in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[name]
    path = SCHEMAS_ROOT / f"{name}.schema.json"
    if not path.exists():
        raise AppError(
            code="schema_not_found",
            message=f"Schema not found: {path}",
            retryable=False,
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError(
            code="schema_invalid_json",
            message=f"Schema JSON invalid: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    _SCHEMA_CACHE[name] = data
    return data


def _validator(name: str) -> Draft202012Validator:
    if name in _VALIDATOR_CACHE:
        return _VALIDATOR_CACHE[name]
    validator = Draft202012Validator(_load_schema(name))
    _VALIDATOR_CACHE[name] = validator
    return validator


def _path(error: ValidationError) -> str:
    parts = ["root"]
    for part in error.absolute_path:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        else:
            parts.append(f".{part}")
    return "".join(parts)


def _error_code(error: ValidationError) -> str:
    validator = str(error.validator or "")
    if validator == "required":
        return "schema_missing_required"
    if validator == "type":
        return "schema_type_mismatch"
    if validator == "enum":
        return "schema_enum_mismatch"
    if validator == "additionalProperties":
        return "schema_additional_properties"
    if validator in {"oneOf", "anyOf"}:
        child_validators = {str(item.validator or "") for item in (error.context or [])}
        if child_validators and child_validators.issubset({"type"}):
            return "schema_type_mismatch"
        return "schema_composition_mismatch"
    if validator in {"allOf", "not"}:
        return "schema_composition_mismatch"
    return "schema_validation_failed"


def _first_error(errors: Iterable[ValidationError]) -> ValidationError | None:
    sorted_errors = sorted(errors, key=lambda item: str(item.path))
    if not sorted_errors:
        return None
    return sorted_errors[0]


def validate_schema(
    request: SchemaValidateRequest, ctx: RunContext
) -> SchemaValidateResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="schema_validation_start",
            module=logger.name,
            fields={"schema": request.schema_name},
        )
    )
    try:
        validator = _validator(request.schema_name)
    except AppError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise AppError(
            code="schema_validator_init_failed",
            message=f"Failed to initialize schema validator: {request.schema_name}",
            cause=exc,
            retryable=False,
        ) from exc

    first_error = _first_error(validator.iter_errors(request.payload))
    if first_error is not None:
        location = _path(first_error)
        code = _error_code(first_error)
        raise AppError(
            code=code,
            message=f"{location} {first_error.message}",
            retryable=False,
            context={"schema": request.schema_name, "validator": first_error.validator},
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="schema_validation_complete",
            module=logger.name,
            fields={"schema": request.schema_name},
        )
    )
    return SchemaValidateResponse(
        schema_version="1.0", schema_name=request.schema_name, valid=True
    )


def validate_evidence_references(
    artifacts_payload: dict[str, Any],
    evidence_pack_payloads: dict[str, Any],
    ctx: RunContext,
) -> None:
    evidence_ids: set[str] = set()
    findings_payload = evidence_pack_payloads.get("findings")
    if isinstance(findings_payload, dict):
        for item in findings_payload.get("findings") or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("id") or "").strip()
            if value:
                evidence_ids.add(value)
    quotes_payload = evidence_pack_payloads.get("quote_candidates")
    if isinstance(quotes_payload, dict):
        for item in quotes_payload.get("quote_candidates") or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("id") or "").strip()
            if value:
                evidence_ids.add(value)
    doc_map_payload = evidence_pack_payloads.get("doc_map")
    if isinstance(doc_map_payload, dict):
        for section in doc_map_payload.get("sections") or []:
            if not isinstance(section, dict):
                continue
            value = str(section.get("id") or "").strip()
            if value:
                evidence_ids.add(value)
    metrics_payload = evidence_pack_payloads.get("key_metrics")
    if isinstance(metrics_payload, dict):
        for item in metrics_payload.get("key_metrics") or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("id") or "").strip()
            if value:
                evidence_ids.add(value)

    references: list[str] = []
    summary = artifacts_payload.get("summary")
    if isinstance(summary, dict):
        for claim in summary.get("claim_evidence_map") or []:
            if isinstance(claim, dict):
                value = str(claim.get("evidence_id") or "").strip()
                if value:
                    references.append(value)
    for key in ("insights_candidates", "insights_final", "quotes_final"):
        for item in artifacts_payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("evidence_id") or "").strip()
            if value:
                references.append(value)

    missing = sorted(
        {reference for reference in references if reference not in evidence_ids}
    )
    if missing:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="schema_reference_validation_failed",
                module=logger.name,
                fields={
                    "missing_reference_count": len(missing),
                    "missing_references": missing,
                },
            )
        )
        raise AppError(
            code="schema_reference_missing",
            message="Artifact evidence references contain unknown identifiers",
            retryable=False,
            context={"missing_references": missing},
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="schema_reference_validation_complete",
            module=logger.name,
            fields={"reference_count": len(references)},
        )
    )
