"""Run a separate, source-grounded editorial review over Step 2 results.

This is an acceptance/evidence tool, not a second verifier.  It receives only
the final corrected claim and the original PDF pages, and it records a separate
shadow manifest without mutating retained or canonical artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.replay_verified_claims_step2 import (
    _explicit_source_records,
    _load_json,
    _relative_repository_path,
    _usage_summary,
)
from src.contracts.config import ConfigLoadRequest
from src.contracts.prompts import PromptRenderRequest
from src.contracts.report_assets import CropRefinePageRenderRequest
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, TaskId
from src.contracts.verified_claims import VisualClaimEvaluationRequest
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    _provider_error_details,
    _rendered_image_path,
    _request,
    _require_visual_policy,
    _response_json,
    _response_metadata,
    _source_pdf_sha256,
    _verify_source_pdf_identity,
)
from src.services.config_service import load_settings
from src.utils.errors import AppError

EDITORIAL_REVIEW_NAMESPACE = "report_vs/validate/editorial_review"
SCHEMA_VERSION = "1.0"
_DECISIONS = frozenset({"approved", "revision_required", "rejected", "unresolved"})
_RATINGS = frozenset(
    {
        "strong",
        "adequate",
        "minor_issue",
        "material_issue",
        "unresolved",
    }
)
_MATERIAL_RATINGS = frozenset({"material_issue"})
_MIN_SOURCE_GROUNDED_EXPLANATION_LENGTH = 40
_DIMENSIONS = (
    "factual_fidelity",
    "analytical_validity",
    "specificity",
    "commercial_relevance",
    "editorial_quality",
    "selection_quality",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strict_pages(value: Any) -> list[int] | None:
    if not isinstance(value, list):
        return None
    pages: list[int] = []
    for page in value:
        if type(page) is not int or page <= 0 or page in pages:
            return None
        pages.append(page)
    return pages


def _nonempty_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _validated_defects(value: Any) -> tuple[list[dict[str, str]], list[str]]:
    if not isinstance(value, list):
        return [], ["defects_invalid"]
    defects: list[dict[str, str]] = []
    diagnostics: list[str] = []
    for defect in value:
        if not isinstance(defect, Mapping):
            diagnostics.append("defects_invalid")
            continue
        dimension = _text(defect.get("dimension"))
        severity = _text(defect.get("severity"))
        description = _text(defect.get("description"))
        if (
            dimension not in _DIMENSIONS
            or severity not in {"minor", "material"}
            or not description
        ):
            diagnostics.append("defects_invalid")
            continue
        defects.append(
            {
                "dimension": dimension,
                "severity": severity,
                "description": description,
            }
        )
    return defects, list(dict.fromkeys(diagnostics))


def _validate_review_payload(
    payload: Any, *, inspected_physical_pages: list[int]
) -> dict[str, Any]:
    """Validate and normalize one independent reviewer response.

    The function is deliberately fail-closed.  It does not decide whether a
    claim is factually true; it ensures that only a complete, source-located
    reviewer assessment can be counted as an approval.
    """

    result: dict[str, Any] = {
        "decision": "unresolved",
        "diagnostics": [],
        "dimensions": {},
        "explanation": "",
        "source_grounded_explanation": "",
        "supporting_physical_pages": [],
        "source_truth_notes_by_page": {},
        "defects": [],
        "suggested_correction": "",
    }
    diagnostics: list[str] = []
    if not isinstance(payload, Mapping):
        result["diagnostics"] = ["review_response_invalid"]
        return result

    raw_decision = payload.get("decision")
    decision = _text(raw_decision).lower()
    if decision not in _DECISIONS:
        diagnostics.append("decision_invalid")
        decision = "unresolved"

    dimensions: dict[str, dict[str, str]] = {}
    for dimension in _DIMENSIONS:
        value = payload.get(dimension)
        if not isinstance(value, Mapping):
            diagnostics.append(f"{dimension}_invalid")
            continue
        rating = _text(value.get("rating")).lower()
        explanation = _nonempty_text(value.get("explanation"))
        if rating not in _RATINGS or explanation is None:
            diagnostics.append(f"{dimension}_invalid")
            continue
        dimensions[dimension] = {"rating": rating, "explanation": explanation}

    explanation = _nonempty_text(payload.get("explanation"))
    source_grounded_explanation = _nonempty_text(
        payload.get("source_grounded_explanation")
    )
    if explanation is None:
        diagnostics.append("explanation_missing")
        explanation = ""
    if source_grounded_explanation is None:
        diagnostics.append("source_grounded_explanation_missing")
        source_grounded_explanation = ""

    raw_pages = payload.get("supporting_physical_pages")
    supporting_pages = _strict_pages(raw_pages)
    if supporting_pages is None or any(
        page not in inspected_physical_pages for page in supporting_pages
    ):
        diagnostics.append("supporting_pages_invalid")
        supporting_pages = []

    raw_notes = payload.get("source_truth_notes_by_page")
    notes: dict[str, str] = {}
    if not isinstance(raw_notes, Mapping):
        diagnostics.append("source_truth_notes_by_page_invalid")
    else:
        for raw_page, raw_note in raw_notes.items():
            try:
                page = int(raw_page)
            except (TypeError, ValueError):
                page = 0
            note = _nonempty_text(raw_note)
            if page <= 0 or note is None or page not in inspected_physical_pages:
                diagnostics.append("source_truth_notes_by_page_invalid")
                continue
            notes[str(page)] = note
        if set(notes) != {str(page) for page in supporting_pages}:
            diagnostics.append("source_truth_notes_by_page_incomplete")

    defects, defect_diagnostics = _validated_defects(payload.get("defects"))
    diagnostics.extend(defect_diagnostics)
    suggested_correction = payload.get("suggested_correction", "")
    if not isinstance(suggested_correction, str):
        diagnostics.append("suggested_correction_invalid")
        suggested_correction = ""

    if len(dimensions) != len(_DIMENSIONS):
        diagnostics.append("dimensions_incomplete")
    if decision == "approved" and not supporting_pages:
        diagnostics.append("supporting_pages_required_for_approval")
    if (
        decision == "approved"
        and len(source_grounded_explanation) < _MIN_SOURCE_GROUNDED_EXPLANATION_LENGTH
    ):
        diagnostics.append("source_grounded_explanation_not_substantive")
    if decision == "approved" and any(len(note) < 20 for note in notes.values()):
        diagnostics.append("source_truth_notes_not_substantive")

    material_factual_issue = dimensions.get("factual_fidelity", {}).get(
        "rating"
    ) in _MATERIAL_RATINGS or any(
        defect["dimension"] == "factual_fidelity" and defect["severity"] == "material"
        for defect in defects
    )
    material_dimension_issue = any(
        dimension.get("rating") in _MATERIAL_RATINGS
        for dimension in dimensions.values()
    )
    unresolved_dimension = any(
        dimension.get("rating") == "unresolved" for dimension in dimensions.values()
    )
    material_defect = any(defect.get("severity") == "material" for defect in defects)
    decision_conflict = decision == "approved" and (
        unresolved_dimension or material_dimension_issue or material_defect
    )
    if decision_conflict:
        diagnostics.append("review_decision_conflict")
    if material_factual_issue and decision == "approved":
        # Retain the existing diagnostic for compatibility, but do not turn a
        # self-contradictory model response into a source-grounded rejection.
        diagnostics.append("material_factual_issue_blocks_approval")

    diagnostics = list(dict.fromkeys(diagnostics))
    structural_diagnostics = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic
        not in {"review_decision_conflict", "material_factual_issue_blocks_approval"}
    ]
    if structural_diagnostics:
        diagnostics.insert(0, "review_response_invalid")
        decision = "unresolved"
    elif decision_conflict:
        decision = "unresolved"

    result.update(
        {
            "decision": decision,
            "diagnostics": diagnostics,
            "dimensions": dimensions,
            "explanation": explanation,
            "source_grounded_explanation": source_grounded_explanation,
            "supporting_physical_pages": supporting_pages,
            "source_truth_notes_by_page": notes,
            "defects": defects,
            "suggested_correction": suggested_correction.strip(),
        }
    )
    return result


def _prompt_evidence_spans(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    keys = {
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
    raw_spans = row.get("evidence_spans")
    if not isinstance(raw_spans, list):
        return []
    return [
        {key: value for key, value in span.items() if key in keys}
        for span in raw_spans
        if isinstance(span, Mapping)
    ]


def _artifact_context(row: Mapping[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {
        "report_title": _text(row.get("report_name") or row.get("report_title")),
        "authority": "metadata_only_non_authoritative",
    }
    raw_categories = row.get("report_categories") or row.get("categories")
    if isinstance(raw_categories, list):
        categories = [_text(value) for value in raw_categories if _text(value)]
        if categories:
            context["categories"] = categories[:8]
    scope = _text(row.get("report_scope") or row.get("scope") or row.get("industry"))
    if scope:
        context["scope"] = scope[:500]
    return context


def _source_context(
    row: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "source_identity": _text(row.get("source_identity")),
        "evidence_ids": [
            _text(value) for value in row.get("evidence_ids") or [] if _text(value)
        ],
        "evidence_spans": _prompt_evidence_spans(row),
        "retained_physical_pages": list(row.get("original_physical_pages") or []),
        "inspected_physical_pages": list(row.get("inspected_physical_pages") or []),
        "source_pdf_sha256_expected": _text(source.get("sha256_expected")),
        "source_pdf_sha256_actual": _text(source.get("sha256_actual")),
    }


def _review_bundle(
    *, settings: Any, ctx: RunContext, dependencies: VerifiedClaimsVisualDependencies
) -> Any:
    bundle = prepare_prompt_bundle(
        namespace=EDITORIAL_REVIEW_NAMESPACE,
        settings=settings,
        ctx=ctx,
        prompt_client=dependencies,
        system_variables={},
        user_variables={
            "final_claim": "",
            "report_context_json": "{}",
            "source_context_json": "{}",
            "image_page_map": "",
            "inspected_physical_pages_json": "[]",
        },
    )
    _require_visual_policy(bundle)
    return bundle


def _image_page_map_text(pages: list[int]) -> str:
    return "\n".join(
        f"image {index} = physical PDF page {page}"
        for index, page in enumerate(pages, start=1)
    )


def _review_request(
    *,
    bundle: Any,
    settings: Any,
    image_paths: list[str],
    report_name: str,
    user_prompt: str,
) -> Any:
    return _request(
        bundle=bundle,
        settings=settings,
        image_paths=image_paths,
        report_name=report_name,
        user_prompt=user_prompt,
        namespace=EDITORIAL_REVIEW_NAMESPACE,
    )


def _base_record(
    *, cohort: str, row: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "cohort": cohort,
        "candidate_id": _text(row.get("candidate_id")),
        "case_id": _text(row.get("case_id")),
        "report_name": _text(row.get("report_name") or row.get("report")),
        "availability": _text(row.get("input_kind")) or "eligible",
        "input_validation_issues": list(row.get("input_validation_issues") or []),
        "original_claim": _text(row.get("original_claim")),
        "final_claim": _text(row.get("final_claim")),
        "source_identity": _text(row.get("source_identity")),
        "source_pdf_sha256_expected": _text(source.get("sha256_expected")),
        "source_pdf_sha256_actual": _text(source.get("sha256_actual")),
        "evidence_ids": list(row.get("evidence_ids") or []),
        "evidence_spans": list(row.get("evidence_spans") or []),
        "original_physical_pages": list(row.get("original_physical_pages") or []),
        "physical_pages": list(row.get("physical_pages") or []),
        "inspected_physical_pages": list(row.get("inspected_physical_pages") or []),
        "source_binding_status": _text(row.get("source_binding_status")),
        "review_invoked": False,
        "decision": "unresolved",
        "diagnostics": [],
        "dimensions": {},
        "explanation": "",
        "source_grounded_explanation": "",
        "supporting_physical_pages": [],
        "source_truth_notes_by_page": {},
        "defects": [],
        "suggested_correction": "",
        "request_id": "",
        "model": "",
        "review_response_sha256": "",
    }


def _unresolved_record(
    *,
    cohort: str,
    row: Mapping[str, Any],
    source: Mapping[str, Any],
    reason: str,
    diagnostics: list[str] | None = None,
) -> dict[str, Any]:
    record = _base_record(cohort=cohort, row=row, source=source)
    record["diagnostics"] = list(dict.fromkeys([reason, *(diagnostics or [])]))
    record["unresolved_reason"] = reason
    return record


def _validate_result_binding(
    row: Mapping[str, Any], source: Mapping[str, Any]
) -> tuple[list[int], str]:
    if not source.get("sha256_matches"):
        return [], "source_pdf_hash_mismatch"
    source_identity = _text(row.get("source_identity"))
    expected_hash = _text(source.get("sha256_expected")).lower()
    try:
        identity_hash = _source_pdf_sha256(source_identity)
    except AppError:
        return [], "source_identity_ambiguous"
    if not expected_hash or identity_hash != expected_hash:
        return [], "source_identity_hash_conflict"
    pages = _strict_pages(row.get("inspected_physical_pages"))
    if not pages:
        return [], "inspected_physical_pages_invalid"
    physical_pages = _strict_pages(row.get("physical_pages"))
    original_pages = _strict_pages(row.get("original_physical_pages"))
    binding_status = _text(row.get("source_binding_status"))
    if (
        binding_status == "provisional_recovered"
        and physical_pages == []
        and original_pages == []
    ):
        if any(page > int(source.get("page_count") or 0) for page in pages):
            return [], "physical_page_out_of_range"
        return pages, ""
    if not physical_pages or not original_pages:
        return [], "retained_physical_pages_invalid"
    if physical_pages != original_pages or not set(original_pages).issubset(pages):
        return [], "retained_physical_pages_conflict"
    if any(page > int(source.get("page_count") or 0) for page in pages):
        return [], "physical_page_out_of_range"
    return pages, ""


def _render_pages(
    *,
    source: Mapping[str, Any],
    report_name: str,
    pages: list[int],
    output_root: Path,
    dependencies: VerifiedClaimsVisualDependencies,
    ctx: RunContext,
) -> tuple[dict[int, str], dict[int, list[str]]]:
    rendered: dict[int, str] = {}
    failures: dict[int, list[str]] = {}
    pdf_path = _text(source.get("resolved_path"))
    for page in pages:
        try:
            response = dependencies.render_page_for_crop_refine(
                CropRefinePageRenderRequest(
                    schema_version="1.1",
                    pdf_path=pdf_path,
                    out_dir=str(output_root),
                    report_name="".join(
                        char if char.isalnum() or char in "-_" else "_"
                        for char in report_name
                    ),
                    page=page - 1,
                    dpi=216,
                ),
                ctx,
            )
            image_path = _rendered_image_path(response, str(output_root))
        except Exception as error:
            rendered[page] = ""
            failures[page] = _provider_error_details("page_render_error", error)
            continue
        if not image_path:
            rendered[page] = ""
            failures[page] = ["page_render_empty_image_path"]
        else:
            rendered[page] = image_path
    return rendered, failures


def _review_one_claim(
    *,
    cohort: str,
    row: Mapping[str, Any],
    source: Mapping[str, Any],
    pages: list[int],
    rendered: Mapping[int, str],
    bundle: Any,
    settings: Any,
    dependencies: VerifiedClaimsVisualDependencies,
    ctx: RunContext,
) -> dict[str, Any]:
    record = _base_record(cohort=cohort, row=row, source=source)
    missing_images = [page for page in pages if not _text(rendered.get(page))]
    if missing_images:
        return _unresolved_record(
            cohort=cohort,
            row=row,
            source=source,
            reason="page_render_failed",
            diagnostics=[f"missing_physical_page:{page}" for page in missing_images],
        )

    report_context = _artifact_context(row)
    source_context = _source_context(row, source)
    rendered_prompt = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=bundle.prompt_set.user,
            variables={
                "final_claim": _text(row.get("final_claim")),
                "report_context_json": json.dumps(
                    report_context, ensure_ascii=False, sort_keys=True
                ),
                "source_context_json": json.dumps(
                    source_context, ensure_ascii=False, sort_keys=True
                ),
                "image_page_map": _image_page_map_text(pages),
                "inspected_physical_pages_json": json.dumps(pages, ensure_ascii=False),
            },
        ),
        ctx,
    )
    request = _review_request(
        bundle=bundle,
        settings=settings,
        image_paths=[rendered[page] for page in pages],
        report_name=_text(row.get("report_name") or row.get("report")),
        user_prompt=rendered_prompt.text,
    )
    record["review_invoked"] = True
    try:
        response = dependencies.openai_chat_json_with_images(request, ctx)
        payload = _response_json(response)
        request_id, model = _response_metadata(response, request)
    except Exception as error:
        record["diagnostics"] = _provider_error_details(
            "editorial_review_provider_error", error
        )
        record["unresolved_reason"] = "editorial_review_provider_error"
        return record

    if payload is None:
        record["diagnostics"] = ["review_response_invalid"]
        record["unresolved_reason"] = "review_response_invalid"
        record["request_id"] = request_id
        record["model"] = model
        return record

    validated = _validate_review_payload(payload, inspected_physical_pages=pages)
    response_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(
        "utf-8"
    )
    record.update(validated)
    record.update(
        {
            "request_id": request_id,
            "model": model,
            "cache_reused": bool(
                isinstance(response, Mapping)
                and (
                    response.get("cache_hit")
                    or response.get("cache_reused")
                    or response.get("from_cache")
                )
            ),
            "review_response_sha256": hashlib.sha256(response_bytes).hexdigest(),
        }
    )
    return record


def _identity_key(report: str, candidate_id: str) -> str:
    return f"{report}\x1f{candidate_id}"


def _append_identity_issue(
    issue_codes: list[str], issue_details: list[dict[str, str]], code: str, detail: str
) -> None:
    if code not in issue_codes:
        issue_codes.append(code)
    issue = {"code": code, "detail": detail}
    if issue not in issue_details:
        issue_details.append(issue)


def _row_identity_issue(row: dict[str, Any], code: str) -> None:
    issues = row.setdefault("input_validation_issues", [])
    if not isinstance(issues, list):
        issues = []
        row["input_validation_issues"] = issues
    if code not in issues:
        issues.append(code)


def _validate_cohort_identity_coverage(
    result: Mapping[str, Any], *, cohort: str
) -> dict[str, Any]:
    """Validate the immutable selected-identity roster before review calls."""

    expected: list[dict[str, str]] = []
    expected_by_id: dict[str, dict[str, str]] = {}
    issue_codes: list[str] = []
    issue_details: list[dict[str, str]] = []

    def add_expected(
        *, report: str, candidate_id: str, availability: str, reason: str = ""
    ) -> None:
        if not candidate_id or not report:
            _append_identity_issue(
                issue_codes,
                issue_details,
                "malformed_expected_identity",
                f"report={report!r}, candidate_id={candidate_id!r}",
            )
            return
        record = {
            "candidate_id": candidate_id,
            "report_name": report,
            "availability": availability,
        }
        if reason:
            record["reason"] = reason
        existing = expected_by_id.get(candidate_id)
        if existing is not None:
            code = (
                "conflicting_expected_identity"
                if existing["report_name"] != report
                else "duplicate_expected_identity"
            )
            _append_identity_issue(
                issue_codes,
                issue_details,
                code,
                f"candidate_id={candidate_id!r}",
            )
            return
        expected.append(record)
        expected_by_id[candidate_id] = record

    claims = result.get("claims")
    claim_rows = claims if isinstance(claims, list) else []
    if not isinstance(claims, list):
        _append_identity_issue(
            issue_codes,
            issue_details,
            "identity_roster_unavailable",
            "result.claims is not a list",
        )

    real_set = result.get("real_shortlisted_set")
    if not isinstance(real_set, Mapping):
        real_set = {}
        _append_identity_issue(
            issue_codes,
            issue_details,
            "identity_roster_unavailable",
            "result.real_shortlisted_set is not an object",
        )

    if cohort == "additional_five":
        inventory = result.get("shortlist_inventory")
        if not isinstance(inventory, list) or not inventory:
            _append_identity_issue(
                issue_codes,
                issue_details,
                "identity_roster_unavailable",
                "result.shortlist_inventory is missing or empty",
            )
            inventory = []
        inventory_unavailable_ids: set[str] = set()
        for raw_inventory in inventory:
            if not isinstance(raw_inventory, Mapping):
                _append_identity_issue(
                    issue_codes,
                    issue_details,
                    "malformed_inventory_entry",
                    "shortlist_inventory contains a non-object entry",
                )
                continue
            report = _text(raw_inventory.get("report"))
            raw_eligible = raw_inventory.get("eligible_candidate_ids")
            eligible = raw_eligible if isinstance(raw_eligible, list) else []
            if not isinstance(raw_eligible, list):
                _append_identity_issue(
                    issue_codes,
                    issue_details,
                    "malformed_inventory_entry",
                    f"report={report!r} eligible_candidate_ids is not a list",
                )
            for raw_candidate_id in eligible:
                add_expected(
                    report=report,
                    candidate_id=_text(raw_candidate_id),
                    availability="eligible",
                )
            raw_unavailable = raw_inventory.get("unavailable")
            unavailable = raw_unavailable if isinstance(raw_unavailable, list) else []
            if not isinstance(raw_unavailable, list):
                _append_identity_issue(
                    issue_codes,
                    issue_details,
                    "malformed_inventory_entry",
                    f"report={report!r} unavailable is not a list",
                )
            for raw_unavailable_row in unavailable:
                if not isinstance(raw_unavailable_row, Mapping):
                    _append_identity_issue(
                        issue_codes,
                        issue_details,
                        "malformed_inventory_entry",
                        f"report={report!r} unavailable contains a non-object entry",
                    )
                    continue
                candidate_id = _text(raw_unavailable_row.get("candidate_id"))
                inventory_unavailable_ids.add(candidate_id)
                add_expected(
                    report=report,
                    candidate_id=candidate_id,
                    availability="unavailable",
                    reason=_text(raw_unavailable_row.get("reason")),
                )
            selected_count = raw_inventory.get("selected_count")
            expected_selected_count = len(eligible) + len(unavailable)
            if (
                type(selected_count) is not int
                or selected_count != expected_selected_count
            ):
                _append_identity_issue(
                    issue_codes,
                    issue_details,
                    "inventory_count_mismatch",
                    "report="
                    f"{report!r} selected_count={selected_count!r} "
                    f"expected={expected_selected_count}",
                )

        result_unavailable = real_set.get("unavailable")
        result_unavailable_rows = (
            result_unavailable if isinstance(result_unavailable, list) else []
        )
        result_unavailable_ids = {
            _text(row.get("candidate_id"))
            for row in result_unavailable_rows
            if isinstance(row, Mapping)
        }
        for candidate_id in sorted(inventory_unavailable_ids - result_unavailable_ids):
            _append_identity_issue(
                issue_codes,
                issue_details,
                "missing_unavailable_record",
                f"candidate_id={candidate_id!r}",
            )
        for candidate_id in sorted(result_unavailable_ids - inventory_unavailable_ids):
            _append_identity_issue(
                issue_codes,
                issue_details,
                "unexpected_unavailable_identity",
                f"candidate_id={candidate_id!r}",
            )
        expected_selected_count = len(expected)
        if real_set.get("selected_claim_count") != expected_selected_count:
            _append_identity_issue(
                issue_codes,
                issue_details,
                "cohort_count_mismatch",
                "selected_claim_count="
                f"{real_set.get('selected_claim_count')!r} "
                f"expected={expected_selected_count}",
            )
        expected_eligible_count = sum(
            record["availability"] == "eligible" for record in expected
        )
        if real_set.get("eligible_claim_count") != expected_eligible_count:
            _append_identity_issue(
                issue_codes,
                issue_details,
                "cohort_count_mismatch",
                "eligible_claim_count="
                f"{real_set.get('eligible_claim_count')!r} "
                f"expected={expected_eligible_count}",
            )
    else:
        real_rows = [
            row
            for row in claim_rows
            if isinstance(row, Mapping)
            and row.get("evaluation_set") == "real_shortlisted"
        ]
        for row in real_rows:
            add_expected(
                report=_text(row.get("report_name") or row.get("report")),
                candidate_id=_text(row.get("candidate_id")),
                availability="eligible",
            )
        expected_count = real_set.get("expected_claim_count")
        input_count = real_set.get("input_claim_count")
        if type(expected_count) is not int or expected_count != len(expected):
            _append_identity_issue(
                issue_codes,
                issue_details,
                "cohort_count_mismatch",
                f"expected_claim_count={expected_count!r} expected={len(expected)}",
            )
        if type(input_count) is not int or input_count != len(expected):
            _append_identity_issue(
                issue_codes,
                issue_details,
                "cohort_count_mismatch",
                f"input_claim_count={input_count!r} expected={len(expected)}",
            )

    normalized_rows: list[dict[str, Any]] = []
    actual_key_counts: Counter[str] = Counter()
    reference_variant_ids: list[str] = []
    for raw_row in claim_rows:
        if not isinstance(raw_row, Mapping):
            _append_identity_issue(
                issue_codes,
                issue_details,
                "malformed_claim_row",
                "result.claims contains a non-object entry",
            )
            continue
        row = dict(raw_row)
        candidate_id = _text(row.get("candidate_id"))
        report = _text(row.get("report_name") or row.get("report"))
        if _text(row.get("cohort")) and _text(row.get("cohort")) != cohort:
            _row_identity_issue(row, "wrong_cohort")
            _append_identity_issue(
                issue_codes,
                issue_details,
                "wrong_cohort",
                f"candidate_id={candidate_id!r}",
            )
        is_selected = row.get("evaluation_set") == "real_shortlisted"
        expected_record = expected_by_id.get(candidate_id)
        if is_selected:
            normalized_rows.append(row)
            if not candidate_id:
                _row_identity_issue(row, "malformed_candidate_id")
                _append_identity_issue(
                    issue_codes,
                    issue_details,
                    "malformed_candidate_id",
                    f"report={report!r}",
                )
            elif expected_record is None:
                _row_identity_issue(row, "unexpected_candidate_id")
                _append_identity_issue(
                    issue_codes,
                    issue_details,
                    "unexpected_candidate_id",
                    f"candidate_id={candidate_id!r}",
                )
            else:
                if report != expected_record["report_name"]:
                    _row_identity_issue(row, "wrong_report")
                    _append_identity_issue(
                        issue_codes,
                        issue_details,
                        "wrong_report",
                        "candidate_id="
                        f"{candidate_id!r} report={report!r} "
                        f"expected={expected_record['report_name']!r}",
                    )
                if expected_record["availability"] != "eligible":
                    _row_identity_issue(row, "unavailable_as_eligible")
                    _append_identity_issue(
                        issue_codes,
                        issue_details,
                        "unavailable_as_eligible",
                        f"candidate_id={candidate_id!r}",
                    )
                actual_key_counts[_identity_key(report, candidate_id)] += 1
        elif candidate_id in expected_by_id:
            _row_identity_issue(row, "incorrectly_classified")
            normalized_rows.append(row)
            _append_identity_issue(
                issue_codes,
                issue_details,
                "incorrectly_classified",
                "candidate_id="
                f"{candidate_id!r} "
                f"evaluation_set={row.get('evaluation_set')!r}",
            )
        elif row.get("evaluation_set") == "reference_variant":
            if not candidate_id:
                _append_identity_issue(
                    issue_codes,
                    issue_details,
                    "malformed_reference_row",
                    "reference_variant has no candidate_id",
                )
            else:
                reference_variant_ids.append(candidate_id)
        else:
            _row_identity_issue(row, "unexpected_candidate_id")
            _append_identity_issue(
                issue_codes,
                issue_details,
                "unexpected_candidate_id",
                "candidate_id="
                f"{candidate_id!r} evaluation_set="
                f"{row.get('evaluation_set')!r}",
            )

    for raw_row in real_set.get("unavailable") or []:
        if not isinstance(raw_row, Mapping):
            _append_identity_issue(
                issue_codes,
                issue_details,
                "malformed_unavailable_row",
                "real_shortlisted_set.unavailable contains a non-object entry",
            )
            continue
        row = dict(raw_row)
        candidate_id = _text(row.get("candidate_id"))
        report = _text(row.get("report") or row.get("report_name"))
        row["report_name"] = report
        row["final_claim"] = ""
        row["original_claim"] = ""
        row["outcome"] = "unavailable"
        row["input_kind"] = "unavailable"
        normalized_rows.append(row)
        expected_record = expected_by_id.get(candidate_id)
        if not candidate_id or expected_record is None:
            _row_identity_issue(row, "unexpected_unavailable_identity")
            _append_identity_issue(
                issue_codes,
                issue_details,
                "unexpected_unavailable_identity",
                f"candidate_id={candidate_id!r}",
            )
        elif report != expected_record["report_name"]:
            _row_identity_issue(row, "wrong_report")
            _append_identity_issue(
                issue_codes,
                issue_details,
                "wrong_report",
                "candidate_id="
                f"{candidate_id!r} report={report!r} "
                f"expected={expected_record['report_name']!r}",
            )
        elif expected_record["availability"] != "unavailable":
            _row_identity_issue(row, "eligible_as_unavailable")
            _append_identity_issue(
                issue_codes,
                issue_details,
                "eligible_as_unavailable",
                f"candidate_id={candidate_id!r}",
            )
        actual_key_counts[_identity_key(report, candidate_id)] += 1

    for row in normalized_rows:
        candidate_id = _text(row.get("candidate_id"))
        report = _text(row.get("report_name") or row.get("report"))
        if actual_key_counts[_identity_key(report, candidate_id)] > 1:
            _row_identity_issue(row, "duplicate_candidate_id")
            _append_identity_issue(
                issue_codes,
                issue_details,
                "duplicate_candidate_id",
                f"candidate_id={candidate_id!r} report={report!r}",
            )

    actual_count = 0
    for record in expected:
        key = _identity_key(record["report_name"], record["candidate_id"])
        if actual_key_counts[key] == 0:
            code = (
                "missing_unavailable_record"
                if record["availability"] == "unavailable"
                else "missing_candidate_id"
            )
            _append_identity_issue(
                issue_codes,
                issue_details,
                code,
                "candidate_id="
                f"{record['candidate_id']!r} "
                f"report={record['report_name']!r}",
            )
            synthetic = {
                "candidate_id": record["candidate_id"],
                "report_name": record["report_name"],
                "input_kind": record["availability"],
                "input_validation_issues": [code],
                "final_claim": "",
                "original_claim": "",
                "outcome": "unavailable"
                if record["availability"] == "unavailable"
                else "",
            }
            normalized_rows.append(synthetic)
        else:
            actual_count += 1

    reference_set = result.get("reference_set")
    if reference_variant_ids:
        if not isinstance(reference_set, Mapping):
            _append_identity_issue(
                issue_codes,
                issue_details,
                "reference_roster_unavailable",
                "reference_set is missing or not an object",
            )
        else:
            expected_reference_count = reference_set.get("candidate_variant_count")
            reference_count_matches = (
                type(expected_reference_count) is int
                and expected_reference_count == len(reference_variant_ids)
            )
            if not reference_count_matches:
                _append_identity_issue(
                    issue_codes,
                    issue_details,
                    "reference_variant_count_mismatch",
                    "reference_variant_count="
                    f"{len(reference_variant_ids)} expected="
                    f"{expected_reference_count!r}",
                )
    coverage_status = "PASS" if not issue_codes and expected else "BLOCKED"
    return {
        "cohort": cohort,
        "coverage_status": coverage_status,
        "authoritative": bool(expected)
        and "identity_roster_unavailable" not in issue_codes,
        "expected_count": len(expected),
        "actual_count": actual_count,
        "expected_records": expected,
        "issue_codes": issue_codes,
        "issues": issue_details,
        "reference_variant_count": len(reference_variant_ids),
        "reference_variant_ids": reference_variant_ids,
        "normalized_rows": normalized_rows,
    }


def _load_review_inputs(
    *, result_path: Path, source_manifest_path: Path, cohort: str
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    result = _load_json(result_path)
    source_manifest = _load_json(source_manifest_path)
    source_records = _explicit_source_records(source_manifest)
    validation = _validate_cohort_identity_coverage(result, cohort=cohort)
    rows = []
    for raw_row in validation["normalized_rows"]:
        row = dict(raw_row)
        row["cohort"] = cohort
        rows.append(row)
    return result, source_records, rows, validation


def _canonical_source_identity(report: str, source: Mapping[str, Any]) -> str:
    return f"{report}|pdf-sha256:{_text(source.get('sha256_expected'))}"


def _verify_report_source(
    *,
    report: str,
    source: Mapping[str, Any],
    output_root: Path,
    ctx: RunContext,
    dependencies: VerifiedClaimsVisualDependencies,
) -> list[str]:
    if not source.get("exists") or not source.get("sha256_matches"):
        return ["source_pdf_hash_mismatch_or_missing"]
    source_identity = _canonical_source_identity(report, source)
    try:
        _verify_source_pdf_identity(
            request=VisualClaimEvaluationRequest(
                schema_version="1.0",
                pdf_path=_text(source.get("resolved_path")),
                output_dir=str(output_root),
                report_name=report,
                source_identity=source_identity,
                claims=[],
                shadow_mode=True,
                dpi=216,
            ),
            ctx=ctx,
            dependencies=dependencies,
        )
    except Exception as error:
        return _provider_error_details("source_pdf_identity_error", error)
    return []


def _record_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = Counter(
        str(record.get("decision") or "unresolved") for record in records
    )
    material_defect_count = 0
    for record in records:
        raw_dimensions = record.get("dimensions")
        dimensions: Mapping[str, Any] = (
            raw_dimensions if isinstance(raw_dimensions, Mapping) else {}
        )
        raw_defects = record.get("defects")
        defects: list[Any] = raw_defects if isinstance(raw_defects, list) else []
        if any(
            isinstance(dimension, Mapping)
            and dimension.get("rating") == "material_issue"
            for dimension in dimensions.values()
        ) or any(
            isinstance(defect, Mapping) and defect.get("severity") == "material"
            for defect in defects
        ):
            material_defect_count += 1
    return {
        "selected_or_unavailable_count": len(records),
        "review_invoked_count": sum(
            bool(record.get("review_invoked")) for record in records
        ),
        "decision_counts": dict(sorted(decisions.items())),
        "material_defect_count": material_defect_count,
        "source_pages_cited": sorted(
            {
                page
                for record in records
                for page in record.get("supporting_physical_pages") or []
                if type(page) is int
            }
        ),
    }


def _acceptance_summary(
    *, records: list[dict[str, Any]], cohort_validations: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Summarize execution, exact identity coverage, and editorial acceptance."""

    coverage_status = (
        "PASS"
        if cohort_validations
        and all(
            validation.get("coverage_status") == "PASS"
            for validation in cohort_validations
        )
        else "BLOCKED"
    )
    execution_reasons: list[str] = []
    for record in records:
        if record.get("review_invoked") or record.get("availability") == "unavailable":
            continue
        execution_reasons.append(
            f"review_not_invoked:{_text(record.get('candidate_id')) or 'unknown'}"
        )
    execution_status = "PASS" if not execution_reasons else "PARTIAL"

    decisions = Counter(
        _text(record.get("decision")) or "unresolved" for record in records
    )
    eligible_decisions = Counter(
        _text(record.get("decision")) or "unresolved"
        for record in records
        if record.get("availability") != "unavailable"
    )
    reasons: list[str] = []
    for validation in cohort_validations:
        for issue_code in validation.get("issue_codes") or []:
            if issue_code not in reasons:
                reasons.append(str(issue_code))
    for decision in ("rejected", "revision_required", "unresolved"):
        if eligible_decisions.get(decision):
            reasons.append(f"{decision}:{eligible_decisions[decision]}")
    if any(record.get("availability") == "unavailable" for record in records):
        reasons.append("expected_unavailable_present")
    reasons = list(dict.fromkeys(reasons))

    eligible_nonapprovals = sum(
        decision_count
        for decision, decision_count in eligible_decisions.items()
        if decision in {"rejected", "revision_required", "unresolved"}
    )
    if coverage_status != "PASS":
        editorial_acceptance_status = "FAIL"
        reasons.insert(0, "identity_coverage_incomplete")
    elif execution_status != "PASS":
        editorial_acceptance_status = "PARTIAL"
        reasons.insert(0, "review_execution_incomplete")
    elif eligible_nonapprovals:
        editorial_acceptance_status = "PARTIAL"
    else:
        editorial_acceptance_status = "PASS"

    return {
        "execution_status": execution_status,
        "coverage_status": coverage_status,
        "editorial_acceptance_status": editorial_acceptance_status,
        "reasons": list(dict.fromkeys(reasons)),
        "selected_claim_count": len(records),
        "review_invoked_count": sum(
            bool(record.get("review_invoked")) for record in records
        ),
        "decision_counts": dict(sorted(decisions.items())),
        "material_defect_count": sum(
            _record_summary([record])["material_defect_count"] for record in records
        ),
        "execution_reasons": list(dict.fromkeys(execution_reasons)),
    }


