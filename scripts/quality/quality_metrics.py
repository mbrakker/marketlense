from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "src" / "schemas"
EXPECTED_PACKS = (
    "doc_map",
    "scope",
    "methods",
    "findings",
    "limitations",
    "quote_candidates",
    "artifacts",
    "validation",
)
PACK_SCHEMA_MAP = {
    "doc_map": "doc_map",
    "scope": "scope_pack",
    "methods": "methods_pack",
    "findings": "findings_pack",
    "limitations": "limitations_pack",
    "quote_candidates": "quote_candidates_pack",
    "artifacts": "artifacts",
    "validation": "validation_report",
    "key_metrics": "key_metrics_pack",
    "risk_register": "risk_register_pack",
    "recommendations": "recommendations_pack",
    "contradictions": "contradictions_pack",
}


@dataclass(frozen=True)
class CoverageSlice:
    name: str
    lines_valid: int
    lines_covered: int

    @property
    def percent(self) -> float:
        if self.lines_valid <= 0:
            return 0.0
        return (self.lines_covered / self.lines_valid) * 100.0


def _schema_validator(name: str) -> Draft202012Validator:
    path = SCHEMA_ROOT / f"{name}.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _collect_package_slice(
    root: ET.Element, package_name: str, prefixes: tuple[str, ...]
) -> CoverageSlice:
    lines_valid = 0
    lines_covered = 0
    normalized_prefixes = tuple(
        prefix.replace("\\", "/").rstrip("/") + "/" for prefix in prefixes
    )
    for class_node in root.findall(".//class"):
        filename = (class_node.attrib.get("filename") or "").replace("\\", "/")
        if not any(filename.startswith(prefix) for prefix in normalized_prefixes):
            continue
        line_nodes = class_node.findall("./lines/line")
        lines_valid += len(line_nodes)
        lines_covered += sum(
            1 for line in line_nodes if int(line.attrib.get("hits", "0")) > 0
        )
    return CoverageSlice(
        name=package_name, lines_valid=lines_valid, lines_covered=lines_covered
    )


def _collect_global_slice(root: ET.Element) -> CoverageSlice:
    lines_valid = int(root.attrib.get("lines-valid", "0"))
    lines_covered = int(root.attrib.get("lines-covered", "0"))
    return CoverageSlice(
        name="global", lines_valid=lines_valid, lines_covered=lines_covered
    )


def load_coverage_metrics(coverage_xml_path: str) -> dict[str, float]:
    root = ET.parse(coverage_xml_path).getroot()
    slices = [
        _collect_global_slice(root),
        _collect_package_slice(
            root, "src/orchestrators", ("src/orchestrators", "orchestrators")
        ),
        _collect_package_slice(
            root, "src/generators", ("src/generators", "generators")
        ),
        _collect_package_slice(root, "src/services", ("src/services", "services")),
    ]
    return {item.name: round(item.percent, 4) for item in slices}


def load_mutation_metrics(mutation_json_path: str) -> dict[str, dict[str, float]]:
    payload = json.loads(Path(mutation_json_path).read_text(encoding="utf-8"))
    targets = payload.get("targets") or []
    result: dict[str, dict[str, float]] = {}
    for target in targets:
        if not isinstance(target, dict):
            continue
        module = str(target.get("module") or "").strip()
        if not module:
            continue
        score = float(target.get("score") or 0.0)
        min_score = float(target.get("min_score") or 0.0)
        result[module] = {
            "score": round(score, 4),
            "min_score": round(min_score, 4),
            "killed": float(target.get("killed") or 0.0),
            "total": float(target.get("total") or 0.0),
        }
    return result


