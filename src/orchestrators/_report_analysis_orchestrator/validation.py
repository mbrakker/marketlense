"""Validation fallback and regeneration-loop execution for report analysis.

This module owns validation failure fallback, validation snapshot persistence,
and bounded artifact regeneration attempts.
"""

from __future__ import annotations

import inspect
import re
from copy import deepcopy
from dataclasses import asdict, replace
from difflib import SequenceMatcher
from time import perf_counter
from typing import Any, Dict, List, Optional

from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    FailureFingerprint,
    RegenerationAttemptResult,
    RegenerationCandidateAudit,
    RegenerationLoopState,
    RepairDelta,
    RepairSeverityChange,
    candidate_rejection_fingerprint,
    repair_strategy_fingerprint,
)
from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.semantic_ids import ReportId
from src.contracts.soft_copy_claim_provenance import soft_copy_material_sentences
from src.contracts.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationRequest,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    merge_public_editorial_quality_validation,
    quality_report_payload,
)
from src.generators.report_generation_dependencies import ReportAnalysisDependencies
from src.generators.report_generation_shared import merge_artifacts_into_payload
from src.generators.validation.regeneration_candidate import (
    CandidateIntegrityResult,
    retained_claim_repair_issues,
    validate_regeneration_candidate,
)
from src.orchestrators._report_analysis_orchestrator.payload import (
    _ensure_report_payload_complete,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.orchestrators._report_analysis_orchestrator.shared import logger
from src.utils.cache_utils import sha256_json
from src.utils.editorial_identity import failed_insight_id
from src.utils.logging import child_context, log_event

__all__ = [
    "_evaluate_and_store_public_editorial_quality",
    "_run_validation_regeneration_loop",
    "_run_validation_with_fallback",
    "_store_validation_snapshot",
    "_promote_regeneration_candidate",
    "_store_regeneration_candidate_audit",
]


_DERIVED_ARTIFACT_ROOT_DEPENDENCIES = {
    "soft_copy_claim_provenance": frozenset(
        {"summary", "expert_comment", "linkedin_post"}
    ),
    "metric_spine": frozenset({"insights_final"}),
    "topics_covered": frozenset({"summary", "insights_final"}),
    "key_figures": frozenset({"insights_final", "summary"}),
    "chart_insight_cards": frozenset({"insights_final", "key_figures", "summary"}),
    "executive_advisory": frozenset({"insights_final", "summary", "quotes_final"}),
    "claim_ledgers": frozenset({"insights_final", "summary", "quotes_final"}),
    "family_status": frozenset(
        {
            "summary",
            "insights_candidates",
            "insights_final",
            "quotes_final",
            "expert_comment",
            "linkedin_post",
        }
    ),
    "_repair_evidence_selection": frozenset(
        {"summary", "expert_comment", "linkedin_post"}
    ),
    "_cache": frozenset(
        {
            "summary",
            "insights_candidates",
            "insights_final",
            "quotes_final",
            "expert_comment",
            "linkedin_post",
        }
    ),
}


def _evaluate_and_store_public_editorial_quality(
    *,
    runtime: ReportRuntimeState,
    dependencies: ReportAnalysisDependencies,
    artifacts: Dict[str, Any],
    pack_name: str,
    ctx,
) -> tuple[ValidationReport | None, str]:
    """Persist the private report and adapt blockers for the existing repair loop."""
    if not isinstance(artifacts, dict):
        return None, ""
    quality = evaluate_public_editorial_quality(
        report_id=str(runtime.file.file_id),
        artifacts=artifacts,
        disabled_rule_waivers=getattr(
            runtime.settings, "public_editorial_quality_disabled_rule_waivers", {}
        ),
    )
    stored = dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=pack_name,
            payload=quality_report_payload(quality),
            report_slug=runtime.report_name,
        ),
        ctx,
    ).output_path
    rule_ids = sorted({issue.rule_id for issue in quality.issues})
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="public_editorial_quality_evaluated",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "status": quality.status,
                "issue_count": len(quality.issues),
                "rule_ids": rule_ids,
                "validator_version": quality.validator_version,
                "quality_report_path": stored,
            },
        )
    )
    if quality.status == "fail":
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="public_editorial_quality_blocked",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "rule_ids": rule_ids,
                    "repairable_issue_count": sum(
                        issue.repair_eligible for issue in quality.issues
                    ),
                    "abstained_issue_count": sum(
                        issue.repair_status == "abstained" for issue in quality.issues
                    ),
                },
            )
        )
    if quality.disabled_rule_waivers:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="public_editorial_quality_rule_waived",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "rule_ids": sorted(quality.disabled_rule_waivers),
                    "waiver_count": len(quality.disabled_rule_waivers),
                },
            )
        )
    issues = merge_public_editorial_quality_validation(
        ValidationReport(
            schema_version="1.1",
            status="pass",
            issues=[],
            severity="pass",
        ),
        quality,
    )
    return issues, stored


def _merge_public_editorial_quality(
    validation: ValidationReport,
    editorial_validation: ValidationReport | None,
) -> ValidationReport:
    if editorial_validation is None:
        return validation
    return ValidationReport(
        schema_version=validation.schema_version,
        status=(
            "fail"
            if validation.status == "fail" or editorial_validation.status == "fail"
            else "pass"
        ),
        issues=list(validation.issues) + list(editorial_validation.issues),
        severity=(
            "error"
            if (
                validation.severity == "error"
                or editorial_validation.severity == "error"
            )
            else validation.severity
        ),
        source_path=validation.source_path,
    )


