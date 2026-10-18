"""Provider-free coverage replay for Verified Claims Step 2 shadow mode."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.contracts.config import ConfigLoadRequest
from src.contracts.pdf_text import PdfTextExtractRequest
from src.contracts.run_context import RunContext
from src.contracts.verified_claims import (
    VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
    VisualClaimEvaluationRequest,
)
from src.generators.artifact_normalization import _insights_semantically_equivalent
from src.generators.claim_validation_generator import (
    _has_printed_page_label,
    _recovery_quantity_values,
    _recovery_tokens,
)
from src.generators.verified_claims_visual_generator import (
    evaluate_shortlisted_claims,
)
from src.services.config_service import load_settings
from src.services.pdf_service import extract_pdf_text
from src.utils.errors import AppError
from src.utils.text_normalization import normalize_for_lookup

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = (
    REPOSITORY_ROOT / "docs/quality/verified-claims-step0-reference-cases-20261018.json"
)
REPORT_ORDER = [
    "Capgemini Research Institute",
    "Activate",
    "KPMG",
    "Reuters Institute",
    "Adjust",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_pdf_status(reference: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for report in REPORT_ORDER:
        source = reference["source_pdfs"][report]
        path = REPOSITORY_ROOT / source["path"]
        exists = path.is_file()
        actual_sha = _sha256(path) if exists else ""
        page_count = 0
        if exists:
            with fitz.open(path) as document:
                page_count = int(document.page_count)
        result[report] = {
            "path": source["path"],
            "exists": exists,
            "sha256_expected": source["sha256"],
            "sha256_actual": actual_sha,
            "sha256_matches": bool(exists and actual_sha == source["sha256"]),
            "page_count": page_count,
        }
    return result


def _retained_report_summary(reference: dict[str, Any]) -> list[dict[str, Any]]:
    output_root = REPOSITORY_ROOT / reference["retained_run"]["isolated_output_root"]
    summaries: list[dict[str, Any]] = []
    for report in REPORT_ORDER:
        digest = reference["report_artifact_digests"][report]
        artifact_path = output_root / digest["analysis_directory"] / "artifacts.json"
        if not artifact_path.is_file():
            summaries.append(
                {
                    "report": report,
                    "artifact_available": False,
                    "selected_ids": [],
                    "selected_count": 0,
                    "theme_count": 0,
                }
            )
            continue
        artifact = _load_json(artifact_path)
        insights = artifact.get("insights_final")
        insights = insights if isinstance(insights, list) else []
        selected_ids = [
            str(item.get("id") or item.get("candidate_id") or "").strip()
            for item in insights
            if isinstance(item, dict)
            and str(item.get("id") or item.get("candidate_id") or "").strip()
        ]
        editorial_plan = artifact.get("editorial_plan")
        themes = (
            editorial_plan.get("themes") if isinstance(editorial_plan, dict) else []
        )
        summaries.append(
            {
                "report": report,
                "artifact_available": True,
                "selected_ids": selected_ids,
                "selected_count": len(selected_ids),
                "theme_count": len(themes) if isinstance(themes, list) else 0,
                "artifact_path": str(artifact_path.relative_to(REPOSITORY_ROOT)),
            }
        )
    return summaries


def _retained_artifact_path(reference: dict[str, Any], report: str) -> Path:
    output_root = REPOSITORY_ROOT / reference["retained_run"]["isolated_output_root"]
    digest = reference["report_artifact_digests"].get(report, {})
    analysis_directory = digest.get("analysis_directory")
    if not isinstance(analysis_directory, str) or not analysis_directory:
        return output_root / "missing" / "artifacts.json"
    return output_root / analysis_directory / "artifacts.json"


def _page_value(page: Any, field: str, default: Any = "") -> Any:
    if isinstance(page, Mapping):
        return page.get(field, default)
    return getattr(page, field, default)


def _page_number(page: Any) -> int:
    value = _page_value(page, "page_number", 0)
    return int(value) if isinstance(value, int) and value > 0 else 0


def _page_text(page: Any) -> str:
    return str(_page_value(page, "text", "") or "").strip()


def _page_is_likely_divider(page_text: str, section_title: str = "") -> bool:
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
    contents_prefix = normalized[:240]
    contents_listing = len(re.findall(r"\b\d+\.", normalized[:1600])) >= 3
    if (
        "contents" in contents_prefix
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


def _page_similarity(page_text: str, source_texts: list[str]) -> tuple[int, int]:
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
    reference_page: Any, source_pages: list[Any]
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
    # DocMap/finding page values may be printed page labels rather than PDF
    # indices.  Prefer the unambiguous printed-label mapping when present; use
    # the physical index only when the PDF has no matching label.
    return list(dict.fromkeys(printed or exact))


def _load_recovery_context(reference: dict[str, Any], report: str) -> dict[str, Any]:
    source = reference.get("source_pdfs", {}).get(report)
    if not isinstance(source, dict):
        return {"available": False, "reason": "recovery_source_unavailable"}
    artifact_path = _retained_artifact_path(reference, report)
    if not artifact_path.is_file():
        return {"available": False, "reason": "recovery_inputs_unavailable"}
    pdf_path = REPOSITORY_ROOT / str(source.get("path") or "")
    expected_sha = str(source.get("sha256") or "").lower()
    if not pdf_path.is_file() or not expected_sha or _sha256(pdf_path) != expected_sha:
        return {"available": False, "reason": "source_pdf_hash_unavailable_or_mismatch"}
    analysis_directory = artifact_path.parent
    doc_map_path = analysis_directory / "doc_map.json"
    findings_path = analysis_directory / "findings.json"
    if not doc_map_path.is_file() or not findings_path.is_file():
        return {"available": False, "reason": "recovery_evidence_packs_unavailable"}
    try:
        with fitz.open(pdf_path) as document:
            page_count = int(document.page_count)
        extracted = extract_pdf_text(
            PdfTextExtractRequest(
                schema_version="1.0",
                path=str(pdf_path),
                max_pages=page_count,
                max_chars=5_000_000,
            ),
            RunContext(
                schema_version="1.0",
                run_id="verified-claims-step2-recovery",
                task_id=f"verified-claims-step2-recovery:{_safe_report_name(report)}",
                span_id=f"verified-claims-step2-recovery:{_safe_report_name(report)}",
            ),
        )
    except AppError as error:
        return {
            "available": False,
            "reason": (
                f"pdf_text_extraction_failed:{error.code}:"
                f"retryable_{str(error.retryable).lower()}"
            ),
        }
    except (OSError, ValueError, TypeError) as error:
        return {
            "available": False,
            "reason": f"pdf_text_extraction_failed:{type(error).__name__}",
        }
    return {
        "available": True,
        "source_identity": f"{report}|pdf-sha256:{expected_sha}",
        "pdf_path": str(pdf_path),
        "pages": list(extracted.pages),
        "doc_map": _load_json(doc_map_path),
        "findings": _load_json(findings_path),
    }


def _recovery_candidates_for_claim(
    reference: dict[str, Any],
    report: str,
    claim: Mapping[str, Any],
    *,
    context: dict[str, Any] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Resolve bounded provisional pages from retained artifacts and PDF text."""

    if limit <= 0:
        return []
    context = context or _load_recovery_context(reference, report)
    if not context.get("available"):
        return []
    pages = list(context.get("pages") or [])
    doc_map = context.get("doc_map") if isinstance(context.get("doc_map"), dict) else {}
    findings_pack = (
        context.get("findings") if isinstance(context.get("findings"), dict) else {}
    )
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
    section_texts = []
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
                _page_is_likely_divider(page_text, section_title),
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
            _page_is_likely_divider(_page_text(page_by_number[page]), section_title)
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

    ranked: list[tuple[tuple[float, ...], dict[str, Any]]] = []
    for page_number, page in page_by_number.items():
        if page_number in original_pages:
            continue
        text = _page_text(page)
        if not text or _page_is_likely_divider(text, section_title):
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
                    "section_id": finding_section_by_page.get(
                        page_number, section_id
                    ),
                    "page_text": text,
                    "reason": recovery_reason,
                    "score": score,
                },
            )
        )
    ranked.sort(key=lambda item: item[0])
    return [item[1] for item in ranked[:limit]]


