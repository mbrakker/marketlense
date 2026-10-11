from __future__ import annotations

import inspect
import json
from dataclasses import asdict
from pathlib import Path

from scripts.quality import compare_model_call_replay_bundles as comparison_cli
from src.contracts.model_call_replay_comparison import (
    ModelCallReplayBundleComparisonRequest,
)
from src.contracts.workflow_control import (
    ModelCallAuditRecord,
    ModelCallReplayBundle,
    ModelCallReplayComparisonEvidence,
)
from src.services import llm_service
from src.services._llm_service import audit

PROMPT_A = "a" * 64
PROMPT_B = "b" * 64
POLICY_A = "c" * 64
POLICY_B = "d" * 64
EVIDENCE_A = "e" * 64
EVIDENCE_B = "f" * 64
OUTPUT_A = "1" * 64
OUTPUT_B = "2" * 64
ARTIFACT_A = "3" * 64
ARTIFACT_B = "4" * 64
ARTIFACT_FAMILY = "report_vs/doc_map"


def _bundle(
    *,
    version: str = "1.1",
    prompt_hash: str = PROMPT_A,
    policy_hash: str | None = POLICY_A,
    evidence_hash: str | None = EVIDENCE_A,
    output_hash: str | None = OUTPUT_A,
    artifact_hash: str | None = ARTIFACT_A,
    schema_version: str = "1.0",
    schema_hash: str | None = None,
    validation_result: str = "pass",
    artifact_family: str = ARTIFACT_FAMILY,
    model: str = "gpt-6-luna",
    live_provider_call_allowed: bool = False,
) -> ModelCallReplayBundle:
    audit_record = ModelCallAuditRecord(
        schema_version="1.0",
        operation="openai_chat_json",
        scope="report-vs",
        provider_decision="openai_primary",
        prompt_namespace="report_vs/doc_map",
        prompt_hash=prompt_hash,
        rendered_prompt_redaction_hash=prompt_hash,
        model=model,
        temperature=0.0,
        seed=17,
        seed_supported=True,
        schema_name="doc_map",
        output_schema_version=schema_version,
        response_id="safe-response-id",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        estimated_cost_usd=0.01,
        cache_key="safe-cache-key",
        cache_decision="disabled",
        validation_result=validation_result,
        reasoning_effort="none",
    )
    replay_inputs = {
        "operation": audit_record.operation,
        "scope": audit_record.scope,
        "provider_decision": audit_record.provider_decision,
        "prompt_namespace": audit_record.prompt_namespace,
        "prompt_hash": audit_record.prompt_hash,
        "rendered_prompt_redaction_hash": audit_record.rendered_prompt_redaction_hash,
        "model": audit_record.model,
        "temperature": audit_record.temperature,
        "reasoning_effort": audit_record.reasoning_effort,
        "seed": audit_record.seed,
        "schema_name": audit_record.schema_name,
        "schema_version": audit_record.output_schema_version,
        "cache_key": audit_record.cache_key,
    }
    comparison_evidence = (
        None
        if version == "1.0"
        else ModelCallReplayComparisonEvidence(
            schema_version="1.0",
            artifact_family=artifact_family,
            policy_sha256=policy_hash,
            evidence_sha256=evidence_hash,
            output_sha256=output_hash,
            artifact_sha256=artifact_hash,
            schema_sha256=schema_hash,
        )
    )
    return ModelCallReplayBundle(
        schema_version=version,
        audit_record=audit_record,
        replay_inputs=replay_inputs,
        live_provider_call_allowed=live_provider_call_allowed,
        comparison_evidence=comparison_evidence,
    )


def _compare(
    baseline: ModelCallReplayBundle,
    candidate: ModelCallReplayBundle,
):
    return audit.compare_model_call_replay_bundles(
        ModelCallReplayBundleComparisonRequest(
            schema_version="1.0",
            artifact_family=ARTIFACT_FAMILY,
            baseline_bundle=baseline,
            candidate_bundle=candidate,
            baseline_bundle_sha256="5" * 64,
            candidate_bundle_sha256="6" * 64,
        )
    )


def test_model_call_replay_comparison_entrypoint_is_available() -> None:
    assert callable(getattr(audit, "compare_model_call_replay_bundles", None))
    assert callable(getattr(llm_service, "compare_model_call_replay_bundles", None))


