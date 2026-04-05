from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.http import (
    download_pdf_from_url,
    ensure_downloaded_pdf,
    resolve_downloaded_mime_type,
    validate_downloaded_pdf_artifact,
)
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url

if TYPE_CHECKING:
    from src.services._browser_report_download.browser import BrowserAgentRunResult

_ROUTE_KINDS = {"pdf_download", "email_delivery"}
_ROUTE_SUMMARY_ACTION_MARKERS = (
    "open",
    "click",
    "fill",
    "enter",
    "submit",
    "select",
    "choose",
    "use",
    "wait",
    "download",
    "inspect",
    "apply",
    "expand",
    "navigate",
)
_ROUTE_SUMMARY_TARGET_MARKERS = (
    "button",
    "link",
    "page",
    "form",
    "field",
    "email",
    "report",
    "pdf",
    "cta",
    "tab",
    "filter",
    "modal",
    "screen",
    "prompt",
)
_SUCCESS_URL_MARKERS = ("thank", "success", "confirm", "complete", "done")


class BrowserUseRouteStep(BaseModel):
    index: int | None = Field(default=None)
    action: str = Field(default="")
    target_text: str = Field(default="")
    target_role: str = Field(default="")
    target_url: str = Field(default="")
    result: str = Field(default="")


class BrowserUseAgentResult(BaseModel):
    route_kind: str = Field(description="Either `pdf_download` or `email_delivery`.")
    route_summary: str = Field(
        default="",
        description="Short description of the working clicks/forms for this URL.",
    )
    route_family: str = Field(
        default="",
        description="Observed route family for this execution attempt when the agent can classify it.",
    )
    resolved_target_url: str = Field(
        default="",
        description="Resolved target URL that produced the final artifact or email form state.",
    )
    final_page_url: str = Field(
        default="",
        description="Final browser URL after the task completed.",
    )
    email_submission_completed: bool | None = Field(
        default=None,
        description="True only when an email-gated form was actually submitted.",
    )
    downloaded_file_path: str | None = Field(
        default=None,
        description="Absolute local path of the downloaded file when one was saved.",
    )
    downloaded_file_name: str | None = Field(
        default=None,
        description="Downloaded file name when available.",
    )
    downloaded_mime_type: str | None = Field(
        default=None,
        description="Downloaded file MIME type when known.",
    )
    encountered_form_fields: list[str] = Field(
        default_factory=list,
        description="Distinct form field labels or names encountered during the route.",
    )
    route_steps: list[BrowserUseRouteStep] = Field(
        default_factory=list,
        description="Ordered structured action trace for the successful route when the agent can provide it.",
    )
    post_submit_message: str = Field(
        default="",
        description="Visible confirmation or status text shown after a form submission attempt.",
    )
    confirmation_url_changed: bool | None = Field(
        default=None,
        description="Whether the page URL changed after the submission or route-completing action.",
    )
    submit_button_state: str = Field(
        default="",
        description="Observed submit-button state after submission, for example `disabled` or `replaced`.",
    )
    form_disappeared: bool | None = Field(
        default=None,
        description="Whether the form disappeared after submission.",
    )


