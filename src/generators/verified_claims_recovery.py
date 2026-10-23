"""Deterministic, provisional source-page recovery for visual claim shadowing."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping, Sequence

from src.contracts.files import FileBundleHashRequest
from src.contracts.pdf_text import PdfTextExtractRequest
from src.contracts.run_context import RunContext
from src.contracts.verified_claims import (
    VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
    VisualClaimEvaluationRequest,
)
from src.generators.claim_validation_generator import (
    _has_printed_page_label,
    _recovery_quantity_values,
    _recovery_tokens,
)
from src.services.file_service import hash_file_bundle as service_hash_file_bundle
from src.services.pdf_service import extract_pdf_text
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.text_normalization import normalize_for_lookup

_PDF_SHA256_PATTERN = re.compile(
    r"(?:^|[|,; ])pdf-sha256[:=]([0-9a-f]{64})(?:$|[|,; ])", re.I
)
_MAX_RECOVERY_CANDIDATES = 3
_ROSTER_SCORE_FIELDS = frozenset(
    {
        "editorial_score",
        "relevance_score",
        "score",
        "rank",
        "selection_rank",
        "_selection_score",
    }
)


def source_pdf_sha256(source_identity: str) -> str:
    """Return the single expected PDF hash embedded in a source identity."""

    matches = {
        match.group(1).lower()
        for match in _PDF_SHA256_PATTERN.finditer(str(source_identity or ""))
    }
    return next(iter(matches), "") if len(matches) == 1 else ""


def candidate_roster_digest(candidates: Sequence[Mapping[str, Any]]) -> str:
    """Identify the factual candidate roster used by visual evaluation."""

    roster: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        candidate_id = str(
            candidate.get("id")
            or candidate.get("stable_candidate_id")
            or candidate.get("candidate_id")
            or ""
        ).strip()
        if not candidate_id:
            continue
        roster.append(
            {
                "candidate_id": candidate_id,
                "candidate": {
                    str(key): deepcopy(value)
                    for key, value in candidate.items()
                    if str(key) not in _ROSTER_SCORE_FIELDS
                },
            }
        )
    roster.sort(key=lambda item: (item["candidate_id"], sha256_json(item)))
    return sha256_json(
        {
            "schema_version": "verified_claims_candidate_roster:1",
            "candidates": roster,
        }
    )


def load_verified_claims_recovery_context(
    *,
    source_identity: str,
    pdf_path: str,
    evidence_packs: Mapping[str, Any],
    ctx: RunContext,
    hash_file_bundle=service_hash_file_bundle,
) -> dict[str, Any]:
    """Load hash-checked source pages and retained evidence packs for shadow use."""

    expected_sha = source_pdf_sha256(source_identity)
    if not expected_sha:
        return {"available": False, "reason": "source_pdf_hash_missing"}
    try:
        response = hash_file_bundle(
            FileBundleHashRequest(schema_version="1.0", paths=[pdf_path]), ctx
        )
    except AppError as error:
        return {
            "available": False,
            "reason": f"source_pdf_hash_failed:{error.code}",
        }
    file_hashes = getattr(response, "file_sha256", None)
    if isinstance(response, dict):
        file_hashes = response.get("file_sha256")
    actual_sha = (
        str(file_hashes.get(pdf_path) or "").strip().lower()
        if isinstance(file_hashes, dict)
        else ""
    )
    if actual_sha != expected_sha:
        return {"available": False, "reason": "source_pdf_hash_mismatch"}

    doc_map = (
        evidence_packs.get("doc_map") if isinstance(evidence_packs, Mapping) else {}
    )
    findings = (
        evidence_packs.get("findings") if isinstance(evidence_packs, Mapping) else {}
    )
    if not isinstance(doc_map, dict) or not isinstance(findings, dict):
        return {"available": False, "reason": "recovery_evidence_packs_unavailable"}
    try:
        extracted = extract_pdf_text(
            PdfTextExtractRequest(
                schema_version="1.0",
                path=pdf_path,
                max_pages=1_000_000,
                max_chars=5_000_000,
            ),
            ctx,
        )
    except AppError as error:
        return {
            "available": False,
            "reason": (
                f"pdf_text_extraction_failed:{error.code}:"
                f"retryable_{str(error.retryable).lower()}"
            ),
        }
    return {
        "available": True,
        "source_identity": source_identity,
        "pdf_path": pdf_path,
        "pages": list(getattr(extracted, "pages", []) or []),
        "doc_map": doc_map,
        "findings": findings,
    }


def _page_value(page: Any, field: str, default: Any = "") -> Any:
    if isinstance(page, Mapping):
        return page.get(field, default)
    return getattr(page, field, default)


def _page_number(page: Any) -> int:
    value = _page_value(page, "page_number", 0)
    return int(value) if isinstance(value, int) and value > 0 else 0


def _page_text(page: Any) -> str:
    return str(_page_value(page, "text", "") or "").strip()


def page_is_likely_divider(page_text: str, section_title: str = "") -> bool:
    """Detect navigation/section pages without treating compact charts as empty."""

    normalized = normalize_for_lookup(page_text)
    if not normalized:
        return True
    words = normalized.split()
    has_chart_or_measure = bool(
        re.search(
            r"(?:%|percent|percentage|figure|table|chart|survey|respondent|"
            r"n\s*=|increase|decrease|decline|growth|compared|versus)",
            normalized,
        )
    )
    if len(words) < 35 and not has_chart_or_measure:
        return True
    contents_listing = len(re.findall(r"\b\d+\.", normalized[:1600])) >= 3
    if (
        "contents" in normalized[:240]
        and contents_listing
        and "source:" not in normalized[:1200]
    ):
        return True
    title = normalize_for_lookup(section_title)
    return bool(
        title
        and normalized.count(title) >= 2
        and len(words) < 260
        and not has_chart_or_measure
    )


def _page_similarity(page_text: str, source_texts: Sequence[str]) -> tuple[int, int]:
    page_tokens = _recovery_tokens(page_text)
    page_quantities = _recovery_quantity_values(page_text)
    best_tokens = 0
    best_quantities = 0
    for source_text in source_texts:
        if not source_text:
            continue
        best_tokens = max(best_tokens, len(page_tokens & _recovery_tokens(source_text)))
        best_quantities = max(
            best_quantities,
            len(page_quantities & _recovery_quantity_values(source_text)),
        )
    return best_tokens, best_quantities


def _physical_pages_for_reference(
    reference_page: Any, source_pages: Sequence[Any]
) -> list[int]:
    if not isinstance(reference_page, int) or reference_page <= 0:
        return []
    exact = [
        _page_number(page)
        for page in source_pages
        if _page_number(page) == reference_page
    ]
    printed = [
        _page_number(page)
        for page in source_pages
        if _page_text(page)
        and _has_printed_page_label(_page_text(page), reference_page)
    ]
    return list(dict.fromkeys(printed or exact))


def recovery_candidates_for_claim(
    *, context: Mapping[str, Any], claim: Mapping[str, Any], limit: int = 3
) -> list[dict[str, Any]]:
    """Return bounded provisional pages from retained packs and full PDF text."""

    if limit <= 0 or not context.get("available"):
        return []
    pages = list(context.get("pages") or [])
    doc_map = context.get("doc_map") if isinstance(context.get("doc_map"), dict) else {}
    findings_pack = context.get("findings")
    if not isinstance(findings_pack, dict):
        findings_pack = {}
    candidate_id = str(claim.get("candidate_id") or claim.get("id") or "").strip()
    claim_text = str(claim.get("text") or claim.get("claim") or "").strip()
    claim_evidence = str(claim.get("evidence") or "").strip()
    evidence_id = str(claim.get("evidence_id") or "").strip()
    if not candidate_id or not claim_text or not pages:
        return []

    sections = doc_map.get("sections") if isinstance(doc_map, dict) else []
    section: dict[str, Any] | None = None
    if isinstance(sections, list):
        for raw_section in sections:
            if not isinstance(raw_section, dict):
                continue
            section_id = str(
                raw_section.get("id") or raw_section.get("section_id") or ""
            )
            if section_id == evidence_id:
                section = raw_section
                break
            for span in claim.get("evidence_spans") or []:
                if (
                    isinstance(span, dict)
                    and str(span.get("section_id") or "") == section_id
                ):
                    section = raw_section
                    break
            if section is not None:
                break

    section_id = str(section.get("id") or "") if section else evidence_id
    section_title = str(section.get("title") or "") if section else ""
    section_texts: list[str] = []
    if section:
        section_texts.extend(
            str(section.get(key) or "").strip()
            for key in ("title", "summary")
            if str(section.get(key) or "").strip()
        )
        section_texts.extend(
            str(item).strip()
            for item in section.get("key_points") or []
            if str(item).strip()
        )

    raw_findings = findings_pack.get("findings")
    relevant_findings = [
        finding
        for finding in raw_findings or []
        if isinstance(finding, dict)
        and (
            not section_id
            or str(finding.get("section_id") or "") == section_id
            or str(finding.get("id") or "") == evidence_id
        )
    ]
    source_texts = [claim_text, claim_evidence, *section_texts]
    for finding in relevant_findings:
        source_texts.extend(
            str(finding.get(key) or "").strip()
            for key in ("text", "evidence")
            if str(finding.get(key) or "").strip()
        )
    source_texts = list(dict.fromkeys(text for text in source_texts if text))

    page_by_number = {
        _page_number(page): page for page in pages if _page_number(page) > 0
    }
    original_pages = {
        int(value)
        for value in claim.get("pages") or []
        if isinstance(value, int) and value > 0
    }
    section_start_pages: set[int] = set()
    if section:
        for reference_page in section.get("pages") or []:
            section_start_pages.update(
                _physical_pages_for_reference(reference_page, pages)
            )
    all_section_starts: list[int] = []
    if isinstance(sections, list):
        for raw_section in sections:
            if not isinstance(raw_section, dict):
                continue
            for reference_page in raw_section.get("pages") or []:
                all_section_starts.extend(
                    _physical_pages_for_reference(reference_page, pages)
                )
    section_start = min(section_start_pages) if section_start_pages else None
    next_section_start = next(
        (
            start
            for start in sorted(set(all_section_starts))
            if section_start and start > section_start
        ),
        None,
    )
    original_quality: list[tuple[int, int, bool, bool]] = []
    for page in sorted(original_pages):
        if page not in page_by_number:
            continue
        page_text = _page_text(page_by_number[page])
        tokens, quantities = _page_similarity(page_text, source_texts)
        inside_section = bool(
            section_start is not None
            and page >= section_start
            and (next_section_start is None or page < next_section_start)
        )
        original_quality.append(
            (
                tokens,
                quantities,
                page_is_likely_divider(page_text, section_title),
                inside_section,
            )
        )
    if len(original_pages) > 1 and any(
        not is_divider for _, _, is_divider, _ in original_quality
    ):
        return []
    retained_is_insufficient = not any(
        not is_divider
        and (tokens >= 7 or (inside_section and tokens >= 5) or quantities >= 2)
        for tokens, quantities, is_divider, inside_section in original_quality
    )
    if not retained_is_insufficient:
        return []
    recovery_reason = (
        "retained_page_is_section_divider"
        if any(
            page_is_likely_divider(_page_text(page_by_number[page]), section_title)
            for page in original_pages
            if page in page_by_number
        )
        else "retained_page_irrelevant_or_insufficient"
    )

    body_pages = {
        page_number
        for page_number in page_by_number
        if section_start_pages
        and page_number >= min(section_start_pages)
        and (next_section_start is None or page_number < next_section_start)
        and page_number not in original_pages
    }

    referenced_pages: set[int] = set()
    finding_by_page: dict[int, str] = {}
    finding_section_by_page: dict[int, str] = {}
    for finding in relevant_findings:
        for reference_page in finding.get("pages") or []:
            for physical_page in _physical_pages_for_reference(reference_page, pages):
                referenced_pages.add(physical_page)
                finding_by_page.setdefault(
                    physical_page, str(finding.get("id") or evidence_id)
                )
                finding_section_by_page.setdefault(
                    physical_page, str(finding.get("section_id") or section_id)
                )

    ranked: list[tuple[tuple[float, int], dict[str, Any]]] = []
    for page_number, page in page_by_number.items():
        if page_number in original_pages:
            continue
        text = _page_text(page)
        if not text or page_is_likely_divider(text, section_title):
            continue
        token_overlap, quantity_overlap = _page_similarity(text, source_texts)
        if token_overlap < 4 and quantity_overlap == 0:
            continue
        is_finding_page = page_number in referenced_pages
        is_body_page = page_number in body_pages
        if (
            not is_finding_page
            and not is_body_page
            and token_overlap < 6
            and quantity_overlap == 0
        ):
            continue
        exact_match = any(
            normalize_for_lookup(source_text) in normalize_for_lookup(text)
            for source_text in source_texts
            if len(normalize_for_lookup(source_text)) >= 40
        )
        score = (
            float(is_finding_page) * 30.0
            + float(is_body_page) * 10.0
            + float(exact_match) * 20.0
            + min(token_overlap, 20) * 2.0
            + min(quantity_overlap, 8) * 5.0
        )
        ranked.append(
            (
                (-score, page_number),
                {
                    "physical_page": page_number,
                    "source_identity": context["source_identity"],
                    "source_pack": "findings" if is_finding_page else "doc_map",
                    "evidence_id": finding_by_page.get(page_number, evidence_id),
                    "section_id": finding_section_by_page.get(page_number, section_id),
                    "page_text": text,
                    "reason": recovery_reason,
                    "score": score,
                },
            )
        )
    ranked.sort(key=lambda item: item[0])
    return [item[1] for item in ranked[: min(limit, _MAX_RECOVERY_CANDIDATES)]]


def build_verified_claims_shadow_request(
    *,
    source_identity: str,
    pdf_path: str,
    output_dir: str,
    report_name: str,
    evidence_packs: Mapping[str, Any],
    shortlisted_insights: Sequence[Mapping[str, Any]],
    ctx: RunContext,
    dpi: int = 216,
    recovery_enabled: bool = False,
    recovery_limit: int = 3,
) -> tuple[VisualClaimEvaluationRequest, dict[str, Any]]:
    """Build an explicit shadow request without mutating report artifacts.

    Recovery is opt-in and only claims carrying the explicit report-level
    replacement policy receive provisional page candidates.  The returned
    request is passed to the existing visual generator by an orchestrator or
    evaluation tool; this helper itself performs no model call or persistence.
    """

    claims = [dict(item) for item in shortlisted_insights if isinstance(item, Mapping)]
    context: dict[str, Any] = {"available": False, "reason": "recovery_disabled"}
    recovery_candidates: dict[str, list[dict[str, Any]]] = {}
    if recovery_enabled is True:
        context = load_verified_claims_recovery_context(
            source_identity=source_identity,
            pdf_path=pdf_path,
            evidence_packs=evidence_packs,
            ctx=ctx,
        )
        if context.get("available"):
            for claim in claims:
                candidate_id = str(
                    claim.get("candidate_id") or claim.get("id") or ""
                ).strip()
                if (
                    not candidate_id
                    or str(claim.get("_visual_replacement_policy") or "")
                    != "report_level_replacement_allowed"
                ):
                    continue
                candidates = recovery_candidates_for_claim(
                    context=context, claim=claim, limit=recovery_limit
                )
                if candidates:
                    recovery_candidates[candidate_id] = candidates
    request = VisualClaimEvaluationRequest(
        schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
        pdf_path=pdf_path,
        output_dir=output_dir,
        report_name=report_name,
        source_identity=source_identity,
        claims=claims,
        candidate_roster_digest=candidate_roster_digest(claims),
        shadow_mode=True,
        dpi=dpi,
        recovery_enabled=bool(recovery_candidates),
        recovery_candidates=recovery_candidates,
        source_page_text_by_physical_page={
            _page_number(page): _page_text(page)
            for page in context.get("pages") or []
            if _page_number(page) > 0 and _page_text(page)
        },
    )
    return request, {
        "recovery_context": {
            "available": bool(context.get("available")),
            "reason": str(context.get("reason") or ""),
        },
        "recovery_candidates": recovery_candidates,
        "canonical_mutation": False,
        "publication_write": False,
    }


__all__ = [
    "build_verified_claims_shadow_request",
    "candidate_roster_digest",
    "load_verified_claims_recovery_context",
    "page_is_likely_divider",
    "recovery_candidates_for_claim",
    "source_pdf_sha256",
]
