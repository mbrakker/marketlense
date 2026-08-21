"""Deterministic no-progress detection for Browser Use acquisition turns."""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

_NO_PROGRESS_EQUIVALENT_TURN_THRESHOLD = 3
_DOCUMENT_URL_PATTERN = re.compile(
    r"https?://[^\s\"'<>]+|(?:href|src)\s*=\s*[\"']([^\"']+)", re.IGNORECASE
)
_DOCUMENT_PATH_MARKERS = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xlsx")
_CONFIRMATION_MARKERS = (
    "thank you",
    "submission received",
    "request received",
    "form submitted",
    "successfully submitted",
    "confirmation",
)


@dataclass(frozen=True)
class BrowserNoProgressObservation:
    """Bounded state used to explain a deterministic Browser Use stop."""

    state_fingerprint: str
    consecutive_equivalent_turns: int
    should_stop: bool
    url: str
    actionable_dom_fingerprint: str
    actionable_dom_available: bool
    blocker_state: str
    document_candidate_count: int
    artifact_count: int
    network_document_count: int
    confirmation_observed: bool
    step_number: int


class BrowserNoProgressDetector:
    """Stop only after several consecutive materially identical agent turns."""

    def __init__(
        self,
        *,
        browser: Any | None = None,
        equivalent_turn_threshold: int = _NO_PROGRESS_EQUIVALENT_TURN_THRESHOLD,
    ) -> None:
        if equivalent_turn_threshold < 2:
            raise ValueError("equivalent_turn_threshold must require multiple turns")
        self._browser = browser
        self._equivalent_turn_threshold = equivalent_turn_threshold
        self._last_fingerprint = ""
        self._last_observation: BrowserNoProgressObservation | None = None
        self._instrumentation_available = True

    @property
    def observation(self) -> BrowserNoProgressObservation | None:
        return self._last_observation

    @property
    def should_stop(self) -> bool:
        return bool(self._last_observation and self._last_observation.should_stop)

    def observe(
        self,
        *,
        state: Any,
        model_output: Any,
        step_number: int,
    ) -> BrowserNoProgressObservation:
        actionable_dom, actionable_dom_available = _actionable_dom_representation(state)
        if not actionable_dom_available:
            self._instrumentation_available = False
        url = _normalized_scalar(getattr(state, "url", ""))
        blocker_state = _blocker_state(model_output)
        document_candidates = _document_candidates(actionable_dom)
        artifact_candidates = _artifact_candidates(self._browser)
        network_documents = _network_document_urls(state, self._browser)
        confirmation_observed = _confirmation_observed(
            actionable_dom,
            getattr(state, "recent_events", ""),
        )
        actionable_dom_fingerprint = _fingerprint(actionable_dom)
        state_fingerprint = (
            _fingerprint(
                "\n".join(
                    (
                        url,
                        actionable_dom_fingerprint,
                        blocker_state,
                        "|".join(document_candidates),
                        "|".join(artifact_candidates),
                        "|".join(network_documents),
                        "confirmation" if confirmation_observed else "",
                    )
                )
            )
            if self._instrumentation_available
            else ""
        )
        consecutive_turns = (
            self._last_observation.consecutive_equivalent_turns + 1
            if self._instrumentation_available
            and state_fingerprint == self._last_fingerprint
            and self._last_observation is not None
            else 1 if self._instrumentation_available else 0
        )
        observation = BrowserNoProgressObservation(
            state_fingerprint=state_fingerprint,
            consecutive_equivalent_turns=consecutive_turns,
            should_stop=(
                self._instrumentation_available
                and consecutive_turns >= self._equivalent_turn_threshold
            ),
            url=url,
            actionable_dom_fingerprint=actionable_dom_fingerprint,
            actionable_dom_available=actionable_dom_available,
            blocker_state=blocker_state,
            document_candidate_count=len(document_candidates),
            artifact_count=len(artifact_candidates),
            network_document_count=len(network_documents),
            confirmation_observed=confirmation_observed,
            step_number=step_number,
        )
        self._last_fingerprint = state_fingerprint
        self._last_observation = observation
        return observation

    def observe_callback(self, state: Any, model_output: Any, step_number: int) -> None:
        self.observe(
            state=state,
            model_output=model_output,
            step_number=step_number,
        )

    async def should_stop_callback(self) -> bool:
        should_stop = self.should_stop
        if should_stop:
            mark_browser_teardown_intentional(self._browser)
        return should_stop


