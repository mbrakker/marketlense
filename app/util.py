import re
import time
from functools import wraps
import hashlib
from pathlib import Path

_slug_re = re.compile(r"[^a-z0-9]+")
def slugify(value: str) -> str:
    raise RuntimeError("slugify moved to src.utils.slugify")

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
    raise RuntimeError("pdf_has_eof_marker moved to src.utils.pdf_utils")
