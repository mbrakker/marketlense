from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List

from openai import OpenAI

from src.contracts.report_assets import RankRequest, RankResponse
from src.contracts.report_models import RankedCandidate
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.rank_service")

RANK_SCHEMA_HINT = (
    'Return STRICT JSON of the form: '
    '{"results":[{"id":"chart-0-1","type":"chart","score":0-100}]}. '
    "No extra keys or commentary."
)


def rank_candidates(request: RankRequest, ctx: RunContext) -> RankResponse:
    log_event(
        logger,
        ctx,
        role="service",
        event="rank_candidates_start",
        fields={"count": len(request.candidates), "model": request.model},
    )
    client = OpenAI(api_key=request.api_key)
    rows = [{
        "id": c.id,
        "type": c.kind,
        "page": c.page,
        "meta": c.meta or {},
        "title_or_caption": (c.caption or "")[:300],
        "table_preview": c.preview_text[:400] if c.kind == "table" else "",
    } for c in request.candidates]
    prompt = (
        "Task: select the most interesting charts/tables (0-100). "
        "Criteria: percentages, deltas, KPIs, strong insights. " + RANK_SCHEMA_HINT
    )
    resp = client.chat.completions.create(
        model=request.model,
        messages=[
            {"role": "system", "content": "You are a product analyst. Return valid JSON only."},
            {"role": "user", "content": prompt},
            {"role": "user", "content": json.dumps(rows, ensure_ascii=True)},
        ],
        response_format={"type": "json_object"},
        temperature=1,
    )
    content = resp.choices[0].message.content

    if request.debug_dir:
        try:
            dbg_dir = os.path.join(os.getcwd(), request.debug_dir)
            os.makedirs(dbg_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d-%H%M%S")
            fname = f"rank_raw_{ts}.txt"
            path = os.path.join(dbg_dir, fname)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            logger.info("Saved raw ranking response to %s", path)
        except Exception:
            logger.exception("Failed to write debug ranking response file")

    try:
        parsed = json.loads(content)
    except Exception:
        logger.exception("Failed to parse ranking response JSON. Raw content: %s", content)
        raise

    items: List[Dict[str, Any]]
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        if "results" in parsed and isinstance(parsed["results"], list):
            items = parsed["results"]
        else:
            found = False
            for candidate_key in ("data", "items", "results"):
                if candidate_key in parsed and isinstance(parsed[candidate_key], list):
                    items = parsed[candidate_key]
                    found = True
                    break
            if not found:
                raise ValueError("Ranking response did not return a JSON list of objects")
    else:
        raise ValueError("Ranking response did not return a JSON list of objects")

    result: List[RankedCandidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            ranked = RankedCandidate(
                id=item.get("id", ""),
                type=item.get("type", ""),
                score=int(item.get("score", 0)),
            )
            result.append(ranked)
        except (ValueError, TypeError):
            continue

    log_event(
        logger,
        ctx,
        role="service",
        event="rank_candidates_complete",
        fields={"count": len(result)},
    )
    return RankResponse(schema_version="1.0", results=result)
