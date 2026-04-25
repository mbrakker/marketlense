from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_RUNBOOK_FIELDS = (
    "failure_code",
    "owner",
    "severity",
    "runbook_path",
    "dashboard_link",
    "alert_labels",
    "detector_log_events",
    "remediation_hooks",
)
REQUIRED_HOOK_FIELDS = ("name", "trigger", "dry_run", "command", "safety")
VALID_SEVERITIES = {"info", "warning", "error", "critical"}


def _require_text(item: dict[str, Any], field_name: str, label: str) -> str:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} missing non-empty {field_name}")
    return value.strip()


def validate_remediation_runbooks(path: Path) -> list[str]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("remediation registry root must be a mapping")
    if str(payload.get("schema_version") or "") != "1.0":
        raise ValueError("remediation registry schema_version must be 1.0")
    _require_text(payload, "owner", "registry")
    date.fromisoformat(_require_text(payload, "last_drill_date", "registry"))

    runbooks = payload.get("runbooks")
    if not isinstance(runbooks, list) or not runbooks:
        raise ValueError("remediation registry requires at least one runbook")

    codes: set[str] = set()
    validated: list[str] = []
    for index, raw_item in enumerate(runbooks, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError(f"runbook {index} must be a mapping")
        label = f"runbook {index}"
        for field_name in REQUIRED_RUNBOOK_FIELDS:
            if field_name not in raw_item:
                raise ValueError(f"{label} missing {field_name}")
        failure_code = _require_text(raw_item, "failure_code", label)
        if failure_code in codes:
            raise ValueError(f"duplicate failure_code: {failure_code}")
        codes.add(failure_code)
        severity = _require_text(raw_item, "severity", label)
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"{failure_code} has invalid severity: {severity}")
        runbook_path = Path(_require_text(raw_item, "runbook_path", label))
        if not runbook_path.is_absolute():
            runbook_path = ROOT / runbook_path
        if not runbook_path.exists():
            raise ValueError(f"{failure_code} runbook_path does not exist")
        alert_labels = raw_item.get("alert_labels")
        if not isinstance(alert_labels, dict) or not alert_labels:
            raise ValueError(f"{failure_code} requires alert_labels")
        detector_events = raw_item.get("detector_log_events")
        if not isinstance(detector_events, list) or not all(
            isinstance(event, str) and event.strip() for event in detector_events
        ):
            raise ValueError(f"{failure_code} requires detector_log_events")
        hooks = raw_item.get("remediation_hooks")
        if not isinstance(hooks, list) or not hooks:
            raise ValueError(f"{failure_code} requires remediation_hooks")
        for hook_index, raw_hook in enumerate(hooks, start=1):
            if not isinstance(raw_hook, dict):
                raise ValueError(f"{failure_code} hook {hook_index} must be a mapping")
            hook_label = f"{failure_code} hook {hook_index}"
            for field_name in REQUIRED_HOOK_FIELDS:
                if field_name not in raw_hook:
                    raise ValueError(f"{hook_label} missing {field_name}")
            _require_text(raw_hook, "name", hook_label)
            _require_text(raw_hook, "trigger", hook_label)
            _require_text(raw_hook, "command", hook_label)
            _require_text(raw_hook, "safety", hook_label)
            if raw_hook.get("dry_run") is not True:
                raise ValueError(f"{hook_label} must be dry_run: true")
        validated.append(failure_code)
    return validated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate top failure runbooks and remediation hook metadata."
    )
    parser.add_argument(
        "--registry",
        default="docs/ops/failure_remediation.yaml",
        help="Failure remediation registry YAML path.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        codes = validate_remediation_runbooks(ROOT / args.registry)
    except (OSError, ValueError) as exc:
        print(f"Remediation runbook gate failed: {exc}")
        return 1
    print(f"Remediation runbook gate passed: {len(codes)} failure classes validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
