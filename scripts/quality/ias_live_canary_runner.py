"""Operational runner for one isolated live IAS first-attempt canary."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import yaml

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.drive import DriveFile
from src.contracts.llm_usage import LLMUsageRunSummaryRequest
from src.contracts.report_store import (
    ReportSourceRecordRequest,
    SourceIdentityObservation,
    SourceIdentityObservationRecordRequest,
)
from src.contracts.validation_run_manifest import (
    PreselectedFrozenValidationCohortSubmissionRequest,
    PreselectedFrozenValidationSource,
)
from src.contracts.workflow_control import SupervisorRunRequest
from src.orchestrators.admission_preflight_orchestrator import (
    AdmissionPreflightRequest,
    admission_configuration_hash,
    admission_policy_hash,
    pipeline_preflight_decision_hash,
    run_admission_preflight,
)
from src.orchestrators.ingest_orchestrator import (
    submit_preselected_frozen_validation_cohort,
)
from src.orchestrators.pipeline_preflight_orchestrator import preflight_report_pipeline
from src.orchestrators.workflow_supervisor_orchestrator import run_supervisor_once
from src.services.config_service import (
    build_ingest_settings,
    load_settings,
    load_workflow_control_settings,
    new_runtime_context,
)
from src.services.llm_usage_ledger_service import read_usage_run_summary
from src.services.report_store_service import (
    record_report_source,
    record_source_identity_observation,
)
from src.utils.errors import AppError


@dataclass(frozen=True)
class IsolatedCanaryRun:
    """Filesystem locations for one fresh, disposable canary execution."""

    root: Path
    config_path: Path
    mutable_paths: tuple[Path, ...]


_AUTOMATIC_REPAIR_DISPOSITIONS = {
    "targeted_repair",
    "full_rerun",
    "structured_output_repair",
    "queue_redelivery",
    "process_restart",
}


def prepare_isolated_canary_run(*, runs_root: Path) -> IsolatedCanaryRun:
    """Create a unique run root and config whose mutable paths stay within it."""

    root_parent = runs_root.resolve()
    root_parent.mkdir(parents=True, exist_ok=True)
    root = Path(
        tempfile.mkdtemp(prefix="ias-first-attempt-", dir=root_parent)
    ).resolve()
    config_path = root / "config" / "app.yaml"
    paths = {
        "canary_state_root": root,
        "output_dir": root / "output",
        "cache_dir": root / "cache",
        "state_db": root / "state" / "workflow.sqlite",
        "reports_db": root / "state" / "reports.sqlite",
        "signal_store_db": root / "state" / "signals.sqlite",
        "ingest_lock": root / "state" / "ingest.lock",
    }
    cost_paths = {
        "usage_db_path": root / "state" / "llm_usage.sqlite",
        "daily_path": root / "state" / "llm_cost_daily.json",
        "ledger_path": root / "state" / "llm_cost_ledger.jsonl",
    }
    mutable_paths = (
        paths["output_dir"],
        paths["cache_dir"],
        paths["state_db"],
        paths["reports_db"],
        paths["signal_store_db"],
        paths["ingest_lock"],
        cost_paths["usage_db_path"],
        cost_paths["daily_path"],
        cost_paths["ledger_path"],
        root / "output" / "browser_downloads",
        root / "output" / "publisher_inventory_discovery",
        root / "state" / "projection_cost_daily.json",
        root / "state" / "projection_cost_ledger.jsonl",
    )
    config = _isolated_config(root=root, paths=paths, cost_paths=cost_paths)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return IsolatedCanaryRun(
        root=root,
        config_path=config_path,
        mutable_paths=mutable_paths,
    )


def _isolated_config(
    *, root: Path, paths: dict[str, Path], cost_paths: dict[str, Path]
) -> dict[str, Any]:
    base_config_path = (
        Path(__file__).resolve().parents[2] / "src" / "config" / "app.yaml"
    )
    config = copy.deepcopy(yaml.safe_load(base_config_path.read_text(encoding="utf-8")))
    if not isinstance(config, dict):
        raise RuntimeError("Base application configuration must be a mapping")
    config["paths"] = {
        **dict(config.get("paths") or {}),
        **{name: str(path) for name, path in paths.items()},
        "publisher_profiles": str(
            base_config_path.parents[2]
            / "Wordpress"
            / "config"
            / "publisher-profiles.json"
        ),
        "category_mappings": str(base_config_path.with_name("category-mappings.yaml")),
        "html_tag_acronyms": str(base_config_path.with_name("html-tag-acronyms.yaml")),
        "cover_styles": str(base_config_path.with_name("cover-styles.yaml")),
    }
    config["analysis"] = {
        **dict(config.get("analysis") or {}),
        "cost_ledger_path": str(cost_paths["ledger_path"]),
    }
    config["cost"] = {
        **dict(config.get("cost") or {}),
        **{name: str(path) for name, path in cost_paths.items()},
        "pricing_path": str(base_config_path.with_name("llm-costs.yaml")),
    }
    config["browser_download"] = {
        **dict(config.get("browser_download") or {}),
        "output_dir": str(root / "output" / "browser_downloads"),
        "identity_config_path": str(
            base_config_path.with_name("browser_download_identity.yaml")
        ),
    }
    config["publisher_discovery"] = {
        **dict(config.get("publisher_discovery") or {}),
        "output_dir": str(root / "output" / "publisher_inventory_discovery"),
    }
    config["publish"] = {
        **dict(config.get("publish") or {}),
        "projection_daily_path": str(root / "state" / "projection_cost_daily.json"),
        "projection_ledger_path": str(root / "state" / "projection_cost_ledger.jsonl"),
    }
    workflow_control = dict(config.get("workflow_control") or {})
    workflow_control["supervisor"] = {
        **dict(workflow_control.get("supervisor") or {}),
        "enabled": True,
        "worker_batches_enabled": True,
    }
    config["workflow_control"] = workflow_control
    return config


def run_ias_first_attempt_canary(
    *,
    runs_root: Path,
    source_path: Path,
    max_duration_seconds: int = 7_200,
) -> dict[str, Any]:
    """Run one IAS source through the normal frozen-cohort queue exactly once."""
    return _run_preselected_canary(
        runs_root=runs_root,
        source_path=source_path,
        source_metadata={
            "source_domain": "integralads.com",
            "report_name": "IAS Industry Pulse Report 2026",
            "landing_page_url": "https://integralads.com/insider/industry-pulse-report/",
            "source_page_url": "https://integralads.com/insider/",
            "publisher_name": "Integral Ad Science",
            "downloaded_at_utc": "2026-09-12T00:00:00Z",
        },
        report_prefix="ias",
        task_id="ias_first_attempt_live_canary",
        missing_source_code="ias_canary_source_missing",
        admission_code_prefix="ias_canary_admission",
        runner_defect_code="ias_canary_runner_defect",
        max_duration_seconds=max_duration_seconds,
    )


def run_first_attempt_canary(
    *,
    runs_root: Path,
    source_path: Path,
    source_metadata: dict[str, str] | None = None,
    max_duration_seconds: int = 7_200,
) -> dict[str, Any]:
    """Run one non-IAS source through the same one-attempt queue path."""
    return _run_preselected_canary(
        runs_root=runs_root,
        source_path=source_path,
        source_metadata=source_metadata or _local_source_metadata(source_path),
        report_prefix="cohort",
        task_id="frozen_reliability_cohort",
        missing_source_code="frozen_cohort_source_missing",
        admission_code_prefix="frozen_cohort_admission",
        runner_defect_code="frozen_cohort_runner_defect",
        max_duration_seconds=max_duration_seconds,
    )


def run_frozen_cohort_once(
    *,
    runs_root: Path,
    sources: list[dict[str, Any]],
    max_duration_seconds: int = 7_200,
) -> dict[str, Any]:
    """Submit one immutable retained cohort through the production queue once."""

    git_sha = _require_clean_git_sha()
    started_at = time.monotonic()
    run = prepare_isolated_canary_run(runs_root=runs_root)
    results = [_empty_result(run, started_at) for _ in sources]
    cohort_metrics: dict[str, Any] = {
        "cost_usd": None,
        "duration_seconds": None,
        "bounded_automatic_repair": None,
    }
    for result in results:
        result["git_sha"] = git_sha
    prepared_sources: list[PreselectedFrozenValidationSource] = []
    try:
        ctx = new_runtime_context(task_id="frozen_reliability_cohort")
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(
                schema_version="1.0",
                app_settings=load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
                    ctx,
                ),
            ),
            ctx,
        )
        _assert_empty_stores(run=run, settings=settings)
        for result, source in zip(results, sources, strict=True):
            source_path = Path(str(source["resolved_source_path"]))
            if not source_path.is_file():
                result["terminal_failure_code"] = "frozen_cohort_source_missing"
                continue
            source_hash = hashlib.md5(
                source_path.read_bytes(), usedforsecurity=False
            ).hexdigest()
            report_id = f"cohort-{source_hash[:20]}"
            result["report_id"] = report_id
            prepared_sources.append(
                PreselectedFrozenValidationSource(
                    schema_version="1.0",
                    report_id=report_id,
                    source_artifact_path=str(source_path.resolve()),
                    content_md5=source_hash,
                    source_domain=str(source["source_domain"]),
                    report_name=str(source["report_name"]),
                    landing_page_url=str(source["landing_page_url"]),
                    source_page_url=str(source["source_page_url"]),
                    publisher_name=str(source["publisher_name"]),
                    downloaded_at_utc=str(source["downloaded_at_utc"]),
                )
            )
        if len(prepared_sources) != len(results):
            raise AppError(
                code="frozen_cohort_submission_incomplete",
                message="Every frozen cohort member must be present before submission",
                retryable=False,
            )
        submission = submit_preselected_frozen_validation_cohort(
            PreselectedFrozenValidationCohortSubmissionRequest(
                schema_version="1.0",
                settings=settings,
                cohort_manifest=str(run.root / "cohort" / "source.json"),
                config_path=str(run.config_path),
                sources=tuple(prepared_sources),
            ),
            ctx,
        )
        decisions = {
            decision.file_id: decision for decision in submission.admission_decisions
        }
        for result in results:
            decision = decisions.get(str(result["report_id"]))
            if decision is None:
                result["terminal_failure_code"] = "frozen_cohort_admission_missing"
                continue
            result["admission_outcome"] = decision.outcome
            result["source_identity_id"] = decision.source_identity_id
            result["publisher_id"] = decision.publisher_id
        if submission.queue_submission is None:
            for result in results:
                if not result["terminal_failure_code"]:
                    result["terminal_failure_code"] = (
                        "frozen_cohort_admission_"
                        f"{result['admission_outcome'] or 'missing'}"
                    )
        else:
            queue_submission = submission.queue_submission
            root_workflow_id = str(queue_submission.root_workflow_id)
            for result in results:
                result["workflow_root_id"] = root_workflow_id
            _drain_report_paths(
                state_db=settings.state_db,
                usage_db_path=settings.usage_db_path,
                config_path=run.config_path,
                report_ids=tuple(str(result["report_id"]) for result in results),
                root_workflow_id=root_workflow_id,
                ctx=ctx,
                max_duration_seconds=max_duration_seconds,
            )
            for result in results:
                result.update(
                    _read_result(
                        settings=settings,
                        report_id=str(result["report_id"]),
                        validation_run_id=str(queue_submission.validation_run_id),
                        root_workflow_id=root_workflow_id,
                        ctx=ctx,
                    )
                )
            cohort_metrics.update(
                {
                    "model_provider_calls": results[0]["model_provider_calls"],
                    "input_tokens": results[0]["input_tokens"],
                    "output_tokens": results[0]["output_tokens"],
                    "cost_usd": results[0]["cost"],
                    "bounded_automatic_repair": any(
                        bool(result["bounded_automatic_repair"]) for result in results
                    ),
                    "operator_intervention_count": _cohort_operator_intervention_count(
                        state_db=settings.state_db,
                        root_workflow_id=root_workflow_id,
                    ),
                }
            )
    except AppError as exc:
        for result in results:
            if not result["terminal_failure_code"]:
                result["terminal_failure_code"] = exc.code
    except Exception:
        for result in results:
            if not result["terminal_failure_code"]:
                result["terminal_failure_code"] = "frozen_cohort_runner_defect"
    finally:
        cohort_metrics["duration_seconds"] = _finish_frozen_cohort_results(
            results, started_at, retain_member_duration=False
        )
        for result in results:
            # Usage and repair records are scoped to the one batch root workflow.
            # They cannot be attributed to an individual member without retained
            # report-specific telemetry, so never duplicate them into members.
            result.update(
                {
                    "bounded_automatic_repair": None,
                    "operator_intervention": None,
                    "model_provider_calls": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost": None,
                    "total_duration_seconds": None,
                    "metric_attribution": "unavailable",
                }
            )
        _write_result(run.root / "cohort_members.json", {"reports": results})
    return {
        "git_sha": git_sha,
        "run_directory": str(run.root),
        "reports": results,
        "cohort_metrics": cohort_metrics,
        "summary": summarize_frozen_cohort_results(
            results, cohort_metrics=cohort_metrics
        ),
    }


def _run_preselected_canary(
    *,
    runs_root: Path,
    source_path: Path,
    source_metadata: dict[str, str],
    report_prefix: str,
    task_id: str,
    missing_source_code: str,
    admission_code_prefix: str,
    runner_defect_code: str,
    max_duration_seconds: int,
) -> dict[str, Any]:
    """Isolate one source, then delegate processing to production orchestration."""

    started_at = time.monotonic()
    run = prepare_isolated_canary_run(runs_root=runs_root)
    result = _empty_result(run, started_at)
    try:
        if not source_path.is_file():
            result["terminal_failure_code"] = missing_source_code
            return result
        ctx = new_runtime_context(task_id=task_id)
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(
                schema_version="1.0",
                app_settings=load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
                    ctx,
                ),
            ),
            ctx,
        )
        _assert_empty_stores(run=run, settings=settings)
        source_hash = hashlib.md5(
            source_path.read_bytes(), usedforsecurity=False
        ).hexdigest()
        report_id = f"{report_prefix}-{source_hash[:20]}"
        result["report_id"] = report_id
        prepared = submit_preselected_frozen_validation_cohort(
            PreselectedFrozenValidationCohortSubmissionRequest(
                schema_version="1.0",
                settings=settings,
                cohort_manifest=str(run.root / "cohort" / "source.json"),
                config_path=str(run.config_path),
                sources=(
                    PreselectedFrozenValidationSource(
                        schema_version="1.0",
                        report_id=report_id,
                        source_artifact_path=str(source_path.resolve()),
                        content_md5=source_hash,
                        source_domain=source_metadata["source_domain"],
                        report_name=source_metadata["report_name"],
                        landing_page_url=source_metadata["landing_page_url"],
                        source_page_url=source_metadata["source_page_url"],
                        publisher_name=source_metadata["publisher_name"],
                        downloaded_at_utc=source_metadata["downloaded_at_utc"],
                    ),
                ),
            ),
            ctx,
        )
        decision = prepared.admission_decisions[0]
        result["admission_outcome"] = decision.outcome
        result["source_identity_id"] = decision.source_identity_id
        result["publisher_id"] = decision.publisher_id
        if prepared.queue_submission is None:
            result["terminal_failure_code"] = (
                f"{admission_code_prefix}_{decision.outcome}"
            )
            return result
        submission = prepared.queue_submission
        result["workflow_root_id"] = str(submission.root_workflow_id)
        _drain_report_path(
            state_db=settings.state_db,
            usage_db_path=settings.usage_db_path,
            config_path=run.config_path,
            report_id=report_id,
            root_workflow_id=str(submission.root_workflow_id),
            ctx=ctx,
            max_duration_seconds=max_duration_seconds,
        )
        result.update(
            _read_result(
                settings=settings,
                report_id=report_id,
                validation_run_id=str(submission.validation_run_id),
                root_workflow_id=str(submission.root_workflow_id),
                ctx=ctx,
            )
        )
    except AppError as exc:
        result["terminal_failure_code"] = exc.code
    except Exception:
        result["terminal_failure_code"] = runner_defect_code
    finally:
        result["total_duration_seconds"] = round(time.monotonic() - started_at, 3)
        _write_result(run.root / "result.json", result)
    return result


def _local_source_metadata(source_path: Path) -> dict[str, str]:
    return {
        "source_domain": "retained.local",
        "report_name": source_path.stem,
        "landing_page_url": source_path.resolve().as_uri(),
        "source_page_url": source_path.resolve().as_uri(),
        "publisher_name": "Retained local source",
        "downloaded_at_utc": "1970-01-01T00:00:00Z",
    }


def preflight_frozen_cohort_member(
    *, runs_root: Path, source_path: Path, source_metadata: dict[str, str]
) -> dict[str, Any]:
    """Component-only admission check; this is not end-to-end workflow validation."""
    started_at = time.monotonic()
    run = prepare_isolated_canary_run(runs_root=runs_root)
    result = _empty_result(run, started_at)
    result["validation_scope"] = "component_admission_preflight_not_end_to_end"
    try:
        if not source_path.is_file():
            result["terminal_failure_code"] = "frozen_cohort_source_missing"
            return result
        ctx = new_runtime_context(task_id="frozen_reliability_cohort_preflight")
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(
                schema_version="1.0",
                app_settings=load_settings(
                    ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
                    ctx,
                ),
            ),
            ctx,
        )
        _assert_empty_stores(run=run, settings=settings)
        source_hash = hashlib.md5(
            source_path.read_bytes(), usedforsecurity=False
        ).hexdigest()
        report_id = f"cohort-{source_hash[:20]}"
        result["report_id"] = report_id
        observation = _record_frozen_source_identity(
            settings=settings,
            source_hash=source_hash,
            metadata=source_metadata,
            ctx=ctx,
        )
        result["source_identity_id"] = observation.source_identity_id
        result["publisher_id"] = observation.publisher_id
        runtime_preflight = preflight_report_pipeline(settings, ctx)
        admission = run_admission_preflight(
            AdmissionPreflightRequest(
                file=DriveFile(
                    schema_version="1.0",
                    file_id=report_id,
                    name=source_path.name,
                    modified_time=None,
                    md5_checksum=source_hash,
                    mime_type="application/pdf",
                ),
                source_artifact_path=str(source_path.resolve()),
                settings=settings,
                runtime_preflight_passed=runtime_preflight.passed,
                runtime_preflight_hash=pipeline_preflight_decision_hash(
                    runtime_preflight
                ),
                configuration_hash=admission_configuration_hash(settings),
                policy_hash=admission_policy_hash(settings),
                known_source_identities={},
                known_title_keys={},
            ),
            ctx,
        )
        result["admission_outcome"] = admission.decision.outcome
        if not admission.admitted:
            result["terminal_failure_code"] = (
                f"frozen_cohort_admission_{admission.decision.outcome}"
            )
        else:
            result["final_state"] = "preflight_admitted"
    except AppError as exc:
        result["terminal_failure_code"] = exc.code
    finally:
        result["total_duration_seconds"] = round(time.monotonic() - started_at, 3)
        _write_result(run.root / "preflight.json", result)
    return result


def _record_frozen_source_identity(*, settings, source_hash: str, metadata, ctx):
    """Persist retained discovery metadata through the production identity boundary."""
    required = (
        "source_domain",
        "report_name",
        "landing_page_url",
        "source_page_url",
        "publisher_name",
        "downloaded_at_utc",
    )
    if any(not str(metadata.get(name) or "").strip() for name in required):
        raise AppError(
            code="frozen_cohort_source_provenance_invalid",
            message="Frozen cohort source metadata is incomplete",
            retryable=False,
        )
    source = record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            source_domain=str(metadata["source_domain"]),
            report_name=str(metadata["report_name"]),
            landing_page_url=str(metadata["landing_page_url"]),
            source_page_url=str(metadata["source_page_url"]),
            downloaded_at_utc=str(metadata["downloaded_at_utc"]),
            md5=source_hash,
            publisher_name=str(metadata["publisher_name"]),
        ),
        ctx,
    )
    return record_source_identity_observation(
        SourceIdentityObservationRecordRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            observation=SourceIdentityObservation(
                schema_version="1.0",
                source_record_id=source.record_id,
                canonical_title=str(metadata["report_name"]),
                title_evidence_locator="frozen_cohort_manifest:report_name",
                publisher_id=str(metadata["publisher_name"]),
                publisher_name=str(metadata["publisher_name"]),
                canonical_landing_page_url=str(metadata["landing_page_url"]),
                acquired_artifact_url=str(metadata["landing_page_url"]),
                source_page_url=str(metadata["source_page_url"]),
                retrieved_at_utc=str(metadata["downloaded_at_utc"]),
                acquisition_route="frozen_cohort_retained_discovery",
                content_hash=f"md5:{source_hash}",
                resolution_method="frozen_cohort_retained_discovery",
                identity_confidence="high",
            ),
        ),
        ctx,
    ).resolution


def _assert_empty_stores(*, run: IsolatedCanaryRun, settings) -> None:
    expected = {
        Path(settings.state_db),
        Path(settings.reports_db),
        Path(settings.usage_db_path),
        Path(settings.cost_ledger_path),
        Path(settings.cost_daily_path),
        *run.mutable_paths,
    }
    nonempty = [str(path) for path in expected if path.exists() and path.is_file()]
    output_entries = [
        str(path)
        for path in (Path(settings.output_dir), Path(settings.cache_dir))
        if path.exists() and any(path.iterdir())
    ]
    if nonempty or output_entries:
        raise AppError(
            code="ias_canary_mutable_state_not_empty",
            message="Fresh IAS canary root contains mutable state before submission",
            retryable=False,
            context={"path_count": len(nonempty) + len(output_entries)},
        )


def _drain_report_path(
    *,
    state_db: str,
    usage_db_path: str,
    config_path: Path,
    report_id: str,
    root_workflow_id: str,
    ctx,
    max_duration_seconds: int,
) -> None:
    _drain_report_paths(
        state_db=state_db,
        usage_db_path=usage_db_path,
        config_path=config_path,
        report_ids=(report_id,),
        root_workflow_id=root_workflow_id,
        ctx=ctx,
        max_duration_seconds=max_duration_seconds,
    )


def _drain_report_paths(
    *,
    state_db: str,
    usage_db_path: str,
    config_path: Path,
    report_ids: tuple[str, ...],
    root_workflow_id: str,
    ctx,
    max_duration_seconds: int,
) -> None:
    """Drive the canonical supervisor until every submitted report is terminal."""

    control = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), ctx
    )
    deadline = time.monotonic() + max(1, max_duration_seconds)
    worker_id = f"ias-live-canary:{root_workflow_id}"
    while time.monotonic() < deadline:
        supervisor = run_supervisor_once(
            SupervisorRunRequest(
                schema_version="1.0",
                state_db=state_db,
                usage_db_path=usage_db_path,
                worker_id=worker_id,
                now_utc=datetime.now(timezone.utc).isoformat(),
                settings=control.supervisor,
            ),
            ctx,
        )
        states = {
            report_id: _queue_terminal_state(
                state_db=state_db,
                report_id=report_id,
                root_workflow_id=root_workflow_id,
            )
            for report_id in report_ids
        }
        if all(state in {"awaiting_review", "failed"} for state in states.values()):
            return
        if supervisor.completed_job_count == 0:
            time.sleep(1)


def _queue_terminal_state(
    *, state_db: str, report_id: str, root_workflow_id: str
) -> str:
    with sqlite3.connect(state_db) as conn:
        readiness = conn.execute(
            """
            SELECT readiness.readiness_status
            FROM workflow_publication_readiness AS readiness
            JOIN workflow_jobs AS job
              ON job.queue_name='publication_readiness'
             AND job.output_content_hash=readiness.package_checksum
            WHERE job.report_id=? AND job.root_workflow_id=? AND job.status='succeeded'
            ORDER BY job.completed_at_utc DESC LIMIT 1
            """,
            (report_id, root_workflow_id),
        ).fetchone()
        if readiness and str(readiness[0]) == "awaiting_review":
            return "awaiting_review"
        if readiness:
            return "failed"
        failure = conn.execute(
            """
            SELECT 1 FROM workflow_jobs
            WHERE report_id=? AND root_workflow_id=?
              AND queue_name IN ('source_ingest','report_selection','report_analysis',
                                 'report_render','publication_readiness')
              AND status IN ('dead_letter','blocked','budget_deferred','cancelled')
            LIMIT 1
            """,
            (report_id, root_workflow_id),
        ).fetchone()
    return "failed" if failure else "running"


def _read_result(
    *, settings, report_id: str, validation_run_id: str, root_workflow_id: str, ctx
) -> dict[str, Any]:
    with sqlite3.connect(settings.state_db) as conn:
        readiness_job = conn.execute(
            """
            SELECT job.status, job.error_code, payload.payload_json
            FROM workflow_jobs AS job
            LEFT JOIN workflow_jobs AS payload ON payload.job_id=job.job_id
            WHERE job.queue_name='publication_readiness'
              AND job.report_id=? AND job.root_workflow_id=?
            ORDER BY job.created_at_utc DESC LIMIT 1
            """,
            (report_id, root_workflow_id),
        ).fetchone()
        status = _queue_terminal_state(
            state_db=settings.state_db,
            report_id=report_id,
            root_workflow_id=root_workflow_id,
        )
        operator_intervention = bool(
            conn.execute(
                """
                SELECT 1 FROM workflow_job_transitions AS transition
                JOIN workflow_jobs AS job ON job.job_id=transition.job_id
                WHERE job.root_workflow_id=?
                  AND transition.reason IN ('operator_requeue','queue-requeue')
                LIMIT 1
                """,
                (root_workflow_id,),
            ).fetchone()
        )
        automatic_queue_repair = bool(
            conn.execute(
                """
                SELECT 1 FROM workflow_job_attempts AS attempts
                JOIN workflow_jobs AS job ON job.job_id=attempts.job_id
                WHERE job.root_workflow_id=? AND attempts.outcome='retry_wait'
                LIMIT 1
                """,
                (root_workflow_id,),
            ).fetchone()
        )
        failure = conn.execute(
            """
            SELECT error_code FROM workflow_jobs
            WHERE report_id=? AND root_workflow_id=? AND error_code<>''
            ORDER BY updated_at_utc LIMIT 1
            """,
            (report_id, root_workflow_id),
        ).fetchone()
    with sqlite3.connect(settings.reports_db) as conn:
        attempts = int(
            conn.execute(
                """
                SELECT COUNT(DISTINCT attempt_number)
                FROM validation_run_entity_attempts
                WHERE validation_run_id=? AND report_id=?
                """,
                (validation_run_id, report_id),
            ).fetchone()[0]
        )
        bounded_manifest_repair = bool(
            conn.execute(
                """
                SELECT 1 FROM validation_run_stage_records
                WHERE validation_run_id=? AND repair_disposition IN ({}) LIMIT 1
                """.format(",".join("?" for _ in _AUTOMATIC_REPAIR_DISPOSITIONS)),
                (validation_run_id, *sorted(_AUTOMATIC_REPAIR_DISPOSITIONS)),
            ).fetchone()
        )
    readiness_payload = _read_readiness_payload(readiness_job)
    usage = read_usage_run_summary(
        LLMUsageRunSummaryRequest(
            schema_version="1.0",
            db_path=settings.usage_db_path,
            run_id=root_workflow_id,
        ),
        ctx,
    )
    validation_pass = _validation_passed(Path(settings.output_dir))
    terminal_failure = ""
    final_state = status
    if status != "awaiting_review":
        # A bounded supervisor drain cannot leave a submitted member in a
        # non-terminal result. Preserve an observed queue failure when present;
        # otherwise make the elapsed bound explicit and typed.
        final_state = "failed"
        terminal_failure = str((failure or ("ias_canary_timeout",))[0])
    return {
        "workflow_attempt_count": attempts,
        "final_state": final_state,
        "awaiting_review": final_state == "awaiting_review",
        "bounded_automatic_repair": (
            bounded_manifest_repair
            or automatic_queue_repair
            or any(
                Path(settings.output_dir).rglob("regeneration_candidate_audit_*.json")
            )
        ),
        "operator_intervention": operator_intervention,
        "publication_readiness": (
            "pass" if readiness_payload.get("status") == "pass" else "fail"
        ),
        "validation": "pass" if validation_pass else "fail",
        "model_provider_calls": usage.call_count,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost": usage.estimated_cost_usd,
        "terminal_failure_code": terminal_failure,
    }


def _read_readiness_payload(row: tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        return {}
    try:
        payload = json.loads(str(row[2]))
        reference = str(payload.get("validation_reference") or "")
        return json.loads(Path(reference).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _cohort_operator_intervention_count(*, state_db: str, root_workflow_id: str) -> int:
    """Count retained manual requeues for the one submitted cohort workflow."""

    with sqlite3.connect(state_db) as conn:
        return int(
            conn.execute(
                """
                SELECT COUNT(*) FROM workflow_job_transitions AS transition
                JOIN workflow_jobs AS job ON job.job_id=transition.job_id
                WHERE job.root_workflow_id=?
                  AND transition.reason IN ('operator_requeue','queue-requeue')
                """,
                (root_workflow_id,),
            ).fetchone()[0]
        )


def _validation_passed(output_dir: Path) -> bool:
    reports = sorted(output_dir.rglob("validation.json"))
    if not reports:
        return False
    try:
        return (
            json.loads(reports[-1].read_text(encoding="utf-8")).get("status") == "pass"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _empty_result(run: IsolatedCanaryRun, started_at: float) -> dict[str, Any]:
    del started_at
    return {
        "git_sha": _git_sha(),
        "report_id": "",
        "source_identity_id": "",
        "publisher_id": "",
        "workflow_root_id": "",
        "workflow_attempt_count": 0,
        "admission_outcome": "",
        "isolated_fresh_state": True,
        "final_state": "failed",
        "awaiting_review": False,
        "bounded_automatic_repair": False,
        "operator_intervention": False,
        "publication_readiness": "fail",
        "validation": "fail",
        "model_provider_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
        "total_duration_seconds": 0.0,
        "terminal_failure_code": "",
        "run_directory": str(run.root),
    }


def _finish_frozen_cohort_results(
    results: list[dict[str, Any]],
    started_at: float,
    *,
    retain_member_duration: bool = True,
) -> float:
    """Make every retained cohort member explicitly terminal before export."""

    duration = round(time.monotonic() - started_at, 3)
    for result in results:
        if result["final_state"] not in {"awaiting_review", "failed"}:
            result["final_state"] = "failed"
        if result["final_state"] == "failed" and not result["terminal_failure_code"]:
            result["terminal_failure_code"] = "frozen_cohort_terminal_outcome_missing"
        if retain_member_duration:
            result["total_duration_seconds"] = duration
    return duration


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() or "unknown"


def _require_clean_git_sha() -> str:
    """Refuse a measured cohort run unless its source revision is immutable."""

    sha = _git_sha()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    if (
        len(sha) != 40
        or any(character not in "0123456789abcdef" for character in sha)
        or dirty.returncode != 0
        or dirty.stdout.strip()
    ):
        raise AppError(
            code="frozen_cohort_git_worktree_dirty",
            message="Measured frozen cohort runs require a clean 40-character git SHA",
            retryable=False,
        )
    return sha


def _write_result(path: Path, result: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def summarize_frozen_cohort_results(
    results: list[dict[str, Any]],
    *,
    cohort_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize every frozen admitted member without changing its denominator."""

    count = len(results)
    denominator = max(1, count)
    admitted = [
        item
        for item in results
        if item.get("admission_outcome", "admitted") == "admitted"
    ]
    workflow_denominator = max(1, len(admitted))
    costs = [float(item.get("cost") or 0.0) for item in results]
    durations = [float(item.get("total_duration_seconds") or 0.0) for item in results]
    failures = [
        str(item.get("terminal_failure_code") or "")
        for item in results
        if str(item.get("terminal_failure_code") or "")
    ]
    terminal_states = {"awaiting_review", "failed"}
    missing_terminal_report_ids = sorted(
        str(item.get("report_id") or "")
        for item in results
        if str(item.get("final_state") or "") not in terminal_states
    )
    pareto = {code: failures.count(code) for code in sorted(set(failures))}
    summary = {
        "report_count": count,
        "terminal_outcome_complete": not missing_terminal_report_ids,
        "missing_terminal_report_count": len(missing_terminal_report_ids),
        "missing_terminal_report_ids": missing_terminal_report_ids,
        "admitted_report_count": len(admitted),
        "cohort_admission_rate": len(admitted) / denominator,
        "workflow_denominator": len(admitted),
        "first_attempt_awaiting_review_rate": sum(
            bool(item.get("awaiting_review"))
            and int(item.get("workflow_attempt_count") or 1) == 1
            for item in admitted
        )
        / workflow_denominator,
        "publication_readiness_rate": sum(
            item.get("publication_readiness") == "pass" for item in admitted
        )
        / workflow_denominator,
        "bounded_repair_rate": sum(
            bool(item.get("bounded_automatic_repair")) for item in admitted
        )
        / workflow_denominator,
        "workflow_failure_rate": sum(
            item.get("final_state") != "awaiting_review" for item in admitted
        )
        / workflow_denominator,
        "typed_terminal_rate": sum(
            item.get("final_state") in {"awaiting_review", "failed"}
            for item in admitted
        )
        / workflow_denominator,
        "operator_intervention_count": sum(
            bool(item.get("operator_intervention")) for item in results
        ),
        "failure_code_pareto": pareto,
        "mean_cost": round(sum(costs) / denominator, 6),
        "median_cost": round(median(costs), 6) if costs else 0.0,
        "mean_duration_seconds": round(sum(durations) / denominator, 3),
        "median_duration_seconds": round(median(durations), 3) if durations else 0.0,
    }
    if cohort_metrics is not None:
        summary.update(
            {
                "cohort_cost_usd": cohort_metrics.get("cost_usd"),
                "cohort_duration_seconds": cohort_metrics.get("duration_seconds"),
                "cohort_bounded_automatic_repair": cohort_metrics.get(
                    "bounded_automatic_repair"
                ),
                "cohort_model_provider_calls": cohort_metrics.get(
                    "model_provider_calls"
                ),
                "cohort_input_tokens": cohort_metrics.get("input_tokens"),
                "cohort_output_tokens": cohort_metrics.get("output_tokens"),
                "bounded_repair_rate": "unavailable",
                "operator_intervention_count": cohort_metrics.get(
                    "operator_intervention_count", "unavailable"
                ),
                "mean_cost": "unavailable",
                "median_cost": "unavailable",
                "mean_duration_seconds": "unavailable",
                "median_duration_seconds": "unavailable",
            }
        )
    return summary
