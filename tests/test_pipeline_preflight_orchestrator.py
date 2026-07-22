from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from dataclasses import FrozenInstanceError

from src.contracts.drive import DriveWritePreflightResponse
from src.contracts.files import (
    DeleteFileResponse,
    FileStatResponse,
    WriteBytesResponse,
)
from src.contracts.pipeline_preflight import PipelinePreflightRequest
from src.contracts.prompts import PromptSet, PromptTemplate
from src.contracts.run_context import RunContext
from src.orchestrators.pipeline_preflight_orchestrator import (
    PipelinePreflightDependencies,
    assert_expensive_side_effects_allowed,
    report_pipeline_prompt_namespaces,
    run_pipeline_preflight,
)
from src.utils.errors import AppError
from src.utils.model_resolver import registered_production_llm_namespaces


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _prompt_set(namespace: str) -> PromptSet:
    return PromptSet(
        schema_version="1.0",
        system=PromptTemplate(
            schema_version="1.0",
            path=f"src/prompts/{namespace}/system.yaml",
            text="system",
            sha256="s" * 64,
        ),
        user=PromptTemplate(
            schema_version="1.0",
            path=f"src/prompts/{namespace}/user.yaml",
            text="user",
            sha256="u" * 64,
        ),
    )


def _events(caplog) -> list[dict]:
    events: list[dict] = []
    for record in caplog.records:
        try:
            payload = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if payload.get("module") == "market_lense.pipeline_preflight_orchestrator":
            events.append(payload)
    return events


def _deps(tmp_path: Path, *, prompt_error: AppError | None = None):
    def _file_stat(req, ctx):
        path = Path(req.path)
        return FileStatResponse(
            schema_version="1.0",
            path=req.path,
            exists=path.exists(),
            is_file=path.is_file(),
            is_dir=path.is_dir(),
            size_bytes=path.stat().st_size
            if path.exists() and path.is_file()
            else None,
            mtime_utc=path.stat().st_mtime if path.exists() else None,
            md5=None,
        )

    def _write_bytes(req, ctx):
        path = Path(req.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(req.content)
        return WriteBytesResponse(
            schema_version="1.0",
            path=req.path,
            bytes_written=len(req.content),
            md5="md5",
        )

    def _delete_file(req, ctx):
        Path(req.path).unlink(missing_ok=True)
        return DeleteFileResponse(schema_version="1.0", path=req.path, deleted=True)

    def _load_prompt(req, ctx):
        if prompt_error is not None:
            raise prompt_error
        return _prompt_set(req.namespace)

    return PipelinePreflightDependencies(
        file_stat=_file_stat,
        write_bytes=_write_bytes,
        delete_file=_delete_file,
        load_prompt_set=_load_prompt,
        preflight_drive_write_access=lambda req, ctx: DriveWritePreflightResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            auth_mode=req.auth_mode,
            credentials_refreshed=False,
            scopes_verified=True,
            folder_access_verified=True,
            write_access_verified=True,
        ),
        preflight_wordpress_publish_target=lambda settings, ctx: SimpleNamespace(
            status="ok"
        ),
    )


def test_pipeline_preflight_passes_and_auto_fixes_missing_output_dirs(
    tmp_path,
    ingest_settings,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(
        logging.INFO, logger="market_lense.pipeline_preflight_orchestrator"
    )
    settings = replace(
        ingest_settings,
        output_dir=str(tmp_path / "missing-out"),
        cache_dir=str(tmp_path / "missing-cache"),
        state_db=str(tmp_path / "state" / "state.sqlite"),
        reports_db=str(tmp_path / "state" / "reports.sqlite"),
    )

    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="report_pipeline",
            planned_side_effects=["model", "ocr"],
            settings=settings,
            prompt_namespaces=["report_vs/doc_map"],
            require_llm=True,
            require_drive=False,
            require_publish=False,
            require_browser=False,
            require_live_endpoints=True,
        ),
        _ctx(),
        dependencies=_deps(tmp_path),
    )

    assert report.passed is True
    assert report.expensive_side_effects_allowed is True
    assert report.blocker_count == 0
    assert report.warning_count == 0
    assert report.auto_fixed_count >= 2
    assert "continue_pipeline" in report.next_actions
    assert {check.status for check in report.checks} >= {"pass", "auto_fixed"}

    events = _events(caplog)
    assert [event["event"] for event in events] == [
        "pipeline_preflight_start",
        "pipeline_preflight_complete",
    ]
    assert_logs_have_required_fields(events)


