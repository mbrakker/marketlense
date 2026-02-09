import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.orchestrators import ingest_orchestrator as orch


class _DummyExecutor:
    def __init__(self, max_workers: int, captured: dict) -> None:
        self.max_workers = max_workers
        captured["max_workers"] = max_workers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future


class TestIngestParallel(unittest.TestCase):
    def test_parallel_executor_orders_results(self) -> None:
        settings = IngestSettings(
            schema_version="1.0",
            google_sa_path="sa.json",
            gdrive_folder_id="folder",
            openai_api_key="key",
            openai_model="gpt-5",
            batch_limit=2,
            output_dir="./out",
            cache_dir="./cache",
            state_db="./state/index.sqlite",
            reports_db="./state/reports.sqlite",
            category_mapping_path="./src/config/category-mappings.yaml",
            cover_style_path="./src/config/cover-styles.yaml",
            ingest_lock_path="./state/ingest.lock",
            ingest_lock_ttl_seconds=7200.0,
            temperature=1.0,
            ingest_worker_limit=2,
        )
        files = [
            DriveFile(schema_version="1.0", file_id="file_a", name="a.pdf", modified_time=None, md5_checksum="md5a"),
            DriveFile(schema_version="1.0", file_id="file_b", name="b.pdf", modified_time=None, md5_checksum="md5b"),
        ]
        outcomes = [
            IngestOutcome(
                schema_version="1.0",
                file_id="file_a",
                name="a.pdf",
                md5="md5a",
                html_path="out/a.html",
                status="processed",
            ),
            IngestOutcome(
                schema_version="1.0",
                file_id="file_b",
                name="b.pdf",
                md5="md5b",
                html_path="out/b.html",
                status="processed",
            ),
        ]

        def _fake_process(file, index, settings, root_ctx):
            return orch._FileProcessResult(index=index, outcome=outcomes[index], processed=1, had_error=False)

        captured: dict[str, int] = {}

        def _executor_factory(max_workers):
            return _DummyExecutor(max_workers, captured)

        with patch.object(orch, "ThreadPoolExecutor", side_effect=_executor_factory):
            with patch.object(orch, "acquire_lock", return_value=SimpleNamespace(acquired=True, lock=SimpleNamespace(lock_path=settings.ingest_lock_path, owner_id="owner", pid=123), conflict=None)):
                with patch.object(orch, "release_lock", return_value=None):
                    with patch.object(orch, "flush_uncategorized_tags", return_value=None):
                        with patch.object(orch, "check_state_db_access", return_value=SimpleNamespace(accessible=True, locked=False)):
                            with patch.object(orch, "check_report_db_access", return_value=SimpleNamespace(accessible=True, locked=False)):
                                with patch.object(orch, "list_pdfs", return_value=files):
                                    with patch.object(orch, "state_already_processed", return_value=False):
                                        with patch.object(orch, "_process_file", side_effect=_fake_process):
                                            results = orch.run_ingest(settings, limit=2)

        self.assertEqual(2, captured.get("max_workers"))
        self.assertEqual(["file_a", "file_b"], [r.file_id for r in results])


if __name__ == "__main__":
    unittest.main()
