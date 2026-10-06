# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


def test_run_report_pipeline_uses_workflow_retry_policy(
    caplog, external_boundary_mocks_only
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.report_pipeline_orchestrator")
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    calls = {"count": 0}
    sleep_calls: list[float] = []
    catalog = workflow_control.default_workflow_control_settings()

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
        calls["count"] += 1
        if calls["count"] == 1:
            raise AppError(
                code="openai_request_failed",
                message="retry once",
                retryable=True,
            )
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path="./out/a.html",
            status="processed",
        )

    external_boundary_mocks_only.setattr(
        retry_orch.random, "uniform", lambda _a, _b: 0.0
    )
    external_boundary_mocks_only.setattr(
        orch.time, "sleep", lambda seconds: sleep_calls.append(float(seconds))
    )

    response = orch.run_report_pipeline(
        file,
        local_pdf_path="./cache/a.pdf",
        settings=_settings(),
        md5="md5",
        ctx=_ctx(),
        retries=0,
        generate_report_fn=_gen,
        workflow_control_settings=catalog,
    )

    assert response.status == "processed"
    assert calls["count"] == 2
    assert sleep_calls == [1.0]
    events = _events(caplog)
    starts = [event for event in events if event["event"] == "report_pipeline_start"]
    assert starts[-1]["fields"]["retry_policy_id"] == (
        "report_generation.report_pipeline.v1"
    )


def test_report_pipeline_orchestrator_does_not_use_signature_reflection() -> None:
    source = orch.__loader__.get_source(orch.__name__)

    assert source is not None
    assert "inspect.signature" not in source


def test_report_generation_client_bundle_rejects_missing_client(
    assert_app_error,
) -> None:
    bundle = ReportGenerationClientBundle(
        schema_version="1.0",
        source_ocr_client=object(),
        taxonomy_client=object(),
        category_fit_client=object(),
        evidence_pack_client=object(),
        artifact_client=object(),
        validation_client=object(),
        regeneration_client=object(),
        figure_caption_client=None,
    )

    with pytest.raises(AppError) as exc_info:
        bundle.validate()

    assert_app_error(
        exc_info.value,
        code="report_generation_client_bundle_invalid",
        retryable=False,
        severity="error",
    )
    assert exc_info.value.context["field"] == "figure_caption_client"


def test_run_report_pipeline_preflights_before_model_client_construction(
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="f1",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    model_client_calls = {"count": 0}

    def _build_client(*_args, **_kwargs):
        model_client_calls["count"] += 1
        raise AssertionError("model clients must not be built after blocking preflight")

    blocking_check = PipelinePreflightCheck(
        schema_version="1.0",
        check_name="openai_api_key",
        status="blocker",
        code="openai_missing_api_key",
        message="OpenAI API key is missing",
        next_action="set_OPENAI_API_KEY",
        auto_fix_applied=False,
        metadata={},
    )
    blocking_report = PipelinePreflightReport(
        schema_version="1.0",
        workflow="report_pipeline",
        planned_side_effects=["pdf", "model"],
        passed=False,
        expensive_side_effects_allowed=False,
        blocker_count=1,
        warning_count=0,
        auto_fixed_count=0,
        checks=[blocking_check],
        blockers=[blocking_check],
        warnings=[],
        auto_fixable_issues=[],
        next_actions=["set_OPENAI_API_KEY", "rerun_preflight"],
    )

    external_boundary_mocks_only.setattr(
        orch.llm_service, "build_client_for_settings", _build_client
    )

    with pytest.raises(AppError) as exc_info:
        orch.run_report_pipeline(
            file,
            local_pdf_path="./cache/a.pdf",
            settings=_settings(),
            md5="md5",
            ctx=_ctx(),
            retries=0,
            generate_report_fn=lambda *_args, **_kwargs: None,
            preflight_fn=lambda *_args, **_kwargs: blocking_report,
        )

    assert_app_error(
        exc_info.value,
        code="pipeline_preflight_blocked",
        retryable=False,
        severity="error",
    )
    assert model_client_calls["count"] == 0
