"""Compare two retained model-call replay bundles without provider access."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import MISSING, asdict, fields
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.contracts.model_call_replay_comparison import (  # noqa: E402
    ModelCallReplayBundleComparisonRequest,
    ModelCallReplayBundleComparisonResponse,
)
from src.contracts.workflow_control import (  # noqa: E402
    ModelCallAuditRecord,
    ModelCallReplayBundle,
    ModelCallReplayComparisonEvidence,
)
from src.services import llm_service  # noqa: E402

_MAX_BUNDLE_BYTES = 1_000_000
_MAX_JSON_NODES = 4096
_MAX_JSON_DEPTH = 16
_FORBIDDEN_CONTENT_KEYS = frozenset(
    {
        "system_prompt",
        "user_prompt",
        "prompt_text",
        "source_text",
        "model_response",
        "response_text",
        "api_key",
        "access_token",
        "secret",
        "credential",
        "credentials",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_EXPECTATION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class _DuplicateJsonKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError


def _payload_issue(value: object) -> str | None:
    pending: list[tuple[object, int]] = [(value, 0)]
    visited = 0
    while pending:
        current, depth = pending.pop()
        visited += 1
        if visited > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            return "BUNDLE_TOO_COMPLEX"
        if isinstance(current, dict):
            for key, nested in current.items():
                if isinstance(key, str) and key.casefold() in _FORBIDDEN_CONTENT_KEYS:
                    return "BUNDLE_CONTENT_UNSAFE"
                pending.append((nested, depth + 1))
        elif isinstance(current, list):
            pending.extend((nested, depth + 1) for nested in current)
    return None


def _load_bundle(
    path: Path, side: str
) -> tuple[ModelCallReplayBundle | None, str, str | None]:
    try:
        with path.open("rb") as bundle_file:
            raw_bytes = bundle_file.read(_MAX_BUNDLE_BYTES + 1)
    except OSError:
        return None, "", f"{side}_BUNDLE_UNREADABLE"
    if len(raw_bytes) > _MAX_BUNDLE_BYTES:
        return None, "", f"{side}_BUNDLE_TOO_LARGE"

    bundle_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        payload = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
        return None, bundle_sha256, f"{side}_JSON_MALFORMED"
    payload_issue = _payload_issue(payload)
    if payload_issue is not None:
        return None, bundle_sha256, f"{side}_{payload_issue}"

    try:
        bundle = _deserialize_bundle(payload)
    except (TypeError, ValueError, KeyError):
        return None, bundle_sha256, f"{side}_BUNDLE_STRUCTURE_MALFORMED"
    return bundle, bundle_sha256, None


def _deserialize_bundle(payload: object) -> ModelCallReplayBundle:
    if not isinstance(payload, dict):
        raise ValueError
    bundle_fields = {item.name for item in fields(ModelCallReplayBundle)}
    required_bundle_fields = {
        "schema_version",
        "audit_record",
        "replay_inputs",
        "live_provider_call_allowed",
    }
    if not required_bundle_fields.issubset(payload) or set(payload) - bundle_fields:
        raise ValueError

    audit_payload = payload["audit_record"]
    if not isinstance(audit_payload, dict):
        raise ValueError
    audit_fields = {item.name: item for item in fields(ModelCallAuditRecord)}
    if set(audit_payload) - audit_fields.keys():
        raise ValueError
    for name, item in audit_fields.items():
        if (
            name not in audit_payload
            and item.default is MISSING
            and item.default_factory is MISSING
        ):
            raise ValueError
    audit_payload = dict(audit_payload)
    audit_payload.setdefault("reasoning_effort", "")
    if not _valid_audit_values(audit_payload):
        raise ValueError
    audit_record = ModelCallAuditRecord(**audit_payload)

    replay_inputs = payload["replay_inputs"]
    if not isinstance(replay_inputs, dict):
        raise ValueError
    live_call_allowed = payload["live_provider_call_allowed"]
    if not isinstance(live_call_allowed, bool):
        raise ValueError

    evidence_payload = payload.get("comparison_evidence")
    evidence = None
    if evidence_payload is not None:
        if not isinstance(evidence_payload, dict):
            raise ValueError
        evidence_fields = {
            item.name: item for item in fields(ModelCallReplayComparisonEvidence)
        }
        if set(evidence_payload) - evidence_fields.keys():
            raise ValueError
        if not {"schema_version", "artifact_family"}.issubset(evidence_payload):
            raise ValueError
        for name in (
            "policy_sha256",
            "evidence_sha256",
            "output_sha256",
            "artifact_sha256",
            "schema_sha256",
        ):
            if (
                name in evidence_payload
                and evidence_payload[name] is not None
                and (
                    not isinstance(evidence_payload[name], str)
                    or not _SHA256_RE.fullmatch(evidence_payload[name])
                )
            ):
                raise ValueError
        evidence = ModelCallReplayComparisonEvidence(**evidence_payload)

    if not isinstance(payload["schema_version"], str):
        raise ValueError
    return ModelCallReplayBundle(
        schema_version=payload["schema_version"],
        audit_record=audit_record,
        replay_inputs=replay_inputs,
        live_provider_call_allowed=live_call_allowed,
        comparison_evidence=evidence,
    )


def _valid_audit_values(payload: dict[str, Any]) -> bool:
    string_fields = {
        "schema_version",
        "operation",
        "scope",
        "provider_decision",
        "prompt_namespace",
        "prompt_hash",
        "rendered_prompt_redaction_hash",
        "model",
        "schema_name",
        "output_schema_version",
        "response_id",
        "cache_key",
        "cache_decision",
        "validation_result",
        "reasoning_effort",
    }
    if any(not isinstance(payload.get(name), str) for name in string_fields):
        return False
    if not isinstance(payload.get("seed_supported"), bool):
        return False
    for name in ("temperature", "estimated_cost_usd"):
        value = payload.get(name)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return False
    for name in ("seed", "input_tokens", "output_tokens", "total_tokens"):
        value = payload.get(name)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            return False
    return True


def _parse_expectations(values: list[str]) -> dict[str, str]:
    if len(values) > 16:
        raise ValueError
    expectations: dict[str, str] = {}
    for value in values:
        name, separator, expected = value.partition("=")
        if (
            not separator
            or not _EXPECTATION_NAME_RE.fullmatch(name)
            or len(name) > 64
            or not expected
            or len(expected) > 128
            or name in expectations
        ):
            raise ValueError
        expectations[name] = expected
    return expectations


def _render_response(response: ModelCallReplayBundleComparisonResponse) -> str:
    return json.dumps(
        asdict(response),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--artifact-family", required=True)
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="Optional candidate identity expectation; values are omitted from output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        expectations = _parse_expectations(args.expect)
    except ValueError:
        parser.error("Invalid compatibility expectation.")
    baseline, baseline_ref, baseline_error = _load_bundle(args.baseline, "BASELINE")
    candidate, candidate_ref, candidate_error = _load_bundle(
        args.candidate, "CANDIDATE"
    )
    diagnostics = tuple(
        code for code in (baseline_error, candidate_error) if code is not None
    )
    response = llm_service.compare_model_call_replay_bundles(
        ModelCallReplayBundleComparisonRequest(
            schema_version="1.0",
            artifact_family=args.artifact_family,
            baseline_bundle=baseline,
            candidate_bundle=candidate,
            baseline_bundle_sha256=baseline_ref,
            candidate_bundle_sha256=candidate_ref,
            compatibility_expectations=expectations,
            input_diagnostic_codes=diagnostics,
        )
    )
    print(_render_response(response))
    return 2 if response.classification == "malformed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
