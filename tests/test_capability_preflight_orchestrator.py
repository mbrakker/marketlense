from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.config import AppSettings, ConfigLoadRequest
from src.contracts.browser_download import (
    BrowserRuntimeAvailabilityResponse,
    BrowserDownloadIdentity,
    BrowserDownloadSettings,
)
from src.contracts.llm import OpenAIModelPreflightResponse
from src.contracts.publisher_inventory import PublisherInventorySettings
from src.contracts.browser_download import BrowserExecutableAvailabilityResponse
from src.contracts.files import ExecutableAvailabilityResponse
from src.contracts.pipeline_preflight import CapabilityPreflightRequest
from src.contracts.run_context import RunContext
from src.contracts.sqlite_migration import SqliteCapabilityInspectionResponse
from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES, WorkflowQueuePolicy
from src.orchestrators.pipeline_preflight_orchestrator import (
    CapabilityPreflightDependencies,
    default_capability_preflight_dependencies,
    run_capability_preflight,
)
from src.services.config_service import load_workflow_control_settings
from src.services import file_service
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _settings(root: Path, *, api_key: str = "sk-test") -> AppSettings:
    root.mkdir(parents=True, exist_ok=True)
    settings = AppSettings(
        schema_version="1.0",
        google_sa_path=str(root / "service-account.json"),
        gdrive_folder_id="folder-test",
        openai_api_key=api_key,
        openai_model="model-test",
        batch_limit=1,
        output_dir=str(root / "out"),
        cache_dir=str(root / "cache"),
        state_db=str(root / "state.sqlite"),
        reports_db=str(root / "reports.sqlite"),
        publisher_profiles_path=str(root / "publishers.json"),
        category_mapping_path=str(root / "categories.yaml"),
        cover_style_path=str(root / "cover-style.yaml"),
        ingest_lock_path=str(root / "ingest.lock"),
        temperature=0.0,
    )
    (root / "categories.yaml").write_text("categories: []\n", encoding="utf-8")
    (root / "cover-style.yaml").write_text("style: test\n", encoding="utf-8")
    (root / "publishers.json").write_text("{}\n", encoding="utf-8")
    return settings


def _browser_settings(output_dir: str) -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-test",
        model="gpt-test",
        temperature=0.0,
        timeout_seconds=5.0,
        max_steps=1,
        output_dir=output_dir,
        state_db="state.sqlite",
        reports_db="reports.sqlite",
        identity_config_path="identity.yaml",
        identity_profile=BrowserDownloadIdentity(schema_version="1.0", fields=[]),
        openai_api_key="sk-test",
    )


def _publisher_inventory_settings(
    *, openrouter_api_key: str = "openrouter-test", model: str = "openai/gpt-test"
) -> PublisherInventorySettings:
    return PublisherInventorySettings(
        schema_version="1.0",
        openrouter_api_key=openrouter_api_key,
        model=model,
        temperature=0.0,
        timeout_seconds=5.0,
        max_steps=1,
        output_dir="out/publisher-discovery",
        reports_db="reports.sqlite",
        google_sa_path="service-account.json",
        prompt_namespace="publisher_inventory/discovery",
        pagination_max_pages=1,
        http_timeout_seconds=5.0,
        candidate_screening_enabled=False,
    )


def _control(profile_name: str):
    return load_workflow_control_settings(
        ConfigLoadRequest(
            schema_version="1.0",
            path="src/config/app.yaml",
            profile_name="autonomous_mvp" if profile_name == "autonomous_mvp" else "",
        ),
        _ctx(),
    )


def _queues(*enabled: str) -> dict[str, WorkflowQueuePolicy]:
    control = _control("autonomous_mvp")
    policies = {
        name: WorkflowQueuePolicy(
            queue_name=name,
            enabled=name in enabled,
            max_workers=1,
            max_attempts=2,
            lease_seconds=60,
            maximum_pending=10,
            maximum_fanout=2,
            budget_profile=(
                "cross_report_analysis" if name == "report_analysis" else "publishing"
            ),
        )
        for name in WORKFLOW_QUEUE_NAMES
    }
    assert control.available_budget_profile_refs
    return policies


