# app/normalize.py
from __future__ import annotations
from typing import Any, Dict, List

def _s(x: Any) -> str:
    if x is None: return ""
    return x if isinstance(x, str) else str(x)

def _list_str(x: Any) -> List[str]:
    if not isinstance(x, list): x = [x] if x is not None else []
    out = [ _s(i) for i in x ]
    return out

def normalize_report_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Coerces the OpenAI JSON into the expected schema so downstream code and Jinja never crash.
    Ensures:
      - tldr/commentary/source are strings
      - insights is a list of exactly 5 strings (truncate/pad)
      - quote and figure are dicts with required keys as strings
    Leaves any extra keys intact.
    """
    if not isinstance(data, dict):
        data = {"tldr": _s(data)}

    # tldr / commentary / source
    data["tldr"] = _s(data.get("tldr", ""))
    data["commentary"] = _s(data.get("commentary", ""))
    data["source"] = _s(data.get("source", ""))

    # insights → exactly 5 strings
    ins = _list_str(data.get("insights", []))
    if len(ins) < 5:
        ins += [""] * (5 - len(ins))
    data["insights"] = ins[:5]

    # quote → dict with text/author
    q = data.get("quote", {})
    if not isinstance(q, dict):
        q = {"text": _s(q), "author": "Unknown"}
    q["text"] = _s(q.get("text", ""))
    q["author"] = _s(q.get("author", "Unknown"))
    data["quote"] = q

    # figure → dict with title/evidence
    f = data.get("figure", {})
    if not isinstance(f, dict):
        f = {"title": _s(f), "evidence": ""}
    f["title"] = _s(f.get("title", ""))
    f["evidence"] = _s(f.get("evidence", ""))
    data["figure"] = f

    # ensure optional fields used later exist with safe types
    if not isinstance(data.get("_figure_gallery", []), list):
        data["_figure_gallery"] = []
    data["_figure_top"] = _s(data.get("_figure_top", ""))
    data["_figure_image"] = _s(data.get("_figure_image", ""))

    # If a top figure path wasn't set but a selected figure image exists,
    # use it as the top figure so templates show it.
    if not data["_figure_top"] and data["_figure_image"]:
        data["_figure_top"] = data["_figure_image"]

    return data
