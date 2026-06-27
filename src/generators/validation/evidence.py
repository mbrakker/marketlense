from __future__ import annotations

import heapq
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from src.contracts.files import PdfCacheTextReadRequest
from src.contracts.run_context import RunContext
from src.contracts.validation import ValidationRequest
from src.services import file_service
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.quantity import extract_quantities, should_ground_quantity
from src.utils.text_normalization import normalize_for_lookup, normalize_text

from .models import EvidenceWindow
from .quantities import quantity_supported
from .shared import (
    LOGGER_NAME,
    QUOTE_MIN_LEXICAL_OVERLAP,
    QUOTE_PARAPHRASE_HINTS,
    RETRIEVE_NEIGHBOR_RADIUS,
    RETRIEVE_TOP_K,
    WINDOW_STRIDE,
    WINDOW_TOKEN_MIN,
    WINDOW_TOKEN_TARGET,
    ensure_dict,
    logger,
    s,
    section_policy,
)


def collect_evidence_texts(
    artifacts: dict,
    evidence_packs: dict,
    *,
    pdf_text: str = "",
) -> Tuple[List[str], Dict[str, str]]:
    texts: List[str] = []
    text_keys: set[str] = set()
    evidence_by_id: Dict[str, str] = {}

    def add(text: str) -> None:
        cleaned = s(text).strip()
        if not cleaned:
            return
        key = normalize_text(cleaned)
        if not key or key in text_keys:
            return
        text_keys.add(key)
        texts.append(cleaned)

    def add_id_mapping(evidence_id: str, evidence_text: str) -> None:
        key = s(evidence_id).strip()
        value = s(evidence_text).strip()
        if key and value:
            evidence_by_id[key] = value

    if isinstance(artifacts, dict):
        summary = ensure_dict(artifacts.get("summary"))
        for claim in summary.get("claim_evidence_map") or []:
            if isinstance(claim, dict):
                add(s(claim.get("evidence")))
        for insight in artifacts.get("insights_final") or []:
            if isinstance(insight, dict):
                evidence_text = s(insight.get("evidence"))
                evidence_id = s(insight.get("evidence_id"))
                if evidence_text:
                    add(evidence_text)
                    if evidence_id:
                        evidence_by_id[evidence_id] = evidence_text
        for quote in artifacts.get("quotes_final") or []:
            if isinstance(quote, dict):
                add(s(quote.get("citation")))

    if isinstance(evidence_packs, dict):
        for pack in evidence_packs.values():
            if not isinstance(pack, dict):
                continue
            findings = pack.get("findings")
            if isinstance(findings, list):
                for entry in findings:
                    if not isinstance(entry, dict):
                        continue
                    evidence_text = s(entry.get("evidence"))
                    evidence_id = s(entry.get("id"))
                    add(evidence_text)
                    add_id_mapping(evidence_id, evidence_text)
                    add(s(entry.get("text")))
                    add(s(entry.get("description")))
                    add(s(entry.get("title")))

            scope_value = pack.get("scope")
            if isinstance(scope_value, str):
                add(scope_value)
            elif isinstance(scope_value, dict):
                add(s(scope_value.get("summary")))
                add(s(scope_value.get("description")))
                add(s(scope_value.get("scope")))

            methods = pack.get("methods")
            if isinstance(methods, list):
                for entry in methods:
                    if isinstance(entry, str):
                        add(entry)
                    elif isinstance(entry, dict):
                        add(s(entry.get("name")))
                        add(s(entry.get("description")))
                        add(s(entry.get("method")))

            limitations = pack.get("limitations")
            if isinstance(limitations, list):
                for entry in limitations:
                    if isinstance(entry, str):
                        add(entry)
                    elif isinstance(entry, dict):
                        add(s(entry.get("description")))
                        add(s(entry.get("text")))

            quote_candidates = pack.get("quote_candidates")
            if isinstance(quote_candidates, list):
                for quote in quote_candidates:
                    if not isinstance(quote, dict):
                        continue
                    quote_text = s(quote.get("text"))
                    quote_id = s(quote.get("id"))
                    add(quote_text)
                    add(s(quote.get("source")))
                    add_id_mapping(quote_id, quote_text)

            key_metrics = pack.get("key_metrics")
            if isinstance(key_metrics, list):
                for metric in key_metrics:
                    if not isinstance(metric, dict):
                        continue
                    metric_text = " ".join(
                        part
                        for part in (
                            s(metric.get("metric")),
                            s(metric.get("value")),
                            s(metric.get("unit")),
                        )
                        if part
                    )
                    add(metric_text)
                    add_id_mapping(s(metric.get("id")), metric_text)
                    add_id_mapping(s(metric.get("evidence_id")), metric_text)

            risk_register = pack.get("risk_register")
            if isinstance(risk_register, list):
                for risk in risk_register:
                    if not isinstance(risk, dict):
                        continue
                    risk_text = " ".join(
                        part
                        for part in (
                            s(risk.get("risk")),
                            s(risk.get("impact")),
                            s(risk.get("likelihood")),
                            s(risk.get("mitigation")),
                        )
                        if part
                    )
                    add(risk_text)
                    add_id_mapping(s(risk.get("id")), risk_text)
                    add_id_mapping(s(risk.get("evidence_id")), risk_text)

            recommendations = pack.get("recommendations")
            if isinstance(recommendations, list):
                for recommendation in recommendations:
                    if not isinstance(recommendation, dict):
                        continue
                    recommendation_text = " ".join(
                        part
                        for part in (
                            s(recommendation.get("recommendation")),
                            s(recommendation.get("rationale")),
                        )
                        if part
                    )
                    add(recommendation_text)
                    add_id_mapping(s(recommendation.get("id")), recommendation_text)
                    add_id_mapping(
                        s(recommendation.get("evidence_id")), recommendation_text
                    )

            contradictions = pack.get("contradictions")
            if isinstance(contradictions, list):
                for contradiction in contradictions:
                    if not isinstance(contradiction, dict):
                        continue
                    contradiction_text = " ".join(
                        part
                        for part in (
                            s(contradiction.get("statement_a")),
                            s(contradiction.get("statement_b")),
                            s(contradiction.get("explanation")),
                        )
                        if part
                    )
                    add(contradiction_text)
                    add_id_mapping(s(contradiction.get("id")), contradiction_text)
                    for evidence_id in contradiction.get("evidence_ids") or []:
                        add_id_mapping(s(evidence_id), contradiction_text)

    add(pdf_text)
    return texts, evidence_by_id


