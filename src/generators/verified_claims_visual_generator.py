"""Shadow-mode visual correction and independent verification for claims."""

from __future__ import annotations

import copy
import json
import logging
import re
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from src.contracts.files import FileBundleHashRequest
from src.contracts.llm import LLMContextCompactionPolicy
from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_assets import CropRefinePageRenderRequest
from src.contracts.run_context import RunContext
from src.contracts.verified_claims import (
    VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
    VERIFIED_FACT_SCHEMA_VERSION,
    VisualClaimCorrectionAttempt,
    VisualClaimEvaluationRequest,
    VisualClaimEvaluationResponse,
    VisualClaimEvaluationResult,
    VisualClaimVerificationAttempt,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.verified_claims_recovery import candidate_roster_digest
from src.services import llm_service
from src.services.file_service import hash_file_bundle as service_hash_file_bundle
from src.services.pdf_service import render_page_for_crop_refine
from src.services.prompt_service import load_prompt_set, render_prompt
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

LOGGER = logging.getLogger("market_lense.verified_claims_visual_generator")

CORRECTION_NAMESPACE = "report_vs/validate/visual_claim_correction"
VERIFICATION_NAMESPACE = "report_vs/validate/visual_claim_verification"
_CORRECTION_STATUSES = frozenset({"corrected", "unresolved", "failed"})
_VERIFICATION_OUTCOMES = frozenset({"verified", "rejected", "unresolved"})
_MAX_RECOVERY_PAGES_PER_CLAIM = 3
_PDF_SHA256_PATTERN = re.compile(
    r"(?:^|[|,; ])pdf-sha256[:=]([0-9a-f]{64})(?:$|[|,; ])", re.I
)
_PROTECTED_METRIC_FIELDS = (
    "label",
    "value",
    "unit",
    "trend",
    "timeframe",
    "geography",
    "segment",
    "sample_size",
    "confidence",
    "subject",
    "cohort",
    "denominator",
    "observation_status",
    "forecast_status",
    "observations",
)


@dataclass(frozen=True)
class VerifiedClaimsVisualDependencies:
    """Injected existing boundaries used by the shadow evaluator."""

    load_prompt_set: Callable[[PromptLoadRequest, RunContext], Any]
    render_prompt: Callable[[PromptRenderRequest, RunContext], Any]
    render_page_for_crop_refine: Callable[
        [CropRefinePageRenderRequest, RunContext], Any
    ]
    openai_chat_json_with_images: Callable[
        [OpenAIJSONImagePromptRequest, RunContext], Any
    ]
    hash_file_bundle: Callable[[FileBundleHashRequest, RunContext], Any] = (
        service_hash_file_bundle
    )

    @classmethod
    def default(cls) -> "VerifiedClaimsVisualDependencies":
        return cls(
            load_prompt_set=load_prompt_set,
            render_prompt=render_prompt,
            render_page_for_crop_refine=render_page_for_crop_refine,
            openai_chat_json_with_images=llm_service.openai_chat_json_with_images,
            hash_file_bundle=service_hash_file_bundle,
        )


@dataclass(frozen=True)
class _PreparedVisualClaim:
    """Immutable claim inputs prepared before any visual provider work starts."""

    index: int
    claim: Mapping[str, Any]
    image_paths: tuple[str, ...]
    inspected_physical_pages: tuple[int, ...]
    recovery_candidates: tuple[dict[str, Any], ...]
    ctx: RunContext


def _text(value: Any) -> str:
    return str(value or "").strip()


def _complete_metric_binding(claim: Mapping[str, Any]) -> dict[str, Any]:
    raw_metric = claim.get("metric")
    if not isinstance(raw_metric, Mapping):
        return {}
    binding = {str(key): copy.deepcopy(value) for key, value in raw_metric.items()}
    for field_name in _PROTECTED_METRIC_FIELDS:
        binding.setdefault(field_name, "")
    return binding


def _claims_have_identical_proposition(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", _text(value)).casefold()

    return bool(normalize(left)) and normalize(left) == normalize(right)


def _candidate_id(claim: Mapping[str, Any]) -> str:
    for key in ("stable_candidate_id", "candidate_id", "id"):
        value = _text(claim.get(key))
        if value:
            return value
    return ""


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _unique_positive_pages(values: list[int | None]) -> list[int]:
    pages: list[int] = []
    for page in values:
        if page is not None and page not in pages:
            pages.append(page)
    return pages


def _source_binding_status(
    original_physical_pages: list[int], supporting_physical_pages: list[int]
) -> str:
    """Classify only pages that independently support the final claim."""

    if any(page not in original_physical_pages for page in supporting_physical_pages):
        return "provisional_recovered"
    return "retained"


def _numeric_score(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _physical_pages(claim: Mapping[str, Any]) -> list[int]:
    explicit_pages: list[int] = []
    for key in ("physical_page", "physical_pdf_page"):
        page = _positive_int(claim.get(key))
        if page is not None:
            explicit_pages.append(page)
    pages = claim.get("pages")
    raw_page_values = (
        [_positive_int(value) for value in pages] if isinstance(pages, list) else []
    )
    page_values = _unique_positive_pages(raw_page_values)
    if page_values:
        return page_values
    if explicit_pages:
        return list(dict.fromkeys(explicit_pages))
    spans = claim.get("evidence_spans")
    raw_span_pages = (
        [_positive_int(span.get("page")) for span in spans if isinstance(span, dict)]
        if isinstance(spans, list)
        else []
    )
    return _unique_positive_pages(raw_span_pages)


def _physical_page(claim: Mapping[str, Any]) -> int | None:
    pages = _physical_pages(claim)
    return pages[0] if pages else None


def _image_page_map(inspected_physical_pages: list[int]) -> list[dict[str, int]]:
    return [
        {"image_index": index, "physical_page": page}
        for index, page in enumerate(inspected_physical_pages, start=1)
    ]


def _image_page_map_text(inspected_physical_pages: list[int]) -> str:
    return "\n".join(
        f"image {index} = physical PDF page {page} "
        "(authoritative; cite this page, not any printed page label)"
        for index, page in enumerate(inspected_physical_pages, start=1)
    )


def _prompt_evidence_spans(claim: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project retained span provenance without supplying unverified source text."""

    provenance_keys = {
        "char_end",
        "char_start",
        "end",
        "evidence_id",
        "line_end",
        "line_start",
        "page",
        "section_id",
        "source_id",
        "source_identity",
        "source_pack",
        "span_id",
        "start",
    }
    spans = claim.get("evidence_spans")
    if not isinstance(spans, list):
        return []
    return [
        {
            key: copy.deepcopy(value)
            for key, value in span.items()
            if key in provenance_keys
        }
        for span in spans
        if isinstance(span, Mapping)
    ]


def _source_pdf_sha256(source_identity: str) -> str:
    matches = {
        match.group(1).lower()
        for match in _PDF_SHA256_PATTERN.finditer(_text(source_identity))
    }
    if len(matches) > 1:
        raise AppError(
            code="verified_claims_source_identity_ambiguous",
            message="Source identity contains conflicting PDF hashes",
            retryable=False,
        )
    return next(iter(matches), "")


def _verify_source_pdf_identity(
    *,
    request: VisualClaimEvaluationRequest,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
) -> None:
    expected_sha256 = _source_pdf_sha256(request.source_identity)
    if not expected_sha256:
        raise AppError(
            code="verified_claims_source_pdf_hash_missing",
            message="Visual evaluation requires an expected source PDF hash",
            retryable=False,
        )
    response = dependencies.hash_file_bundle(
        FileBundleHashRequest(schema_version="1.0", paths=[request.pdf_path]),
        ctx,
    )
    file_hashes = getattr(response, "file_sha256", None)
    if isinstance(response, dict):
        file_hashes = response.get("file_sha256")
    actual_sha256 = (
        _text(file_hashes.get(request.pdf_path))
        if isinstance(file_hashes, dict)
        else ""
    ).lower()
    if actual_sha256 != expected_sha256:
        raise AppError(
            code="verified_claims_source_pdf_hash_mismatch",
            message="Source PDF hash does not match the expected source identity",
            retryable=False,
            context={
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
            },
        )


def _binding_conflict_reason(claim: Mapping[str, Any], source_identity: str) -> str:
    claim_source_identity = _text(claim.get("source_identity"))
    if claim_source_identity and claim_source_identity != _text(source_identity):
        return "claim_source_identity_conflict"
    raw_pages = claim.get("pages")
    if raw_pages is not None and not isinstance(raw_pages, list):
        return "pages_not_a_list"
    if isinstance(raw_pages, list):
        parsed_pages = [_positive_int(value) for value in raw_pages]
        if any(value is None for value in parsed_pages):
            return "pages_invalid"
        declared_pages = set(parsed_pages)
    else:
        declared_pages = set()

    explicit_pages = [
        _positive_int(claim.get(key))
        for key in ("physical_page", "physical_pdf_page")
        if claim.get(key) is not None
    ]
    if any(page is None for page in explicit_pages):
        return "physical_page_invalid"
    if len(set(explicit_pages)) > 1:
        return "physical_page_conflict"
    if declared_pages and any(page not in declared_pages for page in explicit_pages):
        return "physical_page_not_in_pages"

    spans = claim.get("evidence_spans")
    if spans is not None and not isinstance(spans, list):
        return "evidence_spans_not_a_list"
    span_pages: set[int] = set()
    span_evidence_ids: set[str] = set()
    span_source_ids: set[str] = set()
    for span in spans or []:
        if not isinstance(span, dict):
            return "evidence_span_invalid"
        page = span.get("page")
        if page is not None:
            parsed_page = _positive_int(page)
            if parsed_page is None:
                return "evidence_span_page_invalid"
            span_pages.add(parsed_page)
        evidence_id = _text(span.get("evidence_id"))
        if evidence_id:
            span_evidence_ids.add(evidence_id)
        for key in ("source_identity", "source_id"):
            value = _text(span.get(key))
            if value:
                span_source_ids.add(value)

    if declared_pages and not span_pages.issubset(declared_pages):
        return "evidence_span_page_conflict"
    if (
        not declared_pages
        and explicit_pages
        and span_pages
        and (explicit_pages[0] not in span_pages)
    ):
        return "evidence_span_page_conflict"
    if span_source_ids and span_source_ids != {_text(source_identity)}:
        return "evidence_span_source_conflict"
    top_evidence_id = _text(claim.get("evidence_id"))
    if (
        top_evidence_id
        and span_evidence_ids
        and top_evidence_id not in span_evidence_ids
    ):
        return "evidence_id_conflict"
    return ""


def _evidence_ids(claim: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    raw_plural = claim.get("evidence_ids")
    plural_values = raw_plural if isinstance(raw_plural, list) else []
    for value in [*plural_values, _text(claim.get("evidence_id"))]:
        value = _text(value)
        if value and value not in values:
            values.append(value)
    spans = claim.get("evidence_spans")
    if isinstance(spans, list):
        for span in spans:
            if not isinstance(span, dict):
                continue
            value = _text(span.get("evidence_id"))
            if value and value not in values:
                values.append(value)
    return values


def _evidence_spans(claim: Mapping[str, Any]) -> list[dict[str, Any]]:
    spans = claim.get("evidence_spans")
    return (
        [copy.deepcopy(span) for span in spans if isinstance(span, dict)]
        if isinstance(spans, list)
        else []
    )


def _recovery_candidates(
    request: VisualClaimEvaluationRequest, claim: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Return bounded, source-consistent provisional pages for one claim.

    Recovery candidates are supplied by the deterministic replay/orchestration
    boundary.  The visual generator only checks the source identity and page
    shape; it never promotes a candidate's evidence ID, text, or metric into the
    retained binding.
    """

    if getattr(request, "recovery_enabled", False) is not True:
        return []
    if _text(claim.get("_visual_replacement_policy")) != (
        "report_level_replacement_allowed"
    ):
        return []
    candidate_id = _candidate_id(claim)
    raw_by_id = getattr(request, "recovery_candidates", {})
    raw_candidates = (
        raw_by_id.get(candidate_id, []) if isinstance(raw_by_id, Mapping) else []
    )
    if not isinstance(raw_candidates, list):
        return []
    original_pages = set(_physical_pages(claim))
    accepted: list[dict[str, Any]] = []
    seen_pages: set[int] = set()
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            continue
        page = _positive_int(raw.get("physical_page") or raw.get("page"))
        if page is None or page in original_pages or page in seen_pages:
            continue
        candidate_identity = _text(raw.get("source_identity"))
        if candidate_identity and candidate_identity != _text(request.source_identity):
            continue
        seen_pages.add(page)
        accepted.append(dict(raw))
    accepted.sort(
        key=lambda item: (
            -_numeric_score(item.get("score")),
            _positive_int(item.get("physical_page") or item.get("page")) or 0,
        )
    )
    return accepted[:_MAX_RECOVERY_PAGES_PER_CLAIM]


def _recovery_prompt_sources(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose recovery provenance as context without changing authoritative fields."""

    output: list[dict[str, Any]] = []
    for candidate in candidates:
        page = _positive_int(candidate.get("physical_page") or candidate.get("page"))
        if page is None:
            continue
        excerpt = _text(candidate.get("page_text") or candidate.get("text"))
        output.append(
            {
                "physical_page": page,
                "reason": _text(candidate.get("reason")),
                "source_pack": _text(candidate.get("source_pack")),
                "evidence_id": _text(candidate.get("evidence_id")),
                "source_excerpt": excerpt[:4000],
            }
        )
    return output


def _claim_binding(
    *,
    claim: Mapping[str, Any],
    source_identity: str,
    physical_page: int,
    inspected_physical_pages: list[int] | None = None,
    recovery_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    original_pages = _physical_pages(claim)
    inspected_pages = list(inspected_physical_pages or original_pages)
    recovered_pages = [page for page in inspected_pages if page not in original_pages]
    return {
        "candidate_id": _candidate_id(claim),
        "original_claim": _text(claim.get("text") or claim.get("claim")),
        "source_identity": source_identity,
        "physical_page": physical_page,
        "physical_pages": original_pages,
        "original_physical_pages": original_pages,
        "inspected_physical_pages": inspected_pages,
        "recovered_physical_pages": recovered_pages,
        "evidence_ids": _evidence_ids(claim),
        "evidence_spans": _prompt_evidence_spans(claim),
        "evidence_span_text_is_unverified": True,
        "replacement_policy": (
            _text(claim.get("_visual_replacement_policy"))
            or "strict_original_direction"
        ),
        "recovery_sources": _recovery_prompt_sources(recovery_candidates or []),
        "image_page_map": _image_page_map(inspected_pages),
    }


def _rendered_image_path(response: Any, output_dir: str) -> str:
    raw_path = (
        response.get("image_path")
        if isinstance(response, dict)
        else getattr(response, "image_path", "")
    )
    normalized_path = _text(raw_path)
    if not normalized_path:
        return ""
    path = Path(normalized_path)
    return str(path if path.is_absolute() else Path(output_dir) / path)


def _response_json(response: Any) -> dict[str, Any] | None:
    payload = (
        response.get("parsed_json")
        if isinstance(response, dict)
        else getattr(response, "parsed_json", None)
    )
    return payload if isinstance(payload, dict) else None


def _response_metadata(
    response: Any, request: OpenAIJSONImagePromptRequest
) -> tuple[str, str]:
    request_id = (
        _text(response.get("request_id"))
        if isinstance(response, dict)
        else _text(getattr(response, "request_id", ""))
    )
    model = (
        _text(response.get("model"))
        if isinstance(response, dict)
        else _text(getattr(response, "model", ""))
    )
    return request_id, model or request.model


def _strict_string_list(payload: Mapping[str, Any], key: str) -> list[str] | None:
    value = payload.get(key)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        return None
    return [item.strip() for item in value]


def _strict_physical_page_list(
    payload: Mapping[str, Any], key: str
) -> list[int] | None:
    value = payload.get(key)
    if not isinstance(value, list):
        return None
    pages: list[int] = []
    for item in value:
        if type(item) is not int or item <= 0 or item in pages:
            return None
        pages.append(item)
    return pages


def _supporting_page_notes(
    payload: Mapping[str, Any], inspected_physical_pages: list[int]
) -> tuple[list[int], dict[str, str], list[str]]:
    supporting_pages = _strict_physical_page_list(payload, "supporting_physical_pages")
    raw_notes = payload.get("source_truth_notes_by_page")
    diagnostics: list[str] = []
    if (
        supporting_pages is None
        or not supporting_pages
        or any(page not in inspected_physical_pages for page in supporting_pages)
    ):
        diagnostics.append("verification_supporting_pages_invalid")
        supporting_pages = []

    notes: dict[str, str] = {}
    if not isinstance(raw_notes, dict):
        diagnostics.append("verification_source_truth_notes_by_page_invalid")
    else:
        for raw_page, raw_note in raw_notes.items():
            page = _positive_int(raw_page)
            if page is None or not isinstance(raw_note, str) or not raw_note.strip():
                diagnostics.append("verification_source_truth_notes_by_page_invalid")
                continue
            notes[str(page)] = raw_note.strip()
        expected_keys = {str(page) for page in supporting_pages}
        if set(notes) != expected_keys:
            diagnostics.append("verification_source_truth_notes_by_page_incomplete")
        if any(page not in inspected_physical_pages for page in map(int, notes)):
            diagnostics.append("verification_source_truth_notes_by_page_invalid")
    return supporting_pages, notes, list(dict.fromkeys(diagnostics))


def _normalise_verified_fact_payload(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Validate the factual fields returned by the existing verifier call."""

    raw_fact = payload.get("verified_fact")
    if raw_fact is None:
        return {}, []
    if not isinstance(raw_fact, Mapping):
        return {}, ["verification_verified_fact_invalid"]
    statement = _text(raw_fact.get("statement"))
    raw_metric = raw_fact.get("metric")
    if not statement or not isinstance(raw_metric, Mapping):
        return {}, ["verification_verified_fact_invalid"]
    metric = {
        field_name: copy.deepcopy(raw_metric.get(field_name, ""))
        for field_name in _PROTECTED_METRIC_FIELDS
        if field_name not in {"forecast_status", "observations"}
    }
    if "forecast_status" in raw_metric:
        metric["forecast_status"] = copy.deepcopy(raw_metric["forecast_status"])
    if "observations" in raw_metric:
        if not isinstance(raw_metric["observations"], list) or any(
            not isinstance(observation, Mapping)
            for observation in raw_metric["observations"]
        ):
            return {}, ["verification_verified_fact_observations_invalid"]
        metric["observations"] = copy.deepcopy(raw_metric["observations"])
    for alias, field_name in (("direction", "trend"), ("population", "segment")):
        if not metric[field_name] and alias in raw_metric:
            metric[field_name] = copy.deepcopy(raw_metric.get(alias))
    if metric["value"] and (not _text(metric["label"]) or not _text(metric["unit"])):
        return {}, ["verification_verified_fact_metric_incomplete"]
    raw_qualifiers = raw_fact.get("qualifiers", [])
    if not isinstance(raw_qualifiers, list) or any(
        not isinstance(value, str) or not value.strip() for value in raw_qualifiers
    ):
        return {}, ["verification_verified_fact_qualifiers_invalid"]
    raw_pages = raw_fact.get("supporting_physical_pages")
    if (
        raw_pages is not None
        and _strict_physical_page_list(
            {"supporting_physical_pages": raw_pages}, "supporting_physical_pages"
        )
        is None
    ):
        return {}, ["verification_verified_fact_pages_invalid"]
    return {
        "statement": statement,
        "metric": metric,
        "qualifiers": [value.strip() for value in raw_qualifiers],
    }, []


def _authoritative_verified_fact(
    *,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    outcome: str,
    verified_fact: Mapping[str, Any] | None,
    supporting_physical_pages: list[int],
    inspected_physical_pages: list[int],
    source_truth_notes_by_page: Mapping[str, str],
) -> dict[str, Any]:
    if outcome not in {"verified", "verified_after_retry"} or not isinstance(
        verified_fact, Mapping
    ):
        return {}
    statement = _text(verified_fact.get("statement"))
    metric = verified_fact.get("metric")
    if not statement or not isinstance(metric, Mapping):
        return {}
    return {
        "schema_version": VERIFIED_FACT_SCHEMA_VERSION,
        "fact_id": _candidate_id(claim),
        "statement": statement,
        "metric": copy.deepcopy(dict(metric)),
        "qualifiers": copy.deepcopy(verified_fact.get("qualifiers") or []),
        "source_identity": request.source_identity,
        "source_pdf_sha256": _source_pdf_sha256(request.source_identity),
        "supporting_physical_pages": list(supporting_physical_pages),
        "verification_outcome": outcome,
        "provenance": {
            "inspected_physical_pages": list(inspected_physical_pages),
            "source_truth_notes_by_page": dict(source_truth_notes_by_page),
            "discovery_candidate_id": _candidate_id(claim),
            "discovery_evidence_ids": _evidence_ids(claim),
        },
    }


def _provider_error_details(prefix: str, error: Exception) -> list[str]:
    if isinstance(error, AppError):
        return [
            prefix,
            f"error_code:{error.code}",
            f"retryable:{str(error.retryable).lower()}",
            f"severity:{error.severity}",
        ]
    return [prefix, f"error_type:{type(error).__name__}", "retryable:unknown"]


def _attempt_is_non_retryable(details: list[str]) -> bool:
    return any(detail.strip().casefold() == "retryable:false" for detail in details)


def _source_truth_notes_present(notes: str) -> bool:
    """Require a bounded, source-specific explanation without judging prose."""

    if not isinstance(notes, str):
        return False
    normalized = re.sub(r"\s+", " ", notes).strip().casefold()
    normalized_without_terminal_punctuation = normalized.rstrip(".!?")
    if len(normalized) < 32:
        return False
    if normalized_without_terminal_punctuation in {
        "the claim is supported by the source",
        "the claim is supported by the source page",
        "the claim is plausible and supported by the source page",
    }:
        return False
    return bool(
        re.search(
            r"\b(?:page|chart|table|figure|section|report|survey|respondent|cohort|"
            r"population|metric|value|share|percent|shows?|reports?|observed|forecast)\b"
            r"|\d|%",
            normalized,
        )
    )


def _require_visual_policy(bundle: Any) -> None:
    model = _text(bundle.resolved_model).lower().removeprefix("openai/")
    effort = _text(bundle.effective_reasoning_effort).lower()
    if not model.startswith("gpt-6-luna") or effort != "high":
        raise AppError(
            code="verified_claims_visual_policy_invalid",
            message=(
                "Visual verified-claims evaluation requires GPT-6 Luna high reasoning"
            ),
            retryable=False,
            context={"model": model, "reasoning_effort": effort},
        )


def _bundle(
    *,
    namespace: str,
    variables: dict[str, Any],
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
):
    bundle = prepare_prompt_bundle(
        namespace=namespace,
        settings=settings,
        ctx=ctx,
        prompt_client=dependencies,
        system_variables={},
        user_variables=variables,
    )
    _require_visual_policy(bundle)
    return bundle


def _request(
    *,
    bundle: Any,
    settings: Any,
    image_paths: list[str],
    report_name: str,
    user_prompt: str,
    namespace: str,
) -> OpenAIJSONImagePromptRequest:
    return OpenAIJSONImagePromptRequest(
        schema_version="1.0",
        system_prompt=bundle.system_prompt,
        user_prompt=user_prompt,
        model=bundle.resolved_model,
        temperature=bundle.effective_temperature,
        api_key=_text(getattr(settings, "openai_api_key", "")),
        image_paths=image_paths,
        reasoning_effort=bundle.effective_reasoning_effort,
        seed=bundle.effective_seed,
        timeout_seconds=bundle.effective_timeout_seconds,
        max_output_tokens=bundle.effective_max_output_tokens,
        cost_ledger_path=_text(
            getattr(settings, "cost_ledger_path", "./out/cost-ledger.jsonl")
        ),
        cost_daily_path=_text(
            getattr(settings, "cost_daily_path", "./out/cost-daily.json")
        ),
        model_pricing=getattr(settings, "model_pricing", {}) or {},
        response_cache_enabled=True,
        response_cache_dir=_text(getattr(settings, "cache_dir", "./cache")),
        response_cache_ttl_seconds=604800.0,
        publisher_name="",
        report_name=report_name,
        source_url="",
        prompt_namespace=namespace,
        prompt_hash=bundle.prompt_content_hash,
        usage_db_path=_text(
            getattr(settings, "usage_db_path", "./state/llm_usage.sqlite")
        ),
        context_compaction_policy=LLMContextCompactionPolicy(
            schema_version="1.0",
            enabled=bundle.routing_decision.compaction_enabled,
            max_input_tokens=bundle.routing_decision.max_input_tokens or None,
        ),
    )


def _record_result(
    *,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    physical_page: int,
    outcome: str,
    failure_reason: str = "",
    final_claim: str = "",
    correction_attempts: list[VisualClaimCorrectionAttempt] | None = None,
    verification_attempts: list[VisualClaimVerificationAttempt] | None = None,
    inspected_physical_pages: list[int] | None = None,
    recovered_physical_pages: list[int] | None = None,
    recovery_reason: str = "",
    source_binding_status: str = "retained",
    supporting_physical_pages: list[int] | None = None,
    source_truth_notes_by_page: Mapping[str, str] | None = None,
    verified_fact: Mapping[str, Any] | None = None,
    canonical_approval_status: str = "not_approved",
) -> VisualClaimEvaluationResult:
    original_physical_pages = _physical_pages(claim) if physical_page > 0 else []
    supporting_pages = list(supporting_physical_pages or [])
    original_claim = _text(claim.get("text") or claim.get("claim"))
    binding_status = _source_binding_status(original_physical_pages, supporting_pages)
    original_evidence_ids = _evidence_ids(claim)
    original_evidence_spans = _evidence_spans(claim)
    original_metric_binding = _complete_metric_binding(claim)
    authoritative_verified_fact = _authoritative_verified_fact(
        claim=claim,
        request=request,
        outcome=outcome,
        verified_fact=verified_fact,
        supporting_physical_pages=supporting_pages,
        inspected_physical_pages=list(
            inspected_physical_pages or original_physical_pages
        ),
        source_truth_notes_by_page=source_truth_notes_by_page or {},
    )
    final_binding_is_retained = (
        bool(final_claim)
        and binding_status == "retained"
        and bool(original_evidence_ids)
        and _claims_have_identical_proposition(original_claim, final_claim)
    )
    return VisualClaimEvaluationResult(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        candidate_id=_candidate_id(claim),
        original_claim=original_claim,
        source_identity=request.source_identity,
        physical_page=physical_page,
        physical_pages=_physical_pages(claim) if physical_page > 0 else [],
        outcome=outcome,
        evidence_ids=original_evidence_ids,
        evidence_spans=original_evidence_spans,
        original_metric_binding=original_metric_binding,
        corrected_evidence_ids=(
            list(original_evidence_ids) if final_binding_is_retained else []
        ),
        corrected_evidence_spans=(
            copy.deepcopy(original_evidence_spans) if final_binding_is_retained else []
        ),
        corrected_metric_binding=(
            copy.deepcopy(original_metric_binding) if final_binding_is_retained else {}
        ),
        corrected_source_binding_status=(
            "retained" if final_binding_is_retained else "unbound"
        ),
        correction_attempts=list(correction_attempts or []),
        verification_attempts=list(verification_attempts or []),
        final_claim=final_claim,
        failure_reason=failure_reason,
        original_physical_pages=original_physical_pages,
        inspected_physical_pages=list(
            inspected_physical_pages or original_physical_pages
        ),
        recovered_physical_pages=list(recovered_physical_pages or []),
        recovery_reason=recovery_reason,
        source_binding_status=binding_status,
        supporting_physical_pages=supporting_pages,
        source_truth_notes_by_page=dict(source_truth_notes_by_page or {}),
        canonical_approval_status=canonical_approval_status,
        verified_fact=authoritative_verified_fact,
    )


def _correction_attempt(
    *,
    attempt: int,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    image_paths: list[str],
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
    bundle: Any,
    retry_feedback: list[str],
    inspected_physical_pages: list[int],
    recovery_candidates: list[dict[str, Any]],
) -> tuple[VisualClaimCorrectionAttempt, str]:
    binding = _claim_binding(
        claim=claim,
        source_identity=request.source_identity,
        physical_page=(
            _physical_page(claim)
            or (inspected_physical_pages[0] if inspected_physical_pages else 0)
        ),
        inspected_physical_pages=inspected_physical_pages,
        recovery_candidates=recovery_candidates,
    )
    rendered = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=bundle.prompt_set.user,
            variables={
                "claim_json": json.dumps(binding, ensure_ascii=False, sort_keys=True),
                "attempt": attempt,
                "retry_feedback": json.dumps(retry_feedback, ensure_ascii=False),
                "image_page_map": _image_page_map_text(inspected_physical_pages),
            },
        ),
        ctx,
    )
    model_request = _request(
        bundle=bundle,
        settings=settings,
        image_paths=image_paths,
        report_name=request.report_name,
        user_prompt=rendered.text,
        namespace=CORRECTION_NAMESPACE,
    )
    try:
        response = dependencies.openai_chat_json_with_images(model_request, ctx)
        payload = _response_json(response)
        request_id, model = _response_metadata(response, model_request)
    except Exception as error:
        return (
            VisualClaimCorrectionAttempt(
                schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
                attempt=attempt,
                claim="",
                status="failed",
                issues=_provider_error_details("correction_provider_error", error),
                model=model_request.model,
            ),
            "",
        )
    if payload is None:
        return (
            VisualClaimCorrectionAttempt(
                schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
                attempt=attempt,
                claim="",
                status="failed",
                issues=["correction_response_invalid"],
                request_id=request_id,
                model=model,
            ),
            "",
        )
    issues: list[str] | None
    if not isinstance(payload.get("claim"), str) or not isinstance(
        payload.get("status"), str
    ):
        status = "failed"
        corrected_claim = ""
        issues = ["correction_response_invalid"]
    else:
        corrected_claim = _text(payload.get("claim"))
        status = _text(payload.get("status")).lower()
        issues = _strict_string_list(payload, "issues")
    if issues is None:
        status = "failed"
        corrected_claim = ""
        issues = ["correction_response_invalid"]
    if (
        status not in _CORRECTION_STATUSES
        or (status == "corrected" and not corrected_claim)
        or (status != "corrected" and corrected_claim)
    ):
        status = "failed"
        issues = [*issues, "correction_response_invalid"]
        corrected_claim = ""
    return (
        VisualClaimCorrectionAttempt(
            schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
            attempt=attempt,
            claim=corrected_claim,
            status=status,
            issues=issues,
            request_id=request_id,
            model=model,
        ),
        corrected_claim if status == "corrected" else "",
    )


def _verification_attempt(
    *,
    attempt: int,
    corrected_claim: str,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    image_paths: list[str],
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
    bundle: Any,
    inspected_physical_pages: list[int],
    recovery_candidates: list[dict[str, Any]],
) -> VisualClaimVerificationAttempt:
    original_physical_pages = _physical_pages(claim)
    source_payload = {
        "source_identity": request.source_identity,
        "physical_page": (
            _physical_page(claim)
            or (inspected_physical_pages[0] if inspected_physical_pages else None)
        ),
        "physical_pages": original_physical_pages,
        "original_physical_pages": original_physical_pages,
        "inspected_physical_pages": inspected_physical_pages,
        "recovered_physical_pages": [
            page
            for page in inspected_physical_pages
            if page not in original_physical_pages
        ],
        "evidence_ids": _evidence_ids(claim),
        "evidence_spans": _prompt_evidence_spans(claim),
        "evidence_span_text_is_unverified": True,
        "replacement_policy": (
            _text(claim.get("_visual_replacement_policy"))
            or "strict_original_direction"
        ),
        "recovery_sources": _recovery_prompt_sources(recovery_candidates),
        "image_page_map": _image_page_map(inspected_physical_pages),
    }
    rendered = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=bundle.prompt_set.user,
            variables={
                "source_json": json.dumps(
                    source_payload, ensure_ascii=False, sort_keys=True
                ),
                "original_claim": _text(claim.get("text") or claim.get("claim")),
                "corrected_claim": corrected_claim,
                "image_page_map": _image_page_map_text(inspected_physical_pages),
            },
        ),
        ctx,
    )
    model_request = _request(
        bundle=bundle,
        settings=settings,
        image_paths=image_paths,
        report_name=request.report_name,
        user_prompt=rendered.text,
        namespace=VERIFICATION_NAMESPACE,
    )
    try:
        response = dependencies.openai_chat_json_with_images(model_request, ctx)
        payload = _response_json(response)
        request_id, model = _response_metadata(response, model_request)
    except Exception as error:
        return VisualClaimVerificationAttempt(
            schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
            attempt=attempt,
            outcome="rejected",
            diagnostics=_provider_error_details("verification_provider_error", error),
            model=model_request.model,
        )
    if payload is None:
        return VisualClaimVerificationAttempt(
            schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
            attempt=attempt,
            outcome="rejected",
            diagnostics=[
                "verification_response_invalid",
                "verification_response_malformed",
            ],
            request_id=request_id,
            model=model,
        )
    diagnostics: list[str] | None
    verified_fact: dict[str, Any] = {}
    verified_fact_issues: list[str] = []
    if not isinstance(payload.get("outcome"), str) or not isinstance(
        payload.get("source_truth_notes"), str
    ):
        outcome = "rejected"
        diagnostics = ["verification_response_invalid"]
        if not isinstance(payload.get("outcome"), str):
            diagnostics.append("verification_outcome_missing")
        if not isinstance(payload.get("source_truth_notes"), str):
            diagnostics.append("verification_source_truth_notes_missing")
        notes = ""
        supporting_pages: list[int] = []
        notes_by_page: dict[str, str] = {}
    else:
        outcome = _text(payload.get("outcome")).lower()
        diagnostics = _strict_string_list(payload, "diagnostics")
        notes = _text(payload.get("source_truth_notes"))
        supporting_pages, notes_by_page, support_diagnostics = _supporting_page_notes(
            payload, inspected_physical_pages
        )
        diagnostics = (
            [*diagnostics, *support_diagnostics] if diagnostics is not None else None
        )
        verified_fact, verified_fact_issues = _normalise_verified_fact_payload(payload)
        if not verified_fact and not verified_fact_issues:
            # A terminal visual verification is only authoritative when it
            # carries the complete source-established fact that downstream
            # admission will project.  Page notes alone are not a factual
            # binding, even when the final claim is unchanged.
            verified_fact_issues.append("verification_verified_fact_missing")
        raw_fact_pages = (
            payload.get("verified_fact", {}).get("supporting_physical_pages")
            if isinstance(payload.get("verified_fact"), Mapping)
            else None
        )
        if (
            verified_fact
            and isinstance(raw_fact_pages, list)
            and raw_fact_pages != supporting_pages
        ):
            verified_fact_issues.append("verification_verified_fact_pages_conflict")
    if diagnostics is None:
        outcome = "rejected"
        diagnostics = [
            "verification_response_invalid",
            "verification_diagnostics_invalid",
        ]
    if outcome not in _VERIFICATION_OUTCOMES:
        outcome = "rejected"
        diagnostics = [*diagnostics, "verification_response_invalid"]
    elif outcome == "verified":
        quality_issues: list[str] = []
        if not notes.strip():
            quality_issues.append("verification_explanation_missing")
        elif not _source_truth_notes_present(notes):
            quality_issues.append("verification_explanation_insubstantial")
        if not supporting_pages:
            quality_issues.append("verification_supporting_pages_invalid")
        if any(
            diagnostic
            in {
                "verification_source_truth_notes_by_page_invalid",
                "verification_source_truth_notes_by_page_incomplete",
            }
            for diagnostic in diagnostics
        ):
            quality_issues.append("verification_source_truth_notes_by_page_invalid")
        quality_issues.extend(verified_fact_issues)
        if quality_issues:
            outcome = "rejected"
            diagnostics = [*diagnostics, *quality_issues]
    elif outcome in {"rejected", "unresolved"} and not diagnostics:
        outcome = "rejected"
        diagnostics = ["verification_diagnostics_missing"]
    if outcome != "verified":
        supporting_pages = []
        notes_by_page = {}
        verified_fact = {}
    return VisualClaimVerificationAttempt(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        attempt=attempt,
        outcome=outcome,
        diagnostics=diagnostics,
        source_truth_notes=notes,
        supporting_physical_pages=supporting_pages,
        source_truth_notes_by_page=notes_by_page,
        verified_fact=verified_fact,
        request_id=request_id,
        model=model,
    )


def _evaluate_claim(
    *,
    claim: Mapping[str, Any],
    request: VisualClaimEvaluationRequest,
    image_paths: list[str],
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
    correction_bundle: Any,
    verification_bundle: Any,
    inspected_physical_pages: list[int],
    recovery_candidates: list[dict[str, Any]],
) -> VisualClaimEvaluationResult:
    original_physical_page = _physical_page(claim)
    physical_page = original_physical_page or (
        inspected_physical_pages[0] if inspected_physical_pages else None
    )
    if not _candidate_id(claim):
        return _record_result(
            claim=claim,
            request=request,
            physical_page=physical_page or 0,
            outcome="skipped",
            failure_reason="candidate_id_missing",
            inspected_physical_pages=inspected_physical_pages,
            recovered_physical_pages=[
                page
                for page in inspected_physical_pages
                if page not in _physical_pages(claim)
            ],
            recovery_reason=_text(recovery_candidates[0].get("reason"))
            if recovery_candidates
            else "",
            source_binding_status=(
                "provisional_recovered" if recovery_candidates else "retained"
            ),
        )
    if physical_page is None:
        return _record_result(
            claim=claim,
            request=request,
            physical_page=0,
            outcome="skipped",
            failure_reason="physical_page_missing",
            inspected_physical_pages=inspected_physical_pages,
        )
    original_claim = _text(claim.get("text") or claim.get("claim"))
    if not original_claim:
        return _record_result(
            claim=claim,
            request=request,
            physical_page=physical_page,
            outcome="skipped",
            failure_reason="claim_text_missing",
            inspected_physical_pages=inspected_physical_pages,
        )
    correction_attempts: list[VisualClaimCorrectionAttempt] = []
    verification_attempts: list[VisualClaimVerificationAttempt] = []
    retry_feedback: list[str] = []
    for correction_number in (1, 2):
        correction_ctx = child_context(
            ctx,
            task_id=f"{ctx.task_id}:correction:{_candidate_id(claim)}:{correction_number}",
        )
        correction, corrected_claim = _correction_attempt(
            attempt=correction_number,
            claim=claim,
            request=request,
            image_paths=image_paths,
            settings=settings,
            ctx=correction_ctx,
            dependencies=dependencies,
            bundle=correction_bundle,
            retry_feedback=retry_feedback,
            inspected_physical_pages=inspected_physical_pages,
            recovery_candidates=recovery_candidates,
        )
        correction_attempts.append(correction)
        if not corrected_claim:
            if _attempt_is_non_retryable(correction.issues):
                return _record_result(
                    claim=claim,
                    request=request,
                    physical_page=physical_page,
                    outcome="unresolved",
                    failure_reason="correction_non_retryable",
                    correction_attempts=correction_attempts,
                    verification_attempts=verification_attempts,
                    inspected_physical_pages=inspected_physical_pages,
                    recovered_physical_pages=[
                        page
                        for page in inspected_physical_pages
                        if page not in _physical_pages(claim)
                    ],
                    recovery_reason=_text(recovery_candidates[0].get("reason"))
                    if recovery_candidates
                    else "",
                    source_binding_status=(
                        "provisional_recovered" if recovery_candidates else "retained"
                    ),
                )
            if correction_number == 1:
                retry_feedback = correction.issues
                continue
            return _record_result(
                claim=claim,
                request=request,
                physical_page=physical_page,
                outcome="unresolved",
                failure_reason="correction_unresolved",
                correction_attempts=correction_attempts,
                verification_attempts=verification_attempts,
                inspected_physical_pages=inspected_physical_pages,
                recovered_physical_pages=[
                    page
                    for page in inspected_physical_pages
                    if page not in _physical_pages(claim)
                ],
                recovery_reason=_text(recovery_candidates[0].get("reason"))
                if recovery_candidates
                else "",
                source_binding_status=(
                    "provisional_recovered" if recovery_candidates else "retained"
                ),
            )
        verification_ctx = child_context(
            ctx,
            task_id=f"{ctx.task_id}:verification:{_candidate_id(claim)}:{correction_number}",
        )
        verification = _verification_attempt(
            attempt=correction_number,
            corrected_claim=corrected_claim,
            claim=claim,
            request=request,
            image_paths=image_paths,
            settings=settings,
            ctx=verification_ctx,
            dependencies=dependencies,
            bundle=verification_bundle,
            inspected_physical_pages=inspected_physical_pages,
            recovery_candidates=recovery_candidates,
        )
        verification_attempts.append(verification)
        if verification.outcome == "verified":
            return _record_result(
                claim=claim,
                request=request,
                physical_page=physical_page,
                outcome="verified"
                if correction_number == 1
                else "verified_after_retry",
                final_claim=corrected_claim,
                correction_attempts=correction_attempts,
                verification_attempts=verification_attempts,
                inspected_physical_pages=inspected_physical_pages,
                recovered_physical_pages=[
                    page
                    for page in inspected_physical_pages
                    if page not in _physical_pages(claim)
                ],
                supporting_physical_pages=verification.supporting_physical_pages,
                source_truth_notes_by_page=verification.source_truth_notes_by_page,
                verified_fact=verification.verified_fact,
                recovery_reason=_text(recovery_candidates[0].get("reason"))
                if recovery_candidates
                else "",
                source_binding_status=(
                    "provisional_recovered" if recovery_candidates else "retained"
                ),
            )
        if _attempt_is_non_retryable(verification.diagnostics):
            return _record_result(
                claim=claim,
                request=request,
                physical_page=physical_page,
                outcome="unresolved",
                failure_reason="verification_non_retryable",
                correction_attempts=correction_attempts,
                verification_attempts=verification_attempts,
                inspected_physical_pages=inspected_physical_pages,
                recovered_physical_pages=[
                    page
                    for page in inspected_physical_pages
                    if page not in _physical_pages(claim)
                ],
                recovery_reason=_text(recovery_candidates[0].get("reason"))
                if recovery_candidates
                else "",
                source_binding_status=(
                    "provisional_recovered" if recovery_candidates else "retained"
                ),
            )
        retry_feedback = verification.diagnostics
    return _record_result(
        claim=claim,
        request=request,
        physical_page=physical_page,
        outcome="failed_verification",
        failure_reason="verification_failed_twice",
        correction_attempts=correction_attempts,
        verification_attempts=verification_attempts,
        inspected_physical_pages=inspected_physical_pages,
        recovered_physical_pages=[
            page
            for page in inspected_physical_pages
            if page not in _physical_pages(claim)
        ],
        recovery_reason=_text(recovery_candidates[0].get("reason"))
        if recovery_candidates
        else "",
        source_binding_status=(
            "provisional_recovered" if recovery_candidates else "retained"
        ),
    )


def _evaluate_prepared_claim(
    *,
    prepared: _PreparedVisualClaim,
    request: VisualClaimEvaluationRequest,
    settings: Any,
    dependencies: VerifiedClaimsVisualDependencies,
    correction_bundle: Any,
    verification_bundle: Any,
) -> VisualClaimEvaluationResult:
    return _evaluate_claim(
        claim=prepared.claim,
        request=request,
        image_paths=list(prepared.image_paths),
        settings=settings,
        ctx=prepared.ctx,
        dependencies=dependencies,
        correction_bundle=correction_bundle,
        verification_bundle=verification_bundle,
        inspected_physical_pages=list(prepared.inspected_physical_pages),
        recovery_candidates=copy.deepcopy(list(prepared.recovery_candidates)),
    )


def _visual_claim_parallel_workers(settings: Any, eligible_count: int) -> int:
    try:
        configured = int(
            getattr(settings, "verified_visual_claim_parallel_workers", 1) or 1
        )
    except (TypeError, ValueError):
        configured = 1
    return min(max(1, configured), max(0, eligible_count))


def _evaluate_prepared_claims(
    *,
    prepared_claims: list[_PreparedVisualClaim],
    request: VisualClaimEvaluationRequest,
    settings: Any,
    dependencies: VerifiedClaimsVisualDependencies,
    correction_bundle: Any,
    verification_bundle: Any,
) -> dict[int, VisualClaimEvaluationResult]:
    """Evaluate prepared candidates with bounded, indexed worker scheduling."""

    if not prepared_claims:
        return {}

    worker_count = _visual_claim_parallel_workers(settings, len(prepared_claims))
    results: dict[int, VisualClaimEvaluationResult] = {}

    def evaluate_one(
        prepared: _PreparedVisualClaim,
    ) -> VisualClaimEvaluationResult:
        return _evaluate_prepared_claim(
            prepared=prepared,
            request=request,
            settings=settings,
            dependencies=dependencies,
            correction_bundle=correction_bundle,
            verification_bundle=verification_bundle,
        )

    if worker_count <= 1:
        for prepared in prepared_claims:
            results[prepared.index] = evaluate_one(prepared)
        return results

    executor = ThreadPoolExecutor(max_workers=worker_count)
    active: dict[Future[VisualClaimEvaluationResult], _PreparedVisualClaim] = {}
    next_index = 0
    try:
        while next_index < min(worker_count, len(prepared_claims)):
            prepared = prepared_claims[next_index]
            active[executor.submit(evaluate_one, prepared)] = prepared
            next_index += 1

        while active:
            completed, _ = wait(active, return_when=FIRST_COMPLETED)
            completed_items = sorted(
                ((future, active[future]) for future in completed),
                key=lambda item: item[1].index,
            )
            completed_results: list[
                tuple[_PreparedVisualClaim, VisualClaimEvaluationResult]
            ] = []
            for future, prepared in completed_items:
                active.pop(future)
                completed_results.append((prepared, future.result()))
            for prepared, result in completed_results:
                results[prepared.index] = result
            for _ in completed_results:
                if next_index >= len(prepared_claims):
                    break
                prepared = prepared_claims[next_index]
                active[executor.submit(evaluate_one, prepared)] = prepared
                next_index += 1
    except BaseException:
        for future in active:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    return results


def evaluate_shortlisted_claims(
    *,
    request: VisualClaimEvaluationRequest,
    settings: Any,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies | None = None,
) -> VisualClaimEvaluationResponse:
    """Evaluate shortlisted claims in shadow mode without mutating the source artifact.

    The returned assessment is intentionally separate from the retained artifact.
    """

    if request.shadow_mode is not True:
        raise AppError(
            code="verified_claims_shadow_mode_required",
            message="Visual verified-claims evaluation is shadow-mode only",
            retryable=False,
        )
    dependencies = dependencies or VerifiedClaimsVisualDependencies.default()
    evaluation_ctx = child_context(ctx, task_id=f"{ctx.task_id}:verified_claims_visual")
    _verify_source_pdf_identity(
        request=request,
        ctx=evaluation_ctx,
        dependencies=dependencies,
    )
    correction_bundle = _bundle(
        namespace=CORRECTION_NAMESPACE,
        variables={
            "claim_json": "",
            "attempt": 1,
            "retry_feedback": "[]",
            "image_page_map": "",
        },
        settings=settings,
        ctx=evaluation_ctx,
        dependencies=dependencies,
    )
    verification_bundle = _bundle(
        namespace=VERIFICATION_NAMESPACE,
        variables={
            "source_json": "{}",
            "corrected_claim": "",
            "image_page_map": "",
        },
        settings=settings,
        ctx=evaluation_ctx,
        dependencies=dependencies,
    )
    rendered_pages: dict[int, str] = {}
    result_slots: list[VisualClaimEvaluationResult | None] = [None] * len(
        request.claims
    )
    prepared_claims: list[_PreparedVisualClaim] = []
    for index, raw_claim in enumerate(request.claims):
        claim = copy.deepcopy(dict(raw_claim)) if isinstance(raw_claim, Mapping) else {}
        physical_pages = _physical_pages(claim)
        recovery_candidates = _recovery_candidates(request, claim)
        raw_recovered_pages = [
            _positive_int(item.get("physical_page") or item.get("page"))
            for item in recovery_candidates
        ]
        recovered_pages = _unique_positive_pages(raw_recovered_pages)
        inspected_physical_pages = list(
            dict.fromkeys([*physical_pages, *recovered_pages])
        )
        physical_page = (
            inspected_physical_pages[0] if inspected_physical_pages else None
        )
        if not inspected_physical_pages:
            result_slots[index] = _record_result(
                claim=claim,
                request=request,
                physical_page=0,
                outcome="skipped",
                failure_reason="physical_page_missing",
            )
            continue
        binding_conflict = _binding_conflict_reason(claim, request.source_identity)
        if binding_conflict:
            result_slots[index] = _record_result(
                claim=claim,
                request=request,
                physical_page=physical_page or 0,
                outcome="skipped",
                failure_reason="source_binding_conflict",
            )
            continue
        missing_page = False
        for page in inspected_physical_pages:
            if page in rendered_pages:
                continue
            render_ctx = child_context(
                evaluation_ctx, task_id=f"{evaluation_ctx.task_id}:render:{page}"
            )
            try:
                render_response = dependencies.render_page_for_crop_refine(
                    CropRefinePageRenderRequest(
                        schema_version="1.1",
                        pdf_path=request.pdf_path,
                        out_dir=request.output_dir,
                        report_name=request.report_name,
                        page=page - 1,
                        dpi=request.dpi,
                    ),
                    render_ctx,
                )
                image_path = _rendered_image_path(render_response, request.output_dir)
            except Exception:
                image_path = ""
            if not image_path:
                missing_page = True
                break
            rendered_pages[page] = image_path
        if missing_page:
            result_slots[index] = _record_result(
                claim=claim,
                request=request,
                physical_page=physical_page or 0,
                outcome="skipped",
                failure_reason="page_render_failed",
                inspected_physical_pages=inspected_physical_pages,
                recovered_physical_pages=recovered_pages,
                recovery_reason=_text(recovery_candidates[0].get("reason"))
                if recovery_candidates
                else "",
                source_binding_status=(
                    "provisional_recovered" if recovery_candidates else "retained"
                ),
            )
            continue
        prepared_claims.append(
            _PreparedVisualClaim(
                index=index,
                claim=claim,
                image_paths=tuple(
                    rendered_pages[page] for page in inspected_physical_pages
                ),
                inspected_physical_pages=tuple(inspected_physical_pages),
                recovery_candidates=tuple(copy.deepcopy(recovery_candidates)),
                ctx=child_context(
                    evaluation_ctx, task_id=f"{evaluation_ctx.task_id}:claim:{index}"
                ),
            )
        )
    evaluated_results = _evaluate_prepared_claims(
        prepared_claims=prepared_claims,
        request=request,
        settings=settings,
        dependencies=dependencies,
        correction_bundle=correction_bundle,
        verification_bundle=verification_bundle,
    )
    for index, result in evaluated_results.items():
        result_slots[index] = result
    results: list[VisualClaimEvaluationResult] = []
    for index, slot_result in enumerate(result_slots):
        if slot_result is None:
            raise AppError(
                code="verified_claims_visual_result_incomplete",
                message=(
                    "Visual evaluation did not produce one terminal result per claim"
                ),
                retryable=False,
                context={"claim_index": index},
            )
        results.append(slot_result)
    LOGGER.info(
        log_event(
            evaluation_ctx,
            role="generator",
            event="verified_claims_visual_shadow_complete",
            module=LOGGER.name,
            fields={
                "claim_count": len(results),
                "rendered_page_count": len(rendered_pages),
                "verified_count": sum(
                    item.outcome in {"verified", "verified_after_retry"}
                    for item in results
                ),
                "failed_verification_count": sum(
                    item.outcome == "failed_verification" for item in results
                ),
                "shadow_mode": True,
            },
        )
    )
    return VisualClaimEvaluationResponse(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        shadow_mode=True,
        claims=results,
        candidate_roster_digest=(
            str(getattr(request, "candidate_roster_digest", "") or "").strip()
            or candidate_roster_digest(request.claims)
        ),
        rendered_pages=rendered_pages,
    )


__all__ = [
    "CORRECTION_NAMESPACE",
    "VERIFICATION_NAMESPACE",
    "VerifiedClaimsVisualDependencies",
    "evaluate_shortlisted_claims",
]
