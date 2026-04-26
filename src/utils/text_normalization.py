from __future__ import annotations

import re
import unicodedata
from typing import Any

# Keep these characters because they carry numeric/unit semantics.
_PRESERVED_NUMERIC_PUNCT = ".,%$€£¥"

_CHAR_REPLACEMENTS: dict[str, str | int | None] = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u2032": "'",
    "\u2035": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u201f": '"',
    "\u00ab": '"',
    "\u00bb": '"',
    "\u2033": '"',
    "\u2036": '"',
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u00a0": " ",
}


def normalize_text(value: Any) -> str:
    """Return a canonical text form for matching and retrieval."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    text = unicodedata.normalize("NFKC", text)
    if not text:
        return ""
    text = text.translate(str.maketrans(_CHAR_REPLACEMENTS))
    # Remove spacing artifacts while preserving numeric punctuation.
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([([{])\s+", r"\1", text)
    text = re.sub(r"\s+([)\]}])", r"\1", text)
    text = re.sub(r"([$€£¥])\s+", r"\1", text)
    # Normalize delimiter spacing around hyphens used in prose.
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def normalize_for_lookup(value: Any) -> str:
    """
    Lookup-oriented normalization that keeps only alnum, space,
    and numeric punctuation needed for quantity parsing/matching.
    """
    text = normalize_text(value)
    if not text:
        return ""
    cleaned = []
    for ch in text:
        if (
            ch.isalnum()
            or ch.isspace()
            or ch in _PRESERVED_NUMERIC_PUNCT
            or ch in {"-", "/", ":", ">", "<", "=", "~", "≈"}
        ):
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()
