from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger("market_lense.browser_report_download_service.cdp")

from .models import (
    _TARGET_LEVEL_METHODS,
    _INTERNAL_TARGET_URL_PREFIXES,
    _CDP_OPERATION_TIMEOUT_SECONDS,
    _ResolvedCdpSession,
)

from .transport import (
    _send_raw_cdp,
    _await_with_timeout,
)


def _send_browser_download_cdp(
    *,
    browser: Any,
    method: str,
    params: dict[str, Any],
    timeout_seconds: float,
    target_url: str = "",
) -> tuple[dict[str, Any], str, str]:
    if method in _TARGET_LEVEL_METHODS:
        client = _resolve_root_cdp_client(browser)
        result = _send_raw_cdp(
            client=client,
            method=method,
            params=params,
            session_id="",
            timeout_seconds=timeout_seconds,
        )
        return result, "", ""
    resolved_session = _resolve_browser_cdp_session(
        browser,
        timeout_seconds=timeout_seconds,
        target_url=target_url,
    )
    try:
        result = _send_raw_cdp(
            client=resolved_session.client,
            method=method,
            params=params,
            session_id=resolved_session.session_id,
            timeout_seconds=timeout_seconds,
        )
        return result, resolved_session.target_id, resolved_session.session_id
    finally:
        if resolved_session.transient:
            _detach_transient_cdp_session(
                client=resolved_session.client,
                session_id=resolved_session.session_id,
            )


def _resolve_browser_cdp_session(
    browser: Any,
    *,
    timeout_seconds: float,
    target_url: str = "",
) -> _ResolvedCdpSession:
    if str(target_url or "").strip():
        return _resolve_browser_cdp_session_for_target_url(
            browser,
            target_url=target_url,
            timeout_seconds=timeout_seconds,
        )
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if not callable(get_session):
        return _attach_transient_cdp_session(
            browser,
            timeout_seconds=timeout_seconds,
        )
    try:
        session = _await_with_timeout(
            get_session(target_id=None, focus=False),
            timeout_seconds=timeout_seconds,
        )
    except TypeError:
        session = _await_with_timeout(get_session(), timeout_seconds=timeout_seconds)
    except Exception:
        return _attach_transient_cdp_session(
            browser,
            timeout_seconds=timeout_seconds,
        )
    client = getattr(session, "cdp_client", None)
    session_id = str(getattr(session, "session_id", "") or "")
    target_id = str(getattr(session, "target_id", "") or "")
    if client is None or not session_id:
        return _attach_transient_cdp_session(
            browser,
            timeout_seconds=timeout_seconds,
        )
    return _ResolvedCdpSession(
        client=client,
        target_id=target_id,
        session_id=session_id,
        transient=False,
    )


def _resolve_browser_cdp_session_for_target_url(
    browser: Any,
    *,
    target_url: str,
    timeout_seconds: float,
) -> _ResolvedCdpSession:
    client = _resolve_root_cdp_client(browser)
    targets_result = _send_raw_cdp(
        client=client,
        method="Target.getTargets",
        params={},
        session_id="",
        timeout_seconds=timeout_seconds,
    )
    target_id = _select_real_page_target_id(
        targets_result,
        target_url=target_url,
        require_url_match=True,
    )
    if not target_id:
        raise RuntimeError("no real page target matched the requested CDP target URL")
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if callable(get_session):
        try:
            session = _await_with_timeout(
                get_session(target_id=target_id, focus=False),
                timeout_seconds=timeout_seconds,
            )
            client_from_session = getattr(session, "cdp_client", None)
            session_id = str(getattr(session, "session_id", "") or "")
            resolved_target_id = str(getattr(session, "target_id", "") or target_id)
            if client_from_session is not None and session_id:
                return _ResolvedCdpSession(
                    client=client_from_session,
                    target_id=resolved_target_id,
                    session_id=session_id,
                    transient=False,
                )
        except TypeError:
            pass
        except Exception:
            pass
    attach_result = _send_raw_cdp(
        client=client,
        method="Target.attachToTarget",
        params={"targetId": target_id, "flatten": True},
        session_id="",
        timeout_seconds=timeout_seconds,
    )
    session_id = str(attach_result.get("sessionId") or "").strip()
    if not session_id:
        raise RuntimeError("CDP target attach returned no session ID")
    return _ResolvedCdpSession(
        client=client,
        target_id=target_id,
        session_id=session_id,
        transient=True,
    )


def _resolve_browser_cdp_session_for_target_id(
    *,
    browser: Any,
    target_id: str,
    timeout_seconds: float,
) -> _ResolvedCdpSession:
    token = str(target_id or "").strip()
    if not token:
        raise RuntimeError("CDP target ID is required for target hygiene")
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if callable(get_session):
        try:
            session = _await_with_timeout(
                get_session(target_id=token, focus=False),
                timeout_seconds=timeout_seconds,
            )
            client_from_session = getattr(session, "cdp_client", None)
            session_id = str(getattr(session, "session_id", "") or "")
            resolved_target_id = str(getattr(session, "target_id", "") or token)
            if client_from_session is not None and session_id:
                return _ResolvedCdpSession(
                    client=client_from_session,
                    target_id=resolved_target_id,
                    session_id=session_id,
                    transient=False,
                )
        except TypeError:
            pass
        except Exception:
            pass
    client = _resolve_root_cdp_client(browser)
    attach_result = _send_raw_cdp(
        client=client,
        method="Target.attachToTarget",
        params={"targetId": token, "flatten": True},
        session_id="",
        timeout_seconds=timeout_seconds,
    )
    session_id = str(attach_result.get("sessionId") or "").strip()
    if not session_id:
        raise RuntimeError("CDP target attach returned no session ID")
    return _ResolvedCdpSession(
        client=client,
        target_id=token,
        session_id=session_id,
        transient=True,
    )


