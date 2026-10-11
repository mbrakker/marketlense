from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from src.contracts.model_call_replay_comparison import (
    ModelCallReplayBundleComparisonRequest,
    ModelCallReplayBundleComparisonResponse,
)
from src.contracts.workflow_control import (
    ModelCallAuditRecord,
    ModelCallReplayBundle,
    ModelCallReplayComparisonEvidence,
)
from src.utils.model_resolver import effective_sampling_controls

_COMPARISON_SCHEMA_VERSION = "1.0"
_SUPPORTED_BUNDLE_VERSIONS = {"1.0", "1.1"}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ARTIFACT_FAMILY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,95}$")
_FIELD_ORDER = (
    "artifact_family",
    "operation",
    "scope",
    "provider_decision",
    "prompt_namespace",
    "prompt_hash",
    "rendered_prompt_redaction_hash",
    "model",
    "temperature",
    "reasoning_effort",
    "seed",
    "seed_supported",
    "schema_name",
    "output_schema_version",
    "schema_sha256",
    "policy_sha256",
    "evidence_sha256",
    "output_sha256",
    "artifact_sha256",
    "validation_result",
)
_COHORT_FIELDS = frozenset(
    {
        "artifact_family",
        "operation",
        "scope",
        "provider_decision",
        "prompt_namespace",
        "prompt_hash",
        "rendered_prompt_redaction_hash",
        "model",
        "temperature",
        "reasoning_effort",
        "seed",
        "seed_supported",
        "schema_name",
        "output_schema_version",
        "schema_sha256",
        "policy_sha256",
        "evidence_sha256",
    }
)
_KNOWN_VALIDATION_PASS = {"pass", "passed", "valid", "success", "ok"}
_KNOWN_VALIDATION_FAIL = {"fail", "failed", "invalid", "error"}


def compare_model_call_replay_bundles(
    request: ModelCallReplayBundleComparisonRequest,
) -> ModelCallReplayBundleComparisonResponse:
    request_diagnostics = _validate_comparison_request(request)
    input_diagnostics = _validated_input_diagnostics(request.input_diagnostic_codes)
    if input_diagnostics is None:
        request_diagnostics = (*request_diagnostics, "INPUT_DIAGNOSTIC_INVALID")
    safe_family = _safe_artifact_family(request.artifact_family)
    safe_baseline_ref = _safe_sha256(request.baseline_bundle_sha256)
    safe_candidate_ref = _safe_sha256(request.candidate_bundle_sha256)
    if request_diagnostics:
        return _comparison_response(
            artifact_family=safe_family,
            baseline_ref=safe_baseline_ref,
            candidate_ref=safe_candidate_ref,
            classification="malformed",
            cohort_compatibility="unknown",
            diagnostic_codes=(*request_diagnostics, *(input_diagnostics or ())),
        )

    baseline = request.baseline_bundle
    candidate = request.candidate_bundle
    if baseline is None or candidate is None:
        return _comparison_response(
            artifact_family=safe_family,
            baseline_ref=safe_baseline_ref,
            candidate_ref=safe_candidate_ref,
            classification="malformed",
            cohort_compatibility="unknown",
            diagnostic_codes=input_diagnostics or ("BUNDLE_MALFORMED",),
        )

    baseline_errors = _bundle_errors(baseline)
    candidate_errors = _bundle_errors(candidate)
    malformed_codes = tuple(dict.fromkeys((*baseline_errors, *candidate_errors)))
    if malformed_codes:
        return _comparison_response(
            artifact_family=safe_family,
            baseline_ref=safe_baseline_ref,
            candidate_ref=safe_candidate_ref,
            classification="malformed",
            cohort_compatibility="unknown",
            diagnostic_codes=malformed_codes,
        )

    baseline_identity, baseline_missing = _comparison_identity(baseline)
    candidate_identity, candidate_missing = _comparison_identity(candidate)
    for optional_field in (
        "rendered_prompt_redaction_hash",
        "schema_sha256",
        "validation_result",
    ):
        if (optional_field in baseline_identity) != (
            optional_field in candidate_identity
        ):
            baseline_missing.add(optional_field)
            candidate_missing.add(optional_field)
    missing_fields = _ordered_fields(baseline_missing | candidate_missing)
    changed_fields = _ordered_difference(baseline_identity, candidate_identity)

    family_mismatch = (
        "artifact_family" in baseline_identity
        and baseline_identity["artifact_family"] != safe_family
    ) or (
        "artifact_family" in candidate_identity
        and candidate_identity["artifact_family"] != safe_family
    )
    cohort_changed = any(field_name in _COHORT_FIELDS for field_name in changed_fields)
    cohort_incompatible = cohort_changed or family_mismatch
    regression_evidence: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    if missing_fields:
        classification = "incomplete"
        cohort_compatibility = "incompatible" if cohort_incompatible else "unknown"
        diagnostics = ("IDENTITY_INCOMPLETE",)
        if cohort_incompatible:
            diagnostics = (*diagnostics, "COHORT_INCOMPATIBLE")
        if family_mismatch:
            diagnostics = (*diagnostics, "ARTIFACT_FAMILY_MISMATCH")
    elif cohort_incompatible:
        classification = "incompatible"
        cohort_compatibility = "incompatible"
        diagnostics = ("COHORT_INCOMPATIBLE",)
        if family_mismatch:
            diagnostics = (*diagnostics, "ARTIFACT_FAMILY_MISMATCH")
    else:
        cohort_compatibility = "compatible"
        baseline_validation = _validation_state(baseline.audit_record.validation_result)
        candidate_validation = _validation_state(
            candidate.audit_record.validation_result
        )
        output_changed = "output_sha256" in changed_fields
        if (
            output_changed
            and baseline_validation == "pass"
            and candidate_validation == "fail"
        ):
            classification = "materially_regressed"
            diagnostics = ("COMPARABLE_VALIDATION_REGRESSION",)
            regression_evidence = ("OUTPUT_IDENTITY_CHANGED", "VALIDATION_REGRESSED")
        elif changed_fields:
            classification = "compatible_but_changed"
            diagnostics = ("COMPATIBLE_IDENTITY_CHANGED",)
            regression_evidence = ()
        else:
            classification = "equivalent"
            diagnostics = ()
            regression_evidence = ()
        return _comparison_response(
            artifact_family=safe_family,
            baseline_ref=safe_baseline_ref,
            candidate_ref=safe_candidate_ref,
            classification=classification,
            cohort_compatibility=cohort_compatibility,
            compared_fields=_ordered_fields(
                set(baseline_identity).intersection(candidate_identity)
            ),
            changed_fields=changed_fields,
            missing_fields=missing_fields,
            diagnostic_codes=diagnostics,
            regression_evidence=regression_evidence,
        )

    return _comparison_response(
        artifact_family=safe_family,
        baseline_ref=safe_baseline_ref,
        candidate_ref=safe_candidate_ref,
        classification=classification,
        cohort_compatibility=cohort_compatibility,
        compared_fields=_ordered_fields(
            set(baseline_identity).intersection(candidate_identity)
        ),
        changed_fields=changed_fields,
        missing_fields=missing_fields,
        diagnostic_codes=diagnostics,
    )


