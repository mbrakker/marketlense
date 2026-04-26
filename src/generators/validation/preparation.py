from __future__ import annotations

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationRequest

from .evidence import (
    build_evidence_windows,
    collect_evidence_texts,
    extract_quotes,
    load_pdf_text_from_cache,
)
from .models import ValidationPreparedInputs
from .shared import (
    ensure_list,
    grounding_retrieval_mode,
    resolve_grounding_vector_store_mode,
)


def prepare_validation_inputs(
    request: ValidationRequest,
    settings: AppSettings | IngestSettings,
    ctx: RunContext,
    *,
    md5: str | None,
) -> ValidationPreparedInputs:
    grounding_use_vector_store = resolve_grounding_vector_store_mode(
        request=request, settings=settings
    )
    retrieval_mode = grounding_retrieval_mode(grounding_use_vector_store)
    insights = ensure_list(
        request.artifacts.get("insights_final")
        if isinstance(request.artifacts, dict)
        else []
    )
    quotes = extract_quotes(request, insights)
    pdf_text = load_pdf_text_from_cache(settings.cache_dir, md5, ctx)
    evidence_texts, evidence_map = collect_evidence_texts(
        request.artifacts,
        request.evidence_packs,
        pdf_text=pdf_text,
    )
    window_sources = list(evidence_texts)
    if pdf_text:
        window_sources.append(pdf_text)
    evidence_windows = build_evidence_windows(window_sources)
    return ValidationPreparedInputs(
        insights=insights,
        quotes=quotes,
        pdf_text=pdf_text,
        evidence_texts=evidence_texts,
        evidence_map=evidence_map,
        evidence_windows=evidence_windows,
        grounding_use_vector_store=grounding_use_vector_store,
        grounding_retrieval_mode=retrieval_mode,
    )