def _dependencies(
    *, model_check=None, openrouter_check=None, prompt_check=None
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
        raise AssertionError("local-only preflight called a provider")

    return CapabilityPreflightDependencies(
        inspect_sqlite=lambda _request, _ctx: ready_sqlite,
        file_stat=file_service.file_stat,
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
        load_prompt_set=prompt_check or (lambda _request, _ctx: object()),
        preflight_openai_model=model_check or unexpected_provider_call,
        preflight_openrouter_model=openrouter_check or unexpected_provider_call,
        preflight_drive_folder_access=unexpected_provider_call,
        preflight_mailbox_access=unexpected_provider_call,
        preflight_wordpress_publish_target=unexpected_provider_call,
    )


def test_local_only_profile_preflight_makes_no_provider_calls_or_external_writes(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="manual",
            settings=settings,
            workflow_control=_control("manual"),
            queue_policies=_queues(),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    assert report.status == "degraded"
    assert report.workflow_names == ["report_generation"]
    assert report.provider_calls == 0
    assert report.external_writes == 0
    llm = next(check for check in report.checks if check.capability == "llm_model")
    assert llm.status == "not_checked"
    assert llm.required is True


def test_autonomous_preflight_only_checks_enabled_queue_capabilities(
    tmp_path: Path,
) -> None:
    control = _control("autonomous_mvp")
    request = CapabilityPreflightRequest(
        schema_version="1.0",
        profile_name="autonomous_mvp",
        settings=_settings(tmp_path),
        workflow_control=control,
        queue_policies=_queues("report_analysis"),
        live_checks=False,
    )

    report = run_capability_preflight(request, _ctx(), dependencies=_dependencies())

    assert report.workflow_names == ["report_analysis"]
    assert report.provider_calls == 0
    assert report.external_writes == 0
    assert all(
        "wordpress_publish" not in check.affected_workflows for check in report.checks
    )
    assert (
        next(check for check in report.checks if check.capability == "wordpress").status
        == "not_required"
    )


def test_publication_readiness_does_not_require_wordpress_access(
    tmp_path: Path,
) -> None:
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("publication_readiness"),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    wordpress = next(
        check for check in report.checks if check.capability == "wordpress"
    )
    assert wordpress.status == "not_required"
    assert "publication_readiness" not in wordpress.affected_workflows


def test_optional_wordpress_failure_does_not_block_independent_workflow(
    tmp_path: Path,
) -> None:
    policies = _queues("cost_reconciliation", "wordpress_publish")
    control = _control("autonomous_mvp")
    request = CapabilityPreflightRequest(
        schema_version="1.0",
        profile_name="autonomous_mvp",
        settings=_settings(tmp_path),
        workflow_control=control,
        queue_policies=policies,
        live_checks=False,
    )

    report = run_capability_preflight(request, _ctx(), dependencies=_dependencies())

    assert report.workflow_statuses["cost_reconciliation"] == "ready"
    assert report.workflow_statuses["wordpress_publish"] == "blocked"
    assert report.status == "degraded"


def test_prompt_failure_only_affects_workflows_that_use_that_prompt(
    tmp_path: Path,
) -> None:
    def fail_prompt(_request, _ctx):
        raise RuntimeError("prompt unavailable")

    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("cost_reconciliation", "report_analysis"),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(prompt_check=fail_prompt),
    )

    assert report.workflow_statuses["cost_reconciliation"] == "ready"
    assert report.workflow_statuses["report_analysis"] == "blocked"


def test_shared_storage_path_attributes_failure_to_each_dependent_workflow(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("occupied", encoding="utf-8")
    settings = replace(_settings(tmp_path), output_dir=str(output_file))
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=settings,
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("publisher_discovery", "report_analysis"),
            browser_settings=_browser_settings(settings.output_dir),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    shared_output_check = next(
        check
        for check in report.checks
        if check.capability == "writable_storage" and check.status == "blocked"
    )
    assert shared_output_check.affected_workflows == [
        "publisher_discovery",
        "report_analysis",
    ]
    assert report.workflow_statuses["report_analysis"] == "blocked"


def test_claim_embedding_model_is_required_but_not_probed_locally(
    tmp_path: Path,
) -> None:
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("claim_embedding"),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    model = next(
        check for check in report.checks if check.capability == "openai_embedding_model"
    )
    assert model.status == "not_checked"
    assert model.required is True
    assert model.affected_workflows == ["claim_embedding"]
    assert report.provider_calls == 0


def test_claim_embedding_live_probe_checks_its_embedding_model(
    tmp_path: Path,
) -> None:
    observed_models: list[str] = []

    def check_model(request, _ctx):
        observed_models.append(request.model)
        return OpenAIModelPreflightResponse(
            schema_version="1.0",
            model=request.model,
            accessible=True,
            provider_calls=1,
        )

    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("claim_embedding"),
            live_checks=True,
        ),
        _ctx(),
        dependencies=_dependencies(model_check=check_model),
    )

    model = next(
        check for check in report.checks if check.capability == "openai_embedding_model"
    )
    assert model.status == "ready"
    assert observed_models == ["text-embedding-3-large"]
    assert report.provider_calls == 1