def finalize_browser_report_download_result(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    delivery_email: str | None,
    download_dir: Path,
    browser_run: BrowserAgentRunResult,
) -> BrowserReportDownloadResult:
    final_url = str(
        browser_run.final_page_url or request.attempt_url or normalized_url
    ).strip()
    agent_result = _parse_browser_result(
        raw_model_response=browser_run.raw_model_response,
        normalized_url=normalized_url,
    )
    if agent_result is None:
        return _salvage_without_structured_result(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            final_url=final_url,
            download_dir=download_dir,
            browser_run=browser_run,
        )

    downloaded_path = _resolve_downloaded_file(
        explicit_path=agent_result.downloaded_file_path,
        browser_downloaded_files=browser_run.downloaded_files,
        download_dir=download_dir,
    )
    resolved_target_url = str(
        agent_result.resolved_target_url
        or final_url
        or request.attempt_url
        or normalized_url
    ).strip()
    downloaded_path, used_candidate_pdf_url = _complete_pdf_artifact(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        downloaded_path=downloaded_path,
        target_urls=[
            request.candidate_trace.pdf_url if request.candidate_trace is not None else "",
            resolved_target_url,
            final_url,
        ],
    )
    route_kind = _resolve_route_kind(
        route_kind=agent_result.route_kind,
        downloaded_path=downloaded_path,
        encountered_form_fields=agent_result.encountered_form_fields,
        post_submit_message=agent_result.post_submit_message,
    )
    if route_kind == "pdf_download" and downloaded_path is None:
        raise AppError(
            code="browser_download_missing_file",
            message="browser-use classified the route as a PDF download but no local file was found",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "download_dir": str(download_dir),
            },
        )

    confirmation_evidence = _build_confirmation_evidence(
        agent_result=agent_result,
        final_url=final_url,
    )
    encountered_form_fields = _normalize_encountered_form_fields(
        agent_result.encountered_form_fields
    )
    route_steps = _resolve_route_steps(
        request=request,
        agent_result=agent_result,
        raw_summary=agent_result.route_summary,
        resolved_target_url=resolved_target_url,
        downloaded_path=downloaded_path,
        confirmation_evidence=confirmation_evidence,
    )
    route_summary = _resolve_route_summary(
        raw_summary=agent_result.route_summary,
        route_steps=route_steps,
        normalized_url=normalized_url,
    )
    final_url = str(agent_result.final_page_url or final_url or normalized_url).strip()
    downloaded_mime_type = resolve_downloaded_mime_type(
        reported_mime_type=str(agent_result.downloaded_mime_type).strip()
        if agent_result.downloaded_mime_type
        else None,
        downloaded_path=downloaded_path,
    )
    validate_downloaded_pdf_artifact(
        downloaded_path=downloaded_path,
        downloaded_mime_type=downloaded_mime_type,
        normalized_url=normalized_url,
    )
    outcome, route_status = _classify_route_result(
        route_kind=route_kind,
        downloaded_path=downloaded_path,
        confirmation_evidence=confirmation_evidence,
        encountered_form_fields=encountered_form_fields,
        email_submission_completed=agent_result.email_submission_completed,
    )
    downloaded_file_name = downloaded_path.name if downloaded_path else None
    downloaded_size_bytes = downloaded_path.stat().st_size if downloaded_path else None
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind=route_kind,
        route_family=_resolve_route_family(
            request=request,
            agent_result=agent_result,
            route_kind=route_kind,
        ),
        route_status=route_status,
        outcome=outcome,
        route_summary=route_summary,
        final_page_url=final_url,
        resolved_target_url=resolved_target_url,
        used_route_hint=bool(request.route_hint),
        route_steps=route_steps,
        confirmation_evidence=confirmation_evidence,
        browser_had_structured_result=True,
        used_candidate_pdf_url=used_candidate_pdf_url,
        used_candidate_source_page=_used_candidate_source_page(request),
        encountered_form_fields=encountered_form_fields,
        downloaded_file_path=str(downloaded_path) if downloaded_path else None,
        downloaded_file_name=downloaded_file_name,
        downloaded_mime_type=downloaded_mime_type,
        downloaded_size_bytes=downloaded_size_bytes,
    )


def _parse_browser_result(
    *,
    raw_model_response: str,
    normalized_url: str,
) -> BrowserUseAgentResult | None:
    payload = str(raw_model_response or "").strip()
    if not payload:
        return None
    try:
        return BrowserUseAgentResult.model_validate_json(payload)
    except ValidationError as exc:
        raise AppError(
            code="browser_download_invalid_result",
            message="browser-use returned an invalid structured result",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "raw_model_response": raw_model_response,
            },
        ) from exc


