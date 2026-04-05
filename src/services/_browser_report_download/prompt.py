from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.run_context import RunContext
from src.services import prompt_service
from src.utils.logging import log_event

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
        "download_dir": str(download_dir),
        "identity_prompt": _render_identity_prompt(
            request=request,
            delivery_email=delivery_email,
        ),
        "route_hint_text": _render_route_hint_text(
            route_hint=request.route_hint,
            route_kind_hint=request.route_kind_hint,
        ),
        "delivery_instruction": _render_delivery_instruction(
            delivery_email=delivery_email,
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
                "rendered_user_prompt": bundle.rendered_user_prompt,
                "task_prompt": bundle.task_prompt,
                "model": request.settings.model,
                "temperature": request.settings.temperature,
                "timeout_seconds": request.settings.timeout_seconds,
                "max_steps": request.settings.max_steps,
            },
        )
    )
    return bundle


def _render_identity_prompt(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
) -> str:
    lines = [
        "Use the following configured identity values when a matching form field is available. Do not invent missing values."
    ]
    for field in request.settings.identity_profile.fields:
        aliases = ", ".join(field.aliases)
        value = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            value = delivery_email.strip()
        if not value:
            continue
        alias_text = f" (aliases: {aliases})" if aliases else ""
        lines.append(f"- {field.label}{alias_text}: {value}")
    if len(lines) == 1:
        lines.append("- No non-empty identity values are configured.")
    lines.append(
        "If a required field has no configured value, stop before submission, still report encountered_form_fields, and do not invent replacement values."
    )
    return "\n".join(lines)


def _render_route_hint_text(
    *,
    route_hint: str | None,
    route_kind_hint: str | None,
) -> str:
    if not route_hint:
        return "No previously successful route summary is available for this URL."
    hint_prefix = (
        f"Previously successful route kind: {route_kind_hint}. "
        if route_kind_hint
        else ""
    )
    return (
        f"{hint_prefix}Previously successful route summary for this URL: {route_hint}"
    )


def _render_delivery_instruction(*, delivery_email: str | None) -> str:
    if delivery_email:
        return (
            "If an email form is required, use this email address and confirm "
            f"submission: {delivery_email}"
        )
    return (
        "If the site requires email delivery and no configured email value is "
        "available, do not invent one. Classify the route as `email_delivery` "
        "and set email_submission_completed to false."
    )
