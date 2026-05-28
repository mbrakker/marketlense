"""Deterministic publisher-inventory candidate screening policy.

This module owns no-model prefilter and fallback report-likelihood heuristics,
including URL, title, source-context, and batch-size decisions.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateScreeningDecision,
    PublisherInventoryCandidateScreeningItem,
)
from src.generators._publisher_inventory_candidate_screening.shared import (
    _DIRECT_DETAIL_SOURCE_URL_MARKERS,
    _EDITORIAL_NON_REPORT_URL_MARKERS,
    _EDITORIAL_REPORT_URL_MARKERS,
    _EDITORIAL_SPECIFIC_REPORT_TITLE_MARKERS,
    _FALLBACK_LISTING_QUERY_KEYS,
    _FALLBACK_NON_REPORT_TITLE_MARKERS,
    _FALLBACK_NON_REPORT_URL_MARKERS,
    _FALLBACK_REPORT_COLLECTION_SEGMENTS,
    _FALLBACK_REPORT_TITLE_MARKERS,
    _FALLBACK_REPORT_URL_MARKERS,
    _FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS,
    _GENERIC_CTA_TITLES,
    _INFORMATIONAL_TITLE_PREFIXES,
    _COLLECTION_ROOT_URL_TOKENS,
    _REPORT_CONTEXT_STOP_WORDS,
    _contains_any_title_marker,
    _normalize_title_fingerprint,
)

_TARGET_MAX_SCREENING_BATCHES = 8


_MAX_DYNAMIC_SCREENING_BATCH_SIZE = 35


def _partition_candidates_for_llm_screening(
    candidates: list[PublisherInventoryCandidateScreeningItem],
) -> tuple[
    list[PublisherInventoryCandidateScreeningItem],
    list[PublisherInventoryCandidateScreeningDecision],
]:
    llm_candidates: list[PublisherInventoryCandidateScreeningItem] = []
    prefilter_decisions: list[PublisherInventoryCandidateScreeningDecision] = []
    for candidate in candidates:
        prefilter_decision = _prefilter_screening_decision(candidate)
        if prefilter_decision is None:
            llm_candidates.append(candidate)
            continue
        prefilter_decisions.append(prefilter_decision)
    return llm_candidates, prefilter_decisions


def _resolve_candidate_screening_batch_size(
    *,
    candidate_count: int,
    configured_batch_size: int,
) -> int:
    batch_size = max(configured_batch_size, 1)
    if candidate_count <= batch_size * _TARGET_MAX_SCREENING_BATCHES:
        return batch_size
    dynamic_batch_size = (
        candidate_count + _TARGET_MAX_SCREENING_BATCHES - 1
    ) // _TARGET_MAX_SCREENING_BATCHES
    return max(batch_size, min(dynamic_batch_size, _MAX_DYNAMIC_SCREENING_BATCH_SIZE))


def _fallback_screening_decision(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> PublisherInventoryCandidateScreeningDecision:
    normalized_title = _normalize_title_fingerprint(candidate.title)
    normalized_url = candidate.canonical_url.casefold()
    if _looks_like_collection_root_candidate_url(candidate.canonical_url):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="fallback_non_report_url",
        )
    if _contains_any_title_marker(normalized_title, _FALLBACK_NON_REPORT_TITLE_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="fallback_non_report_title",
        )
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="fallback_non_report_url",
        )
    if _has_strong_report_detail_url(candidate.canonical_url):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="fallback_report_detail_url",
        )
    if _contains_any_title_marker(
        normalized_title, _FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS
    ):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="fallback_specific_report_title",
        )
    if _contains_any_title_marker(normalized_title, _FALLBACK_REPORT_TITLE_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="fallback_report_signal",
        )
    return PublisherInventoryCandidateScreeningDecision(
        schema_version="1.0",
        canonical_url=candidate.canonical_url,
        accepted=False,
        reason="fallback_unknown_candidate",
    )


def _is_probable_report_asset(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> bool:
    normalized_title = _normalize_title_fingerprint(candidate.title)
    normalized_url = candidate.canonical_url.casefold()
    if urlsplit(normalized_url).path.endswith(".pdf"):
        return _has_pdf_report_signal(candidate)
    if _has_editorial_report_detail_candidate(candidate):
        return True
    if _has_strong_report_detail_url(candidate.canonical_url):
        return True
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return False
    if _contains_any_title_marker(normalized_title, _FALLBACK_NON_REPORT_TITLE_MARKERS):
        return False
    return _contains_any_title_marker(normalized_title, _FALLBACK_REPORT_TITLE_MARKERS)


def _prefilter_screening_decision(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> PublisherInventoryCandidateScreeningDecision | None:
    normalized_title = _normalize_title_fingerprint(candidate.title)
    normalized_url = candidate.canonical_url.casefold()
    parsed_url = urlsplit(normalized_url)
    if normalized_url.endswith(".pdf") and not _has_pdf_report_signal(candidate):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="low_report_probability_prefilter",
        )
    if any(token in parsed_url.query for token in _FALLBACK_LISTING_QUERY_KEYS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="low_report_probability_prefilter",
        )
    if _looks_like_confident_direct_detail_source(candidate):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="direct_detail_source_prefilter",
        )
    if _looks_like_collection_root_candidate_url(candidate.canonical_url):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="low_report_probability_prefilter",
        )
    if _has_editorial_report_detail_candidate(candidate):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="editorial_report_detail_url_prefilter",
        )
    if (
        _is_generic_cta_title(normalized_title)
        and _looks_like_insights_detail_url(candidate.canonical_url)
        and not _has_specific_editorial_report_slug(candidate.canonical_url)
    ):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="low_report_probability_prefilter",
        )
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="low_report_probability_prefilter",
        )
    if _contains_any_title_marker(normalized_title, _FALLBACK_NON_REPORT_TITLE_MARKERS):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="low_report_probability_prefilter",
        )
    if _has_strong_report_detail_url(candidate.canonical_url):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="strong_report_detail_url_prefilter",
        )
    if _contains_any_title_marker(
        normalized_title, _FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS
    ):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="specific_report_title_prefilter",
        )
    if _has_report_archive_context(
        candidate.source_page_url
    ) and _looks_like_human_archive_title(normalized_title):
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=True,
            reason="report_archive_context_prefilter",
        )
    if _is_probable_report_asset(candidate):
        return None
    return PublisherInventoryCandidateScreeningDecision(
        schema_version="1.0",
        canonical_url=candidate.canonical_url,
        accepted=False,
        reason="low_report_probability_prefilter",
    )


def _has_strong_report_detail_url(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    if _looks_like_collection_root_candidate_url(normalized_url):
        return False
    parsed = urlsplit(normalized_url)
    if parsed.path.endswith(".pdf"):
        return True
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return False
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if not path_segments:
        return False
    if any(token in parsed.query for token in _FALLBACK_LISTING_QUERY_KEYS):
        return False
    if "/page/" in parsed.path or "/type/" in parsed.path:
        return False
    leaf_segment = path_segments[-1]
    if leaf_segment.isdigit() or leaf_segment in _FALLBACK_REPORT_COLLECTION_SEGMENTS:
        return False
    leaf_title = leaf_segment.rsplit(".", 1)[0].replace("_", "-").replace("-", " ")
    if any(marker in normalized_url for marker in _FALLBACK_REPORT_URL_MARKERS):
        return True
    leaf_tokens = [token for token in re.findall(r"[a-z0-9]+", leaf_title) if token]
    return len(leaf_tokens) >= 3 and _contains_any_title_marker(
        leaf_title,
        _FALLBACK_REPORT_TITLE_MARKERS,
    )


def _has_report_archive_context(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    if any(marker in normalized_url for marker in _FALLBACK_NON_REPORT_URL_MARKERS):
        return False
    return (
        any(
            marker in path
            for marker in (
                "/publication",
                "/publications/",
                "/report",
                "/reports/",
                "/research",
                "/resources/",
                "/whitepaper",
                "/whitepapers/",
                "/ebooks/",
                "/guides-whitepapers",
                "/livres-blancs",
            )
        )
        or "/type/report" in normalized_url
    )


def _looks_like_human_archive_title(title: str) -> bool:
    normalized_title = _normalize_title_fingerprint(title)
    if not normalized_title or _is_generic_cta_title(normalized_title):
        return False
    if _contains_any_title_marker(normalized_title, _FALLBACK_NON_REPORT_TITLE_MARKERS):
        return False
    if normalized_title.startswith(
        (
            "how ",
            "what ",
            "why ",
        )
    ):
        return False
    tokens = [token for token in re.findall(r"[a-z0-9]+", normalized_title) if token]
    alpha_tokens = [token for token in tokens if any(char.isalpha() for char in token)]
    return len(alpha_tokens) >= 3 and len(normalized_title) >= 16


def _has_pdf_report_signal(candidate: PublisherInventoryCandidateScreeningItem) -> bool:
    normalized_url = str(candidate.canonical_url or "").strip().casefold()
    parsed_url = urlsplit(normalized_url)
    if not parsed_url.path.endswith(".pdf"):
        return False
    leaf_title = (
        parsed_url.path.rsplit("/", 1)[-1]
        .rsplit(".", 1)[0]
        .replace("_", "-")
        .replace("-", " ")
    )
    source_url_signal = str(candidate.source_page_url or "").strip().casefold()
    combined_signal_text = " ".join(
        part
        for part in (
            leaf_title,
            _normalize_title_fingerprint(candidate.title),
            source_url_signal,
        )
        if part
    )
    if _contains_any_title_marker(
        combined_signal_text, _FALLBACK_NON_REPORT_TITLE_MARKERS
    ):
        return False
    return _contains_any_title_marker(
        combined_signal_text,
        _FALLBACK_REPORT_TITLE_MARKERS,
    )


def _has_editorial_report_detail_candidate(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> bool:
    normalized_url = str(candidate.canonical_url or "").strip().casefold()
    if not normalized_url:
        return False
    if not any(marker in normalized_url for marker in _EDITORIAL_REPORT_URL_MARKERS):
        return False
    if any(marker in normalized_url for marker in _EDITORIAL_NON_REPORT_URL_MARKERS):
        return False
    parsed = urlsplit(normalized_url)
    if any(token in parsed.query for token in _FALLBACK_LISTING_QUERY_KEYS):
        return False
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf.isdigit() or leaf in _FALLBACK_REPORT_COLLECTION_SEGMENTS:
        return False
    normalized_title = _normalize_title_fingerprint(candidate.title)
    if normalized_title.startswith(_INFORMATIONAL_TITLE_PREFIXES):
        return False
    if _contains_any_title_marker(normalized_title, _FALLBACK_NON_REPORT_TITLE_MARKERS):
        return False
    leaf_title = leaf.replace("_", "-").replace("-", " ")
    combined_signal_text = " ".join(
        part
        for part in (
            leaf_title,
            normalized_title,
        )
        if part
    )
    leaf_tokens = [
        token for token in re.findall(r"[a-z0-9]+", combined_signal_text) if token
    ]
    return len(leaf_tokens) >= 3 and (
        _contains_any_title_marker(
            combined_signal_text,
            _FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS,
        )
        or _has_contextual_report_term(combined_signal_text)
    )


def _looks_like_collection_root_candidate_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf in _FALLBACK_REPORT_COLLECTION_SEGMENTS:
        return True
    leaf_tokens = [token for token in re.findall(r"[a-z0-9]+", leaf) if token]
    if not leaf_tokens:
        return False
    if any(token.isdigit() for token in leaf_tokens):
        return False
    return all(token in _COLLECTION_ROOT_URL_TOKENS for token in leaf_tokens)


def _has_contextual_report_term(value: str) -> bool:
    normalized_value = _normalize_title_fingerprint(value)
    if not normalized_value:
        return False
    tokens = [token for token in re.findall(r"[a-z0-9]+", normalized_value) if token]
    if "report" not in tokens and "reports" not in tokens:
        return False
    contextual_tokens = [
        token
        for token in tokens
        if token not in _REPORT_CONTEXT_STOP_WORDS
        and token not in {"report", "reports"}
    ]
    return len(contextual_tokens) >= 2


def _looks_like_confident_direct_detail_source(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> bool:
    normalized_url = str(candidate.canonical_url or "").strip().casefold()
    source_page_url = str(candidate.source_page_url or "").strip().casefold()
    if not normalized_url or not source_page_url:
        return False
    if normalized_url != source_page_url:
        return False
    if not any(
        marker in normalized_url for marker in _DIRECT_DETAIL_SOURCE_URL_MARKERS
    ):
        return False
    return not _looks_like_collection_root_candidate_url(normalized_url)


def _is_generic_cta_title(title: str) -> bool:
    normalized_title = _normalize_title_fingerprint(title)
    return normalized_title in _GENERIC_CTA_TITLES


def _looks_like_insights_detail_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path.startswith("/insights/"):
        return False
    segments = [segment for segment in path.split("/") if segment]
    return (
        len(segments) >= 2 and segments[-1] not in _FALLBACK_REPORT_COLLECTION_SEGMENTS
    )


def _has_specific_editorial_report_slug(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf_title = segments[-1].rsplit(".", 1)[0].replace("_", "-").replace("-", " ")
    leaf_tokens = [token for token in re.findall(r"[a-z0-9]+", leaf_title) if token]
    if len(leaf_tokens) < 3:
        return False
    return _contains_any_title_marker(
        leaf_title,
        _EDITORIAL_SPECIFIC_REPORT_TITLE_MARKERS,
    )


__all__ = [
    "_TARGET_MAX_SCREENING_BATCHES",
    "_MAX_DYNAMIC_SCREENING_BATCH_SIZE",
    "_partition_candidates_for_llm_screening",
    "_resolve_candidate_screening_batch_size",
    "_fallback_screening_decision",
    "_is_probable_report_asset",
    "_prefilter_screening_decision",
    "_has_strong_report_detail_url",
    "_has_report_archive_context",
    "_looks_like_human_archive_title",
    "_has_pdf_report_signal",
    "_has_editorial_report_detail_candidate",
    "_looks_like_collection_root_candidate_url",
    "_has_contextual_report_term",
    "_looks_like_confident_direct_detail_source",
    "_is_generic_cta_title",
    "_looks_like_insights_detail_url",
    "_has_specific_editorial_report_slug",
]
