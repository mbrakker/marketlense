from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from src.contracts.context_category_fit import (
    ReportCategoryContext,
    ReportContextBuildRequest,
    ReportContextSection,
)
from src.contracts.files import ReadTextRequest
from src.contracts.semantic_ids import ReportId
from src.services import file_service
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.report_context_generator")


def build_report_category_context(
    request: ReportContextBuildRequest,
    ctx,
    *,
    file_client=file_service,
) -> ReportCategoryContext:
    report = request.report
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="report_context_build_start",
            module=logger.name,
            fields={
                "report_id": report.file_id,
                "title": report.title,
                "publisher": report.publisher or "",
                "region": report.region or "",
                "time_period": report.time_period or "",
                "evidence_pack_count": len(report.evidence_pack_paths or {}),
            },
        )
    )
    doc_map = _load_json_pack(report.evidence_pack_paths, "doc_map", file_client, ctx)
    scope = _load_json_pack(report.evidence_pack_paths, "scope", file_client, ctx)
    methods = _load_json_pack(report.evidence_pack_paths, "methods", file_client, ctx)
    findings = _load_json_pack(report.evidence_pack_paths, "findings", file_client, ctx)
    limitations = _load_json_pack(
        report.evidence_pack_paths, "limitations", file_client, ctx
    )
    context = ReportCategoryContext(
        schema_version="1.0",
        report_id=ReportId(report.file_id),
        title=report.title,
        publisher=str(report.publisher or "").strip(),
        region=str(report.region or "").strip(),
        time_period=str(report.time_period or "").strip(),
        overview=_build_overview(doc_map, scope),
        methods=_coerce_method_points(methods, limit=request.max_methods),
        key_findings=_coerce_findings(findings, limit=request.max_findings),
        limitations=_coerce_limitations(limitations, limit=request.max_limitations),
        sections=_coerce_sections(doc_map, findings, limit=request.max_sections),
    )
    if not context.overview and not context.sections and not context.key_findings:
        raise AppError(
            code="report_context_empty",
            message=f"No usable evidence context found for report '{report.file_id}'",
            retryable=False,
            context={"report_id": report.file_id, "title": report.title},
        )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="report_context_build_complete",
            module=logger.name,
            fields={
                "report_id": context.report_id,
                "overview_length": len(context.overview),
                "method_count": len(context.methods),
                "finding_count": len(context.key_findings),
                "limitation_count": len(context.limitations),
                "section_count": len(context.sections),
            },
        )
    )
    return context


def _load_json_pack(
    evidence_pack_paths: Dict[str, str],
    pack_name: str,
    file_client,
    ctx,
) -> Any:
    path = str((evidence_pack_paths or {}).get(pack_name) or "").strip()
    if not path:
        return {}
    pack_ctx = child_context(ctx, task_id=f"{ctx.task_id}:{pack_name}")
    response = file_client.read_text(
        ReadTextRequest(schema_version="1.0", path=path),
        pack_ctx,
    )
    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="report_context_pack_invalid_json",
            message=f"Evidence pack '{pack_name}' is not valid JSON",
            cause=exc,
            retryable=False,
            context={"pack_name": pack_name, "path": path},
        ) from exc
    logger.info(
        log_event(
            pack_ctx,
            role="generator",
            event="report_context_pack_loaded",
            module=logger.name,
            fields={
                "pack_name": pack_name,
                "path": path,
                "payload_type": type(payload).__name__,
            },
        )
    )
    return payload


def _build_overview(doc_map: Any, scope: Any) -> str:
    parts: List[str] = []
    if isinstance(doc_map, dict):
        summary = _clean_text(doc_map.get("summary"))
        title = _clean_text(doc_map.get("title"))
        publisher = _clean_text(doc_map.get("publisher"))
        if title:
            title_piece = title
            if publisher:
                title_piece = f"{title_piece} by {publisher}"
            parts.append(title_piece)
        if summary:
            parts.append(summary)
    if isinstance(scope, dict):
        scope_value = _clean_text(scope.get("scope"))
        if scope_value:
            parts.append(scope_value)
    return _join_unique(parts, limit=1800)


def _coerce_method_points(methods: Any, *, limit: int) -> List[str]:
    if not isinstance(methods, dict):
        return []
    return _clean_text_list(methods.get("methods"), limit=limit, item_limit=320)


def _coerce_limitations(limitations: Any, *, limit: int) -> List[str]:
    if not isinstance(limitations, dict):
        return []
    return _clean_text_list(
        limitations.get("limitations"),
        limit=limit,
        item_limit=260,
    )


def _coerce_findings(findings: Any, *, limit: int) -> List[str]:
    if not isinstance(findings, dict):
        return []
    results: List[str] = []
    for item in findings.get("findings") or []:
        if len(results) >= limit:
            break
        if isinstance(item, dict):
            text = _clean_text(item.get("text"), limit=260)
            if text:
                results.append(text)
        elif isinstance(item, str):
            text = _clean_text(item, limit=260)
            if text:
                results.append(text)
    return _dedupe_preserve_order(results)


def _coerce_sections(doc_map: Any, findings: Any, *, limit: int) -> List[ReportContextSection]:
    sections: List[ReportContextSection] = []
    if isinstance(doc_map, dict):
        for section in doc_map.get("sections") or []:
            if len(sections) >= limit:
                break
            if not isinstance(section, dict):
                continue
            label = _clean_text(section.get("title"), limit=120) or _clean_text(
                section.get("id"), limit=120
            )
            if not label:
                continue
            summary = _clean_text(section.get("summary"), limit=260)
            key_points = _clean_text_list(
                section.get("key_points"), limit=3, item_limit=200
            )
            if not summary and not key_points:
                continue
            sections.append(
                ReportContextSection(
                    schema_version="1.0",
                    section_label=label,
                    source_pack="doc_map",
                    summary=summary or _join_unique(key_points, limit=260),
                    key_points=key_points,
                )
            )
    findings_bucket: List[str] = _coerce_findings(findings, limit=max(0, limit - len(sections)))
    for idx, text in enumerate(findings_bucket, start=1):
        sections.append(
            ReportContextSection(
                schema_version="1.0",
                section_label=f"Key finding {idx}",
                source_pack="findings",
                summary=text,
                key_points=[],
            )
        )
        if len(sections) >= limit:
            break
    return sections


def _clean_text(value: Any, *, limit: int = 0) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    if not text:
        return ""
    if limit > 0 and len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _clean_text_list(values: Any, *, limit: int, item_limit: int) -> List[str]:
    if not isinstance(values, list):
        return []
    results: List[str] = []
    for value in values:
        if len(results) >= limit:
            break
        text = _clean_text(value, limit=item_limit)
        if text:
            results.append(text)
    return _dedupe_preserve_order(results)


def _join_unique(values: List[str], *, limit: int) -> str:
    joined = " ".join(_dedupe_preserve_order([_clean_text(value) for value in values if _clean_text(value)]))
    if limit > 0 and len(joined) > limit:
        return joined[: limit - 3].rstrip() + "..."
    return joined


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    results: List[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(value)
    return results
