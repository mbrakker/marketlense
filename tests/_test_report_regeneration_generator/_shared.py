from __future__ import annotations

import json
import re

from src.contracts.openai import OpenAIResponseResult
from src.contracts.soft_copy_claim_provenance import (
    align_soft_copy_claim_bindings_to_text,
    soft_copy_material_sentences,
)


_MISSING_REPAIR_FIXTURE_PATH = object()


def _legacy_repair_decision_response(req, result):
    """Adapt older family fixtures to the current private patch contract."""
    variables = _parse_fixture_variables(req.user_prompt)
    if variables is None:
        raise AssertionError("Fixture repair request has no rendered variables")
    context = json.loads(variables["repair_context_json"])
    grounding = json.loads(variables["grounding_package_json"])
    if not context["allowed_paths"]:
        raise AssertionError("Regeneration test fixture needs explicit allowed_paths")
    allowed_paths = context["allowed_paths"]
    resolved_values = [
        (path, _legacy_repair_path_value(result.parsed_json, path))
        for path in allowed_paths
    ]
    path, patch_value = next(
        (
            pair
            for pair in resolved_values
            if pair[1] is not _MISSING_REPAIR_FIXTURE_PATH
        ),
        (allowed_paths[0], _MISSING_REPAIR_FIXTURE_PATH),
    )
    if patch_value is _MISSING_REPAIR_FIXTURE_PATH:
        raise AssertionError(f"Fixture response does not cover planned path {path!r}")
    failure_reasons = json.loads(variables.get("failure_reasons_json", "[]"))
    quarantined = set(grounding.get("quarantined_evidence_ids", []))
    quarantined.update(context.get("quarantined_evidence_ids", []))
    quarantined.update(
        evidence_id
        for issue in failure_reasons
        if isinstance(issue, dict)
        for evidence_id in issue.get("excluded_evidence_ids", [])
    )
    retained_evidence_ids = set(grounding.get("evidence_ids", [])) - quarantined
    provenance = result.parsed_json.get("claim_provenance", [])
    used_evidence_ids = list(
        dict.fromkeys(
            str(evidence_id)
            for claim in provenance
            if isinstance(claim, dict)
            for evidence_id in claim.get("evidence_ids", [])
            if str(evidence_id) in retained_evidence_ids
        )
    )
    if not used_evidence_ids and retained_evidence_ids:
        used_evidence_ids = [sorted(retained_evidence_ids)[0]]
    provenance = [
        {
            "claim": str(claim.get("claim") or ""),
            "classification": str(claim.get("classification") or "interpretive"),
            "evidence_ids": [
                str(evidence_id)
                for evidence_id in claim.get("evidence_ids", [])
                if evidence_id in used_evidence_ids
            ],
        }
        for claim in provenance
        if isinstance(claim, dict)
        and set(claim.get("evidence_ids") or []).intersection(used_evidence_ids)
    ]
    if isinstance(patch_value, str):
        family = path.split(".", 1)[0].split("[", 1)[0]
        if family in {"summary", "expert_comment", "linkedin_post"}:
            provenance = align_soft_copy_claim_bindings_to_text(
                artifact_family=family,
                text=patch_value,
                claim_bindings=provenance,
            )
    decision = {
        "schema_version": "1.0",
        "repair_action": context["repair_action"],
        "repair_strategy": context["repair_strategy"],
        "evidence_ids_used": used_evidence_ids,
        "protected_fields": context["required_protected_fields"],
        "changed_paths": [path],
        "minimal_patch": [
            {
                "op": "replace",
                "path": path,
                "value_json": json.dumps(patch_value, ensure_ascii=False),
            }
        ],
        "claim_provenance": provenance,
    }
    payload = {"repair_decision": decision}
    return OpenAIResponseResult(
        schema_version=result.schema_version,
        text=json.dumps(payload, ensure_ascii=False),
        parsed_json=payload,
        request_id=result.request_id,
    )


def _legacy_repair_path_value(payload, path):
    tokens = re.findall(r"([^.[\]]+)(?:\[([^\]]+)\])?", path)
    if not tokens:
        return _MISSING_REPAIR_FIXTURE_PATH
    current = payload
    for key, selector in tokens:
        if isinstance(current, dict):
            if key not in current:
                return _MISSING_REPAIR_FIXTURE_PATH
            current = current[key]
        else:
            return _MISSING_REPAIR_FIXTURE_PATH
        if not selector:
            continue
        if selector.isdigit() and isinstance(current, list):
            index = int(selector)
            if index >= len(current):
                return _MISSING_REPAIR_FIXTURE_PATH
            current = current[index]
            continue
        selector_key, separator, selector_value = selector.partition("=")
        if separator and selector_key == "claim_index":
            if not isinstance(current, str):
                return _MISSING_REPAIR_FIXTURE_PATH
            sentences = soft_copy_material_sentences(current)
            if len(sentences) > 1:
                try:
                    current = sentences[int(selector_value)]
                except (IndexError, ValueError):
                    return _MISSING_REPAIR_FIXTURE_PATH
            continue
        if not separator or not isinstance(current, list):
            return _MISSING_REPAIR_FIXTURE_PATH
        matches = [
            item
            for item in current
            if isinstance(item, dict) and str(item.get(selector_key)) == selector_value
        ]
        if selector_key == "item":
            matches = [
                item
                for item in current
                if isinstance(item, dict)
                and selector_value
                in {
                    str(item.get(field) or "").strip()
                    for field in (
                        "id",
                        "insight_id",
                        "key_figure_id",
                        "claim_id",
                        "evidence_id",
                    )
                }
            ]
        if len(matches) != 1:
            return _MISSING_REPAIR_FIXTURE_PATH
        current = matches[0]
    return current


def _parse_fixture_variables(value):
    decoder = json.JSONDecoder()
    for index, character in enumerate(str(value)):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(value, index)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and "repair_context_json" in parsed:
            return parsed
    return None
