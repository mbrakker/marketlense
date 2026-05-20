from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.contracts.config import ConfigLoadRequest
from src.contracts.logging import LoggingSetupRequest
from src.orchestrators.publish_orchestrator import run_publish
from src.services.config_service import load_publish_settings
from src.services.logging_service import setup_logging
from src.utils.logging import new_run_context


HTML_PATHS = ["out/guide-how-to-improve-your-b2b-site-performance-pdf.html"]


def main() -> int:
    ctx = new_run_context(task_id="live_publish_contentsquare_retry")
    setup_logging(LoggingSetupRequest(schema_version="1.0"), ctx)
    settings = load_publish_settings(ConfigLoadRequest(schema_version="1.0", path=""), ctx)
    outcomes = run_publish(settings, html_paths=HTML_PATHS, ctx=ctx)
    payload = [asdict(outcome) for outcome in outcomes]
    output_path = ROOT / ".codex_tmp" / "live_run_20260520" / "publish_retry_contentsquare.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if all(item.get("status") in {"published", "skipped"} for item in payload) else 1


if __name__ == "__main__":
    raise SystemExit(main())
