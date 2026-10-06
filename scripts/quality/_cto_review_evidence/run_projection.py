"""Project retained producer artifacts into the canonical CTO evidence bundle."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Literal, TypeGuard, cast

from src.contracts.cto_evidence import (
    SCHEMA_VERSION,
    CTOEvidenceAttempt,
    CTOEvidenceBundle,
    CTOEvidenceComparison,
    CTOEvidenceCriterion,
    CTOEvidenceCriterionCounts,
    CTOEvidenceExecutiveSummary,
    CTOEvidenceExternalAction,
    CTOEvidenceHistoricalState,
    CTOEvidenceMetric,
    CTOEvidenceOutcomeCount,
    CTOEvidenceQualityDimension,
    CTOEvidenceReuseDecision,
    CTOEvidenceRun,
    CTOEvidenceRunEvidence,
    CTOEvidenceSourceReference,
    CTOEvidenceSubject,
    cto_evidence_bundle_payload,
    derive_required_criteria_disposition,
    parse_cto_evidence_run,
)

FORMAT_GENERIC = "marketlense/generic-metrics/1.0"
FORMAT_FROZEN_COHORT = "marketlense/frozen-cohort-result/1.0"
FORMAT_ARTIFACT_DAG = "marketlense/artifact-dag-benchmark/1.0"
FORMAT_PROVIDER_PROFILE = "marketlense/provider-latency-profile/1.0"
FORMAT_PROVIDER_CRITICAL_PATH = "marketlense/provider-critical-path-profile/1.0"
FORMAT_CONCURRENCY = "marketlense/concurrency-proof/1.0"
FORMAT_REUSE = "marketlense/validation-reuse-benchmark/1.0"
FORMAT_FILE_SEARCH = "marketlense/file-search-reduction/1.0"
FORMAT_ACQUISITION = "marketlense/acquisition-projection/1.0"
FORMAT_CROP_QA = "marketlense/crop-qa-sidecar/1.0"
FORMAT_HUMAN_REVIEW = "marketlense/editorial-review/1.0"
FORMAT_WORDPRESS = "marketlense/wordpress-publication-evidence/1.0"
_NUMERIC_FORMAT_EVIDENCE_CLASSES = {
    FORMAT_ARTIFACT_DAG: frozenset(
        {"performance", "provider_timing", "resource_usage", "quality", "side_effects"}
    ),
    FORMAT_PROVIDER_PROFILE: frozenset(
        {"performance", "provider_timing", "resource_usage"}
    ),
    FORMAT_PROVIDER_CRITICAL_PATH: frozenset(
        {"performance", "provider_timing", "resource_usage", "quality"}
    ),
    FORMAT_CONCURRENCY: frozenset(
        {"performance", "provider_timing", "resource_usage", "concurrency", "quality"}
    ),
    FORMAT_REUSE: frozenset({"performance", "resource_usage", "quality"}),
    FORMAT_FILE_SEARCH: frozenset(
        {"performance", "resource_usage", "quality", "side_effects"}
    ),
    FORMAT_ACQUISITION: frozenset({"performance", "resource_usage"}),
}

_METRIC_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.:-]{0,127}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_DYNAMIC_SECTIONS = {
    "attempts",
    "calls",
    "candidates",
    "failure_pareto",
    "members",
    "remaining_failures",
    "report_comparison",
    "reports",
    "route_metrics",
    "rows",
    "slowest_provider_calls",
    "source_manifest",
    "workflow_attempt_count_by_report",
}
_IDENTITY_FIELDS = {
    "batch",
    "candidate_id",
    "cohort_id",
    "path",
    "producer_commit",
    "publisher",
    "publisher_id",
    "report_id",
    "report_name",
    "report_number",
    "report_title",
    "run_id",
    "run_root",
    "source_identity_id",
    "tested_commit",
    "url",
    "workflow_id",
}
_AttemptKind = Literal[
    "initial_execution",
    "deterministic_recovery",
    "structured_output_recovery",
    "evidence_claim_reuse",
    "semantic_repair",
    "targeted_regeneration",
    "workflow_retry",
    "operator_retry",
    "manual_intervention",
    "abstention",
    "terminal_failure",
]
_AttemptOutcome = Literal["success", "failed", "abstained", "not_evaluated"]


@dataclass
class _SourceProjection:
    metrics: list[CTOEvidenceMetric] = field(default_factory=list)
    subject_outcomes: dict[str, str] = field(default_factory=dict)
    attempts: list[CTOEvidenceAttempt] = field(default_factory=list)
    reuse_decisions: list[CTOEvidenceReuseDecision] = field(default_factory=list)
    quality_dimensions: list[CTOEvidenceQualityDimension] = field(default_factory=list)
    external_actions: list[CTOEvidenceExternalAction] = field(default_factory=list)
    outcome_counts: Counter[str] = field(default_factory=Counter)
    available_classes: set[str] = field(default_factory=set)
    limitations: list[str] = field(default_factory=list)
    attempt_history_status: str = "unavailable"
    reuse_status: str = "unavailable"
    invalid: bool = False
    unprojected_sources: bool = False


def _merge_outcomes(target: _SourceProjection, incoming: _SourceProjection) -> None:
    detail_counts = Counter(incoming.subject_outcomes.values())
    if incoming.subject_outcomes:
        if incoming.outcome_counts != detail_counts:
            target.invalid = True
            target.limitations.append(
                "Producer outcome totals do not reconcile to subject outcomes."
            )
        for subject_id, outcome in incoming.subject_outcomes.items():
            existing = target.subject_outcomes.get(subject_id)
            if existing is not None and existing != outcome:
                target.invalid = True
                target.limitations.append(
                    "Authoritative sources disagree on a subject terminal outcome."
                )
                continue
            target.subject_outcomes[subject_id] = outcome
        reconciled = Counter(target.subject_outcomes.values())
        if target.outcome_counts and target.outcome_counts != reconciled:
            target.invalid = True
            target.limitations.append(
                "Aggregate and subject outcome evidence disagree."
            )
        target.outcome_counts = reconciled
        return
    if not incoming.outcome_counts:
        return
    if target.subject_outcomes:
        if incoming.outcome_counts != Counter(target.subject_outcomes.values()):
            target.invalid = True
            target.limitations.append(
                "Aggregate and subject outcome evidence disagree."
            )
        return
    if target.outcome_counts and target.outcome_counts != incoming.outcome_counts:
        target.invalid = True
        target.limitations.append(
            "Authoritative sources report contradictory aggregate outcomes."
        )
        return
    target.outcome_counts = Counter(incoming.outcome_counts)


@dataclass(frozen=True)
class _LoadedSource:
    reference: CTOEvidenceSourceReference
    payload: object | None
    path: Path | None
    issue: str | None = None


def project_cto_evidence(
    *,
    run_manifest_path: Path | None,
    repository_root: Path,
    collector_repository_sha: str,
    historical_telemetry_path: Path,
) -> CTOEvidenceBundle:
    """Build a declared-run bundle or explicit historical snapshot from local files."""

    historical_ref, historical_state = _project_historical_state(
        historical_telemetry_path,
        repository_root=repository_root,
        collector_sha=collector_repository_sha,
    )
    if run_manifest_path is None:
        summary = _executive_summary(
            run=None,
            run_evidence=None,
            historical_state=historical_state,
            completeness="complete",
            disposition="not_evaluated",
            limitations=(),
        )
        return CTOEvidenceBundle(
            schema_version=SCHEMA_VERSION,
            generated_at_utc=_utc_now(),
            collector_repository_sha=collector_repository_sha,
            mode="historical_system_snapshot",
            run=None,
            run_evidence=None,
            historical_state=historical_state,
            source_references=(historical_ref,),
            completeness="complete",
            disposition="not_evaluated",
            executive_summary=summary,
            limitations=(
                "No workload run was declared; collected runtime metrics are "
                "historical system state.",
            ),
        )

    manifest_path = _resolve_inside_root(run_manifest_path, repository_root)
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_ref = CTOEvidenceSourceReference(
        schema_version=SCHEMA_VERSION,
        source_id="run_manifest",
        producer="cto_review_collector",
        format_id="marketlense/cto-evidence-run-manifest/1.0",
        path=_relative_reference_path(manifest_path, repository_root, manifest_sha),
        sha256=manifest_sha,
        tested_repository_sha=None,
        role="supporting",
        status="verified",
        byte_count=len(manifest_bytes),
        observed_sha256=manifest_sha,
    )
    payload = _decode_json(manifest_bytes, "run manifest")
    run = parse_cto_evidence_run(_manifest_run_payload(payload))
    if any(
        item.source_id in {"run_manifest", "historical_runtime_telemetry"}
        for item in run.sources
    ):
        raise ValueError("run source IDs use a collector-reserved value")

    loaded, source_refs, input_issues = _load_run_sources(run, repository_root)
    source_projection = _SourceProjection()
    available_classes = _declared_evidence_classes(run)
    if run.started_at_utc is None:
        source_projection.limitations.append(
            "Producer run timestamps were not retained in the declared manifest."
        )
    if source_refs and all(item.status == "verified" for item in source_refs):
        available_classes.add("source_integrity")
    comparison_sources: dict[str, object] = {}
    crop_sources: list[_LoadedSource] = []
    run_sha_source_count = 0
    run_sha_sources_bound = True
    run_sha_is_proven = False
    for item in loaded:
        needs_run_sha = item.reference.role in {"run", "candidate"}
        if needs_run_sha:
            run_sha_source_count += 1
        if item.issue is not None:
            if needs_run_sha:
                run_sha_sources_bound = False
            source_projection.limitations.append(item.issue)
            if (
                item.reference.status == "mismatch"
                or item.reference.status == "verified"
            ):
                source_projection.invalid = True
            continue
        if item.payload is None:
            continue
        source_sha = _embedded_tested_sha(
            item.reference.format_id,
            item.payload,
            comparison_side=item.reference.role
            if item.reference.role in {"baseline", "candidate"}
            else None,
        )
        declared_sha = item.reference.tested_repository_sha
        declared_sha = declared_sha.lower() if declared_sha is not None else None
        if item.reference.role == "baseline" and run.comparison is not None:
            expected_sha = run.comparison.baseline_repository_sha.lower()
        elif item.reference.role == "candidate" and run.comparison is not None:
            expected_sha = run.comparison.candidate_repository_sha.lower()
        elif needs_run_sha:
            expected_sha = (
                run.tested_repository_sha.lower()
                if run.tested_repository_sha is not None
                else None
            )
        else:
            expected_sha = declared_sha
        if expected_sha is not None and (
            (declared_sha is not None and declared_sha != expected_sha)
            or (source_sha is not None and source_sha != expected_sha)
        ):
            if needs_run_sha:
                run_sha_sources_bound = False
            source_projection.invalid = True
            source_projection.limitations.append(
                f"Source {item.reference.source_id} tested SHA contradicts its "
                "declared run or comparison endpoint."
            )
            continue
        if needs_run_sha:
            bound = expected_sha is not None and (
                declared_sha == expected_sha or source_sha == expected_sha
            )
            run_sha_sources_bound = run_sha_sources_bound and bound
            if bound and expected_sha == run.tested_repository_sha:
                run_sha_is_proven = True
        if item.reference.format_id == FORMAT_CROP_QA:
            crop_sources.append(item)
            continue
        projected = _project_source(item, run)
        source_projection.metrics.extend(projected.metrics)
        _merge_outcomes(source_projection, projected)
        source_projection.attempts.extend(projected.attempts)
        source_projection.reuse_decisions.extend(projected.reuse_decisions)
        source_projection.quality_dimensions.extend(projected.quality_dimensions)
        source_projection.external_actions.extend(projected.external_actions)
        source_projection.available_classes.update(projected.available_classes)
        source_projection.limitations.extend(projected.limitations)
        source_projection.invalid = source_projection.invalid or projected.invalid
        source_projection.unprojected_sources = (
            source_projection.unprojected_sources or projected.unprojected_sources
        )
        source_projection.attempt_history_status = _merge_status(
            source_projection.attempt_history_status, projected.attempt_history_status
        )
        source_projection.reuse_status = _merge_status(
            source_projection.reuse_status, projected.reuse_status
        )
        if item.reference.source_id in {
            run.comparison.baseline_source_id if run.comparison else "",
            run.comparison.candidate_source_id if run.comparison else "",
        }:
            comparison_sources[item.reference.source_id] = item.payload

    if run_sha_source_count > 0 and run_sha_sources_bound and run_sha_is_proven:
        available_classes.add("exact_repository_sha")

    if crop_sources:
        crop_projection = _project_crop_sidecars(crop_sources, run)
        source_projection.metrics.extend(crop_projection.metrics)
        source_projection.quality_dimensions.extend(crop_projection.quality_dimensions)
        source_projection.available_classes.update(crop_projection.available_classes)
        source_projection.limitations.extend(crop_projection.limitations)
        source_projection.invalid = source_projection.invalid or crop_projection.invalid
        source_projection.attempt_history_status = _merge_status(
            source_projection.attempt_history_status,
            crop_projection.attempt_history_status,
        )

    output_subjects = _project_subjects(
        run.subjects, source_projection.subject_outcomes
    )
    _add_unavailable_subject_resources(run, source_projection, output_subjects)
    source_projection.metrics.extend(
        _outcome_metrics(
            output_subjects,
            source_projection.outcome_counts,
            tuple(item.source_id for item in run.sources),
        )
    )
    criteria = _evaluate_criteria(run, source_projection.metrics)
    if _metric_conflicts(tuple(source_projection.metrics)):
        source_projection.invalid = True
        source_projection.limitations.append(
            "Authoritative sources report contradictory values for the same run metric."
        )
    comparison = _project_comparison(run.comparison, comparison_sources)
    if comparison is not None and comparison.status == "compatible":
        source_projection.metrics.extend(comparison.metric_deltas)
        source_projection.available_classes.add("comparison")

    available_classes.update(source_projection.available_classes)
    required_classes = set(run.required_evidence_classes) | {"exact_repository_sha"}
    missing_classes = required_classes - available_classes
    if missing_classes:
        source_projection.limitations.extend(
            f"Required evidence class {name} is unavailable from retained "
            "authoritative sources."
            for name in sorted(missing_classes)
        )
    if input_issues:
        source_projection.limitations.extend(input_issues)
    if len(output_subjects) != len(run.subjects):
        source_projection.invalid = True
        source_projection.limitations.append(
            "Projected and declared subject counts do not reconcile."
        )
    missing_terminal_outcomes = any(
        item.terminal_outcome is None for item in output_subjects
    )
    if missing_terminal_outcomes and "outcomes" in run.required_evidence_classes:
        source_projection.limitations.append(
            "One or more declared subjects have no retained terminal outcome."
        )

    run_evidence = CTOEvidenceRunEvidence(
        schema_version=SCHEMA_VERSION,
        subjects=output_subjects,
        metrics=tuple(_unique_metrics(source_projection.metrics)),
        criteria=criteria,
        outcomes=tuple(
            CTOEvidenceOutcomeCount(
                schema_version=SCHEMA_VERSION,
                outcome=name,
                count=count,
            )
            for name, count in sorted(source_projection.outcome_counts.items())
        ),
        attempts=tuple(
            sorted(
                source_projection.attempts,
                key=lambda item: (item.subject_id, item.attempt_number),
            )
        ),
        reuse_decisions=tuple(
            sorted(source_projection.reuse_decisions, key=lambda item: item.subject_id)
        ),
        quality_dimensions=tuple(
            sorted(
                source_projection.quality_dimensions, key=lambda item: item.dimension
            )
        ),
        external_actions=tuple(source_projection.external_actions),
        comparison=comparison,
        attempt_history_status=source_projection.attempt_history_status,  # type: ignore[arg-type]
        reuse_evidence_status=source_projection.reuse_status,  # type: ignore[arg-type]
        limitations=tuple(_unique_text(source_projection.limitations)),
    )

    if _metric_conflicts(run_evidence.metrics):
        source_projection.invalid = True
        source_projection.limitations.append(
            "Authoritative sources report contradictory values for the same run metric."
        )
    if _metric_reconciliation_errors(run_evidence.metrics):
        source_projection.invalid = True
        source_projection.limitations.append(
            "Per-subject measurements do not reconcile to their retained run aggregate."
        )
    if _attempt_history_invalid(run_evidence.attempts):
        source_projection.invalid = True
        source_projection.limitations.append(
            "Attempt history is duplicated or does not preserve append-only ordering."
        )
    if source_projection.invalid:
        run_evidence = replace(
            run_evidence,
            limitations=tuple(_unique_text(source_projection.limitations)),
        )

    incomplete = (
        bool(missing_classes or input_issues)
        or (missing_terminal_outcomes and "outcomes" in run.required_evidence_classes)
        or source_projection.unprojected_sources
        or any(
            item.required and item.disposition == "insufficient_evidence"
            for item in criteria
        )
    )
    completeness = (
        "invalid"
        if source_projection.invalid
        else "incomplete"
        if incomplete
        else "complete"
    )
    disposition = (
        "fail"
        if completeness == "invalid"
        else derive_required_criteria_disposition(criteria)
    )
    if completeness == "incomplete" and disposition == "pass":
        disposition = "insufficient_evidence"
    limitations = tuple(
        _unique_text(
            [
                *source_projection.limitations,
                *[text for item in criteria for text in _criterion_limit(item)],
            ]
        )
    )
    summary = _executive_summary(
        run=run,
        run_evidence=run_evidence,
        historical_state=historical_state,
        completeness=completeness,
        disposition=disposition,
        limitations=limitations,
    )
    public_sources = tuple(
        _public_source_reference(item)
        for item in (manifest_ref, *source_refs, historical_ref)
    )
    public_run = replace(
        run,
        sources=tuple(_public_source_reference(item) for item in run.sources),
    )
    bundle = CTOEvidenceBundle(
        schema_version=SCHEMA_VERSION,
        generated_at_utc=_utc_now(),
        collector_repository_sha=collector_repository_sha,
        mode="declared_run",
        run=public_run,
        run_evidence=run_evidence,
        historical_state=historical_state,
        source_references=public_sources,
        completeness=completeness,  # type: ignore[arg-type]
        disposition=disposition,
        executive_summary=summary,
        limitations=limitations,
    )
    cto_evidence_bundle_payload(bundle)
    return bundle


def _public_source_reference(
    reference: CTOEvidenceSourceReference,
) -> CTOEvidenceSourceReference:
    if reference.format_id != FORMAT_CROP_QA:
        return reference
    return replace(
        reference,
        path=f"evidence/crop-qa/{reference.sha256[:24]}.qa.json",
    )


def _declared_evidence_classes(run: CTOEvidenceRun) -> set[str]:
    classes: set[str] = set()
    if run.subjects and all(item.immutable for item in run.subjects):
        classes.add("immutable_subjects")
    if run.configuration_identities:
        classes.add("configuration_identity")
    if run.stages_in_scope or run.stages_out_of_scope:
        classes.add("stage_scope")
    if run.started_at_utc is not None and run.ended_at_utc is not None:
        classes.add("run_timestamps")
    if run.external_side_effects_enabled is not None:
        classes.add("external_side_effect_policy")
    return classes


def _project_source(source: _LoadedSource, run: CTOEvidenceRun) -> _SourceProjection:
    payload = source.payload
    if not isinstance(payload, dict):
        return _malformed_projection("Retained evidence source is not a JSON object.")
    fmt = source.reference.format_id
    if fmt == FORMAT_GENERIC:
        return _project_generic(payload, source.reference, run)
    if fmt == FORMAT_FROZEN_COHORT:
        return _project_frozen_cohort(payload, source.reference, run)
    if fmt == FORMAT_ARTIFACT_DAG:
        result = _project_numeric(
            payload, source.reference, roots=("before", "after", "comparison", "report")
        )
        result.limitations.extend(_producer_limitations(fmt, payload))
        return result
    if fmt == FORMAT_PROVIDER_PROFILE:
        result = _project_numeric(payload, source.reference)
        _bind_single_subject(result, run, payload.get("report_id"))
        result.limitations.append(
            "Summed provider elapsed time is aggregate work; it is not the report "
            "critical path or total wall time."
        )
        result.attempt_history_status = "partial"
        return result
    if fmt == FORMAT_PROVIDER_CRITICAL_PATH:
        result = _project_numeric(payload, source.reference)
        profile = payload.get("provider_profile")
        report_id = profile.get("report_id") if isinstance(profile, dict) else None
        _bind_single_subject(result, run, report_id)
        if isinstance(payload.get("critical_path_recommendation"), str) or isinstance(
            payload.get("top_5_wall_clock_exposure_opportunities"), list
        ):
            result.available_classes.add("critical_path")
        result.limitations.extend(_producer_limitations(fmt, payload))
        return result
    if fmt == FORMAT_CONCURRENCY:
        result = _project_numeric(payload, source.reference)
        if not run.subjects and isinstance(payload.get("manifest"), dict):
            manifest = payload["manifest"]
            if _nonnegative_int(manifest.get("report_count")):
                result.limitations.append(
                    "Producer retained a cohort size but no immutable "
                    "per-subject identities."
                )
        result.limitations.extend(_producer_limitations(fmt, payload))
        return result
    if fmt == FORMAT_REUSE:
        return _project_reuse(payload, source.reference, run)
    if fmt == FORMAT_FILE_SEARCH:
        return _project_file_search(payload, source.reference, run)
    if fmt == FORMAT_ACQUISITION:
        return _project_acquisition(payload, source.reference, run)
    if fmt == FORMAT_HUMAN_REVIEW:
        return _project_human_review(payload, source.reference, run)
    if fmt == FORMAT_WORDPRESS:
        return _project_wordpress(payload, source.reference)
    return _unsupported_projection(source)


def _project_generic(
    payload: dict[str, Any], source: CTOEvidenceSourceReference, run: CTOEvidenceRun
) -> _SourceProjection:
    result = _SourceProjection()
    measurements = payload.get("measurements")
    if isinstance(measurements, dict):
        flattened = _flatten_numeric(measurements)
        for name, value in flattened.items():
            result.metrics.append(
                _metric(
                    f"{source.source_id}.{name}",
                    value,
                    source.source_id,
                    semantics=_semantics(name),
                )
            )
        if flattened:
            result.available_classes.add("measurements")
    elif measurements is not None:
        result.invalid = True
        result.limitations.append(
            "Generic measurements must be an object of numeric values."
        )
    if isinstance(payload.get("subjects"), list):
        result.available_classes.update({"outcomes", "subjects"})
    _project_generic_subjects(payload.get("subjects"), run, source, result)
    detailed_outcomes = Counter(result.outcome_counts)
    raw_outcomes = payload.get("outcomes")
    if isinstance(raw_outcomes, dict):
        declared_outcomes: Counter[str] = Counter()
        for raw_name, raw_count in raw_outcomes.items():
            normalized_name = _safe_outcome(raw_name)
            if normalized_name is None or not _nonnegative_int(raw_count):
                result.invalid = True
                result.limitations.append("Generic outcome evidence is malformed.")
                continue
            declared_outcomes[normalized_name] = raw_count
        if detailed_outcomes and declared_outcomes != detailed_outcomes:
            result.invalid = True
            result.limitations.append(
                "Generic subject outcomes do not reconcile to aggregate outcomes."
            )
        elif not detailed_outcomes:
            result.outcome_counts.update(declared_outcomes)
        result.available_classes.add("outcomes")
    _generic_attempts(payload.get("attempts"), run, source.source_id, result)
    _generic_reuse(payload.get("reuse_decisions"), run, source.source_id, result)
    return result


def _project_generic_subjects(
    rows: object,
    run: CTOEvidenceRun,
    source: CTOEvidenceSourceReference,
    result: _SourceProjection,
) -> None:
    if not isinstance(rows, list):
        return
    subjects_by_hash = {item.identity_sha256: item for item in run.subjects}
    seen_subjects: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            result.invalid = True
            continue
        identity_hash = row.get("identity_sha256")
        subject = (
            subjects_by_hash.get(str(identity_hash))
            if isinstance(identity_hash, str)
            else None
        )
        if subject is None:
            result.invalid = True
            result.limitations.append(
                "Generic subject identity does not match the declared cohort."
            )
            continue
        if subject.subject_id in seen_subjects:
            result.invalid = True
            result.limitations.append(
                "Generic subject rows contain duplicate immutable identities."
            )
            continue
        seen_subjects.add(subject.subject_id)
        outcome = _safe_outcome(row.get("outcome"))
        if outcome is not None:
            if subject.subject_id in result.subject_outcomes:
                result.invalid = True
                result.limitations.append("Generic subject outcome is duplicated.")
                continue
            result.subject_outcomes[subject.subject_id] = outcome
            result.outcome_counts[outcome] += 1
        metrics = row.get("metrics")
        if metrics is None:
            continue
        if not isinstance(metrics, dict):
            result.invalid = True
            result.limitations.append("Generic per-subject metrics are malformed.")
            continue
        for raw_name, value in _flatten_numeric(metrics).items():
            result.metrics.append(
                _metric(
                    f"{source.source_id}.{raw_name}",
                    value,
                    source.source_id,
                    subject_id=subject.subject_id,
                    semantics="Producer-declared per-subject measurement.",
                )
            )


def _project_numeric(
    payload: dict[str, Any],
    source: CTOEvidenceSourceReference,
    *,
    roots: tuple[str, ...] | None = None,
) -> _SourceProjection:
    result = _SourceProjection()
    selected = (
        {key: payload[key] for key in roots if key in payload}
        if roots is not None
        else payload
    )
    flattened = _flatten_numeric(selected)
    for name, value in flattened.items():
        result.metrics.append(
            _metric(
                f"{source.source_id}.{name}",
                value,
                source.source_id,
                status="observed",
                semantics=_semantics(name),
            )
        )
    if result.metrics:
        result.available_classes.add("measurements")
        result.available_classes.update(
            _NUMERIC_FORMAT_EVIDENCE_CLASSES.get(source.format_id, ())
        )
    return result


def _bind_single_subject(
    projection: _SourceProjection,
    run: CTOEvidenceRun,
    raw_identity: object,
) -> None:
    if not isinstance(raw_identity, str) or not raw_identity:
        if run.subjects:
            projection.invalid = True
            projection.limitations.append(
                "Per-report source does not retain an identity matching the "
                "declared subject."
            )
        else:
            projection.limitations.append(
                "Per-report metrics are aggregate because no immutable subject "
                "was declared."
            )
        return
    subject = _subject_for_identity(run, _hash_identity(raw_identity))
    if subject is None or len(run.subjects) != 1:
        projection.invalid = True
        projection.limitations.append(
            "Per-report source identity does not match exactly one declared subject."
        )
        return
    projection.metrics.extend(
        replace(metric, subject_id=subject.subject_id)
        for metric in tuple(projection.metrics)
    )
    projection.available_classes.add("subjects")


def _project_frozen_cohort(
    payload: dict[str, Any], source: CTOEvidenceSourceReference, run: CTOEvidenceRun
) -> _SourceProjection:
    result = _SourceProjection()
    summary = payload.get("summary")
    cohort_metrics = payload.get("cohort_metrics")
    if not isinstance(summary, dict) or not isinstance(cohort_metrics, dict):
        return _malformed_projection("Frozen-cohort result lacks its typed summary.")
    report_count = payload.get("cohort_size")
    summary_count = summary.get("report_count")
    if not _nonnegative_int(report_count) or not _nonnegative_int(summary_count):
        return _malformed_projection(
            "Frozen-cohort subject denominator is unavailable."
        )
    if report_count != summary_count or report_count != len(run.subjects):
        result.invalid = True
        result.limitations.append(
            "Frozen-cohort denominator contradicts the declared immutable subjects."
        )
    metric_map = (
        ("subjects.denominator", report_count, "subjects", "observed"),
        (
            "outcomes.admitted_count",
            summary.get("admitted_report_count"),
            "subjects",
            "observed",
        ),
        (
            "quality.publication_readiness_rate",
            summary.get("publication_readiness_rate"),
            "ratio",
            "observed",
        ),
        (
            "quality.validation_terminal_rate",
            summary.get("typed_terminal_rate"),
            "ratio",
            "observed",
        ),
        (
            "reliability.workflow_failure_rate",
            summary.get("workflow_failure_rate"),
            "ratio",
            "observed",
        ),
        (
            "operator.intervention_count",
            summary.get("operator_intervention_count"),
            "subjects",
            "observed",
        ),
        (
            "resource.provider_calls",
            cohort_metrics.get("model_provider_calls"),
            "calls",
            "partial",
        ),
        (
            "resource.input_tokens",
            cohort_metrics.get("input_tokens"),
            "tokens",
            "partial",
        ),
        (
            "resource.output_tokens",
            cohort_metrics.get("output_tokens"),
            "tokens",
            "partial",
        ),
        ("resource.cost_usd", cohort_metrics.get("cost_usd"), "USD", "partial"),
        (
            "performance.wall_seconds",
            cohort_metrics.get("duration_seconds"),
            "seconds",
            "partial",
        ),
    )
    for metric_id, value, unit, status in metric_map:
        if _finite_scalar(value):
            result.metrics.append(
                _metric(
                    metric_id,
                    value,
                    source.source_id,
                    status=status,
                    unit=unit,
                    denominator=report_count
                    if metric_id != "subjects.denominator"
                    else None,
                    semantics=(
                        "Cohort total is retained, but per-subject attribution is "
                        "unavailable."
                        if status == "partial"
                        else "Producer-declared cohort outcome."
                    ),
                )
            )
        else:
            result.metrics.append(
                _metric(
                    metric_id,
                    None,
                    source.source_id,
                    status="unavailable",
                    unit=unit,
                    limitations=(
                        "The retained producer result has no value for this measure.",
                    ),
                )
            )
    reports = payload.get("reports")
    if not isinstance(reports, list):
        result.invalid = True
        result.limitations.append("Frozen-cohort per-subject outcome rows are missing.")
    else:
        seen: set[str] = set()
        subjects_by_identity = {item.identity_sha256: item for item in run.subjects}
        for row in reports:
            if not isinstance(row, dict) or not isinstance(row.get("report_id"), str):
                result.invalid = True
                continue
            identity_hash = _hash_identity(str(row["report_id"]))
            subject = subjects_by_identity.get(identity_hash)
            if subject is None or identity_hash in seen:
                result.invalid = True
                result.limitations.append(
                    "Frozen-cohort subject identities do not match the declared set."
                )
                continue
            seen.add(identity_hash)
            outcome = _reliability_outcome(row)
            result.subject_outcomes[subject.subject_id] = outcome
            result.outcome_counts[outcome] += 1
        if len(seen) != len(run.subjects):
            result.invalid = True
            result.limitations.append(
                "Frozen-cohort outcome rows do not cover the declared denominator."
            )
    for subject in run.subjects:
        for metric_id, unit in (
            ("resource.provider_calls", "calls"),
            ("resource.input_tokens", "tokens"),
            ("resource.output_tokens", "tokens"),
            ("resource.cost_usd", "USD"),
            ("performance.wall_seconds", "seconds"),
        ):
            result.metrics.append(
                _metric(
                    metric_id,
                    None,
                    source.source_id,
                    status="unavailable",
                    unit=unit,
                    subject_id=subject.subject_id,
                    limitations=(
                        "The retained cohort result does not attribute this total "
                        "to each subject.",
                    ),
                )
            )
    result.available_classes.update({"outcomes", "subjects"})
    if any(
        metric.status in {"observed", "partial"}
        for metric in result.metrics
        if metric.metric_id.startswith("quality.")
    ):
        result.available_classes.add("quality")
    if any(
        metric.status in {"observed", "partial"}
        for metric in result.metrics
        if metric.metric_id.startswith("resource.")
    ):
        result.available_classes.add("resource_usage")
    result.attempt_history_status = "partial"
    result.reuse_status = "unavailable"
    result.limitations.extend(
        (
            "Per-subject calls, tokens, cost, and duration are not attributed in "
            "the retained cohort result.",
            "Workflow attempt counts are aggregate and do not preserve typed "
            "first-attempt and recovery events.",
        )
    )
    return result


def _project_reuse(
    payload: dict[str, Any], source: CTOEvidenceSourceReference, run: CTOEvidenceRun
) -> _SourceProjection:
    result = _project_numeric(payload, source)
    counters: dict[str, int] = {}
    follow_up = payload.get("repair_bearing_follow_up")
    if isinstance(follow_up, dict):
        raw_counters = follow_up.get("summed_reuse_counters")
        if isinstance(raw_counters, dict):
            counters = {
                key: int(value)
                for key, value in raw_counters.items()
                if _nonnegative_int(value)
            }
    decisions: object = (
        follow_up.get("reuse_decisions") if isinstance(follow_up, dict) else None
    )
    if (
        isinstance(decisions, list)
        and decisions
        and all(
            isinstance(row, dict)
            and isinstance(row.get("subject_identity_sha256"), str)
            for row in decisions
        )
    ):
        _reuse_decisions_from_rows(decisions, run, source.source_id, result)
    elif isinstance(decisions, list) and decisions:
        result.limitations.append(
            "Producer reuse rows are aggregate and do not retain immutable "
            "subject identities."
        )
    if counters:
        for field_name, metric_id, unit in (
            ("reused_validation_results", "reuse.reused_validations", "validations"),
            ("newly_validated_claims", "reuse.new_validations", "validations"),
            ("grounding_calls_avoided", "reuse.avoided_grounding_calls", "calls"),
            (
                "semantic_validation_calls_avoided",
                "reuse.avoided_semantic_calls",
                "calls",
            ),
        ):
            if field_name in counters:
                result.metrics.append(
                    _metric(
                        metric_id, counters[field_name], source.source_id, unit=unit
                    )
                )
        result.reuse_status = "partial" if not result.reuse_decisions else "observed"
        result.available_classes.add("reuse")
    else:
        result.reuse_status = "unavailable"
        result.limitations.append(
            "No retained reuse counters were present in the producer artifact."
        )
    result.attempt_history_status = "partial"
    return result


def _project_file_search(
    payload: dict[str, Any], source: CTOEvidenceSourceReference, run: CTOEvidenceRun
) -> _SourceProjection:
    result = _project_numeric(
        payload, source, roots=("cohorts", "publication_side_effects")
    )
    cohorts = payload.get("cohorts")
    if isinstance(cohorts, dict) and all(
        isinstance(cohorts.get(side), dict) for side in ("baseline", "candidate")
    ):
        result.available_classes.add("comparison")
    comparisons = payload.get("report_comparison")
    _subject_outcomes_from_rows(
        comparisons,
        run,
        result,
        identity_key="report_id",
        outcome_builder=_file_search_outcome,
    )
    per_subject_calls: dict[str, dict[str, int]] = {
        "baseline": {},
        "candidate": {},
    }
    if isinstance(comparisons, list):
        if comparisons:
            result.available_classes.update({"outcomes", "subjects"})
        for row in comparisons:
            if not isinstance(row, dict):
                continue
            identity = row.get("report_id")
            if not isinstance(identity, str):
                continue
            subject = _subject_for_identity(run, _hash_identity(identity))
            if subject is None:
                result.invalid = True
                result.limitations.append(
                    "File Search subject identity does not match the declared cohort."
                )
                continue
            for side in ("baseline", "candidate"):
                calls = row.get(f"{side}_file_search_calls")
                if _nonnegative_int(calls):
                    metric_id = f"resource.file_search_calls.{side}"
                    result.metrics.append(
                        _metric(
                            metric_id,
                            calls,
                            source.source_id,
                            unit="calls",
                            subject_id=subject.subject_id,
                        )
                    )
                    per_subject_calls[side][subject.subject_id] = calls
    if isinstance(comparisons, list) and len(comparisons) != len(run.subjects):
        result.invalid = True
        result.limitations.append(
            "File Search subject rows do not reconcile to the declared cohort."
        )
    if isinstance(cohorts, dict):
        for side in ("baseline", "candidate"):
            cohort = cohorts.get(side)
            cohort_metrics = cohort.get("metrics") if isinstance(cohort, dict) else None
            aggregate_calls = (
                cohort_metrics.get("file_search_calls")
                if isinstance(cohort_metrics, dict)
                else None
            )
            if not _nonnegative_int(aggregate_calls):
                continue
            values = per_subject_calls[side]
            if (
                run.subjects
                and len(values) == len(run.subjects)
                and sum(values.values()) != aggregate_calls
            ):
                result.invalid = True
                result.limitations.append(
                    f"File Search {side} per-subject calls do not reconcile to "
                    "the cohort total."
                )
            result.metrics.append(
                _metric(
                    f"resource.file_search_calls.{side}",
                    aggregate_calls,
                    source.source_id,
                    unit="calls",
                    semantics=(
                        "Producer-declared cohort total; per-subject rows are "
                        "reconciled when complete."
                    ),
                )
            )
    result.limitations.extend(_producer_limitations(FORMAT_FILE_SEARCH, payload))
    return result


def _project_acquisition(
    payload: dict[str, Any], source: CTOEvidenceSourceReference, run: CTOEvidenceRun
) -> _SourceProjection:
    result = _project_numeric(payload, source, roots=("before_after", "consistency"))
    if isinstance(payload.get("before_after"), dict):
        result.available_classes.add("acquisition")
    attempts = payload.get("attempts")
    if not isinstance(attempts, list):
        result.attempt_history_status = "unavailable"
        result.limitations.append("Acquisition attempt detail is unavailable.")
        return result
    subject_by_hash = {item.identity_sha256: item for item in run.subjects}
    attempt_numbers: Counter[str] = Counter()
    attempt_measurements: dict[str, dict[str, list[float]]] = {}
    metric_fields = (
        ("agent_calls", "resource.acquisition.agent_calls", "calls"),
        ("browser_launches", "resource.acquisition.browser_launches", "launches"),
        ("cost_usd", "resource.acquisition.cost_usd", "USD"),
        ("duration_seconds", "performance.acquisition.duration_seconds", "seconds"),
        ("mailbox_reads", "resource.acquisition.mailbox_reads", "reads"),
        ("tokens", "resource.acquisition.tokens", "tokens"),
    )
    for row in attempts:
        if not isinstance(row, dict) or not isinstance(row.get("candidate_id"), str):
            result.invalid = True
            continue
        identity_hash = _hash_identity(str(row["candidate_id"]))
        subject = subject_by_hash.get(identity_hash)
        if subject is None:
            result.invalid = True
            result.limitations.append(
                "Acquisition subject identity does not match the declared set."
            )
            continue
        attempt_numbers[subject.subject_id] += 1
        subject_measurements = attempt_measurements.setdefault(subject.subject_id, {})
        for field_name, metric_id, _unit_name in metric_fields:
            value = row.get(field_name)
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and value >= 0
            ):
                subject_measurements.setdefault(metric_id, []).append(float(value))
        successful = row.get("verified_artifact") is True
        outcome: _AttemptOutcome = "success" if successful else "failed"
        result.attempts.append(
            CTOEvidenceAttempt(
                schema_version=SCHEMA_VERSION,
                subject_id=subject.subject_id,
                attempt_number=attempt_numbers[subject.subject_id],
                kind="initial_execution"
                if attempt_numbers[subject.subject_id] == 1
                else "workflow_retry",
                outcome=outcome,
                failure_code=_safe_code(row.get("failure_class")),
                source_id=source.source_id,
            )
        )
        result.subject_outcomes[subject.subject_id] = (
            "acquired" if successful else "not_acquired"
        )
    total_attempts = sum(attempt_numbers.values())
    if total_attempts:
        for _field_name, metric_id, unit_name in metric_fields:
            retained_attempt_count = sum(
                len(values.get(metric_id, []))
                for values in attempt_measurements.values()
            )
            if not retained_attempt_count:
                continue
            aggregate_status = (
                "observed" if retained_attempt_count == total_attempts else "partial"
            )
            aggregate_value = sum(
                sum(values.get(metric_id, []))
                for values in attempt_measurements.values()
            )
            limitation = (
                ()
                if aggregate_status == "observed"
                else ("Some retained acquisition attempts lack this measure.",)
            )
            result.metrics.append(
                _metric(
                    metric_id,
                    aggregate_value,
                    source.source_id,
                    status=aggregate_status,
                    unit=unit_name,
                    semantics=(
                        "Retained acquisition attempt totals; this is not "
                        "provider-active time."
                    ),
                    limitations=limitation,
                )
            )
            for subject in run.subjects:
                subject_values = attempt_measurements.get(subject.subject_id, {}).get(
                    metric_id, []
                )
                expected_subject_attempts = attempt_numbers.get(subject.subject_id, 0)
                subject_status = (
                    "unavailable"
                    if not subject_values
                    else "observed"
                    if len(subject_values) == expected_subject_attempts
                    else "partial"
                )
                result.metrics.append(
                    _metric(
                        metric_id,
                        sum(subject_values) if subject_values else None,
                        source.source_id,
                        status=subject_status,
                        unit=unit_name,
                        subject_id=subject.subject_id,
                        semantics=(
                            "Retained acquisition attempt totals for this subject."
                        ),
                        limitations=(
                            ()
                            if subject_status == "observed"
                            else (
                                "One or more subject attempt measures are unavailable.",
                            )
                        ),
                    )
                )
        if any(
            metric.metric_id.startswith("resource.acquisition.")
            for metric in result.metrics
        ):
            result.available_classes.add("resource_usage")
    result.outcome_counts.update(Counter(result.subject_outcomes.values()))
    result.available_classes.add("outcomes")
    result.available_classes.add("attempt_history")
    result.attempt_history_status = "observed"
    result.limitations.extend(_producer_limitations(FORMAT_ACQUISITION, payload))
    return result


def _project_human_review(
    payload: dict[str, Any], source: CTOEvidenceSourceReference, run: CTOEvidenceRun
) -> _SourceProjection:
    result = _SourceProjection()
    reports = payload.get("reports")
    if not isinstance(reports, list):
        return _malformed_projection("Editorial review report list is missing.")
    score_values: dict[str, list[float]] = {}
    reviewed_subjects: set[str] = set()
    subject_by_hash = {item.identity_sha256: item for item in run.subjects}
    for row in reports:
        if not isinstance(row, dict):
            result.invalid = True
            continue
        html_sha = row.get("reviewed_final_html_sha256")
        if not isinstance(html_sha, str) or not _SHA_RE.fullmatch(html_sha):
            result.invalid = True
            continue
        subject = subject_by_hash.get(html_sha)
        if subject is None:
            result.invalid = True
            result.limitations.append(
                "Editorial review subject hashes do not match the declared set."
            )
            continue
        if subject.subject_id in reviewed_subjects:
            result.invalid = True
            result.limitations.append(
                "Editorial review contains duplicate subject rows."
            )
            continue
        reviewed_subjects.add(subject.subject_id)
        scores = row.get("scores")
        if not isinstance(scores, dict):
            continue
        for key, value in scores.items():
            if not _METRIC_KEY_RE.fullmatch(str(key)) or not _finite_number(value):
                continue
            score_values.setdefault(str(key), []).append(float(value))
    for key, values in sorted(score_values.items()):
        mean_score = sum(values) / len(values)
        result.metrics.append(
            _metric(
                f"quality.human_editorial.{key}.mean",
                round(mean_score, 4),
                source.source_id,
                unit="score",
                numerator=sum(values),
                denominator=len(values),
                semantics=(
                    "Arithmetic mean of retained reviewer scores; rubric scale "
                    "remains producer-defined."
                ),
            )
        )
    result.metrics.append(
        _metric(
            "quality.human_editorial.reviewed_subject_count",
            len(reviewed_subjects),
            source.source_id,
            unit="subjects",
        )
    )
    result.quality_dimensions.append(
        CTOEvidenceQualityDimension(
            schema_version=SCHEMA_VERSION,
            dimension="human_editorial",
            status="observed" if score_values else "unavailable",
            reviewed_subject_count=len(reviewed_subjects),
            rubric_id=None,
            reviewer_attribution="unavailable",
            metric_ids=tuple(item.metric_id for item in result.metrics),
            source_ids=(source.source_id,),
        )
    )
    if score_values:
        result.available_classes.update({"quality", "human_quality"})
    if reviewed_subjects:
        result.available_classes.add("subjects")
    result.attempt_history_status = "not_applicable"
    result.limitations.append(
        "Reviewer attribution and a versioned rubric are not retained with this "
        "review corpus."
    )
    if len(reviewed_subjects) != len(run.subjects):
        result.invalid = True
        result.limitations.append(
            "Editorial review count does not reconcile to declared subjects."
        )
    return result


def _project_wordpress(
    payload: dict[str, Any], source: CTOEvidenceSourceReference
) -> _SourceProjection:
    result = _SourceProjection()
    attempt = payload.get("publication_attempt")
    readback = payload.get("readback")
    repeat = payload.get("repeat_publication")
    scope = payload.get("scope")
    if not all(isinstance(item, dict) for item in (attempt, readback, repeat, scope)):
        return _malformed_projection(
            "WordPress action evidence is missing a required typed section."
        )
    assert (
        isinstance(attempt, dict)
        and isinstance(readback, dict)
        and isinstance(repeat, dict)
        and isinstance(scope, dict)
    )
    created = attempt.get("created_count")
    blocked = attempt.get("blocked_count")
    requested = scope.get("authorized_publication_subset_size")
    attempted = (
        created + blocked
        if _nonnegative_int(created) and _nonnegative_int(blocked)
        else None
    )
    if _nonnegative_int(requested) and attempted is not None and requested != attempted:
        result.invalid = True
        result.limitations.append(
            "WordPress attempt outcomes do not reconcile to the authorized subset size."
        )
    errors = (
        (attempt.get("outcome_counts") or {}).get("error")
        if isinstance(attempt.get("outcome_counts"), dict)
        else None
    )
    readback_status = _wordpress_readback_status(readback.get("status"))
    repeat_status = _wordpress_repeat_status(
        repeat.get("status"), repeat.get("actual_writes")
    )
    result.external_actions.append(
        CTOEvidenceExternalAction(
            schema_version=SCHEMA_VERSION,
            system="wordpress",
            attempted_actions=attempted,
            actual_writes=None,
            skipped_actions=None,
            blocked_actions=blocked if _nonnegative_int(blocked) else None,
            failed_actions=errors if _nonnegative_int(errors) else None,
            authenticated_readback=readback_status,
            repeat_result=repeat_status,
            idempotency_result=(
                "passed"
                if repeat_status == "zero_write"
                else "failed"
                if repeat_status in {"writes", "failed"}
                else "not_evaluated"
                if repeat_status == "not_run"
                else "unavailable"
            ),
            source_id=source.source_id,
        )
    )
    result.metrics.extend(
        (
            _metric(
                "external.wordpress.authorized_subset_size",
                requested if _nonnegative_int(requested) else None,
                source.source_id,
                unit="actions",
            ),
            _metric(
                "external.wordpress.attempted_actions",
                attempted,
                source.source_id,
                unit="actions",
            ),
            _metric(
                "external.wordpress.reported_created_outcomes",
                created if _nonnegative_int(created) else None,
                source.source_id,
                unit="outcomes",
            ),
            _metric(
                "external.wordpress.blocked_actions",
                blocked if _nonnegative_int(blocked) else None,
                source.source_id,
                unit="actions",
            ),
            _metric(
                "external.wordpress.actual_writes",
                None,
                source.source_id,
                status="unavailable",
                unit="writes",
                limitations=(
                    "The retained addendum does not reconcile created outcomes "
                    "to authenticated writes.",
                ),
            ),
            _metric(
                "external.wordpress.authenticated_readback_count",
                readback.get("authenticated_full_readback_verified_count")
                if _nonnegative_int(
                    readback.get("authenticated_full_readback_verified_count")
                )
                else None,
                source.source_id,
                status="observed"
                if _nonnegative_int(
                    readback.get("authenticated_full_readback_verified_count")
                )
                else "unavailable",
                unit="subjects",
            ),
        )
    )
    result.available_classes.add("external_actions")
    result.available_classes.add("side_effects")
    result.attempt_history_status = "partial"
    result.limitations.extend(
        (
            "Created outcomes are not treated as reconciled actual writes without "
            "authenticated readback.",
            "Repeat publication was not run; no zero-write replay is inferred.",
        )
    )
    return result


def _wordpress_readback_status(
    value: object,
) -> Literal["verified", "failed", "not_run", "unavailable"]:
    normalized = str(value or "").casefold().replace("-", "_")
    if normalized in {"verified", "passed", "complete", "completed", "authenticated"}:
        return "verified"
    if normalized in {"failed", "failure", "mismatch"}:
        return "failed"
    if normalized in {"not_run", "not_started", "not_completed", "skipped"}:
        return "not_run"
    return "unavailable"


def _wordpress_repeat_status(
    status: object,
    actual_writes: object,
) -> Literal["zero_write", "writes", "failed", "not_run", "unavailable"]:
    normalized = str(status or "").casefold().replace("-", "_")
    if normalized in {"failed", "failure"}:
        return "failed"
    if normalized in {"not_run", "not_started", "skipped"}:
        return "not_run"
    if normalized in {"verified", "passed", "complete", "completed"}:
        if _nonnegative_int(actual_writes):
            return "zero_write" if actual_writes == 0 else "writes"
        return "unavailable"
    return "unavailable"


def _project_crop_sidecars(
    sources: list[_LoadedSource], run: CTOEvidenceRun
) -> _SourceProjection:
    result = _SourceProjection()
    from scripts.quality.crop_qa_scorecard import build_crop_qa_scorecard

    valid = [item for item in sources if item.path is not None]
    if not valid:
        return _malformed_projection("No hash-verified crop QA sidecar is available.")
    try:
        scorecard = build_crop_qa_scorecard([str(item.path) for item in valid])
    except (OSError, ValueError, json.JSONDecodeError):
        return _malformed_projection(
            "Retained crop QA scorecard could not read its declared sidecars."
        )
    for item in valid:
        try:
            actual_hash = (
                hashlib.sha256(item.path.read_bytes()).hexdigest() if item.path else ""
            )
        except OSError:
            actual_hash = ""
        if actual_hash != item.reference.sha256:
            result.invalid = True
            result.limitations.append(
                "Crop QA sidecar changed after its declared hash was checked."
            )
    values = (
        ("quality.visual.sidecar_count", scorecard.sidecar_count, "crops"),
        ("quality.visual.accepted_count", scorecard.accepted_count, "crops"),
        ("quality.visual.rejected_count", scorecard.rejected_count, "crops"),
        ("quality.visual.mean_score", scorecard.mean_total_score, "score"),
        ("quality.visual.mean_render_dpi", scorecard.mean_render_dpi, "DPI"),
        ("quality.visual.artifact_bytes", scorecard.artifact_bytes, "bytes"),
        (
            "quality.visual.clipping_defect_count",
            scorecard.clipping_defect_count,
            "defects",
        ),
    )
    ids = tuple(item.reference.source_id for item in valid)
    for metric_id, value, unit in values:
        status = "observed" if scorecard.sidecar_count else "unavailable"
        result.metrics.append(
            _metric(
                metric_id,
                value if scorecard.sidecar_count else None,
                ids[0],
                source_ids=ids,
                status=status,
                unit=unit,
                limitations=(
                    "Crop QA aggregates final sidecars; extraction candidates are "
                    "a separate measurement.",
                ),
            )
        )
    result.quality_dimensions.append(
        CTOEvidenceQualityDimension(
            schema_version=SCHEMA_VERSION,
            dimension="visual_crop_qa",
            status="observed" if scorecard.sidecar_count else "unavailable",
            reviewed_subject_count=scorecard.sidecar_count,
            rubric_id="crop_qa_scorecard_v1.0",
            reviewer_attribution="not_applicable",
            metric_ids=tuple(item[0] for item in values),
            source_ids=ids,
        )
    )
    if scorecard.sidecar_count:
        result.available_classes.update({"quality", "visual_quality"})
        subject_by_identity = {item.identity_sha256: item for item in run.subjects}
        matched_subject_ids: set[str] = set()
        for row in scorecard.rows:
            identity = _hash_identity(row.candidate_id) if row.candidate_id else ""
            subject = subject_by_identity.get(identity)
            if subject is None or subject.subject_id in matched_subject_ids:
                result.invalid = True
                result.limitations.append(
                    "Crop QA candidate identities do not match the declared "
                    "subject set."
                )
                continue
            matched_subject_ids.add(subject.subject_id)
        if len(matched_subject_ids) != len(run.subjects):
            result.invalid = True
            result.limitations.append(
                "Crop QA sidecars do not cover the declared immutable subjects."
            )
        else:
            result.available_classes.add("subjects")
    else:
        result.invalid = True
        result.limitations.append("No readable final crop QA sidecars were retained.")
    result.attempt_history_status = "not_applicable"
    if scorecard.missing_sidecars:
        result.limitations.append(
            "One or more declared crop QA sidecars were missing or unreadable."
        )
    return result


def _project_subjects(
    subjects: tuple[CTOEvidenceSubject, ...], outcomes: dict[str, str]
) -> tuple[CTOEvidenceSubject, ...]:
    return tuple(
        replace(subject, terminal_outcome=outcomes.get(subject.subject_id))
        for subject in subjects
    )


def _project_historical_state(
    path: Path, *, repository_root: Path, collector_sha: str
) -> tuple[CTOEvidenceSourceReference, CTOEvidenceHistoricalState]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("historical telemetry source must be a file")
    content = resolved.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    reference = CTOEvidenceSourceReference(
        schema_version=SCHEMA_VERSION,
        source_id="historical_runtime_telemetry",
        producer="cto_review_collector",
        format_id="marketlense/runtime-telemetry/1.0",
        path=(
            _relative_reference_path(resolved, repository_root, digest)
            if resolved.resolve().is_relative_to(repository_root.resolve())
            else resolved.name
        ),
        sha256=digest,
        tested_repository_sha=None,
        role="supporting",
        status="verified",
        byte_count=len(content),
        observed_sha256=digest,
    )
    payload = _decode_json(content, "historical runtime telemetry")
    metrics: list[CTOEvidenceMetric] = []
    if isinstance(payload, dict):
        for key, record in payload.items():
            if key == "schema_version" or not isinstance(record, dict):
                continue
            status = _telemetry_status(record.get("status"))
            values = record.get("values")
            flattened = _flatten_numeric(values if isinstance(values, dict) else {})
            source_status = status
            for name, value in flattened.items():
                metrics.append(
                    _metric(
                        f"historical.{_metric_segment(key)}.{name}",
                        value if source_status != "unavailable" else None,
                        reference.source_id,
                        source_ids=(reference.source_id,),
                        status="partial"
                        if source_status == "partial"
                        else "observed"
                        if source_status == "available"
                        else "unavailable",
                        unit=_unit(name),
                        semantics=(
                            "Historical accumulated system state; excluded from "
                            "all run denominators and totals."
                        ),
                    )
                )
            if not flattened:
                metrics.append(
                    _metric(
                        f"historical.{_metric_segment(key)}",
                        None,
                        reference.source_id,
                        source_ids=(reference.source_id,),
                        status="unavailable",
                        unit="unavailable",
                        limitations=(
                            "No scalar historical value was retained for this "
                            "metric group.",
                        ),
                    )
                )
    metric_status: Literal["available", "partial", "unavailable"] = (
        "available"
        if any(item.status == "observed" for item in metrics)
        else "partial"
        if metrics
        else "unavailable"
    )
    limitations = (
        "Historical SQLite and artifact totals are context only and are not "
        "attributed to any declared workload run.",
    )
    return reference, CTOEvidenceHistoricalState(
        schema_version=SCHEMA_VERSION,
        status=metric_status,
        metrics=tuple(metrics),
        source_ids=(reference.source_id,),
        limitations=limitations,
    )


def _load_run_sources(
    run: CTOEvidenceRun, repository_root: Path
) -> tuple[
    list[_LoadedSource], tuple[CTOEvidenceSourceReference, ...], tuple[str, ...]
]:
    loaded: list[_LoadedSource] = []
    refs: list[CTOEvidenceSourceReference] = []
    issues: list[str] = []
    for reference in run.sources:
        try:
            path = _resolve_inside_root(
                repository_root / reference.path, repository_root
            )
        except FileNotFoundError:
            missing = replace(
                reference, status="missing", byte_count=None, observed_sha256=None
            )
            refs.append(missing)
            loaded.append(
                _LoadedSource(
                    missing,
                    None,
                    None,
                    f"Declared source {reference.source_id} is missing.",
                )
            )
            issues.append(f"Declared source {reference.source_id} is missing.")
            continue
        content = path.read_bytes()
        observed = hashlib.sha256(content).hexdigest()
        if observed != reference.sha256:
            mismatch = replace(
                reference,
                status="mismatch",
                byte_count=len(content),
                observed_sha256=observed,
            )
            refs.append(mismatch)
            loaded.append(
                _LoadedSource(
                    mismatch,
                    None,
                    path,
                    f"Declared source {reference.source_id} hash does not match.",
                )
            )
            issues.append(f"Declared source {reference.source_id} hash does not match.")
            continue
        verified = replace(
            reference,
            status="verified",
            byte_count=len(content),
            observed_sha256=observed,
        )
        refs.append(verified)
        try:
            payload = _decode_json(content, f"source {reference.source_id}")
        except ValueError:
            loaded.append(
                _LoadedSource(
                    verified,
                    None,
                    path,
                    f"Declared source {reference.source_id} is not valid JSON.",
                )
            )
            issues.append(f"Declared source {reference.source_id} is not valid JSON.")
            continue
        loaded.append(_LoadedSource(verified, payload, path))
    return loaded, tuple(refs), tuple(issues)


def _embedded_tested_sha(
    format_id: str,
    payload: object,
    *,
    comparison_side: str | None = None,
) -> str | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("tested_repository_sha"), str):
        return str(payload["tested_repository_sha"]).lower()
    if isinstance(payload.get("tested_sha"), str):
        return str(payload["tested_sha"]).lower()
    if format_id == FORMAT_FROZEN_COHORT and isinstance(payload.get("git_sha"), str):
        return str(payload["git_sha"]).lower()
    if format_id == FORMAT_ACQUISITION:
        attempts = payload.get("attempts")
        shas = (
            {
                str(item.get("tested_commit")).lower()
                for item in attempts
                if isinstance(item, dict) and isinstance(item.get("tested_commit"), str)
            }
            if isinstance(attempts, list)
            else set()
        )
        if len(shas) == 1:
            return next(iter(shas))
    if format_id == FORMAT_FILE_SEARCH:
        cohorts = payload.get("cohorts")
        selected = (
            cohorts.get(comparison_side or "candidate")
            if isinstance(cohorts, dict)
            else None
        )
        if isinstance(selected, dict) and isinstance(selected.get("git_sha"), str):
            return str(selected["git_sha"]).lower()
    if format_id == FORMAT_CONCURRENCY and isinstance(payload.get("tested_head"), str):
        return str(payload["tested_head"]).lower()
    if format_id == FORMAT_REUSE and isinstance(
        payload.get("implementation_commit"), str
    ):
        return str(payload["implementation_commit"]).lower()
    if format_id == FORMAT_HUMAN_REVIEW and isinstance(
        payload.get("reviewed_producer_build_identity"), str
    ):
        build_identity = str(payload["reviewed_producer_build_identity"]).lower()
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", build_identity):
            return build_identity
    if format_id == FORMAT_ARTIFACT_DAG:
        implementation = payload.get("implementation")
        side_data = payload.get("before" if comparison_side == "baseline" else "after")
        if comparison_side == "baseline":
            baseline_sha = (
                side_data.get("implementation_commit")
                if isinstance(side_data, dict)
                else None
            )
            if not isinstance(baseline_sha, str) and isinstance(implementation, dict):
                baseline_sha = implementation.get("base_commit")
            return str(baseline_sha).lower() if isinstance(baseline_sha, str) else None
        candidate_sha = (
            implementation.get("dag_commit")
            if isinstance(implementation, dict)
            else None
        )
        if not isinstance(candidate_sha, str) and isinstance(side_data, dict):
            candidate_sha = side_data.get("implementation_commit")
        return str(candidate_sha).lower() if isinstance(candidate_sha, str) else None
    if format_id == FORMAT_WORDPRESS and isinstance(
        payload.get("producer_commit"), str
    ):
        return str(payload["producer_commit"]).lower()
    if format_id == FORMAT_PROVIDER_CRITICAL_PATH and isinstance(
        payload.get("implementation_commit"), str
    ):
        return str(payload["implementation_commit"]).lower()
    return None


def _manifest_run_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        raise ValueError("run manifest must be a JSON object")
    if "run" not in payload:
        return payload
    if (
        set(payload) != {"schema_version", "run"}
        or payload.get("schema_version") != SCHEMA_VERSION
    ):
        raise ValueError("run manifest wrapper has unexpected fields or schema version")
    return payload["run"]


def _project_subject_outcomes_from_rows(
    rows: object,
    run: CTOEvidenceRun,
    result: _SourceProjection,
    *,
    identity_key: str,
    outcome_builder: Callable[[dict[str, Any]], str | None],
) -> None:
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(identity_key), str):
            continue
        subject = _subject_for_identity(run, _hash_identity(str(row[identity_key])))
        if subject is None:
            result.invalid = True
            continue
        outcome = outcome_builder(row)
        if outcome is not None:
            result.subject_outcomes[subject.subject_id] = outcome
            result.outcome_counts[outcome] += 1


def _subject_outcomes_from_rows(
    rows: object,
    run: CTOEvidenceRun,
    result: _SourceProjection,
    *,
    identity_key: str,
    outcome_builder: Callable[[dict[str, Any]], str | None] | None = None,
) -> None:
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = row.get(identity_key)
        if not isinstance(identity, str):
            continue
        subject = _subject_for_identity(
            run, identity if _SHA_RE.fullmatch(identity) else _hash_identity(identity)
        )
        if subject is None:
            result.invalid = True
            result.limitations.append(
                "Retained subject identity does not match the declared set."
            )
            continue
        outcome = (
            outcome_builder(row)
            if outcome_builder
            else _safe_outcome(row.get("outcome"))
        )
        if outcome is not None:
            result.subject_outcomes[subject.subject_id] = outcome
            result.outcome_counts[outcome] += 1


def _generic_attempts(
    rows: object,
    run: CTOEvidenceRun,
    source_id: str,
    result: _SourceProjection,
) -> None:
    if not isinstance(rows, list):
        return
    subject_by_hash = {item.identity_sha256: item for item in run.subjects}
    for row in rows:
        if not isinstance(row, dict):
            result.invalid = True
            continue
        identity = row.get("subject_identity_sha256")
        subject = (
            subject_by_hash.get(str(identity)) if isinstance(identity, str) else None
        )
        if subject is None:
            result.invalid = True
            continue
        kind = row.get("kind")
        outcome = row.get("outcome")
        if kind not in {
            "initial_execution",
            "deterministic_recovery",
            "structured_output_recovery",
            "evidence_claim_reuse",
            "semantic_repair",
            "targeted_regeneration",
            "workflow_retry",
            "operator_retry",
            "manual_intervention",
            "abstention",
            "terminal_failure",
        } or outcome not in {"success", "failed", "abstained", "not_evaluated"}:
            result.invalid = True
            continue
        number = row.get("attempt_number")
        parent = row.get("parent_attempt_number")
        if (
            not _nonnegative_int(number)
            or number < 1
            or (parent is not None and not _nonnegative_int(parent))
        ):
            result.invalid = True
            continue
        result.attempts.append(
            CTOEvidenceAttempt(
                schema_version=SCHEMA_VERSION,
                subject_id=subject.subject_id,
                attempt_number=number,
                kind=cast(_AttemptKind, kind),
                outcome=cast(_AttemptOutcome, outcome),
                failure_code=_safe_code(row.get("failure_code")),
                parent_attempt_number=parent,
                operator_intervention=row.get("operator_intervention") is True,
                source_id=source_id,
            )
        )
    result.attempt_history_status = "observed"
    result.available_classes.add("attempt_history")


def _generic_reuse(
    rows: object,
    run: CTOEvidenceRun,
    source_id: str,
    result: _SourceProjection,
) -> None:
    _reuse_decisions_from_rows(rows, run, source_id, result)


def _reuse_decisions_from_rows(
    rows: object,
    run: CTOEvidenceRun,
    source_id: str,
    result: _SourceProjection,
) -> None:
    if not isinstance(rows, list):
        return
    subject_by_hash = {item.identity_sha256: item for item in run.subjects}
    for row in rows:
        if not isinstance(row, dict):
            result.invalid = True
            continue
        identity = row.get("subject_identity_sha256")
        subject = (
            subject_by_hash.get(str(identity)) if isinstance(identity, str) else None
        )
        if subject is None:
            result.invalid = True
            continue
        counts: dict[str, int | None] = {}
        valid = True
        for key in (
            "eligible_candidates",
            "reused_validations",
            "newly_executed_validations",
            "avoided_grounding_calls",
            "avoided_provider_calls",
        ):
            value = row.get(key)
            if value is not None and not _nonnegative_int(value):
                valid = False
                break
            counts[key] = value
        if not valid:
            result.invalid = True
            continue
        result.reuse_decisions.append(
            CTOEvidenceReuseDecision(
                schema_version=SCHEMA_VERSION,
                subject_id=subject.subject_id,
                eligible_candidates=counts["eligible_candidates"],
                reused_validations=counts["reused_validations"],
                newly_executed_validations=counts["newly_executed_validations"],
                avoided_grounding_calls=counts["avoided_grounding_calls"],
                avoided_provider_calls=counts["avoided_provider_calls"],
                fallback_reason_code=_safe_code(row.get("fallback_reason_code")),
                source_id=source_id,
            )
        )
    result.reuse_status = "observed"
    result.available_classes.add("reuse")


def _subject_for_identity(
    run: CTOEvidenceRun, identity_hash: str
) -> CTOEvidenceSubject | None:
    return next(
        (item for item in run.subjects if item.identity_sha256 == identity_hash), None
    )


def _file_search_outcome(row: dict[str, Any]) -> str | None:
    validation = str(row.get("validation") or "").casefold()
    readiness = str(row.get("publication_readiness") or "").casefold()
    if validation in {"passed", "pass"} and readiness in {"passed", "pass"}:
        return "ready"
    if validation in {"failed", "fail"}:
        return "validation_failed"
    return "outcome_unavailable"


def _reliability_outcome(row: dict[str, Any]) -> str:
    if str(row.get("terminal_failure_code") or "").strip():
        return "terminal_failure"
    if row.get("validation") in {"failed", "fail"}:
        return "validation_failed"
    if row.get("publication_readiness") in {"pass", "passed"}:
        if row.get("awaiting_review") is True:
            return "awaiting_review"
        return "ready"
    if row.get("awaiting_review") is True:
        return "awaiting_review"
    return "outcome_unavailable"


def _outcome_metrics(
    subjects: tuple[CTOEvidenceSubject, ...],
    outcomes: Counter[str],
    source_ids: tuple[str, ...],
) -> list[CTOEvidenceMetric]:
    metric_source_ids = tuple(dict.fromkeys(source_ids))
    metrics = [
        _metric(
            "subjects.denominator",
            len(subjects),
            metric_source_ids[0]
            if metric_source_ids
            else "historical_runtime_telemetry",
            source_ids=metric_source_ids,
            unit="subjects",
            semantics=(
                "Declared immutable subject denominator; historical state is excluded."
            ),
        )
    ]
    for outcome, count in sorted(outcomes.items()):
        metrics.append(
            _metric(
                f"outcomes.{outcome}.count",
                count,
                metric_source_ids[0]
                if metric_source_ids
                else "historical_runtime_telemetry",
                source_ids=metric_source_ids,
                unit="subjects",
            )
        )
    return metrics


def _add_unavailable_subject_resources(
    run: CTOEvidenceRun,
    projection: _SourceProjection,
    subjects: tuple[CTOEvidenceSubject, ...],
) -> None:
    unavailable_metrics = {
        "resource.provider_calls": "calls",
        "resource.input_tokens": "tokens",
        "resource.output_tokens": "tokens",
        "resource.reasoning_tokens": "tokens",
        "resource.cost_usd": "USD",
        "performance.wall_seconds": "seconds",
        "performance.queue_wait_seconds": "seconds",
    }
    existing = {(item.metric_id, item.subject_id) for item in projection.metrics}
    source_id = (
        run.sources[0].source_id if run.sources else "historical_runtime_telemetry"
    )
    for subject in subjects:
        for metric_id, unit in unavailable_metrics.items():
            if (metric_id, subject.subject_id) in existing:
                continue
            projection.metrics.append(
                _metric(
                    metric_id,
                    None,
                    source_id,
                    status="unavailable",
                    unit=unit,
                    subject_id=subject.subject_id,
                    limitations=("No authoritative per-subject value is retained.",),
                )
            )


def _evaluate_criteria(
    run: CTOEvidenceRun, metrics: list[CTOEvidenceMetric]
) -> tuple[CTOEvidenceCriterion, ...]:
    by_id: dict[str, CTOEvidenceMetric] = {}
    conflicting_ids: set[str] = set()
    for metric in metrics:
        if metric.subject_id is not None:
            continue
        if metric.metric_id in by_id:
            prior = by_id[metric.metric_id]
            if prior.status != metric.status or prior.value != metric.value:
                conflicting_ids.add(metric.metric_id)
                by_id.pop(metric.metric_id)
        else:
            if metric.metric_id not in conflicting_ids:
                by_id[metric.metric_id] = metric
    evaluated: list[CTOEvidenceCriterion] = []
    for criterion in run.criteria:
        if criterion.stage is not None and criterion.stage in run.stages_out_of_scope:
            evaluated.append(
                replace(criterion, actual_value=None, disposition="not_evaluated")
            )
            continue
        selected_metric = by_id.get(criterion.metric_id)
        if criterion.metric_id in conflicting_ids:
            evaluated.append(
                replace(
                    criterion, actual_value=None, disposition="insufficient_evidence"
                )
            )
            continue
        if (
            selected_metric is None
            or selected_metric.value is None
            or selected_metric.status in {"unavailable", "not_applicable"}
        ):
            evaluated.append(
                replace(
                    criterion, actual_value=None, disposition="insufficient_evidence"
                )
            )
            continue
        if criterion.required and selected_metric.status == "partial":
            evaluated.append(
                replace(
                    criterion,
                    actual_value=selected_metric.value,
                    disposition="insufficient_evidence",
                )
            )
            continue
        passed = _compare_values(
            selected_metric.value, criterion.operator, criterion.expected_value
        )
        evaluated.append(
            replace(
                criterion,
                actual_value=selected_metric.value,
                disposition="pass" if passed else "fail",
            )
        )
    return tuple(evaluated)


def _project_comparison(
    comparison: CTOEvidenceComparison | None, sources: dict[str, object]
) -> CTOEvidenceComparison | None:
    if comparison is None:
        return None
    baseline_payload = sources.get(comparison.baseline_source_id)
    candidate_payload = sources.get(comparison.candidate_source_id)
    if not isinstance(baseline_payload, dict) or not isinstance(
        candidate_payload, dict
    ):
        return replace(comparison, status="unavailable", metric_deltas=())
    baseline = _select_path(baseline_payload, comparison.baseline_selector)
    candidate = _select_path(candidate_payload, comparison.candidate_selector)
    before = _flatten_numeric(baseline)
    after = _flatten_numeric(candidate)
    deltas = []
    for name in sorted(set(before) & set(after)):
        left, right = before[name], after[name]
        if isinstance(left, bool) or isinstance(right, bool):
            continue
        deltas.append(
            _metric(
                f"comparison.{comparison.comparison_id}.{name}.delta",
                float(right) - float(left),
                comparison.candidate_source_id,
                source_ids=(
                    comparison.baseline_source_id,
                    comparison.candidate_source_id,
                ),
                unit=_unit(name),
                semantics=(
                    "Candidate minus baseline; a before/after delta does not "
                    "establish causal attribution."
                ),
                limitations=comparison.limitations,
            )
        )
    limitations = comparison.limitations
    if not deltas:
        limitations = (
            *limitations,
            "No shared numeric measures were retained for this comparison.",
        )
    return replace(
        comparison,
        status="compatible" if deltas else "unavailable",
        metric_deltas=tuple(deltas),
        limitations=tuple(_unique_text(limitations)),
        causal_attribution="not_established",
    )


def _executive_summary(
    *,
    run: CTOEvidenceRun | None,
    run_evidence: CTOEvidenceRunEvidence | None,
    historical_state: CTOEvidenceHistoricalState,
    completeness: str,
    disposition: str,
    limitations: tuple[str, ...],
) -> CTOEvidenceExecutiveSummary:
    criteria = run_evidence.criteria if run_evidence is not None else ()
    counts = CTOEvidenceCriterionCounts(
        schema_version=SCHEMA_VERSION,
        pass_count=sum(
            item.disposition == "pass" for item in criteria if item.required
        ),
        fail_count=sum(
            item.disposition == "fail" for item in criteria if item.required
        ),
        not_evaluated_count=sum(
            item.disposition == "not_evaluated" for item in criteria if item.required
        ),
        insufficient_evidence_count=sum(
            item.disposition == "insufficient_evidence"
            for item in criteria
            if item.required
        ),
    )
    metrics = run_evidence.metrics if run_evidence is not None else ()
    key_metrics = _executive_key_metrics(metrics)
    recovery_count: int | None = None
    reuse_count: int | None = None
    avoided_provider_calls: int | None = None
    if run_evidence is not None and run_evidence.attempts:
        recovery_count = sum(
            item.kind != "initial_execution" for item in run_evidence.attempts
        )
    if run_evidence is not None:
        if run_evidence.reuse_decisions:
            reused_values = [
                item.reused_validations for item in run_evidence.reuse_decisions
            ]
            avoided_values = [
                item.avoided_provider_calls for item in run_evidence.reuse_decisions
            ]
            if all(value is not None for value in reused_values):
                reuse_count = sum(value for value in reused_values if value is not None)
            if all(value is not None for value in avoided_values):
                avoided_provider_calls = sum(
                    value for value in avoided_values if value is not None
                )
        else:
            reuse_count = _summary_metric_sum(metrics, {"reuse.reused_validations"})
            avoided_provider_calls = _summary_metric_sum(
                metrics, {"reuse.avoided_provider_calls"}
            )
            if avoided_provider_calls is None:
                avoided_components = {
                    "reuse.avoided_grounding_calls",
                    "reuse.avoided_semantic_calls",
                }
                if all(
                    any(
                        item.metric_id == metric_id
                        and item.status in {"observed", "partial"}
                        and isinstance(item.value, (int, float))
                        and not isinstance(item.value, bool)
                        for item in metrics
                    )
                    for metric_id in avoided_components
                ):
                    avoided_provider_calls = _summary_metric_sum(
                        metrics, avoided_components
                    )
    outcomes = run_evidence.outcomes if run_evidence is not None else ()
    quality = run_evidence.quality_dimensions if run_evidence is not None else ()
    actions = run_evidence.external_actions if run_evidence is not None else ()
    return CTOEvidenceExecutiveSummary(
        schema_version=SCHEMA_VERSION,
        mode="declared_run" if run is not None else "historical_system_snapshot",
        run_id=run.run_id if run else None,
        run_type=run.run_type if run else None,
        objective=run.objective if run else None,
        tested_repository_sha=run.tested_repository_sha if run else None,
        subject_count=len(run.subjects) if run is not None else None,
        required_criteria=counts,
        outcomes=outcomes,
        key_metrics=key_metrics,
        recovery_attempt_count=recovery_count,
        reused_validation_count=reuse_count,
        avoided_provider_call_count=avoided_provider_calls,
        quality_dimensions=quality,
        external_actions=actions,
        historical_metric_count=len(historical_state.metrics),
        completeness=completeness,  # type: ignore[arg-type]
        disposition=disposition,  # type: ignore[arg-type]
        limitations=limitations,
    )


def _executive_key_metrics(
    metrics: tuple[CTOEvidenceMetric, ...],
) -> tuple[CTOEvidenceMetric, ...]:
    def priority(metric: CTOEvidenceMetric) -> int | None:
        key = metric.metric_id.casefold()
        for rank, tokens in enumerate(
            (
                ("subjects.denominator",),
                ("wall",),
                ("duration",),
                ("cost",),
                ("provider_call", "grounding_call"),
                ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"),
                ("provider_active", "queue_wait", "provider_elapsed"),
                ("reused_validations", "avoided_"),
                ("quality", "readiness", "factual", "editorial"),
                ("file_search_call",),
                ("actual_write", "publication"),
            )
        ):
            if any(token in key for token in tokens):
                return rank
        return None

    selected = [
        (rank, metric.metric_id, metric)
        for metric in metrics
        if metric.subject_id is None and (rank := priority(metric)) is not None
    ]
    selected.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in selected[:20])


def _summary_metric_sum(
    metrics: tuple[CTOEvidenceMetric, ...], metric_ids: set[str]
) -> int | None:
    values = [
        float(item.value)
        for item in metrics
        if item.metric_id in metric_ids
        and item.status in {"observed", "partial"}
        and isinstance(item.value, (int, float))
        and not isinstance(item.value, bool)
    ]
    return round(sum(values)) if values else None


def _metric(
    metric_id: str,
    value: object,
    primary_source_id: str,
    *,
    source_ids: tuple[str, ...] = (),
    status: str | None = None,
    unit: str | None = None,
    numerator: float | None = None,
    denominator: float | None = None,
    semantics: str = "",
    limitations: tuple[str, ...] = (),
    subject_id: str | None = None,
) -> CTOEvidenceMetric:
    safe_id = _safe_metric_id(metric_id)
    inferred_status = status or ("observed" if _finite_scalar(value) else "unavailable")
    safe_value = value if _finite_scalar(value) else None
    return CTOEvidenceMetric(
        schema_version=SCHEMA_VERSION,
        metric_id=safe_id,
        status=inferred_status,  # type: ignore[arg-type]
        value=safe_value,  # type: ignore[arg-type]
        unit=unit or _unit(safe_id),
        source_ids=source_ids or (primary_source_id,),
        limitations=tuple(_unique_text(limitations)),
        numerator=numerator,
        denominator=denominator,
        measurement_semantics=semantics,
        subject_id=subject_id,
    )


def _flatten_numeric(
    value: object, prefix: str = "", *, depth: int = 0
) -> dict[str, int | float | bool]:
    flattened: dict[str, int | float | bool] = {}
    if not isinstance(value, dict) or depth > 5:
        return flattened
    for raw_key, nested in value.items():
        key = str(raw_key)
        normalized = key.casefold()
        if normalized in _DYNAMIC_SECTIONS or normalized in _IDENTITY_FIELDS:
            continue
        if any(
            token in normalized
            for token in (
                "report_id",
                "publisher",
                "source_identity",
                "run_root",
                "path",
                "title",
                "url",
            )
        ):
            continue
        path = f"{prefix}.{_metric_segment(key)}" if prefix else _metric_segment(key)
        if isinstance(nested, (int, float)) and math.isfinite(float(nested)):
            flattened[path] = nested
        elif isinstance(nested, dict):
            flattened.update(_flatten_numeric(nested, path, depth=depth + 1))
    return flattened


def _metric_segment(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", value).strip("_.:-")
    if not normalized or not normalized[0].isalpha():
        return "metric_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return normalized[:64]


def _safe_metric_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", value).strip("_.:-")
    if not normalized or not _METRIC_KEY_RE.fullmatch(normalized):
        normalized = "metric." + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    if len(normalized) > 128:
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        normalized = f"{normalized[:104]}.{digest}"
    return normalized


def _unit(value: str) -> str:
    key = value.casefold()
    if key.endswith("_usd") or "cost_usd" in key:
        return "USD"
    if "token" in key:
        return "tokens"
    if "provider_call" in key or key.endswith("_calls") or "grounding_call" in key:
        return "calls"
    if key.endswith("_seconds") or "duration_seconds" in key or "wall_seconds" in key:
        return "seconds"
    if key.endswith("_ms") or "_ms_" in key or "_wait_ms" in key or "latency_ms" in key:
        return "milliseconds"
    if "byte" in key:
        return "bytes"
    if "dpi" in key:
        return "DPI"
    if "rate" in key or "percent" in key or "_delta" in key and "score" not in key:
        return "ratio_or_delta"
    if "score" in key:
        return "score"
    if "concurr" in key:
        return "workers"
    if (
        "report" in key
        or "subject" in key
        or key.endswith("_count")
        or key.endswith("_rows")
    ):
        return "subjects_or_count"
    return "value"


def _semantics(metric_id: str) -> str:
    key = metric_id.casefold()
    if "provider_elapsed_ms_total" in key or "provider_elapsed_seconds_total" in key:
        return (
            "Summed provider elapsed work; aggregate work, not critical path or "
            "report wall time."
        )
    if (
        "interval_union" in key
        or "active_interval" in key
        or "provider_active_wall" in key
    ):
        return (
            "Producer-declared union of active provider intervals; not summed "
            "provider work."
        )
    if "exclusive_exposure" in key or "exclusive_provider" in key:
        return (
            "Producer-declared exclusive provider exposure; semantics are "
            "retained from its profiler."
        )
    if "queue_wait" in key:
        return "Queue wait is separate from provider-active time."
    if "non_provider_residual" in key:
        return "Non-provider residual is separate from provider elapsed work."
    if "wall" in key:
        return "Producer-declared wall-clock duration."
    return (
        "Producer-retained scalar measurement; no stronger causal interpretation "
        "is added."
    )


def _producer_limitations(format_id: str, payload: dict[str, Any]) -> list[str]:
    candidates: list[object] = []
    if format_id == FORMAT_ARTIFACT_DAG:
        comparison = payload.get("comparison")
        if isinstance(comparison, dict):
            candidates.extend(
                [
                    comparison.get("measurement_limit"),
                    comparison.get("cost_and_token_attribution_note"),
                ]
            )
    elif format_id == FORMAT_PROVIDER_CRITICAL_PATH:
        candidates.append(payload.get("path_regression"))
    elif format_id == FORMAT_CONCURRENCY:
        candidates.extend([payload.get("limitations"), payload.get("limitation")])
    elif format_id == FORMAT_FILE_SEARCH:
        candidates.append(
            payload.get("file_search_accounting", {}).get("basis")
            if isinstance(payload.get("file_search_accounting"), dict)
            else None
        )
    elif format_id == FORMAT_ACQUISITION:
        candidates.append(
            payload.get("consistency", {}).get("current_jsonl_sha256")
            if isinstance(payload.get("consistency"), dict)
            else None
        )
    result = []
    for item in candidates:
        if (
            isinstance(item, str)
            and 0 < len(item) <= 320
            and not re.search(
                r"https?://|\b[^\s@]+@[^\s@]+\.[^\s@]+", item, re.IGNORECASE
            )
        ):
            result.append(" ".join(item.split()))
        elif isinstance(item, list):
            result.extend(
                " ".join(value.split())
                for value in item
                if isinstance(value, str)
                and 0 < len(value) <= 320
                and not re.search(
                    r"https?://|\b[^\s@]+@[^\s@]+\.[^\s@]+", value, re.IGNORECASE
                )
            )
    return result


def _compare_values(actual: object, operator: str, expected: object) -> bool:
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "truthy":
        return bool(actual) is bool(expected)
    if isinstance(actual, bool) or isinstance(expected, bool):
        raise ValueError("ordered criteria require numeric values")
    if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
        raise ValueError("ordered criteria require numeric values")
    return {
        "gt": actual > expected,
        "gte": actual >= expected,
        "lt": actual < expected,
        "lte": actual <= expected,
    }[operator]


def _select_path(payload: object, selector: str) -> object:
    value = payload
    if selector in {"", "."}:
        return value
    for segment in selector.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


def _telemetry_status(value: object) -> str:
    return {
        "available": "available",
        "partial": "partial",
        "empty": "unavailable",
        "unavailable": "unavailable",
    }.get(str(value), "unavailable")


def _merge_status(current: str, incoming: str) -> str:
    rank = {"unavailable": 0, "not_applicable": 1, "partial": 2, "observed": 3}
    return incoming if rank.get(incoming, 0) > rank.get(current, 0) else current


def _safe_outcome(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", value.strip().casefold())[:64]
    return normalized if normalized and normalized[0].isalpha() else None


def _safe_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if _METRIC_KEY_RE.fullmatch(normalized) else None


def _nonnegative_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _finite_scalar(value: object) -> bool:
    return isinstance(value, (str, int, float, bool)) and (
        not isinstance(value, float) or math.isfinite(value)
    )


def _hash_identity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolve_inside_root(path: Path, repository_root: Path) -> Path:
    root = repository_root.resolve()
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "evidence source must resolve inside the repository root"
        ) from exc
    return resolved


def _relative_reference_path(path: Path, repository_root: Path, digest: str) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return f"external/{digest[:16]}/{path.name}"


def _decode_json(content: bytes, label: str) -> object:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc


def _malformed_projection(message: str) -> _SourceProjection:
    return _SourceProjection(invalid=True, limitations=[message])


def _unsupported_projection(source: _LoadedSource) -> _SourceProjection:
    return _SourceProjection(
        limitations=[
            "No projection adapter is registered for retained format "
            f"{source.reference.format_id}."
        ],
        unprojected_sources=True,
    )


def _unique_metrics(metrics: list[CTOEvidenceMetric]) -> list[CTOEvidenceMetric]:
    result: dict[tuple[str, str | None], list[CTOEvidenceMetric]] = {}
    for metric in metrics:
        key = (metric.metric_id, metric.subject_id)
        previous_values = result.get(key)
        if previous_values is None:
            result[key] = [metric]
            continue
        previous = previous_values[0]
        if (previous.status, previous.value, previous.unit) != (
            metric.status,
            metric.value,
            metric.unit,
        ):
            previous_values.append(metric)
            continue
        previous_values[0] = replace(
            previous,
            source_ids=tuple(dict.fromkeys((*previous.source_ids, *metric.source_ids))),
            limitations=tuple(
                _unique_text((*previous.limitations, *metric.limitations))
            ),
        )
    return [
        metric
        for key in sorted(
            result, key=lambda item: (item[0], item[1] is not None, item[1] or "")
        )
        for metric in result[key]
    ]


def _metric_conflicts(metrics: tuple[CTOEvidenceMetric, ...]) -> bool:
    values: dict[tuple[str, str | None], tuple[str, object, str]] = {}
    for metric in metrics:
        key = (metric.metric_id, metric.subject_id)
        current = (metric.status, metric.value, metric.unit)
        previous = values.get(key)
        if previous is not None and previous != current:
            return True
        values[key] = current
    return False


def _metric_reconciliation_errors(metrics: tuple[CTOEvidenceMetric, ...]) -> bool:
    per_subject: dict[str, list[float]] = {}
    aggregate: dict[str, float] = {}
    for metric in metrics:
        if not isinstance(metric.value, (int, float)) or isinstance(metric.value, bool):
            continue
        if metric.subject_id is None:
            aggregate[metric.metric_id] = float(metric.value)
        else:
            per_subject.setdefault(metric.metric_id, []).append(float(metric.value))
    return any(
        metric_id in aggregate
        and not math.isclose(
            sum(values), aggregate[metric_id], rel_tol=0.0, abs_tol=0.000001
        )
        for metric_id, values in per_subject.items()
    )


def _attempt_history_invalid(attempts: tuple[CTOEvidenceAttempt, ...]) -> bool:
    last_attempt: dict[str, int] = {}
    for attempt in attempts:
        previous = last_attempt.get(attempt.subject_id, 0)
        if attempt.attempt_number <= previous:
            return True
        if (
            attempt.parent_attempt_number is not None
            and attempt.parent_attempt_number > previous
        ):
            return True
        last_attempt[attempt.subject_id] = attempt.attempt_number
    return False


def _criterion_limit(criterion: CTOEvidenceCriterion) -> tuple[str, ...]:
    if criterion.disposition == "insufficient_evidence":
        return (
            f"Required measurement {criterion.metric_id} was unavailable or "
            f"partial for criterion {criterion.criterion_id}.",
        )
    return ()


def _unique_text(values: Any) -> list[str]:
    result = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = " ".join(value.split())
        if normalized and normalized not in result:
            result.append(normalized[:320])
    return result


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
