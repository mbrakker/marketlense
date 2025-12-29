from __future__ import annotations

import hashlib
import re

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    raw = value.strip()
    v = raw.lower()
    v = _slug_re.sub("-", v)
    v = v.strip("-")
    if not v:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
        return f"report-{digest}"
    return v[:120]
