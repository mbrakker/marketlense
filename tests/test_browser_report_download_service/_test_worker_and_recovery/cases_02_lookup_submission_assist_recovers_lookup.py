# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_download_report_with_browser_use_lookup_submission_assist_recovers_lookup_blocked_submit(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form but the location lookup still blocked submission.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class LookupBlockedSubmitAgent(original_runtime):
        def run_sync(self, max_steps: int):
            browser = self.browser
            browser.url = "https://example.com/report#download"
            browser.title = "Example report"
            browser.html = ""

            class LookupBlockedSubmitPage:
                def evaluate(self, script):
                    script_text = str(script or "")
                    if (
                        "selected_count" in script_text
                        and ".lookupFormFieldBlock" in script_text
                    ):
                        browser.url = "https://example.com/report#success"
                        browser.title = "Thank you"
                        browser.html = (
                            "<html><body>"
                            "Thank you for your interest. You will be emailed a "
                            "downloadable copy of this insight shortly."
                            "</body></html>"
                        )
                        return {
                            "acted": True,
                            "selected_count": 1,
                            "submitted": True,
                            "final_url": browser.url,
                        }
                    if "navigationEntries" in script_text:
                        return []
                    if "document.querySelectorAll" in script_text:
                        return []
                    return []

            browser.current_page_factory = LookupBlockedSubmitPage
            payload = {
                "route_kind": "email_delivery",
                "route_summary": (
                    "Filled the form, typed Austria in Location, clicked submit, "
                    "and remained on the form."
                ),
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/report#download",
                "final_page_url": "https://example.com/report#download",
                "email_submission_completed": False,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [
                    "First Name",
                    "Last Name",
                    "Business Email Address",
                    "Business Phone",
                    "Company Name",
                    "Role",
                    "Department",
                    "Industry",
                    "Location",
                ],
                "route_steps": [
                    {
                        "index": 10,
                        "action": "input",
                        "target_text": "Austria",
                        "target_role": "textbox",
                        "target_url": "https://example.com/report#download",
                        "result": "Typed 'Austria'",
                    },
                    {
                        "index": 11,
                        "action": "click",
                        "target_text": "Submit",
                        "target_role": "button",
                        "target_url": "https://example.com/report#download",
                        "result": 'Clicked button "Submit"',
                    },
                ],
                "post_submit_message": None,
                "confirmation_url_changed": False,
                "submit_button_state": None,
                "form_disappeared": False,
                "blocked_reason": "blocked_unknown_required_enum",
                "blocked_reason_detail": (
                    "The Location field did not resolve to a valid lookup selection."
                ),
                "final_page_title": "Example report",
                "terminal_text_excerpt": None,
                "traversed_page_urls": [
                    "https://example.com/report",
                    "https://example.com/report#download",
                ],
                "onsite_capture_path": None,
                "onsite_capture_format": None,
                "onsite_page_count": None,
                "onsite_completeness_status": None,
            }

            class LookupBlockedSubmitHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return LookupBlockedSubmitHistory()

    runtime.Agent = LookupBlockedSubmitAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.route_status == "verified"
    assert response.final_page_url == "https://example.com/report#success"
    assert response.confirmation_evidence is not None
    assert response.confirmation_evidence.visible_confirmation_text.startswith(
        "Thank you for your interest."
    )

