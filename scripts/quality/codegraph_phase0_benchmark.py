"""Run the narrow, reproducible CodeGraph Phase-0 retrieval comparison.

The benchmark measures tool retrieval only.  It deliberately does not claim to
measure model reasoning, tokens billed by a provider, or production behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _percentage_reduction(before: float, after: float) -> float:
    if before <= 0:
        return 0.0
    return round((before - after) * 100 / before, 2)


def evaluate_phase0(
    *,
    native_rows: tuple[dict[str, Any], ...],
    codegraph_rows: tuple[dict[str, Any], ...],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    """Score paired retrieval measurements against the Phase-0 guardrails."""
    native_by_id = {str(row["case_id"]): row for row in native_rows}
    codegraph_by_id = {str(row["case_id"]): row for row in codegraph_rows}
    failures: list[str] = []

    if set(native_by_id) != set(codegraph_by_id):
        failures.append("case_ids_do_not_match")

    for case_id in sorted(set(native_by_id) & set(codegraph_by_id)):
        native = native_by_id[case_id]
        codegraph = codegraph_by_id[case_id]
        if (
            float(codegraph["relevant_file_recall"])
            < float(native["relevant_file_recall"])
            or float(codegraph["relevant_file_recall"]) < 1.0
        ):
            failures.append(f"missed_relevant_files:{case_id}")
        if codegraph["structural_conclusion"] != "correct":
            failures.append(f"wrong_structural_conclusion:{case_id}")

    def total(rows: tuple[dict[str, Any], ...], field: str) -> float:
        return sum(float(row[field]) for row in rows)

    aggregate = {
        "native_retrieval_calls": total(native_rows, "retrieval_calls"),
        "codegraph_retrieval_calls": total(codegraph_rows, "retrieval_calls"),
        "native_token_proxy": total(native_rows, "token_proxy"),
        "codegraph_token_proxy": total(codegraph_rows, "token_proxy"),
        "native_elapsed_ms": total(native_rows, "elapsed_ms"),
        "codegraph_elapsed_ms": total(codegraph_rows, "elapsed_ms"),
    }
    aggregate["retrieval_calls_reduction_percent"] = _percentage_reduction(
        aggregate["native_retrieval_calls"], aggregate["codegraph_retrieval_calls"]
    )
    aggregate["token_proxy_reduction_percent"] = _percentage_reduction(
        aggregate["native_token_proxy"], aggregate["codegraph_token_proxy"]
    )
    aggregate["elapsed_time_reduction_percent"] = _percentage_reduction(
        aggregate["native_elapsed_ms"], aggregate["codegraph_elapsed_ms"]
    )

    for field, failure in (
        ("retrieval_calls_reduction_percent", "retrieval_calls_target_not_met"),
        ("token_proxy_reduction_percent", "token_proxy_target_not_met"),
        ("elapsed_time_reduction_percent", "elapsed_time_target_not_met"),
    ):
        if aggregate[field] < float(thresholds[field]):
            failures.append(failure)

    return {"passed": not failures, "failures": failures, "aggregate": aggregate}


def _run(command: list[str], *, root: Path) -> tuple[str, int]:
    started = time.perf_counter_ns()
    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_ms = round((time.perf_counter_ns() - started) / 1_000_000)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n{output}"
        )
    return output, elapsed_ms


def _token_proxy(value: str) -> int:
    """Use the documented, deterministic four-bytes-per-token proxy."""
    return (len(value.encode("utf-8")) + 3) // 4


def native_discovery_files(discovery_output: str) -> tuple[str, ...]:
    """Return only repository-relative file paths emitted by native discovery.

    Phase-0 intentionally measures discovery output, not evaluator knowledge.
    The relevant-file list is used only afterwards to calculate diagnostic recall.
    """
    files: list[str] = []
    for raw_line in discovery_output.splitlines():
        candidate = raw_line.strip().replace("\\", "/")
        if candidate.startswith(("src/", "tests/", "scripts/", "docs/", ".codex/")):
            files.append(candidate)
    return tuple(dict.fromkeys(files))


def discovery_files_from_text(output: str) -> tuple[str, ...]:
    """Extract repository-relative paths from MCP text without evaluator data."""
    matches = re.findall(
        r"(?<![\w./])((?:src|tests|scripts|docs|\.codex)/[A-Za-z0-9_./-]+)",
        output.replace("\\", "/"),
    )
    return tuple(dict.fromkeys(match.rstrip(".,:;`)") for match in matches))


def _mcp_text(message: dict[str, Any]) -> str:
    """Extract text content from a successful MCP tools/call response."""
    result = message.get("result")
    content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, list):
        raise RuntimeError("CodeGraph MCP response did not contain tool content")
    return "\n".join(
        item["text"]
        for item in content
        if isinstance(item, dict)
        and item.get("type") == "text"
        and isinstance(item.get("text"), str)
    )


class _McpSession:
    """Minimal stdio MCP client used solely for the one CodeGraph tool."""

    def __init__(self, *, command: str, root: Path) -> None:
        self._process = subprocess.Popen(
            [command, "serve", "--mcp"],
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None:
            raise RuntimeError("CodeGraph MCP did not expose stdio streams")
        self._messages: queue.Queue[str] = queue.Queue()
        self._next_request_id = 1
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._messages.put(line)

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_request_id
        self._next_request_id += 1
        assert self._process.stdin is not None
        self._process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            + "\n"
        )
        self._process.stdin.flush()
        while True:
            try:
                message = json.loads(self._messages.get(timeout=30))
            except queue.Empty as error:
                raise RuntimeError(
                    f"Timed out waiting for CodeGraph MCP {method}"
                ) from error
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CodeGraph MCP {method} failed: {message['error']}")
            return message

    def start(self) -> int:
        started = time.perf_counter_ns()
        self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "marketlense-phase0", "version": "1.0"},
            },
        )
        assert self._process.stdin is not None
        self._process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        self._process.stdin.flush()
        return round((time.perf_counter_ns() - started) / 1_000_000)

    def explore(self, *, query: str, max_files: int) -> tuple[str, int]:
        started = time.perf_counter_ns()
        response = self._request(
            "tools/call",
            {
                "name": "codegraph_explore",
                "arguments": {"query": query, "maxFiles": max_files},
            },
        )
        return _mcp_text(response), round(
            (time.perf_counter_ns() - started) / 1_000_000
        )

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        if os.name == "nt":
            # The Windows .cmd launcher can leave the server as a child process.
            # Terminate only the process tree created for this benchmark run.
            subprocess.run(
                ["taskkill", "/PID", str(self._process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )


def _native_row(case: dict[str, Any], *, root: Path) -> dict[str, Any]:
    started = time.perf_counter_ns()
    discovery_output, _ = _run(
        [str(value) for value in case["native_discovery_command"]], root=root
    )
    files_discovered = native_discovery_files(discovery_output)
    readable_files = [
        relative_path
        for relative_path in files_discovered
        if (root / relative_path).is_file()
    ]
    relevant_files = [str(value) for value in case["relevant_files"]]
    source_output = "\n".join(
        (root / relative_path).read_text(encoding="utf-8")
        for relative_path in readable_files
    )
    markers = [str(value) for value in case["required_markers"]]
    relevant_discovered = [
        relative_path
        for relative_path in relevant_files
        if relative_path in files_discovered
    ]
    return {
        "case_id": case["id"],
        "relevant_file_recall": len(relevant_discovered) / len(relevant_files),
        "structural_conclusion": (
            "correct"
            if len(relevant_discovered) == len(relevant_files)
            and all(marker in source_output for marker in markers)
            else "incorrect"
        ),
        "retrieval_calls": 1 + len(readable_files),
        "source_read_calls": len(readable_files),
        "response_bytes": len((discovery_output + source_output).encode("utf-8")),
        "token_proxy": _token_proxy(discovery_output + source_output),
        "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000),
        "files_discovered": files_discovered,
    }


def _codegraph_row(case: dict[str, Any], *, session: _McpSession) -> dict[str, Any]:
    output, elapsed_ms = session.explore(
        query=str(case["codegraph_query"]),
        max_files=int(case.get("codegraph_max_files", 3)),
    )
    normalized_output = output.replace("\\", "/")
    relevant_files = [str(value) for value in case["relevant_files"]]
    files_discovered = discovery_files_from_text(output)
    relevant_discovered = [
        relative_path
        for relative_path in relevant_files
        if relative_path in files_discovered
    ]
    markers = [str(value) for value in case["required_markers"]]
    recall = len(relevant_discovered) / len(relevant_files)
    return {
        "case_id": case["id"],
        "relevant_file_recall": recall,
        "structural_conclusion": (
            "correct"
            if recall == 1.0 and all(marker in normalized_output for marker in markers)
            else "not_verified"
        ),
        "retrieval_calls": 1,
        "source_read_calls": 0,
        "response_bytes": len(output.encode("utf-8")),
        "token_proxy": _token_proxy(output),
        "elapsed_ms": elapsed_ms,
        "files_discovered": files_discovered,
    }


def _load_spec(path: Path) -> dict[str, Any]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != "1.0" or not isinstance(spec.get("cases"), list):
        raise ValueError(f"Unsupported Phase-0 benchmark specification: {path}")
    return spec


def run_phase0(
    spec: dict[str, Any], *, root: Path, codegraph_command: str
) -> dict[str, Any]:
    cases = tuple(spec["cases"])
    native_rows = tuple(_native_row(case, root=root) for case in cases)
    session = _McpSession(command=codegraph_command, root=root)
    try:
        server_startup_ms = session.start()
        codegraph_rows = tuple(_codegraph_row(case, session=session) for case in cases)
    finally:
        session.close()
    report = evaluate_phase0(
        native_rows=native_rows,
        codegraph_rows=codegraph_rows,
        thresholds=spec["thresholds"],
    )
    return {
        "schema_version": "1.0",
        "benchmark_kind": "codegraph_phase0_retrieval_comparison",
        "repository_commit": spec["repository_commit"],
        "codegraph_release": spec["codegraph_release"],
        "measurement_note": (
            "This is a retrieval-only diagnostic, not an adoption decision. "
            "Token values "
            "are a deterministic response-byte proxy (ceil(bytes / 4)); provider token "
            "usage and cost are not available in this tool-only run."
        ),
        "thresholds": spec["thresholds"],
        "codegraph_server_startup_ms_excluded_from_query_timing": server_startup_ms,
        "native_rows": native_rows,
        "codegraph_rows": codegraph_rows,
        **report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spec", default="benchmarks/agent-engineering/codegraph-phase0.json"
    )
    parser.add_argument("--output", default="")
    parser.add_argument("--codegraph", required=True)
    args = parser.parse_args()
    report = run_phase0(
        _load_spec((ROOT / args.spec).resolve()),
        root=ROOT,
        codegraph_command=args.codegraph,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = (ROOT / args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
