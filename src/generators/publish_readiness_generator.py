"""Canonical, deterministic readiness gate for rendered report publication."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    CLAIM_VALIDATION_SCHEMA_VERSION,
    CLAIM_VALIDATION_VALIDATOR_VERSION,
    ClaimValidationPackage,
)
from src.contracts.public_editorial_quality import PublicEditorialQualityReport
from src.contracts.publish_readiness import (
    PUBLISH_READINESS_SCHEMA_VERSION,
    PUBLISH_READINESS_VALIDATOR_VERSION,
    PublishReadinessArtifact,
    PublishReadinessRefreshPlan,
    PublishReadinessRuleResult,
)
from src.contracts.validation import ValidationReport
from src.generators.claim_validation_generator import (
    claim_validation_package_hash_valid,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from src.utils.cache_utils import sha256_json
from src.utils.publication_projection import publication_projection_hash

_INTERNAL_TOKEN = re.compile(
    r"\b(?:evidence|claim|file|finding|insight|quote|figure)"
    r"(?:_[a-z0-9][a-z0-9_]*|-[a-z0-9-]*\d[a-z0-9-]*)\b",
    re.IGNORECASE,
)
_RAW_EVIDENCE_TOKEN = re.compile(
    r"\b(?:turn\d+(?:file|search)\d+|(?:f|e|ev|ic|fig)[_-]?\d{1,5})\b",
    re.IGNORECASE,
)
_PRIVATE_LOCATION = re.compile(
    r"(?:https?://(?:drive\.google\.com|localhost|127\.0\.0\.1)\S*|"
    r"\b[A-Za-z]:[\\/]|(?:^|[\"'])/(?:out|cache|state)/)",
    re.IGNORECASE,
)
_FILENAME_TITLE = re.compile(
    r"(?:^|\s)[^\s]+\.(?:pdf|html?|json|png|jpe?g|webp)(?:\s|$)", re.IGNORECASE
)
_DUPLICATED_YEAR = re.compile(r"\b(20\d{2})\D{0,4}\1\b")
_NON_PUBLIC_CARD_STATUSES = {
    "abstained",
    "limited",
    "not_applicable",
    "omitted",
    "text_only",
    "unavailable",
    "weak",
    "weak_evidence",
}
_MAX_READINESS_AGE = timedelta(hours=24)
_READINESS_REFRESH_AVOIDED_CALLS = [
    "crop_qa",
    "crop_render",
    "ocr",
    "pdf_parse",
    "report_analysis_model",
    "validator_model",
    "vector_store",
]
_ANALYSIS_RULES = {
    "publish_readiness.category_consistency",
    "publish_readiness.editorial_quality",
    "publish_readiness.material_claim_evidence",
    "publish_readiness.report_card_manifest",
    "publish_readiness.regeneration",
    "publish_readiness.semantic_grounding",
}
_BUILD_PROVENANCE_FIELDS = (
    "git_sha",
    "generation_run_id",
    "validation_run_id",
    "source_id",
    "source_md5",
    "artifact_hash",
    "generation_profile",
    "generated_at_utc",
)


@dataclass(frozen=True)
class PublishReadinessVerification:
    """Outcome of consuming a retained readiness decision at publication time."""

    status: str
    issues: list[str]


def plan_publish_readiness_refresh(
    *,
    report_id: str,
    readiness: PublishReadinessArtifact | None,
    final_html: str,
    configuration_hash: str = "",
    policy_hash: str = "",
    producer_revision: str = "",
    current_artifact_hashes: dict[str, str] | None = None,
    evaluated_at_utc: datetime,
    expiry_warning_window: timedelta = timedelta(hours=1),
) -> PublishReadinessRefreshPlan:
    """Classify one retained readiness decision without re-evaluating content.

    This pure boundary only proposes a checkpoint and invalidation.  The
    canonical lineage planner must still prove that proposal before execution.
    """
    evaluated_at = _as_utc(evaluated_at_utc)
    if readiness is None:
        return _refresh_plan(
            report_id=report_id,
            state="missing_unverifiable",
            reason="publish_readiness.missing",
            invalidated="publish_readiness.missing",
            selected_resume_stage=None,
            regenerated_stages=[],
            forced_invalidations={},
            configuration_hash=configuration_hash,
            policy_hash=policy_hash,
            producer_revision=producer_revision,
            readiness_artifact_hash="",
            execution_result="blocked",
        )

    verification = verify_publish_readiness(
        artifact=readiness,
        report_id=report_id,
        final_html=final_html,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
        producer_revision=producer_revision,
        now=evaluated_at,
    )
    issues = list(verification.issues)
    if current_artifact_hashes is not None and any(
        str(current_artifact_hashes.get(name) or "") != expected
        for name, expected in readiness.artifact_hashes.items()
    ):
        issues.append("publish_readiness.artifact_hash_changed")
    issues = sorted(set(issues))
    if verification.status == "pass" and not issues:
        expires_at = _parse_utc(readiness.expires_at_utc)
        if (
            expires_at is not None
            and expires_at - evaluated_at <= expiry_warning_window
        ):
            return _render_refresh_plan(
                report_id=report_id,
                state="expiring",
                reason="publish_readiness.expiring",
                invalidated="publish_readiness.expiring",
                configuration_hash=configuration_hash,
                policy_hash=policy_hash,
                producer_revision=producer_revision,
                readiness_artifact_hash=readiness.artifact_hash,
            )
        return _refresh_plan(
            report_id=report_id,
            state="ready",
            reason="publish_readiness.current",
            invalidated="",
            selected_resume_stage=None,
            regenerated_stages=[],
            forced_invalidations={},
            configuration_hash=configuration_hash,
            policy_hash=policy_hash,
            producer_revision=producer_revision,
            readiness_artifact_hash=readiness.artifact_hash,
            execution_result="not_required",
        )

    if "publish_readiness.not_ready" in issues:
        failed_rules = sorted(
            item.rule_id for item in readiness.rule_results if item.status == "fail"
        )
        if any(rule in _ANALYSIS_RULES for rule in failed_rules):
            reason = failed_rules[0] if failed_rules else "publish_readiness.not_ready"
            return _refresh_plan(
                report_id=report_id,
                state="failed",
                reason=reason,
                invalidated=reason,
                selected_resume_stage="selection_complete",
                regenerated_stages=["analysis_complete", "render_complete"],
                forced_invalidations={"validation": reason},
                execution_intent="targeted_repair",
                configuration_hash=configuration_hash,
                policy_hash=policy_hash,
                producer_revision=producer_revision,
                readiness_artifact_hash=readiness.artifact_hash,
            )
        reason = failed_rules[0] if failed_rules else "publish_readiness.not_ready"
        return _render_refresh_plan(
            report_id=report_id,
            state="failed",
            reason=reason,
            invalidated=reason,
            configuration_hash=configuration_hash,
            policy_hash=policy_hash,
            producer_revision=producer_revision,
            readiness_artifact_hash=readiness.artifact_hash,
        )

    if any(
        issue
        in {
            "publish_readiness.schema_unsupported",
            "publish_readiness.validator_unsupported",
            "publish_readiness.report_id_mismatch",
            "publish_readiness.configuration_changed",
            "publish_readiness.policy_changed",
            "publish_readiness.producer_revision_changed",
            "publish_readiness.artifact_hash_changed",
        }
        for issue in issues
    ):
        reason = issues[0]
        return _render_refresh_plan(
            report_id=report_id,
            state="incompatible",
            reason=reason,
            invalidated=reason,
            configuration_hash=configuration_hash,
            policy_hash=policy_hash,
            producer_revision=producer_revision,
            readiness_artifact_hash=readiness.artifact_hash,
        )

    if any(
        issue
        in {
            "publish_readiness.expired",
            "publish_readiness.final_html_changed",
            "publish_readiness.publication_projection_changed",
        }
        for issue in issues
    ):
        reason = issues[0]
        return _render_refresh_plan(
            report_id=report_id,
            state="stale",
            reason=reason,
            invalidated=reason,
            configuration_hash=configuration_hash,
            policy_hash=policy_hash,
            producer_revision=producer_revision,
            readiness_artifact_hash=readiness.artifact_hash,
        )

    reason = issues[0] if issues else "publish_readiness.unverifiable"
    return _refresh_plan(
        report_id=report_id,
        state="missing_unverifiable",
        reason=reason,
        invalidated=reason,
        selected_resume_stage=None,
        regenerated_stages=[],
        forced_invalidations={},
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
        producer_revision=producer_revision,
        readiness_artifact_hash=readiness.artifact_hash,
        execution_result="blocked",
    )


def publish_readiness_refresh_plan_payload(
    plan: PublishReadinessRefreshPlan,
) -> dict[str, Any]:
    """Serialize typed refresh telemetry for an atomic retained artifact."""
    return asdict(plan)


def complete_publish_readiness_refresh_plan(
    plan: PublishReadinessRefreshPlan,
    *,
    execution_result: str,
    execution_plan_hash: str,
    reused_stages: list[str],
    reused_artifacts: list[str],
    regenerated_stages: list[str],
    avoided_external_calls: list[str],
) -> PublishReadinessRefreshPlan:
    """Return the final immutable telemetry record for an executed refresh."""
    completed = replace(
        plan,
        execution_result=execution_result,
        execution_plan_hash=execution_plan_hash,
        reused_stages=sorted(set(reused_stages)),
        reused_artifacts=sorted(set(reused_artifacts)),
        regenerated_stages=list(regenerated_stages),
        avoided_external_calls=sorted(set(avoided_external_calls)),
        refresh_plan_hash="",
    )
    return replace(completed, refresh_plan_hash=_refresh_plan_hash(completed))


def _render_refresh_plan(
    *,
    report_id: str,
    state: str,
    reason: str,
    invalidated: str,
    configuration_hash: str,
    policy_hash: str,
    producer_revision: str,
    readiness_artifact_hash: str,
) -> PublishReadinessRefreshPlan:
    return _refresh_plan(
        report_id=report_id,
        state=state,
        reason=reason,
        invalidated=invalidated,
        selected_resume_stage="analysis_complete",
        regenerated_stages=["render_complete"],
        forced_invalidations={"rendered_html": reason},
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
        producer_revision=producer_revision,
        readiness_artifact_hash=readiness_artifact_hash,
    )


def _refresh_plan(
    *,
    report_id: str,
    state: str,
    reason: str,
    invalidated: str,
    selected_resume_stage: str | None,
    regenerated_stages: list[str],
    forced_invalidations: dict[str, str],
    execution_intent: str = "render_repair",
    configuration_hash: str,
    policy_hash: str,
    producer_revision: str,
    readiness_artifact_hash: str,
    execution_result: str = "planned",
) -> PublishReadinessRefreshPlan:
    reused_stages = (
        ["source_prepared", "selection_complete", "analysis_complete"]
        if selected_resume_stage == "analysis_complete"
        else (
            ["source_prepared", "selection_complete"] if selected_resume_stage else []
        )
    )
    plan = PublishReadinessRefreshPlan(
        report_id=str(report_id),
        previous_readiness_state=state,
        reason=reason,
        invalidated_artifact_or_check=invalidated,
        selected_resume_stage=selected_resume_stage,
        execution_intent=execution_intent,
        reused_stages=reused_stages,
        reused_artifacts=["source_pdf", "crop", "analysis", "validation"]
        if selected_resume_stage == "analysis_complete"
        else (["source_pdf", "crop"] if selected_resume_stage else []),
        regenerated_stages=regenerated_stages,
        forced_invalidations=dict(sorted(forced_invalidations.items())),
        configuration_hash=_hash_or_sentinel(configuration_hash, "configuration"),
        policy_hash=_hash_or_sentinel(policy_hash, "policy"),
        producer_revision=str(producer_revision or "workspace"),
        readiness_artifact_hash=readiness_artifact_hash,
        avoided_external_calls=(
            list(_READINESS_REFRESH_AVOIDED_CALLS)
            if selected_resume_stage == "analysis_complete"
            else []
        ),
        avoided_provider_calls=None,
        execution_result=execution_result,
    )
    return replace(plan, refresh_plan_hash=_refresh_plan_hash(plan))


def _refresh_plan_hash(plan: PublishReadinessRefreshPlan) -> str:
    payload = asdict(replace(plan, refresh_plan_hash=""))
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def evaluate_publish_readiness(
    *,
    report_id: str,
    artifacts: dict[str, Any],
    evidence_packs: dict[str, dict[str, Any]],
    validation_report: ValidationReport | None,
    final_html: str,
    final_html_path: str,
    category_ids: Iterable[object] = (),
    regeneration_attempts: Iterable[object] = (),
    artifact_hashes: dict[str, str] | None = None,
    configuration_hash: str = "",
    policy_hash: str = "",
    producer_revision: str = "",
    provenance: dict[str, str] | None = None,
    metadata_evidence: Mapping[str, object] | None = None,
    created_at: datetime | None = None,
    retained_claim_package: ClaimValidationPackage | Mapping[str, Any] | None = None,
    retained_claim_required: bool = False,
    report_card_manifest_path: str = "",
    source_id: str = "",
    source_md5: str = "",
) -> PublishReadinessArtifact:
    """Evaluate the one release policy over artifacts, final HTML and projection."""
    safe_artifacts = artifacts if isinstance(artifacts, dict) else {}
    safe_packs = evidence_packs if isinstance(evidence_packs, dict) else {}
    now = created_at or datetime.now(UTC)
    results: list[PublishReadinessRuleResult] = []
    results.append(_validation_result(validation_report))
    results.append(_report_card_manifest_result(report_card_manifest_path))
    results.append(
        _retained_claim_grounding_result(
            retained_claim_package=retained_claim_package,
            required=retained_claim_required,
            report_id=str(report_id),
            artifacts=safe_artifacts,
            evidence_packs=safe_packs,
            final_html=final_html,
            source_id=source_id,
            source_md5=source_md5,
            configuration_hash=configuration_hash,
            policy_hash=policy_hash,
        )
    )
    results.append(_category_result(safe_artifacts, category_ids, safe_packs))
    results.append(_material_evidence_result(safe_artifacts, safe_packs))
    results.append(_evidence_fidelity_result(safe_artifacts, safe_packs, final_html))
    results.append(_regeneration_result(regeneration_attempts))
    quality = evaluate_public_editorial_quality(
        report_id=str(report_id),
        artifacts=safe_artifacts,
        html=final_html,
        html_path=final_html_path,
        metadata_evidence=metadata_evidence,
    )
    results.append(_source_fidelity_result(quality))
    results.append(_figure_linkage_result(safe_artifacts, safe_packs, final_html))
    results.extend(
        _html_results(
            quality=quality,
            final_html=final_html,
        )
    )
    results.append(_build_traceability_result(final_html))
    results.append(_provenance_result(final_html, provenance or {}))
    results.sort(key=lambda item: item.rule_id)
    artifact = PublishReadinessArtifact(
        report_id=str(report_id),
        status="pass" if all(item.status == "pass" for item in results) else "fail",
        artifact_hashes={
            str(key): str(value)
            for key, value in sorted((artifact_hashes or {}).items())
            if str(key).strip() and str(value).strip()
        }
        | _retained_claim_package_artifact_hash(retained_claim_package),
        rule_results=results,
        final_html_hash=_sha256(final_html),
        publication_projection_hash=publication_projection_hash(final_html),
        configuration_hash=_hash_or_sentinel(configuration_hash, "configuration"),
        policy_hash=_hash_or_sentinel(policy_hash, "policy"),
        producer_revision=str(producer_revision or "workspace"),
        created_at_utc=now.isoformat(),
        expires_at_utc=(now + _MAX_READINESS_AGE).isoformat(),
        staleness_conditions=[
            "final_html_hash_changed",
            "publication_projection_hash_changed",
            "artifact_hash_changed",
            "retained_claim_grounding_changed",
            "configuration_hash_changed",
            "policy_hash_changed",
            "producer_revision_changed",
            "expired",
        ],
        provenance={
            str(key): str(value) for key, value in sorted((provenance or {}).items())
        },
    )
    return replace(artifact, artifact_hash=_artifact_signature(artifact))


def publish_readiness_payload(artifact: PublishReadinessArtifact) -> dict[str, Any]:
    """Serialize the artifact without exposing rendered content in events."""
    return asdict(artifact)


def parse_publish_readiness_payload(payload: object) -> PublishReadinessArtifact:
    """Parse the persisted artifact strictly enough for fail-closed publication."""
    data = payload if isinstance(payload, dict) else {}
    raw_results = data.get("rule_results")
    malformed = not isinstance(payload, dict) or not isinstance(raw_results, list)
    results: list[PublishReadinessRuleResult] = []
    for item in raw_results if isinstance(raw_results, list) else []:
        if not isinstance(item, dict):
            malformed = True
            continue
        surfaces = item.get("surfaces")
        if not isinstance(surfaces, list) or any(
            not isinstance(surface, str) for surface in surfaces
        ):
            malformed = True
            continue
        results.append(
            PublishReadinessRuleResult(
                rule_id=str(item.get("rule_id") or ""),
                status=str(item.get("status") or "fail"),
                surfaces=[surface for surface in surfaces if surface],
                detail=str(item.get("detail") or ""),
                schema_version=str(
                    item.get("schema_version") or PUBLISH_READINESS_SCHEMA_VERSION
                ),
            )
        )
    return PublishReadinessArtifact(
        report_id=str(data.get("report_id") or ""),
        status=str(data.get("status") or "fail"),
        artifact_hashes={
            str(key): str(value)
            for key, value in (data.get("artifact_hashes") or {}).items()
            if str(key) and str(value)
        }
        if isinstance(data.get("artifact_hashes"), dict)
        else {},
        rule_results=results,
        final_html_hash=str(data.get("final_html_hash") or ""),
        publication_projection_hash=str(data.get("publication_projection_hash") or ""),
        configuration_hash=str(data.get("configuration_hash") or ""),
        policy_hash=str(data.get("policy_hash") or ""),
        producer_revision=str(data.get("producer_revision") or ""),
        created_at_utc=str(data.get("created_at_utc") or ""),
        expires_at_utc=str(data.get("expires_at_utc") or ""),
        staleness_conditions=[
            str(value) for value in data.get("staleness_conditions", []) if str(value)
        ]
        if isinstance(data.get("staleness_conditions"), list)
        else [],
        provenance={
            str(key): str(value)
            for key, value in (data.get("provenance") or {}).items()
        }
        if isinstance(data.get("provenance"), dict)
        else {},
        artifact_hash=str(data.get("artifact_hash") or ""),
        validator_version=str(data.get("validator_version") or ""),
        schema_version="" if malformed else str(data.get("schema_version") or ""),
    )


def verify_publish_readiness(
    *,
    artifact: PublishReadinessArtifact | None,
    report_id: str,
    final_html: str,
    configuration_hash: str = "",
    policy_hash: str = "",
    producer_revision: str = "",
    now: datetime | None = None,
) -> PublishReadinessVerification:
    """Verify the existing decision; intentionally never re-evaluates quality rules."""
    if artifact is None:
        return PublishReadinessVerification("missing", ["publish_readiness.missing"])
    issues: list[str] = []
    if artifact.schema_version != PUBLISH_READINESS_SCHEMA_VERSION:
        issues.append("publish_readiness.schema_unsupported")
    if artifact.validator_version != PUBLISH_READINESS_VALIDATOR_VERSION:
        issues.append("publish_readiness.validator_unsupported")
    if artifact.report_id != str(report_id):
        issues.append("publish_readiness.report_id_mismatch")
    if artifact.status != "pass":
        issues.append("publish_readiness.not_ready")
    if not artifact.artifact_hash or artifact.artifact_hash != _artifact_signature(
        artifact
    ):
        issues.append("publish_readiness.signature_invalid")
    if artifact.final_html_hash != _sha256(final_html):
        issues.append("publish_readiness.final_html_changed")
    if artifact.publication_projection_hash != publication_projection_hash(final_html):
        issues.append("publish_readiness.publication_projection_changed")
    if configuration_hash and artifact.configuration_hash != _hash_or_sentinel(
        configuration_hash, "configuration"
    ):
        issues.append("publish_readiness.configuration_changed")
    if policy_hash and artifact.policy_hash != _hash_or_sentinel(policy_hash, "policy"):
        issues.append("publish_readiness.policy_changed")
    if producer_revision and artifact.producer_revision != producer_revision:
        issues.append("publish_readiness.producer_revision_changed")
    expires = _parse_utc(artifact.expires_at_utc)
    if expires is None or expires <= (now or datetime.now(UTC)):
        issues.append("publish_readiness.expired")
    return PublishReadinessVerification(
        "pass" if not issues else "fail", sorted(issues)
    )


def verify_publication_projection(
    *, artifact: PublishReadinessArtifact | None, projected_body_html: str
) -> PublishReadinessVerification:
    """Verify the completed WordPress body without rerunning editorial rules."""
    if artifact is None:
        return PublishReadinessVerification("missing", ["publish_readiness.missing"])
    if artifact.publication_projection_hash != publication_projection_hash(
        projected_body_html
    ):
        return PublishReadinessVerification(
            "fail", ["publish_readiness.publication_projection_changed"]
        )
    return PublishReadinessVerification("pass", [])


def _validation_result(
    validation_report: ValidationReport | None,
) -> PublishReadinessRuleResult:
    if validation_report is None:
        return _fail(
            "publish_readiness.semantic_grounding",
            ["validation"],
            "validation report missing",
        )
    failed = [
        issue
        for issue in validation_report.issues
        if str(issue.severity).casefold() == "error"
        or str(issue.rule_id).casefold() == "deferred_grounding_required"
    ]
    if validation_report.status != "pass" or failed:
        return _fail(
            "publish_readiness.semantic_grounding",
            ["validation"],
            "semantic or grounding validation did not pass",
        )
    return _pass("publish_readiness.semantic_grounding", ["validation"])


def _report_card_manifest_result(path: str) -> PublishReadinessRuleResult:
    if not str(path or "").strip():
        return _fail(
            "publish_readiness.report_card_manifest",
            ["report_card_manifest"],
            "report card manifest missing",
        )
    return _pass("publish_readiness.report_card_manifest", ["report_card_manifest"])


def _retained_claim_grounding_result(
    *,
    retained_claim_package: ClaimValidationPackage | Mapping[str, Any] | None,
    required: bool,
    report_id: str,
    artifacts: dict[str, Any],
    evidence_packs: dict[str, dict[str, Any]],
    final_html: str,
    source_id: str,
    source_md5: str,
    configuration_hash: str,
    policy_hash: str,
) -> PublishReadinessRuleResult:
    if retained_claim_package is None:
        if not required:
            return _pass(
                "publish_readiness.retained_claim_grounding",
                ["retained_claim_validation"],
                "package not required for this readiness evaluation",
            )
        return _fail(
            "publish_readiness.retained_claim_grounding",
            ["retained_claim_validation"],
            "package_missing; unsupported_factual_count=unknown; "
            "unresolved_factual_count=unknown",
        )

    payload = (
        asdict(retained_claim_package)
        if isinstance(retained_claim_package, ClaimValidationPackage)
        else dict(retained_claim_package)
    )
    lineage = payload.get("lineage")
    lineage = lineage if isinstance(lineage, Mapping) else {}
    results = payload.get("results")
    results = results if isinstance(results, list) else []
    problems: set[str] = set()
    if not lineage:
        problems.add("final_lineage_missing")
    elif lineage.get("schema_version") != "1.1":
        problems.add("final_lineage_schema_stale")
    if not str(configuration_hash or "").strip():
        problems.add("current_configuration_identity_missing")
    if not str(policy_hash or "").strip():
        problems.add("current_policy_identity_missing")
    unsupported = 0
    unresolved = 0
    semantic_rows: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for result in results:
        if not isinstance(result, Mapping):
            problems.add("package_result_invalid")
            continue
        candidate = result.get("candidate")
        if not isinstance(candidate, Mapping) or not isinstance(
            candidate.get("factual"), bool
        ):
            problems.add("package_candidate_invalid")
            continue
        if candidate.get("factual") is True:
            if result.get("status") == "unsupported":
                unsupported += 1
            elif result.get("status") == "unresolved":
                unresolved += 1
            elif result.get("status") not in {"supported", "not_applicable"}:
                problems.add("package_claim_status_invalid")
        if result.get("semantic_validator_used") is True:
            identity = result.get("semantic_identity")
            if not isinstance(identity, Mapping):
                problems.add("semantic_execution_identity_missing")
            else:
                semantic_rows.append((result, identity))

    recorded_unsupported = payload.get("unsupported_factual_count")
    recorded_unresolved = payload.get("unresolved_factual_count")
    recorded_semantic = payload.get("semantic_validation_count")
    if (
        not _is_nonnegative_int(recorded_unsupported)
        or recorded_unsupported != unsupported
    ):
        problems.add("unsupported_factual_count_mismatch")
    if (
        not _is_nonnegative_int(recorded_unresolved)
        or recorded_unresolved != unresolved
    ):
        problems.add("unresolved_factual_count_mismatch")
    if (
        not _is_nonnegative_int(recorded_semantic)
        or recorded_semantic != len(semantic_rows)
    ):
        problems.add("semantic_validation_count_mismatch")
    expected_package_status = (
        "not_publishable" if unsupported or unresolved else "awaiting_review"
    )
    if payload.get("readiness_status") != expected_package_status:
        problems.add("package_readiness_status_mismatch")

    if payload.get("schema_version") != CLAIM_VALIDATION_SCHEMA_VERSION:
        problems.add("package_schema_version_stale")
    if not claim_validation_package_hash_valid(payload):
        problems.add("package_hash_invalid")
    validation_identity = payload.get("validation_identity")
    if not isinstance(validation_identity, Mapping):
        problems.add("validation_execution_identity_missing")
    else:
        if validation_identity.get("schema_version") != "1.1":
            problems.add("validation_execution_identity_invalid")
        if validation_identity.get("report_id") != report_id:
            problems.add("report_id_stale")
        if not str(validation_identity.get("configuration_hash") or "").strip():
            problems.add("validation_execution_configuration_identity_missing")
        if not str(validation_identity.get("policy_hash") or "").strip():
            problems.add("validation_execution_policy_identity_missing")
        if (
            validation_identity.get("claim_validation_validator_version")
            != CLAIM_VALIDATION_VALIDATOR_VERSION
            or validation_identity.get("grounding_validator_version")
            != CLAIM_GROUNDING_VALIDATOR_VERSION
        ):
            problems.add("validation_execution_validator_version_stale")
        if validation_identity.get("source_id") != source_id:
            problems.add("validation_execution_source_id_stale")
        if validation_identity.get("source_md5") != source_md5:
            problems.add("validation_execution_source_md5_stale")
        if (
            configuration_hash
            and validation_identity.get("configuration_hash") != configuration_hash
        ):
            problems.add("validation_execution_configuration_hash_stale")
        if policy_hash and validation_identity.get("policy_hash") != policy_hash:
            problems.add("validation_execution_policy_hash_stale")

    current_artifact_hash = sha256_json(artifacts)
    if payload.get("artifact_hash") != current_artifact_hash:
        problems.add("artifact_hash_stale")
    if lineage.get("final_artifact_hash") != current_artifact_hash:
        problems.add("final_artifact_hash_stale")
    if lineage.get("publication_projection_hash") != publication_projection_hash(
        final_html
    ):
        problems.add("publication_projection_hash_stale")
    if lineage.get("report_id") != report_id:
        problems.add("report_id_stale")
    if lineage.get("evidence_pack_hash") != sha256_json(evidence_packs):
        problems.add("evidence_pack_hash_stale")
    if lineage.get("source_id") != source_id:
        problems.add("source_id_stale")
    if lineage.get("source_md5") != source_md5:
        problems.add("source_md5_stale")
    if (
        lineage.get("claim_validation_validator_version")
        != CLAIM_VALIDATION_VALIDATOR_VERSION
    ):
        problems.add("claim_validation_validator_version_stale")
    if lineage.get("grounding_validator_version") != CLAIM_GROUNDING_VALIDATOR_VERSION:
        problems.add("grounding_validator_version_stale")
    if configuration_hash and lineage.get("configuration_hash") != configuration_hash:
        problems.add("configuration_hash_stale")
    if policy_hash and lineage.get("policy_hash") != policy_hash:
        problems.add("policy_hash_stale")
    if not str(lineage.get("configuration_hash") or "").strip():
        problems.add("lineage_configuration_identity_missing")
    if not str(lineage.get("policy_hash") or "").strip():
        problems.add("lineage_policy_identity_missing")

    execution_identities: set[str] = set()
    prompt_hashes: set[str] = set()
    model_identities: set[str] = set()
    for result, identity in semantic_rows:
        if identity.get("schema_version") != "1.0":
            problems.add("semantic_execution_identity_invalid")
        required_identity_fields = (
            "claim_id",
            "claim_text_hash",
            "evidence_hash",
            "prompt_family",
            "prompt_content_hash",
            "execution_identity",
            "validator_version",
            "model_provider",
            "model_name",
            "configuration_policy_identity",
            "relevant_input_hash",
        )
        if any(
            not str(identity.get(field) or "").strip()
            for field in required_identity_fields
        ):
            problems.add("semantic_execution_identity_incomplete")
        if identity.get("validator_version") != CLAIM_GROUNDING_VALIDATOR_VERSION:
            problems.add("semantic_validator_version_stale")
        candidate = result.get("candidate")
        candidate = candidate if isinstance(candidate, Mapping) else {}
        if candidate.get("factual") is not True:
            problems.add("semantic_claim_not_factual")
        references = candidate.get("evidence_references")
        references = references if isinstance(references, list) else []
        reference_identity: list[dict[str, Any]] = []
        reference_ids: list[str] = []
        for reference in references:
            if not isinstance(reference, Mapping):
                problems.add("semantic_evidence_reference_invalid")
                continue
            reference_ids.append(str(reference.get("evidence_id") or ""))
            reference_identity.append(
                {
                    "evidence_id": reference.get("evidence_id"),
                    "source_pack": reference.get("source_pack", ""),
                    "page": reference.get("page"),
                    "text_hash": reference.get("text_hash", ""),
                }
            )
        if (
            identity.get("claim_id") != candidate.get("claim_id")
            or identity.get("claim_text_hash") != candidate.get("text_hash")
            or identity.get("evidence_ids") != reference_ids
            or identity.get("evidence_hash") != sha256_json(reference_identity)
        ):
            problems.add("semantic_claim_evidence_identity_mismatch")
        if identity.get("source_identity") != source_id:
            problems.add("semantic_source_identity_stale")
        expected_status = {
            "entailed": "supported",
            "contradicted": "unsupported",
            "not_established": "unresolved",
        }.get(result.get("semantic_outcome"))
        if (
            result.get("deterministic_status") != "unresolved"
            or expected_status != result.get("status")
        ):
            problems.add("semantic_disposition_mismatch")
        execution_identity = str(identity.get("execution_identity") or "")
        prompt_hash = str(identity.get("prompt_content_hash") or "")
        provider = str(identity.get("model_provider") or "")
        model = str(identity.get("model_name") or "")
        if execution_identity:
            execution_identities.add(execution_identity)
        if prompt_hash:
            prompt_hashes.add(prompt_hash)
        if provider and model:
            model_identities.add(f"{provider}/{model}")
    expected_execution_identities = sorted(execution_identities)
    if (
        sorted(_string_list(payload.get("semantic_execution_identities")))
        != expected_execution_identities
    ):
        problems.add("semantic_execution_identities_mismatch")
    if (
        sorted(_string_list(lineage.get("semantic_execution_identities")))
        != expected_execution_identities
    ):
        problems.add("lineage_semantic_execution_identities_mismatch")
    if sorted(_string_list(lineage.get("semantic_prompt_content_hashes"))) != sorted(
        prompt_hashes
    ):
        problems.add("semantic_prompt_identity_mismatch")
    if sorted(_string_list(lineage.get("semantic_model_identities"))) != sorted(
        model_identities
    ):
        problems.add("semantic_model_identity_mismatch")

    surfaces = ["retained_claim_validation"]
    if unsupported:
        surfaces.append("unsupported_factual_claims")
    if unresolved:
        surfaces.append("unresolved_material_factual_claims")
    detail = (
        f"unsupported_factual_count={unsupported}; "
        f"unresolved_factual_count={unresolved}"
    )
    if problems:
        detail = "package_invalid; " + detail + "; " + "; ".join(sorted(problems))
    elif unsupported or unresolved:
        detail = "not_publishable; " + detail
    if unsupported or unresolved or problems:
        return _fail(
            "publish_readiness.retained_claim_grounding",
            surfaces,
            detail,
        )
    return _pass(
        "publish_readiness.retained_claim_grounding",
        surfaces,
        detail,
    )


def _retained_claim_package_artifact_hash(
    package: ClaimValidationPackage | Mapping[str, Any] | None,
) -> dict[str, str]:
    if isinstance(package, ClaimValidationPackage):
        package_hash = package.package_hash
    elif isinstance(package, Mapping):
        package_hash = str(package.get("package_hash") or "")
    else:
        package_hash = ""
    return {"retained_claim_validation": package_hash} if package_hash else {}


def _is_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _string_list(value: object) -> list[str]:
    return (
        [str(item) for item in value if str(item).strip()]
        if isinstance(value, list)
        else []
    )


def _category_result(
    artifacts: dict[str, Any],
    category_ids: Iterable[object],
    evidence_packs: dict[str, dict[str, Any]],
) -> PublishReadinessRuleResult:
    canonical = _normalized_strings(category_ids)
    artifact_values = _normalized_strings(
        artifacts.get("categories") or artifacts.get("category_decisions") or []
    )
    if not canonical:
        if _has_explicit_uncategorized_abstention(evidence_packs):
            return _pass(
                "publish_readiness.category_consistency",
                ["categories", "context_category_fit"],
            )
        return _fail(
            "publish_readiness.category_consistency",
            ["categories", "artifacts.category_decisions"],
            "canonical category assignment missing",
        )
    if not artifact_values:
        return _fail(
            "publish_readiness.category_consistency",
            ["categories", "artifacts.category_decisions"],
            "retained category assignment missing",
        )
    if artifact_values != canonical:
        return _fail(
            "publish_readiness.category_consistency",
            ["categories", "artifacts.category_decisions"],
            "rendered category decisions differ from retained category assignment",
        )
    return _pass("publish_readiness.category_consistency", ["categories"])


def _has_explicit_uncategorized_abstention(
    evidence_packs: dict[str, dict[str, Any]],
) -> bool:
    """Accept only the audited no-category outcome produced after bounded repair."""
    fit_payload = evidence_packs.get("context_category_fit")
    if not isinstance(fit_payload, dict):
        return False
    if _normalized_strings(fit_payload.get("selected_category_ids") or []):
        return False
    fits = _dict_items(fit_payload.get("category_fits"))
    return bool(fits) and all(
        str(item.get("decision") or "").casefold() == "reject"
        and str(item.get("semantic_rule_status") or "").casefold() == "rejected"
        and str(item.get("remediation_signal") or "")
        == "topic_semantics_unresolved_abstained"
        for item in fits
    )


def _material_evidence_result(
    artifacts: dict[str, Any], evidence_packs: dict[str, dict[str, Any]]
) -> PublishReadinessRuleResult:
    valid_ids = _evidence_ids(evidence_packs)
    missing: list[str] = []
    invalid: list[str] = []
    for family, item in _material_claim_items(artifacts):
        evidence_ids = _claim_evidence_ids(item)
        if evidence_ids is None:
            invalid.append(family)
            continue
        if not evidence_ids or any(
            evidence_id not in valid_ids for evidence_id in evidence_ids
        ):
            missing.append(family)
    if invalid:
        return _fail(
            "publish_readiness.material_claim_evidence",
            ["artifacts", "evidence_packs"],
            f"{len(invalid)} material claims have an invalid evidence reference shape",
        )
    if missing:
        return _fail(
            "publish_readiness.material_claim_evidence",
            ["artifacts", "evidence_packs"],
            f"{len(missing)} material claims lack a valid retained evidence reference",
        )
    return _pass(
        "publish_readiness.material_claim_evidence", ["artifacts", "evidence_packs"]
    )


def _evidence_fidelity_result(
    artifacts: dict[str, Any],
    evidence_packs: dict[str, dict[str, Any]],
    final_html: str,
) -> PublishReadinessRuleResult:
    """Block only factual evidence that remains in the rendered public output."""
    fidelity = evidence_packs.get("evidence_fidelity")
    if not isinstance(fidelity, dict):
        return _pass("publish_readiness.evidence_fidelity", ["evidence_fidelity"])
    untrusted_ids = _untrusted_factual_evidence_ids(fidelity)
    if not untrusted_ids:
        return _pass("publish_readiness.evidence_fidelity", ["evidence_fidelity"])
    rendered_ids = _rendered_material_evidence_ids(artifacts, final_html)
    rendered_untrusted_ids = sorted(
        {
            evidence_id
            for untrusted_source_pack, evidence_id in untrusted_ids
            for rendered_source_pack, rendered_evidence_id in rendered_ids
            if evidence_id == rendered_evidence_id
            and (
                not untrusted_source_pack
                or not rendered_source_pack
                or untrusted_source_pack == rendered_source_pack
            )
        }
    )
    if rendered_untrusted_ids:
        return _fail(
            "publish_readiness.evidence_fidelity",
            [
                f"rendered_html:evidence:{evidence_id}"
                for evidence_id in rendered_untrusted_ids
            ],
            (
                f"audit_untrusted={len(untrusted_ids)}; "
                f"rendered_untrusted={len(rendered_untrusted_ids)}"
            ),
        )
    return _pass(
        "publish_readiness.evidence_fidelity",
        ["evidence_fidelity", "rendered_html"],
        f"audit_untrusted={len(untrusted_ids)}; rendered_untrusted=0",
    )


def _untrusted_factual_evidence_ids(
    fidelity: dict[str, Any],
) -> set[tuple[str, str]]:
    """Return only audit candidates whose factual support was not established."""
    identifiers: set[tuple[str, str]] = set()
    for result in _dict_items(fidelity.get("results")):
        candidate = result.get("candidate")
        if not isinstance(candidate, dict) or candidate.get("factual") is not True:
            continue
        if str(result.get("status") or "").casefold() == "supported":
            continue
        claim_id = str(candidate.get("claim_id") or "").strip()
        parts = claim_id.split(":", 2)
        if len(parts) == 3 and parts[0] == "evidence" and parts[2].strip():
            source_family = str(candidate.get("source_family") or "").strip()
            source_pack = (
                source_family.removeprefix("evidence_pack:").strip().casefold()
                if source_family.startswith("evidence_pack:")
                else ""
            )
            identifiers.add((source_pack, parts[2].strip()))
    return identifiers


def _rendered_material_evidence_ids(
    artifacts: dict[str, Any], final_html: str
) -> set[tuple[str, str]]:
    """Map retained material claims to evidence only when their text is public HTML."""
    rendered_text = _normalized_public_text(
        BeautifulSoup(final_html, "html.parser").get_text(" ", strip=True)
    )
    if not rendered_text:
        return set()
    identifiers: set[tuple[str, str]] = set()
    for family, item in _material_claim_items(artifacts):
        claim_text = _material_claim_text(family, item)
        if not claim_text or claim_text not in rendered_text:
            continue
        identities = _claim_evidence_identities(item)
        if identities:
            identifiers.update(identities)
    return identifiers


def _claim_evidence_identities(
    item: dict[str, Any],
) -> set[tuple[str, str]] | None:
    """Use typed source references when present, otherwise retain conservative IDs."""
    typed_references: set[tuple[str, str]] = set()
    saw_reference_field = False
    malformed_reference = False
    for field_name in ("evidence_references", "evidence_spans"):
        references = item.get(field_name)
        if references is None:
            continue
        saw_reference_field = True
        if not isinstance(references, (list, tuple)):
            malformed_reference = True
            continue
        for reference in references:
            if not isinstance(reference, dict):
                malformed_reference = True
                continue
            evidence_id = str(reference.get("evidence_id") or "").strip()
            source_pack = str(reference.get("source_pack") or "").strip().casefold()
            if not evidence_id or not source_pack:
                malformed_reference = True
                continue
            typed_references.add((source_pack, evidence_id))
    if saw_reference_field and typed_references and not malformed_reference:
        return typed_references

    evidence_ids = _claim_evidence_ids(item)
    if evidence_ids is None:
        return None
    return {("", evidence_id) for evidence_id in evidence_ids}


def _material_claim_text(family: str, item: dict[str, Any]) -> str:
    if family == "summary.claim_evidence_map":
        value = item.get("claim")
    elif family == "claim_ledgers":
        value = item.get("claim_text") or item.get("claim") or item.get("statement")
    else:
        value = item.get("text") or item.get("claim") or item.get("caption")
    return _normalized_public_text(str(value or ""))


def _normalized_public_text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _regeneration_result(
    regeneration_attempts: Iterable[object],
) -> PublishReadinessRuleResult:
    attempts = list(regeneration_attempts or [])
    if not attempts:
        return _pass("publish_readiness.regeneration_promotion", ["regeneration"])
    last = attempts[-1]
    outcome = str(
        last.get("promotion_outcome")
        if isinstance(last, dict)
        else getattr(last, "promotion_outcome", "")
    ).casefold()
    if outcome != "promoted":
        return _fail(
            "publish_readiness.regeneration_promotion",
            ["regeneration"],
            "latest regenerated artifact was not promoted",
        )
    return _pass("publish_readiness.regeneration_promotion", ["regeneration"])


def _figure_linkage_result(
    artifacts: dict[str, Any], evidence_packs: dict[str, dict[str, Any]], html: str
) -> PublishReadinessRuleResult:
    cards = _dict_items(artifacts.get("chart_insight_cards"))
    public_cards = [
        card
        for card in cards
        if str(card.get("status") or "").casefold() not in _NON_PUBLIC_CARD_STATUSES
        and card.get("crop_qa_accepted") is True
    ]
    candidates = _accepted_candidates(evidence_packs)
    evidence_ids = _evidence_ids(evidence_packs)
    insight_ids = {
        str(item.get("id") or "").strip()
        for item in _dict_items(artifacts.get("insights_final"))
        if str(item.get("id") or "").strip()
    }
    incomplete = 0
    for card in public_cards:
        candidate_id = str(card.get("candidate_id") or "").strip()
        candidate = candidates.get(candidate_id)
        source_page = str(card.get("source_page") or "").strip()
        evidence_id = str(card.get("evidence_id") or "").strip()
        insight_id = str(card.get("insight_id") or "").strip()
        caption = str(card.get("caption") or card.get("retained_caption") or "").strip()
        takeaway = str(card.get("public_takeaway") or "").strip()
        candidate_page = (
            str(candidate.get("source_page") or candidate.get("page") or "").strip()
            if candidate
            else ""
        )
        candidate_evidence_id = (
            str(candidate.get("evidence_id") or "").strip() if candidate else ""
        )
        if (
            candidate is None
            or not source_page
            or not candidate_page
            or candidate_page != source_page
            or evidence_id not in evidence_ids
            or (candidate_evidence_id and candidate_evidence_id != evidence_id)
            or insight_id not in insight_ids
            or not caption
            or not takeaway
        ):
            incomplete += 1
    rendered_cards = _rendered_chart_cards(html)
    expected_takeaways = {
        str(card.get("public_takeaway") or "").strip() for card in public_cards
    }
    rendered_takeaways = {
        takeaway
        for takeaway in expected_takeaways
        if takeaway
        and any(takeaway in rendered_card for rendered_card in rendered_cards)
    }
    if (
        incomplete
        or len(rendered_cards) != len(public_cards)
        or rendered_takeaways != expected_takeaways
    ):
        return _fail(
            "publish_readiness.figure_linkage",
            ["artifacts.chart_insight_cards", "rendered.chart_cards"],
            (
                "public chart cards are unlinked, weak, or differ from the "
                "accepted-card projection"
            ),
        )
    return _pass(
        "publish_readiness.figure_linkage",
        ["artifacts.chart_insight_cards", "rendered.chart_cards"],
    )


def _html_results(
    *, quality: PublicEditorialQualityReport, final_html: str
) -> list[PublishReadinessRuleResult]:
    editorial_result = _editorial_result(quality)
    document = BeautifulSoup(final_html, "html.parser")
    surfaces = _html_surfaces(document)
    joined = " ".join(value for _, value in surfaces)
    visible_or_metadata = " ".join(
        value for name, value in surfaces if name != "link_href"
    )
    results = [editorial_result]
    if (
        _INTERNAL_TOKEN.search(visible_or_metadata)
        or _RAW_EVIDENCE_TOKEN.search(visible_or_metadata)
        or _PRIVATE_LOCATION.search(joined)
    ):
        results.append(
            _fail(
                "publish_readiness.public_identifier_leak",
                [name for name, _ in surfaces],
                "internal identifier or private location rendered",
            )
        )
    else:
        results.append(
            _pass(
                "publish_readiness.public_identifier_leak",
                [name for name, _ in surfaces],
            )
        )
    scaffold_issue_ids = {
        "public_editorial_quality.mechanical_editorial_scaffold",
        "public_editorial_quality.literal_truncation",
    }
    if any(
        issue.affected_artifact == "rendered_html"
        and issue.rule_id in scaffold_issue_ids
        for issue in quality.issues
    ):
        results.append(
            _fail(
                "publish_readiness.rendered_scaffolding",
                [name for name, _ in surfaces],
                "mechanical scaffold or unresolved truncation rendered",
            )
        )
    else:
        results.append(
            _pass(
                "publish_readiness.rendered_scaffolding", [name for name, _ in surfaces]
            )
        )
    title_values = [
        value for name, value in surfaces if name in {"title", "h1", "heading"}
    ]
    if any(
        _FILENAME_TITLE.search(value) or _DUPLICATED_YEAR.search(value)
        for value in title_values
    ):
        results.append(
            _fail(
                "publish_readiness.public_title_quality",
                ["title", "heading"],
                "filename-style title or duplicated year rendered",
            )
        )
    else:
        results.append(
            _pass("publish_readiness.public_title_quality", ["title", "heading"])
        )
    if _has_repeated_boilerplate(surfaces):
        results.append(
            _fail(
                "publish_readiness.repeated_boilerplate",
                ["body", "caption", "quotation"],
                "substantial public sentence repeats",
            )
        )
    else:
        results.append(
            _pass(
                "publish_readiness.repeated_boilerplate",
                ["body", "caption", "quotation"],
            )
        )
    return results


def _provenance_result(
    html: str, provenance: dict[str, str]
) -> PublishReadinessRuleResult:
    document = BeautifulSoup(html, "html.parser")
    source = document.select_one("#source")
    source_links = source.select("a[href]") if source else []
    hrefs = [str(link.get("href") or "").strip() for link in source_links]
    safe_verified = {
        value.rstrip("/")
        for key, value in provenance.items()
        if key in {"publisher_landing_page_url", "original_report_url"}
        and _is_safe_public_url(value)
    }
    if any(
        not _is_safe_public_url(href) or href.rstrip("/") not in safe_verified
        for href in hrefs
    ):
        return _fail(
            "publish_readiness.public_source_provenance",
            ["source.links"],
            "public source link is not verified publisher provenance",
        )
    if not hrefs:
        safe_attribution = "Source URL: Not available"
        source_text = source.get_text(" ", strip=True) if source else ""
        if safe_verified or safe_attribution not in source_text:
            return _fail(
                "publish_readiness.public_source_provenance",
                ["source"],
                "missing safe attribution for unavailable publisher provenance",
            )
    return _pass(
        "publish_readiness.public_source_provenance", ["source", "source.links"]
    )


def _build_traceability_result(html: str) -> PublishReadinessRuleResult:
    expected_prefix = "marketbearing-build:"
    comments = re.findall(r"<!--(.*?)-->", str(html or ""), flags=re.DOTALL)
    block = next(
        (comment for comment in comments if expected_prefix in comment),
        "",
    )
    if not block:
        return _fail(
            "publish_readiness.build_traceability",
            ["html_comment"],
            "missing marketbearing-build provenance comment",
        )
    present = {
        match.group(1): match.group(2).strip()
        for match in re.finditer(
            r"^\s{2}([a-z0-9_]+):\s*(.*?)\s*$", block, re.MULTILINE
        )
    }
    missing = [field for field in _BUILD_PROVENANCE_FIELDS if not present.get(field)]
    if missing:
        return _fail(
            "publish_readiness.build_traceability",
            ["html_comment"],
            "missing build provenance values: " + ", ".join(missing),
        )
    return _pass("publish_readiness.build_traceability", ["html_comment"])


def _editorial_result(
    report: PublicEditorialQualityReport,
) -> PublishReadinessRuleResult:
    if report.status != "pass":
        return _fail(
            "publish_readiness.editorial_quality",
            ["artifacts", "rendered_html"],
            "canonical editorial rule failed",
        )
    return _pass("publish_readiness.editorial_quality", ["artifacts", "rendered_html"])


def _source_fidelity_result(
    report: PublicEditorialQualityReport,
) -> PublishReadinessRuleResult:
    """Project unwaivable atomic fidelity failures into signed readiness."""
    hard_failures = [issue for issue in report.issues if issue.hard_fail_class]
    if hard_failures:
        return _fail(
            "publish_readiness.source_fidelity",
            sorted(
                issue.public_item_id for issue in hard_failures if issue.public_item_id
            ),
            "unresolved source-fidelity hard failure: "
            + ", ".join(sorted({issue.hard_fail_class for issue in hard_failures})),
        )
    return _pass("publish_readiness.source_fidelity", ["public_items"])


def _html_surfaces(document: BeautifulSoup) -> list[tuple[str, str]]:
    surfaces: list[tuple[str, str]] = []
    for tag_name in (
        "title",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "figcaption",
        "blockquote",
    ):
        for node in document.find_all(tag_name):
            surfaces.append(
                (
                    "heading" if tag_name.startswith("h") else tag_name,
                    node.get_text(" ", strip=True),
                )
            )
    body = (
        document.body.get_text(" ", strip=True)
        if document.body
        else document.get_text(" ", strip=True)
    )
    surfaces.append(("body", body))
    for node in document.select("a"):
        surfaces.append(("link_label", node.get_text(" ", strip=True)))
        surfaces.append(("link_href", str(node.get("href") or "")))
    for node in document.select("[alt]"):
        surfaces.append(("alt", str(node.get("alt") or "")))
    for node in document.select("meta, link[rel=canonical]"):
        name = str(node.get("name") or node.get("property") or node.get("rel") or "")
        value = str(node.get("content") or node.get("href") or "")
        surfaces.append(("metadata", " ".join(part for part in (name, value) if part)))
    for node in document.select('script[type="application/ld+json"]'):
        surfaces.append(("json_ld", node.get_text(" ", strip=True)))
    return [(name, value) for name, value in surfaces if value]


def _has_repeated_boilerplate(surfaces: list[tuple[str, str]]) -> bool:
    sentences: list[str] = []
    for name, text in surfaces:
        if name != "body":
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            normalized = " ".join(
                re.sub(r"[^a-z0-9]+", " ", sentence.casefold()).split()
            )
            if len(normalized) >= 48 and _looks_like_boilerplate(normalized):
                sentences.append(normalized)
    return any(count > 1 for count in _counts(sentences).values())


def _looks_like_boilerplate(sentence: str) -> bool:
    """Avoid treating deliberate evidence reuse as repeated generic copy."""
    return bool(
        re.search(
            r"\b(?:marketlense|marketbearing|source backed|decision relevance|"
            r"review this|this (?:report|source|briefing)|readers? can|"
            r"report can be evaluated)\b",
            sentence,
        )
    )


def _counts(items: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def _material_claim_items(
    artifacts: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    raw_summary = artifacts.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    for item in _dict_items(summary.get("claim_evidence_map")):
        if str(item.get("claim") or "").strip():
            items.append(("summary.claim_evidence_map", item))
    for family in ("insights_final", "quotes_final", "chart_insight_cards"):
        for item in _dict_items(artifacts.get(family)):
            text = str(
                item.get("text") or item.get("claim") or item.get("caption") or ""
            ).strip()
            if text:
                items.append((family, item))
    for item in _dict_items(artifacts.get("claim_ledgers")):
        text = str(
            item.get("claim_text") or item.get("claim") or item.get("statement") or ""
        ).strip()
        if text:
            items.append(("claim_ledgers", item))
    return items


def _claim_evidence_ids(item: dict[str, Any]) -> set[str] | None:
    scalar = item.get("evidence_id")
    plural = item.get("evidence_ids", [])
    if scalar is not None and not isinstance(scalar, str):
        return None
    if not isinstance(plural, (list, tuple)) or any(
        not isinstance(value, str) or not value.strip() for value in plural
    ):
        return None
    values = [scalar, *plural]
    return {
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    }


def _evidence_ids(value: object) -> set[str]:
    identifiers: set[str] = set()
    for item in _walk_dicts(value):
        for key in ("evidence_id", "id"):
            identifier = str(item.get(key) or "").strip()
            if identifier and (
                key == "evidence_id"
                or any(
                    name in item
                    for name in (
                        "snippet",
                        "evidence",
                        "text",
                        "citation",
                        "page",
                        "pages",
                    )
                )
            ):
                identifiers.add(identifier)
    return identifiers


def _accepted_candidates(
    evidence_packs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for pack in evidence_packs.values():
        if not isinstance(pack, dict):
            continue
        for field_name in (
            "chart_candidates",
            "charts",
            "figures",
            "visual_candidates",
        ):
            for item in _dict_items(pack.get(field_name)):
                candidate_id = str(
                    item.get("candidate_id")
                    or item.get("chart_id")
                    or item.get("id")
                    or ""
                ).strip()
                accepted = (
                    item.get("accepted") is True or item.get("crop_qa_accepted") is True
                )
                if candidate_id and accepted:
                    candidates[candidate_id] = item
    return candidates


def _rendered_chart_cards(html: str) -> list[str]:
    document = BeautifulSoup(html, "html.parser")
    return [
        node.get_text(" ", strip=True)
        for node in document.select(".chart-insight-grid > article")
    ]


def _walk_dicts(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_dicts(nested)


def _dict_items(value: object) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _normalized_strings(values: object) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            value = (
                value.get("category_id")
                or value.get("category")
                or value.get("id")
                or ""
            )
        token = str(value).strip()
        if token:
            normalized.add(token)
    return sorted(normalized)


def _is_safe_public_url(value: object) -> bool:
    parsed = urlsplit(str(value or "").strip())
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and not parsed.username
        and not parsed.password
        and parsed.hostname
        and parsed.hostname.casefold()
        not in {"drive.google.com", "localhost", "127.0.0.1", "::1"}
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_or_sentinel(value: str, namespace: str) -> str:
    normalized = str(value or "").strip()
    return (
        normalized
        if normalized
        else _sha256(f"publish-readiness:{namespace}:unavailable")
    )


def _artifact_signature(artifact: PublishReadinessArtifact) -> str:
    payload = asdict(replace(artifact, artifact_hash=""))
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _pass(
    rule_id: str, surfaces: list[str], detail: str = ""
) -> PublishReadinessRuleResult:
    return PublishReadinessRuleResult(
        rule_id=rule_id, status="pass", surfaces=surfaces, detail=detail
    )


def _fail(rule_id: str, surfaces: list[str], detail: str) -> PublishReadinessRuleResult:
    return PublishReadinessRuleResult(
        rule_id=rule_id, status="fail", surfaces=surfaces, detail=detail
    )


__all__ = [
    "PublishReadinessVerification",
    "complete_publish_readiness_refresh_plan",
    "evaluate_publish_readiness",
    "parse_publish_readiness_payload",
    "plan_publish_readiness_refresh",
    "publish_readiness_payload",
    "publish_readiness_refresh_plan_payload",
    "verify_publish_readiness",
    "verify_publication_projection",
]