def test_browser_worker_main_preserves_candidate_trace(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/report",
        title="Example Report",
        discovered_on_page_number=2,
        source_page_urls=[
            "https://example.com/insights",
            "https://example.com/resources",
        ],
        discovery_provenances=["http_parse", "browser_dom"],
        pdf_url="https://cdn.example.com/example-report.pdf",
        published_at_text="April 2026",
        max_confidence=0.92,
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url=candidate_trace.canonical_url,
        settings=_settings(tmp_path),
        candidate_trace=candidate_trace,
        attempt_url="https://example.com/report?download=1",
        route_family_hint="browser_pdf_click",
    )
    download_dir = tmp_path / "worker-run"
    payload_path = tmp_path / "browser_agent_worker_request.json"
    response_path = tmp_path / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "request": {
                    **json.loads(
                        json.dumps(request, default=lambda value: value.__dict__)
                    ),
                },
                "ctx": run_context.__dict__,
                "normalized_url": request.url,
                "execution_url": request.attempt_url,
                "download_dir": str(download_dir),
                "prompt_bundle": {
                    "schema_version": "1.0",
                    "namespace": "browser_report_download/browser_route",
                    "system_prompt_path": "system.yaml",
                    "user_prompt_path": "user.yaml",
                    "system_prompt_sha256": "system",
                    "user_prompt_sha256": "user",
                    "rendered_system_prompt": "system",
                    "rendered_user_prompt": "user",
                    "task_prompt": "task",
                },
            }
        ),
        encoding="utf-8",
    )

    observed_requests: list[BrowserReportDownloadRequest] = []

    def fake_run_browser_report_download_agent(**kwargs):
        observed_requests.append(kwargs["request"])
        return browser_runtime.BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response="{}",
            final_page_url="https://example.com/final",
            final_page_title="Example",
            final_page_html="<html></html>",
            downloaded_files=[],
            attachment_paths=[],
            network_resource_urls=[],
            network_events=[],
            html_snapshot_path="",
            screenshot_path="",
        )

    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "run_browser_report_download_agent",
        fake_run_browser_report_download_agent,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "setup_logging",
        lambda *args, **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime.sys,
        "argv",
        [
            "browser_worker.py",
            str(payload_path),
            str(response_path),
        ],
    )

    assert browser_worker_runtime.main() == 0
    assert response_path.exists()
    assert len(observed_requests) == 1
    observed_request = observed_requests[0]
    assert observed_request.candidate_trace is not None
    assert (
        observed_request.candidate_trace.canonical_url == candidate_trace.canonical_url
    )
    assert observed_request.candidate_trace.pdf_url == candidate_trace.pdf_url
    assert observed_request.candidate_trace.discovery_provenances == (
        candidate_trace.discovery_provenances
    )

def test_browser_worker_main_redacts_identity_values_from_persisted_response(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    delivery_email = "submitted@example.com"
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path, work_email="ops@example.com"),
        delivery_email=delivery_email,
    )
    payload_path = tmp_path / "browser_agent_worker_request.json"
    response_path = tmp_path / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "request": json.loads(
                    json.dumps(request, default=lambda value: value.__dict__)
                ),
                "ctx": run_context.__dict__,
                "normalized_url": request.url,
                "execution_url": request.url,
                "download_dir": str(tmp_path / "worker-download"),
                "prompt_bundle": {
                    "schema_version": "1.0",
                    "namespace": "browser_report_download/browser_route",
                    "system_prompt_path": "system.yaml",
                    "user_prompt_path": "user.yaml",
                    "system_prompt_sha256": "system",
                    "user_prompt_sha256": "user",
                    "rendered_system_prompt": "system",
                    "rendered_user_prompt": "user",
                    "task_prompt": "task",
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_run_browser_report_download_agent(**kwargs):
        return browser_runtime.BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response=json.dumps(
                {
                    "route_kind": "email_delivery",
                    "target_text": f"Work email -> {delivery_email}",
                    "observed_evidence": [
                        f"typed ops@example.com and {delivery_email}"
                    ],
                }
            ),
            final_page_url="https://example.com/thanks",
            final_page_title="Thanks",
            final_page_html=(
                f'<html><input value="ops@example.com">'
                f'<a href="https://example.com/download?email={delivery_email}">'
                "download</a></html>"
            ),
            downloaded_files=[],
            attachment_paths=[],
            network_resource_urls=[
                f"https://example.com/pixel?email={delivery_email}",
            ],
            network_events=[],
            html_snapshot_path="",
            screenshot_path="",
        )

    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "run_browser_report_download_agent",
        fake_run_browser_report_download_agent,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "setup_logging",
        lambda *args, **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime.sys,
        "argv",
        [
            "browser_worker.py",
            str(payload_path),
            str(response_path),
        ],
    )

    assert browser_worker_runtime.main() == 0

    persisted = response_path.read_text(encoding="utf-8")
    assert "ops@example.com" not in persisted
    assert delivery_email not in persisted
    assert "***REDACTED***" in persisted