def _salvage_without_structured_result(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    final_url: str,
    download_dir: Path,
    browser_run: BrowserAgentRunResult,
) -> BrowserReportDownloadResult:
    downloaded_path = _resolve_downloaded_file(
        explicit_path=None,
        browser_downloaded_files=browser_run.downloaded_files,
        download_dir=download_dir,
    )
    downloaded_path, used_candidate_pdf_url = _complete_pdf_artifact(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        downloaded_path=downloaded_path,
        target_urls=[
            request.candidate_trace.pdf_url if request.candidate_trace is not None else "",
            final_url,
            request.attempt_url or "",
        ],
    )
    if downloaded_path is not None:
        return _build_pdf_result(
            request=request,
            normalized_url=normalized_url,
            final_url=final_url,
            resolved_target_url=final_url or request.attempt_url or normalized_url,
            downloaded_path=downloaded_path,
            downloaded_mime_type=resolve_downloaded_mime_type(
                reported_mime_type=None,
                downloaded_path=downloaded_path,
            ),
            browser_had_structured_result=False,
            used_candidate_pdf_url=used_candidate_pdf_url,
        )
    raise AppError(
        code="browser_download_empty_result",
        message="browser-use returned no structured result and no PDF artifact could be salvaged",
        retryable=True,
        context={
            "normalized_url": normalized_url,
            "final_url": final_url,
            "candidate_pdf_url": (
                request.candidate_trace.pdf_url if request.candidate_trace else None
            ),
        },
    )


def _complete_pdf_artifact(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    downloaded_path: Path | None,
    target_urls: list[str],
) -> tuple[Path | None, bool]:
    if downloaded_path is not None:
        ensured_path = ensure_downloaded_pdf(
            downloaded_path=downloaded_path,
            ctx=ctx,
            normalized_url=normalized_url,
            document_url=str(request.attempt_url or normalized_url).strip(),
            timeout_seconds=request.settings.timeout_seconds,
        )
        return ensured_path, False
    candidate_pdf_url = (
        str(request.candidate_trace.pdf_url or "").strip()
        if request.candidate_trace is not None
        else ""
    )
    for target_url in target_urls:
        normalized_target = str(target_url or "").strip()
        if not normalized_target:
            continue
        fetched_path = _try_fetch_pdf_target(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            target_url=normalized_target,
        )
        if fetched_path is not None:
            return fetched_path, normalized_target == candidate_pdf_url
    return None, False


def _try_fetch_pdf_target(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    target_url: str,
) -> Path | None:
    destination_name = Path(urlsplit(target_url).path).name or "download.pdf"
    destination_path = download_dir / destination_name
    try:
        download_pdf_from_url(
            pdf_url=target_url,
            destination_path=destination_path,
            timeout_seconds=request.settings.timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        ensured_path = ensure_downloaded_pdf(
            downloaded_path=destination_path,
            ctx=ctx,
            normalized_url=normalized_url,
            document_url=target_url,
            timeout_seconds=request.settings.timeout_seconds,
        )
        validate_downloaded_pdf_artifact(
            downloaded_path=ensured_path,
            downloaded_mime_type=resolve_downloaded_mime_type(
                reported_mime_type=None,
                downloaded_path=ensured_path,
            ),
            normalized_url=normalized_url,
        )
        return ensured_path
    except AppError:
        destination_path.unlink(missing_ok=True)
        return None


def _build_pdf_result(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    final_url: str,
    resolved_target_url: str,
    downloaded_path: Path,
    downloaded_mime_type: str | None,
    browser_had_structured_result: bool,
    used_candidate_pdf_url: bool,
) -> BrowserReportDownloadResult:
    route_steps = [
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=0,
            action="open",
            target_text=resolved_target_url,
            target_role="url",
            target_url=resolved_target_url,
            result="downloaded",
        )
    ]
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="pdf_download",
        route_family=request.route_family_hint or "browser_pdf_click",
        route_status="verified",
        outcome="downloaded",
        route_summary="Open the target page or PDF URL and save the downloaded PDF file locally.",
        final_page_url=final_url,
        resolved_target_url=resolved_target_url,
        used_route_hint=bool(request.route_hint),
        route_steps=route_steps,
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=final_url,
        ),
        browser_had_structured_result=browser_had_structured_result,
        used_candidate_pdf_url=used_candidate_pdf_url,
        used_candidate_source_page=_used_candidate_source_page(request),
        encountered_form_fields=[],
        downloaded_file_path=str(downloaded_path),
        downloaded_file_name=downloaded_path.name,
        downloaded_mime_type=downloaded_mime_type,
        downloaded_size_bytes=downloaded_path.stat().st_size,
    )


