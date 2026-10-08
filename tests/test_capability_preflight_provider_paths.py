from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts._browser_download.dev_diagnostics import (
    BrowserExecutableAvailabilityResponse,
    BrowserRuntimeAvailabilityResponse,
)
from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadSettings,
)
from src.contracts.config import AppSettings, ConfigLoadRequest
from src.contracts.drive import DriveFolderCapabilityPreflightResponse
from src.contracts.files import ExecutableAvailabilityResponse
from src.contracts.mailbox_acquisition import (
    MailboxAccessPreflightResponse,
    MailboxAcquisitionSettings,
)
from src.contracts.pipeline_preflight import (
    CapabilityPreflightReport,
    CapabilityPreflightRequest,
)
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.sqlite_migration import SqliteCapabilityInspectionResponse
from src.contracts.wordpress import (
    WordPressAuthSettings,
    WordPressPublishTargetPreflightResponse,
)
from src.contracts.workflow_control import WorkflowControlSettings
from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES, WorkflowQueuePolicy
from src.orchestrators.pipeline_preflight_orchestrator import (
    CapabilityPreflightDependencies,
    run_capability_preflight,
)
from src.services import config_service, file_service
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _settings(root: Path, *, openai_api_key: str = "sk-test") -> AppSettings:
    root.mkdir(parents=True, exist_ok=True)
    assets = {
        "categories": root / "categories.yaml",
        "cover_style": root / "cover-style.yaml",
        "publishers": root / "publishers.json",
    }
    assets["categories"].write_text("categories: []\n", encoding="utf-8")
    assets["cover_style"].write_text("style: test\n", encoding="utf-8")
    assets["publishers"].write_text("{}\n", encoding="utf-8")
    return AppSettings(
        schema_version="1.0",
        google_sa_path=str(root / "service-account.json"),
        gdrive_folder_id="configured-folder",
        openai_api_key=openai_api_key,
        openai_model="model-test",
        batch_limit=1,
        output_dir=str(root / "out"),
        cache_dir=str(root / "cache"),
        state_db=str(root / "state.sqlite"),
        reports_db=str(root / "reports.sqlite"),
        publisher_profiles_path=str(assets["publishers"]),
        category_mapping_path=str(assets["categories"]),
        cover_style_path=str(assets["cover_style"]),
        ingest_lock_path=str(root / "ingest.lock"),
        temperature=0.0,
    )


def _control() -> WorkflowControlSettings:
    config_path = Path(__file__).resolve().parents[1] / "src" / "config" / "app.yaml"
    return config_service.load_workflow_control_settings(
        ConfigLoadRequest(
            schema_version="1.0",
            path=str(config_path),
            profile_name="autonomous_mvp",
        ),
        _ctx(),
    )


def _queues(workflow: str) -> dict[str, WorkflowQueuePolicy]:
    budget_profiles = {
        "report_acquisition": "browser_acquisition",
        "mailbox_delivery": "mailbox_delivery",
        "wordpress_publish": "publishing",
    }
    return {
        name: WorkflowQueuePolicy(
            queue_name=name,
            enabled=name == workflow,
            max_workers=1,
            max_attempts=1,
            lease_seconds=60,
            maximum_pending=10,
            maximum_fanout=1,
            budget_profile=budget_profiles.get(name, "publishing"),
        )
        for name in WORKFLOW_QUEUE_NAMES
    }


