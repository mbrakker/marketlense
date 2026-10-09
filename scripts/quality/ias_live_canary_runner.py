"""Operational runner for one isolated live IAS first-attempt canary."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from types import TracebackType
from typing import Any
from urllib.parse import SplitResult, urlsplit

import yaml

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.drive import DriveFile
from src.contracts.logging import REQUIRED_LOG_EVENT_FIELDS
from src.contracts.llm_usage import LLMUsageRunSummaryRequest
from src.contracts.report_analysis import AnalysisPackPathRequest
from src.contracts.report_store import (
    ReportSourceRecordRequest,
    SourceIdentityObservation,
    SourceIdentityObservationRecordRequest,
)
from src.contracts.semantic_ids import ReportId
from src.contracts.signal_candidates import (
    SIGNAL_CANDIDATE_SCHEMA_VERSION,
    SignalCandidateReadRequest,
    SignalCandidateStoreRequest,
)
from src.contracts.validation_run_manifest import (
    PreselectedFrozenValidationCohortSubmissionRequest,
    PreselectedFrozenValidationSource,
)
from src.contracts.workflow_control import SupervisorRunRequest
from src.contracts.workflow_queue import WorkflowQueueControl
from src.contracts.workflow_queue import WorkflowJobSubmission
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
    load_publish_settings,
    load_workflow_control_settings,
    load_workflow_queue_policies,
    new_runtime_context,
)
from src.services._config_service.yaml_mapping import deep_merge_mappings
from src.services.llm_usage_ledger_service import read_usage_run_summary
from src.services.analytics_store_service import (
    read_signal_candidates,
    upsert_signal_candidates,
)
from src.services.report_analysis_store_service import (
    pack_path as resolve_report_analysis_pack_path,
)
from src.services.report_store_service import (
    record_report_source,
    record_source_identity_observation,
)
from src.services.workflow_queue_service import (
    enqueue_workflow_job,
    get_workflow_queue_control,
    get_workflow_job,
    load_workflow_job_payload,
    seed_workflow_queue_controls,
    set_workflow_queue_control,
)
from src.services.wordpress_service import preflight_publish_capability
from src.utils.errors import AppError
from src.utils.slugify import slugify

_VALIDATION_REUSE_LOGGER_NAME = "market_lense.validation_generator"
_VALIDATION_REUSE_EVENT_NAME = "validation_claim_reuse_decided"
_VALIDATION_REUSE_COUNTER_FIELDS = (
    "total_candidate_claims",
    "reused_validation_results",
    "newly_validated_claims",
    "grounding_calls_avoided",
    "semantic_validation_calls_avoided",
)


def _reuse_event_payload(record: logging.LogRecord) -> dict[str, Any] | None:
    if record.name != _VALIDATION_REUSE_LOGGER_NAME:
        return None
    try:
        payload = json.loads(record.getMessage())
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("event") != _VALIDATION_REUSE_EVENT_NAME:
        return None
    if payload.get("module") != _VALIDATION_REUSE_LOGGER_NAME:
        return None
    return payload


class _PreserveValidationLoggerFilter(logging.Filter):
    """Only enable the target INFO event when INFO was previously disabled."""

    def __init__(self, previous_effective_level: int) -> None:
        super().__init__()
        self._previous_effective_level = previous_effective_level

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= self._previous_effective_level:
            return (
                record.levelno != logging.INFO
                or _reuse_event_payload(record) is not None
            )
        return (
            record.levelno == logging.INFO and _reuse_event_payload(record) is not None
        )


class _ValidationReuseDecisionHandler(logging.Handler):
    """Retain only bounded claim-reuse counters from the existing log event."""

    def __init__(self, path: Path) -> None:
        super().__init__(level=logging.INFO)
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("w", encoding="utf-8", newline="\n")
        self.event_count = 0
        self.invalid_event_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        payload = _reuse_event_payload(record)
        if payload is None:
            return
        raw_fields = payload.get("fields")
        if not REQUIRED_LOG_EVENT_FIELDS.issubset(payload) or not isinstance(
            raw_fields, dict
        ):
            self.invalid_event_count += 1
            return
        fields: dict[str, Any] = {}
        for name in _VALIDATION_REUSE_COUNTER_FIELDS:
            value = raw_fields.get(name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                self.invalid_event_count += 1
                return
            fields[name] = value
        fallback_counts = raw_fields.get("reuse_fallback_reason_counts")
        if not isinstance(fallback_counts, dict):
            self.invalid_event_count += 1
            return
        fields["reuse_fallback_reason_counts"] = {
            str(reason): count
            for reason, count in sorted(
                fallback_counts.items(), key=lambda item: str(item[0])
            )
            if isinstance(reason, str)
            and reason.strip()
            and len(reason) <= 120
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
        }
        retained = {name: payload[name] for name in REQUIRED_LOG_EVENT_FIELDS}
        retained["fields"] = fields
        try:
            self._stream.write(
                json.dumps(retained, sort_keys=True, separators=(",", ":")) + "\n"
            )
            self._stream.flush()
            self.event_count += 1
        except (OSError, TypeError, ValueError):
            self.invalid_event_count += 1

    def close(self) -> None:
        try:
            self._stream.close()
        finally:
            super().close()


class _ValidationReuseEventCapture:
    """Temporarily retain one safe structured event in a frozen run directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handler: _ValidationReuseDecisionHandler | None = None
        self.logger = logging.getLogger(_VALIDATION_REUSE_LOGGER_NAME)
        self.previous_level = self.logger.level
        self.previous_effective_level = self.logger.getEffectiveLevel()
        self.filter: _PreserveValidationLoggerFilter | None = None

    def __enter__(self) -> _ValidationReuseDecisionHandler:
        self.handler = _ValidationReuseDecisionHandler(self.path)
        self.logger.addHandler(self.handler)
        if self.previous_effective_level > logging.INFO:
            self.filter = _PreserveValidationLoggerFilter(self.previous_effective_level)
            self.logger.addFilter(self.filter)
            self.logger.setLevel(logging.INFO)
        return self.handler

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.handler is not None:
            self.logger.removeHandler(self.handler)
            self.handler.close()
        if self.filter is not None:
            self.logger.removeFilter(self.filter)
        self.logger.setLevel(self.previous_level)


def _validation_reuse_telemetry_summary(
    path: Path, handler: _ValidationReuseDecisionHandler
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    totals = {name: 0 for name in _VALIDATION_REUSE_COUNTER_FIELDS}
    fallback_totals: dict[str, int] = {}
    for event in events:
        fields = event.get("fields")
        if not isinstance(fields, dict):
            continue
        for name in _VALIDATION_REUSE_COUNTER_FIELDS:
            value = fields.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[name] += value
        reasons = fields.get("reuse_fallback_reason_counts")
        if isinstance(reasons, dict):
            for reason, count in reasons.items():
                if isinstance(reason, str) and isinstance(count, int):
                    fallback_totals[reason] = fallback_totals.get(reason, 0) + count
    return {
        "artifact_path": path.name,
        "event_count": len(events),
        "invalid_event_count": handler.invalid_event_count,
        "totals_across_validation_passes": totals,
        "reuse_fallback_reason_counts": dict(sorted(fallback_totals.items())),
    }


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
_DIAGNOSTIC_TOKEN_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-[]"
)
_FROZEN_REPORT_QUEUE_STAGES = (
    "source_ingest",
    "report_selection",
    "report_analysis",
    "report_render",
    "publication_readiness",
)
_CROSS_REPORT_QUEUE_NAMES = (
    "analytics_projection",
    "signal_candidate",
    "signal_generation",
    "briefing_opportunity",
    "briefing_generation",
)
_CROSS_REPORT_DESCENDANT_QUEUE_NAMES = (
    *_CROSS_REPORT_QUEUE_NAMES,
    "cover_generation",
    "publication_readiness",
    "wordpress_publish",
    "wordpress_projection",
)
_CROSS_REPORT_TERMINAL_STATUSES = {"succeeded", "blocked", "dead_letter", "cancelled"}
_CONFIRMED_WORDPRESS_STAGING_HOST = "marketlense.medianewsonline.com"


