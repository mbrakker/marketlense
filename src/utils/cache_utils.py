from __future__ import annotations

import hashlib
import json


def stable_json_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def sha256_json(payload: object) -> str:
    return hashlib.sha256(stable_json_dumps(payload).encode("utf-8")).hexdigest()