def _dependencies(
    *,
    file_stat=None,
    drive_probe=None,
    mailbox_probe=None,
    wordpress_probe=None,
) -> CapabilityPreflightDependencies:
    ready_sqlite = SqliteCapabilityInspectionResponse(
        schema_version="1.0",
        database_key="state_db",
        status="ready",
        reason_code="sqlite_capability_ready",
        retryable=False,
        current_version=1,
        expected_version=1,
        integrity_ok=True,
        foreign_keys_ok=True,
        write_lock_available=True,
    )

    def unexpected_provider_call(*_args, **_kwargs):
        raise AssertionError("unexpected provider call in capability test")

    return CapabilityPreflightDependencies(
        inspect_sqlite=lambda _request, _ctx: ready_sqlite,
        file_stat=file_stat or file_service.file_stat,
        write_bytes=file_service.write_bytes,
        delete_file=file_service.delete_file,
        inspect_executable=lambda request, _ctx: ExecutableAvailabilityResponse(
            schema_version="1.0",
            executable_name=request.executable_name,
            available=True,
        ),
        preflight_browser_executable=lambda _request, _ctx: (
            BrowserExecutableAvailabilityResponse(schema_version="1.0", available=True)
        ),
        preflight_browser_runtime=lambda _ctx: BrowserRuntimeAvailabilityResponse(
            schema_version="1.0",
            available=True,
            reason_code="browser_runtime_available",
        ),
        load_prompt_set=lambda _request, _ctx: object(),
        preflight_openai_model=unexpected_provider_call,
        preflight_openrouter_model=unexpected_provider_call,
        preflight_drive_folder_access=drive_probe or unexpected_provider_call,
        preflight_mailbox_access=mailbox_probe or unexpected_provider_call,
        preflight_wordpress_publish_target=wordpress_probe or unexpected_provider_call,
    )


def _report(
    tmp_path: Path,
    workflow: str,
    *,
    live: bool,
    openai_api_key: str = "sk-test",
    supervisor_enabled: bool = True,
    without_preflight_profile: str | None = None,
    file_stat=None,
    drive_probe=None,
    mailbox_probe=None,
    wordpress_probe=None,
    browser_settings: BrowserDownloadSettings | None = None,
    mailbox_settings: MailboxAcquisitionSettings | None = None,
    publish_settings: PublishSettings | None = None,
) -> CapabilityPreflightReport:
    settings = _settings(tmp_path, openai_api_key=openai_api_key)
    Path(settings.google_sa_path).write_text("{}", encoding="utf-8")
    workflow_control = _control()
    if not supervisor_enabled:
        workflow_control = replace(
            workflow_control,
            supervisor=replace(workflow_control.supervisor, enabled=False),
        )
    if without_preflight_profile is not None:
        profiles = dict(workflow_control.preflight_profiles)
        profiles.pop(without_preflight_profile, None)
        workflow_control = replace(workflow_control, preflight_profiles=profiles)
    return run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=settings,
            workflow_control=workflow_control,
            queue_policies=_queues(workflow),
            browser_settings=browser_settings,
            mailbox_settings=mailbox_settings,
            publish_settings=publish_settings,
            live_checks=live,
        ),
        _ctx(),
        dependencies=_dependencies(
            file_stat=file_stat,
            drive_probe=drive_probe,
            mailbox_probe=mailbox_probe,
            wordpress_probe=wordpress_probe,
        ),
    )


@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_calls"),
    [
        ("accessible", "ready", 2),
        ("inaccessible", "blocked", 1),
        ("transient", "degraded", 1),
        ("permanent", "blocked", 1),
        ("unexpected", "degraded", 1),
    ],
)
def test_drive_live_probe_maps_access_and_failures_to_workflow_status(
    tmp_path: Path,
    outcome: str,
    expected_status: str,
    expected_calls: int,
) -> None:
    def probe(request, _ctx):
        assert request.folder_id == "configured-folder"
        assert request.timeout_seconds == 5.0
        if outcome == "transient":
            raise AppError(
                code="drive_provider_unavailable", message="unavailable", retryable=True
            )
        if outcome == "permanent":
            raise AppError(
                code="drive_folder_unavailable", message="missing", retryable=False
            )
        if outcome == "unexpected":
            raise RuntimeError("provider error")
        return DriveFolderCapabilityPreflightResponse(
            schema_version="1.0",
            accessible=outcome == "accessible",
            provider_calls=2 if outcome == "accessible" else 1,
        )

    report = _report(
        tmp_path,
        "report_acquisition",
        live=True,
        drive_probe=probe,
    )
    check = next(item for item in report.checks if item.capability == "google_drive")

    assert check.status == expected_status
    assert report.provider_calls >= expected_calls
    assert report.external_writes == 0