def test_pipeline_preflight_reports_warning_only_browser_dependency(
    tmp_path,
    ingest_settings,
) -> None:
    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="browser_acquisition",
            planned_side_effects=["browser"],
            settings=ingest_settings,
            prompt_namespaces=[],
            require_llm=False,
            require_drive=False,
            require_publish=False,
            require_browser=True,
            require_live_endpoints=False,
        ),
        _ctx(),
        dependencies=_deps(tmp_path),
    )

    assert report.passed is True
    assert report.warning_count == 1
    assert report.warnings[0].code == "browser_dependency_live_check_skipped"
    assert report.expensive_side_effects_allowed is True


def test_pipeline_preflight_blocks_missing_credential_before_side_effects(
    tmp_path,
    ingest_settings,
    assert_app_error,
) -> None:
    settings = replace(ingest_settings, openai_api_key="")
    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="report_pipeline",
            planned_side_effects=["model"],
            settings=settings,
            prompt_namespaces=["report_vs/doc_map"],
            require_llm=True,
            require_drive=False,
            require_publish=False,
            require_browser=False,
            require_live_endpoints=False,
        ),
        _ctx(),
        dependencies=_deps(tmp_path),
    )

    assert report.passed is False
    assert report.blocker_count == 1
    assert report.blockers[0].code == "openai_missing_api_key"
    assert report.blockers[0].next_action == "set_OPENAI_API_KEY"
    assert report.expensive_side_effects_allowed is False

    with pytest.raises(AppError) as exc_info:
        assert_expensive_side_effects_allowed(report, _ctx())
    assert_app_error(
        exc_info.value,
        code="pipeline_preflight_blocked",
        retryable=False,
        severity="error",
    )


def test_pipeline_preflight_blocks_incomplete_explicit_llm_policy_matrix(
    tmp_path,
    ingest_settings,
) -> None:
    settings = replace(
        ingest_settings,
        llm_execution_policies={
            "report_vs": {
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "temperature": 0.0,
                "provider_retry_count": 0,
            }
        },
    )
    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="report_pipeline",
            planned_side_effects=["model"],
            settings=settings,
            prompt_namespaces=["report_vs/doc_map"],
            require_llm=True,
            require_drive=False,
            require_publish=False,
            require_browser=False,
            require_live_endpoints=False,
        ),
        _ctx(),
        dependencies=_deps(tmp_path),
    )

    assert report.passed is False
    assert report.blockers[-1].check_name == "llm_execution_policy_matrix"
    assert report.blockers[-1].code == "llm_execution_policy_unknown_namespace"


def test_pipeline_preflight_persists_complete_resolved_policy_matrix(
    tmp_path,
    ingest_settings,
) -> None:
    settings = replace(
        ingest_settings,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state" / "state.sqlite"),
        reports_db=str(tmp_path / "state" / "reports.sqlite"),
        llm_execution_policies={
            namespace: {
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "temperature": 0.0,
                "provider_retry_count": 0,
            }
            for namespace in registered_production_llm_namespaces()
        },
    )

    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="report_pipeline",
            planned_side_effects=["model"],
            settings=settings,
            prompt_namespaces=["report_vs/doc_map"],
            require_llm=True,
            require_drive=False,
            require_publish=False,
            require_browser=False,
            require_live_endpoints=False,
        ),
        _ctx(),
        dependencies=_deps(tmp_path),
    )

    matrix_path = Path(settings.output_dir) / "preflight" / "r.llm_policy_matrix.json"
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert report.passed is True
    assert len(payload["resolved_matrix"]) == len(
        registered_production_llm_namespaces()
    )
    assert payload["resolved_matrix"][0]["provider"] == "openai"


