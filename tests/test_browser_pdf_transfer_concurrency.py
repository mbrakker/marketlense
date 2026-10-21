from __future__ import annotations

import multiprocessing
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty

from src.contracts.run_context import RunContext
from src.services._browser_report_download._http.pdf_transfer import (
    download_pdf_from_url,
)
from src.services._browser_report_download.artifact_paths import windows_path_units
from src.services._browser_report_download.request import (
    create_download_workspace,
    prepare_download_dir,
)
from src.utils.errors import AppError


def _canonical_windows_path(path: Path) -> str:
    normalized = os.path.normcase(os.path.normpath(str(path)))
    if normalized.startswith("\\\\?\\"):
        normalized = normalized[4:]
    return normalized.rstrip("\\/")


class _GatedPdfHandler(BaseHTTPRequestHandler):
    payloads = {
        "/a.pdf": b"%PDF-1.7\n" + (b"A" * 1024 * 1024) + b"\n%%EOF\n",
        "/b.pdf": b"%PDF-1.7\n" + (b"B" * 1024 * 1024) + b"\n%%EOF\n",
    }
    first_chunk_barrier = threading.Barrier(2)
    first_chunks_ready = threading.Event()
    release_second_chunks = threading.Event()

    def do_GET(self) -> None:  # noqa: N802
        payload = self.payloads.get(self.path)
        if payload is None:
            self.send_error(404)
            return
        midpoint = len(payload) // 2
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload[:midpoint])
        self.wfile.flush()
        try:
            self.first_chunk_barrier.wait(timeout=15)
        except threading.BrokenBarrierError:
            return
        self.first_chunks_ready.set()
        if not self.release_second_chunks.wait(timeout=15):
            return
        self.wfile.write(payload[midpoint:])
        self.wfile.flush()

    def log_message(self, _format: str, *_args: object) -> None:
        return None


def _download_in_process(
    pdf_url: str,
    destination_path: str,
    result_queue,
) -> None:
    try:
        download_pdf_from_url(
            pdf_url=pdf_url,
            destination_path=Path(destination_path),
            timeout_seconds=20.0,
            ctx=RunContext(
                schema_version="1.0",
                run_id="concurrency-run",
                task_id="concurrency-task",
                span_id="concurrency-span",
            ),
            normalized_url=pdf_url,
        )
    except AppError as exc:
        result_queue.put(("error", exc.code))
    except BaseException as exc:  # pragma: no cover - process diagnostic guard
        result_queue.put(("exception", type(exc).__name__))
    else:
        result_queue.put(("ok", ""))


def _create_workspace_in_process(
    root_dir: str,
    normalized_url: str,
    allocation_barrier,
    result_queue,
) -> None:
    try:
        stable_dir = prepare_download_dir(
            root_dir=root_dir,
            normalized_url=normalized_url,
        )
        allocation_barrier.wait(timeout=15)
        workspace = create_download_workspace(stable_dir)
        artifact = workspace / "owned.txt"
        artifact.write_text("owned", encoding="utf-8")
        result_queue.put(("ok", str(workspace)))
    except BaseException as exc:  # pragma: no cover - process diagnostic guard
        result_queue.put(("exception", type(exc).__name__))


def test_concurrent_pdf_transfers_use_independent_owned_stages(tmp_path: Path) -> None:
    _GatedPdfHandler.first_chunk_barrier = threading.Barrier(2)
    _GatedPdfHandler.first_chunks_ready = threading.Event()
    _GatedPdfHandler.release_second_chunks = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _GatedPdfHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    destination = tmp_path / "report.pdf"
    port = server.server_address[1]
    processes = [
        context.Process(
            target=_download_in_process,
            args=(
                f"http://127.0.0.1:{port}/{name}.pdf",
                str(destination),
                result_queue,
            ),
        )
        for name in ("a", "b")
    ]

    try:
        for process in processes:
            process.start()
        assert _GatedPdfHandler.first_chunks_ready.wait(timeout=15)

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if len(list(tmp_path.glob("*.part"))) == 2:
                break
            threading.Event().wait(0.01)
        assert len(list(tmp_path.glob("*.part"))) == 2
    finally:
        _GatedPdfHandler.release_second_chunks.set()
        for process in processes:
            process.join(timeout=30)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=15)

    results = []
    for _ in processes:
        try:
            results.append(result_queue.get(timeout=10))
        except Empty:
            results.append(("missing", ""))

    assert all(process.exitcode == 0 for process in processes)
    assert [kind for kind, _code in results].count("ok") == 1
    assert results.count(("error", "browser_download_pdf_commit_conflict")) == 1
    assert destination.read_bytes() in _GatedPdfHandler.payloads.values()
    assert list(tmp_path.glob("*.part")) == []


def test_concurrent_same_url_workspace_allocations_are_independent(
    tmp_path: Path,
) -> None:
    context = multiprocessing.get_context("spawn")
    allocation_barrier = context.Barrier(2)
    result_queue = context.Queue()
    normalized_url = "https://example.com/concurrent-report"
    processes = [
        context.Process(
            target=_create_workspace_in_process,
            args=(str(tmp_path), normalized_url, allocation_barrier, result_queue),
        )
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    results = []
    for _ in processes:
        try:
            results.append(result_queue.get(timeout=10))
        except Empty:
            results.append(("missing", ""))
    for process in processes:
        process.join(timeout=30)

    assert all(process.exitcode == 0 for process in processes)
    workspace_paths = [Path(path) for kind, path in results if kind == "ok"]
    assert len(workspace_paths) == 2
    assert workspace_paths[0] != workspace_paths[1]
    assert _canonical_windows_path(
        workspace_paths[0].parent
    ) == _canonical_windows_path(workspace_paths[1].parent)
    assert all(
        windows_path_units(path) <= 240 and (path / "owned.txt").read_text() == "owned"
        for path in workspace_paths
    )
