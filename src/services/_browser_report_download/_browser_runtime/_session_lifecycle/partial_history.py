from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.services._browser_report_download._browser_runtime import (
    _EMAIL_DOMAIN_BLOCK_MARKERS,
    _EMAIL_DOMAIN_FAILURE_MARKERS,
    _LOOKUP_FAILURE_MARKERS,
    _LOOKUP_FIELD_MARKERS,
    _LOOKUP_SUBMIT_MARKERS,
    _PARTIAL_HISTORY_TEXT_MAX_CHARS,
)
from src.services._browser_report_download._browser_runtime.terminal_assets import (
    _read_history_final_state,
)

@dataclass(frozen=True)
class _SyntheticHistoryState:
    url: str
    title: str
    screenshot_path: str | None = None


@dataclass(frozen=True)
class _SyntheticHistoryEntry:
    state: _SyntheticHistoryState


@dataclass(frozen=True)
class _SyntheticActionResult:
    attachments: list[str]


class _SyntheticAgentHistory:
    def __init__(
        self,
        *,
        payload: dict[str, Any],
        state: _SyntheticHistoryState,
    ) -> None:
        self._payload = payload
        self.history = [_SyntheticHistoryEntry(state=state)]

    def is_done(self) -> bool:
        return True

    def final_result(self) -> str:
        return json.dumps(self._payload, ensure_ascii=True)

    def action_results(self) -> list[_SyntheticActionResult]:
        return [_SyntheticActionResult(attachments=[])]


def _read_lookup_blocker_partial_history(
    *,
    agent: Any,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
) -> Any | None:
    if str(request.route_family_hint or "").strip() != "browser_email_form":
        return None
    history = getattr(agent, "history", None)
    entries = getattr(history, "history", None)
    if not isinstance(entries, list) or not entries:
        return None
    history_text = _collect_agent_history_text(history)
    lowered = history_text.casefold()
    if not (
        any(marker in lowered for marker in _LOOKUP_FIELD_MARKERS)
        and any(marker in lowered for marker in _LOOKUP_FAILURE_MARKERS)
        and any(marker in lowered for marker in _LOOKUP_SUBMIT_MARKERS)
    ):
        return None
    state = _read_history_final_state(history)
    final_page_url = (
        str(getattr(state, "url", "") or "").strip()
        or str(request.attempt_url or request.url).strip()
        or normalized_url
    )
    final_page_title = str(getattr(state, "title", "") or "").strip()
    screenshot_path = str(getattr(state, "screenshot_path", "") or "").strip() or None
    lookup_label = _resolve_lookup_blocker_label(lowered)
    encountered_form_fields = _infer_encountered_form_fields(lowered, lookup_label)
    payload = {
        "route_kind": "email_delivery",
        "route_summary": (
            "Opened the report page, filled the email form, but could not verify "
            f"the required {lookup_label} lookup selection before submission."
        ),
        "route_family": "browser_email_form",
        "resolved_target_url": final_page_url,
        "final_page_url": final_page_url,
        "email_submission_completed": False,
        "downloaded_file_path": None,
        "downloaded_file_name": None,
        "downloaded_mime_type": None,
        "encountered_form_fields": encountered_form_fields,
        "route_steps": [
            {
                "index": None,
                "action": "submit",
                "target_text": "Submit",
                "target_role": "button",
                "target_url": final_page_url,
                "result": (
                    f"Submission was not verified because the required {lookup_label} "
                    "lookup field did not resolve to a valid option."
                ),
            }
        ],
        "post_submit_message": None,
        "confirmation_url_changed": False,
        "submit_button_state": None,
        "form_disappeared": False,
        "blocked_reason": "blocked_unknown_required_enum",
        "blocked_reason_detail": (
            f"The {lookup_label} field did not resolve to a valid lookup selection "
            "before submission."
        ),
        "final_page_title": final_page_title,
        "terminal_text_excerpt": _truncate_partial_history_excerpt(history_text),
        "traversed_page_urls": _read_distinct_history_urls(history, final_page_url),
        "onsite_capture_path": None,
        "onsite_capture_format": None,
        "onsite_page_count": None,
        "onsite_completeness_status": None,
    }
    return _SyntheticAgentHistory(
        payload=payload,
        state=_SyntheticHistoryState(
            url=final_page_url,
            title=final_page_title,
            screenshot_path=screenshot_path,
        ),
    )


def _read_terminal_blocker_partial_history(
    *,
    agent: Any,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
) -> Any | None:
    email_blocker_history = _read_email_domain_blocker_partial_history(
        agent=agent,
        request=request,
        normalized_url=normalized_url,
    )
    if email_blocker_history is not None:
        return email_blocker_history
    return _read_lookup_blocker_partial_history(
        agent=agent,
        request=request,
        normalized_url=normalized_url,
    )