def test_pipeline_preflight_blocks_missing_prompt_namespace(
    tmp_path,
    ingest_settings,
) -> None:
    prompt_error = AppError(
        code="prompt_not_found",
        message="missing",
        retryable=False,
        context={"namespace": "missing/ns"},
    )

    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="report_pipeline",
            planned_side_effects=["model"],
            settings=ingest_settings,
            prompt_namespaces=["missing/ns"],
            require_llm=False,
            require_drive=False,
            require_publish=False,
            require_browser=False,
            require_live_endpoints=False,
        ),
        _ctx(),
        dependencies=_deps(tmp_path, prompt_error=prompt_error),
    )

    assert report.passed is False
    assert report.blockers[0].check_name == "prompt_namespace:missing/ns"
    assert report.blockers[0].code == "prompt_not_found"
    assert "fix_prompt_namespace:missing/ns" in report.next_actions


def test_pipeline_preflight_blocks_unwritable_db_path(
    tmp_path,
    ingest_settings,
) -> None:
    settings = replace(
        ingest_settings, state_db=str(tmp_path / "blocked" / "state.sqlite")
    )

    base_deps = _deps(tmp_path)

    def _write_failed(req, ctx):
        if "state" not in str(req.path):
            return base_deps.write_bytes(req, ctx)
        raise AppError(code="file_write_failed", message="denied", retryable=False)

    deps = PipelinePreflightDependencies(
        file_stat=base_deps.file_stat,
        write_bytes=_write_failed,
        delete_file=base_deps.delete_file,
        load_prompt_set=base_deps.load_prompt_set,
        preflight_drive_write_access=base_deps.preflight_drive_write_access,
        preflight_wordpress_publish_target=base_deps.preflight_wordpress_publish_target,
    )

    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="report_pipeline",
            planned_side_effects=["model"],
            settings=settings,
            prompt_namespaces=[],
            require_llm=False,
            require_drive=False,
            require_publish=False,
            require_browser=False,
            require_live_endpoints=False,
        ),
        _ctx(),
        dependencies=deps,
    )

    assert report.passed is False
    assert report.blockers[0].check_name == "path_writable:state_db"
    assert report.blockers[0].next_action == "fix_path_permissions:state_db"


def test_pipeline_preflight_surfaces_drive_oauth_refresh_as_auto_fix(
    tmp_path,
    ingest_settings,
) -> None:
    settings = replace(
        ingest_settings,
        drive_auth_mode="oauth_user",
        google_oauth_token_path=str(tmp_path / "token.json"),
    )

    deps = _deps(tmp_path)
    deps = PipelinePreflightDependencies(
        file_stat=deps.file_stat,
        write_bytes=deps.write_bytes,
        delete_file=deps.delete_file,
        load_prompt_set=deps.load_prompt_set,
        preflight_drive_write_access=lambda req, ctx: DriveWritePreflightResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            auth_mode=req.auth_mode,
            credentials_refreshed=True,
            scopes_verified=True,
            folder_access_verified=True,
            write_access_verified=True,
        ),
        preflight_wordpress_publish_target=deps.preflight_wordpress_publish_target,
    )

    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="report_pipeline",
            planned_side_effects=["drive"],
            settings=settings,
            prompt_namespaces=[],
            require_llm=False,
            require_drive=True,
            require_publish=False,
            require_browser=False,
            require_live_endpoints=True,
        ),
        _ctx(),
        dependencies=deps,
    )

    assert report.passed is True
    assert any(
        check.code == "drive_oauth_credentials_refreshed" for check in report.checks
    )
    assert report.auto_fixed_count == 1


