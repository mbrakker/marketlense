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
    avoided_stages: tuple[str, ...]
    avoided_provider_calls: tuple[str, ...]
    avoided_token_estimate: int | None
    avoided_cost_estimate_usd: float | None


_RULES: tuple[FailureRecoveryRule, ...] = (
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="taxonomy_invalid_json",
        retryability=True,
        retry_scope="taxonomy",
        max_attempts=1,
        required_checkpoint="selection_complete",
        reusable_artifacts=("source_pdf", "analysis_pdf", "vector_store"),
        required_invalidations=("report_vs/taxonomy",),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
        avoided_stages=("source_prepared", "selection_complete"),
        avoided_provider_calls=("pdf_parse", "ocr", "crop_render", "crop_qa"),
        avoided_token_estimate=None,
        avoided_cost_estimate_usd=None,
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="taxonomy_schema_invalid",
        retryability=True,
        retry_scope="taxonomy",
        max_attempts=1,
        required_checkpoint="selection_complete",
        reusable_artifacts=("source_pdf", "analysis_pdf", "vector_store"),
        required_invalidations=("report_vs/taxonomy",),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
        avoided_stages=("source_prepared", "selection_complete"),
        avoided_provider_calls=("pdf_parse", "ocr", "crop_render", "crop_qa"),
        avoided_token_estimate=None,
        avoided_cost_estimate_usd=None,
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="category_fit_contradiction",
        retryability=True,
        retry_scope="category_fit",
        max_attempts=1,
        required_checkpoint="selection_complete",
        reusable_artifacts=("source_pdf", "analysis_pdf", "vector_store"),
        required_invalidations=("report_vs/context_category_fit",),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
        avoided_stages=("source_prepared", "selection_complete"),
        avoided_provider_calls=("pdf_parse", "ocr", "crop_render", "crop_qa"),
        avoided_token_estimate=None,
        avoided_cost_estimate_usd=None,
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="unsupported_material_claim",
        retryability=True,
        retry_scope="affected_claim_or_insight",
        max_attempts=1,
        required_checkpoint="analysis_complete",
        reusable_artifacts=("analysis_pdf", "artifacts", "validation"),
        required_invalidations=("report_vs/artifacts/insights_final",),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
        avoided_stages=("source_prepared", "selection_complete"),
        avoided_provider_calls=(
            "pdf_parse",
            "ocr",
            "crop_render",
            "crop_qa",
            "taxonomy_model",
            "category_fit_model",
            "evidence_pack_model",
        ),
        avoided_token_estimate=None,
        avoided_cost_estimate_usd=None,
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="final_html_internal_identifier",
        retryability=True,
        retry_scope="rendering",
        max_attempts=1,
        required_checkpoint="analysis_complete",
        reusable_artifacts=("analysis_pdf", "artifacts", "validation"),
        required_invalidations=("rendered_html", "publish_readiness"),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
        avoided_stages=("source_prepared", "selection_complete", "analysis_complete"),
        avoided_provider_calls=(
            "pdf_parse",
            "ocr",
            "crop_render",
            "crop_qa",
            "vector_store",
            "report_analysis_model",
            "validator_model",
        ),
        avoided_token_estimate=None,
        avoided_cost_estimate_usd=None,
    ),
    FailureRecoveryRule(
        workflow="report_generation",
        error_code="missing_report_card_manifest",
        retryability=True,
        retry_scope="report_cards",
        max_attempts=1,
        required_checkpoint="analysis_complete",
        reusable_artifacts=("analysis_pdf", "artifacts", "validation"),
        required_invalidations=("report_cards", "rendered_html", "publish_readiness"),
        next_action="rerun_targeted_artifact_family",
        terminal_fallback="permanent_failure",
        avoided_stages=("source_prepared", "selection_complete", "analysis_complete"),
        avoided_provider_calls=(
            "pdf_parse",
            "ocr",
            "crop_render",
            "crop_qa",
            "vector_store",
            "report_analysis_model",
            "validator_model",
        ),
        avoided_token_estimate=None,
        avoided_cost_estimate_usd=None,
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
        avoided_stages=(
            "source_prepared",
            "selection_complete",
            "analysis_complete",
            "render_complete",
        ),
        avoided_provider_calls=(
            "pdf_parse",
            "ocr",
            "crop_render",
            "crop_qa",
            "vector_store",
            "report_analysis_model",
            "validator_model",
            "html_render",
            "wordpress_write",
        ),
        avoided_token_estimate=None,
        avoided_cost_estimate_usd=None,
    ),
)

_ERROR_CODE_ALIASES = {
    "wp_post_readback_failed": "wordpress_readback_failed",
    "wordpress_idempotency_readback_missing": "wordpress_readback_failed",
    "wordpress_post_create_readback_missing": "wordpress_readback_failed",
}
_TYPED_RECOVERY_CODES = {rule.error_code for rule in _RULES}


def canonical_failure_code(error_code: str) -> str:
    """Normalize historic provider names to the finite recovery taxonomy."""

    raw = str(error_code or "").strip()
    normalized = raw.lower()
    # Typed application failures use lower-case stable codes and are compared
    # case-insensitively here. Unexpected exception class names retain their
    # existing spelling in durable state, preserving the generic remediation
    # ledger contract while still being excluded from typed auto-recovery.
    if normalized in _TYPED_RECOVERY_CODES:
        return normalized
    return _ERROR_CODE_ALIASES.get(normalized, raw)


def recovery_rule_for(workflow: str, error_code: str) -> FailureRecoveryRule | None:
    normalized_workflow = str(workflow or "").strip().lower()
    normalized_error = canonical_failure_code(error_code)
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
        "retryability": rule.retryability,
        "recovery_scope": rule.retry_scope,
        "required_checkpoint": rule.required_checkpoint,
        "reusable_artifacts": list(rule.reusable_artifacts),
        "required_invalidations": list(rule.required_invalidations),
        "terminal_fallback": rule.terminal_fallback,
        "recovery_max_attempts": rule.max_attempts,
        "avoided_stages": list(rule.avoided_stages),
        "avoided_provider_calls": list(rule.avoided_provider_calls),
        "avoided_token_estimate": rule.avoided_token_estimate,
        "avoided_cost_estimate_usd": rule.avoided_cost_estimate_usd,
        "avoidance_cost_status": (
            "known" if rule.avoided_cost_estimate_usd is not None else "unpriced"
        ),
    }
