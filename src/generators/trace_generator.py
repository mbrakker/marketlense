from __future__ import annotations

from datetime import datetime
from typing import Any

from src.contracts.tracing import (
    TraceBuildRequest,
    TraceBuildResult,
    TraceDiagnostic,
    TraceSpanSummary,
    TraceWorkflowStageSummary,
)
from src.contracts.logging import REQUIRED_LOG_EVENT_FIELDS


_EMPTY_ALLOWED_REQUIRED_FIELDS = {"parent_span_id"}
_WORKFLOW_MARKERS = {
    "report": ("report_generation", "report_render", "report_generate"),
    "publish": ("publish_", "publish:", "wordpress"),
    "cross_report": ("cross_report",),
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_timestamp(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _duration_ms(start: str, end: str) -> float:
    start_dt = _parse_timestamp(start)
    end_dt = _parse_timestamp(end)
    if start_dt is None or end_dt is None:
        return 0.0
    return max(0.0, (end_dt - start_dt).total_seconds() * 1000.0)


def _event_matches(request: TraceBuildRequest, event: dict[str, Any]) -> bool:
    if request.trace_id and _text(event.get("trace_id")) != request.trace_id:
        return False
    if request.run_id and _text(event.get("run_id")) != request.run_id:
        return False
    if request.task_id and _text(event.get("task_id")) != request.task_id:
        return False
    if not _text(event.get("span_id")):
        return False
    return True


def _event_matches_filters(request: TraceBuildRequest, event: dict[str, Any]) -> bool:
    if request.trace_id and _text(event.get("trace_id")) != request.trace_id:
        return False
    if request.run_id and _text(event.get("run_id")) != request.run_id:
        return False
    if request.task_id and _text(event.get("task_id")) != request.task_id:
        return False
    return True


def _span_sort_key(span: TraceSpanSummary) -> tuple[str, str]:
    return (span.start_utc, span.span_id)


def _required_field_diagnostics(
    events: list[dict[str, Any]],
) -> list[TraceDiagnostic]:
    diagnostics: list[TraceDiagnostic] = []
    for event_index, event in enumerate(events):
        for field_name in sorted(REQUIRED_LOG_EVENT_FIELDS):
            if field_name not in event:
                diagnostics.append(
                    TraceDiagnostic(
                        schema_version="1.0",
                        code="trace_event_missing_required_field",
                        severity="error",
                        message=f"Trace event is missing required field: {field_name}",
                        span_id=_text(event.get("span_id")),
                        event_index=event_index,
                        field_name=field_name,
                    )
                )
                continue
            if field_name in _EMPTY_ALLOWED_REQUIRED_FIELDS:
                continue
            if not _text(event.get(field_name)):
                diagnostics.append(
                    TraceDiagnostic(
                        schema_version="1.0",
                        code="trace_event_empty_required_field",
                        severity="error",
                        message=f"Trace event has empty required field: {field_name}",
                        span_id=_text(event.get("span_id")),
                        event_index=event_index,
                        field_name=field_name,
                    )
                )
    return diagnostics


def _parent_link_diagnostics(
    filtered_events: list[dict[str, Any]],
    span_ids: set[str],
) -> list[TraceDiagnostic]:
    diagnostics: list[TraceDiagnostic] = []
    seen_orphans: set[tuple[str, str]] = set()
    for event_index, event in enumerate(filtered_events):
        span_id = _text(event.get("span_id"))
        parent_span_id = _text(event.get("parent_span_id"))
        if not span_id or not parent_span_id or parent_span_id in span_ids:
            continue
        key = (span_id, parent_span_id)
        if key in seen_orphans:
            continue
        seen_orphans.add(key)
        diagnostics.append(
            TraceDiagnostic(
                schema_version="1.0",
                code="trace_orphan_span",
                severity="error",
                message=f"Trace span references missing parent span: {parent_span_id}",
                span_id=span_id,
                event_index=event_index,
                field_name="parent_span_id",
                parent_span_id=parent_span_id,
            )
        )
    return diagnostics


def _workflow_names_for_event(event: dict[str, Any]) -> set[str]:
    haystack = " ".join(
        [
            _text(event.get("module")),
            _text(event.get("event")),
            _text(event.get("span_name")),
            _text(event.get("task_id")),
        ]
    ).lower()
    workflow_names: set[str] = set()
    for workflow_name, markers in _WORKFLOW_MARKERS.items():
        if any(marker in haystack for marker in markers):
            workflow_names.add(workflow_name)
    return workflow_names


def _workflow_names_for_span(
    span: TraceSpanSummary,
    spans_by_id: dict[str, TraceSpanSummary],
    span_details: dict[str, dict[str, Any]],
    memo: dict[str, set[str]],
) -> set[str]:
    if span.span_id in memo:
        return memo[span.span_id]
    workflow_names = set(span_details.get(span.span_id, {}).get("workflow_names", set()))
    if span.parent_span_id and span.parent_span_id in spans_by_id:
        workflow_names.update(
            _workflow_names_for_span(
                spans_by_id[span.parent_span_id],
                spans_by_id,
                span_details,
                memo,
            )
        )
    memo[span.span_id] = workflow_names
    return workflow_names


def _build_workflow_stage_summaries(
    summaries: list[TraceSpanSummary],
    span_details: dict[str, dict[str, Any]],
) -> list[TraceWorkflowStageSummary]:
    spans_by_id = {span.span_id: span for span in summaries}
    workflow_names_by_span: dict[str, set[str]] = {}
    for span in summaries:
        workflow_names_by_span[span.span_id] = _workflow_names_for_span(
            span,
            spans_by_id,
            span_details,
            workflow_names_by_span,
        )

    stages: list[TraceWorkflowStageSummary] = []
    for workflow_name in sorted(_WORKFLOW_MARKERS):
        workflow_spans = [
            span
            for span in summaries
            if workflow_name in workflow_names_by_span.get(span.span_id, set())
        ]
        if not workflow_spans:
            continue
        roles_seen = sorted(
            {
                role
                for span in workflow_spans
                for role in span_details.get(span.span_id, {}).get("roles_seen", set())
                if role
            }
        )
        modules_seen = {
            module
            for span in workflow_spans
            for module in span_details.get(span.span_id, {}).get("modules_seen", set())
            if module
        }
        event_count = sum(
            int(span_details.get(span.span_id, {}).get("event_count", 0) or 0)
            for span in workflow_spans
        )
        has_orchestrator = "orchestrator" in roles_seen
        has_generator = "generator" in roles_seen
        has_service = "service" in roles_seen
        stages.append(
            TraceWorkflowStageSummary(
                schema_version="1.0",
                workflow_name=workflow_name,
                span_ids=[span.span_id for span in workflow_spans],
                roles_seen=roles_seen,
                module_count=len(modules_seen),
                event_count=event_count,
                has_orchestrator=has_orchestrator,
                has_generator=has_generator,
                has_service=has_service,
                complete=has_orchestrator and has_generator and has_service,
            )
        )
    return stages


def build_trace_summary(request: TraceBuildRequest) -> TraceBuildResult:
    scoped_events = [
        event
        for event in request.events
        if isinstance(event, dict) and _event_matches_filters(request, event)
    ]
    filtered_events = [
        event
        for event in scoped_events
        if isinstance(event, dict) and _event_matches(request, event)
    ]
    diagnostics = _required_field_diagnostics(scoped_events)
    spans_by_id: dict[str, dict[str, Any]] = {}
    for event in filtered_events:
        span_id = _text(event.get("span_id"))
        timestamp = _text(event.get("timestamp_utc"))
        current = spans_by_id.setdefault(
            span_id,
            {
                "trace_id": _text(event.get("trace_id")),
                "span_id": span_id,
                "parent_span_id": _text(event.get("parent_span_id")),
                "span_name": _text(event.get("span_name"))
                or _text(event.get("task_id")),
                "span_depth": int(event.get("span_depth") or 0),
                "task_id": _text(event.get("task_id")),
                "role": _text(event.get("role")),
                "module": _text(event.get("module")),
                "roles_seen": set(),
                "modules_seen": set(),
                "workflow_names": set(),
                "event_count": 0,
                "start_utc": timestamp,
                "end_utc": timestamp,
            },
        )
        current["event_count"] = int(current["event_count"]) + 1
        current["roles_seen"].add(_text(event.get("role")))
        current["modules_seen"].add(_text(event.get("module")))
        current["workflow_names"].update(_workflow_names_for_event(event))
        current["role"] = _text(event.get("role")) or current["role"]
        current["module"] = _text(event.get("module")) or current["module"]
        if timestamp and (
            not current["start_utc"] or timestamp < str(current["start_utc"])
        ):
            current["start_utc"] = timestamp
        if timestamp and timestamp > str(current["end_utc"]):
            current["end_utc"] = timestamp

    child_ids_by_parent: dict[str, list[str]] = {}
    for span_id, span in spans_by_id.items():
        parent_span_id = _text(span.get("parent_span_id"))
        if parent_span_id:
            child_ids_by_parent.setdefault(parent_span_id, []).append(span_id)

    summaries: list[TraceSpanSummary] = []
    for span in spans_by_id.values():
        start_utc = _text(span.get("start_utc"))
        end_utc = _text(span.get("end_utc"))
        child_span_ids = sorted(
            child_ids_by_parent.get(_text(span.get("span_id")), []),
            key=lambda child_id: (
                _text(spans_by_id.get(child_id, {}).get("start_utc")),
                child_id,
            ),
        )
        summaries.append(
            TraceSpanSummary(
                schema_version="1.0",
                trace_id=_text(span.get("trace_id")),
                span_id=_text(span.get("span_id")),
                parent_span_id=_text(span.get("parent_span_id")),
                span_name=_text(span.get("span_name")),
                span_depth=int(span.get("span_depth") or 0),
                task_id=_text(span.get("task_id")),
                role=_text(span.get("role")),
                module=_text(span.get("module")),
                event_count=int(span.get("event_count") or 0),
                start_utc=start_utc,
                end_utc=end_utc,
                duration_ms=_duration_ms(start_utc, end_utc),
                child_span_ids=child_span_ids,
            )
        )

    summaries = sorted(summaries, key=_span_sort_key)
    span_ids = {span.span_id for span in summaries}
    diagnostics.extend(_parent_link_diagnostics(filtered_events, span_ids))
    root_span_ids = [
        span.span_id
        for span in summaries
        if not span.parent_span_id
    ]
    resolved_trace_id = request.trace_id or (
        summaries[0].trace_id if summaries else ""
    )
    resolved_run_id = request.run_id or (
        _text(filtered_events[0].get("run_id")) if filtered_events else ""
    )
    return TraceBuildResult(
        schema_version="1.0",
        trace_id=resolved_trace_id,
        run_id=resolved_run_id,
        task_id=request.task_id,
        event_count=len(filtered_events),
        span_count=len(summaries),
        root_span_ids=root_span_ids,
        spans=summaries,
        diagnostics=diagnostics,
        diagnostic_count=len(diagnostics),
        valid=not diagnostics,
        workflow_stages=_build_workflow_stage_summaries(summaries, spans_by_id),
    )
