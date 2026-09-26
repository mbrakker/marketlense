"""Replay frozen retained repair failures through the production repair loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.drive import DriveFile
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_generation import ReportRuntimeState
from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId
from src.contracts.validation import ValidationIssue, ValidationReport
from src.contracts.validation_reliability import (
    ValidationReliabilityBuildRequest,
    ValidationReliabilityWriteRequest,
)
from src.contracts.validation_run_manifest import (
    ValidationRunManifestCreateRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.generators._report_generation_dependencies.analysis import (
    ReportAnalysisDependencies,
)
from src.generators.report_generation_shared import (
    merge_artifacts_into_payload,
    resolve_doc_map_metadata,
)
from src.generators.normalize_generator import normalize_report
from src.orchestrators._report_analysis_orchestrator.payload import (
    _ensure_report_payload_complete,
)
from src.orchestrators._report_generation_orchestrator.checkpoints import (
    _report_payload_from_dict,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _run_validation_regeneration_loop,
)
from src.orchestrators.admission_preflight_orchestrator import (
    admission_configuration_hash,
    admission_policy_hash,
)
from src.services import config_service, llm_service
from src.services.report_store_service import (
    create_validation_run_manifest,
    record_validation_run_manifest_stage,
)
from src.services.validation_reliability_service import (
    build_validation_reliability_artifact,
    validation_reliability_artifact_path,
    write_validation_reliability_artifact,
)
from src.utils.cache_utils import sha256_json
from src.utils.slugify import slugify

_SCHEMA_IDENTITY_PATHS = (
    "src/schemas/artifacts.schema.json",
    "src/schemas/regeneration_candidate_audit.schema.json",
    "src/schemas/regeneration_repair_decision.schema.json",
    "src/schemas/validation_report.schema.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_identity_sha256(workspace: Path) -> str:
    file_hashes = {name: _sha256(workspace / name) for name in _SCHEMA_IDENTITY_PATHS}
    encoded = json.dumps(
        file_hashes, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_json(path: Path, expected_sha256: str = "") -> dict[str, Any]:
    if expected_sha256 and _sha256(path) != expected_sha256:
        raise ValueError("frozen benchmark input hash mismatch")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("frozen benchmark input must be an object")
    return payload


def _benchmark_manifest(path: Path) -> tuple[dict[str, Any], str]:
    payload = _read_json(path)
    declared_hash = str(payload.get("manifest_sha256") or "")
    body = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    actual_hash = hashlib.sha256(
        (
            json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    ).hexdigest()
    if (
        payload.get("schema_version") != "2.0"
        or payload.get("frozen") is not True
        or declared_hash != actual_hash
    ):
        raise ValueError("frozen benchmark manifest is invalid")
    return payload, declared_hash


def _root_context(
    *,
    run_id: str,
    validation_run_id: str,
    cohort_id: str,
    configuration_hash: str,
    policy_hash: str,
    implementation_sha: str,
) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id=run_id,
        task_id="validation-repair-benchmark",
        span_id="validation-repair-benchmark",
        trace_id=run_id,
        producer_commit_sha=implementation_sha,
        validation_run_id=validation_run_id,
        cohort_id=cohort_id,
        workflow="report_analysis",
        stage="regeneration",
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
    )


def _build_repair_model_clients(settings: Any) -> tuple[Any, Any]:
    """Build the same scoped model service clients used by report workflows."""
    return (
        llm_service.build_client_for_settings(settings, scope="validation"),
        llm_service.build_client_for_settings(settings, scope="artifact_regeneration"),
    )


def _validation_report(payload: dict[str, Any]) -> ValidationReport:
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raise ValueError("retained initial validation issues are missing")
    issues = [
        ValidationIssue(
            message=str(item.get("message") or ""),
            severity=str(item.get("severity") or "error"),
            affected_section=str(item.get("affected_section") or ""),
            rule_id=str(item.get("rule_id") or ""),
            repair_target=str(item.get("repair_target") or ""),
            entity_id=str(item.get("entity_id") or ""),
            evidence_ids=[str(value) for value in item.get("evidence_ids", [])],
            schema_version=str(item.get("schema_version") or "1.0"),
        )
        for item in raw_issues
        if isinstance(item, dict)
    ]
    if not issues:
        raise ValueError("frozen repair case has no initial validation failures")
    return ValidationReport(
        schema_version=str(payload.get("schema_version") or "1.0"),
        status="fail",
        severity="error",
        issues=issues,
    )


def _case_paths(case: dict[str, Any], workspace: Path) -> tuple[dict[str, Path], Path]:
    files = case.get("input_files")
    if not isinstance(files, dict):
        raise ValueError("frozen case input file references are missing")
    paths: dict[str, Path] = {}
    for name, record in files.items():
        if not isinstance(record, dict):
            raise ValueError("frozen case file reference is invalid")
        relative = Path(str(record.get("path") or ""))
        path = (workspace / relative).resolve()
        if not path.is_file() or not path.is_relative_to(workspace.resolve()):
            raise ValueError("frozen case input file is missing or outside workspace")
        if _sha256(path) != str(record.get("sha256") or ""):
            raise ValueError("frozen case input file hash mismatch")
        paths[str(name)] = path
    artifacts_path = paths.get("artifacts")
    if artifacts_path is None:
        raise ValueError("frozen case original artifacts are missing")
    artifacts = _read_json(artifacts_path)
    if sha256_json(artifacts) != str(
        case.get("original_artifact_canonical_sha256") or ""
    ):
        raise ValueError("frozen case canonical artifact hash mismatch")
    return paths, artifacts_path


def _pointer_value(payload: object, pointer: object) -> object:
    if (
        not isinstance(pointer, list)
        or not pointer
        or not all(isinstance(item, str) and item for item in pointer)
    ):
        raise ValueError("pre-repair payload pointer is invalid")
    current = payload
    for item in pointer:
        if not isinstance(current, dict) or item not in current:
            raise ValueError("pre-repair payload pointer is unresolved")
        current = current[item]
    return current


def _report_payload_from_frozen_state(
    raw_payload: object,
    *,
    expected_sha256: str,
    label: str,
) -> ReportPayload:
    if not isinstance(raw_payload, dict):
        raise ValueError(f"{label} ReportPayload seed must be an object")

    def require_fields(
        raw: object, expected: tuple[str, ...], field_label: str
    ) -> None:
        if not isinstance(raw, dict) or set(raw) != set(expected):
            raise ValueError(f"{label} {field_label} payload fields are incomplete")

    require_fields(
        raw_payload,
        tuple(field.name for field in fields(ReportPayload)),
        "ReportPayload",
    )
    require_fields(
        raw_payload.get("quote"),
        tuple(field.name for field in fields(Quote)),
        "Quote",
    )
    require_fields(
        raw_payload.get("figure"),
        tuple(field.name for field in fields(Figure)),
        "Figure",
    )
    assets = raw_payload.get("_figure_assets")
    if not isinstance(assets, list):
        raise ValueError(f"{label} ReportPayload figure assets are invalid")
    asset_fields = tuple(field.name for field in fields(ReportFigureAsset))
    for index, asset in enumerate(assets):
        require_fields(asset, asset_fields, f"figure asset {index}")

    if sha256_json(raw_payload) != expected_sha256:
        raise ValueError(f"{label} ReportPayload canonical hash mismatch")
    try:
        payload = _report_payload_from_dict(raw_payload)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} ReportPayload seed cannot be decoded") from exc
    if payload.to_dict() != raw_payload:
        raise ValueError(f"{label} ReportPayload seed does not round-trip exactly")
    return payload


def _pre_repair_base_payload(
    *,
    case: dict[str, Any],
    paths: dict[str, Path],
    report_context: dict[str, Any],
    evidence_packs: dict[str, dict[str, Any]],
    case_ctx: RunContext,
) -> ReportPayload:
    state = case.get("pre_repair_state")
    if not isinstance(state, dict):
        raise ValueError("frozen case pre-repair state is missing")
    input_name = str(state.get("input_file") or "")
    checkpoint_path = paths.get(input_name)
    if checkpoint_path is None:
        raise ValueError("frozen case pre-repair checkpoint reference is missing")
    checkpoint = _read_json(checkpoint_path)
    payload_data = _pointer_value(checkpoint, state.get("payload_pointer"))
    expected_sha = str(state.get("canonical_sha256") or "")
    case_label = str(case.get("case_id") or case.get("report_id") or "case")

    def require_caption_generation_disabled() -> None:
        source_cohort_name = str(state.get("source_cohort_file") or "")
        source_cohort_path = paths.get(source_cohort_name)
        if source_cohort_path is None:
            raise ValueError("frozen source configuration reference is missing")
        source_cohort = _read_json(source_cohort_path)
        configuration = source_cohort.get("configuration_snapshot")
        if (
            not isinstance(configuration, dict)
            or configuration.get("figure_caption_enabled") is not False
        ):
            raise ValueError(
                "frozen source figure-caption configuration is unsupported"
            )

    if state.get("kind") == "analysis_checkpoint":
        return _report_payload_from_frozen_state(
            payload_data,
            expected_sha256=expected_sha,
            label=case_label,
        )
    if state.get("kind") == "analysis_checkpoint_reconstruction":
        require_caption_generation_disabled()
        analysis_state = (
            checkpoint.get("payload", {}).get("analysis")
            if isinstance(checkpoint.get("payload"), dict)
            else None
        )
        source_artifacts = (
            analysis_state.get("artifacts_payload")
            if isinstance(analysis_state, dict)
            else None
        )
        source_artifact_sha = str(state.get("source_artifact_canonical_sha256") or "")
        if (
            not isinstance(source_artifacts, dict)
            or sha256_json(source_artifacts) != source_artifact_sha
            or source_artifact_sha
            != str(case.get("original_artifact_canonical_sha256") or "")
        ):
            raise ValueError("analysis checkpoint artifact identity does not match")
        source_payload = _report_payload_from_frozen_state(
            payload_data,
            expected_sha256=str(state.get("source_payload_sha256") or ""),
            label=f"{case_label} production analysis state",
        )
        normalized = normalize_report(source_payload, case_ctx)
        if sha256_json(normalized.to_dict()) != expected_sha:
            raise ValueError(f"{case_label} reconstructed ReportPayload hash mismatch")
        return normalized
    if state.get("kind") != "selection_checkpoint_reconstruction":
        raise ValueError("frozen case pre-repair state kind is unsupported")

    payload = _report_payload_from_frozen_state(
        payload_data,
        expected_sha256=str(state.get("selection_payload_sha256") or ""),
        label=f"{case_label} selection",
    )
    source_checkpoint = checkpoint.get("payload")
    source_state = (
        source_checkpoint.get("source") if isinstance(source_checkpoint, dict) else None
    )
    title_resolution = (
        source_state.get("title_resolution") if isinstance(source_state, dict) else None
    )
    source_title = (
        str(title_resolution.get("title") or "").strip()
        if isinstance(title_resolution, dict)
        else ""
    )

    taxonomy = state.get("taxonomy_ids")
    categories = state.get("category_ids")
    if (
        not isinstance(taxonomy, list)
        or not all(isinstance(item, str) and item for item in taxonomy)
        or not isinstance(categories, list)
        or not all(isinstance(item, str) and item for item in categories)
    ):
        raise ValueError("frozen case taxonomy or category stage outputs are invalid")
    source_state_db_name = str(state.get("source_state_db_file") or "")
    if not source_state_db_name or source_state_db_name not in paths:
        raise ValueError("frozen taxonomy and category source database is missing")
    stage_provenance = state.get("stage_output_provenance")
    if stage_provenance != {
        "category_ids_stage": "category_fit",
        "region_and_time_period_input": "report_context",
        "taxonomy_ids_stage": "taxonomy",
        "taxonomy_and_category_stage_records_file": source_state_db_name,
    }:
        raise ValueError("frozen taxonomy and category stage provenance is invalid")
    if not isinstance(report_context.get("region"), str) or not isinstance(
        report_context.get("time_period"), str
    ):
        raise ValueError("frozen report context region or time period is missing")

    require_caption_generation_disabled()

    source_publisher = str(state.get("source_publisher") or "").strip()
    doc_map = evidence_packs.get("doc_map")
    if not isinstance(doc_map, dict):
        raise ValueError("frozen doc map is missing")
    artifact_doc_map = dict(doc_map)
    if source_publisher:
        artifact_doc_map["publisher"] = source_publisher
    doc_map_title, resolved_publisher, _, _ = resolve_doc_map_metadata(artifact_doc_map)

    payload.taxonomy = list(taxonomy)
    payload.categories = list(categories)
    payload.region = report_context["region"]
    payload.time_period = report_context["time_period"]
    if doc_map_title and not source_title:
        payload.title = doc_map_title
    if source_publisher:
        payload.publisher = source_publisher
    elif resolved_publisher:
        payload.publisher = resolved_publisher

    normalized = normalize_report(payload, case_ctx)
    if sha256_json(normalized.to_dict()) != expected_sha:
        raise ValueError(f"{case_label} reconstructed ReportPayload hash mismatch")
    return normalized


def _verify_reconstructed_analysis_payload(
    *,
    case: dict[str, Any],
    paths: dict[str, Path],
    state: dict[str, Any],
    merged_payload: ReportPayload,
) -> None:
    if state.get("kind") != "analysis_checkpoint_reconstruction":
        return
    input_name = str(state.get("input_file") or "")
    checkpoint_path = paths.get(input_name)
    if checkpoint_path is None:
        raise ValueError("frozen analysis checkpoint reference is missing")
    checkpoint = _read_json(checkpoint_path)
    normalized_data = _pointer_value(
        checkpoint, state.get("normalized_payload_pointer")
    )
    source_normalized = _report_payload_from_frozen_state(
        normalized_data,
        expected_sha256=str(state.get("source_normalized_payload_sha256") or ""),
        label=f"{case.get('case_id') or 'case'} persisted normalized payload",
    ).to_dict()
    replay_normalized = merged_payload.to_dict()
    # These two fields name resources from the original run. The replay uses
    # its own isolated vector/evidence resources; all semantic payload fields
    # must remain byte-for-byte equivalent after canonical serialization.
    for field_name in ("_evidence_packs", "_vector_store_id"):
        source_normalized.pop(field_name, None)
        replay_normalized.pop(field_name, None)
    if source_normalized != replay_normalized:
        raise ValueError("reconstructed payload differs from persisted analysis state")


def _preflight_benchmark_cases(
    cases: list[Any], workspace: Path, root_ctx: RunContext
) -> list[dict[str, Any]]:
    required_evidence = {
        "doc_map",
        "findings",
        "limitations",
        "methods",
        "quote_candidates",
        "scope",
    }
    prepared_cases: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("frozen benchmark case must be an object")
        paths, _ = _case_paths(case, workspace)
        artifacts = _read_json(paths["artifacts"])
        evidence_packs = {
            name: _read_json(paths[name]) for name in required_evidence if name in paths
        }
        if set(evidence_packs) != required_evidence:
            raise ValueError("frozen benchmark evidence pack set is incomplete")
        report_context = _read_json(paths["report_context"])
        initial_validation = _validation_report(_read_json(paths["initial_validation"]))
        report_id = str(case.get("report_id") or "")
        if not report_id:
            raise ValueError("frozen benchmark report identity is missing")
        case_ctx = replace(
            root_ctx,
            task_id=f"report:{report_id}",
            span_id=f"report:{report_id}",
            report_id=report_id,
            source_identity_id=str(case.get("source_identity_id") or ""),
            publisher_id=str(
                case.get("publisher_id") or report_context.get("publisher") or ""
            ),
        )
        base_payload = _pre_repair_base_payload(
            case=case,
            paths=paths,
            report_context=report_context,
            evidence_packs=evidence_packs,
            case_ctx=case_ctx,
        )
        initial_payload = merge_artifacts_into_payload(
            deepcopy(base_payload), artifacts
        )
        state = case.get("pre_repair_state")
        if not isinstance(state, dict):
            raise ValueError("frozen case pre-repair state is missing")
        if sha256_json(initial_payload.to_dict()) != str(
            state.get("merged_canonical_sha256") or ""
        ):
            raise ValueError("frozen merged pre-repair ReportPayload hash mismatch")
        _verify_reconstructed_analysis_payload(
            case=case,
            paths=paths,
            state=state,
            merged_payload=initial_payload,
        )
        _ensure_report_payload_complete(
            initial_payload,
            artifacts=artifacts,
            ctx=case_ctx,
            file_id=report_id,
            stage="benchmark_preflight",
        )
        prepared_cases.append(
            {
                "case": case,
                "paths": paths,
                "artifacts": artifacts,
                "evidence_packs": evidence_packs,
                "report_context": report_context,
                "initial_validation": initial_validation,
                "case_ctx": case_ctx,
                "base_payload": base_payload,
                "initial_payload": initial_payload,
            }
        )
    return prepared_cases


def replay_benchmark(
    *,
    manifest_path: Path,
    output_dir: Path,
    implementation_sha: str,
) -> dict[str, Any]:
    workspace = Path.cwd().resolve()
    actual_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual_sha != implementation_sha:
        raise ValueError("implementation SHA does not match the checked out revision")
    manifest, manifest_sha = _benchmark_manifest(manifest_path.resolve())
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("frozen benchmark has no cases")

    run_id = f"e13-repair-{implementation_sha[:12]}-{manifest_sha[:8]}"
    validation_run_id = f"validation:{run_id}"
    cohort_id = f"cohort:{manifest_sha[:24]}"
    initial_context = RunContext(
        schema_version="1.0",
        run_id=run_id,
        task_id="validation-repair-benchmark-config",
        span_id="config",
        trace_id=run_id,
    )
    app_settings = config_service.load_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"),
        initial_context,
    )
    settings = config_service.build_ingest_settings(
        IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
        initial_context,
    )
    configuration_hash = admission_configuration_hash(settings)
    policy_hash = admission_policy_hash(settings)
    if settings.validation_regeneration_max_attempts > 3:
        raise ValueError("configured retry limit exceeds the frozen benchmark limit")
    producer_build_identity = implementation_sha
    reports_db = output_dir / "state" / "reports.sqlite"
    usage_db = output_dir / "state" / "llm_usage.sqlite"
    base_output = output_dir / "output"
    isolated_settings = replace(
        settings,
        output_dir=str(base_output),
        cache_dir=str(output_dir / "cache"),
        state_db=str(output_dir / "state" / "state.sqlite"),
        reports_db=str(reports_db),
        usage_db_path=str(usage_db),
        cost_ledger_path=str(output_dir / "state" / "cost-ledger.jsonl"),
        cost_daily_path=str(output_dir / "state" / "cost-daily.json"),
    )
    root_ctx = _root_context(
        run_id=run_id,
        validation_run_id=validation_run_id,
        cohort_id=cohort_id,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
        implementation_sha=implementation_sha,
    )
    prepared_cases = _preflight_benchmark_cases(cases, workspace, root_ctx)
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=str(reports_db),
            validation_run_id=validation_run_id,
            cohort_id=cohort_id,
            workflow_run_id=run_id,
            configuration_hash=configuration_hash,
            policy_hash=policy_hash,
            producer_build_identity=producer_build_identity,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        ),
        root_ctx,
    )
    dependencies = ReportAnalysisDependencies.default()
    validation_model_client, regeneration_model_client = _build_repair_model_clients(
        isolated_settings
    )
    for prepared in prepared_cases:
        case = prepared["case"]
        artifacts = prepared["artifacts"]
        evidence_packs = prepared["evidence_packs"]
        report_context = prepared["report_context"]
        initial_validation = prepared["initial_validation"]
        case_ctx = prepared["case_ctx"]
        base_payload = prepared["base_payload"]
        report_id = str(case["report_id"])
        report_slug = slugify(str(case.get("report_slug") or report_id))
        source_identity_id = str(case.get("source_identity_id") or "")
        publisher_id = str(
            case.get("publisher_id") or report_context.get("publisher") or ""
        )
        runtime = ReportRuntimeState(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=report_id,
                name=report_slug,
                modified_time=None,
                md5_checksum=None,
                mime_type="application/pdf",
            ),
            local_pdf_path="",
            settings=isolated_settings,
            md5=None,
            ctx=case_ctx,
            file_name=report_slug,
            report_name=report_slug,
            report_title=str(report_context.get("title") or report_slug),
            analysis_mode="validation_repair_benchmark",
            analysis_modes=["validation_repair_benchmark"],
            report_worker_limit=1,
            parallel_within_file=False,
            publisher_name=str(report_context.get("publisher") or publisher_id),
            source_report_name=str(report_context.get("title") or report_slug),
            source_url=str(report_context.get("source_url") or ""),
        )
        dependencies.analysis_store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=str(base_output),
                report_id=ReportId(report_id),
                pack_name="artifacts",
                payload=artifacts,
                report_slug=report_slug,
            ),
            case_ctx,
        )
        (
            _,
            final_validation,
            attempts,
            loop_state,
            _,
            _,
        ) = _run_validation_regeneration_loop(
            runtime=runtime,
            mode_ctx=case_ctx,
            base_payload=base_payload,
            current_artifacts=artifacts,
            current_validation_report=initial_validation,
            evidence_packs=evidence_packs,
            source_status=(
                artifacts.get("source_status")
                if isinstance(artifacts.get("source_status"), dict)
                else {}
            ),
            category_labels=base_payload.categories,
            vector_store_id=None,
            dependencies=dependencies,
            validation_openai_client=validation_model_client,
            regeneration_openai_client=regeneration_model_client,
        )
        end = datetime.now(timezone.utc).isoformat()
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0",
                db_path=str(reports_db),
                record=ValidationRunManifestStageRecord(
                    schema_version="1.0",
                    validation_run_id=validation_run_id,
                    cohort_id=cohort_id,
                    workflow_run_id=run_id,
                    entity_type="report",
                    publisher_id=publisher_id,
                    report_id=report_id,
                    source_identity_id=source_identity_id,
                    stage="final_validation",
                    attempt_number=1,
                    parent_attempt_number=0,
                    input_artifact_ids=(
                        "artifact:" + str(case["original_artifact_canonical_sha256"]),
                    ),
                    output_artifact_ids=("validation:" + report_id,),
                    started_at_utc=end,
                    completed_at_utc=end,
                    terminal_outcome="succeeded"
                    if final_validation.status == "pass"
                    else "failed",
                    failure_code=""
                    if final_validation.status == "pass"
                    else "validation_failed",
                    retryable=False,
                    repair_disposition="targeted_repair",
                    duplicate_disposition="none",
                    supersession_state="current",
                    idempotency_state="new",
                    configuration_hash=configuration_hash,
                    policy_hash=policy_hash,
                    producer_build_identity=producer_build_identity,
                ),
            ),
            case_ctx,
        )
        print(
            json.dumps(
                {
                    "case_id": str(case.get("case_id") or report_id),
                    "attempt_count": len(attempts),
                    "final_status": final_validation.status,
                    "max_reached": loop_state.max_reached,
                },
                sort_keys=True,
            )
        )

    artifact = build_validation_reliability_artifact(
        ValidationReliabilityBuildRequest(
            schema_version="1.0",
            reports_db_path=str(reports_db),
            usage_db_path=str(usage_db),
            validation_run_id=validation_run_id,
            repair_evidence_root=str(base_output),
            repair_benchmark_manifest_path=str(manifest_path.resolve()),
            current_schema_identity_sha256=_schema_identity_sha256(workspace),
        ),
        root_ctx,
    )
    telemetry_path = validation_reliability_artifact_path(
        output_dir=str(base_output), validation_run_id=validation_run_id
    )
    written = write_validation_reliability_artifact(
        ValidationReliabilityWriteRequest(
            schema_version="1.0",
            artifact=artifact,
            artifact_path=telemetry_path,
        ),
        root_ctx,
    )
    return {
        "implementation_sha": implementation_sha,
        "benchmark_manifest_sha256": manifest_sha,
        "scorecard_path": written.artifact_path,
        "scorecard_sha256": written.artifact_hash,
        "scorecard": asdict(artifact.repair_scorecard),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--implementation-sha", required=True)
    args = parser.parse_args()
    result = replay_benchmark(
        manifest_path=args.manifest,
        output_dir=args.output_dir.resolve(),
        implementation_sha=args.implementation_sha,
    )
    result.pop("scorecard_path", None)
    summary = result.pop("scorecard")
    result["scorecard"] = {
        name: summary.get(name)
        for name in (
            "measurement_status",
            "repair_chain_count",
            "repair_attempt_count",
            "success_at_1_count",
            "success_at_1_rate",
            "success_at_3_count",
            "success_at_3_rate",
            "out_of_scope_mutation_attempt_count",
            "hard_failure_introduction_attempt_count",
            "unsupported_evidence_introduction_attempt_count",
            "baseline_success_at_3_rate",
            "baseline_residual_failure_odds_state",
            "current_residual_failure_odds_state",
            "residual_odds_reduction_state",
            "benchmark_denominator_complete",
            "benchmark_comparison_status",
            "usage_attribution",
            "model_call_count",
            "input_tokens",
            "output_tokens",
            "estimated_cost_usd",
            "latency_ms",
        )
    }
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