def _normalize_encountered_form_fields(raw_fields: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_field in raw_fields:
        token = str(raw_field or "").strip()
        if not token:
            continue
        dedupe_key = token.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(token)
    return normalized


def _resolve_route_summary(
    *,
    raw_summary: str,
    route_steps: list[BrowserDownloadRouteStep],
    normalized_url: str,
) -> str:
    route_summary = str(raw_summary or "").strip()
    if route_summary and _is_semantic_route_summary(route_summary):
        return route_summary
    if route_steps:
        return _derive_route_summary(route_steps)
    if route_summary:
        raise AppError(
            code="browser_download_route_summary_too_weak",
            message="browser-use returned a route summary without enough reusable action detail",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "route_summary": route_summary,
            },
        )
    raise AppError(
        code="browser_download_missing_route_summary",
        message="browser-use returned no reusable route summary or route steps",
        retryable=True,
        context={"normalized_url": normalized_url},
    )


def _derive_route_summary(route_steps: list[BrowserDownloadRouteStep]) -> str:
    fragments: list[str] = []
    for step in route_steps[:3]:
        action = step.action or "follow"
        target = step.target_text or step.target_role or step.target_url or "page"
        result = step.result or "completed"
        fragments.append(f"{action} {target} ({result})")
    return "; then ".join(fragments).strip()


def _is_semantic_route_summary(route_summary: str) -> bool:
    normalized = " ".join(str(route_summary or "").split()).strip()
    if not normalized:
        return False
    lowered = normalized.casefold()
    tokens = [token for token in re.split(r"[^a-z0-9]+", lowered) if token]
    if len(tokens) < 4:
        return False
    has_action = any(marker in lowered for marker in _ROUTE_SUMMARY_ACTION_MARKERS)
    has_target = any(marker in lowered for marker in _ROUTE_SUMMARY_TARGET_MARKERS)
    if not has_action or not has_target:
        return False
    return (
        len(tokens) >= 6
        or bool(
            re.search(
                r"\b(first|second|then|after|until|when|once|final)\b",
                lowered,
            )
        )
        or any(
            marker in lowered
            for marker in ("completion", "finish", "saved", "sent", "submitted")
        )
    )


def _resolve_route_kind(
    *,
    route_kind: str,
    downloaded_path: Path | None,
    encountered_form_fields: list[str],
    post_submit_message: str,
) -> str:
    token = str(route_kind or "").strip().lower()
    if downloaded_path is not None:
        return "pdf_download"
    if encountered_form_fields or _message_indicates_email_delivery(post_submit_message):
        return "email_delivery"
    if token in _ROUTE_KINDS:
        return token
    raise AppError(
        code="browser_download_route_kind_invalid",
        message="browser-use returned an unsupported route classification",
        retryable=True,
        context={"route_kind": route_kind},
    )


def _build_confirmation_evidence(
    *,
    agent_result: BrowserUseAgentResult,
    final_url: str,
) -> BrowserDownloadConfirmationEvidence:
    visible_confirmation_text = str(agent_result.post_submit_message or "").strip()
    return BrowserDownloadConfirmationEvidence(
        schema_version="1.0",
        url_changed=bool(agent_result.confirmation_url_changed),
        visible_confirmation_text=visible_confirmation_text,
        submit_button_state=str(agent_result.submit_button_state or "").strip()
        or "unchanged",
        form_disappeared=bool(agent_result.form_disappeared),
        final_page_url=str(agent_result.final_page_url or final_url).strip(),
    )


