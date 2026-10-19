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
from src.contracts.run_context import RunContext
from src.contracts.verified_claims import (
    VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
    VisualClaimEvaluationRequest,
)
from src.generators.artifact_normalization import _insights_semantically_equivalent
from src.generators.public_editorial_quality_generator import (
    _FORECAST_MARKER,
    _material_numbers,
    _temporal_qualifiers,
)
from src.generators.verified_claims_recovery import (
    load_verified_claims_recovery_context,
    recovery_candidates_for_claim,
)
from src.generators.verified_claims_recovery import (
    page_is_likely_divider as _recovery_page_is_likely_divider,
)
from src.generators.verified_claims_visual_generator import (
    evaluate_shortlisted_claims,
)
from src.services.config_service import load_settings
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


def _page_is_likely_divider(page_text: str, section_title: str = "") -> bool:
    return _recovery_page_is_likely_divider(page_text, section_title)


def _load_recovery_context(reference: dict[str, Any], report: str) -> dict[str, Any]:
    source = reference.get("source_pdfs", {}).get(report)
    if not isinstance(source, dict):
        return {"available": False, "reason": "recovery_source_unavailable"}
    artifact_path = _retained_artifact_path(reference, report)
    if not artifact_path.is_file():
        return {"available": False, "reason": "recovery_inputs_unavailable"}
    pdf_path = REPOSITORY_ROOT / str(source.get("path") or "")
    expected_sha = str(source.get("sha256") or "").lower()
    if not pdf_path.is_file() or not expected_sha:
        return {"available": False, "reason": "source_pdf_hash_unavailable_or_mismatch"}
    analysis_directory = artifact_path.parent
    doc_map_path = analysis_directory / "doc_map.json"
    findings_path = analysis_directory / "findings.json"
    if not doc_map_path.is_file() or not findings_path.is_file():
        return {"available": False, "reason": "recovery_evidence_packs_unavailable"}
    return load_verified_claims_recovery_context(
        source_identity=f"{report}|pdf-sha256:{expected_sha}",
        pdf_path=str(pdf_path),
        evidence_packs={
            "doc_map": _load_json(doc_map_path),
            "findings": _load_json(findings_path),
        },
        ctx=RunContext(
            schema_version="1.0",
            run_id="verified-claims-step2-recovery",
            task_id=f"verified-claims-step2-recovery:{_safe_report_name(report)}",
            span_id=f"verified-claims-step2-recovery:{_safe_report_name(report)}",
        ),
    )