def _accepts_keyword(callable_obj, keyword: str) -> bool:
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False
    return keyword in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _run_validation_with_fallback(
    *,
    runtime: ReportRuntimeState,
    mode_ctx,
    dependencies: ReportAnalysisDependencies,
    validation_req: ValidationRequest,
    pack_name: str,
    openai_client=None,
) -> ValidationReport:
    kwargs = {}
    if openai_client is not None and _accepts_keyword(
        dependencies.run_validation, "openai_client"
    ):
        kwargs["openai_client"] = openai_client
    try:
        return dependencies.run_validation(
            validation_req,
            runtime.settings,
            child_context(mode_ctx, task_id=f"{mode_ctx.task_id}:{pack_name}"),
            pack_name=pack_name,
            report_name=runtime.report_name,
            md5=runtime.md5,
            **kwargs,
        )
    except Exception as exc:
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_failed",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "error": str(exc),
                    "mode": runtime.analysis_mode,
                    "pack_name": pack_name,
                },
            )
        )
        fallback_path = dependencies.analysis_pack_path(
            AnalysisPackPathRequest(
                schema_version="1.0",
                output_dir=runtime.settings.output_dir,
                report_id=ReportId(runtime.file.file_id),
                pack_name=pack_name,
                report_slug=runtime.report_name,
            ),
            mode_ctx,
        ).output_path
        fallback_report = ValidationReport(
            schema_version="1.1",
            status="fail",
            issues=[
                ValidationIssue(
                    schema_version="1.0",
                    message=f"Validation error: {exc}",
                    severity="error",
                    affected_section="validation",
                )
            ],
            severity="error",
            source_path=fallback_path,
        )
        try:
            dependencies.analysis_store_pack(
                AnalysisStorePackRequest(
                    schema_version="1.0",
                    output_dir=runtime.settings.output_dir,
                    report_id=ReportId(runtime.file.file_id),
                    pack_name=pack_name,
                    payload=fallback_report.to_dict(),
                    report_slug=runtime.report_name,
                ),
                mode_ctx,
            )
        except Exception as store_exc:  # pragma: no cover
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_store_failed",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "error": str(store_exc),
                        "mode": runtime.analysis_mode,
                    },
                )
            )
        return fallback_report


def _candidate_artifacts_path(response) -> str:
    """Use the candidate-only response field; tolerate legacy test doubles."""

    return str(getattr(response, "candidate_artifacts_path", "") or "").strip()


def _candidate_validation_report(
    validation: ValidationReport,
    candidate: CandidateIntegrityResult,
) -> ValidationReport:
    issues = list(candidate.issues) + list(validation.issues)
    severity = (
        "error"
        if any(item.severity == "error" for item in issues)
        else (
            "warning" if any(item.severity == "warning" for item in issues) else "pass"
        )
    )
    return ValidationReport(
        schema_version=validation.schema_version,
        status="fail" if severity == "error" else "pass",
        issues=issues,
        severity=severity,
        source_path=validation.source_path,
    )


def _with_retained_claim_repair_diagnostics(
    report: ValidationReport,
    artifacts: Dict[str, Any],
    evidence_packs: Dict[str, Any],
) -> ValidationReport:
    diagnostics = retained_claim_repair_issues(artifacts, evidence_packs)
    known = {
        (
            issue.rule_id,
            issue.affected_section,
            issue.entity_id,
            tuple(issue.evidence_ids),
        )
        for issue in report.issues
    }
    added = [
        issue
        for issue in diagnostics
        if (
            issue.rule_id,
            issue.affected_section,
            issue.entity_id,
            tuple(issue.evidence_ids),
        )
        not in known
    ]
    if not added:
        return report
    return replace(
        report,
        status="fail",
        severity="error",
        issues=[*report.issues, *added],
    )


def _failure_fingerprint(issue: ValidationIssue) -> FailureFingerprint:
    return FailureFingerprint(
        rule_id=str(issue.rule_id or "validation").strip(),
        affected_section=str(issue.affected_section or "").strip(),
        entity_id=str(issue.entity_id or "").strip(),
        evidence_ids=sorted(
            str(value).strip() for value in issue.evidence_ids if str(value).strip()
        ),
    )


def _retained_claim_severity_by_fingerprint(
    report: ValidationReport,
) -> Dict[str, str]:
    """Return the strongest promoted severity for each retained-claim finding."""

    severity_rank = {"info": 0, "warning": 1, "error": 2}
    severities: Dict[str, str] = {}
    for issue in report.issues:
        if not str(issue.rule_id or "").startswith("retained_claim."):
            continue
        severity = str(issue.severity or "").strip().lower()
        if severity not in severity_rank:
            continue
        fingerprint = _failure_fingerprint(issue).key
        existing = severities.get(fingerprint)
        if existing is None or severity_rank[severity] > severity_rank[existing]:
            severities[fingerprint] = severity
    return severities


def _repair_delta(before: ValidationReport, after: ValidationReport) -> RepairDelta:
    before_by_key = {_failure_fingerprint(item).key: item for item in before.issues}
    after_by_key = {_failure_fingerprint(item).key: item for item in after.issues}
    before_items = {
        key: _failure_fingerprint(item) for key, item in before_by_key.items()
    }
    after_items = {
        key: _failure_fingerprint(item) for key, item in after_by_key.items()
    }
    return RepairDelta(
        resolved=[
            before_items[key]
            for key in sorted(before_items.keys() - after_items.keys())
        ],
        persisting=[
            after_items[key] for key in sorted(before_items.keys() & after_items.keys())
        ],
        introduced=[
            after_items[key] for key in sorted(after_items.keys() - before_items.keys())
        ],
        severity_changes=[
            RepairSeverityChange(
                failure_fingerprint=key,
                before=before_by_key[key].severity,
                after=after_by_key[key].severity,
            )
            for key in sorted(before_items.keys() & after_items.keys())
            if before_by_key[key].severity != after_by_key[key].severity
        ],
    )


def _introduced_hard_failure_count(
    before: ValidationReport, after: ValidationReport
) -> int:
    before_keys = {
        _failure_fingerprint(issue).key
        for issue in before.issues
        if str(issue.severity or "").lower() == "error"
    }
    after_keys = {
        _failure_fingerprint(issue).key
        for issue in after.issues
        if str(issue.severity or "").lower() == "error"
    }
    return len(after_keys - before_keys)


def _candidate_validator_identity(runtime: ReportRuntimeState) -> str:
    """Stable identity for the deterministic and semantic promotion gates."""

    return ":".join(
        (
            "regeneration-candidate-v1",
            str(runtime.ctx.configuration_hash or ""),
            str(runtime.ctx.policy_hash or ""),
        )
    )


def _append_candidate_hash_repeat_issue(
    report: ValidationReport,
) -> ValidationReport:
    issue = ValidationIssue(
        message=(
            "[regeneration_candidate_hash_repeat] Candidate content repeated for "
            "the same promoted input and validator identity after rejection."
        ),
        severity="error",
        affected_section="regeneration_candidate",
        rule_id="regeneration_candidate_hash_repeat",
    )
    return replace(
        report,
        status="fail",
        severity="error",
        issues=[*report.issues, issue],
    )


def _plan_strategy_fingerprint(plan) -> str:
    fingerprints = [
        issue.failure_fingerprint
        or _failure_fingerprint(
            ValidationIssue(
                message=issue.message,
                severity=issue.severity,
                affected_section=issue.affected_section,
                rule_id=issue.rule_id,
                entity_id=issue.entity_id,
                evidence_ids=issue.evidence_ids,
            )
        ).key
        for target in plan.targets
        for issue in target.issues
    ]
    evidence_ids = [
        evidence_id
        for target in plan.targets
        for evidence_id in target.selected_evidence_ids
    ]
    strategy = "+".join(target.repair_strategy for target in plan.targets)
    return repair_strategy_fingerprint(fingerprints, strategy, evidence_ids)


