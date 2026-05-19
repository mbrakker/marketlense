from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserRoutePlaybookSelection,
)
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.services._browser_report_download.request import (
    resolve_effective_identity_fields,
)
from src.services import prompt_service
from src.utils.logging import REDACTED, log_event
from src.utils.browser_route_playbooks import serialize_selected_playbooks_for_prompt

logger = logging.getLogger("market_lense.browser_report_download_service")

PROMPT_NAMESPACE = "browser_report_download/browser_route"


@dataclass(frozen=True)
class BrowserDownloadPromptBundle:
    schema_version: str
    namespace: str
    system_prompt_path: str
    user_prompt_path: str
    system_prompt_sha256: str
    user_prompt_sha256: str
    rendered_system_prompt: str
    rendered_user_prompt: str
    task_prompt: str


def render_browser_report_download_prompt(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    delivery_email: str | None,
) -> BrowserDownloadPromptBundle:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=PROMPT_NAMESPACE,
        ),
        ctx,
    )
    variables = {
        "normalized_url": normalized_url,
        "execution_url": execution_url,
        "download_dir": str(download_dir),
        "identity_entries": _build_identity_entries(
            request=request,
            delivery_email=delivery_email,
        ),
        "delivery_email": str(delivery_email or "").strip(),
        "route_hint": str(request.route_hint or "").strip(),
        "route_kind_hint": str(request.route_kind_hint or "").strip(),
        "route_step_lines": _build_route_step_lines(
            route_step_hints=request.route_step_hints,
        ),
        "route_family_hint": str(request.route_family_hint or "").strip(),
        "selected_playbooks": serialize_selected_playbooks_for_prompt(
            request.selected_playbooks
        ),
        "selected_playbook_lines": _build_selected_playbook_lines(
            selected_playbooks=request.selected_playbooks,
        ),
        "publisher_discovery_route_kind": str(
            request.publisher_discovery_route_kind or ""
        ).strip(),
        "publisher_recommended_discovery_route_kind": str(
            request.publisher_recommended_discovery_route_kind or ""
        ).strip(),
        "source_page_url_hint": str(request.source_page_url_hint or "").strip(),
        "candidate_title": (
            str(request.candidate_trace.title).strip()
            if request.candidate_trace is not None
            else ""
        ),
        "candidate_canonical_url": (
            str(request.candidate_trace.canonical_url).strip()
            if request.candidate_trace is not None
            else ""
        ),
        "candidate_pdf_url": (
            str(request.candidate_trace.pdf_url or "").strip()
            if request.candidate_trace is not None
            else ""
        ),
        "candidate_source_page_urls": (
            list(request.candidate_trace.source_page_urls)
            if request.candidate_trace is not None
            else []
        ),
        "candidate_discovery_provenances": (
            list(request.candidate_trace.discovery_provenances)
            if request.candidate_trace is not None
            else []
        ),
        "candidate_max_confidence": (
            f"{request.candidate_trace.max_confidence:.3f}"
            if request.candidate_trace is not None
            and request.candidate_trace.max_confidence is not None
            else ""
        ),
    }
    rendered_system = prompt_service.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables=variables,
        ),
        ctx,
    )
    rendered_user = prompt_service.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.user,
            variables=variables,
        ),
        ctx,
    )
    task_prompt = (
        f"{rendered_system.text.strip()}\n\n{rendered_user.text.strip()}"
    ).strip()
    bundle = BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace=PROMPT_NAMESPACE,
        system_prompt_path=prompt_set.system.path,
        user_prompt_path=prompt_set.user.path,
        system_prompt_sha256=prompt_set.system.sha256,
        user_prompt_sha256=prompt_set.user.sha256,
        rendered_system_prompt=rendered_system.text,
        rendered_user_prompt=rendered_user.text,
        task_prompt=task_prompt,
    )
    log_rendered_user_prompt = redact_browser_report_download_prompt_for_log(
        request=request,
        text=bundle.rendered_user_prompt,
        delivery_email=delivery_email,
    )
    log_task_prompt = redact_browser_report_download_prompt_for_log(
        request=request,
        text=bundle.task_prompt,
        delivery_email=delivery_email,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_prompt_prepared",
            module=logger.name,
            fields={
                "prompt_namespace": bundle.namespace,
                "system_prompt_path": bundle.system_prompt_path,
                "user_prompt_path": bundle.user_prompt_path,
                "system_prompt_sha256": bundle.system_prompt_sha256,
                "user_prompt_sha256": bundle.user_prompt_sha256,
                "rendered_system_prompt": bundle.rendered_system_prompt,
                "rendered_user_prompt": log_rendered_user_prompt,
                "task_prompt": log_task_prompt,
                "model": request.settings.model,
                "temperature": request.settings.temperature,
                "timeout_seconds": request.settings.timeout_seconds,
                "max_steps": request.settings.max_steps,
                "candidate_canonical_url": (
                    request.candidate_trace.canonical_url
                    if request.candidate_trace is not None
                    else ""
                ),
                "candidate_pdf_url": (
                    request.candidate_trace.pdf_url
                    if request.candidate_trace is not None
                    and request.candidate_trace.pdf_url
                    else ""
                ),
                "candidate_source_page_urls": (
                    list(request.candidate_trace.source_page_urls)
                    if request.candidate_trace is not None
                    else []
                ),
                "candidate_discovery_provenances": (
                    list(request.candidate_trace.discovery_provenances)
                    if request.candidate_trace is not None
                    else []
                ),
                "publisher_discovery_route_kind": request.publisher_discovery_route_kind
                or "",
                "publisher_recommended_discovery_route_kind": (
                    request.publisher_recommended_discovery_route_kind or ""
                ),
                "route_family_hint": request.route_family_hint or "",
                "source_page_url_hint": request.source_page_url_hint or "",
                "selected_playbook_ids": [
                    item.playbook_id for item in request.selected_playbooks
                ],
                "prompt_variables": {
                    "identity_entries": _redact_identity_entries_for_log(
                        variables["identity_entries"]
                    ),
                    "delivery_email": (
                        REDACTED if variables["delivery_email"] else ""
                    ),
                    "route_hint": variables["route_hint"],
                    "route_kind_hint": variables["route_kind_hint"],
                    "route_step_lines": variables["route_step_lines"],
                    "route_family_hint": variables["route_family_hint"],
                    "selected_playbooks": variables["selected_playbooks"],
                    "selected_playbook_lines": variables["selected_playbook_lines"],
                    "publisher_discovery_route_kind": variables[
                        "publisher_discovery_route_kind"
                    ],
                    "publisher_recommended_discovery_route_kind": variables[
                        "publisher_recommended_discovery_route_kind"
                    ],
                    "source_page_url_hint": variables["source_page_url_hint"],
                    "candidate_title": variables["candidate_title"],
                    "candidate_canonical_url": variables["candidate_canonical_url"],
                    "candidate_pdf_url": variables["candidate_pdf_url"],
                    "candidate_source_page_urls": variables[
                        "candidate_source_page_urls"
                    ],
                    "candidate_discovery_provenances": variables[
                        "candidate_discovery_provenances"
                    ],
                    "candidate_max_confidence": variables["candidate_max_confidence"],
                },
            },
        )
    )
    return bundle


