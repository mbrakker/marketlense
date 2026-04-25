from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_REVIEW_FIELDS = ("cadence", "owner", "agenda_path", "next_review_date")
REQUIRED_INITIATIVE_FIELDS = (
    "id",
    "title",
    "owner",
    "status",
    "review_date",
    "baseline_metric",
    "current_metric",
    "target_metric",
    "decision",
)
VALID_STATUSES = {"active", "completed", "replanned", "descoped", "stalled"}
VALID_STALLED_DECISIONS = {"replanned", "descoped"}


def _parse_date(value: Any, field_name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc


def _require_text(item: dict[str, Any], field_name: str, label: str) -> None:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} missing non-empty {field_name}")


def validate_quality_ledger(path: Path) -> list[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("quality ledger root must be a mapping")
    if str(payload.get("schema_version") or "") != "1.0":
        raise ValueError("quality ledger schema_version must be 1.0")

    review = payload.get("review")
    if not isinstance(review, dict):
        raise ValueError("quality ledger review block is required")
    for field_name in REQUIRED_REVIEW_FIELDS:
        _require_text(review, field_name, "review")
    _parse_date(review["next_review_date"], "review.next_review_date")
    agenda_path = Path(str(review["agenda_path"]))
    if not agenda_path.is_absolute():
        agenda_path = ROOT / agenda_path
    if not agenda_path.exists():
        raise ValueError(f"review agenda_path does not exist: {review['agenda_path']}")

    initiatives = payload.get("initiatives")
    if not isinstance(initiatives, list) or not initiatives:
        raise ValueError("quality ledger requires at least one initiative")

    ids: set[str] = set()
    validated: list[str] = []
    for index, raw_item in enumerate(initiatives, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError(f"initiative {index} must be a mapping")
        label = f"initiative {index}"
        for field_name in REQUIRED_INITIATIVE_FIELDS:
            _require_text(raw_item, field_name, label)
        item_id = str(raw_item["id"]).strip()
        if item_id in ids:
            raise ValueError(f"duplicate initiative id: {item_id}")
        ids.add(item_id)
        status = str(raw_item["status"]).strip()
        if status not in VALID_STATUSES:
            raise ValueError(f"initiative {item_id} has invalid status: {status}")
        _parse_date(raw_item["review_date"], f"initiative {item_id}.review_date")
        decision = str(raw_item["decision"]).strip()
        if status == "stalled" and decision not in VALID_STALLED_DECISIONS:
            raise ValueError(
                f"stalled initiative {item_id} must be replanned or descoped"
            )
        validated.append(item_id)
    return validated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the monthly quality initiative ledger."
    )
    parser.add_argument(
        "--ledger",
        default="docs/quality/initiative_ledger.yaml",
        help="Quality initiative ledger YAML path.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    ledger_path = ROOT / args.ledger
    try:
        ids = validate_quality_ledger(ledger_path)
    except (OSError, ValueError) as exc:
        print(f"Quality ledger gate failed: {exc}")
        return 1
    print(f"Quality ledger gate passed: {len(ids)} initiatives validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
