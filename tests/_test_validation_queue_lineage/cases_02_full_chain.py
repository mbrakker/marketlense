# ruff: noqa: F401,F403,F405
from __future__ import annotations

import fitz

from ._shared import *  # noqa: F401,F403
from ._shared import (
    _ctx,
    _full_chain_chat_response_factory,
    _full_chain_response_factory,
    _isolated_app_config,
)


@pytest.mark.parametrize(
    ("repair_soft_copy", "reproduce_ias_soft_copy"),
    ((False, False), (True, False), (False, True)),
    ids=(
        "clean-awaiting-review",
        "unsupported-soft-copy-repaired",
        "ias-known-claims-repaired",
    ),
)
def test_a21_full_chain_preserves_grounding_disposition(
    tmp_path,
    external_boundary_mocks_only,
    fake_openai,
    repair_soft_copy: bool,
    reproduce_ias_soft_copy: bool,
) -> None:
    """Keep unsupported candidates out of final artifacts and packages."""
    external_boundary_mocks_only.setenv("OPENAI_API_KEY", "test-openai-key")
    fake_openai.add("vector_stores.create", {"id": "vs_queue_test"})
    fake_openai.add("files.create", {"id": "file_queue_test"})
    fake_openai.add("vector_stores.files.create", {"id": "file_queue_test"})
    fake_openai.add("vector_stores.retrieve", {"status": "completed"})
    fake_openai.add("vector_stores.update", {"id": "vs_queue_test"})
    generated_soft_copy_payloads: list[dict[str, object]] = []
    detected_unsupported_claims: list[str] = []
    fake_openai.add(
        "responses.create",
        _full_chain_response_factory(
            repair_soft_copy=repair_soft_copy,
            reproduce_ias_soft_copy=reproduce_ias_soft_copy,
            detected_unsupported_claims=detected_unsupported_claims,
        ),
    )
    fake_openai.add(
        "chat.completions.create",
        _full_chain_chat_response_factory(
            repair_soft_copy=repair_soft_copy,
            reproduce_ias_soft_copy=reproduce_ias_soft_copy,
            generated_soft_copy_payloads=generated_soft_copy_payloads,
            detected_unsupported_claims=detected_unsupported_claims,
        ),
    )
    config_path = _isolated_app_config(tmp_path)
    settings = build_ingest_settings(
        IngestSettingsBuildRequest(
            schema_version="1.0",
            app_settings=load_settings(
                ConfigLoadRequest(schema_version="1.0", path=str(config_path)),
                _ctx(),
            ),
        ),
        _ctx(),
    )
    source_path = tmp_path / "source.pdf"
    source_pdf = fitz.open()
    source_sentences = [
        "Industry Analytics Summit publishes the Industry Pulse Report 2026.",
        "Customer demand is changing across segments.",
        "The report covers media planning and advertising strategy.",
        "Media teams review audience research before setting campaign priorities.",
        "Planning decisions consider the needs of different customer segments.",
        "Evidence helps teams compare audience needs with campaign objectives.",
        "Organizations should review planning assumptions when market conditions change.",
        "The report describes practical considerations for media planning teams.",
    ]
    source_text = "\n".join(source_sentences * 4)
    for page_number in range(4):
        source_page = source_pdf.new_page()
        source_page.insert_textbox(
            fitz.Rect(48, 48, 564, 744),
            "\n".join(
                source_text.splitlines()[page_number * 8 : (page_number + 1) * 8]
            ),
            fontsize=11,
        )
    source_pdf.save(source_path)
    source_pdf.close()
    source_hash = md5(source_path.read_bytes(), usedforsecurity=False).hexdigest()
    cohort_manifest = tmp_path / "frozen-cohort.json"
    prepared = submit_preselected_frozen_validation_cohort(
        PreselectedFrozenValidationCohortSubmissionRequest(
            schema_version="1.0",
            settings=settings,
            cohort_manifest=str(cohort_manifest),
            config_path=str(config_path),
            sources=(
                PreselectedFrozenValidationSource(
                    schema_version="1.0",
                    report_id="report-1",
                    source_artifact_path=str(source_path),
                    content_md5=source_hash,
                    source_domain="publisher.example",
                    report_name="Industry Pulse Report 2026",
                    landing_page_url="https://publisher.example/reports/industry-pulse-2026",
                    source_page_url="https://publisher.example/reports",
                    publisher_name="Industry Analytics Summit",
                    downloaded_at_utc="2026-08-10T12:00:00Z",
                ),
            ),
        ),
        _ctx(),
    )
    assert len(prepared.admission_decisions) == 1
    assert prepared.admission_decisions[0].outcome == "admitted"
    assert prepared.queue_submission is not None
    response = prepared.queue_submission
    frozen_cohort = json.loads(cohort_manifest.read_text(encoding="utf-8"))
    member = frozen_cohort["members"][0]
    assert member["md5_checksum"] == source_hash
    assert (
        member["source_identity_id"]
        == prepared.admission_decisions[0].source_identity_id
    )
    assert member["publisher_id"] == "Industry Analytics Summit"
    reports_db = settings.reports_db
    state_db = settings.state_db

    assert response.root_workflow_id
    assert response.validation_run_id == frozen_cohort["validation_run_id"]
    assert response.cohort_id == frozen_cohort["cohort_id"]
    assert len(response.jobs) == 1
    source_job = response.jobs[0]
    assert source_job.root_workflow_id == response.root_workflow_id
    payload = load_workflow_job_payload(source_job)
    assert payload.validation_run_id == response.validation_run_id
    assert payload.cohort_id == response.cohort_id
    assert (
        payload.source_identity_id == prepared.admission_decisions[0].source_identity_id
    )
    assert payload.source_content_hash == source_hash
    worker_result = run_workflow_worker_once(
        state_db=state_db,
        queue_name="source_ingest",
        worker_id="validation-lineage-test-worker",
        ctx=_ctx(),
    )
    assert worker_result.terminal_status == "succeeded"
    materialize_workflow_outbox(state_db, "validation-lineage-test-worker", _ctx())
    for queue_name in (
        "report_selection",
        "report_analysis",
        "report_render",
        "publication_readiness",
    ):
        result = run_workflow_worker_once(
            state_db=state_db,
            queue_name=queue_name,
            worker_id="validation-lineage-test-worker",
            ctx=_ctx(),
        )
        completed_job = get_workflow_job(state_db, result.claimed_job_id, _ctx())
        assert result.terminal_status == "succeeded", (
            f"queue={queue_name} model_schemas="
            f"{[call['text']['format']['name'] for call in fake_openai.calls['responses.create']]}"
            f" chat_schemas={[call['response_format'].get('json_schema', {}).get('name', '') for call in fake_openai.calls['chat.completions.create']]}"
            f" error={completed_job.error_code if completed_job else ''}"
            f" message={completed_job.error_message_summary if completed_job else ''}"
        )
        materialize_workflow_outbox(state_db, "validation-lineage-test-worker", _ctx())
    with sqlite3.connect(reports_db) as conn:
        run = conn.execute(
            "SELECT workflow_run_id FROM validation_runs WHERE validation_run_id=?",
            (response.validation_run_id,),
        ).fetchone()
        stage_roots = conn.execute(
            "SELECT DISTINCT workflow_run_id FROM validation_run_stage_records "
            "WHERE validation_run_id=?",
            (response.validation_run_id,),
        ).fetchall()
    with sqlite3.connect(state_db) as conn:
        queue_rows = conn.execute(
            "SELECT queue_name, root_workflow_id, source_identity_id, publisher_id, "
            "payload_json FROM workflow_jobs "
            "WHERE report_id=? ORDER BY created_at_utc, job_id",
            ("report-1",),
        ).fetchall()
        foreign_lineage_rows = conn.execute(
            "SELECT job_id FROM workflow_jobs "
            "WHERE report_id=? AND root_workflow_id<>?",
            ("report-1", response.root_workflow_id),
        ).fetchall()
    assert run == (response.root_workflow_id,)
    assert stage_roots == [(response.root_workflow_id,)]
    assert {row[0] for row in queue_rows} == {
        "source_ingest",
        "report_selection",
        "report_analysis",
        "report_render",
        "analytics_projection",
        "publication_readiness",
    }
    assert foreign_lineage_rows == []
    for (
        _queue_name,
        root_workflow_id,
        source_identity_id,
        publisher_id,
        raw_payload,
    ) in queue_rows:
        payload = json.loads(raw_payload)
        assert root_workflow_id == response.root_workflow_id
        assert payload["validation_run_id"] == response.validation_run_id
        assert payload["cohort_id"] == response.cohort_id
        assert source_identity_id == member["source_identity_id"]
        assert publisher_id == member["publisher_id"]
    with sqlite3.connect(state_db) as conn:
        readiness_rows = conn.execute(
            "SELECT readiness_status FROM workflow_publication_readiness"
        ).fetchall()
    assert readiness_rows == [("awaiting_review",)]

    request = ValidationReliabilityBuildRequest(
        schema_version="1.0",
        reports_db_path=reports_db,
        usage_db_path=settings.usage_db_path,
        state_db_path=state_db,
        validation_run_id=response.validation_run_id,
    )
    first = build_validation_reliability_artifact(request, _ctx())
    second = build_validation_reliability_artifact(request, _ctx())
    first_path = tmp_path / "a21-first.json"
    second_path = tmp_path / "a21-second.json"
    write_validation_reliability_artifact(
        ValidationReliabilityWriteRequest(
            schema_version="1.0", artifact_path=str(first_path), artifact=first
        ),
        _ctx(),
    )
    write_validation_reliability_artifact(
        ValidationReliabilityWriteRequest(
            schema_version="1.0", artifact_path=str(second_path), artifact=second
        ),
        _ctx(),
    )
    assert first_path.read_bytes() == second_path.read_bytes()
    assert (
        sha256(first_path.read_bytes()).hexdigest()
        == sha256(second_path.read_bytes()).hexdigest()
    )
    assert first.artifact_hash == second.artifact_hash
    assert len(first.first_attempt_entities) == 1
    entity = first.first_attempt_entities[0]
    assert entity.eventual_success is True
    assert entity.operator_intervention is False
    awaiting_review_stage = next(
        stage for stage in entity.stages if stage.to_state == "awaiting_review"
    )
    assert awaiting_review_stage.eventual_success is True
    analysis_dirs = sorted((tmp_path / "out").glob("*/report_analysis"))
    artifact_dirs = [
        directory
        for directory in analysis_dirs
        if (directory / "artifacts.json").is_file()
    ]
    assert len(artifact_dirs) == 1, [str(directory) for directory in analysis_dirs]
    analysis_dir = artifact_dirs[0]
    artifacts = json.loads(
        (analysis_dir / "artifacts.json").read_text(encoding="utf-8")
    )
    if repair_soft_copy or reproduce_ias_soft_copy:
        regeneration_audit = json.loads(
            (analysis_dir / "regeneration_candidate_audit_1.json").read_text(
                encoding="utf-8"
            )
        )
        expected_scope = (
            ["expert_comment", "linkedin_post"]
            if reproduce_ias_soft_copy
            else ["expert_comment"]
        )
        assert regeneration_audit["transformation_scope"] == expected_scope
        assert _UNSUPPORTED_SOFT_COPY_CLAIM not in artifacts["expert_comment"]
        if reproduce_ias_soft_copy:
            initial_by_family = {}
            for payload in generated_soft_copy_payloads:
                for family in ("expert_comment", "linkedin_post"):
                    if family in payload:
                        initial_by_family.setdefault(family, str(payload[family]))
            assert set(initial_by_family) == {"expert_comment", "linkedin_post"}
            missing_initial_claims = [
                claim
                for family, claim, _code in IAS_UNSUPPORTED_SOFT_COPY_CLAIMS
                if claim not in initial_by_family[family]
            ]
            assert missing_initial_claims == []
            assert set(detected_unsupported_claims) == {
                claim for _family, claim, _code in IAS_UNSUPPORTED_SOFT_COPY_CLAIMS
            }
            retained_recommendations = " ".join(
                claim
                for family, claim, _code in IAS_UNSUPPORTED_SOFT_COPY_CLAIMS
                if family == "expert_comment"
                and claim.startswith(("Governance should", "Operating models should"))
            )
            assert artifacts["expert_comment"] == retained_recommendations
            assert artifacts["linkedin_post"] == ""
            assert all(
                claim not in artifacts[family]
                for family, claim, _code in IAS_UNSUPPORTED_SOFT_COPY_CLAIMS
                if not claim.startswith(
                    ("Governance should", "Operating models should")
                )
            )
            assert regeneration_audit["unchanged_family_sha256"] == {
                family: sha256_json(artifacts[family])
                for family in (
                    "summary",
                    "insights_candidates",
                    "insights_final",
                    "quotes_final",
                )
            }
        soft_copy_claims = artifacts["soft_copy_claim_provenance"]["claims"]
        repaired_claims = [
            claim
            for claim in soft_copy_claims
            if claim["artifact_family"] == "expert_comment"
        ]
        if reproduce_ias_soft_copy:
            assert len(repaired_claims) == 2
            assert all(
                claim["classification"] == "recommendation"
                and claim["regeneration_attempt"] == 0
                for claim in repaired_claims
            )
        else:
            assert artifacts["expert_comment"] == ""
            assert repaired_claims == []
        assert artifacts["summary"]["tldr"].encode() == (
            b"Customer demand is changing across segments."
        )
        assert artifacts["linkedin_post"].encode() == (
            b""
            if reproduce_ias_soft_copy
            else b"Read the report as an input to planning."
        )
        untouched_soft_copy_families = (
            {"summary"} if reproduce_ias_soft_copy else {"summary", "linkedin_post"}
        )
        assert all(
            claim["regeneration_attempt"] == 0
            for claim in soft_copy_claims
            if claim["artifact_family"] in untouched_soft_copy_families
        )
        if reproduce_ias_soft_copy:
            assert not any(
                claim["artifact_family"] == "linkedin_post"
                for claim in soft_copy_claims
            )
            retained_claims = json.loads(
                (analysis_dir / "retained_claim_validation.json").read_text(
                    encoding="utf-8"
                )
            )
            assert retained_claims["readiness_status"] == "awaiting_review"
            assert retained_claims["unsupported_factual_count"] == 0
            assert retained_claims["unresolved_factual_count"] == 0
            assert (
                json.loads(
                    (analysis_dir / "validation_regen_candidate_1.json").read_text(
                        encoding="utf-8"
                    )
                )["status"]
                == "pass"
            )
            assert (
                json.loads(
                    (
                        analysis_dir / "public_editorial_quality_regen_attempt_1.json"
                    ).read_text(encoding="utf-8")
                )["status"]
                == "pass"
            )
            assert (
                json.loads(
                    (analysis_dir / "publish_readiness.json").read_text(
                        encoding="utf-8"
                    )
                )["status"]
                == "pass"
            )
            for family in ("expert_comment", "linkedin_post"):
                prompt = artifacts["_cache"]["prompts"][
                    f"report_vs/artifacts/regenerate/{family}"
                ]
                assert prompt["namespace"] == f"report_vs/artifacts/regenerate/{family}"
                assert prompt["execution_identity"]
                assert prompt["prompt_content_hash"]
        assert entity.first_pass is False
        assert entity.bounded_recovery is True
    else:
        assert entity.first_pass is True, {
            "awaiting_review_first_failure_code": awaiting_review_stage.first_failure_code,
            "awaiting_review_first_failure_stage": awaiting_review_stage.first_failure_stage,
            "awaiting_review_recovery_type": awaiting_review_stage.recovery_type,
            "awaiting_review_attempts_required": awaiting_review_stage.attempts_required,
            "awaiting_review_terminal_disposition": (
                awaiting_review_stage.terminal_disposition
            ),
            "first_attempt_stage_details": [
                {
                    "to_state": stage.to_state,
                    "first_pass": stage.first_pass,
                    "first_failure_code": stage.first_failure_code,
                    "first_failure_stage": stage.first_failure_stage,
                    "recovery_type": stage.recovery_type,
                    "attempts_required": stage.attempts_required,
                    "terminal_disposition": stage.terminal_disposition,
                }
                for stage in entity.stages
            ],
        }
        assert entity.bounded_recovery is False
