"""Technical prefiltering for publisher-inventory candidate screening."""

from __future__ import annotations

from urllib.parse import urlsplit

from src.contracts.publisher_inventory import (
    PublisherInventoryCandidateScreeningDecision,
    PublisherInventoryCandidateScreeningItem,
)

_TARGET_MAX_SCREENING_BATCHES = 8
_MAX_DYNAMIC_SCREENING_BATCH_SIZE = 35


def _partition_candidates_for_llm_screening(
    candidates: list[PublisherInventoryCandidateScreeningItem],
) -> tuple[
    list[PublisherInventoryCandidateScreeningItem],
    list[PublisherInventoryCandidateScreeningDecision],
]:
    """Keep only URL syntax checks deterministic; qualification stays model-owned."""

    llm_candidates: list[PublisherInventoryCandidateScreeningItem] = []
    prefilter_decisions: list[PublisherInventoryCandidateScreeningDecision] = []
    for candidate in candidates:
        prefilter_decision = _prefilter_screening_decision(candidate)
        if prefilter_decision is None:
            llm_candidates.append(candidate)
        else:
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


def _prefilter_screening_decision(
    candidate: PublisherInventoryCandidateScreeningItem,
) -> PublisherInventoryCandidateScreeningDecision | None:
    """Reject malformed URLs without making a semantic report decision."""

    parsed_url = urlsplit(str(candidate.canonical_url or "").strip())
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return PublisherInventoryCandidateScreeningDecision(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            accepted=False,
            reason="invalid_candidate_url",
        )
    return None


__all__ = [
    "_TARGET_MAX_SCREENING_BATCHES",
    "_MAX_DYNAMIC_SCREENING_BATCH_SIZE",
    "_partition_candidates_for_llm_screening",
    "_resolve_candidate_screening_batch_size",
    "_prefilter_screening_decision",
]