def test_drive_local_mode_reports_probe_skipped_without_provider_calls(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path, "report_acquisition", live=False)
    check = next(item for item in report.checks if item.capability == "google_drive")

    assert check.status == "not_checked"
    assert check.reason_code == "drive_live_probe_skipped"
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_autonomous_profile_with_no_enabled_workflow_is_not_required(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path, "", live=False)
    check = next(item for item in report.checks if item.capability == "workflow_scope")

    assert report.workflow_names == []
    assert report.status == "not_required"
    assert check.status == "not_required"
    assert check.reason_code == "no_workflows_enabled"
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_disabled_autonomous_supervisor_is_a_global_blocker(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        "cost_reconciliation",
        live=False,
        supervisor_enabled=False,
    )
    check = next(
        item for item in report.checks if item.capability == "autonomous_supervisor"
    )

    assert report.workflow_names == []
    assert report.status == "blocked"
    assert check.status == "blocked"
    assert check.reason_code == "autonomous_supervisor_disabled"
    assert check.affected_workflows == []
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_enabled_workflow_without_preflight_profile_is_scoped_blocked(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        "report_acquisition",
        live=False,
        without_preflight_profile="report_download",
    )
    check = next(
        item for item in report.checks if item.capability == "workflow_profile"
    )

    assert report.workflow_names == ["report_acquisition"]
    assert report.workflow_statuses["report_acquisition"] == "blocked"
    assert check.reason_code == "workflow_capability_profile_missing"
    assert check.affected_workflows == ["report_acquisition"]
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_report_analysis_without_openai_key_is_scoped_blocked_without_calls(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        "report_analysis",
        live=False,
        openai_api_key="",
    )
    check = next(item for item in report.checks if item.capability == "llm_model")

    assert report.workflow_names == ["report_analysis"]
    assert report.workflow_statuses["report_analysis"] == "blocked"
    assert check.status == "blocked"
    assert check.reason_code == "openai_missing_api_key"
    assert check.affected_workflows == ["report_analysis"]
    assert report.provider_calls == 0
    assert report.external_writes == 0


def _mailbox_settings(tmp_path: Path) -> MailboxAcquisitionSettings:
    return MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="imap",
        output_dir=str(tmp_path),
        search_window_minutes=60,
        max_results=1,
        poll_timeout_seconds=1.0,
        poll_interval_seconds=0.1,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="",
        gmail_user_id="me",
        imap_host="imap.example.test",
        imap_port=993,
        imap_user="mailbox-user",
        imap_password="mailbox-password-test",
        imap_mailbox="INBOX",
    )


@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_mailbox_calls"),
    [
        ("accessible", "ready", 2),
        ("inaccessible", "blocked", 1),
        ("transient", "degraded", 2),
        ("unexpected", "degraded", 1),
    ],
)
def test_mailbox_live_probe_keeps_retryability_and_call_count_scoped(
    tmp_path: Path,
    outcome: str,
    expected_status: str,
    expected_mailbox_calls: int,
) -> None:
    def mailbox_probe(_settings, _ctx):
        if outcome == "transient":
            raise AppError(
                code="mailbox_provider_unavailable",
                message="unavailable",
                retryable=True,
                context={"provider_calls": 2},
            )
        if outcome == "unexpected":
            raise RuntimeError("provider error")
        return MailboxAccessPreflightResponse(
            schema_version="1.0",
            provider="imap",
            accessible=outcome == "accessible",
            provider_calls=2 if outcome == "accessible" else 1,
        )

    report = _report(
        tmp_path,
        "mailbox_delivery",
        live=True,
        drive_probe=lambda _request, _ctx: DriveFolderCapabilityPreflightResponse(
            schema_version="1.0", accessible=True, provider_calls=1
        ),
        mailbox_probe=mailbox_probe,
        mailbox_settings=_mailbox_settings(tmp_path),
    )
    check = next(item for item in report.checks if item.capability == "mailbox")
    drive_calls = next(
        item for item in report.checks if item.capability == "google_drive"
    )

    assert check.status == expected_status
    assert check.affected_workflows == ["mailbox_delivery"]
    assert report.provider_calls == expected_mailbox_calls + 1
    assert drive_calls.status == "ready"
    assert report.external_writes == 0