def _source_record_for_report(
    source_records: Mapping[str, Mapping[str, Any]], report: str
) -> Mapping[str, Any]:
    return source_records.get(
        report,
        {
            "path": "",
            "resolved_path": "",
            "exists": False,
            "sha256_expected": "",
            "sha256_actual": "",
            "sha256_matches": False,
            "page_count": 0,
            "hash_error": "source_manifest_entry_missing",
        },
    )


def run_editorial_review(
    *,
    frozen_result_path: Path,
    frozen_source_manifest_path: Path,
    additional_result_path: Path,
    additional_source_manifest_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    inputs = [
        ("frozen_five", frozen_result_path, frozen_source_manifest_path),
        ("additional_five", additional_result_path, additional_source_manifest_path),
    ]
    loaded: list[
        tuple[
            str,
            Path,
            Path,
            dict[str, Any],
            dict[str, dict[str, Any]],
            list[dict[str, Any]],
            dict[str, Any],
        ]
    ] = []
    for cohort, result_path, source_path in inputs:
        result, sources, rows, validation = _load_review_inputs(
            result_path=result_path,
            source_manifest_path=source_path,
            cohort=cohort,
        )
        loaded.append(
            (cohort, result_path, source_path, result, sources, rows, validation)
        )

    review_root = output_path.parent
    review_root.mkdir(parents=True, exist_ok=True)
    run_id = RunId(f"verified-claims-step2-editorial-review-{int(time.time())}")
    ctx = RunContext(
        schema_version="1.0",
        run_id=run_id,
        task_id=TaskId(str(run_id)),
        span_id=run_id,
    )
    settings = load_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"),
        ctx,
    )
    if not _text(getattr(settings, "openai_api_key", "")):
        raise RuntimeError("OPENAI_API_KEY is not configured")
    settings = replace(
        settings,
        output_dir=str(review_root),
        cache_dir=str(review_root / "cache"),
        cost_ledger_path=str(review_root / "cost-ledger.jsonl"),
        cost_daily_path=str(review_root / "cost-daily.json"),
        usage_db_path=str(review_root / "usage.sqlite"),
    )
    dependencies = VerifiedClaimsVisualDependencies.default()
    bundle = _review_bundle(settings=settings, ctx=ctx, dependencies=dependencies)

    records: list[dict[str, Any]] = []
    report_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_audit: dict[str, dict[str, Any]] = {}
    rendered_pages: dict[tuple[str, int], str] = {}
    render_failures: dict[tuple[str, int], list[str]] = {}
    report_source_errors: dict[str, list[str]] = {}
    cohort_validations = [entry[6] for entry in loaded]

    all_report_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (
        cohort,
        _result_path,
        _source_path,
        _result,
        source_records,
        rows,
        _validation,
    ) in loaded:
        for row in rows:
            report = _text(row.get("report_name") or row.get("report"))
            all_report_rows[(cohort, report)].append(row)
            source = _source_record_for_report(source_records, report)
            source_audit[f"{cohort}:{report}"] = {
                "report": report,
                "cohort": cohort,
                "path": _relative_repository_path(
                    Path(_text(source.get("resolved_path")))
                )
                if _text(source.get("resolved_path"))
                else "",
                "sha256_expected": _text(source.get("sha256_expected")),
                "sha256_actual": _text(source.get("sha256_actual")),
                "sha256_matches": bool(source.get("sha256_matches")),
                "page_count": int(source.get("page_count") or 0),
            }

    for (cohort, report), rows in sorted(all_report_rows.items()):
        source_records = next(entry[4] for entry in loaded if entry[0] == cohort)
        source = _source_record_for_report(source_records, report)
        source_error = _verify_report_source(
            report=report,
            source=source,
            output_root=review_root,
            ctx=ctx,
            dependencies=dependencies,
        )
        report_source_errors[f"{cohort}:{report}"] = source_error
        render_pages: set[int] = set()
        for row in rows:
            pages = _strict_pages(row.get("inspected_physical_pages"))
            if pages:
                render_pages.update(pages)
        if not source_error:
            rendered, failures = _render_pages(
                source=source,
                report_name=f"{cohort}_{report}",
                pages=sorted(render_pages),
                output_root=review_root / "pages",
                dependencies=dependencies,
                ctx=ctx,
            )
            for page, image_path in rendered.items():
                rendered_pages[(f"{cohort}:{report}", page)] = image_path
            for page, details in failures.items():
                render_failures[(f"{cohort}:{report}", page)] = details

        for index, row in enumerate(rows):
            key = f"{cohort}:{report}"
            input_validation_issues = [
                _text(issue)
                for issue in row.get("input_validation_issues") or []
                if _text(issue)
            ]
            if input_validation_issues:
                record = _unresolved_record(
                    cohort=cohort,
                    row=row,
                    source=source,
                    reason="cohort_identity_invalid",
                    diagnostics=input_validation_issues,
                )
            elif _text(row.get("outcome")) == "unavailable":
                record = _unresolved_record(
                    cohort=cohort,
                    row=row,
                    source=source,
                    reason=_text(row.get("reason")) or "retained_claim_unavailable",
                )
            elif source_error:
                record = _unresolved_record(
                    cohort=cohort,
                    row=row,
                    source=source,
                    reason="source_pdf_identity_unverified",
                    diagnostics=source_error,
                )
            else:
                pages, binding_error = _validate_result_binding(row, source)
                if binding_error:
                    record = _unresolved_record(
                        cohort=cohort,
                        row=row,
                        source=source,
                        reason=binding_error,
                    )
                elif _text(row.get("outcome")) not in {
                    "verified",
                    "verified_after_retry",
                }:
                    record = _unresolved_record(
                        cohort=cohort,
                        row=row,
                        source=source,
                        reason="step2_terminal_outcome_not_verified",
                        diagnostics=[
                            f"step2_outcome:{_text(row.get('outcome')) or 'missing'}"
                        ],
                    )
                elif not _text(row.get("final_claim")):
                    record = _unresolved_record(
                        cohort=cohort,
                        row=row,
                        source=source,
                        reason="final_claim_missing",
                    )
                else:
                    page_rendered = {
                        page: rendered_pages.get((key, page), "") for page in pages
                    }
                    record = _review_one_claim(
                        cohort=cohort,
                        row=row,
                        source=source,
                        pages=pages,
                        rendered=page_rendered,
                        bundle=bundle,
                        settings=settings,
                        dependencies=dependencies,
                        ctx=RunContext(
                            schema_version="1.0",
                            run_id=run_id,
                            task_id=TaskId(f"{run_id}:{cohort}:{report}:{index}"),
                            span_id=f"{run_id}:{cohort}:{report}:{index}",
                        ),
                    )
            records.append(record)
            report_records[key].append(record)

    source_manifest_hashes = [
        {
            "cohort": cohort,
            "result_path": _relative_repository_path(result_path),
            "result_sha256": _sha256(result_path),
            "source_manifest_path": _relative_repository_path(source_path),
            "source_manifest_sha256": _sha256(source_path),
        }
        for (
            cohort,
            result_path,
            source_path,
            _result,
            _sources,
            _rows,
            _validation,
        ) in loaded
    ]
    report_summaries = {
        key: _record_summary(value) for key, value in sorted(report_records.items())
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "verified_claims_step2_independent_editorial_review",
        "immutable": True,
        "shadow_only": True,
        "canonical_mutation": False,
        "publication_write": False,
        "reviewer": {
            "model": bundle.resolved_model,
            "reasoning_effort": bundle.effective_reasoning_effort,
            "prompt_namespace": EDITORIAL_REVIEW_NAMESPACE,
            "prompt_content_hash": bundle.prompt_content_hash,
            "execution_identity": bundle.execution_identity.execution_identity,
            "execution_policy_hash": bundle.execution_policy.policy_hash,
        },
        "input_manifests": source_manifest_hashes,
        "source_audit": dict(sorted(source_audit.items())),
        "report_source_errors": dict(sorted(report_source_errors.items())),
        "reports": report_summaries,
        "cohort_validation": {
            validation["cohort"]: {
                key: value
                for key, value in validation.items()
                if key != "normalized_rows"
            }
            for validation in cohort_validations
        },
        "acceptance": _acceptance_summary(
            records=records, cohort_validations=cohort_validations
        ),
        "summary": {
            **_acceptance_summary(
                records=records, cohort_validations=cohort_validations
            ),
            "rendered_page_count": sum(bool(path) for path in rendered_pages.values()),
            "render_failure_count": len(render_failures),
            "cache_reused_count": sum(
                bool(record.get("cache_reused")) for record in records
            ),
        },
        "usage": _usage_summary(review_root / "cost-ledger.jsonl", run_id=run_id),
        "wall_time_seconds": round(time.perf_counter() - started, 3),
        "render_failures": {},
        "records": records,
    }
    # Keep the failure map explicit and deterministic without embedding raw
    # provider exceptions.
    manifest["render_failures"] = {
        f"{key}:{page}": details
        for (key, page), details in sorted(render_failures.items())
    }
    return manifest


def write_immutable_manifest(path: Path, manifest: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return _sha256(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-result", type=Path, required=True)
    parser.add_argument("--frozen-source-manifest", type=Path, required=True)
    parser.add_argument("--additional-result", type=Path, required=True)
    parser.add_argument("--additional-source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = run_editorial_review(
        frozen_result_path=args.frozen_result,
        frozen_source_manifest_path=args.frozen_source_manifest,
        additional_result_path=args.additional_result,
        additional_source_manifest_path=args.additional_source_manifest,
        output_path=args.output,
    )
    manifest_sha256 = write_immutable_manifest(args.output, manifest)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "manifest_sha256": manifest_sha256,
                "summary": manifest["summary"],
                "usage": manifest["usage"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    acceptance = manifest["acceptance"]
    return (
        0
        if all(
            acceptance.get(key) == "PASS"
            for key in (
                "execution_status",
                "coverage_status",
                "editorial_acceptance_status",
            )
        )
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
