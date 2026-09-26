# ruff: noqa: E501

# ruff: noqa: F401
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
            if schema_name == "regeneration_repair_decision_v3":
                repair_context = _json_prompt_value(call, "Repair context JSON")
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
                decision = {
                    "schema_version": "1.0",
                    "repair_action": repair_context["repair_action"],
                    "repair_strategy": repair_context["repair_strategy"],
                    "evidence_ids_used": used_ids if replacement else [],
                    "protected_fields": repair_context["required_protected_fields"],
                    "changed_paths": [path],
                    "minimal_patch": [
                        {
                            "op": "replace",
                            "path": path,
                            "value_json": json.dumps(replacement, ensure_ascii=False),
                        }
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
            if schema_name == "regeneration_repair_decision_v3":
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


__all__ = [name for name in globals() if not name.startswith("__")]
