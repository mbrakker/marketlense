import re
import time
from functools import wraps

_slug_re = re.compile(r"[^a-z0-9]+")
def slugify(value: str) -> str:
    v = value.strip().lower()
    v = _slug_re.sub("-", v)
    v = v.strip("-")
    return v[:120] or "report"

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
