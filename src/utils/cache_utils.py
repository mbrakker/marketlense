from __future__ import annotations

import hashlib
import json


def stable_json_dumps(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def sha256_json(payload: dict) -> str:
    return hashlib.sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()