def _validate_comparison_request(
    request: ModelCallReplayBundleComparisonRequest,
) -> tuple[str, ...]:
    errors: list[str] = []
    if request.schema_version != _COMPARISON_SCHEMA_VERSION:
        errors.append("REQUEST_SCHEMA_UNSUPPORTED")
    if _safe_artifact_family(request.artifact_family) is None:
        errors.append("ARTIFACT_FAMILY_INVALID")
    if _safe_sha256(request.baseline_bundle_sha256) is None:
        errors.append("BASELINE_REFERENCE_INVALID")
    if _safe_sha256(request.candidate_bundle_sha256) is None:
        errors.append("CANDIDATE_REFERENCE_INVALID")
    if _validated_input_diagnostics(request.input_diagnostic_codes) is None:
        errors.append("INPUT_DIAGNOSTIC_INVALID")
    return tuple(dict.fromkeys(errors))[:12]


def _validated_input_diagnostics(
    codes: object,
) -> tuple[str, ...] | None:
    if not isinstance(codes, tuple) or len(codes) > 8:
        return None
    if any(
        not isinstance(code, str) or not re.fullmatch(r"[A-Z_]{1,64}", code)
        for code in codes
    ):
        return None
    return tuple(dict.fromkeys(codes))


def _bundle_errors(bundle: ModelCallReplayBundle) -> tuple[str, ...]:
    if not isinstance(bundle, ModelCallReplayBundle):
        return ("BUNDLE_MALFORMED",)
    if not isinstance(bundle.schema_version, str):
        return ("BUNDLE_SCHEMA_UNSUPPORTED",)
    if bundle.schema_version not in _SUPPORTED_BUNDLE_VERSIONS:
        return ("BUNDLE_SCHEMA_UNSUPPORTED",)
    if not isinstance(bundle.audit_record, ModelCallAuditRecord):
        return ("AUDIT_RECORD_MALFORMED",)
    if bundle.audit_record.schema_version != "1.0":
        return ("AUDIT_SCHEMA_UNSUPPORTED",)
    if bundle.live_provider_call_allowed is not False:
        return ("LIVE_PROVIDER_REPLAY_NOT_ALLOWED",)
    if not isinstance(bundle.replay_inputs, dict):
        return ("REPLAY_INPUTS_MALFORMED",)
    if bundle.schema_version == "1.0" and bundle.comparison_evidence is not None:
        return ("BUNDLE_SCHEMA_CONFLICT",)

    record = bundle.audit_record
    required_text_fields = (
        "operation",
        "scope",
        "provider_decision",
        "prompt_namespace",
        "prompt_hash",
        "rendered_prompt_redaction_hash",
        "model",
        "schema_name",
        "output_schema_version",
    )
    for field_name in required_text_fields:
        value = getattr(record, field_name)
        if not isinstance(value, str) or _safe_text(value, allow_empty=True) is None:
            return ("AUDIT_RECORD_MALFORMED",)
    if (
        not isinstance(record.reasoning_effort, str)
        or _safe_text(record.reasoning_effort, allow_empty=True) is None
    ):
        return ("AUDIT_RECORD_MALFORMED",)
    if not isinstance(record.validation_result, str) or (
        record.validation_result and _safe_text(record.validation_result) is None
    ):
        return ("AUDIT_RECORD_MALFORMED",)
    if record.temperature is not None and (
        isinstance(record.temperature, bool)
        or not isinstance(record.temperature, (int, float))
        or not math.isfinite(record.temperature)
    ):
        return ("AUDIT_RECORD_MALFORMED",)
    if record.seed is not None and (
        isinstance(record.seed, bool) or not isinstance(record.seed, int)
    ):
        return ("AUDIT_RECORD_MALFORMED",)
    if not isinstance(record.seed_supported, bool):
        return ("AUDIT_RECORD_MALFORMED",)
    if (
        record.rendered_prompt_redaction_hash
        and _safe_sha256(record.rendered_prompt_redaction_hash) is None
    ):
        return ("AUDIT_PROMPT_IDENTITY_MALFORMED",)

    aliases = {
        "operation": "operation",
        "scope": "scope",
        "provider_decision": "provider_decision",
        "prompt_namespace": "prompt_namespace",
        "prompt_hash": "prompt_hash",
        "rendered_prompt_redaction_hash": "rendered_prompt_redaction_hash",
        "model": "model",
        "temperature": "temperature",
        "reasoning_effort": "reasoning_effort",
        "seed": "seed",
        "schema_name": "schema_name",
        "schema_version": "output_schema_version",
        "cache_key": "cache_key",
    }
    for replay_key, record_key in aliases.items():
        if replay_key in bundle.replay_inputs and bundle.replay_inputs[
            replay_key
        ] != getattr(record, record_key):
            return ("REPLAY_INPUT_CONFLICT",)
    evidence = bundle.comparison_evidence
    if evidence is not None:
        if not isinstance(evidence, ModelCallReplayComparisonEvidence):
            return ("COMPARISON_EVIDENCE_MALFORMED",)
        if evidence.schema_version != "1.0":
            return ("COMPARISON_EVIDENCE_SCHEMA_UNSUPPORTED",)
        if _safe_artifact_family(evidence.artifact_family) is None:
            return ("ARTIFACT_FAMILY_INVALID",)
        for value in (
            evidence.policy_sha256,
            evidence.evidence_sha256,
            evidence.output_sha256,
            evidence.artifact_sha256,
            evidence.schema_sha256,
        ):
            if value is not None and _safe_sha256(value) is None:
                return ("IDENTITY_HASH_INVALID",)
    return ()