def _attempt_strategy_fingerprint(plan, regeneration_response) -> str:
    """Fingerprint the strategy/evidence this attempt actually used.

    The generator records the repair action, strategy, and evidence actually
    selected for the attempt.  A failed attempt therefore can never be retried
    under a different nominal label with the same effective inputs.
    """

    strategy = str(getattr(regeneration_response, "repair_strategy", "") or "").strip()
    actual_evidence = list(
        getattr(regeneration_response, "selected_evidence_ids", []) or []
    )
    if not strategy and not actual_evidence:
        return _plan_strategy_fingerprint(plan)
    fingerprints = [
        issue.failure_fingerprint
        or _failure_fingerprint(
            ValidationIssue(
                message=issue.message,
                severity=issue.severity,
                affected_section=issue.affected_section,
                rule_id=issue.rule_id,
                entity_id=issue.entity_id,
                evidence_ids=issue.evidence_ids,
            )
        ).key
        for target in plan.targets
        for issue in target.issues
    ]
    return repair_strategy_fingerprint(fingerprints, strategy, actual_evidence)


_PAYLOAD_OVERRIDE_FIELDS = frozenset({"title", "publisher"})


def _bounded_payload_overrides(overrides: object) -> Dict[str, str]:
    """Keep only bounded report-identity corrections from a repair attempt."""

    if not isinstance(overrides, dict):
        return {}
    return {
        str(field_name): str(value)
        for field_name, value in sorted(overrides.items())
        if field_name in _PAYLOAD_OVERRIDE_FIELDS and str(value or "").strip()
    }


def _scope_validation_report(
    *,
    before: Dict[str, Any],
    after: Dict[str, Any],
    plan,
    verified_derived_roots: frozenset[str] = frozenset(),
) -> ValidationReport:
    allowed_paths = {
        path.strip()
        for target in plan.targets
        for path in target.allowed_paths
        if str(path).strip()
    }
    changed_paths = _artifact_diff_paths(before, after)
    violations = sorted(
        path
        for path in changed_paths
        if not _path_is_declared(path, allowed_paths)
        and not _is_allowed_derived_artifact_change(
            path=path,
            allowed_paths=allowed_paths,
            verified_derived_roots=verified_derived_roots,
        )
    )
    if not violations:
        return ValidationReport(
            schema_version="1.1", status="pass", issues=[], severity="pass"
        )
    return ValidationReport(
        schema_version="1.1",
        status="fail",
        severity="error",
        issues=[
            ValidationIssue(
                message=(
                    "[regeneration_scope_violation] Targeted repair changed an "
                    "undeclared artifact path"
                ),
                severity="error",
                affected_section=path,
                rule_id="regeneration_scope_violation",
            )
            for path in violations
        ],
    )


def _path_root(path: str) -> str:
    return re.split(r"[.\[]", str(path or ""), maxsplit=1)[0]


def _path_is_declared(path: str, allowed_paths: set[str]) -> bool:
    deterministic_family_roots = {
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    }
    return any(
        path == allowed
        or (
            allowed in deterministic_family_roots
            and (path.startswith(f"{allowed}.") or path.startswith(f"{allowed}["))
        )
        for allowed in allowed_paths
    )


def _is_allowed_derived_artifact_change(
    *,
    path: str,
    allowed_paths: set[str],
    verified_derived_roots: frozenset[str],
) -> bool:
    """Allow only deterministic projections of an explicitly scoped repair."""

    root = _path_root(path)
    allowed_roots = {_path_root(value) for value in allowed_paths}
    return root in verified_derived_roots and bool(
        _DERIVED_ARTIFACT_ROOT_DEPENDENCIES.get(root, set()) & allowed_roots
    )


def _verified_dependent_paths(
    *,
    before: Dict[str, Any],
    after: Dict[str, Any],
    plan,
    verified_derived_roots: frozenset[str],
) -> List[str]:
    allowed_paths = {
        path.strip()
        for target in plan.targets
        for path in target.allowed_paths
        if str(path).strip()
    }
    return sorted(
        path
        for path in _artifact_diff_paths(before, after)
        if _is_allowed_derived_artifact_change(
            path=path,
            allowed_paths=allowed_paths,
            verified_derived_roots=verified_derived_roots,
        )
    )


_SOFT_COPY_DIFF_PATHS = frozenset(
    {
        "summary.tldr",
        "summary.card_tldr_compact",
        "summary.executive_summary",
        "expert_comment",
        "linkedin_post",
    }
)


def _artifact_diff_paths(before: Any, after: Any, path: str = "") -> set[str]:
    """Return changed leaf paths, using stable item IDs when the arrays preserve them."""

    if before == after:
        return set()
    if isinstance(before, dict) and isinstance(after, dict):
        changed: set[str] = set()
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else str(key)
            if key not in before or key not in after:
                changed.add(child)
            else:
                changed.update(_artifact_diff_paths(before[key], after[key], child))
        return changed
    if isinstance(before, list) and isinstance(after, list):
        before_ids = _stable_list_ids(before)
        after_ids = _stable_list_ids(after)
        if before_ids is not None and after_ids is not None:
            if set(before_ids) == set(after_ids) and before_ids != after_ids:
                return {path or "$"}
            before_by_id = dict(zip(before_ids, before))
            after_by_id = dict(zip(after_ids, after))
            changed = {
                changed_path
                for identity in before_ids
                if identity in after_by_id
                for changed_path in _artifact_diff_paths(
                    before_by_id[identity],
                    after_by_id[identity],
                    f"{path}[item={identity}]",
                )
            }
            changed.update(
                f"{path}[item={identity}]"
                for identity in set(before_ids) ^ set(after_ids)
            )
            return changed
        changed = set()
        for index in range(max(len(before), len(after))):
            child = f"{path}[{index}]"
            if index >= len(before) or index >= len(after):
                changed.add(child)
            else:
                changed.update(_artifact_diff_paths(before[index], after[index], child))
        return changed
    if (
        path in _SOFT_COPY_DIFF_PATHS
        and isinstance(before, str)
        and isinstance(after, str)
    ):
        return _soft_copy_changed_claim_paths(path, before, after)
    return {path} if path else {"$"}


