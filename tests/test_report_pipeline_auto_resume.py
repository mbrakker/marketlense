from __future__ import annotations

from src.contracts.drive import DriveFile
from src.contracts.ingest import IngestOutcome
from src.orchestrators import report_pipeline_orchestrator as orch
from src.utils.errors import AppError

from tests.test_report_pipeline_orchestrator import _ctx, _settings


def test_auto_resume_falls_back_to_fresh_when_no_checkpoint() -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls: list[str] = []

    def _gen(
        file,
        local_pdf_path,
        settings,
        md5,
        ctx,
        *,
        client_bundle,
        resume_from_stage=None,
    ):
        del local_pdf_path, settings, ctx, client_bundle
        calls.append(str(resume_from_stage or ""))
        if resume_from_stage == "latest_safe":
            raise AppError(
                code="report_pipeline_checkpoint_missing",
                message="No checkpoint",
                retryable=False,
            )
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path="./out/a.html",
            status="processed",
        )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=0,
        generate_report_fn=_gen,
        auto_resume_from_latest_safe=True,
    )

    assert response.status == "processed"
    assert calls == ["latest_safe", ""]
