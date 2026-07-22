"""Closed failure-to-recovery matrix for report reliability workflows.

Rules are deliberately finite.  They describe the only downstream work that
may be queued after a typed failure; a caller must still retain the checkpoint,
artifact, budget, and idempotency proof required by the canonical remediation
ledger before execution is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.contracts.remediation import RemediationActionCode


@dataclass(frozen=True)
class FailureRecoveryRule:
    workflow: str
    error_code: str
    retryability: bool
    retry_scope: str
    max_attempts: int
    required_checkpoint: str
    reusable_artifacts: tuple[str, ...]
    required_invalidations: tuple[str, ...]
    next_action: RemediationActionCode
    terminal_fallback: str


_RULES: tuple[FailureRecoveryRule, ...] = (
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="taxonomy_invalid_json",
        retryability=False,
        retry_scope="taxonomy",
        max_attempts=1,
        required_checkpoint="source_prepared",
        reusable_artifacts=("source_pdf", "analysis_pdf", "vector_store"),
        required_invalidations=("taxonomy",),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="taxonomy_schema_invalid",
        retryability=False,
        retry_scope="taxonomy",
        max_attempts=1,
        required_checkpoint="source_prepared",
        reusable_artifacts=("source_pdf", "analysis_pdf", "vector_store"),
        required_invalidations=("taxonomy",),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="category_fit_contradiction",
        retryability=False,
        retry_scope="category_fit",
        max_attempts=1,
        required_checkpoint="evidence_packs",
        reusable_artifacts=("source_pdf", "vector_store", "evidence_packs", "taxonomy"),
        required_invalidations=("context_category_fit",),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="final_html_internal_identifier",
        retryability=False,
        retry_scope="rendering",
        max_attempts=1,
        required_checkpoint="analysis_complete",
        reusable_artifacts=("analysis", "report_cards"),
        required_invalidations=("rendered_html", "publish_readiness"),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="missing_report_card_manifest",
        retryability=False,
        retry_scope="report_cards",
        max_attempts=1,
        required_checkpoint="analysis_complete",
        reusable_artifacts=("analysis", "rendered_html"),
        required_invalidations=("report_cards", "rendered_html", "publish_readiness"),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
    ),
    FailureRecoveryRule(
        workflow="publishing",
        error_code="wordpress_readback_failed",
        retryability=True,
        retry_scope="wordpress_readback",
        max_attempts=1,
        required_checkpoint="publication_preflight",
        reusable_artifacts=("rendered_html", "publish_readiness"),
        required_invalidations=("wordpress_readback",),
        next_action="retry_idempotent_publication",
        terminal_fallback="blocked",
    ),
)


def recovery_rule_for(workflow: str, error_code: str) -> FailureRecoveryRule | None:
    normalized_workflow = str(workflow or "").strip().lower()
    normalized_error = str(error_code or "").strip().lower()
    return next(
        (
            rule
            for rule in _RULES
            if rule.workflow == normalized_workflow
            and rule.error_code == normalized_error
        ),
        None,
    )


def recovery_rule_diagnostics(rule: FailureRecoveryRule | None) -> dict[str, object]:
    """Return durable, non-sensitive recovery evidence for a remediation row."""

    if rule is None:
        return {}
    return {
        "recovery_scope": rule.retry_scope,
        "required_checkpoint": rule.required_checkpoint,
        "reusable_artifacts": list(rule.reusable_artifacts),
        "required_invalidations": list(rule.required_invalidations),
        "terminal_fallback": rule.terminal_fallback,
        "recovery_max_attempts": rule.max_attempts,
    }
