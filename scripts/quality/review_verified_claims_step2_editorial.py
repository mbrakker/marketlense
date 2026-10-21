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
from collections.abc import Mapping
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

    material_factual_issue = dimensions.get("factual_fidelity", {}).get(
        "rating"
    ) in _MATERIAL_RATINGS or any(
        defect["dimension"] == "factual_fidelity" and defect["severity"] == "material"
        for defect in defects
    )
    if material_factual_issue and decision == "approved":
        diagnostics.append("material_factual_issue_blocks_approval")
        decision = "rejected"

    if decision == "approved":
        if len(dimensions) != len(_DIMENSIONS):
            diagnostics.append("dimensions_incomplete")
        if not supporting_pages:
            diagnostics.append("supporting_pages_required_for_approval")
        if not source_grounded_explanation:
            diagnostics.append("source_grounded_explanation_missing")
        if any(len(note) < 20 for note in notes.values()):
            diagnostics.append("source_truth_notes_not_substantive")

    diagnostics = list(dict.fromkeys(diagnostics))
    if diagnostics and "material_factual_issue_blocks_approval" not in diagnostics:
        diagnostics.insert(0, "review_response_invalid")
    if diagnostics and decision == "approved":
        decision = "unresolved"
    elif diagnostics and decision in {"revision_required", "rejected"}:
        # A malformed non-approval is still an unresolved review, not a
        # fabricated editorial rejection.
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
    path = Path(str(row.get("retained_artifact_path") or ""))
    if not path.is_file():
        return {"report_title": _text(row.get("report_name"))}
    try:
        artifact = _load_json(path)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {"report_title": _text(row.get("report_name"))}
    summary = artifact.get("summary")
    summary_map = summary if isinstance(summary, Mapping) else {}
    topics: list[dict[str, Any]] = []
    for topic in artifact.get("topics_covered") or []:
        if not isinstance(topic, Mapping):
            continue
        topics.append(
            {
                "topic": _text(topic.get("topic")),
                "why_it_matters": _text(topic.get("why_it_matters"))[:700],
                "subtopics": [
                    _text(value)[:240]
                    for value in topic.get("subtopics") or []
                    if _text(value)
                ][:4],
            }
        )
        if len(topics) >= 12:
            break
    return {
        "report_title": _text(row.get("report_name")),
        "categories": [
            _text(value) for value in artifact.get("categories") or [] if _text(value)
        ],
        "summary": {
            "tldr": _text(summary_map.get("tldr"))[:1200],
            "executive_summary": _text(summary_map.get("executive_summary"))[:1800],
        },
        "topics": topics,
    }


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


def _load_review_inputs(
    *, result_path: Path, source_manifest_path: Path, cohort: str
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    result = _load_json(result_path)
    source_manifest = _load_json(source_manifest_path)
    source_records = _explicit_source_records(source_manifest)
    rows: list[dict[str, Any]] = []
    for raw_row in result.get("claims") or []:
        if not isinstance(raw_row, Mapping):
            continue
        if raw_row.get("evaluation_set") != "real_shortlisted":
            continue
        row = dict(raw_row)
        row["cohort"] = cohort
        rows.append(row)

    real_set = result.get("real_shortlisted_set")
    unavailable = real_set.get("unavailable") if isinstance(real_set, Mapping) else []
    for raw_row in unavailable or []:
        if not isinstance(raw_row, Mapping):
            continue
        row = dict(raw_row)
        row["cohort"] = cohort
        row["report_name"] = row.get("report")
        row["final_claim"] = ""
        row["original_claim"] = ""
        row["outcome"] = "unavailable"
        rows.append(row)
    return result, source_records, rows


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
    return {
        "selected_or_unavailable_count": len(records),
        "review_invoked_count": sum(
            bool(record.get("review_invoked")) for record in records
        ),
        "decision_counts": dict(sorted(decisions.items())),
        "material_defect_count": sum(
            any(
                isinstance(defect, Mapping) and defect.get("severity") == "material"
                for defect in record.get("defects") or []
            )
            for record in records
        ),
        "source_pages_cited": sorted(
            {
                page
                for record in records
                for page in record.get("supporting_physical_pages") or []
                if type(page) is int
            }
        ),
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
        ]
    ] = []
    for cohort, result_path, source_path in inputs:
        result, sources, rows = _load_review_inputs(
            result_path=result_path,
            source_manifest_path=source_path,
            cohort=cohort,
        )
        loaded.append((cohort, result_path, source_path, result, sources, rows))

    review_root = output_path.parent
    review_root.mkdir(parents=True, exist_ok=True)
    run_id = f"verified-claims-step2-editorial-review-{int(time.time())}"
    ctx = RunContext(
        schema_version="1.0",
        run_id=run_id,
        task_id=run_id,
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

    all_report_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for cohort, _result_path, _source_path, _result, source_records, rows in loaded:
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
            if _text(row.get("outcome")) == "unavailable":
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
                            task_id=f"{run_id}:{cohort}:{report}:{index}",
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
        for cohort, result_path, source_path, _result, _sources, _rows in loaded
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
        "summary": {
            "selected_claim_count": len(records),
            "review_invoked_count": sum(
                bool(record.get("review_invoked")) for record in records
            ),
            "decision_counts": dict(
                sorted(
                    Counter(str(record.get("decision")) for record in records).items()
                )
            ),
            "material_defect_count": sum(
                any(
                    isinstance(defect, Mapping) and defect.get("severity") == "material"
                    for defect in record.get("defects") or []
                )
                for record in records
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
