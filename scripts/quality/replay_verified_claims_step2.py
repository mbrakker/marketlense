"""Provider-free coverage replay for Verified Claims Step 2 shadow mode."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pymupdf as fitz

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
    args = parser.parse_args()
    report = replay_frozen_step2(provider_free=bool(args.provider_free))
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