def test_browser_worker_subprocess_forces_utf8_and_captures_output(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="task",
    )

    def fake_run(*args, **kwargs):
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.STDOUT
        assert kwargs["text"] is True
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert kwargs["env"][browser_runtime._BROWSER_AGENT_WORKER_ENV] == "1"
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        assert kwargs["env"]["NO_COLOR"] == "1"
        assert kwargs["env"]["RICH_DISABLE"] == "1"
        response_path = Path(args[0][-1])
        response_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "ok",
                    "result": {
                        "schema_version": "1.0",
                        "raw_model_response": "{}",
                        "final_page_url": "https://example.com/final",
                        "final_page_title": "Final",
                        "final_page_html": "<html></html>",
                        "downloaded_files": [],
                        "attachment_paths": [],
                        "network_resource_urls": [],
                        "network_events": [],
                        "html_snapshot_path": "",
                        "screenshot_path": "",
                    },
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="INFO browser_use.Agent Step 1: click download\n",
        )

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    result = browser_runtime._run_browser_report_download_agent_subprocess(
        request=request,
        ctx=run_context,
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path / "worker-download",
        prompt_bundle=prompt_bundle,
    )

    assert result.final_page_url == "https://example.com/final"
    completion_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_worker_complete"
    ]
    assert len(completion_events) == 1
    completion_fields = completion_events[0]["fields"]
    assert completion_fields["worker_output_captured"] is True
    assert completion_fields["worker_output_excerpt"] == (
        "INFO browser_use.Agent Step 1: click download"
    )
    assert_logs_have_required_fields(_service_events(caplog))

def test_browser_worker_subprocess_discards_sensitive_request_payload_after_run(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user with Market Lense",
        task_prompt="task with openrouter-key and Market Lense",
    )
    download_dir = tmp_path / "worker-download"
    payload_path = download_dir / "browser_agent_worker_request.json"
    response_path = download_dir / "browser_agent_worker_response.json"

    def fake_run(*args, **kwargs):
        assert payload_path.exists()
        payload_text = payload_path.read_text(encoding="utf-8")
        assert "openrouter-key" in payload_text
        assert "Market Lense" in payload_text
        response_path = Path(args[0][-1])
        response_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "ok",
                    "result": {
                        "schema_version": "1.0",
                        "raw_model_response": "{}",
                        "final_page_url": "https://example.com/final",
                        "final_page_title": "Final",
                        "final_page_html": "<html></html>",
                        "downloaded_files": [],
                        "attachment_paths": [],
                        "network_resource_urls": [],
                        "network_events": [],
                        "html_snapshot_path": "",
                        "screenshot_path": "",
                    },
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="")

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    result = browser_runtime._run_browser_report_download_agent_subprocess(
        request=request,
        ctx=run_context,
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=download_dir,
        prompt_bundle=prompt_bundle,
    )

    assert result.final_page_url == "https://example.com/final"
    assert response_path.exists()
    assert not payload_path.exists()

def test_browser_worker_subprocess_discards_sensitive_request_payload_after_timeout(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user with Market Lense",
        task_prompt="task with openrouter-key and Market Lense",
    )
    download_dir = tmp_path / "worker-download"
    payload_path = download_dir / "browser_agent_worker_request.json"

    def fake_run(*args, **kwargs):
        assert payload_path.exists()
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=kwargs["timeout"],
            output="INFO browser_use.Agent still running",
        )

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    with pytest.raises(AppError) as exc_info:
        browser_runtime._run_browser_report_download_agent_subprocess(
            request=request,
            ctx=run_context,
            normalized_url=request.url,
            execution_url=request.url,
            download_dir=download_dir,
            prompt_bundle=prompt_bundle,
        )

    assert exc_info.value.code == "browser_download_agent_timeout"
    assert not payload_path.exists()

def test_browser_worker_subprocess_sanitizes_failure_output_excerpt(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="task",
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="browser_use.Agent🤖\r\n\x1b[31mStep 1 failed\x1b[0m\r\n",
        )

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    with pytest.raises(AppError) as exc_info:
        browser_runtime._run_browser_report_download_agent_subprocess(
            request=request,
            ctx=run_context,
            normalized_url=request.url,
            execution_url=request.url,
            download_dir=tmp_path / "worker-download",
            prompt_bundle=prompt_bundle,
        )

    assert exc_info.value.code == "browser_download_agent_missing_result"
    assert exc_info.value.context == {
        "normalized_url": "https://example.com/report",
        "return_code": 1,
        "worker_output_excerpt": "browser_use.Agent\nStep 1 failed",
    }
    completion_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_worker_complete"
    ]
    assert len(completion_events) == 1
    completion_fields = completion_events[0]["fields"]
    assert completion_fields["worker_output_excerpt"] == (
        "browser_use.Agent\nStep 1 failed"
    )
    assert_logs_have_required_fields(_service_events(caplog))