def test_publisher_discovery_model_is_not_checked_without_live_provider_access(
    tmp_path: Path,
) -> None:
    control = _control("autonomous_mvp")
    control = replace(
        control,
        preflight_profiles={
            **control.preflight_profiles,
            "publisher_inventory": replace(
                control.preflight_profiles["publisher_inventory"],
                require_llm=False,
                require_drive=False,
                require_browser=False,
                prompt_namespaces=(),
            ),
        },
    )
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=control,
            queue_policies=_queues("publisher_discovery"),
            publisher_inventory_settings=_publisher_inventory_settings(),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    model = next(
        check for check in report.checks if check.capability == "openrouter_model"
    )
    assert model.status == "not_checked"
    assert model.required is True
    assert model.affected_workflows == ["publisher_discovery"]
    assert report.provider_calls == 0


def test_publisher_discovery_live_probe_verifies_configured_openrouter_model(
    tmp_path: Path,
) -> None:
    observed_models: list[str] = []

    def check_openrouter(request, _ctx):
        observed_models.append(request.model)
        return type("Result", (), {"accessible": True, "provider_calls": 1})()

    control = _control("autonomous_mvp")
    control = replace(
        control,
        preflight_profiles={
            **control.preflight_profiles,
            "publisher_inventory": replace(
                control.preflight_profiles["publisher_inventory"],
                require_llm=False,
                require_drive=False,
                require_browser=False,
                prompt_namespaces=(),
            ),
        },
    )
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=control,
            queue_policies=_queues("publisher_discovery"),
            publisher_inventory_settings=_publisher_inventory_settings(),
            live_checks=True,
        ),
        _ctx(),
        dependencies=_dependencies(openrouter_check=check_openrouter),
    )

    model = next(
        check for check in report.checks if check.capability == "openrouter_model"
    )
    assert model.status == "ready"
    assert observed_models == ["openai/gpt-test"]
    assert report.provider_calls == 1


def test_missing_openrouter_credential_blocks_only_publisher_discovery(
    tmp_path: Path,
) -> None:
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("cost_reconciliation", "publisher_discovery"),
            publisher_inventory_settings=_publisher_inventory_settings(
                openrouter_api_key=""
            ),
            live_checks=True,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    model = next(
        check for check in report.checks if check.capability == "openrouter_model"
    )
    assert model.status == "blocked"
    assert model.reason_code == "openrouter_missing_api_key"
    assert report.workflow_statuses["cost_reconciliation"] == "ready"
    assert report.workflow_statuses["publisher_discovery"] == "blocked"
    assert report.status == "degraded"
    assert report.provider_calls == 0


