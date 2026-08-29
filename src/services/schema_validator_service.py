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
_PROVIDER_OMITTED_PROPERTIES = frozenset({"_cache", "family_status"})


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


def load_schema(name: str) -> dict:
    """Return a defensive JSON-schema copy for provider constrained output."""

    return json.loads(json.dumps(_load_schema(name)))


def output_schema_fragment(schema_name: str, root_key: str = "") -> dict:
    """Return a response schema for a full contract or one root property."""

    schema = load_schema(schema_name)
    root = str(root_key or "").strip()
    if not root:
        return schema
    properties = schema.get("properties")
    if not isinstance(properties, dict) or root not in properties:
        raise AppError(
            code="schema_output_root_missing",
            message=f"Schema {schema_name} has no output root {root}",
            retryable=False,
            context={"schema": schema_name, "root_key": root},
        )
    return {
        "$schema": schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
        "type": "object",
        "required": [root],
        "additionalProperties": False,
        "properties": {root: properties[root]},
    }


def provider_output_schema(schema_name: str, root_key: str = "") -> dict:
    """Project a canonical contract into OpenAI strict-JSON-Schema form.

    Canonical schemas retain optional fields for stored-artifact compatibility.
    OpenAI strict structured output requires every object to reject unknown
    properties and to name every declared property in ``required``.  This
    projection tightens only the provider response constraint; canonical
    validation still uses ``validate_schema`` below.
    """

    return _strict_provider_schema(output_schema_fragment(schema_name, root_key))


def _strict_provider_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_strict_provider_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    projected: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"additionalProperties", "required"}:
            continue
        # OpenAI's strict response-format subset accepts ``anyOf`` but rejects
        # ``oneOf``.  These report schemas use oneOf only for disjoint scalar
        # and object alternatives, so this provider-only projection preserves
        # the accepted values while canonical validation keeps exact oneOf.
        provider_key = "anyOf" if key == "oneOf" else key
        if key == "properties" and isinstance(item, dict):
            projected[provider_key] = {
                name: _strict_provider_schema(property_schema)
                for name, property_schema in item.items()
                if name not in _PROVIDER_OMITTED_PROPERTIES
            }
        else:
            projected[provider_key] = _strict_provider_schema(item)
    properties = projected.get("properties")
    type_value = projected.get("type")
    is_object = type_value == "object" or (
        isinstance(type_value, list) and "object" in type_value
    )
    if is_object or isinstance(properties, dict):
        projected["additionalProperties"] = False
        projected["required"] = list(properties) if isinstance(properties, dict) else []
    return projected


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


def validate_output_schema(
    *,
    payload: object,
    schema_name: str,
    root_key: str,
    ctx: RunContext,
) -> None:
    """Validate one structured model response against a canonical schema root."""

    root = str(root_key or "").strip()
    schema = output_schema_fragment(schema_name, root)
    validator = Draft202012Validator(schema)
    first_error = _first_error(validator.iter_errors(payload))
    if first_error is None:
        return
    code = _error_code(first_error)
    location = _path(first_error)
    raise AppError(
        code=code,
        message=f"{location} {first_error.message}",
        retryable=False,
        context={
            "schema": schema_name,
            "root_key": root,
            "validator": first_error.validator,
        },
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
                for span in claim.get("evidence_spans") or []:
                    if not isinstance(span, dict):
                        continue
                    span_value = str(span.get("evidence_id") or "").strip()
                    if span_value:
                        references.append(span_value)
    editorial_plan = artifacts_payload.get("editorial_plan")
    if isinstance(editorial_plan, dict):
        for theme in editorial_plan.get("themes") or []:
            if not isinstance(theme, dict):
                continue
            for evidence_id in theme.get("evidence_ids") or []:
                value = str(evidence_id or "").strip()
                if value:
                    references.append(value)
    for key in ("insights_candidates", "insights_final", "quotes_final"):
        for item in artifacts_payload.get(key) or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("evidence_id") or "").strip()
            if value:
                references.append(value)
            for span in item.get("evidence_spans") or []:
                if not isinstance(span, dict):
                    continue
                span_value = str(span.get("evidence_id") or "").strip()
                if span_value:
                    references.append(span_value)

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
