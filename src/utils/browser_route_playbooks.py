from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from fnmatch import fnmatch
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserRoutePlaybook,
    BrowserRoutePlaybookSelection,
    BrowserRoutePlaybookSelectionResult,
)


def select_browser_route_playbooks(
    *,
    playbooks: list[BrowserRoutePlaybook],
    normalized_url: str,
    route_family_hint: str,
    now: datetime,
) -> BrowserRoutePlaybookSelectionResult:
    host = urlsplit(normalized_url).netloc.casefold()
    path_query = (
        f"{urlsplit(normalized_url).path}?{urlsplit(normalized_url).query}"
    ).casefold()
    route_family = str(route_family_hint or "").strip()
    selected: list[BrowserRoutePlaybookSelection] = []
    stale_ids: list[str] = []
    for playbook in playbooks:
        match_reason = _match_playbook(
            playbook=playbook,
            host=host,
            path_query=path_query,
            route_family=route_family,
        )
        if not match_reason:
            continue
        if _is_stale(playbook=playbook, now=now):
            stale_ids.append(playbook.playbook_id)
            continue
        selected.append(
            BrowserRoutePlaybookSelection(
                schema_version="1.0",
                playbook_id=playbook.playbook_id,
                version=playbook.version,
                route_family=playbook.route_family,
                route_kind=playbook.route_kind,
                match_reason=match_reason,
                summary=playbook.summary,
                step_lines=[
                    f"{index}. {step.action}: {step.target} -> verify {step.verification}"
                    for index, step in enumerate(playbook.steps[:5], start=1)
                ],
                trap_lines=list(playbook.traps[:5]),
            )
        )
    selected.sort(key=lambda item: _selection_rank_key(item, route_family))
    selected = selected[:3]
    return BrowserRoutePlaybookSelectionResult(
        schema_version="1.0",
        selected_playbooks=selected,
        stale_playbook_ids=stale_ids,
        fallback_to_discovery=not selected,
    )


def serialize_playbook_selection_for_log(
    selection: BrowserRoutePlaybookSelectionResult,
) -> dict[str, object]:
    return {
        "selected_playbooks": [
            {
                "playbook_id": item.playbook_id,
                "version": item.version,
                "route_family": item.route_family,
                "route_kind": item.route_kind,
                "match_reason": item.match_reason,
            }
            for item in selection.selected_playbooks
        ],
        "stale_playbook_ids": list(selection.stale_playbook_ids),
        "fallback_to_discovery": selection.fallback_to_discovery,
        "schema_version": selection.schema_version,
    }


def serialize_selected_playbooks_for_prompt(
    playbooks: list[BrowserRoutePlaybookSelection],
) -> list[dict[str, object]]:
    return [asdict(playbook) for playbook in playbooks]


def _selection_rank_key(
    selection: BrowserRoutePlaybookSelection,
    route_family: str,
) -> tuple[int, str]:
    route_family_penalty = 0 if selection.route_family == route_family else 1
    generic_penalty = 1 if "publisher-agnostic" in selection.match_reason else 0
    return (route_family_penalty + generic_penalty, selection.playbook_id)


def _match_playbook(
    *,
    playbook: BrowserRoutePlaybook,
    host: str,
    path_query: str,
    route_family: str,
) -> str:
    if playbook.status != "active":
        return ""
    if route_family and playbook.route_family != route_family:
        return ""
    host_reason = _match_host_pattern(playbook.host_patterns, host)
    if not host_reason:
        return ""
    marker_reason = _match_path_marker(playbook.url_path_markers, path_query)
    if marker_reason:
        return f"{host_reason}; {marker_reason}"
    if host_reason != "publisher-agnostic host pattern":
        return f"{host_reason}; host-specific playbook"
    return ""


def _match_host_pattern(patterns: list[str], host: str) -> str:
    for raw_pattern in patterns:
        pattern = str(raw_pattern or "").strip().casefold()
        if not pattern:
            continue
        if pattern == "*":
            return "publisher-agnostic host pattern"
        if fnmatch(host, pattern):
            return f"host pattern {pattern}"
        suffix = pattern[2:] if pattern.startswith("*.") else pattern
        if host == suffix or host.endswith(f".{suffix}"):
            return f"host suffix {suffix}"
    return ""


def _match_path_marker(markers: list[str], path_query: str) -> str:
    for raw_marker in markers:
        marker = str(raw_marker or "").strip().casefold()
        if marker and marker in path_query:
            return f"path marker {marker}"
    return ""


def _is_stale(*, playbook: BrowserRoutePlaybook, now: datetime) -> bool:
    stale_after_days = int(playbook.stale_after_days)
    if stale_after_days <= 0:
        return False
    updated_at = _parse_datetime(playbook.updated_at)
    if updated_at is None:
        return True
    age_days = (now.astimezone(timezone.utc) - updated_at).days
    return age_days > stale_after_days


def _parse_datetime(value: str) -> datetime | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = f"{token[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