def test_replay_builder_accepts_explicit_comparison_evidence() -> None:
    assert (
        "comparison_evidence"
        in inspect.signature(audit.build_model_call_replay_bundle).parameters
    )
    source = _bundle()
    evidence = source.comparison_evidence
    assert evidence is not None

    retained = audit.build_model_call_replay_bundle(
        source.audit_record, comparison_evidence=evidence
    )
    legacy = audit.build_model_call_replay_bundle(source.audit_record)

    assert retained.schema_version == "1.1"
    assert retained.comparison_evidence == evidence
    assert legacy.schema_version == "1.1"
    assert legacy.comparison_evidence is None


def test_comparison_cli_script_exists() -> None:
    script = (
        Path(__file__).parents[1]
        / "scripts/quality/compare_model_call_replay_bundles.py"
    )
    assert script.is_file()


def test_cli_is_read_only_provider_free_and_deterministic(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(
        json.dumps(asdict(_bundle()), sort_keys=True), encoding="utf-8"
    )
    candidate_path.write_text(
        json.dumps(asdict(_bundle()), sort_keys=True), encoding="utf-8"
    )
    original_files = {path.name for path in tmp_path.iterdir()}
    original_bytes = (baseline_path.read_bytes(), candidate_path.read_bytes())
    provider_calls: list[str] = []

    def forbidden_provider_call(*_args, **_kwargs):
        provider_calls.append("provider")
        raise AssertionError("comparison attempted a provider call")

    for service_name in (
        "openai_chat_json",
        "openai_chat_json_with_images",
        "openai_respond_with_vector_store",
        "analyze_report",
        "openai_create_embeddings",
        "openai_ocr_pdf",
        "openai_legacy",
        "openrouter_chat_json",
        "build_openai_client",
        "build_openai_client_for_settings",
        "build_openai_client_from_callables",
        "build_openai_browser_use_client",
        "build_browser_use_llm_clients",
        "build_openrouter_client",
        "build_client",
        "build_client_for_settings",
        "build_client_from_callables",
        "openai_vector_store_create",
        "openai_vector_store_upload_file",
        "openai_vector_store_attach_file",
        "openai_vector_store_delete",
        "openai_vector_store_update_metadata",
    ):
        monkeypatch.setattr(llm_service, service_name, forbidden_provider_call)

    args = [
        "--baseline",
        str(baseline_path),
        "--candidate",
        str(candidate_path),
        "--artifact-family",
        ARTIFACT_FAMILY,
    ]
    first_status = comparison_cli.main(args)
    first_output = capsys.readouterr().out
    second_status = comparison_cli.main(args)
    second_output = capsys.readouterr().out

    assert first_status == second_status == 0
    assert first_output == second_output
    assert json.loads(first_output)["classification"] == "equivalent"
    assert provider_calls == []
    assert {path.name for path in tmp_path.iterdir()} == original_files
    assert (baseline_path.read_bytes(), candidate_path.read_bytes()) == original_bytes


def test_cli_never_echoes_retained_private_content(tmp_path: Path, capsys) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    unsafe_payload = asdict(_bundle())
    unsafe_payload["audit_record"]["user_prompt"] = "PRIVATE_PROMPT_MARKER"
    unsafe_payload["model_response"] = "PRIVATE_RESPONSE_MARKER"
    unsafe_payload["api_key"] = "PRIVATE_CREDENTIAL_MARKER"
    baseline_path.write_text(json.dumps(unsafe_payload), encoding="utf-8")
    candidate_path.write_text(
        json.dumps(asdict(_bundle()), sort_keys=True), encoding="utf-8"
    )

    exit_code = comparison_cli.main(
        [
            "--baseline",
            str(baseline_path),
            "--candidate",
            str(candidate_path),
            "--artifact-family",
            ARTIFACT_FAMILY,
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 2
    assert json.loads(output)["classification"] == "malformed"
    assert "PRIVATE_PROMPT_MARKER" not in output
    assert "PRIVATE_RESPONSE_MARKER" not in output
    assert "PRIVATE_CREDENTIAL_MARKER" not in output


def test_identical_bundles_are_equivalent_and_repeatable() -> None:
    baseline = _bundle()

    first = _compare(baseline, _bundle())
    second = _compare(baseline, _bundle())

    assert first == second
    assert first.classification == "equivalent"
    assert first.cohort_compatibility == "compatible"
    assert first.changed_fields == ()
    assert first.regression_evidence == ()
    assert {
        "prompt_hash",
        "model",
        "policy_sha256",
        "schema_name",
        "output_schema_version",
        "evidence_sha256",
        "output_sha256",
        "artifact_sha256",
    }.issubset(first.compared_fields)


def test_output_change_is_compatible_and_names_only_the_changed_field() -> None:
    result = _compare(_bundle(), _bundle(output_hash=OUTPUT_B))

    assert result.classification == "compatible_but_changed"
    assert result.changed_fields == ("output_sha256",)
    assert result.cohort_compatibility == "compatible"
    assert OUTPUT_A not in repr(result)
    assert OUTPUT_B not in repr(result)


def test_prompt_policy_evidence_and_schema_changes_are_incompatible() -> None:
    cases = (
        (_bundle(prompt_hash=PROMPT_B), "prompt_hash"),
        (_bundle(policy_hash=POLICY_B), "policy_sha256"),
        (_bundle(evidence_hash=EVIDENCE_B), "evidence_sha256"),
        (_bundle(schema_version="2.0"), "output_schema_version"),
        (_bundle(model="gpt-6-astra"), "model"),
        (_bundle(artifact_family="report_vs/other"), "artifact_family"),
    )

    for candidate, changed_field in cases:
        result = _compare(_bundle(), candidate)
        assert result.classification == "incompatible"
        assert result.cohort_compatibility == "incompatible"
        assert changed_field in result.changed_fields
        assert result.artifact_family == ARTIFACT_FAMILY


def test_retained_schema_hash_is_compared_when_present_on_both_sides() -> None:
    result = _compare(
        _bundle(schema_hash="7" * 64),
        _bundle(schema_hash="8" * 64),
    )

    assert result.classification == "incompatible"
    assert result.changed_fields == ("schema_sha256",)


def test_legacy_bundle_without_comparison_evidence_is_incomplete() -> None:
    result = _compare(_bundle(version="1.0"), _bundle(version="1.0"))

    assert result.classification == "incomplete"
    assert result.cohort_compatibility == "unknown"
    assert {
        "artifact_family",
        "policy_sha256",
        "evidence_sha256",
        "output_sha256",
        "artifact_sha256",
    }.issubset(result.missing_fields)
    assert result.classification != "equivalent"


def test_invalid_explicit_hash_is_malformed() -> None:
    result = _compare(_bundle(policy_hash="not-a-sha256"), _bundle())

    assert result.classification == "malformed"
    assert "IDENTITY_HASH_INVALID" in result.diagnostic_codes
    assert "not-a-sha256" not in repr(result)


def test_provider_enabled_replay_bundle_is_malformed_for_comparison() -> None:
    result = _compare(
        _bundle(live_provider_call_allowed=True),
        _bundle(),
    )

    assert result.classification == "malformed"
    assert "LIVE_PROVIDER_REPLAY_NOT_ALLOWED" in result.diagnostic_codes


def test_validation_failure_is_regression_only_for_the_same_comparable_cohort() -> None:
    result = _compare(
        _bundle(),
        _bundle(
            output_hash=OUTPUT_B,
            artifact_hash=ARTIFACT_B,
            validation_result="fail",
        ),
    )

    assert result.classification == "materially_regressed"
    assert result.cohort_compatibility == "compatible"
    assert result.regression_evidence == (
        "OUTPUT_IDENTITY_CHANGED",
        "VALIDATION_REGRESSED",
    )


def test_validation_failure_without_changed_output_is_not_a_regression() -> None:
    result = _compare(_bundle(), _bundle(validation_result="fail"))

    assert result.classification == "compatible_but_changed"
    assert result.regression_evidence == ()


def test_changed_fields_follow_fixed_order() -> None:
    candidate = _bundle(
        prompt_hash=PROMPT_B,
        policy_hash=POLICY_B,
        evidence_hash=EVIDENCE_B,
        output_hash=OUTPUT_B,
        artifact_hash=ARTIFACT_B,
        schema_version="2.0",
    )

    first = _compare(_bundle(), candidate)
    second = _compare(_bundle(), candidate)

    assert first == second
    assert first.changed_fields == (
        "prompt_hash",
        "rendered_prompt_redaction_hash",
        "output_schema_version",
        "policy_sha256",
        "evidence_sha256",
        "output_sha256",
        "artifact_sha256",
    )