def _stable_list_ids(values: list[Any]) -> list[str] | None:
    identities: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            return None
        identity = next(
            (
                str(value.get(key) or "").strip()
                for key in ("id", "insight_id", "key_figure_id", "claim_id")
                if str(value.get(key) or "").strip()
            ),
            "",
        )
        if not identity:
            return None
        identities.append(identity)
    return identities if len(set(identities)) == len(identities) else None


def _soft_copy_changed_claim_paths(path: str, before: str, after: str) -> set[str]:
    before_sentences = soft_copy_material_sentences(before)
    after_sentences = soft_copy_material_sentences(after)
    matcher = SequenceMatcher(a=before_sentences, b=after_sentences, autojunk=False)
    changed: set[str] = set()
    for operation, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if operation == "equal":
            continue
        changed.update(
            f"{path}[claim_index={index}]" for index in range(old_start, old_end)
        )
        changed.update(
            f"{path}[claim_index={index}]" for index in range(new_start, new_end)
        )
    return changed or {path}


def _validation_issue_keys(report: ValidationReport) -> list[str]:
    return sorted(
        {
            ":".join(
                value
                for value in (
                    str(item.rule_id or "validation").strip(),
                    str(item.affected_section or "").strip(),
                )
                if value
            )
            for item in report.issues
        }
    )


def _candidate_audit(
    *,
    runtime: ReportRuntimeState,
    attempt_index: int,
    transformation_scope: List[str],
    current_artifacts: Dict[str, Any],
    candidate_artifacts: Dict[str, Any],
    current_artifacts_path: str,
    candidate_artifacts_path: str,
    candidate_result: CandidateIntegrityResult,
    validation_report: ValidationReport | None = None,
    promotion_outcome: str = "candidate",
    plan=None,
    repair_delta: RepairDelta | None = None,
    strategy_fingerprint: str = "",
    latency_ms: int | None = None,
    regeneration_response=None,
) -> RegenerationCandidateAudit:
    report = validation_report or ValidationReport(
        schema_version="1.1",
        status="fail" if not candidate_result.passed else "pass",
        issues=list(candidate_result.issues),
        severity="error" if not candidate_result.passed else "pass",
    )
    actual_action = (
        str(getattr(regeneration_response, "repair_action", "") or "").strip()
        if regeneration_response is not None
        else ""
    )
    actual_strategy = (
        str(getattr(regeneration_response, "repair_strategy", "") or "").strip()
        if regeneration_response is not None
        else ""
    )
    actual_evidence_ids = (
        list(getattr(regeneration_response, "selected_evidence_ids", []) or [])
        if regeneration_response is not None
        else []
    )
    return RegenerationCandidateAudit(
        attempt_index=attempt_index,
        transformation_scope=list(transformation_scope),
        before_sha256=sha256_json(current_artifacts),
        after_sha256=sha256_json(candidate_artifacts),
        unchanged_family_sha256=_unchanged_claim_family_hashes(
            current_artifacts, candidate_artifacts
        ),
        current_artifacts_path=current_artifacts_path,
        candidate_artifacts_path=candidate_artifacts_path,
        validation_status=report.status,
        promotion_outcome=promotion_outcome,
        validation_issues=_validation_issue_keys(report),
        evidence_lineage=list(candidate_result.evidence_lineage),
        failure_fingerprints=[_failure_fingerprint(item).key for item in report.issues],
        repair_action=(
            actual_action
            or (
                "+".join(target.repair_action for target in plan.targets)
                if plan
                else ""
            )
        ),
        repair_strategy=(
            actual_strategy
            or (
                "+".join(target.repair_strategy for target in plan.targets)
                if plan
                else ""
            )
        ),
        allowed_paths=(
            sorted({path for target in plan.targets for path in target.allowed_paths})
            if plan
            else []
        ),
        verified_dependent_paths=(
            _verified_dependent_paths(
                before=current_artifacts,
                after=candidate_artifacts,
                plan=plan,
                verified_derived_roots=candidate_result.verified_derived_roots,
            )
            if plan
            else []
        ),
        selected_evidence_ids=(
            sorted(set(actual_evidence_ids))
            if actual_evidence_ids
            else (
                sorted(
                    {
                        value
                        for target in plan.targets
                        for value in target.selected_evidence_ids
                    }
                )
                if plan
                else []
            )
        ),
        quarantined_evidence_ids=(
            sorted(
                {
                    value
                    for target in plan.targets
                    for value in target.quarantined_evidence_ids
                }
            )
            if plan
            else []
        ),
        repair_delta=repair_delta or RepairDelta(),
        repair_decisions=(
            list(getattr(regeneration_response, "repair_decisions", []) or [])
            if regeneration_response is not None
            else []
        ),
        report_id=str(runtime.ctx.report_id or runtime.file.file_id),
        validation_run_id=str(runtime.ctx.validation_run_id or ""),
        cohort_id=str(runtime.ctx.cohort_id or ""),
        workflow_run_id=str(runtime.ctx.run_id or ""),
        configuration_hash=str(runtime.ctx.configuration_hash or ""),
        policy_hash=str(runtime.ctx.policy_hash or ""),
        producer_build_identity=str(runtime.ctx.producer_commit_sha or "workspace"),
        strategy_fingerprint=strategy_fingerprint,
        latency_ms=latency_ms,
    )


def _unchanged_claim_family_hashes(
    current_artifacts: Dict[str, Any], candidate_artifacts: Dict[str, Any]
) -> Dict[str, str]:
    """Retain byte-equivalence evidence for non-regenerated claim families."""

    return {
        family: before_hash
        for family in (
            "summary",
            "insights_candidates",
            "insights_final",
            "quotes_final",
        )
        if family in current_artifacts
        and family in candidate_artifacts
        and (before_hash := sha256_json(current_artifacts[family]))
        == sha256_json(candidate_artifacts[family])
    }


def _store_regeneration_candidate_audit(
    *,
    runtime: ReportRuntimeState,
    dependencies: ReportAnalysisDependencies,
    audit: RegenerationCandidateAudit,
    ctx,
) -> str:
    return dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=f"regeneration_candidate_audit_{audit.attempt_index}",
            payload=asdict(audit),
            report_slug=runtime.report_name,
        ),
        ctx,
    ).output_path


def _promote_regeneration_candidate(
    *,
    runtime: ReportRuntimeState,
    dependencies: ReportAnalysisDependencies,
    candidate_artifacts: Dict[str, Any],
    ctx,
) -> str:
    """Atomically replace the current artifacts only after all gates pass.

    ``analysis_store_pack`` delegates to the canonical atomic file service;
    the prior current file remains readable until its final replacement wins.
    """

    return dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name="artifacts",
            payload=candidate_artifacts,
            report_slug=runtime.report_name,
        ),
        ctx,
    ).output_path