def _read_email_domain_blocker_partial_history(
    *,
    agent: Any,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
) -> Any | None:
    history = getattr(agent, "history", None)
    entries = getattr(history, "history", None)
    if not isinstance(entries, list) or not entries:
        return None
    history_text = _collect_agent_history_text(history)
    lowered = history_text.casefold()
    if not (
        any(marker in lowered for marker in _EMAIL_DOMAIN_BLOCK_MARKERS)
        and any(marker in lowered for marker in _EMAIL_DOMAIN_FAILURE_MARKERS)
    ):
        return None
    state = _read_history_final_state(history)
    final_page_url = (
        str(getattr(state, "url", "") or "").strip()
        or str(request.attempt_url or request.url).strip()
        or normalized_url
    )
    final_page_title = str(getattr(state, "title", "") or "").strip()
    screenshot_path = str(getattr(state, "screenshot_path", "") or "").strip() or None
    encountered_form_fields = _infer_encountered_form_fields(lowered, "")
    if "Business Email Address" not in encountered_form_fields:
        encountered_form_fields.insert(0, "Business Email Address")
    payload = {
        "route_kind": "email_delivery",
        "route_summary": (
            "Opened the report page and reached an email form, but the configured "
            "email address was rejected because the site requires a business email."
        ),
        "route_family": "browser_email_form",
        "resolved_target_url": final_page_url,
        "final_page_url": final_page_url,
        "email_submission_completed": False,
        "downloaded_file_path": None,
        "downloaded_file_name": None,
        "downloaded_mime_type": None,
        "encountered_form_fields": encountered_form_fields,
        "route_steps": [
            {
                "index": None,
                "action": "submit",
                "target_text": "Download report",
                "target_role": "button",
                "target_url": final_page_url,
                "result": (
                    "Submission was blocked because the configured email address "
                    "was rejected as not being a business email."
                ),
            }
        ],
        "post_submit_message": "The form requires a business email address.",
        "confirmation_url_changed": False,
        "submit_button_state": None,
        "form_disappeared": False,
        "blocked_reason": "blocked_email_domain",
        "blocked_reason_detail": (
            "The form rejected the configured email address as not being a "
            "business or professional email."
        ),
        "final_page_title": final_page_title,
        "terminal_text_excerpt": _truncate_partial_history_excerpt(history_text),
        "traversed_page_urls": _read_distinct_history_urls(history, final_page_url),
        "onsite_capture_path": None,
        "onsite_capture_format": None,
        "onsite_page_count": None,
        "onsite_completeness_status": None,
    }
    return _SyntheticAgentHistory(
        payload=payload,
        state=_SyntheticHistoryState(
            url=final_page_url,
            title=final_page_title,
            screenshot_path=screenshot_path,
        ),
    )


def _collect_agent_history_text(history: Any) -> str:
    pieces: list[str] = []
    entries = getattr(history, "history", None)
    if not isinstance(entries, list):
        return ""
    for entry in entries:
        model_output = getattr(entry, "model_output", None)
        if model_output is not None:
            for attribute in (
                "thinking",
                "evaluation_previous_goal",
                "memory",
                "next_goal",
            ):
                pieces.append(str(getattr(model_output, attribute, "") or ""))
            current_state = getattr(model_output, "current_state", None)
            if current_state is not None:
                for attribute in (
                    "thinking",
                    "evaluation_previous_goal",
                    "memory",
                    "next_goal",
                ):
                    pieces.append(str(getattr(current_state, attribute, "") or ""))
            for action in getattr(model_output, "action", []) or []:
                pieces.append(_serialize_history_fragment(action))
        for result in getattr(entry, "result", []) or []:
            for attribute in (
                "error",
                "long_term_memory",
                "extracted_content",
            ):
                pieces.append(str(getattr(result, attribute, "") or ""))
        state = getattr(entry, "state", None)
        if state is not None:
            pieces.append(str(getattr(state, "url", "") or ""))
            pieces.append(str(getattr(state, "title", "") or ""))
    text = "\n".join(piece for piece in pieces if piece)
    return text[-_PARTIAL_HISTORY_TEXT_MAX_CHARS:]


def _serialize_history_fragment(value: Any) -> str:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return json.dumps(
                model_dump(exclude_none=True, mode="json"),
                ensure_ascii=True,
                sort_keys=True,
            )
        except Exception:
            return str(value)
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
        except Exception:
            return str(value)
    return str(value)


def _resolve_lookup_blocker_label(history_text: str) -> str:
    for label, markers in (
        ("Location", ("location",)),
        ("Country", ("country",)),
        ("State", ("state", "province", "territory")),
        ("Region", ("region",)),
    ):
        if any(marker in history_text for marker in markers):
            return label
    return "Location"


def _infer_encountered_form_fields(history_text: str, lookup_label: str) -> list[str]:
    field_markers = [
        ("First Name", ("first name", "firstname")),
        ("Last Name", ("last name", "lastname")),
        ("Business Email Address", ("business email", "work email", "email")),
        ("Phone", ("phone", "telephone")),
        ("Company Name", ("company", "organization", "organisation")),
        ("Role", ("role", "job level", "seniority")),
        ("Department", ("department",)),
        ("Industry", ("industry",)),
    ]
    lookup_token = str(lookup_label or "").strip()
    if lookup_token:
        field_markers.append((lookup_token, (lookup_token.casefold(),)))
    fields: list[str] = []
    seen: set[str] = set()
    for label, markers in field_markers:
        if label in seen:
            continue
        if any(marker in history_text for marker in markers):
            seen.add(label)
            fields.append(label)
    if lookup_token and lookup_token not in seen:
        fields.append(lookup_token)
    return fields


def _truncate_partial_history_excerpt(history_text: str) -> str:
    excerpt = re.sub(r"\s+", " ", history_text).strip()
    if len(excerpt) <= 500:
        return excerpt
    return excerpt[-500:]


def _read_distinct_history_urls(history: Any, fallback_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    entries = getattr(history, "history", None)
    if isinstance(entries, list):
        for entry in entries:
            state = getattr(entry, "state", None)
            token = str(getattr(state, "url", "") or "").strip()
            if token and token not in seen:
                seen.add(token)
                urls.append(token)
    if fallback_url and fallback_url not in seen:
        urls.append(fallback_url)
    return urls