def _is_non_empty(pack_name: str, payload: dict[str, Any]) -> bool:
    if pack_name == "doc_map":
        return bool(
            str(payload.get("title") or "").strip()
            or str(payload.get("summary") or "").strip()
            or isinstance(payload.get("sections"), list)
            and len(payload.get("sections") or []) > 0
        )
    if pack_name == "scope":
        scope = payload.get("scope")
        if isinstance(scope, str):
            return bool(scope.strip())
        return isinstance(scope, dict) and len(scope) > 0
    if pack_name in {"methods", "findings", "limitations", "quote_candidates"}:
        value = payload.get(pack_name)
        return isinstance(value, list) and len(value) > 0
    if pack_name == "artifacts":
        insights_final = payload.get("insights_final")
        summary = payload.get("summary")
        return (
            isinstance(insights_final, list)
            and len(insights_final) > 0
            or isinstance(summary, dict)
            and bool(str(summary.get("tldr") or "").strip())
        )
    if pack_name == "validation":
        issues = payload.get("issues")
        status = str(payload.get("status") or "").strip()
        return bool(status) or isinstance(issues, list)
    return bool(payload)


def _extract_evidence_ids(pack_payloads: dict[str, dict[str, Any]]) -> set[str]:
    evidence_ids: set[str] = set()
    doc_map = pack_payloads.get("doc_map") or {}
    for section in doc_map.get("sections") or []:
        if isinstance(section, dict):
            section_id = str(section.get("id") or "").strip()
            if section_id:
                evidence_ids.add(section_id)
    findings = pack_payloads.get("findings") or {}
    for finding in findings.get("findings") or []:
        if isinstance(finding, dict):
            finding_id = str(finding.get("id") or "").strip()
            if finding_id:
                evidence_ids.add(finding_id)
    quotes = pack_payloads.get("quote_candidates") or {}
    for quote in quotes.get("quote_candidates") or []:
        if isinstance(quote, dict):
            quote_id = str(quote.get("id") or "").strip()
            if quote_id:
                evidence_ids.add(quote_id)
    return evidence_ids


def _artifact_reference_ok(
    evidence_ids: set[str], artifacts_payload: dict[str, Any]
) -> bool:
    refs: list[str] = []
    summary = artifacts_payload.get("summary")
    if isinstance(summary, dict):
        for claim in summary.get("claim_evidence_map") or []:
            if isinstance(claim, dict):
                refs.append(str(claim.get("evidence_id") or "").strip())
    for key in ("insights_candidates", "insights_final", "quotes_final"):
        for item in artifacts_payload.get(key) or []:
            if isinstance(item, dict):
                refs.append(str(item.get("evidence_id") or "").strip())
    filtered = [ref for ref in refs if ref]
    if not filtered:
        return True
    return all(ref in evidence_ids for ref in filtered)


def collect_docpack_metrics(docpack_root: str) -> dict[str, Any]:
    root = Path(docpack_root)
    report_analysis_dirs = sorted(root.glob("*/report_analysis"))
    report_count = len(report_analysis_dirs)
    validators: dict[str, Draft202012Validator] = {
        pack: _schema_validator(schema_name)
        for pack, schema_name in PACK_SCHEMA_MAP.items()
        if (SCHEMA_ROOT / f"{schema_name}.schema.json").exists()
    }

    pack_present = 0
    pack_total = 0
    pack_non_empty = 0
    schema_valid = 0
    schema_total = 0
    evidence_ref_pass = 0
    evidence_ref_total = 0
    per_pack: dict[str, dict[str, int]] = {
        name: {"present": 0, "non_empty": 0, "schema_valid": 0, "schema_total": 0}
        for name in EXPECTED_PACKS
    }

    for report_dir in report_analysis_dirs:
        pack_payloads: dict[str, dict[str, Any]] = {}
        for pack_name in EXPECTED_PACKS:
            pack_total += 1
            payload_path = report_dir / f"{pack_name}.json"
            if not payload_path.exists():
                continue
            pack_present += 1
            per_pack[pack_name]["present"] += 1
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            pack_payloads[pack_name] = payload
            if _is_non_empty(pack_name, payload):
                pack_non_empty += 1
                per_pack[pack_name]["non_empty"] += 1
            validator = validators.get(pack_name)
            if validator:
                schema_total += 1
                per_pack[pack_name]["schema_total"] += 1
                errors = list(validator.iter_errors(payload))
                if not errors:
                    schema_valid += 1
                    per_pack[pack_name]["schema_valid"] += 1

        artifacts_payload = pack_payloads.get("artifacts")
        if artifacts_payload is not None:
            evidence_ref_total += 1
            evidence_ids = _extract_evidence_ids(pack_payloads)
            if _artifact_reference_ok(evidence_ids, artifacts_payload):
                evidence_ref_pass += 1

    def _rate(num: int, den: int) -> float:
        if den <= 0:
            return 1.0
        return round(num / den, 6)

    pack_stats: dict[str, dict[str, float]] = {}
    for pack_name, counters in per_pack.items():
        present = counters["present"]
        schema_total_pack = counters["schema_total"]
        pack_stats[pack_name] = {
            "present": present,
            "present_rate": _rate(present, report_count),
            "non_empty": counters["non_empty"],
            "non_empty_rate": _rate(counters["non_empty"], max(1, present)),
            "schema_valid": counters["schema_valid"],
            "schema_valid_rate": _rate(counters["schema_valid"], schema_total_pack),
        }

    return {
        "report_count": report_count,
        "expected_packs": list(EXPECTED_PACKS),
        "pack_presence_rate": _rate(pack_present, pack_total),
        "pack_non_empty_rate": _rate(pack_non_empty, max(1, pack_present)),
        "schema_valid_rate": _rate(schema_valid, schema_total),
        "evidence_reference_integrity_rate": _rate(
            evidence_ref_pass, evidence_ref_total
        ),
        "packs": pack_stats,
    }


