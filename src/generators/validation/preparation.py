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
from .verified_facts import (
    canonical_verified_evidence_packs,
    validated_verified_facts,
    verified_facts_mode,
)


def prepare_validation_inputs(
    request: ValidationRequest,
    settings: AppSettings | IngestSettings,
    ctx: RunContext,
    *,
    md5: str | None,
) -> ValidationPreparedInputs:
    verified_mode = verified_facts_mode(
        request.artifacts, str(request.validation_mode or "")
    )
    grounding_use_vector_store = (
        False
        if verified_mode
        else resolve_grounding_vector_store_mode(request=request, settings=settings)
    )
    retrieval_mode = grounding_retrieval_mode(grounding_use_vector_store)
    verified_facts = (
        validated_verified_facts(
            request.artifacts,
            request.evidence_packs,
            expected_source_identity=str(request.source_id or ""),
        )
        if verified_mode
        else {}
    )
    authority_evidence_packs = (
        canonical_verified_evidence_packs(verified_facts) if verified_mode else {}
    )
    insights = ensure_list(
        request.artifacts.get("insights_final")
        if isinstance(request.artifacts, dict)
        else []
    )
    quotes = extract_quotes(request, insights)
    pdf_text = ""
    if not verified_mode:
        pdf_text = str(request.source_text or "").strip()
        if not pdf_text:
            pdf_text = load_pdf_text_from_cache(settings.cache_dir, md5, ctx)
    evidence_texts, evidence_map = collect_evidence_texts(
        request.artifacts,
        authority_evidence_packs if verified_mode else request.evidence_packs,
        pdf_text=pdf_text,
        verified_facts_only=verified_mode,
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
        verified_facts_mode=verified_mode,
        verified_facts=verified_facts,
        authority_evidence_packs=authority_evidence_packs,
    )
