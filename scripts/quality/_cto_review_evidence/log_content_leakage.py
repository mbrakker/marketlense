"""Deterministic, privacy-preserving retained-content log assessment."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from src.utils.gui_utils import (
    extract_log_date_from_filename,
    parse_structured_log_line,
)

# Paragraphs below these bounds are commonly labels, headings, or boilerplate.
MIN_CANARY_CHARACTERS = 160
MIN_CANARY_TOKENS = 24
# Two independent windows make accidental overlap with ordinary operational logs
# unlikely.
WINDOW_CHARACTERS = 80
WINDOW_MATCHES_REQUIRED = 2
_JSON_ESCAPE = re.compile(r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})')
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
_PLACEHOLDERS = {
    "n/a",
    "na",
    "none",
    "not available",
    "unavailable",
    "not generated",
    "abstained",
    "placeholder",
    "tbd",
}
_SOURCE_FILENAMES = {
    "doc_map.json",
    "document_map.json",
    "findings.json",
    "limitations.json",
    "methods.json",
    "quote_candidates.json",
    "scope.json",
    "page_text.json",
    "source_text.json",
    "extracted_text.json",
}
_EDITORIAL_FIELDS = (
    "linkedin_post",
    "expert_comment",
    "commentary",
    "report_commentary",
    "tldr",
    "executive_summary",
)


@dataclass(frozen=True)
class Canary:
    canary_class: str
    report_identity: str
    relative_artifact_path: str
    field_family: str
    normalized_text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.normalized_text.encode("utf-8")).hexdigest()

    @property
    def token_count(self) -> int:
        return len(self.normalized_text.split())

    def public_metadata(self) -> dict[str, object]:
        return {
            "canary_class": self.canary_class,
            "report_identity": self.report_identity,
            "relative_artifact_path": self.relative_artifact_path,
            "field_family": self.field_family,
            "normalized_character_count": len(self.normalized_text),
            "token_count": self.token_count,
            "sha256": self.sha256,
        }


def normalize_text(value: str) -> str:
    """Normalize text shared by extraction and raw-line matching."""

    raw = str(value)
    if raw.isascii() and "\\" not in raw and "&" not in raw:
        return " ".join(raw.casefold().split())

    def replace_escape(match: re.Match[str]) -> str:
        try:
            return json.loads(f'"{match.group(0)}"')
        except json.JSONDecodeError:
            return match.group(0)

    decoded = _JSON_ESCAPE.sub(replace_escape, html.unescape(raw))
    return " ".join(unicodedata.normalize("NFKC", decoded).casefold().split())


def extract_canaries(
    artifact_root: Path,
    *,
    maximum_per_class: int,
) -> tuple[list[Canary], list[Canary], int]:
    """Extract stable source and generated-editorial samples from frozen inputs."""
    source_candidates: list[Canary] = []
    editorial_candidates: list[Canary] = []
    examined = 0
    for path in sorted(artifact_root.rglob("*.json")):
        relative = path.relative_to(artifact_root).as_posix()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            if path.name in _SOURCE_FILENAMES or path.name == "artifacts.json":
                raise ValueError(
                    f"Retained canary artifact cannot be read: {relative}"
                ) from exc
            continue
        examined += 1
        report_identity = _report_identity(relative)
        if path.name in _SOURCE_FILENAMES:
            source_candidates.extend(
                _source_candidates(payload, report_identity, relative, path.name)
            )
        if path.name == "artifacts.json":
            editorial_candidates.extend(
                _editorial_candidates(payload, report_identity, relative)
            )
    return (
        _spread_and_bound(source_candidates, maximum_per_class),
        _spread_and_bound(editorial_candidates, maximum_per_class),
        examined,
    )


def _source_candidates(
    payload: object,
    report_identity: str,
    relative_path: str,
    filename: str,
) -> list[Canary]:
    candidates: list[Canary] = []
    if filename in {"doc_map.json", "document_map.json"} and isinstance(payload, dict):
        for index, section in enumerate(payload.get("sections", [])):
            if isinstance(section, dict):
                candidates.extend(
                    _canaries_from_text(
                        str(section.get("summary") or ""),
                        canary_class="source_report",
                        report_identity=report_identity,
                        relative_path=relative_path,
                        field_family=f"document_map.sections[{index}].summary",
                    )
                )
    for field_path, value in _walk_text(payload):
        if (
            field_path.endswith(".evidence")
            or field_path.endswith(".text")
            or field_path.endswith(".summary")
        ):
            candidates.extend(
                _canaries_from_text(
                    value,
                    canary_class="source_report",
                    report_identity=report_identity,
                    relative_path=relative_path,
                    field_family=f"{filename}:{field_path}",
                )
            )
    return candidates


def _editorial_candidates(
    payload: object, report_identity: str, relative_path: str
) -> list[Canary]:
    if not isinstance(payload, dict):
        return []
    candidates: list[Canary] = []
    for field in _EDITORIAL_FIELDS:
        values: list[tuple[str, str]] = []
        if isinstance(payload.get(field), str):
            values.append((field, str(payload[field])))
        summary = payload.get("summary")
        if isinstance(summary, dict) and isinstance(summary.get(field), str):
            values.append((f"summary.{field}", str(summary[field])))
        for field_family, value in values:
            candidates.extend(
                _canaries_from_text(
                    value,
                    canary_class="generated_editorial",
                    report_identity=report_identity,
                    relative_path=relative_path,
                    field_family=field_family,
                )
            )
    return candidates


def _walk_text(value: object, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key in sorted(value):
            next_path = f"{path}.{key}" if path else str(key)
            yield from _walk_text(value[key], next_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_text(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def _canaries_from_text(
    value: str,
    *,
    canary_class: str,
    report_identity: str,
    relative_path: str,
    field_family: str,
) -> list[Canary]:
    results: list[Canary] = []
    for index, paragraph in enumerate(_PARAGRAPH_SPLIT.split(value)):
        normalized = normalize_text(paragraph)
        if not _eligible(normalized):
            continue
        results.append(
            Canary(
                canary_class=canary_class,
                report_identity=report_identity,
                relative_artifact_path=relative_path,
                field_family=f"{field_family}[{index}]",
                normalized_text=normalized,
            )
        )
    return results


def _eligible(normalized: str) -> bool:
    return (
        len(normalized) >= MIN_CANARY_CHARACTERS
        and len(normalized.split()) >= MIN_CANARY_TOKENS
        and normalized not in _PLACEHOLDERS
    )


def _spread_and_bound(candidates: list[Canary], maximum: int) -> list[Canary]:
    unique = {candidate.sha256: candidate for candidate in candidates}
    by_report: dict[str, list[Canary]] = defaultdict(list)
    for candidate in sorted(
        unique.values(),
        key=lambda item: (
            item.report_identity,
            item.relative_artifact_path,
            item.field_family,
            item.sha256,
        ),
    ):
        by_report[candidate.report_identity].append(candidate)
    selected: list[Canary] = []
    while by_report and len(selected) < maximum:
        for report in sorted(by_report):
            selected.append(by_report[report].pop(0))
            if not by_report[report]:
                del by_report[report]
            if len(selected) == maximum:
                break
    return selected


def scan_logs(
    log_root: Path,
    log_entries: list[dict[str, object]],
    canaries: list[Canary],
    *,
    fresh_after: object | None,
    parse_timestamp: Callable[[str], object | None],
) -> tuple[list[dict[str, object]], dict[str, object], bool]:
    """Scan snapshotted logs line-by-line; return redacted matches and coverage."""
    matches: list[dict[str, object]] = []
    parse_all_structured_events = fresh_after is not None
    coverage: dict[str, object] = {
        "log_files_scanned": 0,
        "log_bytes_scanned": 0,
        "log_lines_scanned": 0,
        "structured_event_metadata_mode": (
            "full" if parse_all_structured_events else "matches_only"
        ),
        "structured_events_parsed": 0 if parse_all_structured_events else None,
        "unparsed_lines": 0 if parse_all_structured_events else None,
    }
    matcher = _build_matcher(canaries)
    fresh_log_seen = False
    for entry in log_entries:
        if entry.get("accessibility") != "readable":
            continue
        relative = str(entry["snapshot_path"])
        path = log_root.parent / relative
        coverage["log_files_scanned"] += 1
        coverage["log_bytes_scanned"] += int(entry.get("snapshot_file_size") or 0)
        log_date = extract_log_date_from_filename(str(entry.get("source_path") or ""))
        first: str | None = None
        last: str | None = None
        line_count = 0
        parsed_count = 0
        unparsed_count = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for number, raw_line in enumerate(handle, start=1):
                line_count += 1
                coverage["log_lines_scanned"] += 1
                matched = matcher(normalize_text(raw_line))
                parsed = (
                    parse_structured_log_line(raw_line, log_date=log_date)
                    if parse_all_structured_events or matched
                    else None
                )
                if parse_all_structured_events and parsed is None:
                    unparsed_count += 1
                    coverage["unparsed_lines"] = (
                        int(coverage["unparsed_lines"] or 0) + 1
                    )
                elif parse_all_structured_events and parsed is not None:
                    parsed_count += 1
                    coverage["structured_events_parsed"] = (
                        int(coverage["structured_events_parsed"] or 0) + 1
                    )
                if parse_all_structured_events and parsed is not None:
                    timestamp = str(parsed.get("timestamp_utc") or "")
                    if timestamp:
                        first = min(first or timestamp, timestamp)
                        last = max(last or timestamp, timestamp)
                for canary, match_type, window_count in matched:
                    matches.append(
                        {
                            "canary_sha256": canary.sha256,
                            "canary_class": canary.canary_class,
                            "report_identity": canary.report_identity,
                            "relative_log_path": str(entry["source_path"]),
                            "line_number": number,
                            "logger_name": str(parsed.get("logger_name") or "")
                            if parsed
                            else "",
                            "module": str(parsed.get("module") or "") if parsed else "",
                            "event": str(parsed.get("event") or "") if parsed else "",
                            "match_type": match_type,
                            "matched_window_count": window_count,
                        }
                    )
        entry["total_line_count"] = line_count
        entry["structured_event_metadata_mode"] = coverage[
            "structured_event_metadata_mode"
        ]
        entry["parsed_structured_event_count"] = (
            parsed_count if parse_all_structured_events else None
        )
        entry["unparsed_line_count"] = (
            unparsed_count if parse_all_structured_events else None
        )
        entry["first_parsed_event_timestamp"] = first
        entry["last_parsed_event_timestamp"] = last
        timestamps = [entry.get("source_modified_at"), first, last]
        if fresh_after is not None and any(
            parsed_time is not None and parsed_time >= fresh_after
            for parsed_time in (
                parse_timestamp(str(item)) for item in timestamps if item
            )
        ):
            fresh_log_seen = True
    return matches, coverage, fresh_log_seen


def _build_matcher(
    canaries: list[Canary],
) -> Callable[[str], list[tuple[Canary, str, int]]]:
    """Compile bounded exact/window patterns once for the whole log corpus."""
    if not canaries:
        return lambda _: []
    full_by_text: dict[str, list[Canary]] = defaultdict(list)
    windows_by_text: dict[str, list[Canary]] = defaultdict(list)
    for canary in canaries:
        full_by_text[canary.normalized_text].append(canary)
        for window in _windows(canary.normalized_text):
            windows_by_text[window].append(canary)
    find_texts = _build_substring_matcher((*full_by_text, *windows_by_text))

    def find_matches(record: str) -> list[tuple[Canary, str, int]]:
        matched_texts = find_texts(record)
        full_canaries = {
            id(canary): canary
            for text in sorted(matched_texts & full_by_text.keys())
            for canary in full_by_text[text]
        }
        window_counts: dict[int, tuple[Canary, set[str]]] = {}
        for window in sorted(matched_texts & windows_by_text.keys()):
            for canary in windows_by_text[window]:
                _, seen = window_counts.setdefault(id(canary), (canary, set()))
                seen.add(window)
        results = [(canary, "full", 0) for canary in full_canaries.values()]
        results.extend(
            (canary, "windowed", len(windows))
            for canary_id, (canary, windows) in window_counts.items()
            if canary_id not in full_canaries
            and len(windows) >= WINDOW_MATCHES_REQUIRED
        )
        return results

    return find_matches


def _build_substring_matcher(
    patterns: Iterable[str],
) -> Callable[[str], set[str]]:
    """Return an Aho-Corasick matcher for bounded canary and window patterns."""
    transitions: list[dict[str, int]] = [{}]
    failures = [0]
    outputs: list[set[str]] = [set()]
    for pattern in sorted(set(patterns)):
        state = 0
        for character in pattern:
            next_state = transitions[state].get(character)
            if next_state is None:
                next_state = len(transitions)
                transitions[state][character] = next_state
                transitions.append({})
                failures.append(0)
                outputs.append(set())
            state = next_state
        outputs[state].add(pattern)

    queue: deque[int] = deque(transitions[0].values())
    while queue:
        state = queue.popleft()
        for character, next_state in transitions[state].items():
            queue.append(next_state)
            fallback = failures[state]
            while fallback and character not in transitions[fallback]:
                fallback = failures[fallback]
            failures[next_state] = transitions[fallback].get(character, 0)
            outputs[next_state].update(outputs[failures[next_state]])

    def find_matches(record: str) -> set[str]:
        state = 0
        matches: set[str] = set()
        for character in record:
            while state and character not in transitions[state]:
                state = failures[state]
            state = transitions[state].get(character, 0)
            if outputs[state]:
                matches.update(outputs[state])
        return matches

    return find_matches


def _match(canary: str, record: str) -> tuple[str, int]:
    if canary in record:
        return "full", 0
    windows = _windows(canary)
    count = sum(window in record for window in windows)
    if count >= WINDOW_MATCHES_REQUIRED:
        return "windowed", count
    return "", 0


def _windows(value: str) -> tuple[str, ...]:
    if len(value) < WINDOW_CHARACTERS * 2:
        return ()
    middle = max(0, (len(value) - WINDOW_CHARACTERS) // 2)
    return tuple(
        dict.fromkeys(
            (
                value[:WINDOW_CHARACTERS],
                value[middle : middle + WINDOW_CHARACTERS],
                value[-WINDOW_CHARACTERS:],
            )
        )
    )


def _report_identity(relative_path: str) -> str:
    parts = Path(relative_path).parts
    return parts[0] if parts else "unknown"