def _attach_transient_cdp_session(
    browser: Any,
    *,
    timeout_seconds: float = _CDP_OPERATION_TIMEOUT_SECONDS,
) -> _ResolvedCdpSession:
    client = _resolve_root_cdp_client(browser)
    targets_result = _send_raw_cdp(
        client=client,
        method="Target.getTargets",
        params={},
        session_id="",
        timeout_seconds=timeout_seconds,
    )
    target_id = _select_real_page_target_id(targets_result)
    if not target_id:
        raise RuntimeError("no real page target is available for CDP evidence capture")
    attach_result = _send_raw_cdp(
        client=client,
        method="Target.attachToTarget",
        params={"targetId": target_id, "flatten": True},
        session_id="",
        timeout_seconds=timeout_seconds,
    )
    session_id = str(attach_result.get("sessionId") or "").strip()
    if not session_id:
        raise RuntimeError("CDP target attach returned no session ID")
    return _ResolvedCdpSession(
        client=client,
        target_id=target_id,
        session_id=session_id,
        transient=True,
    )


def _detach_transient_cdp_session(*, client: Any, session_id: str) -> None:
    token = str(session_id or "").strip()
    if not token:
        return
    try:
        _send_raw_cdp(
            client=client,
            method="Target.detachFromTarget",
            params={"sessionId": token},
            session_id="",
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        return


def _resolve_root_cdp_client(browser: Any) -> Any:
    try:
        client = getattr(browser, "cdp_client", None)
    except Exception as exc:
        raise RuntimeError("browser CDP client is unavailable") from exc
    if client is None:
        raise RuntimeError("browser CDP client is unavailable")
    return client


def _select_real_page_target_id(
    targets_result: dict[str, Any],
    *,
    target_url: str = "",
    require_url_match: bool = False,
) -> str:
    target = _select_real_page_target_info(
        targets_result,
        target_url=target_url,
        require_url_match=require_url_match,
    )
    if target is None:
        return ""
    return str(target.get("targetId") or target.get("target_id") or "").strip()


def _select_real_page_target_info(
    targets_result: dict[str, Any],
    *,
    target_url: str = "",
    require_url_match: bool = False,
) -> dict[str, Any] | None:
    raw_targets = targets_result.get("targetInfos")
    if not isinstance(raw_targets, list):
        return None
    candidates: list[dict[str, Any]] = []
    url_candidates: list[dict[str, Any]] = []
    for raw_target in raw_targets:
        if not isinstance(raw_target, dict):
            continue
        if not _is_user_facing_page_target(raw_target):
            continue
        candidates.append(raw_target)
        url = str(raw_target.get("url") or "").strip()
        if _target_url_matches(url, target_url):
            url_candidates.append(raw_target)
    if target_url:
        return url_candidates[-1] if url_candidates else None
    if require_url_match:
        return None
    return candidates[-1] if candidates else None


def _is_user_facing_page_target(raw_target: dict[str, Any]) -> bool:
    target_type = str(
        raw_target.get("type") or raw_target.get("target_type") or ""
    ).strip()
    if target_type != "page":
        return False
    target_id = str(
        raw_target.get("targetId") or raw_target.get("target_id") or ""
    ).strip()
    if not target_id:
        return False
    url = str(raw_target.get("url") or "").strip()
    if not url:
        return False
    if any(url.startswith(prefix) for prefix in _INTERNAL_TARGET_URL_PREFIXES):
        return False
    return True


def _target_url_matches(candidate_url: str, expected_url: str) -> bool:
    candidate = str(candidate_url or "").strip()
    expected = str(expected_url or "").strip()
    if not candidate or not expected:
        return False
    return _without_url_fragment(candidate).rstrip("/") == _without_url_fragment(
        expected
    ).rstrip("/")


def _without_url_fragment(raw_url: str) -> str:
    return str(raw_url or "").split("#", 1)[0]


def _read_target_viewport_size(
    *,
    client: Any,
    session_id: str,
) -> tuple[int, int, str]:
    try:
        result = _send_raw_cdp(
            client=client,
            method="Page.getLayoutMetrics",
            params={},
            session_id=session_id,
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        return 0, 0, "unknown"
    width = _coerce_viewport_dimension(result, "clientWidth", "width")
    height = _coerce_viewport_dimension(result, "clientHeight", "height")
    if width < 0 and height < 0:
        return width, height, "unknown"
    if width <= 0 or height <= 0:
        return width, height, "zero_size"
    return width, height, "ok"


def _coerce_viewport_dimension(
    result: dict[str, Any],
    primary_key: str,
    fallback_key: str,
) -> int:
    for container_key in (
        "visualViewport",
        "layoutViewport",
        "cssVisualViewport",
        "cssLayoutViewport",
    ):
        container = result.get(container_key)
        if not isinstance(container, dict):
            continue
        raw_value = container.get(primary_key, container.get(fallback_key))
        try:
            value = int(float(str(raw_value)))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return -1


def _focus_browser_use_target(*, browser: Any, target_id: str) -> None:
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if not callable(get_session):
        return
    try:
        _await_with_timeout(
            get_session(target_id=target_id, focus=True),
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        return