def _recovery_candidates_for_claim(
    reference: dict[str, Any],
    report: str,
    claim: Mapping[str, Any],
    *,
    context: dict[str, Any] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    context = context or _load_recovery_context(reference, report)
    return recovery_candidates_for_claim(context=context, claim=claim, limit=limit)


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


def _assert_outcome_count_arithmetic(
    selected_rows: list[dict[str, Any]], counts: Mapping[str, int]
) -> None:
    """Fail closed if aggregate counts cannot be reconciled to terminal rows."""

    if counts.get("verified_total") != (
        counts.get("verified_first_pass", 0) + counts.get("verified_after_retry", 0)
    ):
        raise RuntimeError("Step 2 verified outcome counts are inconsistent")
    terminal_count = sum(
        counts.get(key, 0)
        for key in (
            "verified_first_pass",
            "verified_after_retry",
            "failed_verification",
            "unresolved",
            "skipped",
        )
    )
    if terminal_count != len(selected_rows):
        raise RuntimeError("Step 2 terminal outcome counts do not match evaluated rows")


def _theme_for_evidence_ids(
    evidence_ids: list[str], editorial_plan: Mapping[str, Any]
) -> tuple[int | None, str]:
    normalized_ids = {
        str(value or "").strip().casefold()
        for value in evidence_ids
        if str(value or "").strip()
    }
    matches: list[tuple[int, str]] = []
    for theme in editorial_plan.get("themes") or []:
        if not isinstance(theme, dict) or not isinstance(theme.get("priority"), int):
            continue
        theme_ids = {
            str(value or "").strip().casefold()
            for value in theme.get("evidence_ids") or []
            if str(value or "").strip()
        }
        if normalized_ids.intersection(theme_ids):
            matches.append((theme["priority"], str(theme.get("theme") or "")))
    return min(matches) if matches else (None, "")


def _theme_for_recovery_candidate(
    candidate: Mapping[str, Any], editorial_plan: Mapping[str, Any]
) -> tuple[int | None, str]:
    return _theme_for_evidence_ids(
        [
            str(candidate.get(key) or "")
            for key in ("evidence_id", "section_id")
            if str(candidate.get(key) or "")
        ],
        editorial_plan,
    )


def _metric_bindings_conflict(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    left_metric = left.get("metric") if isinstance(left.get("metric"), dict) else {}
    right_metric = right.get("metric") if isinstance(right.get("metric"), dict) else {}
    for field_name in set(left_metric) | set(right_metric):
        left_value = normalize_for_lookup(left_metric.get(field_name))
        right_value = normalize_for_lookup(right_metric.get(field_name))
        if left_value and right_value and left_value != right_value:
            return True
    return False


def _editorial_quality_report(report: str, insights: list[dict[str, Any]]):
    from src.generators.public_editorial_quality_generator import (
        evaluate_public_editorial_quality,
    )

    return evaluate_public_editorial_quality(
        report_id=report,
        artifacts={"insights_final": insights},
    )


def _editorial_duplicate_pairs(quality_report: Any) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for issue in quality_report.issues:
        if issue.rule_id != "public_editorial_quality.duplicate_insight":
            continue
        field = str(issue.affected_field or "")
        if not field.startswith("insights:") or "~insights:" not in field:
            continue
        left, right = field.split("~insights:", 1)
        left = left.removeprefix("insights:")
        if left and right:
            pairs.add(tuple(sorted((left, right))))
    return pairs


def _proposition_temporal_signature(text: str) -> tuple[frozenset[str], frozenset[str]]:
    """Return existing temporal bindings without treating years as quantities."""

    years = frozenset(
        re.findall(r"\b(?:19|20)\d{2}e?\b", text.casefold())
    )
    return frozenset(_temporal_qualifiers(text)), years


def _editorial_duplicate_status(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    duplicate_pairs: set[tuple[str, str]],
) -> str:
    """Classify final propositions without promoting a near-duplicate to fact."""

    left_id = str(left.get("id") or left.get("candidate_id") or "").strip()
    right_id = str(right.get("id") or right.get("candidate_id") or "").strip()
    if left_id and left_id == right_id:
        return "distinct"

    left_text = normalize_for_lookup(left.get("text"))
    right_text = normalize_for_lookup(right.get("text"))
    if left_text and left_text == right_text:
        return "duplicate"
    if _metric_bindings_conflict(left, right):
        return "distinct"
    if (
        left_id
        and right_id
        and left_id != right_id
        and _insights_semantically_equivalent(dict(left), dict(right))
    ):
        return "duplicate"

    pair = tuple(sorted((left_id, right_id)))
    if pair not in duplicate_pairs:
        return "distinct"

    left_numbers = _material_numbers(str(left.get("text") or ""))
    right_numbers = _material_numbers(str(right.get("text") or ""))
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return "distinct"

    left_temporal = _proposition_temporal_signature(str(left.get("text") or ""))
    right_temporal = _proposition_temporal_signature(str(right.get("text") or ""))
    if left_temporal != right_temporal and (any(left_temporal) or any(right_temporal)):
        return "distinct"

    left_forecast = bool(_FORECAST_MARKER.search(str(left.get("text") or "")))
    right_forecast = bool(_FORECAST_MARKER.search(str(right.get("text") or "")))
    if left_forecast != right_forecast:
        return "distinct"

    # The public quality rule is intentionally a near-duplicate signal.  When
    # no authoritative metric or qualifier binding proves equivalence, retain
    # both findings and surface the pair for editorial review.
    return "ambiguous"


def _editorially_duplicate(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    duplicate_pairs: set[tuple[str, str]],
) -> bool:
    """Return the existing duplicate signal, including pairs needing review."""

    return _editorial_duplicate_status(left, right, duplicate_pairs) != "distinct"


def _verified_corrected_insight(
    row: Mapping[str, Any],
    baseline_by_id: Mapping[str, dict[str, Any]],
    *,
    source_page_text_by_page: Mapping[Any, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a fresh quality input for a verified replacement.

    Retained artifacts are lineage only.  They are deliberately not copied into
    this object because their metric/evidence fields describe the original
    claim, not a visually verified replacement.  Verifier notes explain the
    decision but are not verbatim source evidence; when available, the actual
    inspected PDF page text is the only evidence text used for deterministic
    editorial checks.
    """

    candidate_id = str(row.get("candidate_id") or "").strip()
    final_claim = str(row.get("final_claim") or "").strip()
    if not candidate_id or not final_claim:
        return None

    supporting_pages = [
        page
        for page in row.get("supporting_physical_pages") or []
        if type(page) is int and page > 0
    ]
    source_texts: list[str] = []
    normalized_page_texts = {
        int(page): str(text).strip()
        for page, text in (source_page_text_by_page or {}).items()
        if str(page).strip().isdigit() and str(text).strip()
    }
    for page in supporting_pages:
        page_text = normalized_page_texts.get(page, "")
        if page_text:
            source_texts.append(page_text)
    if not source_texts:
        for candidate in row.get("recovery_candidates") or []:
            if not isinstance(candidate, Mapping):
                continue
            page = candidate.get("physical_page") or candidate.get("page")
            if page not in supporting_pages:
                continue
            page_text = str(candidate.get("page_text") or "").strip()
            if page_text:
                source_texts.append(page_text)
    source_text = "\n\n".join(dict.fromkeys(source_texts))

    insight: dict[str, Any] = {
        "id": candidate_id,
        "text": final_claim,
        "pages": supporting_pages,
        "supporting_physical_pages": supporting_pages,
        "evidence_status": "visual_verified_provisional",
    }
    if source_text:
        insight["evidence_id"] = f"provisional-page:{candidate_id}"
        insight["evidence"] = source_text
    return insight


def _shadow_quality_assessment(
    report: str,
    insight: dict[str, Any],
    *,
    visually_verified: bool,
) -> tuple[list[str], list[str], str]:
    """Separate deterministic editorial blockers from visual-evidence pending work."""

    quality = _editorial_quality_report(report, [insight])
    errors = [
        issue.rule_id for issue in quality.issues if issue.severity == "error"
    ]
    visual_pending_rules = {
        "public_editorial_quality.material_claim_evidence_missing",
        "public_editorial_quality.unsupported_numeric_claim",
    }
    pending = (
        [rule for rule in errors if rule in visual_pending_rules]
        if visually_verified
        else []
    )
    blockers = [rule for rule in errors if rule not in pending]
    status = (
        "abstained"
        if blockers
        else "pending_visual_source_text"
        if pending
        else "pass"
    )
    return errors, blockers, status


def _valid_supporting_pages(
    row: Mapping[str, Any], recovery_candidates: list[dict[str, Any]] | None = None
) -> tuple[list[int], str]:
    raw_pages = row.get("supporting_physical_pages")
    inspected = {
        page
        for page in row.get("inspected_physical_pages") or []
        if type(page) is int and page > 0
    }
    if not isinstance(raw_pages, list):
        return [], "supporting_page_provenance_missing"
    pages = [page for page in raw_pages if type(page) is int and page > 0]
    if not pages or len(set(pages)) != len(pages):
        return [], "supporting_page_provenance_invalid"
    if not set(pages).issubset(inspected):
        return [], "supporting_page_provenance_uninspected"
    recovery_pages = {
        page
        for candidate in recovery_candidates or []
        if isinstance(candidate, dict)
        for page in [candidate.get("physical_page") or candidate.get("page")]
        if type(page) is int and page > 0
    }
    if recovery_pages and any(page not in recovery_pages for page in pages):
        return [], "supporting_page_not_recovery_candidate"
    notes = row.get("source_truth_notes_by_page")
    if not isinstance(notes, dict):
        return [], "supporting_page_notes_missing"
    normalized_notes = {str(key) for key in notes}
    if normalized_notes != {str(page) for page in pages} or any(
        not isinstance(value, str) or not value.strip() for value in notes.values()
    ):
        return [], "supporting_page_notes_incomplete"
    return pages, ""


def _provisional_recovery_ids(
    candidates: list[dict[str, Any]], supporting_pages: list[int]
) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    packs: list[str] = []
    for page in supporting_pages:
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_page = candidate.get("physical_page") or candidate.get("page")
            if candidate_page != page:
                continue
            evidence_id = str(candidate.get("evidence_id") or "").strip()
            source_pack = str(candidate.get("source_pack") or "").strip()
            if evidence_id and evidence_id not in ids:
                ids.append(evidence_id)
            if source_pack and source_pack not in packs:
                packs.append(source_pack)
    return ids, packs


def _shadow_replacement_selection(
    *,
    report: str,
    baseline_insights: list[dict[str, Any]],
    retained_rows: list[dict[str, Any]],
    editorial_plan: Mapping[str, Any],
    source_page_text_by_page: Mapping[Any, Any] | None = None,
) -> dict[str, Any]:
    """Select independently page-supported replacements for shadow audit only."""

    baseline_by_id = {
        str(item.get("id") or item.get("candidate_id") or "").strip(): item
        for item in baseline_insights
        if isinstance(item, dict)
        and str(item.get("id") or item.get("candidate_id") or "").strip()
    }
    baseline_order = {
        candidate_id: index for index, candidate_id in enumerate(baseline_by_id)
    }
    verified_insights: list[dict[str, Any]] = []
    verified_by_id: dict[str, dict[str, Any]] = {}
    for row in retained_rows:
        if row.get("outcome") not in {"verified", "verified_after_retry"}:
            continue
        insight = _verified_corrected_insight(
            row,
            baseline_by_id,
            source_page_text_by_page=source_page_text_by_page,
        )
        if insight is None:
            continue
        candidate_id = str(insight.get("id") or "")
        if candidate_id in verified_by_id:
            continue
        verified_by_id[candidate_id] = insight
        verified_insights.append(insight)

    complete_quality = _editorial_quality_report(report, verified_insights)
    duplicate_pairs = _editorial_duplicate_pairs(complete_quality)
    proposals: list[dict[str, Any]] = []
    pre_rejected: list[dict[str, Any]] = []
    ambiguous_duplicate_pairs: set[tuple[str, str]] = set()
    candidate_count = 0
    recovered_ids: set[str] = set()
    for row_order, row in enumerate(retained_rows):
        if row.get("outcome") not in {"verified", "verified_after_retry"}:
            continue
        recovered_pages = [
            page
            for page in row.get("recovered_physical_pages") or []
            if type(page) is int and page > 0
        ]
        final_claim = str(row.get("final_claim") or "").strip()
        recovery_candidates = row.get("recovery_candidates")
        if (
            not recovered_pages
            or not final_claim
            or not isinstance(recovery_candidates, list)
        ):
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        candidate_count += 1
        supporting_pages, support_error = _valid_supporting_pages(
            row, [item for item in recovery_candidates if isinstance(item, dict)]
        )
        if support_error:
            pre_rejected.append(
                {
                    "candidate_id": candidate_id,
                    "final_claim": final_claim,
                    "selection_status": "abstained",
                    "selection_reason": support_error,
                }
            )
            continue
        provisional_ids, provisional_packs = _provisional_recovery_ids(
            [item for item in recovery_candidates if isinstance(item, dict)],
            supporting_pages,
        )
        original_evidence_ids = [
            str(value).strip()
            for value in row.get("evidence_ids") or []
            if str(value).strip()
        ]
        theme_priority, theme = _theme_for_evidence_ids(
            original_evidence_ids, editorial_plan
        )
        if theme_priority is None:
            for candidate in recovery_candidates:
                if not isinstance(candidate, dict):
                    continue
                page = candidate.get("physical_page") or candidate.get("page")
                if page not in supporting_pages:
                    continue
                theme_priority, theme = _theme_for_recovery_candidate(
                    candidate, editorial_plan
                )
                if theme_priority is not None:
                    break
        if candidate_id not in recovered_ids:
            recovered_ids.add(candidate_id)
        editorial_insight = verified_by_id.get(candidate_id)
        if editorial_insight is None:
            pre_rejected.append(
                {
                    "candidate_id": candidate_id,
                    "final_claim": final_claim,
                    "selection_status": "abstained",
                    "selection_reason": "verified_insight_missing",
                }
            )
            continue
        quality_issues, quality_blockers, quality_status = _shadow_quality_assessment(
            report,
            editorial_insight,
            visually_verified=bool(
                row.get("source_truth_notes_by_page")
                and supporting_pages
                and str(row.get("outcome") or "")
                in {"verified", "verified_after_retry"}
            ),
        )
        proposals.append(
            {
                "candidate_id": candidate_id,
                "original_claim": row.get("original_claim", ""),
                "final_claim": final_claim,
                "source_identity": row.get("source_identity", ""),
                "original_evidence_ids": original_evidence_ids,
                "original_evidence_spans": list(row.get("evidence_spans") or []),
                "original_physical_pages": list(
                    row.get("original_physical_pages") or []
                ),
                "recovered_pages": recovered_pages,
                "supporting_physical_pages": supporting_pages,
                "source_truth_notes_by_page": dict(
                    row.get("source_truth_notes_by_page") or {}
                ),
                "provisional_recovery_evidence_ids": provisional_ids,
                "provisional_recovery_source_packs": provisional_packs,
                "recovery_reason": row.get("recovery_reason", ""),
                "theme": theme,
                "theme_priority": theme_priority,
                "source_score": max(
                    (
                        float(item.get("score"))
                        for item in recovery_candidates
                        if isinstance(item, dict)
                        and isinstance(item.get("score"), (int, float))
                    ),
                    default=0.0,
                ),
                "editorial_quality_issues": quality_issues,
                "editorial_quality_blockers": quality_blockers,
                "editorial_quality_status": quality_status,
                "verification_status": str(row.get("outcome") or ""),
                "source_binding_status": "provisional_recovered",
                "canonical_approval_status": "not_approved",
                "row_order": row_order,
                "baseline_order": baseline_order.get(candidate_id, len(baseline_order)),
            }
        )

    proposals.sort(
        key=lambda item: (
            item["theme_priority"] if item["theme_priority"] is not None else 10_000,
            item["baseline_order"],
            item["row_order"],
            str(item["candidate_id"]),
        )
    )
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = [*pre_rejected]
    for proposal in proposals:
        candidate_id = str(proposal["candidate_id"])
        editorial_insight = verified_by_id[candidate_id]
        if proposal["editorial_quality_blockers"]:
            rejected.append(
                {
                    **proposal,
                    "selection_status": "abstained",
                    "selection_reason": "editorial_quality_blocker:"
                    + ",".join(proposal["editorial_quality_blockers"]),
                }
            )
            continue
        duplicate_of = ""
        baseline = baseline_by_id.get(candidate_id)
        if baseline is not None:
            pair_quality = _editorial_quality_report(
                report, [editorial_insight, dict(baseline)]
            )
            if _editorial_duplicate_status(
                editorial_insight,
                baseline,
                _editorial_duplicate_pairs(pair_quality),
            ) == "duplicate":
                duplicate_of = candidate_id
        if not duplicate_of:
            duplicates: list[str] = []
            for other_id, other in verified_by_id.items():
                if other_id == candidate_id:
                    continue
                status = _editorial_duplicate_status(
                    editorial_insight, other, duplicate_pairs
                )
                pair = tuple(sorted((candidate_id, other_id)))
                if status == "duplicate":
                    duplicates.append(other_id)
                elif status == "ambiguous":
                    ambiguous_duplicate_pairs.add(pair)
            if duplicates:
                non_replacement = [
                    other_id for other_id in duplicates if other_id not in recovered_ids
                ]
                if non_replacement:
                    duplicate_of = min(non_replacement)
                else:
                    winner = min(
                        [candidate_id, *duplicates],
                        key=lambda value: (
                            baseline_order.get(value, len(baseline_order)),
                            next(
                                (
                                    item["row_order"]
                                    for item in proposals
                                    if item["candidate_id"] == value
                                ),
                                10_000,
                            ),
                            value,
                        ),
                    )
                    if winner != candidate_id:
                        duplicate_of = winner
        if not duplicate_of:
            for existing in selected:
                existing_id = str(existing.get("candidate_id") or "")
                status = _editorial_duplicate_status(
                    editorial_insight,
                    verified_by_id.get(existing_id, {}),
                    duplicate_pairs,
                )
                pair = tuple(sorted((candidate_id, existing_id)))
                if status == "duplicate":
                    duplicate_of = existing_id
                    break
                if status == "ambiguous":
                    ambiguous_duplicate_pairs.add(pair)
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
                "id": candidate_id,
                "text": proposal["final_claim"],
                "selection_status": "selected",
                "selection_reason": "source_verified_theme_preserved",
                "theme_coverage_preserved": True,
            }
        )

    return {
        "report": report,
        "selected": selected,
        "rejected_or_abstained": rejected,
        "candidate_count": candidate_count,
        "selected_count": len(selected),
        "ambiguous_duplicate_pairs": [
            list(pair) for pair in sorted(ambiguous_duplicate_pairs)
        ],
        "complete_verified_insight_count": len(verified_insights),
        "complete_verified_set_quality": {
            "status": complete_quality.status,
            "publishable": complete_quality.publishable,
            "duplicate_pairs": [list(pair) for pair in sorted(duplicate_pairs)],
            "ambiguous_duplicate_pairs": [
                list(pair) for pair in sorted(ambiguous_duplicate_pairs)
            ],
            "issue_count": len(complete_quality.issues),
        },
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
            source_page_text_by_physical_page={
                int(getattr(page, "page_number", 0)): str(
                    getattr(page, "text", "") or ""
                ).strip()
                for page in recovery_context.get("pages") or []
                if isinstance(getattr(page, "page_number", None), int)
                and getattr(page, "page_number", 0) > 0
                and str(getattr(page, "text", "") or "").strip()
            },
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
            source_page_text_by_page={
                int(getattr(page, "page_number", 0)): str(
                    getattr(page, "text", "") or ""
                ).strip()
                for page in recovery_context.get("pages") or []
                if isinstance(getattr(page, "page_number", None), int)
                and getattr(page, "page_number", 0) > 0
                and str(getattr(page, "text", "") or "").strip()
            },
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
    real_outcomes = _outcome_counts(retained_rows)
    reference_outcomes = _outcome_counts(reference_rows)
    all_outcomes = _outcome_counts(rows)
    _assert_outcome_count_arithmetic(retained_rows, real_outcomes)
    _assert_outcome_count_arithmetic(reference_rows, reference_outcomes)
    _assert_outcome_count_arithmetic(rows, all_outcomes)
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
            "outcomes": real_outcomes,
        },
        "rendered_page_count": rendered_page_count,
        "outcomes": {
            **all_outcomes,
        },
        "reference_comparison": {
            "evaluated_claim_count": len(reference_rows),
            "outcomes": reference_outcomes,
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