def test_pipeline_preflight_blocks_publish_target_failure(
    tmp_path,
    ingest_settings,
    publish_settings_factory,
) -> None:
    deps = _deps(tmp_path)
    deps = PipelinePreflightDependencies(
        file_stat=deps.file_stat,
        write_bytes=deps.write_bytes,
        delete_file=deps.delete_file,
        load_prompt_set=deps.load_prompt_set,
        preflight_drive_write_access=deps.preflight_drive_write_access,
        preflight_wordpress_publish_target=lambda settings, ctx: (_ for _ in ()).throw(
            AppError(
                code="wordpress_publish_target_unreachable",
                message="unreachable",
                retryable=True,
            )
        ),
    )

    report = run_pipeline_preflight(
        PipelinePreflightRequest(
            schema_version="1.0",
            workflow="publish_ready",
            planned_side_effects=["publish"],
            settings=ingest_settings,
            publish_settings=publish_settings_factory(),
            prompt_namespaces=[],
            require_llm=False,
            require_drive=False,
            require_publish=True,
            require_browser=False,
            require_live_endpoints=True,
        ),
        _ctx(),
        dependencies=deps,
    )

    assert report.passed is False
    assert report.blockers[0].check_name == "wordpress_publish_target"
    assert report.blockers[0].code == "wordpress_publish_target_unreachable"


def test_pipeline_preflight_dependencies_are_immutable(tmp_path) -> None:
    deps = _deps(tmp_path)

    with pytest.raises(FrozenInstanceError):
        deps.file_stat = deps.write_bytes  # type: ignore[misc]


def test_report_pipeline_prompt_namespaces_follow_enabled_settings(
    ingest_settings,
) -> None:
    settings = replace(
        ingest_settings,
        evidence_pack_registry=["doc_map", "scope", "", "findings"],
        crop_refine_enabled=True,
        pdf_text_ocr_enabled=True,
        pdf_text_ocr_prompt_namespace="pdf_text/ocr_fallback",
        figure_caption_enabled=True,
        figure_caption_prompt_namespace="report_vs/figure_caption",
    )

    namespaces = report_pipeline_prompt_namespaces(settings)

    assert namespaces == sorted(
        {
            "rank_candidates",
            "rank_candidates/crop_refine",
            "pdf_text/ocr_fallback",
            "report_vs/context_category_fit",
            "report_vs/context_category_fit_repair",
            "report_vs/doc_map",
            "report_vs/evidence_packs/findings",
            "report_vs/evidence_packs/scope",
            "report_vs/figure_caption",
            "report_vs/taxonomy",
            "report_vs/taxonomy_repair",
        }
    )


def test_pipeline_preflight_blocks_publish_when_auth_or_site_missing(
    tmp_path,
    ingest_settings,
    publish_settings_factory,
) -> None:
    missing_password = publish_settings_factory()
    missing_password = replace(
        missing_password,
        wp=replace(missing_password.wp, app_password=None, bearer_token=None),
    )
    missing_site = replace(
        missing_password,
        wp=replace(
            missing_password.wp,
            site_url="",
            app_password="pass",
            bearer_token=None,
        ),
    )

    for settings in (missing_password, missing_site):
        report = run_pipeline_preflight(
            PipelinePreflightRequest(
                schema_version="1.0",
                workflow="publish_ready",
                planned_side_effects=["publish"],
                settings=ingest_settings,
                publish_settings=settings,
                prompt_namespaces=[],
                require_llm=False,
                require_drive=False,
                require_publish=True,
                require_browser=False,
                require_live_endpoints=True,
            ),
            _ctx(),
            dependencies=_deps(tmp_path),
        )

        assert report.passed is False
        assert report.blockers[0].check_name == "wordpress_credentials"
        assert report.blockers[0].code == "wordpress_credentials_missing"
