from __future__ import annotations

from src.contracts.browser_download import (
    BrowserDownloadCaptchaHandoffPolicy,
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteSuppressionPolicy,
    DownloadTerminalEvidence,
)
from src.contracts.report_store import PublisherDownloadRouteResponse
from src.orchestrators._report_download_orchestrator.workflow import (
    _fresh_remembered_hard_blocker_suppression_reason,
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


def test_route_suppression_default_includes_typed_no_progress_terminal() -> None:
    policy = BrowserDownloadRouteSuppressionPolicy(schema_version="1.0")

    assert "blocked_no_progress" in policy.terminal_failure_classes


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
            "blocked_reason": "blocked_captcha",
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

def test_fresh_exact_verified_hard_blocker_requires_current_policy_and_handoff_guard(
) -> None:
    memory = _route_memory(updated_at=900)
    email_blocker = PublisherDownloadRouteResponse(
        **{
            **memory.__dict__,
            "blocked_reason": "blocked_email_domain",
            "terminal_evidence": DownloadTerminalEvidence(
                **{
                    **memory.terminal_evidence.__dict__,
                    "evidence_labels": ["blocked", "blocked_email_domain"],
                }
            ),
        }
    )
    policy = BrowserDownloadRouteSuppressionPolicy(
        schema_version="1.0",
        enabled=True,
        minimum_sample_size=3,
        terminal_failure_threshold=1.0,
        ttl_seconds=60,
        terminal_failure_classes=("blocked_email_domain",),
    )
    handoff_disabled = BrowserDownloadCaptchaHandoffPolicy(
        schema_version="1.0", enabled=False, timeout_seconds=120.0
    )

    assert _fresh_remembered_hard_blocker_suppression_reason(
        email_blocker,
        ttl_seconds=120,
        policy=policy,
        captcha_handoff_policy=handoff_disabled,
        revalidate_route_policy=False,
        now_seconds=1_000,
    ) == "fresh_remembered_blocked_email_domain"
    assert (
        _fresh_remembered_hard_blocker_suppression_reason(
            PublisherDownloadRouteResponse(
                **{**email_blocker.__dict__, "updated_at": 879}
            ),
            ttl_seconds=120,
            policy=policy,
            captcha_handoff_policy=handoff_disabled,
            revalidate_route_policy=False,
            now_seconds=1_000,
        )
        is None
    )
    assert (
        _fresh_remembered_hard_blocker_suppression_reason(
            PublisherDownloadRouteResponse(
                **{**email_blocker.__dict__, "route_status": "inferred"}
            ),
            ttl_seconds=120,
            policy=policy,
            captcha_handoff_policy=handoff_disabled,
            revalidate_route_policy=False,
            now_seconds=1_000,
        )
        is None
    )
    assert (
        _fresh_remembered_hard_blocker_suppression_reason(
            email_blocker,
            ttl_seconds=120,
            policy=BrowserDownloadRouteSuppressionPolicy(
                **{
                    **policy.__dict__,
                    "terminal_failure_classes": ("blocked_captcha",),
                }
            ),
            captcha_handoff_policy=handoff_disabled,
            revalidate_route_policy=False,
            now_seconds=1_000,
        )
        is None
    )
    assert (
        _fresh_remembered_hard_blocker_suppression_reason(
            email_blocker,
            ttl_seconds=120,
            policy=policy,
            captcha_handoff_policy=handoff_disabled,
            revalidate_route_policy=True,
            now_seconds=1_000,
        )
        is None
    )
    captcha_blocker = PublisherDownloadRouteResponse(
        **{
            **email_blocker.__dict__,
            "blocked_reason": "blocked_captcha",
            "terminal_evidence": DownloadTerminalEvidence(
                **{
                    **email_blocker.terminal_evidence.__dict__,
                    "evidence_labels": ["blocked", "blocked_captcha"],
                }
            ),
        }
    )
    assert (
        _fresh_remembered_hard_blocker_suppression_reason(
            captcha_blocker,
            ttl_seconds=120,
            policy=BrowserDownloadRouteSuppressionPolicy(
                **{
                    **policy.__dict__,
                    "terminal_failure_classes": ("blocked_captcha",),
                }
            ),
            captcha_handoff_policy=BrowserDownloadCaptchaHandoffPolicy(
                schema_version="1.0", enabled=True, timeout_seconds=120.0
            ),
            revalidate_route_policy=False,
            now_seconds=1_000,
        )
        is None
    )
