from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = ROOT / "docs" / "quality" / "refactor_movement_evidence.json"


def validate_movement_evidence(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    records = payload.get("records")
    if not isinstance(records, list):
        return [*errors, "records must be a list"]
    required = (
        "original_file",
        "baseline_ref",
        "moved_symbol_count",
        "unchanged_moved_symbol_count",
        "changed_moved_symbol_count",
        "facade_owned_definitions",
    )
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"record {index} must be an object")
            continue
        for field in required:
            if field not in record:
                errors.append(f"record {index} missing {field}")
        for field in (
            "moved_symbol_count",
            "unchanged_moved_symbol_count",
            "changed_moved_symbol_count",
        ):
            if field in record and (
                not isinstance(record[field], int) or record[field] < 0
            ):
                errors.append(f"record {index} {field} must be a non-negative integer")
        if (
            isinstance(record.get("moved_symbol_count"), int)
            and isinstance(record.get("unchanged_moved_symbol_count"), int)
            and isinstance(record.get("changed_moved_symbol_count"), int)
        ):
            if record["moved_symbol_count"] != (
                record["unchanged_moved_symbol_count"]
                + record["changed_moved_symbol_count"]
            ):
                errors.append(f"record {index} moved symbol counts do not balance")
        if "facade_owned_definitions" in record and not isinstance(
            record["facade_owned_definitions"], list
        ):
            errors.append(f"record {index} facade_owned_definitions must be a list")
    return errors


def main() -> int:
    payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    errors = validate_movement_evidence(payload)
    if errors:
        print("Refactor movement evidence gate failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "Refactor movement evidence gate passed: "
        f"{len(payload.get('records', []))} record(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
