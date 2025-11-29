# app/openai_client.py
import json
from typing import Any, Dict

from openai import OpenAI
from pypdf import PdfReader

from .util import retry
import logging

logger = logging.getLogger("market_lense.openai_client")

# ---------- Prompt & JSON Schema (Structured Output shape) ----------

PROMPT = """Task: Analyze the attached PDF text and return STRICT JSON per schema.
Rules:
1) TL;DR ≤ 4 sentences, no fluff.
2) 5 insights: each must contain a concrete fact/metric/KPI or a clear causal takeaway.
3) Quote: verbatim from the report + author/role (if unknown, set author="Unknown").
4) Figure: pick one key chart/table/metric; explain what it demonstrates (2–3 lines).
5) Commentary: 1 paragraph on implications for brands/measurement/ROAS.
6) Source: put the primary URL if present in the document; else empty string.
7) If uncertain about a number, state uncertainty explicitly.
8) Return ONLY valid JSON. Do not add any extra keys or text.
"""

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["tldr", "insights", "quote", "figure", "commentary", "source"],
    "additionalProperties": False,
    "properties": {
        "tldr": {"type": "string"},
        "insights": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "quote": {
            "type": "object",
            "required": ["text", "author"],
            "additionalProperties": False,
            "properties": {
                "text": {"type": "string"},
                "author": {"type": "string"},
            },
        },
        "figure": {
            "type": "object",
            "required": ["title", "evidence"],
            "additionalProperties": False,
            "properties": {
                "title": {"type": "string"},
                "evidence": {"type": "string"},
            },
        },
        "commentary": {"type": "string"},
        "source": {"type": "string"},
    },
}

REQUIRED_KEYS = ("tldr", "insights", "quote", "figure", "commentary", "source")


# ---------- Helpers ----------

def _validate_payload(data: Dict[str, Any]) -> None:
    for k in REQUIRED_KEYS:
        if k not in data:
            raise ValueError(f"Missing key in JSON: {k}")
    if not isinstance(data.get("insights"), list) or len(data["insights"]) != 5:
        raise ValueError("`insights` must be a list of exactly 5 items")


def _extract_text_first_pages(pdf_path: str, max_pages: int = 5, max_chars: int = 80_000) -> str:
    reader = PdfReader(pdf_path)
    pages = min(len(reader.pages), max_pages)
    chunks = []
    for i in range(pages):
        # extract_text() can return None; guard it
        t = reader.pages[i].extract_text() or ""
        chunks.append(t)
    text = "\n\n".join(chunks)
    return text[:max_chars]


# ---------- Main entry (Completions JSON mode; SDK 2.x compatible) ----------

@retry(backoffs=(1, 2, 4))
def analyze_pdf(pdf_path: str, model: str, temperature: float, openai_api_key: str) -> Dict[str, Any]:
    """
    MVP path: extract first ~5 pages of text locally, then call Chat Completions in JSON mode.
    This avoids file uploads and works across openai==2.x.

    Returns: dict matching SCHEMA + adds _openai_file_id="" (no upload in this path).
    """
    logger.info("analyze_pdf called: pdf_path=%s model=%s temperature=%s", pdf_path, model, temperature)

    # 1) Extract text
    extracted = _extract_text_first_pages(pdf_path)
    logger.debug("Extracted text length=%d", len(extracted or ""))

    # 2) Call OpenAI Chat Completions with JSON mode
    client = OpenAI(api_key=openai_api_key)
    logger.info("Calling OpenAI Chat Completions (model=%s)", model)
    resp = client.chat.completions.create(
        model=model,  # e.g., "gpt-4.1-mini"
        messages=[
            {"role": "system", "content": "You are a careful analyst. Output strict JSON only."},
            {
                "role": "user",
                "content": (
                    f"{PROMPT}\n\n"
                    "[EXTRACTED TEXT START]\n"
                    f"{extracted}\n"
                    "[EXTRACTED TEXT END]"
                ),
            },
        ],
        response_format={"type": "json_object"},  # ensures valid JSON string
        temperature=temperature,
    )

    payload = resp.choices[0].message.content
    logger.debug("Received response payload length=%d", len(payload or ""))
    data = json.loads(payload)

    # 3) Defensive validation
    _validate_payload(data)

    # 4) Mark no file upload used in this path
    data["_openai_file_id"] = ""
    return data