def _validate_regeneration_baseline(
    *,
    runtime: ReportRuntimeState,
    mode_ctx,
    base_payload,
    current_artifacts: Dict[str, Any],
    evidence_packs: Dict[str, Any],
    vector_store_id: Optional[str],
    dependencies: ReportAnalysisDependencies,
    source_text: str = "",
    validation_openai_client=None,
) -> ValidationReport:
    """Run the current production validation stack on unchanged artifacts."""

    baseline_ctx = child_context(
        mode_ctx, task_id=f"{mode_ctx.task_id}:validation_regen_baseline"
    )
    baseline_payload = merge_artifacts_into_payload(
        deepcopy(base_payload), current_artifacts
    )
    _ensure_report_payload_complete(
        baseline_payload,
        artifacts=current_artifacts,
        ctx=baseline_ctx,
        file_id=runtime.file.file_id,
        stage="validation_regen_baseline",
    )
    baseline_integrity = validate_regeneration_candidate(
        current_artifacts=current_artifacts,
        candidate_artifacts=current_artifacts,
        evidence_packs=evidence_packs,
        ctx=baseline_ctx,
    )
    validation = _run_validation_with_fallback(
        runtime=runtime,
        mode_ctx=baseline_ctx,
        dependencies=dependencies,
        validation_req=ValidationRequest(
            schema_version="1.0",
            report_id=ReportId(runtime.file.file_id),
            report=baseline_payload,
            artifacts=current_artifacts,
            evidence_packs=evidence_packs,
            vector_store_id=vector_store_id,
            source_id=str(runtime.ctx.source_identity_id or "").strip(),
            deterministic_grounding_passed=baseline_integrity.passed,
            publisher_name=runtime.publisher_name,
            report_name=runtime.source_report_name or runtime.report_title,
            source_url=runtime.source_url,
            source_text=source_text,
        ),
        pack_name="validation_regen_baseline",
        openai_client=validation_openai_client,
    )
    validation = _candidate_validation_report(validation, baseline_integrity)
    editorial_validation, _ = _evaluate_and_store_public_editorial_quality(
        runtime=runtime,
        dependencies=dependencies,
        artifacts=current_artifacts,
        pack_name="public_editorial_quality_regen_baseline",
        ctx=baseline_ctx,
    )
    validation = _merge_public_editorial_quality(validation, editorial_validation)
    return _with_retained_claim_repair_diagnostics(
        validation,
        current_artifacts,
        evidence_packs,
    )