def prepare_isolated_canary_run(
    *,
    runs_root: Path,
    publish_to_wordpress_staging: bool = False,
    staging_hostname: str = "",
    allow_insecure_staging_http: bool = False,
    enable_cross_report_analysis: bool = False,
) -> IsolatedCanaryRun:
    """Create a unique run root and config whose mutable paths stay within it."""

    _validate_staging_mode(
        publish_to_wordpress_staging=publish_to_wordpress_staging,
        staging_hostname=staging_hostname,
        allow_insecure_staging_http=allow_insecure_staging_http,
    )

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
    config = _isolated_config(
        root=root,
        paths=paths,
        cost_paths=cost_paths,
        publish_to_wordpress_staging=publish_to_wordpress_staging,
        enable_cross_report_analysis=enable_cross_report_analysis,
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return IsolatedCanaryRun(
        root=root,
        config_path=config_path,
        mutable_paths=mutable_paths,
    )


def _isolated_config(
    *,
    root: Path,
    paths: dict[str, Path],
    cost_paths: dict[str, Path],
    publish_to_wordpress_staging: bool = False,
    enable_cross_report_analysis: bool = False,
) -> dict[str, Any]:
    base_config_path = (
        Path(__file__).resolve().parents[2] / "src" / "config" / "app.yaml"
    )
    config = yaml.safe_load(base_config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise RuntimeError("Base application configuration must be a mapping")
    if publish_to_wordpress_staging:
        profile_path = base_config_path.with_name("app.autonomous_mvp.yaml")
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        if not isinstance(profile, dict):
            raise RuntimeError("Autonomous MVP configuration must be a mapping")
        config = deep_merge_mappings(config, profile)
    else:
        config = copy.deepcopy(config)
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
    if publish_to_wordpress_staging:
        workflow_control["autonomous_publication_policy"] = {
            **dict(workflow_control.get("autonomous_publication_policy") or {}),
            "enabled": True,
        }
    config["workflow_control"] = workflow_control
    workflow_queues = dict(config.get("workflow_queues") or {})
    workflow_queues["wordpress_publish"] = {
        **dict(workflow_queues.get("wordpress_publish") or {}),
        "enabled": publish_to_wordpress_staging,
    }
    if publish_to_wordpress_staging:
        for queue_name in (
            "publisher_discovery",
            "report_acquisition",
            "mailbox_delivery",
        ):
            workflow_queues[queue_name] = {
                **dict(workflow_queues.get(queue_name) or {}),
                "enabled": False,
            }
    config["workflow_queues"] = workflow_queues
    publish = dict(config.get("publish") or {})
    wp = dict(publish.get("wp") or {})
    if publish_to_wordpress_staging:
        wp["post_status"] = "draft"
    publish["wp"] = wp
    config["publish"] = publish
    cross_report = dict(config.get("cross_report_analysis") or {})
    cross_report["enabled"] = enable_cross_report_analysis
    config["cross_report_analysis"] = cross_report
    return config


def _validate_staging_mode(
    *,
    publish_to_wordpress_staging: bool,
    staging_hostname: str,
    allow_insecure_staging_http: bool = False,
) -> None:
    normalized_host = str(staging_hostname or "").strip().lower().rstrip(".")
    if publish_to_wordpress_staging:
        if normalized_host != _CONFIRMED_WORDPRESS_STAGING_HOST:
            raise ValueError(
                "WordPress publication requires the confirmed WordPress staging host"
            )
    elif normalized_host:
        raise ValueError(
            "A staging hostname is only accepted when staging publication is enabled"
        )
    if allow_insecure_staging_http and not publish_to_wordpress_staging:
        raise ValueError(
            "HTTP staging opt-in requires WordPress staging publication to be enabled"
        )


def _validate_wordpress_staging_origin(
    site_url: str,
    *,
    staging_hostname: str,
    allow_insecure_http: bool,
) -> SplitResult:
    """Validate a credentialed WordPress target against the pinned staging origin."""

    expected_host = str(staging_hostname or "").strip().lower().rstrip(".")
    if expected_host != _CONFIRMED_WORDPRESS_STAGING_HOST:
        raise ValueError("WordPress target is not the confirmed staging host")
    raw_site_url = str(site_url or "").strip()
    try:
        site = urlsplit(raw_site_url)
        scheme = site.scheme.lower()
        hostname = (site.hostname or "").lower().rstrip(".")
        port = site.port
    except ValueError as exc:
        raise ValueError("WordPress staging URL is invalid") from exc
    if (
        scheme not in {"http", "https"}
        or hostname != expected_host
        or site.username is not None
        or site.password is not None
        or "?" in raw_site_url
        or "#" in raw_site_url
    ):
        raise ValueError("WordPress target is not the confirmed staging origin")
    expected_port = 80 if scheme == "http" else 443
    if port not in {None, expected_port}:
        raise ValueError("WordPress staging URL uses an unapproved port")
    if scheme == "http" and not allow_insecure_http:
        raise ValueError("HTTP WordPress staging requires explicit opt-in")
    return site


def _wordpress_publication_evidence(
    *,
    stage_rows: tuple[tuple[int, str, str, str], ...],
    wordpress_post_id: int | None,
) -> dict[str, bool]:
    """Count only a first-attempt write and matching authenticated readback."""

    if wordpress_post_id is None:
        return {
            "wordpress_created_this_run": False,
            "wordpress_authenticated_readback": False,
        }
    expected_post_id = str(wordpress_post_id)
    first_attempt = {
        stage: (outcome, artifact_ids_json)
        for attempt_number, stage, outcome, artifact_ids_json in stage_rows
        if attempt_number == 1
        and stage in {"wordpress_write", "authenticated_readback"}
    }

    def contains_post_id(stage: str) -> bool:
        record = first_attempt.get(stage)
        if record is None:
            return False
        try:
            artifact_ids = json.loads(record[1])
        except (TypeError, json.JSONDecodeError):
            return False
        return isinstance(artifact_ids, list) and expected_post_id in {
            str(value) for value in artifact_ids
        }

    created = first_attempt.get("wordpress_write", ("", ""))[
        0
    ] == "succeeded" and contains_post_id("wordpress_write")
    readback = (
        created
        and first_attempt.get("authenticated_readback", ("", ""))[0]
        == "published_verified"
        and contains_post_id("authenticated_readback")
    )
    return {
        "wordpress_created_this_run": created,
        "wordpress_authenticated_readback": readback,
    }


def ensure_isolated_publication_queue_disabled(
    *, state_db: str, ctx: Any
) -> WorkflowQueueControl:
    """Persist the canary publication stop at the durable queue boundary."""

    control = get_workflow_queue_control(state_db, "wordpress_publish", ctx)
    return set_workflow_queue_control(
        state_db,
        replace(
            control,
            enabled=False,
            updated_at_utc="",
            updated_by="frozen_cohort_canary",
        ),
        ctx,
    )


def _seed_isolated_workflow_queue_controls(
    *, state_db: str, config_path: Path, ctx: Any
) -> dict[str, WorkflowQueueControl]:
    """Seed a fresh canary queue from its isolated app.yaml before submission."""

    policies = load_workflow_queue_policies(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), ctx
    )
    controls = seed_workflow_queue_controls(
        state_db,
        [
            WorkflowQueueControl(
                schema_version=policy.schema_version,
                queue_name=policy.queue_name,
                mode="active",
                enabled=policy.enabled,
                worker_concurrency_limit=policy.max_workers,
                maximum_pending=policy.maximum_pending,
                maximum_fanout=policy.maximum_fanout,
                max_attempts=policy.max_attempts,
                lease_seconds=policy.lease_seconds,
                budget_profile=policy.budget_profile,
                retry_delay_seconds=policy.retry_delay_seconds,
                emergency_stop_reason="",
                updated_at_utc="",
                updated_by="config_seed",
            )
            for policy in policies.values()
        ],
        ctx,
    )
    return {control.queue_name: control for control in controls}


def _collect_frozen_cohort_queue_timing_evidence(
    *, state_db: str, root_workflow_id: str, report_ids: tuple[str, ...]
) -> dict[str, Any]:
    """Collect queue timing, dependencies, and overlap from retained telemetry."""

    if not report_ids:
        return {
            "stage_attempts": [],
            "terminal_dependency_chain": {"available": False},
            "resource_constrained_critical_path": {
                "derived": False,
                "reason": (
                    "The retained cohort telemetry does not capture all "
                    "scheduler contention."
                ),
            },
        }
    report_marks = ",".join("?" for _ in report_ids)
    stage_marks = ",".join("?" for _ in _FROZEN_REPORT_QUEUE_STAGES)
    with sqlite3.connect(state_db) as conn:
        conn.row_factory = sqlite3.Row
        controls = {
            str(row["queue_name"]): {
                "enabled": bool(row["enabled"]),
                "configured_workers": int(row["worker_concurrency_limit"]),
                "max_attempts": int(row["max_attempts"]),
            }
            for row in conn.execute(
                "SELECT queue_name,enabled,worker_concurrency_limit,max_attempts "
                "FROM workflow_queue_controls WHERE queue_name IN ("
                + stage_marks
                + ", 'wordpress_publish')",
                _FROZEN_REPORT_QUEUE_STAGES,
            )
        }
        jobs = {
            str(row["job_id"]): dict(row)
            for row in conn.execute(
                "SELECT job_id,report_id,queue_name,parent_job_id,job_type,status,"
                "created_at_utc,available_at_utc,started_at_utc,completed_at_utc "
                "FROM workflow_jobs WHERE root_workflow_id=? AND report_id IN ("
                + report_marks
                + ") AND queue_name IN ("
                + stage_marks
                + ")",
                (root_workflow_id, *report_ids, *_FROZEN_REPORT_QUEUE_STAGES),
            )
        }
        attempts: dict[str, list[dict[str, Any]]] = {}
        for row in conn.execute(
            "SELECT a.job_id,a.attempt_number,a.started_at_utc,a.completed_at_utc,"
            "a.outcome,a.error_code FROM workflow_job_attempts AS a "
            "JOIN workflow_jobs AS j ON j.job_id=a.job_id "
            "WHERE j.root_workflow_id=? AND j.report_id IN ("
            + report_marks
            + ") AND j.queue_name IN ("
            + stage_marks
            + ") ORDER BY a.job_id,a.attempt_number",
            (root_workflow_id, *report_ids, *_FROZEN_REPORT_QUEUE_STAGES),
        ):
            attempts.setdefault(str(row["job_id"]), []).append(dict(row))
        measurements: dict[str, dict[str, list[int]]] = {}
        for row in conn.execute(
            "SELECT s.attributes_json,m.metric,m.status,m.integer_value "
            "FROM performance_telemetry_spans AS s "
            "JOIN performance_telemetry_measurements AS m ON m.span_id=s.span_id "
            "WHERE s.stage IN (" + stage_marks + ") ORDER BY s.rowid,m.metric",
            _FROZEN_REPORT_QUEUE_STAGES,
        ):
            if row["status"] != "observed" or row["integer_value"] is None:
                continue
            if row["metric"] not in {"queue_wait_ms", "wall_time_ms"}:
                continue
            try:
                job_id = str(
                    json.loads(row["attributes_json"] or "{}").get("job_id") or ""
                )
            except json.JSONDecodeError:
                continue
            if job_id in jobs:
                measurements.setdefault(job_id, {}).setdefault(
                    str(row["metric"]), []
                ).append(int(row["integer_value"]))
        retry_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM workflow_job_attempts AS a "
                "JOIN workflow_jobs AS j ON j.job_id=a.job_id "
                "WHERE j.root_workflow_id=? AND a.outcome='retry_wait'",
                (root_workflow_id,),
            ).fetchone()[0]
        )
        operator_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM workflow_job_transitions AS t "
                "JOIN workflow_jobs AS j ON j.job_id=t.job_id "
                "WHERE j.root_workflow_id=? AND t.reason IN "
                "('operator_requeue','queue-requeue')",
                (root_workflow_id,),
            ).fetchone()[0]
        )
        publish_attempts = int(
            conn.execute(
                "SELECT COUNT(*) FROM workflow_job_attempts AS a "
                "JOIN workflow_jobs AS j ON j.job_id=a.job_id "
                "WHERE j.root_workflow_id=? AND j.queue_name='wordpress_publish'",
                (root_workflow_id,),
            ).fetchone()[0]
        )
        published = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='published'"
        ).fetchone()
        publish_records = (
            int(conn.execute("SELECT COUNT(*) FROM published").fetchone()[0])
            if published
            else 0
        )

    stage_attempts: list[dict[str, Any]] = []
    by_job: dict[str, list[dict[str, Any]]] = {}
    for job_id, job in jobs.items():
        job_attempts = attempts.get(job_id, [])
        metric_values = measurements.get(job_id, {})
        for index, attempt in enumerate(job_attempts):
            wait_values = metric_values.get("queue_wait_ms", [])
            wall_values = metric_values.get("wall_time_ms", [])
            wait_from_telemetry = len(wait_values) == len(job_attempts)
            wall_from_telemetry = len(wall_values) == len(job_attempts)
            wait_ms = wait_values[index] if wait_from_telemetry else None
            wall_ms = wall_values[index] if wall_from_telemetry else None
            started = str(attempt["started_at_utc"] or "")
            completed = str(attempt["completed_at_utc"] or "")
            start_dt = _parse_telemetry_time(started)
            end_dt = _parse_telemetry_time(completed)
            if wait_ms is None and start_dt is not None:
                ready = _parse_telemetry_time(
                    str(job["available_at_utc"] or job["created_at_utc"])
                )
                if index:
                    prior = _parse_telemetry_time(
                        str(job_attempts[index - 1]["completed_at_utc"] or "")
                    )
                    if prior is not None:
                        ready = max(ready or prior, prior)
                if ready is not None:
                    wait_ms = max(0, round((start_dt - ready).total_seconds() * 1000))
            if wall_ms is None and start_dt is not None and end_dt is not None:
                measured = round((end_dt - start_dt).total_seconds() * 1000)
                wall_ms = measured if measured > 0 else None
            effective_end = (
                start_dt + timedelta(milliseconds=wall_ms)
                if start_dt is not None and wall_ms is not None
                else end_dt
            )
            item = {
                "job_id": job_id,
                "report_id": str(job["report_id"]),
                "stage": str(job["queue_name"]),
                "job_type": str(job["job_type"]),
                "parent_job_id": str(job["parent_job_id"] or ""),
                "attempt_number": int(attempt["attempt_number"]),
                "outcome": str(attempt["outcome"] or ""),
                "error_code": str(attempt["error_code"] or ""),
                "enqueued_at_utc": str(job["created_at_utc"]),
                "available_at_utc": str(job["available_at_utc"]),
                "started_at_utc": started,
                "completed_at_utc": completed,
                "queue_wait_seconds": round(wait_ms / 1000, 3)
                if wait_ms is not None
                else None,
                "queue_wait_source": (
                    "performance_telemetry.queue_wait_ms"
                    if wait_from_telemetry
                    else "persisted_queue_timestamps"
                    if wait_ms is not None
                    else "unavailable"
                ),
                "execution_seconds": round(wall_ms / 1000, 3)
                if wall_ms is not None
                else None,
                "execution_source": (
                    "performance_telemetry.wall_time_ms"
                    if wall_from_telemetry
                    else "workflow_attempt_timestamps"
                    if wall_ms is not None
                    else "unavailable"
                ),
                "effective_completed_at_utc": effective_end.isoformat()
                if effective_end
                else "",
                "on_terminal_dependency_chain": False,
            }
            stage_attempts.append(item)
            by_job.setdefault(job_id, []).append(item)

    readiness: dict[str, tuple[datetime, str]] = {}
    for job_id, job_attempts in by_job.items():
        job = jobs[job_id]
        if job["queue_name"] != "publication_readiness" or not job_attempts:
            continue
        final = job_attempts[-1]
        completed = _parse_telemetry_time(final["effective_completed_at_utc"])
        report_id = str(job["report_id"])
        if completed is not None and (
            report_id not in readiness or completed > readiness[report_id][0]
        ):
            readiness[report_id] = (completed, job_id)
    terminal_dependency_chain: dict[str, Any] = {"available": False}
    if len(readiness) == len(report_ids):
        report_id, (terminal_time, terminal_job_id) = max(
            readiness.items(), key=lambda item: item[1][0]
        )
        chain: list[str] = []
        current = terminal_job_id
        while current in jobs and current not in chain:
            chain.append(current)
            current = str(jobs[current]["parent_job_id"] or "")
        chain.reverse()
        path_available = (
            bool(chain)
            and jobs[chain[0]]["queue_name"] == "source_ingest"
            and jobs[chain[-1]]["queue_name"] == "publication_readiness"
            and all(jobs[job_id]["report_id"] == report_id for job_id in chain)
        )
        path_attempts = [item for job_id in chain for item in by_job.get(job_id, [])]
        path_available = (
            path_available
            and len(path_attempts) > 0
            and all(by_job.get(job_id) for job_id in chain)
        )
        for item in path_attempts:
            item["on_terminal_dependency_chain"] = True
        path_enqueue = (
            _parse_telemetry_time(path_attempts[0]["enqueued_at_utc"])
            if path_available
            else None
        )
        path_start = (
            _parse_telemetry_time(path_attempts[0]["started_at_utc"])
            if path_available
            else None
        )
        terminal_dependency_chain = {
            "available": path_available and path_start is not None,
            "path_source": "workflow_job_parent_chain",
            "terminal_report_id": report_id,
            "terminal_job_id": terminal_job_id,
            "terminal_completed_at_utc": terminal_time.isoformat(),
            "path_enqueued_at_utc": path_enqueue.isoformat() if path_enqueue else "",
            "path_started_at_utc": path_start.isoformat() if path_start else "",
            "elapsed_seconds": (
                round((terminal_time - path_enqueue).total_seconds(), 3)
                if path_enqueue
                else None
            ),
            "jobs": path_attempts,
        }

    concurrency = {}
    for queue_name in _FROZEN_REPORT_QUEUE_STAGES:
        queue_spans = [item for item in stage_attempts if item["stage"] == queue_name]
        concurrency[queue_name] = {
            **controls.get(queue_name, {}),
            "max_observed_running_jobs": _maximum_interval_concurrency(queue_spans),
        }

    stage_metrics = {}
    for item in stage_attempts:
        summary = stage_metrics.setdefault(
            item["stage"], {"queue_wait_seconds": [], "execution_seconds": []}
        )
        for metric in summary:
            if item[metric] is not None:
                summary[metric].append(item[metric])
    performance_by_stage = [
        {
            "stage": stage,
            "sample_count": len(values["execution_seconds"]),
            "queue_wait_seconds_total": round(sum(values["queue_wait_seconds"]), 3),
            "execution_seconds_total": round(sum(values["execution_seconds"]), 3),
            "execution_seconds_max": max(values["execution_seconds"], default=None),
        }
        for stage, values in sorted(stage_metrics.items())
    ]
    return {
        "stage_attempts": stage_attempts,
        "queue_controls": controls,
        "queue_concurrency": concurrency,
        "terminal_dependency_chain": terminal_dependency_chain,
        "resource_constrained_critical_path": {
            "derived": False,
            "reason": (
                "The retained cohort telemetry does not capture all "
                "scheduler contention."
            ),
        },
        "performance_telemetry_by_stage": performance_by_stage,
        "prompt_family_elapsed_time": "unavailable",
        "provider_request_timing": "unavailable",
        "automatic_queue_retry_count": retry_count,
        "operator_intervention_count": operator_count,
        "wordpress_publish_attempt_count": publish_attempts,
        "published_record_count": publish_records,
        "publication_write_count": publish_attempts + publish_records,
    }


