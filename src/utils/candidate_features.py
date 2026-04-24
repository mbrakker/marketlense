from __future__ import annotations

from dataclasses import asdict
from typing import Any

from src.contracts.candidates import Candidate, CandidateFeatures
from src.utils.coercion import coerce_float, coerce_int


def features_from_meta(meta: dict[str, Any] | None) -> CandidateFeatures:
    source = meta if isinstance(meta, dict) else {}
    return CandidateFeatures(
        schema_version="1.0",
        area_frac=coerce_float(source.get("area_frac"), 0.0),
        aspect=coerce_float(source.get("aspect"), 0.0),
        text_lines=coerce_int(source.get("text_lines"), 0),
        text_chars=coerce_int(source.get("text_chars"), 0),
        text_ratio=coerce_float(source.get("text_ratio"), 0.0),
        rows=coerce_int(source.get("rows"), 0),
        cols=coerce_int(source.get("cols"), 0),
        numeric_ratio=coerce_float(source.get("numeric_ratio"), 0.0),
        avg_words_per_cell=coerce_float(source.get("avg_words_per_cell"), 0.0),
        ocr_density=coerce_float(source.get("ocr_density"), 0.0),
        visual_entropy=coerce_float(source.get("visual_entropy"), 0.0),
        chart_confidence=coerce_float(source.get("chart_confidence"), 0.0),
        table_confidence=coerce_float(source.get("table_confidence"), 0.0),
        method=str(source.get("method") or "").strip(),
    )


def candidate_features(candidate: Candidate) -> CandidateFeatures:
    if isinstance(candidate.features, CandidateFeatures):
        return candidate.features
    return features_from_meta(
        candidate.meta if isinstance(candidate.meta, dict) else {}
    )


def candidate_features_payload(candidate: Candidate) -> dict[str, Any]:
    return asdict(candidate_features(candidate))
