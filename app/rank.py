from __future__ import annotations
import json, base64, logging, os, time
from typing import List, Dict, Any
from openai import OpenAI
from .candidates import Candidate

logger = logging.getLogger("market_lense.rank")

RANK_SCHEMA_HINT = """
Верни СТРОГИЙ JSON массив объектов, каждый:
{"id":"chart-0-1","type":"chart","score":0-100}
Никаких лишних ключей/комментариев.
"""

def rank_candidates_text_only(cands: List[Candidate], model: str, api_key: str) -> List[Dict[str, Any]]:
    client = OpenAI(api_key=api_key)
    rows = [{
        "id": c.id, "type": c.kind, "page": c.page,
        "meta": c.meta or {},
        "title_or_caption": (c.caption or "")[:300],
        "table_preview": c.preview_text[:400] if c.kind=="table" else ""
    } for c in cands]
    prompt = (
        "Задача: выбрать самые интересные графики/таблицы (0-100). "
        "Критерии: проценты/динамика/KPI/сильные инсайты. " + RANK_SCHEMA_HINT
    )
    resp = client.chat.completions.create(
        model=model,  # e.g. gpt-4.1-mini
        messages=[
            {"role":"system","content":"Ты продуктовый аналитик. Отвечай только валидным JSON."},
            {"role":"user","content": prompt},
            {"role":"user","content": json.dumps(rows, ensure_ascii=False)}
        ],
        response_format={"type":"json_object"},
        temperature=1,
    )
    content = resp.choices[0].message.content

    # Save raw model response for debugging/inspection
    try:
        dbg_dir = os.path.join(os.getcwd(), "debug")
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

    # Defensive: accept either a bare list or a dict with a `results` key.
    if isinstance(parsed, list):
        return parsed

    # If the model returned an object with a `results` list, use that.
    if isinstance(parsed, dict):
        if "results" in parsed and isinstance(parsed["results"], list):
            logger.info("Coercing ranking response: using parsed['results'] list")
            return parsed["results"]
        # some models might wrap payload under other keys like 'data' or 'items'
        for candidate_key in ("data", "items", "results"):
            if candidate_key in parsed and isinstance(parsed[candidate_key], list):
                logger.info("Coercing ranking response: using parsed['%s'] list", candidate_key)
                return parsed[candidate_key]

    logger.error("Ranking response has unexpected shape: %s", type(parsed).__name__)
    raise ValueError("Ranking response did not return a JSON list of objects")
