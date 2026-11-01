from __future__ import annotations

from dataclasses import replace

import pytest

from src.contracts.public_editorial_quality import (
    PublicEditorialQualityIssue,
    PublicEditorialQualityReport,
)
from src.contracts.validation import ValidationReport
from src.generators.public_editorial_quality_generator import (
    merge_public_editorial_quality_validation,
)
from src.generators.verified_claims_canary import VisualAuthorityCanaryConfig
from src.orchestrators._report_analysis_orchestrator.validation import (
    _validate_public_editorial_review_payload,
)
from src.orchestrators._report_generation_orchestrator.resume import (
    _require_verified_authority_snapshot,
)
from src.utils.errors import AppError
from src.utils.verified_facts import (
    build_verified_authority_context,
    verified_source_identity_matches_runtime,
)
from tests._test_report_render_generator._split_support_cases_01_render_output_and_cards import (
    _runtime,
)
from tests._test_validation_generator._shared import _ctx
from tests.test_pre_e2e_integrity import _valid_report_review_payload
from tests.test_verified_facts_validation_authority import _authority_artifacts


@pytest.mark.parametrize(
    ("status", "severity"),
    [("fail", "warning"), ("unresolved", "info")],
)
def test_public_item_failure_verdict_requires_blocking_severity(
    status: str, severity: str
) -> None:
    items, scope, payload = _valid_report_review_payload()
    payload["verdicts"][0].update(
        status=status,
        severity=severity,
        rule_id="public_editorial_quality.semantic_integrity",
        hard_fail_class="factual_error",
    )

    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(payload, items, _ctx(), scope)

    assert raised.value.code == "public_editorial_quality_review_status_conflict"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda verdict, item: verdict.update(severity="error"),
        lambda verdict, item: verdict.update(
            repair_target=str(item.get("repair_target") or "insights_bundle")
        ),
        lambda verdict, item: verdict.update(hard_fail_class="factual_error"),
    ],
)
def test_public_item_pass_verdict_cannot_carry_failure_fields(mutation) -> None:
    items, scope, payload = _valid_report_review_payload()
    mutation(payload["verdicts"][0], items[0])

    with pytest.raises(AppError) as raised:
        _validate_public_editorial_review_payload(payload, items, _ctx(), scope)

    assert raised.value.code == "public_editorial_quality_review_status_conflict"


def test_public_item_failure_with_error_remains_valid_and_is_blocking() -> None:
    items, scope, payload = _valid_report_review_payload()
    payload["verdicts"][0].update(
        status="fail",
        severity="error",
        rule_id="public_editorial_quality.semantic_integrity",
        hard_fail_class="factual_error",
        reason="The item conflicts with the retained source fact.",
    )

    _validate_public_editorial_review_payload(payload, items, _ctx(), scope)


def test_failed_quality_report_cannot_merge_to_validation_pass() -> None:
    quality = PublicEditorialQualityReport(
        report_id="report-1",
        status="fail",
        issues=[
            PublicEditorialQualityIssue(
                report_id="report-1",
                rule_id="public_editorial_quality.semantic_integrity",
                severity="warning",
                affected_artifact="insights_final",
                affected_field="insights:fact-1",
                explanation="The persisted report verdict is contradictory.",
                public_item_id="insights:fact-1",
            )
        ],
        publishable=False,
    )
    validation = ValidationReport(
        schema_version="1.1",
        status="pass",
        severity="pass",
        issues=[],
    )

    merged = merge_public_editorial_quality_validation(validation, quality)

    assert merged.status == "fail"
    assert merged.severity == "error"
    assert merged.issues
    assert merged.issues[0].rule_id == "public_editorial_quality.report_status_conflict"


@pytest.mark.parametrize(
    ("runtime", "verified", "expected"),
    [
        ("Frozen-Report", "frozen-report|pdf-sha256:" + "a" * 64, False),
        ("frozen-report", "frozen-report|pdf-sha256:" + "A" * 64, True),
        (
            "frozen-report|pdf-sha256:" + "a" * 64,
            "frozen-report|pdf-sha256:" + "A" * 64,
            True,
        ),
        (
            "frozen-report|pdf-sha256:" + "a" * 64 + "|suffix",
            "frozen-report|pdf-sha256:" + "a" * 64,
            False,
        ),
        ("prefix-frozen-report", "frozen-report|pdf-sha256:" + "a" * 64, False),
    ],
)
def test_verified_source_identity_runtime_matching_is_exact(
    runtime: str, verified: str, expected: bool
) -> None:
    assert verified_source_identity_matches_runtime(runtime, verified) is expected


def test_verified_authority_reentry_requires_current_canary_for_saved_context(
    tmp_path,
) -> None:
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    base_runtime = _runtime(tmp_path, md5="source-md5")
    runtime = replace(
        base_runtime,
        ctx=replace(base_runtime.ctx, source_identity_id=source_identity),
    )
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=source_identity
    )

    with pytest.raises(AppError) as raised:
        _require_verified_authority_snapshot(
            runtime,
            artifacts,
            None,
            saved_authority=authority,
            saved_evidence_packs=authority.evidence_packs,
        )

    assert raised.value.code == "verified_facts_canary_configuration_missing"
    assert raised.value.retryable is False


def test_verified_authority_reentry_accepts_only_matching_saved_snapshot(
    tmp_path,
) -> None:
    source_identity = "frozen-report|pdf-sha256:" + "a" * 64
    base_runtime = _runtime(tmp_path, md5="source-md5")
    runtime = replace(
        base_runtime,
        ctx=replace(base_runtime.ctx, source_identity_id=source_identity),
    )
    artifacts = _authority_artifacts()
    authority = build_verified_authority_context(
        artifacts, expected_source_identity=source_identity
    )
    canary = VisualAuthorityCanaryConfig(source_identity=source_identity)

    assert (
        _require_verified_authority_snapshot(
            runtime,
            artifacts,
            canary,
            saved_authority=authority,
            saved_evidence_packs=authority.evidence_packs,
        )
        == authority
    )

    with pytest.raises(AppError) as raised:
        _require_verified_authority_snapshot(
            runtime,
            artifacts,
            canary,
            saved_authority=replace(authority, verified_fact_digest="b" * 64),
            saved_evidence_packs=authority.evidence_packs,
        )
    assert raised.value.code == "verified_facts_canary_artifacts_invalid"

    with pytest.raises(AppError) as changed_runtime:
        _require_verified_authority_snapshot(
            replace(
                runtime,
                ctx=replace(
                    runtime.ctx,
                    source_identity_id="other-report|pdf-sha256:" + "a" * 64,
                ),
            ),
            artifacts,
            canary,
            saved_authority=authority,
            saved_evidence_packs=authority.evidence_packs,
        )
    assert changed_runtime.value.code == "verified_facts_canary_artifacts_invalid"
