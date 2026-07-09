from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = ROOT / "docs" / "quality" / "architecture_policy.yaml"


def load_architecture_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Architecture policy must be a mapping: {path}")
    if str(payload.get("schema_version") or "") != "1.0":
        raise ValueError("Architecture policy schema_version must be 1.0")
    return payload
