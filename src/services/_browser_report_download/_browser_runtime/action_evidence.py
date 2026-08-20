from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from src.contracts.browser_download import BrowserDownloadRouteStep

_ACTION_NAMES = {
    "click": "click",
    "click_element": "click",
    "input": "fill",
    "input_text": "fill",
    "select_dropdown": "select",
    "navigate": "navigate",
    "go_to_url": "navigate",
}


def capture_browser_execution_route_steps(
    *,
    history: Any,
    final_page_url: str = "",
    final_page_title: str = "",
    identity_value_references: dict[str, str] | None = None,
) -> list[BrowserDownloadRouteStep]:
    """Build promotion evidence only from Browser Use's executed-history records.

    The model chooses an action index, but the runtime history records the element
    resolved from the browser selector map and the next browser state.  A route
    action is usable only when exactly one executable action succeeded in that
    history entry, so the following state is bound to that one action.
    """

    entries = getattr(history, "history", None)
    if not isinstance(entries, list):
        return []
    evidence: list[BrowserDownloadRouteStep] = []
    for position, entry in enumerate(entries):
        actions = list(
            getattr(getattr(entry, "model_output", None), "action", []) or []
        )
        results = list(getattr(entry, "result", []) or [])
        if not actions:
            continue
        for action_offset, action in enumerate(actions):
            action_name = _runtime_action_name(action)
            if not action_name:
                continue
            result = results[action_offset] if action_offset < len(results) else None
            interacted = _interacted_element(entry, action_offset)
            post_state = _post_action_state(
                entries=entries,
                position=position,
                action_count=len(actions),
                final_page_url=final_page_url,
                final_page_title=final_page_title,
            )
            locator = _locator_from_interacted_element(interacted)
            observed_url, observed_title = post_state
            identity_values = set((identity_value_references or {}).keys())
            observed_url = _safe_observed_url(observed_url)
            observed_title = _safe_observed_text(observed_title, identity_values)
            if _contains_identity_value(locator[1], identity_values):
                locator = ("", "")
            locator_evidence = _canonical_locator_evidence(*locator)
            postcondition_evidence = _postcondition_evidence(
                url=observed_url, title=observed_title
            )
            verified = (
                len(actions) == 1
                and _action_succeeded(result)
                and bool(locator_evidence)
                and bool(postcondition_evidence)
            )
            selector_type, selector = locator
            identity_field_reference = _identity_field_reference(
                action=action,
                action_name=action_name,
                identity_value_references=identity_value_references or {},
            )
            evidence.append(
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=len(evidence),
                    action=action_name,
                    target_text=selector or action_name,
                    target_role=selector_type or "browser_runtime",
                    target_url=observed_url,
                    result=(
                        "Browser runtime resolved the locator and observed "
                        "the immediate post-action state."
                        if verified
                        else "Browser runtime action evidence is incomplete."
                    ),
                    expected_evidence=["browser_execution"],
                    observed_evidence=(
                        ["browser_execution"] if verified else []
                    ),
                    locator_evidence=([locator_evidence] if locator_evidence else []),
                    postcondition_evidence=postcondition_evidence,
                    verification_status="verified" if verified else "missing",
                    locator_role=(
                        selector.partition(":")[0]
                        if selector_type == "role"
                        else ""
                    ),
                    locator_name=(
                        selector.partition(":")[2]
                        if selector_type == "role"
                        else ""
                    ),
                    locator_label=selector if selector_type == "label" else "",
                    locator_field_name=selector if selector_type == "name" else "",
                    locator_data_attribute=(
                        selector if selector_type == "data_attribute" else ""
                    ),
                    locator_css=selector if selector_type == "css" else "",
                    locator_text=selector if selector_type == "text" else "",
                    identity_field_reference=identity_field_reference,
                    expected_url_contains=observed_url,
                    expected_text=observed_title,
                )
            )
    return evidence


def _runtime_action_name(action: Any) -> str:
    dumped = _model_dump(action)
    for name in dumped:
        mapped = _ACTION_NAMES.get(str(name).strip().casefold())
        if mapped:
            return mapped
    return ""


def _model_dump(value: Any) -> dict[str, Any]:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(exclude_none=True, mode="json")
        except Exception:
            return {}
        return dumped if isinstance(dumped, dict) else {}
    return value if isinstance(value, dict) else {}


def _interacted_element(entry: Any, action_offset: int) -> Any:
    elements = getattr(getattr(entry, "state", None), "interacted_element", None)
    if not isinstance(elements, list) or action_offset >= len(elements):
        return None
    return elements[action_offset]


def _post_action_state(
    *,
    entries: list[Any],
    position: int,
    action_count: int,
    final_page_url: str,
    final_page_title: str,
) -> tuple[str, str]:
    if action_count == 1 and position + 1 < len(entries):
        state = getattr(entries[position + 1], "state", None)
        return (
            str(getattr(state, "url", "") or "").strip(),
            str(getattr(state, "title", "") or "").strip(),
        )
    if action_count == 1 and position + 1 == len(entries):
        return final_page_url.strip(), final_page_title.strip()
    return "", ""


def _action_succeeded(result: Any) -> bool:
    if result is None or str(getattr(result, "error", "") or "").strip():
        return False
    return getattr(result, "success", None) is not False


def _identity_field_reference(
    *,
    action: Any,
    action_name: str,
    identity_value_references: dict[str, str],
) -> str:
    if action_name not in {"fill", "select"}:
        return ""
    action_payload = _model_dump(action)
    nested = next(
        (value for value in action_payload.values() if isinstance(value, dict)), {}
    )
    for value in nested.values():
        reference = identity_value_references.get(str(value))
        if reference:
            return reference
    return ""


def _locator_from_interacted_element(element: Any) -> tuple[str, str]:
    if element is None:
        return "", ""
    attributes = getattr(element, "attributes", None)
    attributes = attributes if isinstance(attributes, dict) else {}
    name = str(getattr(element, "ax_name", "") or "").strip()
    role = str(attributes.get("role") or "").strip()
    if role and name:
        return "role", f"{role}:{name}"
    label = str(attributes.get("aria-label") or "").strip()
    if label:
        return "label", label
    field_name = str(attributes.get("name") or "").strip()
    if field_name:
        return "name", field_name
    for key in sorted(attributes):
        if str(key).startswith("data-") and str(attributes[key]).strip():
            return "data_attribute", f"{key}={attributes[key]}"
    element_id = str(attributes.get("id") or "").strip()
    if element_id:
        return "css", f"#{element_id}"
    if name:
        return "text", name
    return "", ""


def _canonical_locator_evidence(selector_type: str, selector: str) -> str:
    if not selector_type or not selector:
        return ""
    return f"locator:{selector_type}:{selector}"


def _postcondition_evidence(*, url: str, title: str) -> list[str]:
    evidence: list[str] = []
    if url:
        evidence.append(f"url:{url}")
    if title:
        evidence.append(f"text:{title}")
    return evidence


def _safe_observed_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _safe_observed_text(value: str, identity_values: set[str]) -> str:
    return "" if _contains_identity_value(value, identity_values) else value


def _contains_identity_value(value: str, identity_values: set[str]) -> bool:
    return any(
        identity_value and identity_value in value
        for identity_value in identity_values
    )