def test_mailbox_local_mode_reports_probe_skipped_without_provider_calls(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        "mailbox_delivery",
        live=False,
        mailbox_settings=_mailbox_settings(tmp_path),
    )
    check = next(item for item in report.checks if item.capability == "mailbox")

    assert check.status == "not_checked"
    assert check.reason_code == "mailbox_live_probe_skipped"
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_mailbox_missing_settings_is_scoped_to_mailbox_workflow(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        "mailbox_delivery",
        live=False,
        mailbox_settings=None,
    )
    check = next(item for item in report.checks if item.capability == "mailbox")

    assert check.status == "blocked"
    assert check.reason_code == "mailbox_configuration_missing"
    assert check.affected_workflows == ["mailbox_delivery"]
    assert report.provider_calls == 0


def test_mailbox_missing_gmail_token_is_blocked_without_provider_calls(
    tmp_path: Path,
) -> None:
    settings = replace(
        _mailbox_settings(tmp_path),
        provider="gmail",
        gmail_oauth_token_path=str(tmp_path / "missing-token.json"),
    )
    report = _report(
        tmp_path,
        "mailbox_delivery",
        live=False,
        mailbox_settings=settings,
    )
    check = next(item for item in report.checks if item.capability == "mailbox")

    assert check.status == "blocked"
    assert check.reason_code == "mailbox_credentials_missing"
    assert report.provider_calls == 0


def test_mailbox_file_stat_failure_is_treated_as_missing_token(
    tmp_path: Path,
) -> None:
    settings = replace(
        _mailbox_settings(tmp_path),
        provider="gmail",
        gmail_oauth_token_path=str(tmp_path / "token.json"),
    )

    def inaccessible_token(_request, _ctx):
        raise AppError(
            code="file_not_found", message="token unavailable", retryable=False
        )

    report = _report(
        tmp_path,
        "mailbox_delivery",
        live=False,
        file_stat=inaccessible_token,
        mailbox_settings=settings,
    )
    check = next(item for item in report.checks if item.capability == "mailbox")

    assert check.status == "blocked"
    assert check.reason_code == "mailbox_credentials_missing"
    assert report.provider_calls == 0


def test_mailbox_rejects_unknown_provider_before_any_probe(tmp_path: Path) -> None:
    settings = replace(_mailbox_settings(tmp_path), provider="unsupported")
    report = _report(
        tmp_path,
        "mailbox_delivery",
        live=False,
        mailbox_settings=settings,
    )
    check = next(item for item in report.checks if item.capability == "mailbox")

    assert check.status == "blocked"
    assert check.reason_code == "mailbox_provider_invalid"
    assert report.provider_calls == 0


def _browser_settings() -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="",
        model="browser-model",
        temperature=0.0,
        timeout_seconds=5.0,
        max_steps=1,
        output_dir="out",
        state_db="state.sqlite",
        reports_db="reports.sqlite",
        identity_config_path="identity.yaml",
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0", fields=[], delivery_emails=[]
        ),
        openai_api_key="",
    )


def test_browser_without_live_provider_credentials_is_blocked_without_calls(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        "report_acquisition",
        live=False,
        browser_settings=_browser_settings(),
    )
    check = next(item for item in report.checks if item.capability == "browser")

    assert check.status == "blocked"
    assert check.required is True
    assert report.provider_calls == 0
    assert report.external_writes == 0