def _comparison_identity(
    bundle: ModelCallReplayBundle,
) -> tuple[dict[str, object], set[str]]:
    record = bundle.audit_record
    evidence = bundle.comparison_evidence
    missing: set[str] = set()
    identity: dict[str, object] = {}

    for field_name, value in (
        ("operation", record.operation),
        ("scope", record.scope),
        ("provider_decision", record.provider_decision),
        ("prompt_namespace", record.prompt_namespace),
        ("model", record.model),
        ("schema_name", record.schema_name),
        ("output_schema_version", record.output_schema_version),
    ):
        safe_value = _safe_text(value)
        if safe_value is None:
            missing.add(field_name)
        else:
            identity[field_name] = safe_value

    prompt_hash = _safe_sha256(record.prompt_hash)
    if prompt_hash is None:
        missing.add("prompt_hash")
    else:
        identity["prompt_hash"] = prompt_hash
    rendered_hash = _safe_sha256(record.rendered_prompt_redaction_hash)
    if rendered_hash is not None:
        identity["rendered_prompt_redaction_hash"] = rendered_hash
    elif record.rendered_prompt_redaction_hash:
        missing.add("rendered_prompt_redaction_hash")

    if isinstance(record.temperature, bool) or (
        record.temperature is not None
        and (
            not isinstance(record.temperature, (int, float))
            or not math.isfinite(record.temperature)
        )
    ):
        missing.add("temperature")
    else:
        identity["temperature"] = (
            float(record.temperature) if record.temperature is not None else None
        )
    if (
        not isinstance(record.reasoning_effort, str)
        or _safe_text(record.reasoning_effort, allow_empty=True) is None
    ):
        missing.add("reasoning_effort")
    else:
        identity["reasoning_effort"] = record.reasoning_effort
    if record.seed is not None and (
        isinstance(record.seed, bool) or not isinstance(record.seed, int)
    ):
        missing.add("seed")
    else:
        identity["seed"] = record.seed
    if not isinstance(record.seed_supported, bool):
        missing.add("seed_supported")
    else:
        identity["seed_supported"] = record.seed_supported

    if record.validation_result:
        if _safe_text(record.validation_result) is None:
            missing.add("validation_result")
        else:
            identity["validation_result"] = record.validation_result.strip().casefold()

    if evidence is None:
        missing.update(
            {
                "artifact_family",
                "policy_sha256",
                "evidence_sha256",
                "output_sha256",
                "artifact_sha256",
            }
        )
    else:
        identity["artifact_family"] = evidence.artifact_family
        for field_name in (
            "policy_sha256",
            "evidence_sha256",
            "output_sha256",
            "artifact_sha256",
        ):
            value = getattr(evidence, field_name)
            safe_hash = _safe_sha256(value)
            if safe_hash is None:
                missing.add(field_name)
            else:
                identity[field_name] = safe_hash
        schema_hash = _safe_sha256(evidence.schema_sha256)
        if schema_hash is not None:
            identity["schema_sha256"] = schema_hash
        elif evidence.schema_sha256 is not None:
            missing.add("schema_sha256")

    return identity, missing