def build_evidence_windows(texts: Sequence[str]) -> List[EvidenceWindow]:
    windows: List[EvidenceWindow] = []
    idx = 0
    for text in texts:
        raw = s(text).strip()
        if not raw:
            continue
        tokens = tokenize(raw)
        if len(tokens) <= WINDOW_TOKEN_TARGET:
            char_counts = char_ngram_counts(raw, n=3)
            windows.append(
                EvidenceWindow(
                    idx=idx,
                    text=raw,
                    normalized=normalize_for_lookup(raw),
                    tokens=set(tokens),
                    quantities=extract_quantities(raw),
                    char_ngram_counts=char_counts,
                    char_ngram_norm=vector_norm(char_counts),
                )
            )
            idx += 1
            continue
        for chunk in window_tokens(tokens):
            chunk_text = " ".join(chunk).strip()
            if len(chunk_text) < 20:
                continue
            char_counts = char_ngram_counts(chunk_text, n=3)
            windows.append(
                EvidenceWindow(
                    idx=idx,
                    text=chunk_text,
                    normalized=normalize_for_lookup(chunk_text),
                    tokens=set(chunk),
                    quantities=extract_quantities(chunk_text),
                    char_ngram_counts=char_counts,
                    char_ngram_norm=vector_norm(char_counts),
                )
            )
            idx += 1
    return windows