def _run_validation_regeneration_loop(
    *,
    runtime: ReportRuntimeState,
    mode_ctx,
    base_payload,
    current_artifacts: Dict[str, Any],
    current_validation_report: ValidationReport,
    evidence_packs: Dict[str, Any],
    source_status: Dict[str, Any],
    category_labels: List[str],
    vector_store_id: Optional[str],
    dependencies: ReportAnalysisDependencies,
    source_text: str = "",
    validation_openai_client=None,
    regeneration_openai_client=None,
) -> tuple[
    Dict[str, Any],
    ValidationReport,
    List[RegenerationAttemptResult],
    RegenerationLoopState,
    Dict[str, str],
    Dict[str, str],
]:
    max_attempts = max(1, int(runtime.settings.validation_regeneration_max_attempts))
    attempts: List[RegenerationAttemptResult] = []
    evidence_paths: Dict[str, str] = {}
    broad_retry_used = False
    rejected_strategy_keys: set[str] = set()
    rejected_candidate_hashes: set[str] = set()
    repair_memory: List[RepairDelta] = []
    promoted_payload_overrides: Dict[str, str] = {}
    current_artifacts_path = dependencies.analysis_pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name="artifacts",
            report_slug=runtime.report_name,
        ),
        mode_ctx,
    ).output_path
    promoted_artifacts = deepcopy(current_artifacts)
    promoted_validation_report = current_validation_report
    working_artifacts = deepcopy(current_artifacts)
    logger.info(
        log_event(
            mode_ctx,
            role="orchestrator",
            event="validation_regen_loop_start",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "max_attempts": max_attempts,
                "initial_status": current_validation_report.status,
            },
        )
    )
    final_status = current_validation_report.status
    for attempt_index in range(1, max_attempts + 1):
        if current_validation_report.status == "pass":
            final_status = "pass"
            break
        current_validation_report = _with_retained_claim_repair_diagnostics(
            current_validation_report,
            promoted_artifacts,
            evidence_packs,
        )
        plan = _build_regeneration_plan(
            issues=current_validation_report.issues,
            artifacts=working_artifacts,
            broad_retry_available=not broad_retry_used,
            rejected_strategy_keys=rejected_strategy_keys,
        )
        public_issues = [
            issue
            for issue in current_validation_report.issues
            if str(issue.rule_id).startswith("public_editorial_quality.")
        ]
        if public_issues:
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="public_editorial_repair_requested",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "rule_ids": sorted({issue.rule_id for issue in public_issues}),
                        "target_sections": [
                            target.target_section for target in plan.targets
                        ],
                    },
                )
            )
        abstained_public_issues = [
            issue for issue in public_issues if not str(issue.repair_target).strip()
        ]
        if abstained_public_issues:
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="public_editorial_repair_abstained",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "rule_ids": sorted(
                            {issue.rule_id for issue in abstained_public_issues}
                        ),
                        "issue_count": len(abstained_public_issues),
                    },
                )
            )
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_regen_plan_built",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "targets": [target.target_section for target in plan.targets],
                    "target_details": _regeneration_target_details(plan.targets),
                    "unmappable_issue_count": len(plan.unmappable_issues),
                },
            )
        )
        if plan.mode == "skip":
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_regen_skip_no_targets",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "issue_count": len(current_validation_report.issues),
                    },
                )
            )
            final_status = "skipped"
            break
        if plan.mode == "broad":
            broad_retry_used = True
            logger.info(
                log_event(
                    mode_ctx,
                    role="orchestrator",
                    event="validation_regen_unmappable_broad_retry",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "issue_count": len(plan.unmappable_issues),
                    },
                )
            )
        attempt_ctx = replace(
            child_context(
                mode_ctx, task_id=f"{mode_ctx.task_id}:regen:{attempt_index}"
            ),
            repair_attempt=attempt_index,
        )
        logger.info(
            log_event(
                attempt_ctx,
                role="orchestrator",
                event="validation_regen_attempt_start",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "targets": [target.target_section for target in plan.targets],
                    "target_details": _regeneration_target_details(plan.targets),
                    "validation_before_status": current_validation_report.status,
                },
            )
        )
        validation_before_status = current_validation_report.status
        artifacts_before = deepcopy(working_artifacts)
        candidate_parent_path = current_artifacts_path
        attempt_started = perf_counter()
        regeneration_kwargs = {}
        if regeneration_openai_client is not None and _accepts_keyword(
            dependencies.regenerate_artifacts, "openai_client"
        ):
            regeneration_kwargs["openai_client"] = regeneration_openai_client
        regeneration_response = dependencies.regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id=ReportId(runtime.file.file_id),
                report_name=runtime.report_name,
                attempt_index=attempt_index,
                plan=plan,
                current_artifacts=working_artifacts,
                doc_map=evidence_packs.get("doc_map", {}),
                evidence_packs=evidence_packs,
                settings=runtime.settings,
                ctx=attempt_ctx,
                source_status=source_status,
                categories=category_labels,
                vector_store_id=vector_store_id,
                md5=runtime.md5,
                publisher_name=runtime.publisher_name,
                source_url=runtime.source_url,
                repair_memory=list(repair_memory),
            ),
            **regeneration_kwargs,
        )
        candidate_artifacts = regeneration_response.updated_artifacts
        artifact_diff = _artifact_diff_summary(artifacts_before, candidate_artifacts)
        candidate_artifacts_path = _candidate_artifacts_path(regeneration_response)
        candidate_enforced = bool(candidate_artifacts_path)
        candidate_result = (
            validate_regeneration_candidate(
                current_artifacts=working_artifacts,
                candidate_artifacts=candidate_artifacts,
                evidence_packs=evidence_packs,
                ctx=attempt_ctx,
                planned_prompt_namespaces=tuple(
                    namespace
                    for target in plan.targets
                    for namespace in target.prompt_namespaces
                ),
                actual_prompt_namespaces=tuple(regeneration_response.prompt_namespaces),
                baseline_retained_claim_severities=(
                    _retained_claim_severity_by_fingerprint(current_validation_report)
                ),
                removed_insight_ids=tuple(
                    failed_insight_id(issue.entity_id, issue.affected_section)
                    for target in plan.targets
                    if target.target_section == "insights_bundle"
                    and target.repair_action == "REMOVE_CLAIM"
                    for issue in target.issues
                ),
            )
            if candidate_enforced
            else CandidateIntegrityResult(issues=[], evidence_lineage=[])
        )
        candidate_audit_path = ""
        if candidate_enforced:
            candidate_audit_path = _store_regeneration_candidate_audit(
                runtime=runtime,
                dependencies=dependencies,
                audit=_candidate_audit(
                    runtime=runtime,
                    attempt_index=attempt_index,
                    transformation_scope=regeneration_response.regenerated_sections,
                    current_artifacts=working_artifacts,
                    candidate_artifacts=candidate_artifacts,
                    current_artifacts_path=candidate_parent_path,
                    candidate_artifacts_path=candidate_artifacts_path,
                    candidate_result=candidate_result,
                    regeneration_response=regeneration_response,
                    plan=plan,
                ),
                ctx=attempt_ctx,
            )
            evidence_paths[f"artifacts_regen_candidate_{attempt_index}"] = (
                candidate_artifacts_path
            )
            evidence_paths[f"regeneration_candidate_audit_{attempt_index}"] = (
                candidate_audit_path
            )
        if regeneration_response.artifacts_snapshot_path:
            evidence_paths[f"artifacts_regen_attempt_{attempt_index}"] = (
                regeneration_response.artifacts_snapshot_path
            )
        regenerated_payload = merge_artifacts_into_payload(
            deepcopy(base_payload), candidate_artifacts
        )
        payload_overrides = _bounded_payload_overrides(
            getattr(regeneration_response, "payload_overrides", {})
        )
        if payload_overrides:
            # Deterministic identity corrections are part of the candidate:
            # they are validated with it and promoted (or dropped) with it.
            for field_name, value in payload_overrides.items():
                setattr(regenerated_payload, field_name, str(value))
        _ensure_report_payload_complete(
            regenerated_payload,
            artifacts=candidate_artifacts,
            ctx=attempt_ctx,
            file_id=runtime.file.file_id,
            stage=f"regeneration_attempt_{attempt_index}",
        )
        validation_pack_name = (
            f"validation_regen_candidate_{attempt_index}"
            if candidate_enforced
            else "validation"
        )
        candidate_validation_report = _run_validation_with_fallback(
            runtime=runtime,
            mode_ctx=attempt_ctx,
            dependencies=dependencies,
            validation_req=ValidationRequest(
                schema_version="1.0",
                report_id=ReportId(runtime.file.file_id),
                report=regenerated_payload,
                artifacts=candidate_artifacts,
                evidence_packs=evidence_packs,
                vector_store_id=vector_store_id,
                source_id=str(runtime.ctx.source_identity_id or "").strip(),
                deterministic_grounding_passed=candidate_result.passed,
                publisher_name=runtime.publisher_name,
                report_name=runtime.source_report_name or runtime.report_title,
                source_url=runtime.source_url,
                source_text=source_text,
            ),
            pack_name=validation_pack_name,
            openai_client=validation_openai_client,
        )
        candidate_validation_report = _candidate_validation_report(
            candidate_validation_report, candidate_result
        )
        candidate_validation_report = _merge_public_editorial_quality(
            candidate_validation_report,
            _scope_validation_report(
                before=artifacts_before,
                after=candidate_artifacts,
                plan=plan,
                verified_derived_roots=candidate_result.verified_derived_roots,
            ),
        )
        editorial_validation, editorial_path = (
            _evaluate_and_store_public_editorial_quality(
                runtime=runtime,
                dependencies=dependencies,
                artifacts=candidate_artifacts,
                pack_name=f"public_editorial_quality_regen_attempt_{attempt_index}",
                ctx=attempt_ctx,
            )
        )
        candidate_validation_report = _merge_public_editorial_quality(
            candidate_validation_report, editorial_validation
        )
        candidate_input_sha256 = sha256_json(artifacts_before)
        candidate_sha256 = sha256_json(candidate_artifacts)
        validator_identity = _candidate_validator_identity(runtime)
        rejection_fingerprint = candidate_rejection_fingerprint(
            candidate_sha256=candidate_sha256,
            input_sha256=candidate_input_sha256,
            validator_identity=validator_identity,
        )
        repeated_candidate_hash = rejection_fingerprint in rejected_candidate_hashes
        if repeated_candidate_hash:
            candidate_validation_report = _append_candidate_hash_repeat_issue(
                candidate_validation_report
            )
        candidate_validation_path = _store_validation_snapshot(
            runtime=runtime,
            dependencies=dependencies,
            report=candidate_validation_report,
            pack_name=validation_pack_name,
            ctx=attempt_ctx,
        )
        candidate_validation_report = replace(
            candidate_validation_report, source_path=candidate_validation_path
        )
        repair_delta = _repair_delta(
            current_validation_report, candidate_validation_report
        )
        repair_delta = replace(
            repair_delta,
            introduced_hard_failure_count=_introduced_hard_failure_count(
                current_validation_report, candidate_validation_report
            ),
        )
        strategy_fingerprint = _attempt_strategy_fingerprint(
            plan, regeneration_response
        )
        scope_failed = any(
            issue.rule_id == "regeneration_scope_violation"
            for issue in candidate_validation_report.issues
        )
        lineage_failure_rules = {
            "grounding",
            "soft_copy_claim_provenance",
            "regeneration_source_page",
            "regeneration_claim_support",
        }
        evidence_lineage_failed = bool(
            any(item.validation_issues for item in candidate_result.evidence_lineage)
            or any(
                item.rule_id in lineage_failure_rules
                for item in candidate_result.issues
            )
        )
        repair_delta = replace(
            repair_delta,
            mutation_scope_result="fail" if scope_failed else "pass",
            evidence_lineage_result="fail" if evidence_lineage_failed else "pass",
            repair_action=str(
                getattr(regeneration_response, "repair_action", "") or ""
            ),
            repair_strategy=str(
                getattr(regeneration_response, "repair_strategy", "") or ""
            ),
            evidence_ids_used=list(
                getattr(regeneration_response, "selected_evidence_ids", []) or []
            ),
            strategy_fingerprint=strategy_fingerprint,
            candidate_sha256=candidate_sha256,
            input_sha256=candidate_input_sha256,
            validator_identity=validator_identity,
        )
        # The planner reasons over planned strategy/evidence keys, while the
        # audit records what the attempt actually used. Both are retained so a
        # rejected candidate rules out its planned combination for every later
        # attempt regardless of which evidence the generator finally selected.
        planned_strategy_keys = {
            repair_strategy_fingerprint(
                [issue.failure_fingerprint for issue in target.issues],
                target.repair_strategy,
                target.selected_evidence_ids,
            )
            for target in plan.targets
        }
        evidence_paths[f"public_editorial_quality_regen_attempt_{attempt_index}"] = (
            editorial_path
        )
        validation_snapshot_path = _store_validation_snapshot(
            runtime=runtime,
            dependencies=dependencies,
            report=candidate_validation_report,
            pack_name=f"validation_regen_attempt_{attempt_index}",
            ctx=attempt_ctx,
        )
        evidence_paths[f"validation_regen_attempt_{attempt_index}"] = (
            validation_snapshot_path
        )
        promotion_outcome = "not_attempted"
        repeated_rejected_strategy = False
        artifacts_path = regeneration_response.artifacts_path
        if candidate_enforced:
            if candidate_validation_report.status == "pass":
                try:
                    artifacts_path = _promote_regeneration_candidate(
                        runtime=runtime,
                        dependencies=dependencies,
                        candidate_artifacts=candidate_artifacts,
                        ctx=attempt_ctx,
                    )
                except Exception:
                    _store_regeneration_candidate_audit(
                        runtime=runtime,
                        dependencies=dependencies,
                        audit=_candidate_audit(
                            runtime=runtime,
                            attempt_index=attempt_index,
                            transformation_scope=(
                                regeneration_response.regenerated_sections
                            ),
                            current_artifacts=working_artifacts,
                            candidate_artifacts=candidate_artifacts,
                            current_artifacts_path=candidate_parent_path,
                            candidate_artifacts_path=candidate_artifacts_path,
                            candidate_result=candidate_result,
                            validation_report=candidate_validation_report,
                            promotion_outcome="rolled_back",
                            plan=plan,
                            repair_delta=repair_delta,
                            strategy_fingerprint=strategy_fingerprint,
                            regeneration_response=regeneration_response,
                            latency_ms=max(
                                0, int((perf_counter() - attempt_started) * 1000)
                            ),
                        ),
                        ctx=attempt_ctx,
                    )
                    raise
                canonical_validation_path = _store_validation_snapshot(
                    runtime=runtime,
                    dependencies=dependencies,
                    report=candidate_validation_report,
                    pack_name="validation",
                    ctx=attempt_ctx,
                )
                promotion_state = (
                    candidate_artifacts,
                    replace(
                        candidate_validation_report,
                        source_path=canonical_validation_path,
                    ),
                    artifacts_path,
                )
                (
                    promoted_artifacts,
                    promoted_validation_report,
                    current_artifacts_path,
                ) = promotion_state
                working_artifacts = promoted_artifacts
                current_validation_report = promoted_validation_report
                promotion_outcome = "promoted"
                evidence_paths["artifacts"] = artifacts_path
                evidence_paths["validation"] = canonical_validation_path
                promoted_payload_overrides = payload_overrides
            else:
                promotion_outcome = "rolled_back"
                artifacts_path = current_artifacts_path
                # A rejected candidate has never become canonical.  Retrying
                # from it would turn rollback into an untracked mutation and
                # compound the original failure on every later attempt.
                working_artifacts = deepcopy(promoted_artifacts)
                current_validation_report = promoted_validation_report
                # The attempt fingerprint describes the actual strategy and
                # evidence used.  Re-detecting it here means the attempt
                # repeated an already-rejected combination under another
                # nominal label; stop instead of burning further attempts.
                repeated_rejected_strategy = strategy_fingerprint in (
                    rejected_strategy_keys
                )
                rejected_strategy_keys.add(strategy_fingerprint)
                rejected_strategy_keys.update(planned_strategy_keys)
                repair_memory.append(repair_delta)
                rejected_candidate_hashes.add(rejection_fingerprint)
                # Deterministic identity corrections are candidate-scoped: a
                # rolled-back candidate leaves the promoted identity untouched.
                promoted_payload_overrides = {}
            candidate_audit_path = _store_regeneration_candidate_audit(
                runtime=runtime,
                dependencies=dependencies,
                audit=_candidate_audit(
                    runtime=runtime,
                    attempt_index=attempt_index,
                    transformation_scope=regeneration_response.regenerated_sections,
                    current_artifacts=artifacts_before,
                    candidate_artifacts=candidate_artifacts,
                    current_artifacts_path=candidate_parent_path,
                    candidate_artifacts_path=candidate_artifacts_path,
                    candidate_result=candidate_result,
                    validation_report=candidate_validation_report,
                    promotion_outcome=promotion_outcome,
                    plan=plan,
                    repair_delta=repair_delta,
                    strategy_fingerprint=strategy_fingerprint,
                    regeneration_response=regeneration_response,
                    latency_ms=max(0, int((perf_counter() - attempt_started) * 1000)),
                ),
                ctx=attempt_ctx,
            )
        else:
            # Legacy dependency doubles predate candidate promotion. Production
            # regeneration always supplies candidate_artifacts_path above.
            promoted_artifacts = candidate_artifacts
            working_artifacts = candidate_artifacts
            promoted_validation_report = candidate_validation_report
            current_validation_report = promoted_validation_report
            if artifacts_path:
                current_artifacts_path = artifacts_path
                evidence_paths["artifacts"] = artifacts_path
            if current_validation_report.source_path:
                evidence_paths["validation"] = current_validation_report.source_path
        attempt_result = RegenerationAttemptResult(
            attempt_index=attempt_index,
            plan_mode=plan.mode,
            regenerated_sections=regeneration_response.regenerated_sections,
            validation_before_status=validation_before_status,
            validation_after_status=current_validation_report.status,
            artifacts_path=artifacts_path,
            artifacts_snapshot_path=regeneration_response.artifacts_snapshot_path,
            validation_path=current_validation_report.source_path,
            validation_snapshot_path=validation_snapshot_path,
            candidate_artifacts_path=candidate_artifacts_path,
            candidate_audit_path=candidate_audit_path,
            promotion_outcome=promotion_outcome,
            failure_fingerprints=[
                _failure_fingerprint(issue).key
                for issue in current_validation_report.issues
            ],
            repair_delta=repair_delta,
            strategy_fingerprint=strategy_fingerprint,
            latency_ms=max(0, int((perf_counter() - attempt_started) * 1000)),
        )
        attempts.append(attempt_result)
        if repeated_rejected_strategy or repeated_candidate_hash:
            logger.info(
                log_event(
                    attempt_ctx,
                    role="orchestrator",
                    event=(
                        "validation_regen_rejected_candidate_hash_repeated"
                        if repeated_candidate_hash
                        else "validation_regen_equivalent_strategy_rejected"
                    ),
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "strategy_fingerprint": strategy_fingerprint,
                        "candidate_sha256": candidate_sha256,
                    },
                )
            )
            break
        logger.info(
            log_event(
                attempt_ctx,
                role="orchestrator",
                event="validation_regen_attempt_complete",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_index": attempt_index,
                    "mode": plan.mode,
                    "regenerated_sections": regeneration_response.regenerated_sections,
                    "prompt_namespaces": regeneration_response.prompt_namespaces,
                    "artifacts_path": artifacts_path,
                    "candidate_artifacts_path": candidate_artifacts_path,
                    "candidate_audit_path": candidate_audit_path,
                    "promotion_outcome": promotion_outcome,
                    "artifacts_snapshot_path": (
                        regeneration_response.artifacts_snapshot_path
                    ),
                    "artifact_diff": artifact_diff,
                    "validation_after_status": current_validation_report.status,
                },
            )
        )
        if public_issues:
            logger.info(
                log_event(
                    attempt_ctx,
                    role="orchestrator",
                    event="public_editorial_repair_completed",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "regenerated_sections": (
                            regeneration_response.regenerated_sections
                        ),
                    },
                )
            )
        if editorial_validation is not None:
            logger.info(
                log_event(
                    attempt_ctx,
                    role="orchestrator",
                    event="public_editorial_repair_revalidated",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                        "status": current_validation_report.status,
                        "quality_report_path": editorial_path,
                    },
                )
            )
        if current_validation_report.status == "pass":
            logger.info(
                log_event(
                    attempt_ctx,
                    role="orchestrator",
                    event="validation_regen_pass",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "attempt_index": attempt_index,
                    },
                )
            )
            final_status = "pass"
            break
        final_status = current_validation_report.status

    max_reached = (
        current_validation_report.status != "pass" and len(attempts) >= max_attempts
    )

    if max_reached:
        logger.info(
            log_event(
                mode_ctx,
                role="orchestrator",
                event="validation_regen_max_attempts_reached",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "attempt_count": len(attempts),
                    "max_attempts": max_attempts,
                    "remaining_status": current_validation_report.status,
                    "unresolved_sections": [
                        issue.affected_section
                        for issue in current_validation_report.issues
                    ],
                },
            )
        )
        final_status = "fail"
    loop_state = RegenerationLoopState(
        attempt_count=len(attempts),
        max_attempts=max_attempts,
        final_status=final_status,
        max_reached=max_reached,
    )
    return (
        promoted_artifacts,
        promoted_validation_report,
        attempts,
        loop_state,
        evidence_paths,
        promoted_payload_overrides,
    )


