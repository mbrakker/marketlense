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
from typing import Any

import pymupdf as fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.contracts.verified_claims import (
    VERIFIED_CLAIMS_VISUAL_SCHEMA_VERSION,
    VisualClaimEvaluationRequest,
)
from src.generators.artifact_normalization import bind_artifact_evidence_spans
from src.generators.verified_claims_visual_generator import (
    evaluate_shortlisted_claims,
)
from src.services.config_service import load_settings

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


def _retained_claims(
    reference: dict[str, Any], report: str
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load the exact retained Step 1 shortlist without fabricating fixtures."""

    artifact_path = _retained_artifact_path(reference, report)
    if not artifact_path.is_file():
        return [], {}, [
            {
                "report": report,
                "reason": "retained_artifacts_unavailable",
                "path": str(artifact_path),
            }
        ]
    artifact = _load_json(artifact_path)
    insights = artifact.get("insights_final")
    if not isinstance(insights, list):
        return [], {}, [
            {
                "report": report,
                "reason": "retained_insights_final_missing",
                "path": str(artifact_path),
            }
        ]

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
        claims.append(claim)
        metadata[candidate_id] = {
            "evaluation_set": "real_shortlisted",
            "report": report,
            "source_pages": physical_pages,
            "retained_artifact_path": str(artifact_path.relative_to(REPOSITORY_ROOT)),
        }
    doc_map_path = artifact_path.parent / "doc_map.json"
    findings_path = artifact_path.parent / "findings.json"
    fidelity_path = artifact_path.parent / "evidence_fidelity.json"
    doc_map = _load_json(doc_map_path) if doc_map_path.is_file() else {}
    evidence_packs: dict[str, Any] = {}
    if findings_path.is_file():
        evidence_packs["findings"] = _load_json(findings_path)
    if fidelity_path.is_file():
        evidence_packs["evidence_fidelity"] = _load_json(fidelity_path)
    before_bindings = {
        str(claim.get("candidate_id")): {
            "evidence_id": str(claim.get("evidence_id") or ""),
            "pages": list(claim.get("pages") or []),
        }
        for claim in claims
    }
    if isinstance(doc_map, dict) and evidence_packs:
        bind_artifact_evidence_spans(
            summary={},
            insights_candidates=[],
            insights_final=claims,
            quotes_final=[],
            doc_map=doc_map,
            evidence_packs=evidence_packs,
        )
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
        }
        metadata[candidate_id]["source_binding_before"] = before_bindings.get(
            candidate_id, {}
        )
        metadata[candidate_id]["source_binding_after"] = after_binding
        metadata[candidate_id]["source_binding_resolution"] = (
            "direct_finding_rebound"
            if before_bindings.get(candidate_id, {}).get("evidence_id")
            != after_binding["evidence_id"]
            else (
                "unresolved_doc_map_binding"
                if after_binding["source_packs"] == ["doc_map"]
                else "retained"
            )
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
            source_pages.get("physical_pdf")
            if isinstance(source_pages, dict)
            else []
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


def _usage_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "provider_calls": 0,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "estimated_cost_usd": None,
        }
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)

    def _sum_field(field: str) -> int | float | None:
        values = [row.get(field) for row in rows if row.get(field) is not None]
        return sum(values) if values else None

    return {
        "provider_calls": len(rows),
        "input_tokens": _sum_field("input_tokens"),
        "output_tokens": _sum_field("output_tokens"),
        "total_tokens": _sum_field("total_tokens"),
        "estimated_cost_usd": _sum_field("estimated_cost_usd"),
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
        "unresolved": sum(
            row.get("outcome") == "unresolved" for row in selected_rows
        ),
        "skipped": sum(row.get("outcome") == "skipped" for row in selected_rows),
    }


def replay_live_step2(*, output_root: Path | None = None) -> dict[str, Any]:
    """Run the bounded live visual evaluation against retained local inputs."""

    reference = _load_json(REFERENCE_PATH)
    root = output_root or (REPOSITORY_ROOT / "out" / "verified_claims_step2_live")
    root.mkdir(parents=True, exist_ok=True)
    context = RunContext(
        schema_version="1.0",
        run_id="verified-claims-step2-live",
        task_id="verified-claims-step2-live",
        span_id="verified-claims-step2-live",
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
    for report in REPORT_ORDER:
        reference_claims, reference_metadata = _reference_claims(reference, report)
        retained_claims, retained_metadata, unavailable = _retained_claims(
            reference, report
        )
        retained_input_count += len(retained_claims)
        retained_unavailable.extend(unavailable)
        claims = reference_claims + retained_claims
        metadata = {**reference_metadata, **retained_metadata}
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
        )
        report_context = RunContext(
            schema_version="1.0",
            run_id="verified-claims-step2-live",
            task_id=f"verified-claims-step2-live:{_safe_report_name(report)}",
            span_id=f"verified-claims-step2-live:{_safe_report_name(report)}",
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
                }
            )
            rows.append(result_payload)

    usage = _usage_summary(root / "cost-ledger.jsonl")
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
        "reports": REPORT_ORDER,
        "reference_set": {"case_count": 15, "candidate_variant_count": 39},
        "input_claim_count": len(rows),
        "real_shortlisted_set": {
            "input_claim_count": retained_input_count,
            "expected_claim_count": 29,
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
