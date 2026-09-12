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
    FrozenValidationCohortQueueSubmissionRequest,
)
from src.contracts.workflow_queue import SourceIngestPayload
from src.orchestrators.admission_preflight_orchestrator import (
    AdmissionPreflightRequest,
    admission_configuration_hash,
    admission_decision_payload,
    admission_policy_hash,
    pipeline_preflight_decision_hash,
    run_admission_preflight,
)
from src.orchestrators.ingest_orchestrator import (
    IngestBatchDependencies,
    _frozen_cohort,
    submit_frozen_validation_cohort_to_queue,
)
from src.orchestrators.pipeline_preflight_orchestrator import preflight_report_pipeline
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services.config_service import (
    build_ingest_settings,
    load_settings,
    new_runtime_context,
)
from src.services.llm_usage_ledger_service import read_usage_run_summary
from src.services.report_store_service import (
    record_report_source,
    record_source_identity_observation,
)
from src.services.workflow_queue_service import materialize_workflow_outbox
from src.utils.errors import AppError


@dataclass(frozen=True)
class IsolatedCanaryRun:
    """Filesystem locations for one fresh, disposable canary execution."""

    root: Path
    config_path: Path
    mutable_paths: tuple[Path, ...]


_REPORT_QUEUES = (
    "source_ingest",
    "report_selection",
    "report_analysis",
    "report_render",
    "publication_readiness",
)
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
    }
    config["analysis"] = {
        **dict(config.get("analysis") or {}),
        "cost_ledger_path": str(cost_paths["ledger_path"]),
    }
    config["cost"] = {
        **dict(config.get("cost") or {}),
        **{name: str(path) for name, path in cost_paths.items()},
    }
    config["browser_download"] = {
        **dict(config.get("browser_download") or {}),
        "output_dir": str(root / "output" / "browser_downloads"),
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
    return config


def run_ias_first_attempt_canary(
    *,
    runs_root: Path,
    source_path: Path,
    max_duration_seconds: int = 7_200,
) -> dict[str, Any]:
    """Run one IAS source through the normal frozen-cohort queue exactly once."""

    started_at = time.monotonic()
    run = prepare_isolated_canary_run(runs_root=runs_root)
    result = _empty_result(run, started_at)
    try:
        if not source_path.is_file():
            result["terminal_failure_code"] = "ias_canary_source_missing"
            return result
        ctx = new_runtime_context(task_id="ias_first_attempt_live_canary")
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
        report_id = f"ias-{source_hash[:20]}"
        result["report_id"] = report_id
        observation = _record_ias_source_identity(
            settings=settings,
            report_id=report_id,
            source_hash=source_hash,
            ctx=ctx,
        )
        source = DriveFile(
            schema_version="1.0",
            file_id=report_id,
            name=source_path.name,
            modified_time=None,
            md5_checksum=source_hash,
            mime_type="application/pdf",
        )
        runtime_preflight = preflight_report_pipeline(settings, ctx)
        admission = run_admission_preflight(
            AdmissionPreflightRequest(
                file=source,
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
        if not admission.admitted:
            result["source_identity_id"] = observation.source_identity_id
            result["publisher_id"] = observation.publisher_id
            result["terminal_failure_code"] = (
                f"ias_canary_admission_{admission.decision.outcome}"
            )
            return result
        decision = admission_decision_payload(admission.decision)
        result["source_identity_id"] = str(decision["source_identity_id"])
        result["publisher_id"] = str(decision["publisher_id"])
        cohort_manifest = run.root / "cohort" / "ias.json"
        _frozen_cohort(
            cohort_size=1,
            cohort_manifest=str(cohort_manifest),
            selected_files=[source],
            settings=settings,
            deps=IngestBatchDependencies.default(),
            root_ctx=ctx,
            admission_decisions=[decision],
        )
        submission = submit_frozen_validation_cohort_to_queue(
            FrozenValidationCohortQueueSubmissionRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                cohort_manifest=str(cohort_manifest),
                source_ingest_payloads=(
                    SourceIngestPayload(
                        source_identity_id=str(decision["source_identity_id"]),
                        source_artifact_reference=str(source_path.resolve()),
                        source_content_hash=source_hash,
                        report_id=report_id,
                        parser_ocr_compatibility_version="parser.v1",
                        input_reference=str(source_path.resolve()),
                        input_content_hash=source_hash,
                        processing_version="parser.v1",
                        attributes={"config_path": str(run.config_path)},
                    ),
                ),
            ),
            ctx,
        )
        result["workflow_root_id"] = str(submission.root_workflow_id)
        _drain_report_path(
            state_db=settings.state_db,
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
        result["terminal_failure_code"] = "ias_canary_runner_defect"
    finally:
        result["total_duration_seconds"] = round(time.monotonic() - started_at, 3)
        _write_result(run.root / "result.json", result)
    return result


def run_first_attempt_canary(
    *,
    runs_root: Path,
    source_path: Path,
    max_duration_seconds: int = 7_200,
) -> dict[str, Any]:
    """Run one non-IAS source through the same one-attempt queue path."""

    started_at = time.monotonic()
    run = prepare_isolated_canary_run(runs_root=runs_root)
    result = _empty_result(run, started_at)
    try:
        if not source_path.is_file():
            result["terminal_failure_code"] = "frozen_cohort_source_missing"
            return result
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
        source_hash = hashlib.md5(
            source_path.read_bytes(), usedforsecurity=False
        ).hexdigest()
        report_id = f"cohort-{source_hash[:20]}"
        result["report_id"] = report_id
        source = DriveFile(
            schema_version="1.0",
            file_id=report_id,
            name=source_path.name,
            modified_time=None,
            md5_checksum=source_hash,
            mime_type="application/pdf",
        )
        runtime_preflight = preflight_report_pipeline(settings, ctx)
        admission = run_admission_preflight(
            AdmissionPreflightRequest(
                file=source,
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
        decision = admission_decision_payload(admission.decision)
        result["source_identity_id"] = str(decision.get("source_identity_id") or "")
        result["publisher_id"] = str(decision.get("publisher_id") or "")
        if not admission.admitted:
            result["terminal_failure_code"] = (
                f"frozen_cohort_admission_{admission.decision.outcome}"
            )
            return result
        cohort_manifest = run.root / "cohort" / "source.json"
        _frozen_cohort(
            cohort_size=1,
            cohort_manifest=str(cohort_manifest),
            selected_files=[source],
            settings=settings,
            deps=IngestBatchDependencies.default(),
            root_ctx=ctx,
            admission_decisions=[decision],
        )
        submission = submit_frozen_validation_cohort_to_queue(
            FrozenValidationCohortQueueSubmissionRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                cohort_manifest=str(cohort_manifest),
                source_ingest_payloads=(
                    SourceIngestPayload(
                        source_identity_id=str(decision["source_identity_id"]),
                        source_artifact_reference=str(source_path.resolve()),
                        source_content_hash=source_hash,
                        report_id=report_id,
                        parser_ocr_compatibility_version="parser.v1",
                        input_reference=str(source_path.resolve()),
                        input_content_hash=source_hash,
                        processing_version="parser.v1",
                        attributes={"config_path": str(run.config_path)},
                    ),
                ),
            ),
            ctx,
        )
        result["workflow_root_id"] = str(submission.root_workflow_id)
        _drain_report_path(
            state_db=settings.state_db,
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
        result["terminal_failure_code"] = "frozen_cohort_runner_defect"
    finally:
        result["total_duration_seconds"] = round(time.monotonic() - started_at, 3)
        _write_result(run.root / "result.json", result)
    return result


def _record_ias_source_identity(*, settings, report_id: str, source_hash: str, ctx):
    source = record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            source_domain="integralads.com",
            report_name="IAS Industry Pulse Report 2026",
            landing_page_url="https://integralads.com/insider/industry-pulse-report/",
            downloaded_at_utc="2026-09-12T00:00:00Z",
            md5=source_hash,
            publisher_name="Integral Ad Science",
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
                canonical_title="IAS Industry Pulse Report 2026",
                title_evidence_locator="ias-live-canary:fixture-title",
                publisher_id="publisher:integral-ad-science",
                publisher_name="Integral Ad Science",
                canonical_landing_page_url=(
                    "https://integralads.com/insider/industry-pulse-report/"
                ),
                source_page_url="https://integralads.com/insider/",
                retrieved_at_utc="2026-09-12T00:00:00Z",
                acquisition_route="frozen_ias_fixture",
                content_hash=f"md5:{source_hash}",
                resolution_method="ias_live_canary_source_observation",
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
    report_id: str,
    root_workflow_id: str,
    ctx,
    max_duration_seconds: int,
) -> None:
    deadline = time.monotonic() + max(1, max_duration_seconds)
    worker_id = f"ias-live-canary:{root_workflow_id}"
    while time.monotonic() < deadline:
        materialize_workflow_outbox(state_db, worker_id, ctx)
        progress = False
        for queue_name in _REPORT_QUEUES:
            worker = run_workflow_worker_once(
                state_db=state_db,
                queue_name=queue_name,
                worker_id=worker_id,
                ctx=ctx,
            )
            progress = progress or bool(worker.claimed_job_id)
        materialize_workflow_outbox(state_db, worker_id, ctx)
        state = _queue_terminal_state(
            state_db=state_db,
            report_id=report_id,
            root_workflow_id=root_workflow_id,
        )
        if state in {"awaiting_review", "failed"}:
            return
        if not progress:
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
    if status != "awaiting_review":
        terminal_failure = str((failure or ("ias_canary_timeout",))[0])
    return {
        "workflow_attempt_count": attempts,
        "final_state": status,
        "awaiting_review": status == "awaiting_review",
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


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() or "unknown"


def _write_result(path: Path, result: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def summarize_frozen_cohort_results(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize every frozen admitted member without changing its denominator."""

    count = len(results)
    denominator = max(1, count)
    costs = [float(item.get("cost") or 0.0) for item in results]
    durations = [float(item.get("total_duration_seconds") or 0.0) for item in results]
    failures = [
        str(item.get("terminal_failure_code") or "")
        for item in results
        if str(item.get("terminal_failure_code") or "")
    ]
    pareto = {code: failures.count(code) for code in sorted(set(failures))}
    return {
        "report_count": count,
        "first_attempt_awaiting_review_rate": sum(
            bool(item.get("awaiting_review"))
            and int(item.get("workflow_attempt_count") or 1) == 1
            for item in results
        )
        / denominator,
        "publication_readiness_rate": sum(
            item.get("publication_readiness") == "pass" for item in results
        )
        / denominator,
        "bounded_repair_rate": sum(
            bool(item.get("bounded_automatic_repair")) for item in results
        )
        / denominator,
        "workflow_failure_rate": sum(
            item.get("final_state") != "awaiting_review" for item in results
        )
        / denominator,
        "typed_terminal_rate": sum(
            item.get("final_state") in {"awaiting_review", "failed"} for item in results
        )
        / denominator,
        "operator_intervention_count": sum(
            bool(item.get("operator_intervention")) for item in results
        ),
        "failure_code_pareto": pareto,
        "mean_cost": round(sum(costs) / denominator, 6),
        "median_cost": round(median(costs), 6) if costs else 0.0,
        "mean_duration_seconds": round(sum(durations) / denominator, 3),
        "median_duration_seconds": round(median(durations), 3) if durations else 0.0,
    }