def window_tokens(tokens: Sequence[str]) -> Iterable[List[str]]:
    if len(tokens) <= WINDOW_TOKEN_TARGET:
        yield list(tokens)
        return
    start = 0
    token_count = len(tokens)
    while start < token_count:
        end = min(token_count, start + WINDOW_TOKEN_TARGET)
        chunk = list(tokens[start:end])
        if len(chunk) < WINDOW_TOKEN_MIN and start != 0:
            break
        yield chunk
        if end >= token_count:
            break
        start += WINDOW_STRIDE


def retrieve_evidence_windows(
    claim_text: str,
    windows: Sequence[EvidenceWindow],
    *,
    top_k: int = RETRIEVE_TOP_K,
) -> List[EvidenceWindow]:
    if not claim_text or not windows or top_k <= 0:
        return []
    claim_norm = normalize_for_lookup(claim_text)
    claim_tokens = set(tokenize(claim_norm))
    claim_quantities = extract_quantities(claim_text)
    if not claim_tokens and not claim_quantities:
        return []
    claim_vector = char_ngram_counts(claim_norm, n=3)
    claim_vector_norm = vector_norm(claim_vector)
    best: List[Tuple[float, int, int]] = []
    for position, window in enumerate(windows):
        embedding_sim = pseudo_embedding_similarity_from_vectors(
            claim_vector,
            claim_vector_norm,
            window.char_ngram_counts,
            window.char_ngram_norm,
        )
        overlap = token_overlap_score(claim_tokens, window.tokens)
        bm25_score = bm25ish(claim_tokens, window.tokens)
        quantity_score = quantity_boost(claim_quantities, window.quantities)
        score = (
            (0.35 * embedding_sim)
            + (0.30 * overlap)
            + (0.20 * bm25_score)
            + (0.15 * quantity_score)
        )
        if score > 0:
            candidate = (score, -position, window.idx)
            if len(best) < top_k:
                heapq.heappush(best, candidate)
            elif candidate > best[0]:
                heapq.heapreplace(best, candidate)
    if not best:
        return []
    selected_idx = {idx for _, _, idx in best}
    max_idx = max(window.idx for window in windows)
    expanded_idx = set(selected_idx)
    for idx in list(selected_idx):
        for delta in range(1, RETRIEVE_NEIGHBOR_RADIUS + 1):
            if idx - delta >= 0:
                expanded_idx.add(idx - delta)
            if idx + delta <= max_idx:
                expanded_idx.add(idx + delta)
    by_idx = {window.idx: window for window in windows}
    return [by_idx[idx] for idx in sorted(expanded_idx) if idx in by_idx]


def token_overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    if overlap == 0:
        return 0.0
    return overlap / max(1, len(left | right))