def _parse_telemetry_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _maximum_interval_concurrency(spans: list[dict[str, Any]]) -> int:
    events = []
    for span in spans:
        start = _parse_telemetry_time(span["started_at_utc"])
        end = _parse_telemetry_time(span["effective_completed_at_utc"])
        if start is not None and end is not None and end > start:
            events.extend(((end, -1), (start, 1)))
    active = maximum = 0
    for _, delta in sorted(events, key=lambda event: (event[0], event[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


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
    publish_to_wordpress_staging: bool = False,
    staging_hostname: str = "",
    allow_insecure_staging_http: bool = False,
    enable_cross_report_analysis: bool = False,
) -> dict[str, Any]:
    """Submit one immutable retained cohort through the production queue once."""

    _validate_staging_mode(
        publish_to_wordpress_staging=publish_to_wordpress_staging,
        staging_hostname=staging_hostname,
        allow_insecure_staging_http=allow_insecure_staging_http,
    )
    if publish_to_wordpress_staging and not enable_cross_report_analysis:
        raise ValueError(
            "Staging publication requires cross-report handoff verification"
        )
    git_sha = _require_clean_git_sha()
    run_started_at_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    started_at = time.monotonic()
    run = prepare_isolated_canary_run(
        runs_root=runs_root,
        publish_to_wordpress_staging=publish_to_wordpress_staging,
        staging_hostname=staging_hostname,
        allow_insecure_staging_http=allow_insecure_staging_http,
        enable_cross_report_analysis=enable_cross_report_analysis,
    )
    reuse_events_path = run.root / "validation_claim_reuse_decisions.jsonl"
    reuse_event_handler: _ValidationReuseDecisionHandler | None = None
    results = [_empty_result(run, started_at) for _ in sources]
    cohort_metrics: dict[str, Any] = {
        "cost_usd": None,
        "duration_seconds": None,
        "bounded_automatic_repair": None,
        "wordpress_staging_preflight": None,
        "wordpress_replay": None,
        "duration_measurement": "runner entry to all five report workflows terminal",
    }
    terminal_observed_at_utc = ""
    terminal_observed_monotonic: float | None = None
    report_terminal_observed_monotonic: float | None = None
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
        if publish_to_wordpress_staging:
            publish_settings = load_publish_settings(
                ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
                ctx,
            )
            try:
                site = _validate_wordpress_staging_origin(
                    publish_settings.wp.site_url,
                    staging_hostname=staging_hostname,
                    allow_insecure_http=allow_insecure_staging_http,
                )
            except ValueError as exc:
                raise AppError(
                    code="wordpress_staging_host_mismatch",
                    message="Resolved WordPress target is not the confirmed staging host",
                    retryable=False,
                ) from exc
            if publish_settings.wp.post_status.strip().lower() != "draft":
                raise AppError(
                    code="wordpress_staging_status_unsafe",
                    message="The isolated WordPress canary must create drafts",
                    retryable=False,
                )
            preflight = preflight_publish_capability(publish_settings, ctx)
            if (
                not preflight.reachable
                or not preflight.authenticated
                or "create_posts" not in preflight.verified_capabilities
                or publish_settings.wp.post_type not in preflight.verified_post_types
            ):
                raise AppError(
                    code="wordpress_staging_capability_unavailable",
                    message="WordPress staging did not confirm draft publication capability",
                    retryable=True,
                )
            cohort_metrics["wordpress_staging_preflight"] = {
                "hostname": site.hostname,
                "scheme": site.scheme.lower(),
                "insecure_http_opt_in": allow_insecure_staging_http,
                "post_type": publish_settings.wp.post_type,
                "post_status": publish_settings.wp.post_status,
                "authenticated": preflight.authenticated,
                "reachable": preflight.reachable,
                "verified_capabilities": list(preflight.verified_capabilities),
                "provider_calls": preflight.provider_calls,
            }
        _assert_empty_stores(run=run, settings=settings)
        seeded_controls = _seed_isolated_workflow_queue_controls(
            state_db=settings.state_db,
            config_path=run.config_path,
            ctx=ctx,
        )
        if not publish_to_wordpress_staging:
            ensure_isolated_publication_queue_disabled(
                state_db=settings.state_db, ctx=ctx
            )
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
            with _ValidationReuseEventCapture(reuse_events_path) as reuse_event_handler:
                drain_timing = _drain_report_paths(
                    state_db=settings.state_db,
                    usage_db_path=settings.usage_db_path,
                    config_path=run.config_path,
                    report_ids=tuple(str(result["report_id"]) for result in results),
                    root_workflow_id=root_workflow_id,
                    ctx=ctx,
                    max_duration_seconds=max_duration_seconds,
                    drain_cross_report_handoffs=enable_cross_report_analysis,
                )
            report_terminal_observed_monotonic = drain_timing[
                "core_reports_terminal_monotonic"
            ]
            terminal_observed_monotonic = time.monotonic()
            terminal_observed_at_utc = datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            )
            queue_timing = _collect_frozen_cohort_queue_timing_evidence(
                state_db=settings.state_db,
                root_workflow_id=root_workflow_id,
                report_ids=tuple(str(result["report_id"]) for result in results),
            )
            supervisor_capacity = load_workflow_control_settings(
                ConfigLoadRequest(schema_version="1.0", path=str(run.config_path)),
                ctx,
            ).supervisor
            queue_timing.update(
                {
                    "supervisor_dispatch_capacity": {
                        "max_parallel_workers": (
                            supervisor_capacity.max_parallel_workers
                        ),
                        "max_jobs_per_queue": supervisor_capacity.max_jobs_per_queue,
                        "max_total_jobs": supervisor_capacity.max_total_jobs,
                    },
                    "runner_started_at_utc": run_started_at_utc,
                    "all_reports_terminal_observed_at_utc": drain_timing[
                        "core_reports_terminal_at_utc"
                    ],
                    "all_handoffs_terminal_observed_at_utc": terminal_observed_at_utc,
                    "core_reports_terminal_wall_seconds": drain_timing[
                        "core_reports_terminal_wall_seconds"
                    ],
                    "cross_report_handoff_drain_wall_seconds": drain_timing[
                        "cross_report_handoff_drain_wall_seconds"
                    ],
                    "cross_report_handoffs_terminal": drain_timing[
                        "cross_report_handoffs_terminal"
                    ],
                    "runner_to_terminal_wall_seconds": round(
                        terminal_observed_monotonic - started_at, 3
                    ),
                    "configured_queue_controls_at_bootstrap": {
                        name: {
                            "enabled": control.enabled,
                            "worker_concurrency_limit": (
                                control.worker_concurrency_limit
                            ),
                            "max_attempts": control.max_attempts,
                            "budget_profile": control.budget_profile,
                        }
                        for name, control in sorted(seeded_controls.items())
                        if name
                        in {
                            *_FROZEN_REPORT_QUEUE_STAGES,
                            "wordpress_publish",
                        }
                    },
                }
            )
            for result, source in zip(results, sources, strict=True):
                result.update(
                    _read_result(
                        settings=settings,
                        report_id=str(result["report_id"]),
                        source_path=Path(str(source["resolved_source_path"])),
                        validation_run_id=str(queue_submission.validation_run_id),
                        root_workflow_id=root_workflow_id,
                        ctx=ctx,
                    )
                )
            if publish_to_wordpress_staging:
                cohort_metrics["wordpress_replay"] = _replay_completed_wordpress_jobs(
                    state_db=settings.state_db,
                    root_workflow_id=root_workflow_id,
                    report_ids=tuple(str(result["report_id"]) for result in results),
                    ctx=ctx,
                )
            cross_report_provider_usage = {
                "provider_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
            }
            if enable_cross_report_analysis:
                cross_report_evidence = _collect_cross_report_handoff_evidence(
                    state_db=settings.state_db,
                    signal_store_db=settings.signal_store_db,
                    usage_db_path=settings.usage_db_path,
                    root_workflow_id=root_workflow_id,
                    ctx=ctx,
                )
                cohort_metrics["cross_report_handoffs"] = cross_report_evidence
                cross_report_provider_usage = dict(
                    cross_report_evidence["provider_usage"]
                )
            total_provider_calls = results[0]["model_provider_calls"]
            total_input_tokens = results[0]["input_tokens"]
            total_output_tokens = results[0]["output_tokens"]
            total_cost = results[0]["cost"]

            def report_scope_usage(total, cross_report):
                if total is None or cross_report > total:
                    return None
                return total - cross_report

            cohort_metrics.update(
                {
                    "model_provider_calls": report_scope_usage(
                        total_provider_calls,
                        cross_report_provider_usage["provider_calls"],
                    ),
                    "input_tokens": report_scope_usage(
                        total_input_tokens,
                        cross_report_provider_usage["input_tokens"],
                    ),
                    "output_tokens": report_scope_usage(
                        total_output_tokens,
                        cross_report_provider_usage["output_tokens"],
                    ),
                    "cost_usd": report_scope_usage(
                        total_cost,
                        cross_report_provider_usage["estimated_cost_usd"],
                    ),
                    "combined_run_provider_calls": total_provider_calls,
                    "combined_run_input_tokens": total_input_tokens,
                    "combined_run_output_tokens": total_output_tokens,
                    "combined_run_cost_usd": total_cost,
                    "file_search_calls": results[0]["file_search_calls"],
                    "bounded_automatic_repair": any(
                        bool(result["bounded_automatic_repair"]) for result in results
                    ),
                    "automatic_repair_count": sum(
                        int(result["automatic_repair_count"]) for result in results
                    ),
                    "structured_output_repair_calls": sum(
                        int(result["structured_output_repair_calls"])
                        for result in results
                    ),
                    "workflow_retry_count": queue_timing["automatic_queue_retry_count"],
                    "operator_intervention_count": _cohort_operator_intervention_count(
                        state_db=settings.state_db,
                        root_workflow_id=root_workflow_id,
                    ),
                    "queue_timing": queue_timing,
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
        if reuse_event_handler is not None and reuse_events_path.is_file():
            cohort_metrics["validation_reuse_telemetry"] = (
                _validation_reuse_telemetry_summary(
                    reuse_events_path, reuse_event_handler
                )
            )
        cohort_metrics["duration_seconds"] = (
            round(
                (report_terminal_observed_monotonic or terminal_observed_monotonic)
                - started_at,
                3,
            )
            if terminal_observed_monotonic is not None
            else _finish_frozen_cohort_results(
                results, started_at, retain_member_duration=False
            )
        )
        cohort_metrics["end_to_end_duration_seconds"] = (
            round(terminal_observed_monotonic - started_at, 3)
            if terminal_observed_monotonic is not None
            else cohort_metrics["duration_seconds"]
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
                    "file_search_calls": None,
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
                source_path=source_path,
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
    drain_cross_report_handoffs: bool = False,
) -> dict[str, Any]:
    """Drain the report cohort and, when enabled, its isolated handoff queues."""

    control = load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path=str(config_path)), ctx
    )
    deadline = time.monotonic() + max(1, max_duration_seconds)
    started_at = time.monotonic()
    reports_terminal_at: float | None = None
    reports_terminal_at_utc = ""
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
        reports_terminal = all(
            state in {"awaiting_review", "published", "failed"}
            for state in states.values()
        )
        now = time.monotonic()
        if reports_terminal and reports_terminal_at is None:
            reports_terminal_at = now
            reports_terminal_at_utc = datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            )
        handoffs_terminal = (
            _cross_report_handoffs_terminal(
                state_db=state_db, root_workflow_id=root_workflow_id
            )
            if drain_cross_report_handoffs and reports_terminal
            else not drain_cross_report_handoffs
        )
        if reports_terminal and handoffs_terminal:
            return {
                "core_reports_terminal_wall_seconds": round(
                    (reports_terminal_at or now) - started_at, 3
                ),
                "core_reports_terminal_monotonic": reports_terminal_at,
                "core_reports_terminal_at_utc": reports_terminal_at_utc,
                "cross_report_handoff_drain_wall_seconds": round(
                    max(0.0, now - reports_terminal_at),
                    3
                    if drain_cross_report_handoffs and reports_terminal_at is not None
                    else 0.0,
                ),
                "cross_report_handoffs_terminal": handoffs_terminal,
            }
        if supervisor.completed_job_count == 0:
            time.sleep(1)
    return {
        "core_reports_terminal_wall_seconds": (
            round(reports_terminal_at - started_at, 3)
            if reports_terminal_at is not None
            else None
        ),
        "core_reports_terminal_monotonic": reports_terminal_at,
        "core_reports_terminal_at_utc": reports_terminal_at_utc,
        "cross_report_handoff_drain_wall_seconds": (
            round(max(0.0, time.monotonic() - reports_terminal_at), 3)
            if drain_cross_report_handoffs and reports_terminal_at is not None
            else 0.0
        ),
        "cross_report_handoffs_terminal": (
            _cross_report_handoffs_terminal(
                state_db=state_db, root_workflow_id=root_workflow_id
            )
            if drain_cross_report_handoffs
            else True
        ),
    }


