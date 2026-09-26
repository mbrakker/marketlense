from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.quality.replay_validation_repair_benchmark import (
    _SCHEMA_IDENTITY_PATHS,
    _benchmark_manifest,
    _build_repair_model_clients,
    _case_paths,
    _pre_repair_base_payload,
    _preflight_benchmark_cases,
    _report_payload_from_frozen_state,
    _terminal_case_failure,
    _validation_report,
)
from src.contracts.report_models import Figure, Quote, ReportFigureAsset, ReportPayload
from src.contracts.run_context import RunContext
from src.generators.normalize_generator import normalize_report
from src.generators.report_generation_shared import merge_artifacts_into_payload
from src.orchestrators._report_generation_orchestrator.checkpoints import (
    _report_payload_from_dict,
)
from src.services.llm_service import LLMServiceClient
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError


def test_benchmark_manifest_requires_its_frozen_self_hash(tmp_path: Path) -> None:
    body = {"schema_version": "2.0", "frozen": True, "cases": []}
    canonical = (
        json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    body["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(body), encoding="utf-8")

    loaded, expected = _benchmark_manifest(path)
    assert loaded["frozen"] is True
    assert expected == body["manifest_sha256"]

    body["frozen"] = False
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest is invalid"):
        _benchmark_manifest(path)


def test_benchmark_case_inputs_are_hash_pinned_and_workspace_local(
    tmp_path: Path,
) -> None:
    artifact = {"schema_version": "1.0", "summary": {"tldr": "retained"}}
    artifact_path = tmp_path / "artifacts.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    case = {
        "input_files": {
            "artifacts": {
                "path": "artifacts.json",
                "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            }
        },
        "original_artifact_canonical_sha256": sha256_json(artifact),
    }

    paths, observed_path = _case_paths(case, tmp_path)
    assert paths["artifacts"] == artifact_path.resolve()
    assert observed_path == artifact_path.resolve()

    case["input_files"]["artifacts"]["path"] = "../outside.json"
    with pytest.raises(ValueError, match="outside workspace"):
        _case_paths(case, tmp_path)


def test_benchmark_reuses_the_retained_initial_validation_failures() -> None:
    report = _validation_report(
        {
            "schema_version": "1.0",
            "issues": [
                {
                    "message": "retained validator failure",
                    "severity": "error",
                    "affected_section": "summary.tldr",
                    "rule_id": "grounding",
                    "repair_target": "summary",
                    "entity_id": "summary:1",
                    "evidence_ids": ["finding:1"],
                }
            ],
        }
    )
    assert report.status == "fail"
    assert report.issues[0].rule_id == "grounding"
    assert report.issues[0].repair_target == "summary"


def test_benchmark_builds_production_model_clients_for_both_repair_stages() -> None:
    validation_client, regeneration_client = _build_repair_model_clients(object())

    assert isinstance(validation_client, LLMServiceClient)
    assert isinstance(regeneration_client, LLMServiceClient)
    assert validation_client is not regeneration_client


def test_terminal_nonretryable_case_failure_is_retained_without_content() -> None:
    error = AppError(
        "regeneration_repair_decision_invalid",
        "provider generated an unsafe response",
        context={"reason": "patch_target_not_atomic", "content": "sensitive"},
    )

    assert _terminal_case_failure(error) == {
        "failure_code": "regeneration_repair_decision_invalid",
        "failure_reason": "patch_target_not_atomic",
    }


def test_terminal_case_failure_propagates_retryable_errors() -> None:
    error = AppError(
        "provider_unavailable",
        "retry later",
        retryable=True,
        context={"reason": "busy"},
    )

    with pytest.raises(AppError) as raised:
        _terminal_case_failure(error)

    assert raised.value is error


def test_benchmark_schema_identity_includes_the_private_repair_response_schema() -> (
    None
):
    assert "src/schemas/regeneration_repair_decision.schema.json" in (
        _SCHEMA_IDENTITY_PATHS
    )


def _complete_payload_seed() -> dict[str, Any]:
    payload = ReportPayload(
        schema_version="1.1",
        tldr="Retained summary",
        title="Retained report title",
        insights=["one", "two", "three", "four", "five"],
        quote=Quote(text="Retained quote", author="Analyst"),
        figure=Figure(
            title="Original figure title", evidence="Original figure evidence"
        ),
        commentary="Retained commentary",
        source="",
        _figure_assets=[
            ReportFigureAsset(
                image_path="report/figure.png",
                page=2,
                candidate_id="table-2",
                kind="table",
                is_primary=True,
                display_caption="Figure table caption",
                caption_source="legacy",
                crop_qa_score=0.87,
                crop_qa_defects=["minor_crop"],
                crop_qa_detector_summary={"table_boundary": 0.82},
                crop_qa_accepted=True,
                crop_qa_sidecar_path="report/figure.png.qa.json",
                crop_quality_profile="publication_strict",
            )
        ],
    )
    return payload.to_dict()


def test_frozen_payload_roundtrip_preserves_figure_and_all_asset_state() -> None:
    payload_data = _complete_payload_seed()
    expected_hash = sha256_json(payload_data)

    payload = _report_payload_from_frozen_state(
        payload_data,
        expected_sha256=expected_hash,
        label="fixture",
    )

    assert payload.to_dict() == payload_data
    assert payload.figure.title == "Original figure title"
    assert payload.figure.evidence == "Original figure evidence"
    assert payload._figure_assets[0].crop_qa_accepted is True
    assert payload._figure_assets[0].crop_qa_score == 0.87

    checkpoint_roundtrip = _report_payload_from_dict(payload_data).to_dict()
    assert checkpoint_roundtrip == payload_data


def test_frozen_payload_rejects_missing_fields_and_hash_mismatch() -> None:
    incomplete = _complete_payload_seed()
    del incomplete["figure"]["evidence"]

    with pytest.raises(ValueError, match="payload fields are incomplete"):
        _report_payload_from_frozen_state(
            incomplete,
            expected_sha256=sha256_json(incomplete),
            label="fixture",
        )

    complete = _complete_payload_seed()
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        _report_payload_from_frozen_state(
            complete,
            expected_sha256="0" * 64,
            label="fixture",
        )


def test_benchmark_case_preflight_merges_and_validates_before_repair_setup(
    tmp_path: Path,
) -> None:
    artifacts = {
        "schema_version": "1.0",
        "summary": {
            "tldr": "Retained summary",
            "executive_summary": "Retained commentary",
        },
        "insights_final": ["one", "two", "three", "four", "five"],
        "quotes_final": [{"text": "Retained quote", "speaker": "Analyst"}],
    }
    base_payload = _complete_payload_seed()
    merged_payload = merge_artifacts_into_payload(
        _report_payload_from_dict(base_payload), artifacts
    )
    inputs: dict[str, dict[str, str]] = {}

    def retain(name: str, value: dict[str, object]) -> None:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")
        inputs[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    retain("artifacts", artifacts)
    for name in (
        "doc_map",
        "findings",
        "limitations",
        "methods",
        "quote_candidates",
        "scope",
    ):
        retain(name, {"schema_version": "1.0", "items": []})
    retain("report_context", {"title": "Retained report title", "publisher": ""})
    retain(
        "initial_validation",
        {"schema_version": "1.0", "issues": [{"rule_id": "grounding"}]},
    )
    retain(
        "pre_repair_checkpoint",
        {"payload": {"analysis": {"payload": base_payload}}},
    )
    case = {
        "case_id": "fixture",
        "report_id": "report-fixture",
        "report_slug": "fixture",
        "input_files": inputs,
        "original_artifact_canonical_sha256": sha256_json(artifacts),
        "pre_repair_state": {
            "kind": "analysis_checkpoint",
            "input_file": "pre_repair_checkpoint",
            "payload_pointer": ["payload", "analysis", "payload"],
            "canonical_sha256": sha256_json(base_payload),
            "merged_canonical_sha256": sha256_json(merged_payload.to_dict()),
        },
    }
    root_ctx = RunContext(
        schema_version="1.0",
        run_id="benchmark-fixture",
        task_id="benchmark-fixture",
        span_id="benchmark-fixture",
        trace_id="benchmark-fixture",
    )

    prepared = _preflight_benchmark_cases([case], tmp_path, root_ctx)

    assert prepared[0]["base_payload"].figure.title == "Original figure title"
    assert prepared[0]["base_payload"].figure.evidence == "Original figure evidence"
    assert prepared[0]["initial_payload"].figure == prepared[0]["base_payload"].figure
    assert prepared[0]["initial_payload"].quote.text == "Retained quote"


def test_benchmark_case_preflight_rejects_incomplete_payload_before_clients(
    tmp_path: Path,
) -> None:
    artifacts = {
        "schema_version": "1.0",
        "summary": {"tldr": "summary", "executive_summary": "commentary"},
        "insights_final": ["one", "two", "three", "four", "five"],
        "quotes_final": [{"text": "quote", "speaker": "analyst"}],
    }
    base_payload = _complete_payload_seed()
    del base_payload["figure"]["title"]
    inputs: dict[str, dict[str, str]] = {}
    values = {
        "artifacts": artifacts,
        "doc_map": {"schema_version": "1.0"},
        "findings": {"schema_version": "1.0"},
        "limitations": {"schema_version": "1.0"},
        "methods": {"schema_version": "1.0"},
        "quote_candidates": {"schema_version": "1.0"},
        "scope": {"schema_version": "1.0"},
        "report_context": {"title": "Retained report title", "publisher": ""},
        "initial_validation": {
            "schema_version": "1.0",
            "issues": [{"rule_id": "grounding"}],
        },
        "pre_repair_checkpoint": {"payload": {"analysis": {"payload": base_payload}}},
    }
    for name, value in values.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value, ensure_ascii=True), encoding="utf-8")
        inputs[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    case = {
        "case_id": "fixture",
        "report_id": "report-fixture",
        "input_files": inputs,
        "original_artifact_canonical_sha256": sha256_json(artifacts),
        "pre_repair_state": {
            "kind": "analysis_checkpoint",
            "input_file": "pre_repair_checkpoint",
            "payload_pointer": ["payload", "analysis", "payload"],
            "canonical_sha256": sha256_json(base_payload),
            "merged_canonical_sha256": "0" * 64,
        },
    }
    root_ctx = RunContext(
        schema_version="1.0",
        run_id="benchmark-fixture",
        task_id="benchmark-fixture",
        span_id="benchmark-fixture",
    )

    with pytest.raises(ValueError, match="payload fields are incomplete"):
        _preflight_benchmark_cases([case], tmp_path, root_ctx)


def test_selection_reconstruction_uses_persisted_outputs_and_keeps_figure_state(
    tmp_path: Path,
) -> None:
    selection_payload = _complete_payload_seed()
    selection_payload["taxonomy"] = []
    selection_payload["categories"] = []
    selection_payload["region"] = ""
    selection_payload["time_period"] = ""
    selection_payload["publisher"] = ""
    checkpoint = {
        "payload": {
            "selection": {"payload": selection_payload},
            "source": {"title_resolution": {"title": "Retained report title"}},
        }
    }
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    source_cohort_path = tmp_path / "source.json"
    source_cohort_path.write_text(
        json.dumps({"configuration_snapshot": {"figure_caption_enabled": False}}),
        encoding="utf-8",
    )
    source_state_db_path = tmp_path / "source-state.sqlite"
    source_state_db_path.write_bytes(b"pinned source stage data")
    context = {
        "region": "Global",
        "time_period": "2024 to 2026",
    }
    doc_map = {"title": "Doc map title", "publisher": "Retained publisher"}
    selection = _report_payload_from_dict(selection_payload)
    selection.taxonomy = ["technology"]
    selection.categories = ["ai_automation"]
    selection.region = context["region"]
    selection.time_period = context["time_period"]
    selection.publisher = "Retained publisher"
    expected = normalize_report(
        selection,
        RunContext(
            schema_version="1.0",
            run_id="benchmark-fixture",
            task_id="benchmark-fixture",
            span_id="benchmark-fixture",
        ),
    )
    state = {
        "kind": "selection_checkpoint_reconstruction",
        "input_file": "selection_checkpoint",
        "payload_pointer": ["payload", "selection", "payload"],
        "selection_payload_sha256": sha256_json(selection_payload),
        "canonical_sha256": sha256_json(expected.to_dict()),
        "taxonomy_ids": ["technology"],
        "category_ids": ["ai_automation"],
        "source_cohort_file": "source_cohort",
        "source_publisher": "",
        "source_state_db_file": "source_state_db",
        "stage_output_provenance": {
            "category_ids_stage": "category_fit",
            "region_and_time_period_input": "report_context",
            "taxonomy_ids_stage": "taxonomy",
            "taxonomy_and_category_stage_records_file": "source_state_db",
        },
    }
    case = {"case_id": "fixture", "pre_repair_state": state}
    root_ctx = RunContext(
        schema_version="1.0",
        run_id="benchmark-fixture",
        task_id="benchmark-fixture",
        span_id="benchmark-fixture",
    )

    reconstructed = _pre_repair_base_payload(
        case=case,
        paths={
            "selection_checkpoint": selection_path,
            "source_cohort": source_cohort_path,
            "source_state_db": source_state_db_path,
        },
        report_context=context,
        evidence_packs={"doc_map": doc_map},
        case_ctx=root_ctx,
    )

    assert reconstructed.to_dict() == expected.to_dict()
    assert reconstructed.title == "Retained report title"
    assert reconstructed.publisher == "Retained publisher"
    assert reconstructed.taxonomy == ["technology"]
    assert reconstructed.categories == ["ai_automation"]
    assert reconstructed.region == "Global"
    assert reconstructed.time_period == "2024 to 2026"
    assert reconstructed.figure.title == "Original figure title"
    assert reconstructed.figure.evidence == "Original figure evidence"
    assert reconstructed._figure_assets[0].crop_qa_accepted is True