def _regeneration_target_details(targets) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for target in targets:
        rule_ids = sorted(
            {
                str(issue.rule_id or "").strip()
                for issue in target.issues
                if str(issue.rule_id or "").strip()
            }
        )
        details.append(
            {
                "target_section": target.target_section,
                "regenerate_steps": list(target.regenerate_steps),
                "prompt_namespaces": list(target.prompt_namespaces),
                "rule_ids": rule_ids,
            }
        )
    return details


def _artifact_diff_summary(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> Dict[str, List[str]]:
    before_keys = set(before.keys()) if isinstance(before, dict) else set()
    after_keys = set(after.keys()) if isinstance(after, dict) else set()
    common = before_keys & after_keys
    return {
        "added_keys": sorted(after_keys - before_keys),
        "removed_keys": sorted(before_keys - after_keys),
        "changed_keys": sorted(
            key for key in common if before.get(key) != after.get(key)
        ),
    }


def _store_validation_snapshot(
    *,
    runtime: ReportRuntimeState,
    dependencies: ReportAnalysisDependencies,
    report: ValidationReport,
    pack_name: str,
    ctx,
) -> str:
    output_path = dependencies.analysis_pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=pack_name,
            report_slug=runtime.report_name,
        ),
        ctx,
    ).output_path
    payload = report.to_dict()
    payload["source_path"] = output_path
    dependencies.analysis_store_pack(
        AnalysisStorePackRequest(
            schema_version="1.0",
            output_dir=runtime.settings.output_dir,
            report_id=ReportId(runtime.file.file_id),
            pack_name=pack_name,
            payload=payload,
            report_slug=runtime.report_name,
        ),
        ctx,
    )
    return output_path
