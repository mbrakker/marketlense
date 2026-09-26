# ruff: noqa: E501

from __future__ import annotations

import json
import sqlite3
from hashlib import md5, sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import SourceIngestPayload
from src.contracts.validation_reliability import (
    ValidationReliabilityBuildRequest,
    ValidationReliabilityWriteRequest,
)
from src.contracts.validation_run_manifest import (
    PreselectedFrozenValidationCohortSubmissionRequest,
    PreselectedFrozenValidationSource,
)
from src.generators.claim_validation_generator import validate_retained_claims
from src.orchestrators.ingest_orchestrator import (
    submit_preselected_frozen_validation_cohort,
)
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.orchestrators import workflow_queue_orchestrator as queue_orchestrator
from src.services.config_service import build_ingest_settings, load_settings
from src.services.validation_reliability_service import (
    build_validation_reliability_artifact,
    write_validation_reliability_artifact,
)
from src.services.workflow_queue_service import (
    get_workflow_job,
    load_workflow_job_payload,
    materialize_workflow_outbox,
)
from src.utils.cache_utils import sha256_json
from tests.support.fakes import FakeOpenAIResult
from tests.support.ias_soft_copy_reproduction import (
    IAS_UNSUPPORTED_SOFT_COPY_CLAIMS,
    ias_soft_copy_payload,
)
from tests.test_workflow_queue_registry import _isolated_app_config, _workflow_job


def test_queue_stage_builder_preserves_workflow_lineage() -> None:
    job = _workflow_job(
        queue_name="report_acquisition", job_type="report_acquisition.v1"
    )
    stage = queue_orchestrator._stage_child_submission(
        job=job,
        payload=SourceIngestPayload(
            source_artifact_reference="retained:source.pdf",
            source_content_hash="source-md5",
            report_id="report-1",
            processing_version="parser.v2",
            validation_run_id="validation-1",
            cohort_id="cohort-1",
            validation_attempt_number=2,
            validation_parent_attempt_number=1,
        ),
        next_queue="report_selection",
        next_payload=SourceIngestPayload(
            source_artifact_reference="retained:source.pdf",
            source_content_hash="source-md5",
            report_id="report-1",
            processing_version="parser.v2",
        ),
    )
    assert stage.idempotency_key == "report-1:report_selection:source-md5:parser.v2"
    assert stage.root_workflow_id == job.job_id
    assert stage.correlation_id == job.job_id
    assert stage.source_identity_id == "source-1"
    assert stage.payload.validation_run_id == "validation-1"
    assert stage.payload.cohort_id == "cohort-1"
    assert stage.payload.validation_attempt_number == 2
    assert stage.payload.validation_parent_attempt_number == 1


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="submission-request-run",
        task_id="task-1",
        span_id="span-1",
        producer_commit_sha="build-sha",
    )


