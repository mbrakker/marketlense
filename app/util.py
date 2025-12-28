import re
import time
from functools import wraps
import hashlib
from pathlib import Path

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

def retry(backoffs=(1, 2, 4, 8), exceptions=(Exception,)):
    def deco(fn):
        @wraps(fn)
        def wrap(*a, **kw):
            last = None
            for n, delay in enumerate((0,)+tuple(backoffs)):
                try:
                    if delay: time.sleep(delay)
                    return fn(*a, **kw)
                except exceptions as e:
                    last = e
            raise last
        return wrap
    return deco

def pdf_has_eof_marker(path: str, tail_bytes: int = 2048) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        with p.open("rb") as fh:
            if p.stat().st_size <= tail_bytes:
                data = fh.read()
            else:
                fh.seek(-tail_bytes, 2)
                data = fh.read()
        return b"%%EOF" in data
    except Exception:
        return False