def _cross_report_handoffs_terminal(*, state_db: str, root_workflow_id: str) -> bool:
    """Require cohort handoff jobs and outbox rows to reach durable terminal state."""

    handoff_marks = ",".join("?" for _ in _CROSS_REPORT_QUEUE_NAMES)
    descendant_marks = ",".join("?" for _ in _CROSS_REPORT_DESCENDANT_QUEUE_NAMES)
    with sqlite3.connect(state_db) as conn:
        job_rows = conn.execute(
            f"""
            SELECT status FROM workflow_jobs
            WHERE root_workflow_id=? AND (
              queue_name IN ({handoff_marks})
              OR (queue_name IN ({descendant_marks})
                  AND (entity_type IN ('briefing','signal')
                       OR queue_name='wordpress_projection'))
            )
            """,
            (
                root_workflow_id,
                *_CROSS_REPORT_QUEUE_NAMES,
                *_CROSS_REPORT_DESCENDANT_QUEUE_NAMES,
            ),
        ).fetchall()
        outbox_rows = conn.execute(
            f"""
            SELECT status FROM workflow_outbox
            WHERE root_workflow_id=? AND queue_name IN ({descendant_marks})
            """,
            (root_workflow_id, *_CROSS_REPORT_DESCENDANT_QUEUE_NAMES),
        ).fetchall()
    return all(
        str(row[0]) in _CROSS_REPORT_TERMINAL_STATUSES for row in job_rows
    ) and all(str(row[0]) in {"materialised", "dead_letter"} for row in outbox_rows)