def _resolve_route_steps(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    raw_summary: str,
    resolved_target_url: str,
    downloaded_path: Path | None,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> list[BrowserDownloadRouteStep]:
    steps: list[BrowserDownloadRouteStep] = []
    for index, raw_step in enumerate(agent_result.route_steps):
        action = str(raw_step.action or "").strip() or "follow"
        target_text = str(raw_step.target_text or "").strip()
        target_role = str(raw_step.target_role or "").strip() or "page"
        target_url = str(raw_step.target_url or "").strip()
        result = str(raw_step.result or "").strip() or "completed"
        steps.append(
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=int(raw_step.index) if raw_step.index is not None else index,
                action=action,
                target_text=target_text,
                target_role=target_role,
                target_url=target_url,
                result=result,
            )
        )
    if steps:
        return steps
    if not _is_semantic_route_summary(str(raw_summary or "").strip()):
        return []
    fallback_result = "downloaded" if downloaded_path is not None else "completed"
    if confirmation_evidence.visible_confirmation_text or confirmation_evidence.url_changed:
        fallback_result = "submitted"
    return [
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=0,
            action="open",
            target_text=str(request.attempt_url or request.url).strip(),
            target_role="url",
            target_url=resolved_target_url,
            result=fallback_result,
        )
    ]


def _classify_route_result(
    *,
    route_kind: str,
    downloaded_path: Path | None,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    encountered_form_fields: list[str],
    email_submission_completed: bool | None,
) -> tuple[str, str]:
    if downloaded_path is not None:
        return "downloaded", "verified"
    if route_kind != "email_delivery":
        raise AppError(
            code="browser_download_missing_file",
            message="No PDF artifact was produced for a non-email route",
            retryable=True,
        )
    if _has_strong_confirmation_signal(confirmation_evidence):
        return "email_requested", "verified"
    if email_submission_completed is True:
        raise AppError(
            code="browser_download_email_confirmation_missing",
            message="browser-use identified an email-delivery route but did not capture a visible delivery confirmation",
            retryable=True,
            context={"final_page_url": confirmation_evidence.final_page_url},
        )
    if encountered_form_fields or email_submission_completed is False:
        return "email_required", "inferred"
    raise AppError(
        code="browser_download_email_submission_missing",
        message="browser-use did not produce enough evidence to verify an email-gated route",
        retryable=True,
        context={"final_page_url": confirmation_evidence.final_page_url},
    )


def _has_strong_confirmation_signal(
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> bool:
    if _message_indicates_email_delivery(confirmation_evidence.visible_confirmation_text):
        return True
    if confirmation_evidence.url_changed and _url_indicates_confirmation(
        confirmation_evidence.final_page_url
    ):
        return True
    if confirmation_evidence.submit_button_state in {"disabled", "replaced"}:
        return True
    return confirmation_evidence.form_disappeared


def _message_indicates_email_delivery(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    email_markers = ("email", "inbox", "mailbox", "mail")
    delivery_markers = (
        "check",
        "sent",
        "send",
        "receive",
        "receiving",
        "delivered",
        "delivery",
        "download link",
        "link",
    )
    return any(marker in token for marker in email_markers) and any(
        marker in token for marker in delivery_markers
    )


def _url_indicates_confirmation(url: str) -> bool:
    lowered = str(url or "").strip().casefold()
    return any(marker in lowered for marker in _SUCCESS_URL_MARKERS)


def _resolve_route_family(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    route_kind: str,
) -> str:
    token = str(agent_result.route_family or "").strip()
    if token:
        return token
    if request.route_family_hint:
        return request.route_family_hint
    if route_kind == "email_delivery":
        return "browser_email_form"
    return "browser_pdf_click"


def _used_candidate_source_page(request: BrowserReportDownloadRequest) -> bool:
    attempt_url = str(request.attempt_url or "").strip()
    source_page_url = str(request.source_page_url_hint or "").strip()
    if not attempt_url or not source_page_url:
        return False
    return normalize_url(attempt_url) == normalize_url(source_page_url)


def _resolve_downloaded_file(
    *,
    explicit_path: str | None,
    browser_downloaded_files: list[str],
    download_dir: Path,
) -> Path | None:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    for raw_path in browser_downloaded_files:
        candidates.append(Path(raw_path).expanduser())
    for path in sorted(download_dir.glob("*")):
        if path.is_file():
            candidates.append(path)

    resolved_candidates: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        if download_dir not in resolved.parents:
            continue
        resolved_candidates.append(resolved)
    if not resolved_candidates:
        return None
    pdf_candidates = [
        path for path in resolved_candidates if path.suffix.lower() == ".pdf"
    ]
    selected = pdf_candidates or resolved_candidates
    selected.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return selected[0]