def _ordered_difference(
    baseline: dict[str, object], candidate: dict[str, object]
) -> tuple[str, ...]:
    changed = {
        field_name
        for field_name in baseline.keys() & candidate.keys()
        if baseline[field_name] != candidate[field_name]
    }
    return _ordered_fields(changed)


def _ordered_fields(field_names: set[str]) -> tuple[str, ...]:
    return tuple(name for name in _FIELD_ORDER if name in field_names)


def _safe_artifact_family(value: object) -> str | None:
    if not isinstance(value, str) or not _ARTIFACT_FAMILY_RE.fullmatch(value):
        return None
    return value


def _safe_sha256(value: object) -> str | None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        return None
    return value.casefold()


def _safe_text(value: object, *, allow_empty: bool = False) -> str | None:
    if (
        not isinstance(value, str)
        or (not value and not allow_empty)
        or len(value) > 128
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        return None
    return value


def _validation_state(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized in _KNOWN_VALIDATION_PASS:
        return "pass"
    if normalized in _KNOWN_VALIDATION_FAIL:
        return "fail"
    return "unknown"


def _comparison_response(
    *,
    artifact_family: str | None,
    baseline_ref: str | None,
    candidate_ref: str | None,
    classification: str,
    cohort_compatibility: str,
    compared_fields: tuple[str, ...] = (),
    changed_fields: tuple[str, ...] = (),
    missing_fields: tuple[str, ...] = (),
    diagnostic_codes: tuple[str, ...] = (),
    regression_evidence: tuple[str, ...] = (),
) -> ModelCallReplayBundleComparisonResponse:
    return ModelCallReplayBundleComparisonResponse(
        schema_version=_COMPARISON_SCHEMA_VERSION,
        artifact_family=artifact_family or "",
        baseline_bundle_sha256=baseline_ref or "",
        candidate_bundle_sha256=candidate_ref or "",
        classification=classification,  # type: ignore[arg-type]
        cohort_compatibility=cohort_compatibility,  # type: ignore[arg-type]
        compared_fields=compared_fields[: len(_FIELD_ORDER)],
        changed_fields=changed_fields[: len(_FIELD_ORDER)],
        missing_fields=missing_fields[: len(_FIELD_ORDER)],
        diagnostic_codes=tuple(dict.fromkeys(diagnostic_codes))[:12],
        regression_evidence=regression_evidence[:4],
    )


def build_model_call_audit_record(
    *,
    operation: str,
    scope: str,
    request: Any,
    response: Any,
) -> ModelCallAuditRecord:
    system_prompt = str(getattr(request, "system_prompt", "") or "")
    user_prompt = str(getattr(request, "user_prompt", "") or "")
    rendered_hash = hashlib.sha256(
        f"{system_prompt}\n{user_prompt}".encode("utf-8")
    ).hexdigest()
    prompt_hash = str(
        getattr(request, "prompt_hash", "")
        or getattr(request, "prompt_sha256", "")
        or getattr(request, "prompt_user_sha256", "")
        or rendered_hash
    )
    seed = getattr(request, "seed", None)
    try:
        normalized_seed = int(seed) if seed is not None else None
    except (TypeError, ValueError):
        normalized_seed = None
    actual_temperature, normalized_seed = effective_sampling_controls(
        str(getattr(request, "model", "") or ""),
        str(getattr(request, "reasoning_effort", "") or ""),
        getattr(request, "temperature", None),
        normalized_seed,
    )
    return ModelCallAuditRecord(
        schema_version="1.0",
        operation=str(operation),
        scope=str(scope),
        provider_decision=str(
            getattr(response, "provider_decision", "")
            or getattr(request, "provider_decision", "")
            or "openai_primary"
        ),
        prompt_namespace=str(getattr(request, "prompt_namespace", "") or ""),
        prompt_hash=prompt_hash,
        rendered_prompt_redaction_hash=rendered_hash,
        model=str(
            getattr(response, "model", "") or getattr(request, "model", "") or ""
        ),
        temperature=actual_temperature,
        reasoning_effort=str(getattr(request, "reasoning_effort", "") or ""),
        seed=normalized_seed,
        seed_supported=normalized_seed is not None,
        schema_name=str(getattr(request, "schema_name", "") or ""),
        output_schema_version=str(getattr(request, "schema_version", "") or ""),
        response_id=str(
            getattr(response, "request_id", "")
            or getattr(response, "response_id", "")
            or ""
        ),
        input_tokens=getattr(response, "input_tokens", None),
        output_tokens=getattr(response, "output_tokens", None),
        total_tokens=getattr(response, "total_tokens", None),
        estimated_cost_usd=float(getattr(response, "estimated_cost_usd", 0.0) or 0.0),
        cache_key=str(getattr(request, "response_cache_key", "") or ""),
        cache_decision=(
            "enabled"
            if bool(getattr(request, "response_cache_enabled", False))
            else "disabled"
        ),
        validation_result=str(getattr(request, "validation_result", "") or ""),
    )


def build_model_call_replay_bundle(
    audit_record: ModelCallAuditRecord,
    *,
    comparison_evidence: ModelCallReplayComparisonEvidence | None = None,
) -> ModelCallReplayBundle:
    return ModelCallReplayBundle(
        schema_version="1.1",
        audit_record=audit_record,
        replay_inputs={
            "operation": audit_record.operation,
            "scope": audit_record.scope,
            "provider_decision": audit_record.provider_decision,
            "prompt_namespace": audit_record.prompt_namespace,
            "prompt_hash": audit_record.prompt_hash,
            "rendered_prompt_redaction_hash": (
                audit_record.rendered_prompt_redaction_hash
            ),
            "model": audit_record.model,
            "temperature": audit_record.temperature,
            "reasoning_effort": audit_record.reasoning_effort,
            "seed": audit_record.seed,
            "schema_name": audit_record.schema_name,
            "schema_version": audit_record.output_schema_version,
            "cache_key": audit_record.cache_key,
        },
        live_provider_call_allowed=False,
        comparison_evidence=comparison_evidence,
    )


def audit_record_fields(record: ModelCallAuditRecord) -> dict[str, object]:
    return {
        "operation": record.operation,
        "scope": record.scope,
        "provider_decision": record.provider_decision,
        "prompt_namespace": record.prompt_namespace,
        "prompt_hash": record.prompt_hash,
        "rendered_prompt_redaction_hash": record.rendered_prompt_redaction_hash,
        "model": record.model,
        "temperature": record.temperature,
        "reasoning_effort": record.reasoning_effort,
        "seed": record.seed,
        "seed_supported": record.seed_supported,
        "schema_name": record.schema_name,
        "schema_version": record.output_schema_version,
        "response_id": record.response_id,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "total_tokens": record.total_tokens,
        "estimated_cost_usd": record.estimated_cost_usd,
        "cache_key": record.cache_key,
        "cache_decision": record.cache_decision,
        "validation_result": record.validation_result,
    }
