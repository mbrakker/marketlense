from __future__ import annotations

from src.generators.evidence_packs.base import (
    build_list_pack_strategy,
)
from src.generators.evidence_packs.common import (
    coerce_pack_items,
    first_non_empty_text,
    to_dict,
)
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


RISK_REGISTER_STRATEGY = build_list_pack_strategy(
    pack_name="risk_register",
    prompt_namespace_suffix="evidence_packs/risk_register",
    schema_name="risk_register_pack",
    root_key="risk_register",
    source_aliases=("risks",),
    normalize_items=normalize_risk_register,
)