def test_transient_openrouter_preflight_failure_is_retryable_degraded(
    tmp_path: Path,
) -> None:
    def fail_openrouter(_request, _ctx):
        raise AppError(
            code="openrouter_provider_unavailable",
            message="provider unavailable",
            retryable=True,
        )

    control = _control("autonomous_mvp")
    control = replace(
        control,
        preflight_profiles={
            **control.preflight_profiles,
            "publisher_inventory": replace(
                control.preflight_profiles["publisher_inventory"],
                require_llm=False,
                require_drive=False,
                require_browser=False,
                prompt_namespaces=(),
            ),
        },
    )
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=control,
            queue_policies=_queues("publisher_discovery"),
            publisher_inventory_settings=_publisher_inventory_settings(),
            live_checks=True,
        ),
        _ctx(),
        dependencies=_dependencies(openrouter_check=fail_openrouter),
    )

    model = next(
        check for check in report.checks if check.capability == "openrouter_model"
    )
    assert model.status == "degraded"
    assert model.retryable is True
    assert report.workflow_statuses["publisher_discovery"] == "degraded"
    assert report.provider_calls == 1


def test_publisher_config_error_is_scoped_and_actionable(
    tmp_path: Path,
) -> None:
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("cost_reconciliation", "publisher_discovery"),
            publisher_inventory_config_error=(
                "publisher_inventory_openrouter_api_key_missing"
            ),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    config = next(
        check
        for check in report.checks
        if check.capability == "publisher_inventory_configuration"
    )
    assert config.status == "blocked"
    assert config.reason_code == "publisher_inventory_openrouter_api_key_missing"
    assert config.remediation == "Set OPENROUTER_API_KEY"
    assert report.workflow_statuses["cost_reconciliation"] == "ready"
    assert report.workflow_statuses["publisher_discovery"] == "blocked"
    assert report.provider_calls == 0


def test_optional_integration_config_errors_preserve_other_workflow_readiness(
    tmp_path: Path,
) -> None:
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues(
                "cost_reconciliation",
                "mailbox_delivery",
                "source_revalidation",
                "wordpress_publish",
            ),
            publish_settings_config_error="publish_configuration_invalid",
            mailbox_settings_config_error="mailbox_configuration_invalid",
            browser_settings_config_error="browser_configuration_invalid",
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    assert report.workflow_names == [
        "cost_reconciliation",
        "mailbox_delivery",
        "source_revalidation",
        "wordpress_publish",
    ]
    assert report.workflow_statuses["cost_reconciliation"] == "ready"
    assert report.workflow_statuses["mailbox_delivery"] == "blocked"
    assert report.workflow_statuses["source_revalidation"] == "blocked"
    assert report.workflow_statuses["wordpress_publish"] == "blocked"
    assert report.provider_calls == 0
    assert {
        check.capability: check.reason_code
        for check in report.checks
        if check.capability in {"mailbox", "browser", "wordpress"}
    } == {
        "mailbox": "mailbox_configuration_invalid",
        "browser": "browser_configuration_invalid",
        "wordpress": "publish_configuration_invalid",
    }


def test_transient_model_failure_is_retryable_degraded_and_counted(
    tmp_path: Path,
) -> None:
    def fail_model(_request, _ctx):
        raise AppError(
            code="openai_provider_unavailable",
            message="provider unavailable",
            retryable=True,
        )

    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="manual",
            settings=_settings(tmp_path),
            workflow_control=_control("manual"),
            queue_policies=_queues(),
            live_checks=True,
        ),
        _ctx(),
        dependencies=_dependencies(model_check=fail_model),
    )

    llm = next(check for check in report.checks if check.capability == "llm_model")
    assert llm.status == "degraded"
    assert llm.retryable is True
    assert report.status == "degraded"
    assert report.provider_calls == 1