def _retained_claims(
    reference: dict[str, Any], report: str
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load the exact retained Step 1 shortlist without fabricating fixtures."""

    artifact_path = _retained_artifact_path(reference, report)
    if not artifact_path.is_file():
        return (
            [],
            {},
            [
                {
                    "report": report,
                    "reason": "retained_artifacts_unavailable",
                    "path": str(artifact_path),
                }
            ],
        )
    artifact = _load_json(artifact_path)
    insights = artifact.get("insights_final")
    if not isinstance(insights, list):
        return (
            [],
            {},
            [
                {
                    "report": report,
                    "reason": "retained_insights_final_missing",
                    "path": str(artifact_path),
                }
            ],
        )

    claims: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, Any]] = {}
    unavailable: list[dict[str, Any]] = []
    for position, insight in enumerate(insights):
        if not isinstance(insight, dict):
            unavailable.append(
                {
                    "report": report,
                    "position": position,
                    "reason": "retained_insight_not_an_object",
                }
            )
            continue
        candidate_id = str(
            insight.get("id") or insight.get("candidate_id") or ""
        ).strip()
        text = str(insight.get("text") or "").strip()
        pages = insight.get("pages")
        physical_pages = (
            [int(page) for page in pages if isinstance(page, int) and page > 0]
            if isinstance(pages, list)
            else []
        )
        if not candidate_id or not text or not physical_pages:
            unavailable.append(
                {
                    "report": report,
                    "position": position,
                    "candidate_id": candidate_id,
                    "reason": "retained_claim_missing_id_text_or_pages",
                }
            )
            continue
        claim = dict(insight)
        claim["candidate_id"] = candidate_id
        claim["text"] = text
        claim["pages"] = physical_pages
        claim["_visual_replacement_policy"] = "report_level_replacement_allowed"
        claims.append(claim)
        metadata[candidate_id] = {
            "evaluation_set": "real_shortlisted",
            "report": report,
            "source_pages": physical_pages,
            "retained_artifact_path": str(artifact_path.relative_to(REPOSITORY_ROOT)),
        }
    before_bindings = {
        str(claim.get("candidate_id")): {
            "evidence_id": str(claim.get("evidence_id") or ""),
            "pages": list(claim.get("pages") or []),
        }
        for claim in claims
    }
    for claim in claims:
        candidate_id = str(claim.get("candidate_id") or "")
        after_binding = {
            "evidence_id": str(claim.get("evidence_id") or ""),
            "pages": list(claim.get("pages") or []),
            "source_packs": sorted(
                {
                    str(span.get("source_pack") or "")
                    for span in claim.get("evidence_spans") or []
                    if isinstance(span, dict) and str(span.get("source_pack") or "")
                }
            ),
            "canonical_promotion": False,
        }
        metadata[candidate_id]["source_binding_before"] = before_bindings.get(
            candidate_id, {}
        )
        metadata[candidate_id]["source_binding_after"] = after_binding
        metadata[candidate_id]["source_binding_resolution"] = (
            "provisional_page_inspection"
            if after_binding["source_packs"] == ["doc_map"]
            else "retained"
        )
    return claims, metadata, unavailable


def _safe_report_name(report: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", report.lower()).strip("-") or "report"


def _reference_claims(
    reference: dict[str, Any], report: str
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    claims: list[dict[str, Any]] = []
    metadata: dict[str, dict[str, Any]] = {}
    for case in reference.get("cases", []):
        if not isinstance(case, dict) or case.get("report") != report:
            continue
        source_pages = case.get("source_pages")
        physical_pages = (
            source_pages.get("physical_pdf") if isinstance(source_pages, dict) else []
        )
        default_pages = physical_pages
        physical_pages = [
            int(page) for page in physical_pages if isinstance(page, int) and page > 0
        ]
        evidence_ids = [
            str(value).strip()
            for value in case.get("canonical_evidence_ids", [])
            if str(value).strip()
        ]
        fixture = case.get("evaluation_fixture")
        candidates = fixture.get("candidates", []) if isinstance(fixture, dict) else []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            locator_override = candidate.get("evidence_locator_override")
            if isinstance(locator_override, dict):
                physical_pages = locator_override.get("physical_pdf", default_pages)
            else:
                physical_pages = default_pages
            candidate_id = str(candidate.get("candidate_id") or "").strip()
            text = str(candidate.get("text") or "").strip()
            if not candidate_id or not text or not physical_pages:
                continue
            claim: dict[str, Any] = {
                "candidate_id": candidate_id,
                "text": text,
                "pages": physical_pages,
                "_visual_replacement_policy": "strict_original_direction",
            }
            if len(evidence_ids) == 1:
                claim["evidence_id"] = evidence_ids[0]
            elif evidence_ids:
                claim["evidence_ids"] = evidence_ids
            claims.append(claim)
            metadata[candidate_id] = {
                "case_id": str(case.get("case_id") or ""),
                "report": report,
                "expected_assessment": candidate.get("expected_assessment"),
                "corrected_statement_assessment": candidate.get(
                    "corrected_statement_assessment"
                ),
                "mutation": candidate.get("mutation"),
                "source_pages": physical_pages,
                "expected_source_supported": (
                    candidate.get("expected_assessment") == "supported"
                    or candidate.get("corrected_statement_assessment") == "supported"
                ),
            }
    return claims, metadata


def _usage_summary(path: Path, *, run_id: str | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {
            "provider_calls": 0,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "estimated_cost_usd": None,
        }
    rows: list[dict[str, Any]] = []
    all_rows = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            all_rows += 1
            if run_id is not None and payload.get("run_id") != run_id:
                continue
            rows.append(payload)

    def _sum_field(field: str) -> int | float | None:
        values = [row.get(field) for row in rows if row.get(field) is not None]
        return sum(values) if values else None

    input_tokens = _sum_field("input_tokens")
    output_tokens = _sum_field("output_tokens")
    total_tokens = _sum_field("total_tokens")
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    return {
        "provider_calls": len(rows),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": _sum_field("estimated_cost_usd"),
        "ledger_rows_selected": len(rows),
        "ledger_rows_seen": all_rows,
        "ledger_run_id": run_id,
    }


def _outcome_counts(selected_rows: list[dict[str, Any]]) -> dict[str, int]:
    """Return mutually exclusive terminal outcome counts plus verified total."""

    return {
        "verified_total": sum(
            row.get("outcome") in {"verified", "verified_after_retry"}
            for row in selected_rows
        ),
        "verified_first_pass": sum(
            row.get("outcome") == "verified" for row in selected_rows
        ),
        "verified_after_retry": sum(
            row.get("outcome") == "verified_after_retry" for row in selected_rows
        ),
        "failed_verification": sum(
            row.get("outcome") == "failed_verification" for row in selected_rows
        ),
        "unresolved": sum(row.get("outcome") == "unresolved" for row in selected_rows),
        "skipped": sum(row.get("outcome") == "skipped" for row in selected_rows),
    }


def _theme_for_recovery_candidate(
    candidate: Mapping[str, Any], editorial_plan: Mapping[str, Any]
) -> tuple[int | None, str]:
    evidence_ids = {
        str(candidate.get(key) or "").strip().casefold()
        for key in ("evidence_id", "section_id")
        if str(candidate.get(key) or "").strip()
    }
    matches: list[tuple[int, str]] = []
    for theme in editorial_plan.get("themes") or []:
        if not isinstance(theme, dict):
            continue
        theme_ids = {
            str(value or "").strip().casefold()
            for value in theme.get("evidence_ids") or []
        }
        if evidence_ids.intersection(theme_ids):
            priority = theme.get("priority")
            if isinstance(priority, int):
                matches.append((priority, str(theme.get("theme") or "")))
    return min(matches) if matches else (None, "")


def _shadow_replacement_selection(
    *,
    report: str,
    baseline_insights: list[dict[str, Any]],
    retained_rows: list[dict[str, Any]],
    editorial_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Select verified recovered wording for audit only; never mutate artifacts."""

    proposals: list[dict[str, Any]] = []
    for row in retained_rows:
        if row.get("outcome") not in {"verified", "verified_after_retry"}:
            continue
        recovered_pages = [
            page
            for page in row.get("recovered_physical_pages") or []
            if isinstance(page, int) and page > 0
        ]
        final_claim = str(row.get("final_claim") or "").strip()
        recovery_candidates = row.get("recovery_candidates")
        if (
            not recovered_pages
            or not final_claim
            or not isinstance(recovery_candidates, list)
        ):
            continue
        best_source = max(
            (item for item in recovery_candidates if isinstance(item, dict)),
            key=lambda item: (
                float(item.get("score"))
                if isinstance(item.get("score"), (int, float))
                else 0.0
            ),
            default={},
        )
        theme_priority, theme = _theme_for_recovery_candidate(
            best_source, editorial_plan
        )
        specificity = len(_recovery_tokens(final_claim))
        quantities = len(_recovery_quantity_values(final_claim))
        proposals.append(
            {
                "candidate_id": row.get("candidate_id", ""),
                "original_claim": row.get("original_claim", ""),
                "final_claim": final_claim,
                "source_identity": row.get("source_identity", ""),
                "original_evidence_ids": list(row.get("evidence_ids") or []),
                "original_evidence_spans": list(row.get("evidence_spans") or []),
                "recovered_pages": recovered_pages,
                "recovered_evidence_id": best_source.get("evidence_id", ""),
                "recovered_source_pack": best_source.get("source_pack", ""),
                "recovery_reason": row.get("recovery_reason", ""),
                "theme": theme,
                "theme_priority": theme_priority,
                "specificity_tokens": specificity,
                "numeric_values": quantities,
                "source_score": best_source.get("score", 0.0),
                "source_binding_status": "provisional_recovered",
            }
        )

    proposals.sort(
        key=lambda item: (
            item["theme_priority"] if item["theme_priority"] is not None else 10_000,
            -float(item["source_score"] or 0.0),
            -item["numeric_values"],
            -item["specificity_tokens"],
            str(item["candidate_id"]),
        )
    )
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for proposal in proposals:
        shadow_candidate = {
            "id": proposal["candidate_id"],
            "text": proposal["final_claim"],
            "evidence_id": proposal["recovered_evidence_id"],
            "pages": proposal["recovered_pages"],
        }
        duplicate_of = next(
            (
                str(existing.get("id") or existing.get("candidate_id") or "")
                for existing in baseline_insights
                if isinstance(existing, dict)
                and _insights_semantically_equivalent(shadow_candidate, existing)
            ),
            "",
        )
        duplicate_of = duplicate_of or next(
            (
                str(existing.get("candidate_id") or "")
                for existing in selected
                if _insights_semantically_equivalent(shadow_candidate, existing)
            ),
            "",
        )
        if duplicate_of:
            rejected.append(
                {
                    **proposal,
                    "selection_status": "rejected",
                    "selection_reason": f"duplicate_of:{duplicate_of}",
                }
            )
            continue
        if proposal["theme_priority"] is None:
            rejected.append(
                {
                    **proposal,
                    "selection_status": "abstained",
                    "selection_reason": "no_editorial_theme_binding",
                }
            )
            continue
        selected.append(
            {
                **proposal,
                "id": proposal["candidate_id"],
                "text": proposal["final_claim"],
                "evidence_id": proposal["recovered_evidence_id"],
                "selection_status": "selected",
            }
        )

    return {
        "report": report,
        "selected": selected,
        "rejected_or_abstained": rejected,
        "candidate_count": len(proposals),
        "selected_count": len(selected),
        "canonical_mutation": False,
        "publication_write": False,
    }


def replay_live_step2(
    *,
    output_root: Path | None = None,
    reports: list[str] | None = None,
    real_claim_ids: set[str] | None = None,
    include_reference: bool = True,
) -> dict[str, Any]:
    """Run the bounded live visual evaluation against retained local inputs."""

    reference = _load_json(REFERENCE_PATH)
    report_order = reports or REPORT_ORDER
    root = output_root or (REPOSITORY_ROOT / "out" / "verified_claims_step2_live")
    root.mkdir(parents=True, exist_ok=True)
    live_run_id = f"verified-claims-step2-live-{int(time.time())}"
    context = RunContext(
        schema_version="1.0",
        run_id=live_run_id,
        task_id=live_run_id,
        span_id=live_run_id,
    )
    settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"),
        context,
    )
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    settings = replace(
        settings,
        output_dir=str(root),
        cache_dir=str(root / "cache"),
        cost_ledger_path=str(root / "cost-ledger.jsonl"),
        cost_daily_path=str(root / "cost-daily.json"),
        usage_db_path=str(root / "usage.sqlite"),
    )

    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    rendered_page_count = 0
    retained_unavailable: list[dict[str, Any]] = []
    retained_input_count = 0
    shadow_replacement_selection: dict[str, dict[str, Any]] = {}
    for report in REPORT_ORDER:
        if report not in report_order:
            continue
        reference_claims, reference_metadata = (
            _reference_claims(reference, report) if include_reference else ([], {})
        )
        retained_claims, retained_metadata, unavailable = _retained_claims(
            reference, report
        )
        if real_claim_ids is not None:
            retained_claims = [
                claim
                for claim in retained_claims
                if str(claim.get("candidate_id") or "") in real_claim_ids
            ]
            retained_metadata = {
                key: value
                for key, value in retained_metadata.items()
                if key
                in {str(claim.get("candidate_id") or "") for claim in retained_claims}
            }
        retained_input_count += len(retained_claims)
        retained_unavailable.extend(unavailable)
        claims = reference_claims + retained_claims
        metadata = {**reference_metadata, **retained_metadata}
        recovery_context = _load_recovery_context(reference, report)
        recovery_candidates: dict[str, list[dict[str, Any]]] = {}
        for retained_claim in retained_claims:
            candidate_id = str(retained_claim.get("candidate_id") or "")
            candidates_for_claim = _recovery_candidates_for_claim(
                reference,
                report,
                retained_claim,
                context=recovery_context,
            )
            if candidates_for_claim:
                recovery_candidates[candidate_id] = candidates_for_claim
                metadata.setdefault(candidate_id, {})["recovery_candidates"] = [
                    {
                        key: value
                        for key, value in candidate.items()
                        if key != "page_text"
                    }
                    | {"page_text_excerpt": str(candidate.get("page_text") or "")[:600]}
                    for candidate in candidates_for_claim
                ]
                metadata[candidate_id]["recovery_enabled"] = True
            else:
                metadata.setdefault(candidate_id, {})["recovery_candidates"] = []
                metadata[candidate_id]["recovery_enabled"] = False
        metadata["__recovery_context__"] = {
            "available": bool(recovery_context.get("available")),
            "reason": recovery_context.get("reason", ""),
        }
        source = reference["source_pdfs"][report]
        pdf_path = REPOSITORY_ROOT / source["path"]
        request = VisualClaimEvaluationRequest(
            schema_version=VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
            pdf_path=str(pdf_path),
            output_dir=str(root),
            report_name=_safe_report_name(report),
            source_identity=f"{report}|pdf-sha256:{source['sha256']}",
            claims=claims,
            shadow_mode=True,
            dpi=216,
            recovery_enabled=bool(
                retained_claims and recovery_context.get("available")
            ),
            recovery_candidates=recovery_candidates,
        )
        report_context = RunContext(
            schema_version="1.0",
            run_id=live_run_id,
            task_id=f"{live_run_id}:{_safe_report_name(report)}",
            span_id=f"{live_run_id}:{_safe_report_name(report)}",
        )
        response = evaluate_shortlisted_claims(
            request=request,
            settings=settings,
            ctx=report_context,
        )
        rendered_page_count += len(response.rendered_pages)
        for result in response.claims:
            result_payload = asdict(result)
            result_metadata = metadata.get(result.candidate_id, {})
            verified = result.outcome in {"verified", "verified_after_retry"}
            evaluation_set = result_metadata.get("evaluation_set", "reference_variant")
            expected = result_metadata.get("expected_source_supported")
            result_payload.update(
                {
                    "report_name": report,
                    "evaluation_set": evaluation_set,
                    "case_id": result_metadata.get("case_id", ""),
                    "expected_source_supported": (
                        bool(expected)
                        if evaluation_set == "reference_variant"
                        else None
                    ),
                    "outcome_matches_reference": (
                        verified == bool(expected)
                        if evaluation_set == "reference_variant"
                        else None
                    ),
                    "mutation": result_metadata.get("mutation", ""),
                    "retained_artifact_path": result_metadata.get(
                        "retained_artifact_path", ""
                    ),
                    "source_binding_before": result_metadata.get(
                        "source_binding_before", {}
                    ),
                    "source_binding_after": result_metadata.get(
                        "source_binding_after", {}
                    ),
                    "source_binding_resolution": result_metadata.get(
                        "source_binding_resolution", ""
                    ),
                    "recovery_enabled": result_metadata.get("recovery_enabled", False),
                    "recovery_candidates": result_metadata.get(
                        "recovery_candidates", []
                    ),
                }
            )
            rows.append(result_payload)
        artifact = (
            _load_json(_retained_artifact_path(reference, report))
            if _retained_artifact_path(reference, report).is_file()
            else {}
        )
        editorial_plan = (
            artifact.get("editorial_plan")
            if isinstance(artifact.get("editorial_plan"), dict)
            else {}
        )
        shadow_replacement_selection[report] = _shadow_replacement_selection(
            report=report,
            baseline_insights=(
                artifact.get("insights_final")
                if isinstance(artifact.get("insights_final"), list)
                else []
            ),
            retained_rows=[
                row
                for row in rows
                if row.get("report_name") == report
                and row.get("evaluation_set") == "real_shortlisted"
            ],
            editorial_plan=editorial_plan,
        )

    usage = _usage_summary(root / "cost-ledger.jsonl", run_id=live_run_id)
    reference_rows = [
        row for row in rows if row.get("evaluation_set") == "reference_variant"
    ]
    retained_rows = [
        row for row in rows if row.get("evaluation_set") == "real_shortlisted"
    ]
    expected_matches = sum(
        bool(row.get("outcome_matches_reference")) for row in reference_rows
    )
    false_accepts = sum(
        row.get("expected_source_supported") is False
        and row.get("outcome") in {"verified", "verified_after_retry"}
        for row in reference_rows
    )
    false_rejects = sum(
        row.get("expected_source_supported") is True
        and row.get("outcome") not in {"verified", "verified_after_retry"}
        for row in reference_rows
    )
    report = {
        "schema_version": "1.0",
        "stage": "verified_claims_step2_visual_live",
        "provider_status": "dispatched",
        "model": settings.openai_model,
        "reasoning_effort": "high",
        "manifest_sha256": reference.get("scope", {}).get("manifest_sha256", ""),
        "reports": report_order,
        "reference_set": {
            "case_count": (
                sum(
                    1
                    for case in reference.get("cases", [])
                    if isinstance(case, dict) and case.get("report") in report_order
                )
                if include_reference
                else 0
            ),
            "candidate_variant_count": len(reference_rows) if include_reference else 0,
        },
        "input_claim_count": len(rows),
        "real_shortlisted_set": {
            "input_claim_count": retained_input_count,
            "expected_claim_count": (
                29
                if real_claim_ids is None and report_order == REPORT_ORDER
                else retained_input_count
            ),
            "evaluated_claim_count": len(retained_rows),
            "unavailable": retained_unavailable,
            "outcomes": _outcome_counts(retained_rows),
        },
        "rendered_page_count": rendered_page_count,
        "outcomes": {
            **_outcome_counts(rows),
        },
        "reference_comparison": {
            "evaluated_claim_count": len(reference_rows),
            "outcome_matches": expected_matches,
            "false_accepts": false_accepts,
            "false_rejects": false_rejects,
            "note": (
                "Expected-source outcome matching is a reference-case gate; it is "
                "not a substitute for human review of corrected wording."
            ),
        },
        "shadow_replacement_selection": shadow_replacement_selection,
        "usage": usage,
        "wall_time_seconds": round(time.perf_counter() - started, 3),
        "cache": {
            "enabled": True,
            "cache_dir": str(root / "cache"),
            "reuse_measured": False,
        },
        "claims": rows,
    }
    return report