def _publish_settings() -> PublishSettings:
    return PublishSettings(
        schema_version="1.0",
        output_dir="out",
        state_db="state.sqlite",
        reports_db="reports.sqlite",
        category_mapping_path="categories.yaml",
        wp=WordPressAuthSettings(
            schema_version="1.0",
            site_url="https://site.example.test",
            username="preflight-user",
            app_password="password-test",
            bearer_token=None,
            post_status="publish",
            post_type="ml_report",
        ),
    )


@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_calls"),
    [
        ("ready", "ready", 3),
        ("unverified", "blocked", 2),
        ("transient", "degraded", 2),
        ("unexpected", "degraded", 1),
    ],
)
def test_wordpress_live_probe_requires_verified_create_capability(
    tmp_path: Path,
    outcome: str,
    expected_status: str,
    expected_calls: int,
) -> None:
    def wordpress_probe(_settings, _ctx):
        if outcome == "transient":
            raise AppError(
                code="wordpress_provider_unavailable",
                message="unavailable",
                retryable=True,
                context={"provider_calls": 2},
            )
        if outcome == "unexpected":
            raise RuntimeError("provider error")
        return WordPressPublishTargetPreflightResponse(
            schema_version="1.0",
            base_url="https://site.example.test",
            post_type="ml_report",
            endpoint="https://site.example.test/wp-json/wp/v2/ml_report",
            reachable=True,
            status_code=200,
            authenticated=True,
            verified_capabilities=(
                ("create_posts", "publish_posts") if outcome == "ready" else ()
            ),
            provider_calls=3 if outcome == "ready" else 2,
        )

    report = _report(
        tmp_path,
        "wordpress_publish",
        live=True,
        wordpress_probe=wordpress_probe,
        publish_settings=_publish_settings(),
    )
    check = next(item for item in report.checks if item.capability == "wordpress")

    assert check.status == expected_status
    assert check.affected_workflows == ["wordpress_publish"]
    assert report.provider_calls == expected_calls
    assert report.external_writes == 0


def test_wordpress_local_mode_does_not_claim_unverified_readiness(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        "wordpress_publish",
        live=False,
        publish_settings=_publish_settings(),
    )
    check = next(item for item in report.checks if item.capability == "wordpress")

    assert check.status == "not_checked"
    assert check.reason_code == "wordpress_live_probe_skipped"
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_wordpress_invalid_endpoint_configuration_is_blocked_locally(
    tmp_path: Path,
) -> None:
    settings = _publish_settings()
    publish_settings = replace(
        settings,
        wp=replace(settings.wp, site_url="not-a-valid-url"),
    )
    report = _report(
        tmp_path,
        "wordpress_publish",
        live=False,
        publish_settings=publish_settings,
    )
    check = next(item for item in report.checks if item.capability == "wordpress")

    assert check.status == "blocked"
    assert check.reason_code == "wordpress_configuration_invalid"
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_wordpress_missing_credentials_is_blocked_locally(tmp_path: Path) -> None:
    settings = _publish_settings()
    publish_settings = replace(
        settings,
        wp=replace(settings.wp, username="", app_password="", bearer_token=None),
    )
    report = _report(
        tmp_path,
        "wordpress_publish",
        live=False,
        publish_settings=publish_settings,
    )
    check = next(item for item in report.checks if item.capability == "wordpress")

    assert check.status == "blocked"
    assert check.reason_code == "wordpress_credentials_missing"
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_wordpress_missing_settings_is_scoped_to_publish_workflow(
    tmp_path: Path,
) -> None:
    report = _report(
        tmp_path,
        "wordpress_publish",
        live=False,
        publish_settings=None,
    )
    check = next(item for item in report.checks if item.capability == "wordpress")

    assert check.status == "blocked"
    assert check.reason_code == "wordpress_configuration_missing"
    assert check.affected_workflows == ["wordpress_publish"]
    assert report.provider_calls == 0
    assert report.external_writes == 0