def redact_browser_report_download_prompt_for_log(
    *,
    request: BrowserReportDownloadRequest,
    text: str,
    delivery_email: str | None,
) -> str:
    redacted = str(text or "")
    values = _identity_values_for_log_redaction(
        request=request,
        delivery_email=delivery_email,
    )
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, REDACTED)
    return redacted


def _identity_values_for_log_redaction(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
) -> set[str]:
    values: set[str] = set()
    for field in resolve_effective_identity_fields(request):
        value = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            value = delivery_email.strip()
        if value:
            values.add(value)
    delivery = str(delivery_email or "").strip()
    if delivery:
        values.add(delivery)
    return values


def _redact_identity_entries_for_log(
    entries: list[dict[str, str]],
) -> list[dict[str, str]]:
    redacted_entries: list[dict[str, str]] = []
    for entry in entries:
        redacted_entry = dict(entry)
        if str(redacted_entry.get("value") or "").strip():
            redacted_entry["value"] = REDACTED
        redacted_entries.append(redacted_entry)
    return redacted_entries


def _build_identity_entries(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for field in resolve_effective_identity_fields(request):
        aliases = ", ".join(field.aliases)
        value = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            value = delivery_email.strip()
        if not value:
            continue
        entries.append(
            {
                "label": field.label,
                "aliases": aliases,
                "value": value,
            }
        )
    return entries


def _build_route_step_lines(
    *,
    route_step_hints: list[BrowserDownloadRouteStep],
) -> list[str]:
    lines: list[str] = []
    for index, step in enumerate(route_step_hints[:5], start=1):
        action = str(getattr(step, "action", "") or "").strip() or "follow"
        target = (
            str(getattr(step, "target_text", "") or "").strip()
            or str(getattr(step, "target_role", "") or "").strip()
            or str(getattr(step, "target_url", "") or "").strip()
            or "page"
        )
        result = str(getattr(step, "result", "") or "").strip()
        line = f"{index}. {action} {target}"
        if result:
            line = f"{line} -> {result}"
        lines.append(line)
    return lines


def _build_selected_playbook_lines(
    *,
    selected_playbooks: list[BrowserRoutePlaybookSelection],
) -> list[str]:
    lines: list[str] = []
    for playbook in selected_playbooks[:3]:
        lines.append(
            f"{playbook.playbook_id}@{playbook.version} "
            f"({playbook.route_family}/{playbook.route_kind}): {playbook.summary}"
        )
        for step_line in playbook.step_lines[:5]:
            lines.append(f"  - {step_line}")
        for trap_line in playbook.trap_lines[:5]:
            lines.append(f"  - Avoid: {trap_line}")
    return lines