def replay_frozen_step2(
    *, provider_available: bool | None = None, provider_free: bool = True
) -> dict[str, Any]:
    """Report deterministic Step 2 input coverage without fabricating model output."""

    reference = _load_json(REFERENCE_PATH)
    cases = reference.get("cases") if isinstance(reference.get("cases"), list) else []
    variant_count = sum(
        len(case.get("evaluation_fixture", {}).get("candidates", []))
        for case in cases
        if isinstance(case, dict)
        and isinstance(case.get("evaluation_fixture"), dict)
        and isinstance(case["evaluation_fixture"].get("candidates"), list)
    )
    if provider_available is False:
        provider_status = "skipped_unavailable"
        visual_status = "skipped_provider_unavailable"
    elif provider_free:
        provider_status = "skipped_provider_free"
        visual_status = "skipped_provider_free"
    else:
        provider_status = "available_not_dispatched"
        visual_status = "skipped_live_dispatch_not_requested"

    source_pdfs = _source_pdf_status(reference)
    case_rows: list[dict[str, Any]] = []
    for case in cases:
        source_pages = case.get("source_pages") if isinstance(case, dict) else {}
        physical_pages = (
            source_pages.get("physical_pdf") if isinstance(source_pages, dict) else []
        )
        report = str(case.get("report") or "")
        pdf_status = source_pdfs.get(report, {})
        page_available = bool(
            pdf_status.get("exists")
            and all(
                isinstance(page, int)
                and 1 <= page <= int(pdf_status.get("page_count") or 0)
                for page in physical_pages
            )
        )
        case_rows.append(
            {
                "case_id": case.get("case_id", ""),
                "report": report,
                "candidate_variant_count": len(
                    case.get("evaluation_fixture", {}).get("candidates", [])
                    if isinstance(case.get("evaluation_fixture"), dict)
                    and isinstance(case["evaluation_fixture"].get("candidates"), list)
                    else []
                ),
                "physical_pages": physical_pages,
                "complete_page_available": page_available,
                "visual_assessment": visual_status,
                "skip_reason": (
                    "provider_unavailable"
                    if provider_available is False
                    else "provider_free_replay"
                ),
                "model_claim_output": None,
            }
        )

    return {
        "schema_version": "1.0",
        "stage": "verified_claims_step2_visual_shadow",
        "provider_status": provider_status,
        "fabricated_fixture_substitution": False,
        "reports": REPORT_ORDER,
        "reference_set": {
            "path": str(REFERENCE_PATH.relative_to(REPOSITORY_ROOT)),
            "schema_version": reference.get("schema_version", ""),
            "case_count": len(cases),
            "candidate_variant_count": variant_count,
            "manifest_sha256": reference.get("scope", {}).get("manifest_sha256", ""),
        },
        "source_pdfs": source_pdfs,
        "retained_reports": _retained_report_summary(reference),
        "cases": case_rows,
        "live_visual_evaluation": {
            "performed": False,
            "correction_calls": 0,
            "verification_calls": 0,
            "verified_count": 0,
            "verified_after_retry_count": 0,
            "failed_verification_count": 0,
            "tokens": None,
            "cost_usd": None,
            "latency_ms": None,
            "cache_reuse": None,
        },
        "limitation": (
            "This replay checks retained real-report pages and input coverage only. "
            "It does not claim source verification, correction quality, or live model "
            "improvement."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider-free",
        action="store_true",
        help="Report retained input coverage without provider calls.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Dispatch the bounded GPT-6 Luna High shadow evaluation.",
    )
    args = parser.parse_args()
    report = (
        replay_live_step2(output_root=args.output.parent if args.output else None)
        if args.live
        else replay_frozen_step2(provider_free=bool(args.provider_free))
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    with contextlib.suppress(AttributeError):
        sys.stdout.reconfigure(encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