def _candidate_bbox_valid(candidate: dict[str, Any]) -> bool:
    bbox = candidate.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    try:
        x0 = float(bbox[0])
        y0 = float(bbox[1])
        x1 = float(bbox[2])
        y1 = float(bbox[3])
    except (TypeError, ValueError):
        return False
    return x1 > x0 and y1 > y0


def collect_candidate_pack_metrics(candidate_root: str) -> dict[str, Any]:
    root = Path(candidate_root)
    candidate_paths = sorted(root.glob("*/candidates/candidates.json"))
    report_count = len(candidate_paths)
    non_empty_reports = 0
    total_candidates = 0
    total_charts = 0
    total_tables = 0
    bbox_valid = 0
    crop_paths_present = 0
    preview_text_present = 0

    for candidate_path in candidate_paths:
        try:
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        candidates_value = payload.get("candidates")
        candidates = candidates_value if isinstance(candidates_value, list) else []
        if candidates:
            non_empty_reports += 1
        total_candidates += len(candidates)
        chart_count = payload.get("chart_count")
        table_count = payload.get("table_count")
        if chart_count is None:
            chart_count = sum(
                1
                for candidate in candidates
                if isinstance(candidate, dict) and str(candidate.get("kind") or "") == "chart"
            )
        if table_count is None:
            table_count = sum(
                1
                for candidate in candidates
                if isinstance(candidate, dict) and str(candidate.get("kind") or "") == "table"
            )
        total_charts += int(chart_count or 0)
        total_tables += int(table_count or 0)
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if _candidate_bbox_valid(candidate):
                bbox_valid += 1
            if str(candidate.get("crop_path") or "").strip():
                crop_paths_present += 1
            if str(candidate.get("preview_text") or "").strip():
                preview_text_present += 1

    def _rate(num: int, den: int) -> float:
        if den <= 0:
            return 1.0
        return round(num / den, 6)

    def _mean(total: int, den: int) -> float:
        if den <= 0:
            return 0.0
        return round(total / den, 6)

    return {
        "report_count": report_count,
        "pack_non_empty_rate": _rate(non_empty_reports, report_count),
        "candidate_count_mean": _mean(total_candidates, report_count),
        "chart_count_mean": _mean(total_charts, report_count),
        "table_count_mean": _mean(total_tables, report_count),
        "bbox_valid_rate": _rate(bbox_valid, total_candidates),
        "crop_path_coverage_rate": _rate(crop_paths_present, total_candidates),
        "preview_text_rate": _rate(preview_text_present, total_candidates),
    }