def bm25ish(query_tokens: set[str], doc_tokens: set[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    hits = sum(1 for token in query_tokens if token in doc_tokens)
    return hits / max(1, len(query_tokens))


def pseudo_embedding_similarity(left: str, right: str) -> float:
    left_vec = char_ngram_counts(left, n=3)
    right_vec = char_ngram_counts(right, n=3)
    return pseudo_embedding_similarity_from_vectors(
        left_vec,
        vector_norm(left_vec),
        right_vec,
        vector_norm(right_vec),
    )


def pseudo_embedding_similarity_from_vectors(
    left_vec: Dict[str, float],
    left_norm: float,
    right_vec: Dict[str, float],
    right_norm: float,
) -> float:
    if not left_vec or not right_vec:
        return 0.0
    dot = 0.0
    for key, left_value in left_vec.items():
        dot += left_value * right_vec.get(key, 0.0)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def char_ngram_counts(text: str, *, n: int) -> Dict[str, float]:
    normalized = normalize_for_lookup(text)
    compact = normalized.replace(" ", "")
    if len(compact) < n:
        return {}
    counts: Dict[str, float] = {}
    for idx in range(len(compact) - n + 1):
        gram = compact[idx : idx + n]
        counts[gram] = counts.get(gram, 0.0) + 1.0
    return counts


def vector_norm(vector: Dict[str, float]) -> float:
    return sum(value * value for value in vector.values()) ** 0.5


def quantity_boost(claim: Sequence[Any], evidence: Sequence[Any]) -> float:
    if not claim or not evidence:
        return 0.0
    matched = 0
    for quantity in claim:
        if quantity_supported(quantity, evidence):
            matched += 1
    return matched / max(1, len(claim))


def load_pdf_text_from_cache(cache_dir: str, md5: str | None, ctx: RunContext) -> str:
    if not md5:
        return ""
    try:
        response = file_service.read_latest_pdf_cache_text(
            PdfCacheTextReadRequest(schema_version="1.0", cache_dir=cache_dir, md5=md5),
            ctx,
        )
    except AppError as exc:  # pragma: no cover - best effort
        if exc.retryable:
            raise
        logger.info(
            log_event(
                ctx,
                role="generator",
                event="validation_pdf_text_cache_read_failed",
                module=LOGGER_NAME,
                fields={"md5": md5, "error": str(exc)},
            )
        )
        return ""
    return s(response.text)


def extract_quotes(request: ValidationRequest, insights: Sequence[dict]) -> List[dict]:
    artifacts = request.artifacts if isinstance(request.artifacts, dict) else {}
    quotes = artifacts.get("quotes_final") or []
    if quotes:
        return quotes
    quote = request.report.quote
    return [
        {
            "text": quote.text,
            "speaker": quote.author,
            "evidence_id": s(insights[0].get("evidence_id")) if insights else "",
        }
    ]


def quote_label(quote: dict, idx: int) -> str:
    explicit = s(quote.get("id") or quote.get("evidence_id"))
    if explicit:
        return explicit
    return str(idx + 1)


def metric_value_supported(
    value: str,
    evidence_text: str,
    *,
    unit: str = "",
    section: str = "",
) -> bool:
    if not value:
        return True
    value_norm = normalize_text(value)
    evidence_normalized = normalize_text(evidence_text)
    if value_norm and value_norm in evidence_normalized:
        return True
    value_quantities = extract_quantities(f"{value} {unit}".strip())
    evidence_quantities = extract_quantities(evidence_text)
    if value_quantities and evidence_quantities:
        for candidate in value_quantities:
            if not should_ground_quantity(
                candidate,
                candidate.sentence,
                section_policy=section_policy(section),
                strict_section=True,
            ):
                continue
            if not quantity_supported(
                candidate, evidence_quantities, numeric_only=True
            ):
                return False
        return True
    return False


def contains_token(token: str, text: str) -> bool:
    token_norm = normalize_text(token)
    if not token_norm:
        return True
    return token_norm in normalize_text(text)


def split_sentences(text: str) -> List[str]:
    cleaned = sanitize_citation_tokens(s(text))
    if not cleaned.strip():
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    return [part.strip() for part in parts if part and part.strip()]


def tokenize(text: str) -> List[str]:
    normalized = normalize_for_lookup(text)
    if not normalized:
        return []
    return re.findall(r"[a-z0-9%$€£¥]+", normalized)


def lexical_overlap(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return overlap / max(1, len(left_tokens))


def quote_near_verbatim(quote: str, evidence: str) -> bool:
    quote_norm = normalize_for_lookup(quote)
    evidence_norm = normalize_for_lookup(evidence)
    if not quote_norm or not evidence_norm:
        return False
    if quote_norm in evidence_norm:
        return True
    return lexical_overlap(quote_norm, evidence_norm) >= QUOTE_MIN_LEXICAL_OVERLAP


def quote_is_paraphrase(quote: dict) -> bool:
    if not isinstance(quote, dict):
        return False
    flags = [s(quote.get("style")), s(quote.get("mode")), s(quote.get("label"))]
    if any(
        any(hint in normalize_text(flag) for hint in QUOTE_PARAPHRASE_HINTS)
        for flag in flags
    ):
        return True
    if quote.get("paraphrase") is True or quote.get("is_paraphrase") is True:
        return True
    text = normalize_text(s(quote.get("text")))
    return text.startswith("paraphrase:")


def sanitize_citation_tokens(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[\ue000-\uf8ff]", " ", text)
    cleaned = re.sub(r"filecite|turn\d+file\d+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