def _collect_cross_report_handoff_evidence(
    *,
    state_db: str,
    signal_store_db: str,
    usage_db_path: str,
    root_workflow_id: str,
    ctx,
) -> dict[str, Any]:
    """Retain bounded queue, Briefing, Signal-manifest, and usage evidence."""

    handoff_marks = ",".join("?" for _ in _CROSS_REPORT_QUEUE_NAMES)
    descendant_marks = ",".join("?" for _ in _CROSS_REPORT_DESCENDANT_QUEUE_NAMES)
    with sqlite3.connect(state_db) as conn:
        job_rows = conn.execute(
            f"""
            SELECT job_id,queue_name,status,entity_type,attempt_count,
                   output_reference,output_content_hash,started_at_utc,
                   completed_at_utc
            FROM workflow_jobs
            WHERE root_workflow_id=? AND (
              queue_name IN ({handoff_marks})
              OR (queue_name IN ({descendant_marks})
                  AND (entity_type IN ('briefing','signal')
                       OR queue_name='wordpress_projection'))
            )
            ORDER BY queue_name,job_id
            """,
            (
                root_workflow_id,
                *_CROSS_REPORT_QUEUE_NAMES,
                *_CROSS_REPORT_DESCENDANT_QUEUE_NAMES,
            ),
        ).fetchall()
        outbox_nonterminal_count = int(
            conn.execute(
                f"""
                SELECT COUNT(*) FROM workflow_outbox
                WHERE root_workflow_id=? AND queue_name IN ({descendant_marks})
                  AND status NOT IN ('materialised','dead_letter')
                """,
                (root_workflow_id, *_CROSS_REPORT_DESCENDANT_QUEUE_NAMES),
            ).fetchone()[0]
        )
        signal_publication_job_count = int(
            conn.execute(
                """SELECT COUNT(*) FROM workflow_jobs
                WHERE root_workflow_id=? AND queue_name='wordpress_publish'
                  AND entity_type IN ('signal','briefing')""",
                (root_workflow_id,),
            ).fetchone()[0]
        )
        opportunity_rows = conn.execute(
            """SELECT generation_job_id,source_hashes_json,publisher_ids_json
            FROM workflow_briefing_opportunities
            WHERE generation_job_id<>''"""
        ).fetchall()
    job_status_counts: dict[str, dict[str, int]] = {}
    job_ids: list[str] = []
    for row in job_rows:
        job_id, queue_name, status = str(row[0]), str(row[1]), str(row[2])
        job_ids.append(job_id)
        status_counts = job_status_counts.setdefault(queue_name, {})
        status_counts[status] = status_counts.get(status, 0) + 1
    queue_terminal = _cross_report_handoffs_terminal(
        state_db=state_db, root_workflow_id=root_workflow_id
    )
    terminal_failure_count = sum(
        1 for row in job_rows if str(row[2]) in {"blocked", "dead_letter", "cancelled"}
    )

    opportunities_by_job = {
        str(job_id): (
            _json_string_set(source_hashes_json),
            _json_string_set(publisher_ids_json),
        )
        for job_id, source_hashes_json, publisher_ids_json in opportunity_rows
    }
    briefing_generation_rows = [
        row for row in job_rows if str(row[1]) == "briefing_generation"
    ]
    briefing_valid_multireport_count = 0
    briefing_valid_multireport_job_ids: list[str] = []
    briefing_valid_multireport_execution_seconds: list[float] = []
    briefing_duration_complete = True
    for row in briefing_generation_rows:
        job_id = str(row[0])
        if str(row[2]) != "succeeded" or not str(row[5]) or not str(row[6]):
            continue
        source_hashes, publishers = opportunities_by_job.get(job_id, (set(), set()))
        if len(source_hashes) >= 2 and len(publishers) >= 2:
            briefing_valid_multireport_count += 1
            briefing_valid_multireport_job_ids.append(job_id)
            elapsed_seconds = _workflow_job_elapsed_seconds(row[7], row[8])
            if elapsed_seconds is None:
                briefing_duration_complete = False
            else:
                briefing_valid_multireport_execution_seconds.append(elapsed_seconds)

    signal_manifest_hashes: list[str] = []
    signal_manifest_readback_count = 0
    signal_manifest_replay_count = 0
    signal_manifest_mutation_preserved = False
    single_source_group_count = 0
    single_source_hold_count = 0
    single_source_unsafe_count = 0
    signal_multireport_group_count = 0
    signal_hold_reason_counts: dict[str, int] = {}
    signal_path = Path(signal_store_db)
    if signal_path.is_file():
        with sqlite3.connect(signal_path) as conn:
            table_exists = conn.execute(
                """SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='signal_candidate_manifests'"""
            ).fetchone()
            manifest_rows = (
                conn.execute(
                    """SELECT manifest_sha256,extraction_request_id,group_id
                    FROM signal_candidate_manifests ORDER BY manifest_sha256"""
                ).fetchall()
                if table_exists
                else []
            )
        for manifest_hash, extraction_request_id, group_id in manifest_rows:
            manifest_hash = str(manifest_hash)
            signal_manifest_hashes.append(manifest_hash)
            request = SignalCandidateReadRequest(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                db_path=signal_store_db,
                manifest_sha256=manifest_hash,
                extraction_request_id=str(extraction_request_id),
                group_ids=[str(group_id)],
            )
            snapshot = read_signal_candidates(request, ctx)
            replayed_snapshot = read_signal_candidates(request, ctx)
            if (
                snapshot.manifest_sha256 != manifest_hash
                or len(snapshot.groups) != 1
                or snapshot.candidates != replayed_snapshot.candidates
                or snapshot.groups != replayed_snapshot.groups
                or replayed_snapshot.manifest_sha256 != manifest_hash
            ):
                continue
            signal_manifest_readback_count += 1
            signal_manifest_replay_count += 1
            group = snapshot.groups[0]
            source_count = len(set(group.source_report_ids))
            if source_count == 1:
                single_source_group_count += 1
                if (
                    group.publication_status == "held"
                    and group.publication_hold_reason == "signal_grounding_insufficient"
                ):
                    single_source_hold_count += 1
                    signal_hold_reason_counts["signal_grounding_insufficient"] = (
                        signal_hold_reason_counts.get(
                            "signal_grounding_insufficient", 0
                        )
                        + 1
                    )
                else:
                    single_source_unsafe_count += 1
            elif source_count >= 2:
                signal_multireport_group_count += 1
        if manifest_rows:
            signal_manifest_mutation_preserved = _verify_signal_manifest_immutable(
                signal_store_db=signal_store_db,
                manifest_hash=str(manifest_rows[0][0]),
                extraction_request_id=str(manifest_rows[0][1]),
                group_id=str(manifest_rows[0][2]),
                ctx=ctx,
            )

    cross_job_ids = [
        str(row[0])
        for row in job_rows
        if str(row[1]) in _CROSS_REPORT_QUEUE_NAMES
        or (
            str(row[1]) in _CROSS_REPORT_DESCENDANT_QUEUE_NAMES
            and (
                str(row[3]) in {"briefing", "signal"}
                or str(row[1]) == "wordpress_projection"
            )
        )
    ]
    usage = _read_workflow_job_usage(usage_db_path, cross_job_ids)
    briefing_usage = _read_workflow_job_usage(
        usage_db_path, briefing_valid_multireport_job_ids
    )
    briefing_execution_seconds = (
        round(sum(briefing_valid_multireport_execution_seconds), 3)
        if briefing_duration_complete
        and briefing_valid_multireport_count > 0
        and len(briefing_valid_multireport_execution_seconds)
        == briefing_valid_multireport_count
        else None
    )
    briefing_generation_success_count = sum(
        1 for row in briefing_generation_rows if str(row[2]) == "succeeded"
    )
    return {
        "enabled": True,
        "queue_terminal": queue_terminal,
        "queue_terminal_failure_count": terminal_failure_count,
        "queue_nonterminal_outbox_count": outbox_nonterminal_count,
        "job_status_counts": job_status_counts,
        "briefing_generation_success_count": briefing_generation_success_count,
        "briefing_validated_multireport_count": briefing_valid_multireport_count,
        "briefing_validated_multireport_execution_seconds": (
            briefing_execution_seconds
        ),
        "briefing_validated_multireport_provider_usage": briefing_usage,
        "signal_manifest_count": len(signal_manifest_hashes),
        "signal_manifest_hashes": signal_manifest_hashes,
        "signal_manifest_readback_verified_count": signal_manifest_readback_count,
        "signal_manifest_replay_verified_count": signal_manifest_replay_count,
        "signal_manifest_mutation_probe_scope": "representative_manifest",
        "signal_manifest_mutation_preserved": signal_manifest_mutation_preserved,
        "signal_single_source_group_count": single_source_group_count,
        "signal_single_source_insufficient_grounding_hold_count": (
            single_source_hold_count
        ),
        "signal_single_source_unsafe_group_count": single_source_unsafe_count,
        "signal_multireport_group_count": signal_multireport_group_count,
        "signal_hold_reason_counts": signal_hold_reason_counts,
        "signal_or_briefing_publication_job_count": signal_publication_job_count,
        "provider_usage": usage,
    }


