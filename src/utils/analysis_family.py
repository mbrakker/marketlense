from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.contracts.analysis_family import AnalysisFamilyStatus


def serialize_family_status(status: AnalysisFamilyStatus) -> dict[str, Any]:
    return asdict(status)


def get_family_status(payload: Any, family: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    family_status = payload.get("family_status")
    if not isinstance(family_status, dict):
        return {}
    if (
        str(family_status.get("family") or "").strip() == family
        and str(family_status.get("status") or "").strip()
    ):
        return family_status
    entry = family_status.get(family)
    return entry if isinstance(entry, dict) else {}


def family_is_abstained(payload: Any, family: str) -> bool:
    return str(
        get_family_status(payload, family).get("status") or ""
    ).strip().lower() == ("abstained")


def family_policy_action(payload: Any, family: str) -> str:
    return str(get_family_status(payload, family).get("policy_action") or "").strip()


def family_reason(payload: Any, family: str) -> str:
    return str(get_family_status(payload, family).get("reason") or "").strip()
