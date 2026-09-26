"""Replay frozen retained repair failures through the production repair loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.drive import DriveFile
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.report_generation import ReportRuntimeState
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
    base_payload,
    merge_artifacts_into_payload,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _run_validation_regeneration_loop,
)
from src.orchestrators.admission_preflight_orchestrator import (
    admission_configuration_hash,
    admission_policy_hash,
)
from src.services import config_service
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
    if payload.get("frozen") is not True or declared_hash != actual_hash:
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
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("frozen benchmark case must be an object")
        paths, _ = _case_paths(case, workspace)
        artifacts = _read_json(paths["artifacts"])
        evidence_names = (
            "doc_map",
            "findings",
            "limitations",
            "methods",
            "quote_candidates",
            "scope",
        )
        evidence_packs = {
            name: _read_json(paths[name]) for name in evidence_names if name in paths
        }
        required_evidence = {
            "doc_map",
            "findings",
            "limitations",
            "methods",
            "quote_candidates",
            "scope",
        }
        if set(evidence_packs) != required_evidence:
            raise ValueError("frozen benchmark evidence pack set is incomplete")
        report_context = _read_json(paths["report_context"])
        initial_validation = _validation_report(_read_json(paths["initial_validation"]))
        report_id = str(case.get("report_id") or "")
        report_slug = slugify(str(case.get("report_slug") or report_id))
        source_identity_id = str(case.get("source_identity_id") or "")
        publisher_id = str(
            case.get("publisher_id") or report_context.get("publisher") or ""
        )
        case_ctx = replace(
            root_ctx,
            task_id=f"report:{report_id}",
            span_id=f"report:{report_id}",
            report_id=report_id,
            source_identity_id=source_identity_id,
            publisher_id=publisher_id,
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
        initial_payload = base_payload(
            title=runtime.report_title,
            contents_page_number=0,
            contents_heading="",
            contents_image="",
        )
        initial_payload.publisher = runtime.publisher_name
        initial_payload.source = runtime.source_url
        initial_payload.region = str(report_context.get("region") or "")
        initial_payload.time_period = str(report_context.get("time_period") or "")
        raw_categories = artifacts.get("categories")
        initial_payload.categories = (
            [str(value) for value in raw_categories if str(value)]
            if isinstance(raw_categories, list)
            else []
        )
        initial_payload = merge_artifacts_into_payload(initial_payload, artifacts)
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
            base_payload=initial_payload,
            current_artifacts=artifacts,
            current_validation_report=initial_validation,
            evidence_packs=evidence_packs,
            source_status=(
                artifacts.get("source_status")
                if isinstance(artifacts.get("source_status"), dict)
                else {}
            ),
            category_labels=initial_payload.categories,
            vector_store_id=None,
            dependencies=dependencies,
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