def _json_string_set(raw: object) -> set[str]:
    try:
        values = json.loads(str(raw or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def _workflow_job_elapsed_seconds(
    started_at: object, completed_at: object
) -> float | None:
    if not str(started_at or "").strip() or not str(completed_at or "").strip():
        return None
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        completed = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=timezone.utc)
    elapsed = (completed - started).total_seconds()
    return round(elapsed, 3) if elapsed >= 0 else None


def _read_workflow_job_usage(usage_db_path: str, job_ids: list[str]) -> dict[str, Any]:
    if not job_ids or not Path(usage_db_path).is_file():
        return {
            "provider_calls": 0,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "tool_calls": 0,
            "estimated_cost_usd": 0.0,
        }
    marks = ",".join("?" for _ in job_ids)
    task_ids = tuple(f"workflow_job:{job_id}" for job_id in job_ids)
    with sqlite3.connect(usage_db_path) as conn:
        row = conn.execute(
            f"""SELECT COUNT(*),COALESCE(SUM(input_tokens),0),
                       COALESCE(SUM(cached_input_tokens),0),
                       COALESCE(SUM(output_tokens),0),COALESCE(SUM(tool_calls),0),
                       COALESCE(SUM(estimated_cost_usd),0.0)
                FROM llm_usage_events WHERE task_id IN ({marks})""",
            task_ids,
        ).fetchone()
    return {
        "provider_calls": int(row[0]),
        "input_tokens": int(row[1]),
        "cached_input_tokens": int(row[2]),
        "output_tokens": int(row[3]),
        "tool_calls": int(row[4]),
        "estimated_cost_usd": round(float(row[5]), 6),
    }


def _verify_signal_manifest_immutable(
    *,
    signal_store_db: str,
    manifest_hash: str,
    extraction_request_id: str,
    group_id: str,
    ctx,
) -> bool:
    """Prove a changed current view cannot alter an existing frozen manifest."""

    source_path = Path(signal_store_db)
    with tempfile.TemporaryDirectory(
        prefix="signal-manifest-mutation-", dir=source_path.parent
    ) as temp_root:
        isolated_db = str(Path(temp_root) / "signals.sqlite")
        with sqlite3.connect(source_path) as source_conn:
            with sqlite3.connect(isolated_db) as copy_conn:
                source_conn.backup(copy_conn)
        request = SignalCandidateReadRequest(
            schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
            db_path=isolated_db,
            manifest_sha256=manifest_hash,
            extraction_request_id=extraction_request_id,
            group_ids=[group_id],
        )
        original = read_signal_candidates(request, ctx)
        if len(original.groups) != 1 or not original.candidates:
            return False
        changed_summary = "Mutation probe for isolated frozen-manifest verification."
        changed_candidates = [
            replace(candidate, summary=changed_summary)
            for candidate in original.candidates
        ]
        changed_groups = [
            replace(group, summary=changed_summary) for group in original.groups
        ]
        changed = upsert_signal_candidates(
            SignalCandidateStoreRequest(
                schema_version=SIGNAL_CANDIDATE_SCHEMA_VERSION,
                db_path=isolated_db,
                extraction_request_id=extraction_request_id,
                candidates=changed_candidates,
                groups=changed_groups,
            ),
            ctx,
        )
        replayed = read_signal_candidates(request, ctx)
        return bool(
            changed.manifest_hashes.get(group_id) != manifest_hash
            and replayed.manifest_sha256 == manifest_hash
            and replayed.candidates == original.candidates
            and replayed.groups == original.groups
        )


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
        if readiness:
            readiness_status = str(readiness[0])
            if readiness_status == "awaiting_review":
                return "awaiting_review"
            if readiness_status == "approved":
                published = conn.execute(
                    "SELECT 1 FROM published WHERE file_id=? LIMIT 1",
                    (report_id,),
                ).fetchone()
                if published:
                    return "published"
                failed_publish = conn.execute(
                    """SELECT 1 FROM workflow_jobs
                    WHERE report_id=? AND root_workflow_id=?
                      AND queue_name='wordpress_publish'
                      AND status IN ('dead_letter','blocked','cancelled')
                    LIMIT 1""",
                    (report_id, root_workflow_id),
                ).fetchone()
                return "failed" if failed_publish else "publishing"
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
    *,
    settings,
    report_id: str,
    source_path: Path,
    validation_run_id: str,
    root_workflow_id: str,
    ctx,
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
        workflow_retry_count = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM workflow_job_attempts AS attempts
                JOIN workflow_jobs AS job ON job.job_id=attempts.job_id
                WHERE job.root_workflow_id=? AND job.report_id=?
                  AND attempts.outcome='retry_wait'
                """,
                (root_workflow_id, report_id),
            ).fetchone()[0]
        )
        failure = conn.execute(
            """
            SELECT error_code FROM workflow_jobs
            WHERE report_id=? AND root_workflow_id=? AND error_code<>''
            ORDER BY updated_at_utc LIMIT 1
            """,
            (report_id, root_workflow_id),
        ).fetchone()
        published_post = conn.execute(
            "SELECT wp_post_id,post_type FROM published WHERE file_id=? LIMIT 1",
            (report_id,),
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
        wordpress_stage_rows = tuple(
            (
                int(attempt_number),
                str(stage),
                str(terminal_outcome),
                str(output_artifact_ids_json or "[]"),
            )
            for attempt_number, stage, terminal_outcome, output_artifact_ids_json in conn.execute(
                """
                SELECT attempts.attempt_number, stages.stage,
                       stages.terminal_outcome, stages.output_artifact_ids_json
                FROM validation_run_entity_attempts AS attempts
                JOIN validation_run_stage_records AS stages
                  ON stages.attempt_id=attempts.attempt_id
                WHERE attempts.validation_run_id=? AND attempts.report_id=?
                  AND stages.stage IN ('wordpress_write','authenticated_readback')
                ORDER BY attempts.attempt_number, stages.stage
                """,
                (validation_run_id, report_id),
            ).fetchall()
        )
        repair_disposition_rows = conn.execute(
            """
            SELECT stages.repair_disposition,COUNT(*)
            FROM validation_run_stage_records AS stages
            JOIN validation_run_entity_attempts AS attempts
              ON attempts.attempt_id=stages.attempt_id
            WHERE attempts.validation_run_id=? AND attempts.report_id=?
              AND stages.repair_disposition IN ({})
            GROUP BY stages.repair_disposition
            """.format(",".join("?" for _ in _AUTOMATIC_REPAIR_DISPOSITIONS)),
            (
                validation_run_id,
                report_id,
                *sorted(_AUTOMATIC_REPAIR_DISPOSITIONS),
            ),
        ).fetchall()
        repair_disposition_counts = {
            str(disposition): int(count)
            for disposition, count in repair_disposition_rows
        }
        automatic_repair_count = sum(repair_disposition_counts.values())
        with sqlite3.connect(settings.usage_db_path) as usage_conn:
            structured_output_repair_calls = int(
                usage_conn.execute(
                    "SELECT COUNT(*) FROM llm_usage_events "
                    "WHERE run_id=? AND report_id=? "
                    "AND action='structured_output:repair'",
                    (root_workflow_id, report_id),
                ).fetchone()[0]
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
    file_search_calls = _read_usage_tool_call_count(
        usage_db_path=settings.usage_db_path, run_id=root_workflow_id
    )
    validation_pass = report_validation_passed(
        Path(settings.output_dir), source_path, report_id=report_id, ctx=ctx
    )
    retained_claim_counts = _read_retained_claim_counts(
        output_dir=Path(settings.output_dir),
        source_path=source_path,
        report_id=report_id,
        ctx=ctx,
    )
    terminal_failure = ""
    final_state = status
    if status not in {"awaiting_review", "published"}:
        # A bounded supervisor drain cannot leave a submitted member in a
        # non-terminal result. Preserve an observed queue failure when present;
        # otherwise make the elapsed bound explicit and typed.
        final_state = "failed"
        terminal_failure = str((failure or ("ias_canary_timeout",))[0])
    failure_diagnostic = (
        _read_failure_diagnostic(
            state_db=Path(settings.state_db),
            reports_db=Path(settings.reports_db),
            report_id=report_id,
            validation_run_id=validation_run_id,
            root_workflow_id=root_workflow_id,
            outer_code=terminal_failure,
        )
        if terminal_failure
        else {}
    )
    report_output_dir = Path(settings.output_dir) / slugify(source_path.name)
    publication_evidence = _wordpress_publication_evidence(
        stage_rows=wordpress_stage_rows,
        wordpress_post_id=int(published_post[0]) if published_post else None,
    )
    return {
        "workflow_attempt_count": attempts,
        "final_state": final_state,
        "awaiting_review": final_state == "awaiting_review",
        "published": final_state == "published",
        "wordpress_post_id": int(published_post[0]) if published_post else None,
        "wordpress_post_type": str(published_post[1]) if published_post else "",
        **publication_evidence,
        "bounded_automatic_repair": (
            automatic_repair_count > 0
            or workflow_retry_count > 0
            or any(report_output_dir.rglob("regeneration_candidate_audit_*.json"))
        ),
        "automatic_repair_count": automatic_repair_count,
        "repair_disposition_counts": repair_disposition_counts,
        "structured_output_repair_calls": structured_output_repair_calls,
        "workflow_retry_count": workflow_retry_count,
        "operator_intervention": operator_intervention,
        "publication_readiness": (
            "pass" if readiness_payload.get("status") == "pass" else "fail"
        ),
        "validation": "pass" if validation_pass else "fail",
        "unsupported_retained_factual_claims": (
            retained_claim_counts[0] if retained_claim_counts is not None else None
        ),
        "unresolved_retained_factual_claims": (
            retained_claim_counts[1] if retained_claim_counts is not None else None
        ),
        "model_provider_calls": usage.call_count,
        "file_search_calls": file_search_calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost": usage.estimated_cost_usd,
        "terminal_failure_code": terminal_failure,
        **({"failure_diagnostic": failure_diagnostic} if failure_diagnostic else {}),
    }


def _replay_completed_wordpress_jobs(
    *, state_db: str, root_workflow_id: str, report_ids: tuple[str, ...], ctx
) -> dict[str, Any]:
    """Repeat completed durable submissions and prove they cause no new write."""

    if not report_ids:
        return {"status": "not_run", "reason": "no_report_ids"}
    marks = ",".join("?" for _ in report_ids)
    with sqlite3.connect(state_db) as conn:
        job_rows = conn.execute(
            """SELECT job_id,status,attempt_count FROM workflow_jobs
            WHERE queue_name='wordpress_publish' AND root_workflow_id=?
              AND report_id IN ("""
            + marks
            + ") ORDER BY job_id",
            (root_workflow_id, *report_ids),
        ).fetchall()
    completed = [row for row in job_rows if str(row[1]) == "succeeded"]
    before_publications = _published_snapshot(state_db, report_ids)
    replayed_job_ids: list[str] = []
    same_job_count = 0
    created_job_count = 0
    for job_id, _, _ in completed:
        job = get_workflow_job(state_db, str(job_id), ctx)
        if job is None or job.status != "succeeded":
            continue
        duplicate, created = enqueue_workflow_job(
            state_db,
            WorkflowJobSubmission(
                schema_version=job.schema_version,
                queue_name=job.queue_name,
                job_type=job.job_type,
                payload=load_workflow_job_payload(job),
                idempotency_key=job.idempotency_key,
                deduplication_scope=job.deduplication_scope,
                workflow_version=job.workflow_version,
                root_workflow_id=job.root_workflow_id,
                parent_job_id=job.parent_job_id,
                trigger_event_id=job.trigger_event_id,
                correlation_id=job.correlation_id,
                entity_type=job.entity_type,
                entity_id=job.entity_id,
                publisher_id=job.publisher_id,
                source_identity_id=job.source_identity_id,
                report_id=job.report_id,
                priority=job.priority,
                max_attempts=job.max_attempts,
                budget_profile=job.budget_profile,
                execution_plan_hash=job.execution_plan_hash,
            ),
            ctx,
        )
        created_job_count += int(created)
        if duplicate.job_id == job.job_id:
            same_job_count += 1
            replayed_job_ids.append(job.job_id)
    after_publications = _published_snapshot(state_db, report_ids)
    with sqlite3.connect(state_db) as conn:
        after_attempts = conn.execute(
            """SELECT job_id,status,attempt_count FROM workflow_jobs
            WHERE queue_name='wordpress_publish' AND root_workflow_id=?
              AND report_id IN ("""
            + marks
            + ") ORDER BY job_id",
            (root_workflow_id, *report_ids),
        ).fetchall()
    attempt_counts_unchanged = [
        (str(row[0]), str(row[1]), int(row[2])) for row in job_rows
    ] == [(str(row[0]), str(row[1]), int(row[2])) for row in after_attempts]
    publication_rows_unchanged = before_publications == after_publications
    status = (
        "verified"
        if completed
        and len(completed) == len(before_publications)
        and len(replayed_job_ids) == len(completed)
        and created_job_count == 0
        and attempt_counts_unchanged
        and publication_rows_unchanged
        else "not_run"
        if not completed
        else "failed"
    )
    return {
        "status": status,
        "completed_publication_jobs": len(completed),
        "first_attempt_publication_jobs": sum(int(row[2]) == 1 for row in completed),
        "duplicate_submissions": len(replayed_job_ids),
        "same_job_ids": same_job_count == len(completed),
        "created_duplicate_jobs": created_job_count,
        "attempt_counts_unchanged": attempt_counts_unchanged,
        "published_rows_unchanged": publication_rows_unchanged,
        "wordpress_post_ids": [row[1] for row in before_publications],
        "additional_wordpress_writes": (0 if status == "verified" else None),
    }


def _published_snapshot(
    state_db: str, report_ids: tuple[str, ...]
) -> list[tuple[str, int, str]]:
    if not report_ids:
        return []
    marks = ",".join("?" for _ in report_ids)
    with sqlite3.connect(state_db) as conn:
        rows = conn.execute(
            f"SELECT file_id,wp_post_id,post_type FROM published "
            f"WHERE file_id IN ({marks}) ORDER BY file_id",
            report_ids,
        ).fetchall()
    return [(str(row[0]), int(row[1]), str(row[2])) for row in rows]


def _read_failure_diagnostic(
    *,
    state_db: Path,
    reports_db: Path,
    report_id: str,
    validation_run_id: str,
    root_workflow_id: str,
    outer_code: str,
) -> dict[str, Any]:
    """Read one bounded terminal cause from canonical retained artifacts/state."""

    if outer_code == "validation_failed":
        validation = _read_validation_failure_diagnostic(
            reports_db=reports_db,
            report_id=report_id,
            validation_run_id=validation_run_id,
            outer_code=outer_code,
        )
        if validation:
            return validation
    remediation = _read_remediation_failure_diagnostic(
        state_db=state_db,
        report_id=report_id,
        root_workflow_id=root_workflow_id,
        outer_code=outer_code,
    )
    if remediation:
        return remediation
    return _read_validation_failure_diagnostic(
        reports_db=reports_db,
        report_id=report_id,
        validation_run_id=validation_run_id,
        outer_code=outer_code,
    )


def _read_validation_failure_diagnostic(
    *, reports_db: Path, report_id: str, validation_run_id: str, outer_code: str
) -> dict[str, Any]:
    if not reports_db.is_file():
        return {}
    try:
        with sqlite3.connect(reports_db) as conn:
            rows = conn.execute(
                """
                SELECT stages.stage, stages.failure_code, stages.repair_disposition,
                       stages.output_artifact_ids_json
                FROM validation_run_stage_records AS stages
                JOIN validation_run_entity_attempts AS attempts
                  ON attempts.attempt_id=stages.attempt_id
                WHERE attempts.validation_run_id=? AND attempts.report_id=?
                  AND stages.failure_code<>''
                ORDER BY stages.completed_at_utc DESC
                """,
                (validation_run_id, report_id),
            ).fetchall()
    except sqlite3.Error:
        return {}
    for stage, failure_code, repair_disposition, artifact_ids in rows:
        if outer_code == "validation_failed" and str(failure_code or "") != outer_code:
            continue
        issue = _read_validation_issue(artifact_ids)
        if issue is None:
            # Terminal checkpoint stages record artifacts that carry no
            # validation-issues document; keep scanning older failing stages
            # so a generic outer code cannot hide the retained inner finding.
            continue
        affected_section = _diagnostic_token(issue.get("affected_section"))
        entity_id = _diagnostic_token(issue.get("entity_id"))
        evidence_ids = issue.get("evidence_ids")
        evidence_id = (
            _diagnostic_token(evidence_ids[0])
            if isinstance(evidence_ids, list) and evidence_ids
            else ""
        )
        rule_id = _diagnostic_token(issue.get("rule_id"))
        context = {
            key: value
            for key, value in (
                ("affected_section", affected_section),
                ("evidence_id", evidence_id),
            )
            if value
        }
        return {
            "stage": _diagnostic_token(stage),
            "outer_code": _diagnostic_token(outer_code),
            "inner_error_class": "",
            "validator_rule": rule_id,
            "artifact_family": affected_section,
            "claim_or_entity_id": entity_id or evidence_id,
            "repair_attempt": 1 if repair_disposition == "targeted_repair" else 0,
            "error_context": context,
        }
    return {}


def _read_validation_issue(artifact_ids: object) -> dict[str, Any] | None:
    try:
        paths = json.loads(str(artifact_ids or "[]"))
    except json.JSONDecodeError:
        return None
    if not isinstance(paths, list):
        return None
    for value in paths:
        try:
            payload = json.loads(Path(str(value)).read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        issues = payload.get("issues") if isinstance(payload, dict) else None
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if isinstance(issue, dict) and issue.get("severity") == "error":
                return issue
    return None


def _read_remediation_failure_diagnostic(
    *, state_db: Path, report_id: str, root_workflow_id: str, outer_code: str
) -> dict[str, Any]:
    if not state_db.is_file():
        return {}
    try:
        with sqlite3.connect(state_db) as conn:
            row = conn.execute(
                """
                SELECT failed_stage, error_code, diagnostics_json
                FROM remediation_records
                WHERE report_id=? AND run_id=? AND error_code=?
                ORDER BY updated_at_utc DESC
                LIMIT 1
                """,
                (report_id, root_workflow_id, outer_code),
            ).fetchone()
    except sqlite3.Error:
        return {}
    if row is None:
        return {}
    stage, error_code, raw_diagnostics = row
    try:
        diagnostics = json.loads(str(raw_diagnostics or "{}"))
    except json.JSONDecodeError:
        diagnostics = {}
    context = diagnostics.get("error_context") if isinstance(diagnostics, dict) else {}
    context = context if isinstance(context, dict) else {}
    artifact_family = _diagnostic_token(context.get("artifact_family"))
    claim_or_entity_id = _first_diagnostic_identifier(context)
    return {
        "stage": _failure_stage(
            stage=_diagnostic_token(stage),
            outer_code=_diagnostic_token(error_code),
            artifact_family=artifact_family,
        ),
        "outer_code": _diagnostic_token(outer_code),
        "inner_error_class": _diagnostic_token(context.get("error_class")),
        "validator_rule": _diagnostic_token(context.get("rule_id")),
        "artifact_family": artifact_family,
        "claim_or_entity_id": claim_or_entity_id,
        "repair_attempt": _repair_attempt(context.get("repair_attempt")),
        "error_context": {
            key: token
            for key, value in sorted(context.items())
            if isinstance(value, str)
            if (token := _diagnostic_token(value))
        },
    }


def _failure_stage(*, stage: str, outer_code: str, artifact_family: str) -> str:
    if stage and stage != "report_pipeline":
        return stage
    if outer_code.startswith("cover_"):
        return "rendering"
    if artifact_family or any(
        token in outer_code for token in ("artifact", "provenance", "reference")
    ):
        return "artifact_generation"
    return stage or "report_pipeline"


def _first_diagnostic_identifier(context: dict[str, Any]) -> str:
    for key in ("claim_id", "entity_id", "evidence_id"):
        if token := _diagnostic_token(context.get(key)):
            return token
    for key in (
        "missing_claim_ids",
        "missing_evidence_ids",
        "missing_references",
        "missing_reference_ids",
    ):
        values = context.get(key)
        if isinstance(values, list):
            for value in values:
                if token := _diagnostic_token(value):
                    return token
    return ""


def _repair_attempt(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return 0
    return max(0, min(9, value))


def _diagnostic_token(value: object) -> str:
    token = str(value or "").strip()
    return (
        token
        if token and len(token) <= 128 and set(token) <= _DIAGNOSTIC_TOKEN_CHARS
        else ""
    )


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


def _report_analysis_pack_path(
    *,
    output_dir: Path,
    source_path: Path,
    report_id: str,
    pack_name: str,
    ctx,
) -> Path:
    response = resolve_report_analysis_pack_path(
        AnalysisPackPathRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            report_id=ReportId(report_id),
            pack_name=pack_name,
            report_slug=slugify(source_path.name),
        ),
        ctx,
    )
    return Path(response.output_path)


def report_validation_passed(
    output_dir: Path, source_path: Path, *, report_id: str, ctx
) -> bool:
    """Read final validation from the artifact belonging to one source report."""

    validation_path = _report_analysis_pack_path(
        output_dir=output_dir,
        source_path=source_path,
        report_id=report_id,
        pack_name="validation",
        ctx=ctx,
    )
    try:
        return (
            json.loads(validation_path.read_text(encoding="utf-8")).get("status")
            == "pass"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _read_retained_claim_counts(
    *, output_dir: Path, source_path: Path, report_id: str, ctx
) -> tuple[int, int] | None:
    """Read final retained-claim counts only when report and source identities match."""

    validation_path = _report_analysis_pack_path(
        output_dir=output_dir,
        source_path=source_path,
        report_id=report_id,
        pack_name="validation_retained_claim_validation_candidate",
        ctx=ctx,
    )
    try:
        payload = json.loads(validation_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    identity = payload.get("validation_identity")
    if not isinstance(identity, dict):
        return None
    source_hash = hashlib.md5(
        source_path.read_bytes(), usedforsecurity=False
    ).hexdigest()
    if (
        identity.get("report_id") != report_id
        or identity.get("source_md5") != source_hash
        or type(payload.get("unsupported_factual_count")) is not int
        or type(payload.get("unresolved_factual_count")) is not int
    ):
        return None
    return (
        int(payload["unsupported_factual_count"]),
        int(payload["unresolved_factual_count"]),
    )


def _read_usage_tool_call_count(*, usage_db_path: str, run_id: str) -> int:
    """Read existing provider tool calls from the canonical LLM usage ledger."""

    if not Path(usage_db_path).is_file():
        return 0
    with sqlite3.connect(usage_db_path) as conn:
        return int(
            conn.execute(
                "SELECT COALESCE(SUM(tool_calls),0) "
                "FROM llm_usage_events WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
        )


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
        "published": False,
        "wordpress_post_id": None,
        "wordpress_post_type": "",
        "wordpress_created_this_run": False,
        "wordpress_authenticated_readback": False,
        "bounded_automatic_repair": False,
        "operator_intervention": False,
        "publication_readiness": "fail",
        "validation": "fail",
        "model_provider_calls": 0,
        "file_search_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost": 0.0,
        "automatic_repair_count": 0,
        "repair_disposition_counts": {},
        "structured_output_repair_calls": 0,
        "workflow_retry_count": 0,
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
        if result["final_state"] not in {"awaiting_review", "published", "failed"}:
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
    costs = [float(item["cost"]) for item in results if item.get("cost") is not None]
    durations = [
        float(item["total_duration_seconds"])
        for item in results
        if item.get("total_duration_seconds") is not None
    ]
    failures = [
        str(item.get("terminal_failure_code") or "")
        for item in results
        if str(item.get("terminal_failure_code") or "")
    ]
    terminal_states = {"awaiting_review", "published", "failed"}
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
        "published_report_count": sum(
            item.get("final_state") == "published" for item in admitted
        ),
        "first_attempt_published_rate": sum(
            item.get("final_state") == "published"
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
            item.get("final_state") not in {"awaiting_review", "published"}
            for item in admitted
        )
        / workflow_denominator,
        "typed_terminal_rate": sum(
            item.get("final_state") in {"awaiting_review", "published", "failed"}
            for item in admitted
        )
        / workflow_denominator,
        "operator_intervention_count": sum(
            bool(item.get("operator_intervention")) for item in results
        ),
        "failure_code_pareto": pareto,
        "mean_cost": (
            round(sum(costs) / denominator, 6) if len(costs) == count else "unavailable"
        ),
        "median_cost": (
            round(median(costs), 6) if len(costs) == count else "unavailable"
        ),
        "mean_duration_seconds": (
            round(sum(durations) / denominator, 3)
            if len(durations) == count
            else "unavailable"
        ),
        "median_duration_seconds": (
            round(median(durations), 3) if len(durations) == count else "unavailable"
        ),
    }
    if cohort_metrics is not None:
        per_report_attribution = bool(results) and all(
            item.get("metric_attribution") == "per_report_isolated_workflow"
            for item in results
        )
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
                "bounded_repair_rate": (
                    summary["bounded_repair_rate"]
                    if per_report_attribution
                    else "unavailable"
                ),
                "operator_intervention_count": cohort_metrics.get(
                    "operator_intervention_count", "unavailable"
                ),
                "mean_cost": (
                    summary["mean_cost"] if per_report_attribution else "unavailable"
                ),
                "median_cost": (
                    summary["median_cost"] if per_report_attribution else "unavailable"
                ),
                "mean_duration_seconds": (
                    summary["mean_duration_seconds"]
                    if per_report_attribution
                    else "unavailable"
                ),
                "median_duration_seconds": (
                    summary["median_duration_seconds"]
                    if per_report_attribution
                    else "unavailable"
                ),
            }
        )
    return summary
