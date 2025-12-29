from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict

import yaml

from src.contracts.prompts import PromptTemplate


def load_prompt(path: Path) -> PromptTemplate:
    data: Dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    text = data.get("text", "")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return PromptTemplate(
        schema_version="1.0",
        path=str(path),
        text=text,
        sha256=digest,
    )


def render_prompt(template: PromptTemplate, **kwargs: Any) -> str:
    try:
        return template.text.format(**kwargs)
    except KeyError as exc:
        raise ValueError(f"Missing prompt variable: {exc}") from exc
