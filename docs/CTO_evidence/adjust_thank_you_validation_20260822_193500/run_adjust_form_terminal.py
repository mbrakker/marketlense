"""Run the retained Adjust candidate until acquisition reaches a terminal state.

This evidence runner deliberately does not invoke mailbox acquisition.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.config import ConfigLoadRequest
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.run_context import RunContext
from src.services.browser_report_download_service import download_report_with_browser_use
from src.services.config_service import load_browser_download_settings
from src.utils.errors import AppError


EVIDENCE_DIR = Path(__file__).resolve().parent
RUN_ID = "adjust_thank_you_validation_20260822_224000"


def main() -> None:
    ctx = RunContext(
        schema_version="1.0",
        run_id=RUN_ID,
        task_id="adjust_all_form_terminal",
        span_id="acquisition",
    )
    settings = load_browser_download_settings(
        ConfigLoadRequest(
            schema_version="1.0",
            path="src/config/app.adjust_thank_you_validation_20260822_210757.yaml",
        ),
        ctx,
    )
    trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://www.adjust.com/resources/ebooks/all",
        title="https://www.adjust.com/resources/ebooks/all",
        discovered_on_page_number=1,
        source_page_urls=["https://www.adjust.com/resources/ebooks"],
        discovery_provenances=["retained_failed_cohort"],
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://www.adjust.com/resources/ebooks/all",
        attempt_url="https://www.adjust.com/resources/ebooks/all",
        settings=settings,
        route_family_hint="browser_email_form",
        source_page_url_hint="https://www.adjust.com/resources/ebooks",
        report_title="https://www.adjust.com/resources/ebooks/all",
        publisher_name="Adjust",
        candidate_trace=trace,
    )
    try:
        result = download_report_with_browser_use(request, ctx)
        payload = {
            "status": "completed",
            "outcome": result.outcome,
            "route_family": result.route_family,
            "route_status": result.route_status,
            "final_page_url": result.final_page_url,
            "resolved_target_url": result.resolved_target_url,
            "confirmation_signal_labels": list(
                result.confirmation_evidence.signal_labels
            ),
            "terminal_artifact_validation_status": (
                result.terminal_evidence.artifact_validation_status
            ),
            "route_step_count": len(result.route_steps),
        }
    except AppError as exc:
        payload = {
            "status": "app_error",
            "code": exc.code,
            "retryable": exc.retryable,
        }
    (EVIDENCE_DIR / "terminal_result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