@pytest.mark.parametrize("bad_value", [0, -1])
def test_enabled_queue_with_invalid_limits_is_blocked(
    tmp_path: Path, bad_value: int
) -> None:
    policies = _queues("report_analysis")
    policies["report_analysis"] = replace(
        policies["report_analysis"], max_workers=bad_value
    )
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=policies,
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    operational = next(
        check for check in report.checks if check.capability == "queue_operations"
    )
    assert operational.status == "blocked"


def test_autonomous_preflight_requires_worker_batch_dispatch_to_be_enabled(
    tmp_path: Path,
) -> None:
    control = _control("autonomous_mvp")
    control = replace(
        control,
        supervisor=replace(control.supervisor, worker_batches_enabled=False),
    )
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=control,
            queue_policies=_queues("cost_reconciliation"),
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    dispatch = next(
        check for check in report.checks if check.capability == "autonomous_dispatch"
    )
    assert dispatch.status == "blocked"
    assert report.workflow_statuses["cost_reconciliation"] == "blocked"


def test_unknown_enabled_queue_fails_closed_without_provider_calls(
    tmp_path: Path,
) -> None:
    policies = _queues()
    policies["unmapped_queue"] = WorkflowQueuePolicy(
        queue_name="unmapped_queue",
        enabled=True,
        max_workers=1,
        max_attempts=1,
        lease_seconds=60,
        maximum_pending=10,
        maximum_fanout=1,
        budget_profile="publishing",
    )
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=policies,
            live_checks=False,
        ),
        _ctx(),
        dependencies=_dependencies(),
    )

    profile = next(
        check for check in report.checks if check.capability == "workflow_profile"
    )
    registry = next(
        check
        for check in report.checks
        if check.capability == "workflow_queue_registry"
    )
    assert report.workflow_names == ["unmapped_queue"]
    assert profile.status == "blocked"
    assert profile.reason_code == "workflow_capability_profile_missing"
    assert profile.affected_workflows == ["unmapped_queue"]
    assert registry.status == "blocked"
    assert registry.reason_code == "workflow_queue_capability_mapping_missing"
    assert registry.affected_workflows == ["unmapped_queue"]
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_browser_preflight_accepts_supported_vendored_runtime_without_playwright(
    tmp_path: Path,
) -> None:
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("report_acquisition"),
            browser_settings=_browser_settings(str(tmp_path / "out")),
            live_checks=False,
        ),
        _ctx(),
        dependencies=default_capability_preflight_dependencies(),
    )

    browser_dependencies = next(
        check for check in report.checks if check.capability == "browser_dependencies"
    )
    assert browser_dependencies.status == "ready"
    assert browser_dependencies.reason_code == "browser_runtime_available"
    assert report.provider_calls == 0
    assert report.external_writes == 0


def test_browser_runtime_unavailable_is_scoped_and_blocks_browser_workflows(
    tmp_path: Path,
) -> None:
    dependencies = replace(
        default_capability_preflight_dependencies(),
        preflight_browser_runtime=lambda _ctx: BrowserRuntimeAvailabilityResponse(
            schema_version="1.0",
            available=False,
            reason_code="browser_runtime_dependency_missing",
        ),
    )
    report = run_capability_preflight(
        CapabilityPreflightRequest(
            schema_version="1.0",
            profile_name="autonomous_mvp",
            settings=_settings(tmp_path),
            workflow_control=_control("autonomous_mvp"),
            queue_policies=_queues("report_acquisition"),
            browser_settings=_browser_settings(str(tmp_path / "out")),
            live_checks=False,
        ),
        _ctx(),
        dependencies=dependencies,
    )

    browser_dependencies = next(
        check for check in report.checks if check.capability == "browser_dependencies"
    )
    browser = next(check for check in report.checks if check.capability == "browser")
    assert browser_dependencies.status == "blocked"
    assert browser_dependencies.affected_workflows == ["report_acquisition"]
    assert browser.reason_code == "browser_runtime_dependency_missing"
    assert report.provider_calls == 0
    assert report.external_writes == 0
