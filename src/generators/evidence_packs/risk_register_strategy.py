from __future__ import annotations

from src.generators.evidence_packs.base import (
    EvidencePackStrategy,
    PackNormalizationResult,
    build_list_pack_empty_payload,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    first_non_empty_text,
    to_dict,
)


def build_empty_payload(reason: str) -> dict[str, object]:
    return build_list_pack_empty_payload(root_key="risk_register", reason=reason)


def normalize_risk_register(raw_risks: object) -> list[dict[str, object]]:
    risks: list[dict[str, object]] = []
    for idx, entry in enumerate(coerce_pack_items(raw_risks)):
        if isinstance(entry, str):
            text_value = entry.strip()
            if not text_value:
                continue
            risks.append(
                {
                    "id": f"risk_{idx + 1}",
                    "risk": text_value,
                    "impact": "",
                    "likelihood": "",
                    "mitigation": "",
                    "evidence_id": "",
                }
            )
            continue
        if not isinstance(entry, dict):
            continue
        item = to_dict(entry)
        risk = first_non_empty_text(
            item.get("risk"), item.get("title"), item.get("description")
        )
        impact = first_non_empty_text(item.get("impact"), item.get("severity"))
        likelihood = first_non_empty_text(
            item.get("likelihood"), item.get("probability")
        )
        mitigation = first_non_empty_text(item.get("mitigation"), item.get("response"))
        evidence_id = first_non_empty_text(
            item.get("evidence_id"),
            item.get("reference_id"),
            item.get("finding_id"),
        )
        if not (risk or impact or likelihood or mitigation or evidence_id):
            continue
        risks.append(
            {
                "id": first_non_empty_text(item.get("id"), f"risk_{idx + 1}"),
                "risk": risk,
                "impact": impact,
                "likelihood": likelihood,
                "mitigation": mitigation,
                "evidence_id": evidence_id,
            }
        )
    return risks


def normalize_payload(
    payload: object, report_id: str, report_name: str
) -> PackNormalizationResult:
    del report_id, report_name
    cache_meta = None
    source = payload
    if isinstance(payload, dict):
        cache_meta = (
            payload.get("_cache") if isinstance(payload.get("_cache"), dict) else None
        )
        wrapped = payload.get("risk_register")
        if wrapped is None:
            wrapped = payload.get("evidence_pack")
        if wrapped is None:
            wrapped = payload.get("evidencePack")
        if wrapped is not None:
            source = wrapped

    root = to_dict(source)
    normalized = build_empty_payload("")
    raw_risks = root.get("risk_register") if isinstance(source, dict) else source
    if raw_risks is None:
        raw_risks = root.get("risks")
    normalized["risk_register"] = normalize_risk_register(raw_risks)
    if cache_meta:
        normalized["_cache"] = cache_meta
    return PackNormalizationResult(payload=normalized, changed=normalized != payload)


RISK_REGISTER_STRATEGY = EvidencePackStrategy(
    pack_name="risk_register",
    prompt_namespace_suffix="evidence_packs/risk_register",
    schema_name="risk_register_pack",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