def _full_chain_model_response(call: dict) -> FakeOpenAIResult:
    """Return the smallest grounded fixture for each external model contract."""

    schema_name = call["text"]["format"]["name"]
    responses = {
        "doc_map_v1": {
            "schema_version": "1.0",
            "doc_id": "report-1",
            "title": "Industry Pulse Report 2026",
            "summary": (
                "A source-backed fixture report about media planning and advertising "
                "strategy."
            ),
            "publisher": "Industry Analytics Summit",
            "provenance_roles": {
                "publication_name": "",
                "publisher_name": "Industry Analytics Summit",
                "author_names": [],
                "author_kind": "unknown",
                "data_provider_names": [],
                "source_organization_names": [],
                "report_owner_name": "",
                "evidence": [
                    {
                        "role": "publisher_name",
                        "name": "Industry Analytics Summit",
                        "source_excerpt": "Industry Analytics Summit",
                    }
                ],
            },
            "sections": [
                {
                    "id": "market-demand",
                    "title": "Market demand",
                    "summary": (
                        "Media planning and advertising strategy priorities are changing."
                    ),
                    "key_points": [
                        "The report covers media planning and advertising strategy."
                    ],
                    "pages": [1],
                    "references": [],
                }
            ],
        },
        "taxonomy_v1": {
            "schema_version": "1.0",
            "taxonomy": ["advertising", "media_planning"],
            "primary_tags": ["advertising", "media_planning"],
            "secondary_tags": [],
            "tag_evidence": [
                {
                    "tag": "advertising",
                    "tier": "primary",
                    "section_label": "Market demand",
                    "evidence": "Digital media and advertising priorities are changing.",
                },
                {
                    "tag": "media_planning",
                    "tier": "primary",
                    "section_label": "Market demand",
                    "evidence": "The report describes media planning challenges.",
                },
            ],
            "region": "",
            "time_period": "2026",
            "not_found_reason": "",
        },
        "scope_v1": {
            "schema_version": "1.0",
            "scope": "The report covers media planning and advertising strategy.",
            "not_found_reason": "",
        },
        "methods_v1": {
            "schema_version": "1.0",
            "methods": ["The report assesses customer demand across segments."],
            "not_found_reason": "",
        },
        "findings_v1": {
            "schema_version": "1.0",
            "findings": [
                {
                    "id": "finding-1",
                    "text": "Customer demand is changing across segments.",
                    "evidence": "Customer demand is changing across segments.",
                    "confidence": "high",
                    "section_id": "market-demand",
                    "section_title": "Market demand",
                    "pages": [1],
                }
            ],
            "not_found_reason": "",
        },
        "limitations_v1": {
            "schema_version": "1.0",
            "limitations": ["The report is limited to the evidence it presents."],
            "not_found_reason": "",
        },
        "quote_candidates_v1": {
            "schema_version": "1.0",
            "quote_candidates": [
                {
                    "id": "quote-1",
                    "text": "Customer demand is changing across segments.",
                    "source": "Industry Analytics Summit",
                    "page": 1,
                }
            ],
            "not_found_reason": "",
        },
        "semantic_validation_output_v1": {"metrics": [], "quotes": []},
        "grounding_validation_output_v1": {"unsupported": [], "checks": []},
        "context_category_fit_v1": {
            "schema_version": "1.0",
            "selected_category_ids": ["advertising_media"],
            "category_fits": [
                {
                    "category_id": "advertising_media",
                    "label": "Advertising Strategy & Media",
                    "fit_score": 0.95,
                    "decision": "primary",
                    "why_fit": "The retained source covers media planning and advertising priorities.",
                    "why_not_fit": "",
                    "evidence_sections": ["market-demand"],
                }
            ],
        },
        "artifact_editorial_plan_v1": {
            "editorial_plan": {
                "report_thesis": "The retained evidence supports a cautious planning lens.",
                "themes": [
                    {
                        "theme": "Customer demand",
                        "priority": 1,
                        "evidence_ids": ["market-demand"],
                    },
                    {
                        "theme": "Commercial planning",
                        "priority": 2,
                        "evidence_ids": ["market-demand"],
                    },
                ],
            }
        },
        "artifact_cover_semantics_v1": {
            "cover_semantics": {
                "evidence_shape": "trend",
                "direction": "neutral",
                "geography_scope": "unknown",
                "evidence_density": "qualitative",
                "domain_layer": "forecast",
                "selection_reason": "The fixture contains qualitative demand evidence.",
            }
        },
        "artifact_insights_candidates_v1": {
            "insights_candidates": [
                {
                    "id": "insight-1",
                    "text": "Customer demand is changing across segments.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
                {
                    "id": "insight-2",
                    "text": "The report identifies changing demand patterns.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
                {
                    "id": "insight-3",
                    "text": "Commercial planning can account for changing demand patterns.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
                {
                    "id": "insight-4",
                    "text": "Demand patterns vary across customer segments.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
                {
                    "id": "insight-5",
                    "text": "Customer demand remains a relevant planning consideration.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
            ]
        },
        "artifact_insights_final_v1": {
            "insights_final": [
                {
                    "id": "insight-1",
                    "text": "Customer demand is changing across segments.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
                {
                    "id": "insight-2",
                    "text": "Market demand patterns are changing across segments.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
                {
                    "id": "insight-3",
                    "text": "Commercial planning can account for changing demand patterns.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
                {
                    "id": "insight-4",
                    "text": "Demand patterns vary across customer segments.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
                {
                    "id": "insight-5",
                    "text": "Customer demand remains a relevant planning consideration.",
                    "evidence_id": "market-demand",
                    "evidence": "Customer demand is changing across segments.",
                    "pages": [1],
                },
            ]
        },
        "artifact_quotes_final_v1": {"quotes_final": []},
        "artifact_summary_v1": {
            "summary": {
                "tldr": "Customer demand is changing across segments.",
                "card_tldr_compact": "Demand patterns are changing.",
                "executive_summary": (
                    "Industry Analytics Summit identifies changing customer demand "
                    "across segments."
                ),
                "claim_evidence_map": [
                    {
                        "claim": "Customer demand is changing across segments.",
                        "evidence_id": "market-demand",
                        "evidence": "Customer demand is changing across segments.",
                        "pages": [1],
                    }
                ],
            },
            "claim_provenance": [
                {
                    "claim": "Customer demand is changing across segments.",
                    "classification": "factual",
                    "evidence_ids": ["market-demand"],
                },
                {
                    "claim": "Demand patterns are changing.",
                    "classification": "factual",
                    "evidence_ids": ["market-demand"],
                },
                {
                    "claim": (
                        "Industry Analytics Summit identifies changing customer demand "
                        "across segments."
                    ),
                    "classification": "factual",
                    "evidence_ids": ["market-demand"],
                },
            ],
        },
        "artifact_expert_comment_v1": {
            "expert_comment": "Use the retained evidence as a planning input.",
            "claim_provenance": [
                {
                    "claim": "Use the retained evidence as a planning input.",
                    "classification": "recommendation",
                    "evidence_ids": [],
                }
            ],
        },
        "artifact_linkedin_post_v1": {
            "linkedin_post": "Read the report as an input to planning.",
            "claim_provenance": [
                {
                    "claim": "Read the report as an input to planning.",
                    "classification": "recommendation",
                    "evidence_ids": [],
                }
            ],
        },
    }
    if schema_name not in responses:
        raise AssertionError(f"missing full-chain model fixture for {schema_name}")
    return FakeOpenAIResult(
        output_text=json.dumps(responses[schema_name]),
        usage={"input_tokens": 10, "output_tokens": 10, "total_tool_calls": 0},
        id=f"fixture-{schema_name}",
    )


_UNSUPPORTED_SOFT_COPY_CLAIM = (
    "The report confirms that demand increased by 40% across all segments."
)
_REPAIRED_SOFT_COPY_CLAIM = "Planning should retain the source evidence."


def _json_prompt_value(call: dict, label: str) -> object:
    """Read one JSON fixture variable from the rendered repair prompt."""

    decoder = json.JSONDecoder()
    marker = f"{label}:"
    for message in call.get("messages", []):
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            continue
        start = content.find(marker)
        if start < 0:
            continue
        value_start = start + len(marker)
        try:
            value, _end = decoder.raw_decode(content[value_start:].lstrip())
        except ValueError:
            continue
        return value
    return None


def _full_chain_response_factory(
    *,
    repair_soft_copy: bool = False,
    reproduce_ias_soft_copy: bool = False,
    detected_unsupported_claims: list[str] | None = None,
):
    """Return the Responses API fixture, optionally forcing one claim repair."""

    def respond(call: dict) -> FakeOpenAIResult:
        response = _full_chain_model_response(call)
        schema_name = call["text"]["format"]["name"]
        payload = json.loads(response.output_text)
        unsupported_claims = (
            IAS_UNSUPPORTED_SOFT_COPY_CLAIMS
            if reproduce_ias_soft_copy
            else (("expert_comment", _UNSUPPORTED_SOFT_COPY_CLAIM, ""),)
        )
        seen_unsupported_claims = [
            (section, claim, code)
            for section, claim, code in unsupported_claims
            if claim in json.dumps(call, default=str)
        ]
        if schema_name == "grounding_validation_output_v1" and seen_unsupported_claims:
            if detected_unsupported_claims is not None:
                detected_unsupported_claims.extend(
                    claim for _section, claim, _code in seen_unsupported_claims
                )
            payload = {
                "unsupported": [
                    {
                        "section": section,
                        "text": claim,
                        "classification": "factual_claim",
                        "entailment_outcome": "not_established",
                        "violation_type": "unsupported_factual_claim",
                        "reason": (
                            "The retained source does not establish this claim"
                            + (f" ({code})." if code else ".")
                        ),
                    }
                    for section, claim, code in seen_unsupported_claims
                ],
                "checks": [],
            }
        return FakeOpenAIResult(
            output_text=json.dumps(payload), usage=response.usage, id=response.id
        )

    return respond


def _full_chain_chat_response_factory(
    *,
    repair_soft_copy: bool = False,
    reproduce_ias_soft_copy: bool = False,
    generated_soft_copy_payloads: list[dict[str, object]] | None = None,
    detected_unsupported_claims: list[str] | None = None,
):
    """Return the legacy chat-completions fixture used by artifact generation."""

    soft_copy_calls = {"expert_comment": 0, "linkedin_post": 0}
    repair_claim_calls = {"expert_comment": 0, "linkedin_post": 0}

    def respond(call: dict) -> SimpleNamespace:
        response_format = call["response_format"]
        schema_name = response_format.get("json_schema", {}).get("name", "")
        if not schema_name:
            response = FakeOpenAIResult(
                output_text=json.dumps({"results": []}),
                usage={
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "total_tool_calls": 0,
                },
                id="fixture-chat-rank-candidates",
            )
        else:
            if schema_name == "regeneration_repair_decision_v1":
                repair_context = _json_prompt_value(call, "Repair context JSON")
                failures = _json_prompt_value(call, "Validator failures JSON")
                if not isinstance(repair_context, dict):
                    raise AssertionError("repair fixture is missing its typed context")
                allowed_paths = repair_context.get("allowed_paths") or []
                if len(allowed_paths) != 1:
                    raise AssertionError(
                        f"repair fixture expects one atomic target, got {allowed_paths!r}"
                    )
                path = str(allowed_paths[0])
                family = path.split(".", 1)[0].split("[", 1)[0]
                if family in repair_claim_calls:
                    repair_claim_calls[family] += 1
                replacement = (
                    _REPAIRED_SOFT_COPY_CLAIM
                    if family == "expert_comment" and repair_claim_calls[family] == 1
                    else (
                        "Read the report as an input to planning."
                        if family == "linkedin_post"
                        else ""
                    )
                )
                # These fixture repairs are recommendations, not claims that
                # rely on a cited source span. Do not invent lineage IDs from
                # the wider prompt package.
                used_ids: list[str] = []
                diagnosed_failure = (
                    str(failures[0].get("rule_id") or "grounding")
                    if isinstance(failures, list)
                    and failures
                    and isinstance(failures[0], dict)
                    else "grounding"
                )
                decision = {
                    "schema_version": "1.0",
                    "diagnosed_failure_class": diagnosed_failure,
                    "repair_action": repair_context["repair_action"],
                    "repair_strategy": repair_context["repair_strategy"],
                    "evidence_ids_used": used_ids if replacement else [],
                    "protected_fields": repair_context["required_protected_fields"],
                    "changed_paths": [path],
                    "minimal_patch": [
                        {"op": "replace", "path": path, "value": replacement}
                    ],
                    "claim_provenance": (
                        [
                            {
                                "claim": replacement,
                                "classification": "recommendation",
                                "evidence_ids": used_ids,
                            }
                        ]
                        if replacement
                        else []
                    ),
                }
                payload = {"repair_decision": decision}
                response = FakeOpenAIResult(
                    output_text=json.dumps(payload),
                    usage={
                        "input_tokens": 10,
                        "output_tokens": 10,
                        "total_tool_calls": 0,
                    },
                    id="fixture-regeneration-repair-decision",
                )
            else:
                response = _full_chain_model_response(
                    {"text": {"format": {"name": schema_name}}}
                )
                payload = json.loads(response.output_text)
            family = schema_name.removeprefix("artifact_").removesuffix("_v1")
            if schema_name == "regeneration_repair_decision_v1":
                pass
            elif reproduce_ias_soft_copy and family in soft_copy_calls:
                soft_copy_calls[family] += 1
                payload = ias_soft_copy_payload(
                    family,
                    repaired=soft_copy_calls[family] > 1,
                    repaired_expert_comment=_REPAIRED_SOFT_COPY_CLAIM,
                )
                if generated_soft_copy_payloads is not None:
                    generated_soft_copy_payloads.append(dict(payload))
            elif repair_soft_copy and schema_name == "artifact_expert_comment_v1":
                soft_copy_calls["expert_comment"] += 1
                if soft_copy_calls["expert_comment"] == 1:
                    payload = {
                        "expert_comment": _UNSUPPORTED_SOFT_COPY_CLAIM,
                        "claim_provenance": [
                            {
                                "claim": _UNSUPPORTED_SOFT_COPY_CLAIM,
                                "classification": "factual",
                                "evidence_ids": ["market-demand"],
                            }
                        ],
                    }
                else:
                    payload = {
                        "expert_comment": _REPAIRED_SOFT_COPY_CLAIM,
                        "claim_provenance": [
                            {
                                "claim": _REPAIRED_SOFT_COPY_CLAIM,
                                "classification": "recommendation",
                                "evidence_ids": [],
                            }
                        ],
                    }
            unsupported_claims = (
                IAS_UNSUPPORTED_SOFT_COPY_CLAIMS
                if reproduce_ias_soft_copy
                else (("expert_comment", _UNSUPPORTED_SOFT_COPY_CLAIM, ""),)
            )
            seen_unsupported_claims = [
                (section, claim, code)
                for section, claim, code in unsupported_claims
                if claim in json.dumps(call, default=str)
            ]
            if (
                schema_name == "grounding_validation_output_v1"
                and seen_unsupported_claims
            ):
                if detected_unsupported_claims is not None:
                    detected_unsupported_claims.extend(
                        claim for _section, claim, _code in seen_unsupported_claims
                    )
                payload = {
                    "unsupported": [
                        {
                            "section": section,
                            "text": claim,
                            "classification": "factual_claim",
                            "entailment_outcome": "not_established",
                            "violation_type": "unsupported_factual_claim",
                            "reason": (
                                "The retained source does not establish this claim"
                                + (f" ({code})." if code else ".")
                            ),
                        }
                        for section, claim, code in seen_unsupported_claims
                    ],
                    "checks": [],
                }
            response = FakeOpenAIResult(
                output_text=json.dumps(payload),
                usage=response.usage,
                id=response.id,
            )
        return SimpleNamespace(
            id=f"fixture-chat-{schema_name}",
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=response.output_text))
            ],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=10,
                total_tokens=20,
                prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            ),
        )

    return respond


@pytest.mark.parametrize(
    ("repair_soft_copy", "reproduce_ias_soft_copy"),
    ((False, False), (True, False), (False, True)),
    ids=("clean", "unsupported-soft-copy-repair", "ias-known-claim-repair"),
)
def test_a21_full_chain_from_frozen_cohort_through_awaiting_review(
    tmp_path,
    external_boundary_mocks_only,
    fake_openai,
    repair_soft_copy: bool,
    reproduce_ias_soft_copy: bool,
) -> None:
    """Run the deterministic durable A21 chain with clean and repaired fixtures."""
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
    source_path = Path(
        "tests/fixtures/pdf_benchmark/golden/IAS - Industry_Pulse_Report_2026_ACIG.pdf"
    ).resolve()
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
        assert artifacts["expert_comment"] == _REPAIRED_SOFT_COPY_CLAIM
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
            assert (
                artifacts["linkedin_post"] == "Read the report as an input to planning."
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
        assert len(repaired_claims) == 1
        assert repaired_claims[0]["regeneration_attempt"] == 1
        assert artifacts["summary"]["tldr"].encode() == (
            b"Customer demand is changing across segments."
        )
        assert artifacts["linkedin_post"].encode() == (
            b"Read the report as an input to planning."
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
            assert any(
                claim["artifact_family"] == "linkedin_post"
                and claim["regeneration_attempt"] == 1
                for claim in soft_copy_claims
            )
            evidence_packs = {
                name: json.loads(
                    (analysis_dir / f"{name}.json").read_text(encoding="utf-8")
                )
                for name in (
                    "doc_map",
                    "findings",
                    "limitations",
                    "methods",
                    "quote_candidates",
                    "scope",
                )
            }
            retained_claims = validate_retained_claims(
                artifacts,
                evidence_packs,
                semantic_validator=lambda candidate, sources: (
                    bool(sources) or not candidate.factual,
                    "fixture_current_schema_evidence",
                    "fixture-current-schema-semantic-v1",
                ),
            )
            assert retained_claims.readiness_status == "awaiting_review"
            assert retained_claims.unsupported_factual_count == 0
            assert retained_claims.unresolved_factual_count == 0
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
