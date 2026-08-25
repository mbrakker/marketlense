# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_browser_preflight.py"
)

from ._shared import *  # noqa: F401,F403


def test_agent_fallback_requires_all_eligible_deterministic_playbooks() -> None:
    selected = [
        SimpleNamespace(playbook_id="publisher-route-a", host_patterns=["a.test"]),
        SimpleNamespace(playbook_id="publisher-route-b", host_patterns=["b.test"]),
    ]

    assert (
        service._deterministic_agent_fallback_is_admitted(
            selected_playbooks=selected,
            attempted_playbook_ids=["publisher-route-a"],
        )
        is False
    )
    assert (
        service._deterministic_agent_fallback_is_admitted(
            selected_playbooks=selected,
            attempted_playbook_ids=["publisher-route-a", "publisher-route-b"],
        )
        is True
    )


def test_preflight_thread_envelope_returns_when_async_cancellation_is_ignored() -> None:
    release = threading.Event()

    async def ignores_cancellation() -> None:
        while not release.is_set():
            try:
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                continue

    coroutine = ignores_cancellation()
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="browser preflight session timed out"):
            try:
                preflight_runtime._run_coroutine_in_thread(
                    coroutine,
                    timeout_seconds=0.01,
                    grace_seconds=0.01,
                )
            except TypeError:
                coroutine.close()
                raise
    finally:
        release.set()
    assert time.monotonic() - started < 0.5


def test_preflight_runs_on_the_calling_thread_when_no_event_loop_is_active() -> None:
    caller_thread = threading.get_ident()

    async def record_thread() -> int:
        return threading.get_ident()

    assert (
        preflight_runtime._run_preflight_coroutine(
            record_thread(),
            timeout_seconds=0.1,
            grace_seconds=0.1,
        )
        == caller_thread
    )


def test_preflight_runner_preserves_the_browser_event_loop_for_handoff() -> None:
    async def record_loop_id() -> int:
        return id(asyncio.get_running_loop())

    with asyncio.Runner() as runner:
        first_loop_id = preflight_runtime._run_preflight_coroutine(
            record_loop_id(),
            timeout_seconds=0.1,
            grace_seconds=0.1,
            event_loop_runner=runner,
        )
        second_loop_id = preflight_runtime._run_preflight_coroutine(
            record_loop_id(),
            timeout_seconds=0.1,
            grace_seconds=0.1,
            event_loop_runner=runner,
        )

    assert first_loop_id == second_loop_id


def test_preflight_runner_shutdown_does_not_block_on_a_stubborn_agent_task() -> None:
    release = asyncio.Event()

    async def ignores_cancellation() -> None:
        while not release.is_set():
            try:
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                continue

    async def start_task() -> asyncio.Task[None]:
        return asyncio.create_task(ignores_cancellation())

    runner = asyncio.Runner()
    session = SimpleNamespace(event_loop_runner=runner)
    task = runner.run(start_task())
    started = time.monotonic()
    browser_runtime._close_preflight_event_loop_runner(session)

    assert time.monotonic() - started < 3.0
    assert session.event_loop_runner is None

    async def release_task() -> None:
        release.set()
        await asyncio.wait_for(task, timeout=0.5)

    runner.run(release_task())
    runner.close()


def test_augmented_error_context_retains_scalar_preflight_diagnostics() -> None:
    probe = BrowserPreflightProbeResult(
        schema_version="1.0",
        status="failed",
        started_url="https://example.com/report",
        final_url="https://example.com/report",
        final_title="",
        html_size=0,
        event_drain_seconds=0.35,
        duration_seconds=24.0,
        candidate_pdf_urls=[],
        selected_pdf_url="",
        observed_event_urls=[],
        network_event_count=0,
        evidence_labels=["preflight_failed", "preflight_phase_browser_start"],
        escalation_reason="browser preflight session timed out",
        avoided_agent_call=False,
        false_negative_rate_sample=0.0,
    )

    error = service._with_augmented_error_context(
        AppError(
            code="browser_download_agent_timeout",
            message="Browser agent timed out",
            retryable=False,
        ),
        normalized_url="https://example.com/report",
        execution_url="https://example.com/report",
        download_dir="downloads",
        route_family_hint="browser_email_form",
        browser_preflight_probe=probe,
    )

    assert error.context["preflight_diagnostics"] == {
        "status": "failed",
        "phase": "browser_start",
        "duration_seconds": 24.0,
        "final_url": "https://example.com/report",
        "html_size": 0,
        "evidence_labels": [
            "preflight_failed",
            "preflight_phase_browser_start",
        ],
    }


__all__ = [
    "test_agent_fallback_requires_all_eligible_deterministic_playbooks",
    "test_preflight_thread_envelope_returns_when_async_cancellation_is_ignored",
    "test_preflight_runs_on_the_calling_thread_when_no_event_loop_is_active",
    "test_preflight_runner_preserves_the_browser_event_loop_for_handoff",
    "test_preflight_runner_shutdown_does_not_block_on_a_stubborn_agent_task",
    "test_augmented_error_context_retains_scalar_preflight_diagnostics",
]