def mark_browser_teardown_intentional(browser: Any | None) -> None:
    """Prevent a terminal no-progress stop from scheduling CDP reconnection.

    Browser Use invokes this callback from the session-owning event loop.  Its
    Agent then exits normally, while ``asyncio.run`` subsequently cancels the
    session's background CDP tasks.  Marking that teardown before the Agent
    exits prevents the WebSocket-drop callback from treating the cancellation
    as a new acquisition opportunity.
    """

    if browser is None:
        return
    with suppress(Exception):
        browser._intentional_stop = True
    browser_profile = getattr(browser, "browser_profile", None)
    if browser_profile is None:
        return
    with suppress(Exception):
        browser_profile.cdp_url = None


def _actionable_dom_representation(state: Any) -> tuple[str, bool]:
    try:
        dom_state = getattr(state, "dom_state", None)
        render = getattr(dom_state, "llm_representation", None)
        if not callable(render):
            return "", False
        representation = _normalized_scalar(render())
    except Exception:
        return "", False
    return representation, bool(representation)


def _blocker_state(model_output: Any) -> str:
    current_state = getattr(model_output, "current_state", None)
    text = " ".join(
        _normalized_scalar(getattr(current_state, attribute, ""))
        for attribute in ("memory", "evaluation_previous_goal", "next_goal")
    ).casefold()
    if any(marker in text for marker in ("captcha", "recaptcha", "hcaptcha")):
        return "blocked_captcha"
    if any(
        marker in text
        for marker in ("business email", "work email", "professional email")
    ):
        return "blocked_email_domain"
    if any(marker in text for marker in ("archived", "no longer available")):
        return "blocked_static_archive"
    if any(marker in text for marker in ("dropdown", "required select", "choose")):
        return "blocked_unknown_required_enum"
    return ""


def _document_candidates(value: str) -> tuple[str, ...]:
    candidates: set[str] = set()
    for match in _DOCUMENT_URL_PATTERN.finditer(value):
        candidate = _normalized_scalar(match.group(1) or match.group(0))
        if any(marker in candidate.casefold() for marker in _DOCUMENT_PATH_MARKERS):
            candidates.add(candidate)
    return tuple(sorted(candidates))


def _network_document_urls(state: Any, browser: Any | None) -> tuple[str, ...]:
    requests = list(getattr(state, "pending_network_requests", []) or [])
    requests.extend(list(getattr(browser, "network_events", []) or []))
    candidates: set[str] = set()
    for item in requests:
        url = _normalized_scalar(
            item.get("url", "") if isinstance(item, dict) else getattr(item, "url", "")
        )
        resource_type = _normalized_scalar(
            item.get("resource_type", "")
            if isinstance(item, dict)
            else getattr(item, "resource_type", "")
        ).casefold()
        if url and (
            resource_type in {"document", "xhr", "fetch"}
            or any(marker in url.casefold() for marker in _DOCUMENT_PATH_MARKERS)
        ):
            candidates.add(url)
    return tuple(sorted(candidates))


def _artifact_candidates(browser: Any | None) -> tuple[str, ...]:
    """Return bounded artifact identifiers exposed by compatible browser runtimes."""
    candidates: set[str] = set()
    for attribute in ("downloaded_files", "attachment_paths", "downloads"):
        for item in list(getattr(browser, attribute, []) or []):
            candidate = _normalized_scalar(
                item.get("path", "") if isinstance(item, dict) else item
            )
            if candidate:
                candidates.add(candidate)
    return tuple(sorted(candidates))


def _confirmation_observed(*values: Any) -> bool:
    text = " ".join(_normalized_scalar(value) for value in values).casefold()
    return any(marker in text for marker in _CONFIRMATION_MARKERS)


def _normalized_scalar(value: Any) -> str:
    return " ".join(str(value or "").split())


def _fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "BrowserNoProgressDetector",
    "BrowserNoProgressObservation",
    "mark_browser_teardown_intentional",
]
