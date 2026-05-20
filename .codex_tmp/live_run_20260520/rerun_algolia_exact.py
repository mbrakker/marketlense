from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.drive import DriveFile
from src.contracts.logging import LoggingSetupRequest
from src.orchestrators.ingest_orchestrator import IngestBatchDependencies, run_ingest
from src.services.config_service import build_ingest_settings, load_settings
from src.services.logging_service import setup_logging
from src.utils.logging import new_run_context


ROOT = Path(".codex_tmp/live_run_20260520")
OUTCOME_PATH = ROOT / "ingest_fix_algolia_exact.json"


def main() -> int:
    ctx = new_run_context(task_id="live_algolia_ocr_exact")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    app_settings = load_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    settings = build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
        ctx,
    )
    target = DriveFile(
        schema_version="1.0",
        file_id="1nlUXikmhL3sVKzp3TrjqEVVkrzCcy3zB",
        name="multi-signal-ranking-transforming-ranking-for-ecommerce-search.pdf",
        modified_time=None,
        md5_checksum="21d25be395a195a837ac578ffa6f16a7",
        mime_type="application/pdf",
    )
    default_deps = IngestBatchDependencies.default()

    def list_target(_request, _ctx):
        return [target]

    def force_not_skipped(files, _state_db, _ctx):
        return {
            (file.file_id, (file.md5_checksum or "").strip()): False
            for file in files
        }

    deps = IngestBatchDependencies(
        list_pdfs=list_target,
        batch_should_skip=force_not_skipped,
        process_file=default_deps.process_file,
        thread_pool_executor_factory=default_deps.thread_pool_executor_factory,
        flush_uncategorized_tags=default_deps.flush_uncategorized_tags,
    )
    outcomes = run_ingest(
        settings,
        folder_id="exact-file-rerun",
        limit=1,
        ctx=ctx,
        dependencies=deps,
    )
    payload = [asdict(outcome) for outcome in outcomes]
    OUTCOME_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if any(outcome.status == "error" for outcome in outcomes):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
