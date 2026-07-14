from __future__ import annotations

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    DownloadTerminalEvidence,
)
from src.contracts.report_store import PublisherDownloadRouteResponse
from src.orchestrators._report_download_orchestrator.workflow import (
    _remembered_route_memory,
    _should_avoid_mailbox_preflight_for_remembered_blocker,
)


def _route_memory(*, updated_at: int) -> PublisherDownloadRouteResponse:
    return PublisherDownloadRouteResponse(
        schema_version="1.0",
        normalized_url="https://example.com/report",
        source_url="https://example.com/reports",
        route_kind="email_delivery",
        route_summary="Submit the verified email form.",
        outcome="email_requested",
        route_family="browser_email_form",
        route_status="verified",
        resolved_target_url="https://example.com/report",
        route_steps=[],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="",
            form_disappeared=False,
            final_page_url="https://example.com/report",
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url="https://example.com/report",
            final_page_title="Report",
            terminal_text_excerpt="Email delivery required.",
            artifact_url="https://example.com/report",
            artifact_kind="email_delivery",
            artifact_validation_status="blocked",
            artifact_validation_detail="Verified form requires a matching mailbox.",
            confirmation_signal_count=1,
            traversed_page_urls=["https://example.com/report"],
        ),
        browser_had_structured_result=True,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        updated_at=updated_at,
        attempts=2,
        verified_successes=1,
        last_n_outcomes=["email_requested"],
        confidence_score=0.8,
    )


def test_route_memory_uses_fresh_evidence_within_configured_ttl() -> None:
    memory = _remembered_route_memory(
        _route_memory(updated_at=900),
        ttl_seconds=120,
        now_seconds=1_000,
    )

    assert memory is not None
    assert memory.route_family == "browser_email_form"
    assert memory.updated_at == 900


def test_route_memory_fails_closed_when_evidence_is_stale_or_unverifiable() -> None:
    assert (
        _remembered_route_memory(
            _route_memory(updated_at=879),
            ttl_seconds=120,
            now_seconds=1_000,
        )
        is None
    )


def test_fresh_hard_blocker_avoids_mailbox_preflight_unless_revalidation_is_explicit() -> None:
    memory = _route_memory(updated_at=900)
    memory = PublisherDownloadRouteResponse(
        **{
            **memory.__dict__,
            "terminal_evidence": DownloadTerminalEvidence(
                **{
                    **memory.terminal_evidence.__dict__,
                    "evidence_labels": ["blocked_captcha"],
                }
            ),
        }
    )

    assert _should_avoid_mailbox_preflight_for_remembered_blocker(
        memory,
        ttl_seconds=120,
        revalidate_route_policy=False,
        now_seconds=1_000,
    )
    assert not _should_avoid_mailbox_preflight_for_remembered_blocker(
        memory,
        ttl_seconds=120,
        revalidate_route_policy=True,
        now_seconds=1_000,
    )
    assert (
        _remembered_route_memory(
            _route_memory(updated_at=0),
            ttl_seconds=120,
            now_seconds=1_000,
        )
        is None
    )