def test_download_report_with_browser_use_cleans_stale_browser_use_temp_dirs_before_launch(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    stale_profile_dir = tmp_path / "browser-use-user-data-dir-stale"
    stale_profile_dir.mkdir(parents=True, exist_ok=True)
    (stale_profile_dir / "SingletonLock").write_text("lock", encoding="utf-8")
    stale_download_dir = tmp_path / "browser-use-downloads-stale"
    stale_download_dir.mkdir(parents=True, exist_ok=True)
    (stale_download_dir / "artifact.tmp").write_text("x", encoding="utf-8")
    old_timestamp = time.time() - (
        browser_runtime._STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS + 60.0
    )
    os.utime(stale_profile_dir, (old_timestamp, old_timestamp))
    os.utime(stale_download_dir, (old_timestamp, old_timestamp))

    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime.tempfile,
        "gettempdir",
        lambda: str(tmp_path),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/stale-temp-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert not stale_profile_dir.exists()
    assert not stale_download_dir.exists()

def test_download_report_with_browser_use_cleans_new_browser_use_temp_dirs_after_run(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class TempLeakAgent(original_runtime):
        def run_sync(self, max_steps: int):
            leaked_profile_dir = tmp_path / "browseruse-tmp-created-during-run"
            leaked_profile_dir.mkdir(parents=True, exist_ok=True)
            (leaked_profile_dir / "cache.tmp").write_text("temp", encoding="utf-8")
            return super().run_sync(max_steps)

    runtime.Agent = TempLeakAgent
    external_boundary_mocks_only.setattr(
        browser_runtime.tempfile,
        "gettempdir",
        lambda: str(tmp_path),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/temp-leak-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert not (tmp_path / "browseruse-tmp-created-during-run").exists()

def test_download_report_with_browser_use_reuses_bounded_same_publisher_profile(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="market_lense.browser_report_download_service.session_reuse",
    )
    reuse_base_dir = tmp_path / "session-reuse"
    settings = replace(
        _settings(tmp_path),
        session_reuse_policy=BrowserDownloadSessionReusePolicy(
            schema_version="1.0",
            enabled=True,
            mode="same_publisher_batch",
            session_key="batch-key",
            publisher_scope="example.com",
            ttl_seconds=120.0,
            base_dir=str(reuse_base_dir),
        ),
    )
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_browser = runtime.Browser
    browser_profile_paths: list[str] = []

    class ReuseTrackingBrowser(original_browser):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            browser_profile_paths.append(str(kwargs.get("user_data_dir") or ""))

    runtime.Browser = ReuseTrackingBrowser
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    first = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/reuse-report",
            settings=settings,
        ),
        run_context,
    )
    second = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/reuse-report",
            settings=settings,
        ),
        run_context,
    )

    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"
    assert len(browser_profile_paths) == 2
    assert browser_profile_paths[0] == browser_profile_paths[1]
    profile_path = Path(browser_profile_paths[0])
    assert profile_path.exists()
    assert (profile_path / "session_reuse_ledger.json").exists()
    reuse_events = []
    for record in caplog.records:
        payload = json.loads(record.message)
        if payload.get("event") == "browser_report_download_session_reuse_resolved":
            reuse_events.append(payload)
    assert [event["fields"]["profile_reused"] for event in reuse_events[-2:]] == [
        False,
        True,
    ]

__all__ = [
    "test_download_report_with_browser_use_lookup_submission_assist_recovers_lookup_blocked_submit",
    "test_browser_worker_main_preserves_candidate_trace",
    "test_browser_worker_main_redacts_identity_values_from_persisted_response",
    "test_browser_worker_subprocess_forces_utf8_and_captures_output",
    "test_browser_worker_subprocess_discards_sensitive_request_payload_after_run",
    "test_browser_worker_subprocess_discards_sensitive_request_payload_after_timeout",
    "test_browser_worker_subprocess_sanitizes_failure_output_excerpt",
    "test_download_report_with_browser_use_cleans_stale_browser_use_temp_dirs_before_launch",
    "test_download_report_with_browser_use_cleans_new_browser_use_temp_dirs_after_run",
    "test_download_report_with_browser_use_reuses_bounded_same_publisher_profile",
]
