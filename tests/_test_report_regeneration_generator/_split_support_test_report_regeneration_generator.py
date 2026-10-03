# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.contracts.ingest import IngestSettings
from src.contracts.openai import OpenAIResponseResult
from src.contracts.prompts import (
    PromptDependency,
    PromptDependencyManifest,
    PromptRenderResponse,
    PromptSet,
    PromptTemplate,
)
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
    RepairDecision,
)
from src.contracts.run_context import RunContext
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_from_payload,
    soft_copy_claim_provenance_to_payload,
    soft_copy_material_sentences,
    soft_copy_public_text,
    valid_soft_copy_evidence_selection,
)
from src.contracts.validation import ValidationIssue
from src.generators._artifact_generator.storage import (
    build_chart_insight_cards,
    build_key_figures,
    derive_metric_spine_from_insights,
)
from src.generators.artifact_normalization import (
    artifact_evidence_span_index,
    normalize_artifact_quotes,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    validation_issues_from_public_editorial_quality,
)
from src.generators.report_regeneration_generator import (
    _build_grounding_package,
    _build_regeneration_state,
    _build_soft_copy_claim_evidence_package,
    _deterministic_family_soft_copy_bindings,
    _merge_regenerated_insights_by_stable_id,
    _repair_decision_protected_fields_are_complete,
    _restore_final_insight_evidence_bindings,
    _restore_missing_final_insight_roster,
    _summary_claim_map_item_index,
)
from src.generators.report_regeneration_generator import (
    regenerate_artifacts as _regenerate_artifacts,
)
from src.generators.soft_copy_claim_provenance import (
    assert_retained_soft_copy_claims_match_public_copy,
    build_soft_copy_claim_provenance,
    retained_soft_copy_claims_cover_text,
)
from src.generators.validation.regeneration_candidate import (
    validate_regeneration_candidate,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _allowed_paths,
    _build_regeneration_plan,
    _build_target,
)
from src.orchestrators._report_analysis_orchestrator.validation import (
    _scope_validation_report,
)
from src.utils.errors import AppError
from ._shared import (
    _legacy_repair_decision_response,
    _parse_fixture_variables,
)

METRIC = {
    "value": "",
    "unit": "",
    "trend": "",
    "timeframe": "",
    "geography": "",
    "segment": "",
    "sample_size": "",
    "confidence": "",
}


def regenerate_artifacts(request, **kwargs):
    """Complete legacy hand-written test plans with planner-owned scope."""
    targets = []
    for target in request.plan.targets:
        issues = list(target.issues)
        had_no_issues = not issues
        if not issues and target.target_section in {
            "summary",
            "insights_bundle",
            "key_figures",
            "quotes",
            "expert_comment",
            "linkedin_post",
            "topics",
        }:
            family = target.target_section
            affected_section = (
                "summary.executive_summary" if family == "summary" else family
            )
            claim_id = ""
            evidence_ids: list[str] = []
            if family in {"expert_comment", "linkedin_post"}:
                provenance = request.current_artifacts.get(
                    "soft_copy_claim_provenance", {}
                )
                claims = (
                    provenance.get("claims", []) if isinstance(provenance, dict) else []
                )
                claim = next(
                    (
                        item
                        for item in claims
                        if isinstance(item, dict)
                        and item.get("artifact_family") == family
                    ),
                    {},
                )
                claim_id = str(claim.get("claim_id") or "")
                evidence_ids = list(claim.get("evidence_ids") or [])
            issues = [
                RegenerationIssue(
                    rule_id="test_fixture_repair",
                    affected_section=affected_section,
                    message="A deterministic test fixture requested repair.",
                    severity="error",
                    entity_id=claim_id,
                    evidence_ids=evidence_ids,
                )
            ]
        planned = _build_target(
            target.target_section,
            issues,
            artifacts=request.current_artifacts,
        )
        paths = list(target.allowed_paths) or _allowed_paths(
            target.target_section,
            issues,
            request.current_artifacts,
            target.repair_action,
        )
        if had_no_issues and target.target_section in {
            "summary",
            "expert_comment",
            "linkedin_post",
        }:
            paths = (
                [f"{target.target_section}[claim_index=0]"]
                if target.target_section in {"expert_comment", "linkedin_post"}
                else paths[:1]
            )
        targets.append(
            replace(
                target,
                issues=issues,
                allowed_paths=paths,
                repair_action=target.repair_action
                or (planned.repair_action if planned else ""),
                repair_strategy=target.repair_strategy
                or (planned.repair_strategy if planned else ""),
            )
        )
    return _regenerate_artifacts(
        replace(request, plan=replace(request.plan, targets=targets)), **kwargs
    )


def _append_retained_soft_copy_sibling(
    artifacts: dict, family: str, sentence: str = "A retained sibling claim."
) -> None:
    existing = artifacts[family]
    claims = artifacts["soft_copy_claim_provenance"]["claims"]
    template = next(claim for claim in claims if claim["artifact_family"] == family)
    retained = existing.rstrip()
    if not retained.endswith((".", "!", "?")):
        retained = f"{retained}."
        retained_hash = hashlib.sha256(retained.encode()).hexdigest()
        template["claim_id"] = f"soft_copy:{family}:{retained_hash[:16]}"
        template["text_hash"] = retained_hash
    artifacts[family] = f"{retained} {sentence}"
    sibling = dict(template)
    sibling["claim_id"] = f"soft_copy:{family}:retained-sibling"
    sibling["text_hash"] = hashlib.sha256(sentence.encode()).hexdigest()
    claims.append(sibling)


def _soft_copy_claim(
    *, evidence_ids: tuple[str, ...] = (), source_spans: tuple[dict, ...] = ()
) -> SoftCopyClaimProvenance:
    return SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:claim-1",
        text_hash="a" * 64,
        classification="interpretive",
        evidence_ids=evidence_ids,
        source_spans=source_spans,
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )


class _FakePromptClient:
    def __init__(self) -> None:
        self.render_calls: list[dict] = []

    def load_prompt_set(self, req, ctx):
        del ctx
        manifest = PromptDependencyManifest(
            schema_version="1.0",
            namespace=req.namespace,
            system_root=PromptDependency(
                schema_version="1.0",
                path=f"{req.namespace}/system.yaml",
                sha256="a" * 64,
                kind="system_root",
            ),
            user_root=PromptDependency(
                schema_version="1.0",
                path=f"{req.namespace}/user.yaml",
                sha256="b" * 64,
                kind="user_root",
            ),
        )
        return PromptSet(
            schema_version="1.0",
            system=PromptTemplate(
                schema_version="1.0",
                path=f"{req.namespace}/system.yaml",
                text=f"system::{req.namespace}",
                sha256=f"sys-{req.namespace}",
            ),
            user=PromptTemplate(
                schema_version="1.0",
                path=f"{req.namespace}/user.yaml",
                text=f"user::{req.namespace}",
                sha256=f"user-{req.namespace}",
            ),
            dependency_manifest=manifest,
            prompt_content_hash="c" * 64,
        )

    def render_prompt(self, req, ctx):
        del ctx
        rendered = f"{req.template.text}|{json.dumps(req.variables, sort_keys=True, ensure_ascii=False)}"
        self.render_calls.append(
            {
                "path": req.template.path,
                "variables": dict(req.variables),
                "text": rendered,
            }
        )
        return PromptRenderResponse(schema_version="1.0", text=rendered)


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def openai_chat_json(self, req, ctx):
        result = self._legacy_chat_json(req, ctx)
        if "regeneration_repair_decision" not in (
            req.structured_output_schema_identity or ""
        ):
            return result
        return _legacy_repair_decision_response(req, result)

    def _legacy_chat_json(self, req, ctx):
        del ctx
        self.calls.append(req)
        if "system::report_vs/artifacts/cover_semantics" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text=(
                    '{"cover_semantics":{"evidence_shape":"trend",'
                    '"direction":"rising","geography_scope":"global",'
                    '"evidence_density":"metric_rich","domain_layer":"grid",'
                    '"selection_reason":"A rising time series is the strongest visual story."}}'
                ),
                parsed_json={
                    "cover_semantics": {
                        "evidence_shape": "trend",
                        "direction": "rising",
                        "geography_scope": "global",
                        "evidence_density": "metric_rich",
                        "domain_layer": "grid",
                        "selection_reason": (
                            "A rising time series is the strongest visual story."
                        ),
                    }
                },
                request_id="req-cover",
            )
        if "system::report_vs/artifacts/regenerate/insights_final" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"insights_final":[{"id":"insight-1","text":"Repaired final insight","evidence_id":"f1","evidence":"Evidence text","metric":{"value":"","unit":"","trend":"","timeframe":"","geography":"","segment":"","sample_size":"","confidence":""},"pages":[1]}]}',
                parsed_json={
                    "insights_final": [
                        {
                            "id": "insight-1",
                            "text": "Repaired final insight",
                            "evidence_id": "f1",
                            "evidence": "Evidence text",
                            "metric": dict(METRIC),
                            "pages": [1],
                        },
                        {
                            "id": "insight-2",
                            "text": "Repaired margin insight",
                            "evidence_id": "f2",
                            "evidence": "Evidence text 2",
                            "metric": dict(METRIC),
                            "pages": [2],
                        },
                    ]
                },
                request_id="req-final",
            )
        if (
            "system::report_vs/artifacts/regenerate/insights_candidates"
            in req.system_prompt
        ):
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"insights_candidates":[{"id":"candidate-1","text":"Repaired candidate","evidence_id":"f1","evidence":"Evidence text","metric":{"value":"","unit":"","trend":"","timeframe":"","geography":"","segment":"","sample_size":"","confidence":""},"pages":[1],"score":1.0}]}',
                parsed_json={
                    "insights_candidates": [
                        {
                            "id": "candidate-1",
                            "text": "Repaired candidate",
                            "evidence_id": "f1",
                            "evidence": "Evidence text",
                            "metric": dict(METRIC),
                            "pages": [1],
                            "score": 1.0,
                        },
                        {
                            "id": "candidate-2",
                            "text": "Repaired margin candidate",
                            "evidence_id": "f2",
                            "evidence": "Evidence text 2",
                            "metric": dict(METRIC),
                            "pages": [2],
                            "score": 0.9,
                        },
                    ]
                },
                request_id="req-candidates",
            )
        if "system::report_vs/artifacts/regenerate/summary" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"summary":{"tldr":"Repaired TLDR.","card_tldr_compact":"Repaired TLDR.","executive_summary":"Repaired executive summary","claim_evidence_map":[{"claim":"Grounded claim","evidence_id":"f1","evidence":"Evidence text","pages":[1]}]}}',
                parsed_json={
                    "summary": {
                        "tldr": "Repaired TLDR.",
                        "card_tldr_compact": "Repaired TLDR.",
                        "executive_summary": "Repaired executive summary",
                        "claim_evidence_map": [
                            {
                                "claim": "Grounded claim",
                                "evidence_id": "f1",
                                "evidence": "Evidence text",
                                "pages": [1],
                            }
                        ],
                    },
                    "claim_provenance": [
                        {
                            "claim": "Repaired TLDR.",
                            "classification": "interpretive",
                            "evidence_ids": ["f1"],
                        },
                        {
                            "claim": "Repaired executive summary",
                            "classification": "interpretive",
                            "evidence_ids": ["f1"],
                        },
                    ],
                },
                request_id="req-summary",
            )
        if "system::report_vs/artifacts/regenerate/quotes" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"quotes_final":[{"text":"A paraphrased section summary","speaker":"Unknown","citation":"Topic","page":1,"evidence_id":"sec-1"}]}',
                parsed_json={
                    "quotes_final": [
                        {
                            "text": "A paraphrased section summary",
                            "speaker": "Unknown",
                            "citation": "Topic",
                            "page": 1,
                            "evidence_id": "sec-1",
                        }
                    ]
                },
                request_id="req-quotes",
            )
        if "system::report_vs/artifacts/regenerate/expert_comment" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"expert_comment":"Retention and margin evidence create a supported planning tension."}',
                parsed_json={
                    "expert_comment": (
                        "Retention and margin evidence create a supported planning "
                        "tension."
                    ),
                    "claim_provenance": [
                        {
                            "claim": (
                                "Retention and margin evidence create a supported "
                                "planning tension."
                            ),
                            "classification": "interpretive",
                            "evidence_ids": ["f1", "f2"],
                        }
                    ],
                },
                request_id="req-expert",
            )
        if "system::report_vs/artifacts/regenerate/linkedin_post" in req.system_prompt:
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"linkedin_post":"Retention efficiency is replacing broad expansion."}',
                parsed_json={
                    "linkedin_post": "Retention efficiency is replacing broad expansion.",
                    "claim_provenance": [
                        {
                            "claim": "Retention efficiency is replacing broad expansion.",
                            "classification": "interpretive",
                            "evidence_ids": ["f1"],
                        }
                    ],
                },
                request_id="req-linkedin",
            )
        raise AssertionError(
            f"Unexpected prompt payload: {req.system_prompt} {req.user_prompt}"
        )

    def openai_respond_with_vector_store(self, req, ctx):
        return self.openai_chat_json(req, ctx)


class _TemporalSummaryOpenAIClient(_FakeOpenAIClient):
    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/summary" in req.system_prompt:
            source = "Share fell from 43% in Q1 2025 to 41% in Q2 2025."
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(
                    {
                        "summary": {
                            "tldr": source,
                            "card_tldr_compact": source,
                            "executive_summary": source,
                            "claim_evidence_map": [
                                {
                                    "claim": source,
                                    "evidence_id": "f1",
                                    "evidence": source,
                                    "pages": [1],
                                }
                            ],
                        }
                    }
                ),
                parsed_json={
                    "summary": {
                        "tldr": source,
                        "card_tldr_compact": source,
                        "executive_summary": source,
                        "claim_evidence_map": [
                            {
                                "claim": source,
                                "evidence_id": "f1",
                                "evidence": source,
                                "pages": [1],
                            }
                        ],
                    },
                    "claim_provenance": [
                        {
                            "claim": source,
                            "classification": "factual",
                            "evidence_ids": ["f1"],
                        }
                    ],
                },
                request_id="req-temporal-summary",
            )
        return super()._legacy_chat_json(req, ctx)


class _MobileSoWhatOpenAIClient(_FakeOpenAIClient):
    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/insights_final" in req.system_prompt:
            self.calls.append(req)
            repaired = {
                "id": "insight-1",
                "text": "Old final insight",
                "so_what": "The repaired implication is evidence-led.",
                "evidence_id": "f1",
                "evidence": "Evidence text",
                "metric": dict(METRIC),
                "pages": [1],
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps({"insights_final": [repaired]}),
                parsed_json={"insights_final": [repaired]},
                request_id="req-mobile-so-what",
            )
        return super()._legacy_chat_json(req, ctx)


class _EvidenceRebindOpenAIClient(_FakeOpenAIClient):
    def __init__(self, evidence_id: str) -> None:
        super().__init__()
        self.evidence_id = evidence_id

    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/insights_final" in req.system_prompt:
            self.calls.append(req)
            repaired = {
                "id": "insight-1",
                "text": "The repaired insight follows retained source evidence.",
                "evidence_id": self.evidence_id,
                "evidence": "Model supplied evidence text.",
                "metric": dict(METRIC),
                "pages": [1],
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps({"insights_final": [repaired]}),
                parsed_json={"insights_final": [repaired]},
                request_id="req-evidence-rebind",
            )
        return super()._legacy_chat_json(req, ctx)


class _ClaimScopedExpertOpenAIClient(_FakeOpenAIClient):
    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/expert_comment" in req.system_prompt:
            self.calls.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"expert_comment":"Repaired middle claim."}',
                parsed_json={
                    "expert_comment": "Repaired middle claim.",
                    "claim_provenance": [
                        {
                            "claim": "Repaired middle claim.",
                            "classification": "interpretive",
                            "evidence_ids": ["f2"],
                        }
                    ],
                },
                request_id="req-claim-scoped-expert",
            )
        return super()._legacy_chat_json(req, ctx)


class _FactualClaimScopedExpertOpenAIClient(_ClaimScopedExpertOpenAIClient):
    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/expert_comment" in req.system_prompt:
            self.calls.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"expert_comment":"Repaired middle claim."}',
                parsed_json={
                    "expert_comment": "Repaired middle claim.",
                    "claim_provenance": [
                        {
                            "claim": "Repaired middle claim.",
                            "classification": "factual",
                            "evidence_ids": ["f2"],
                        }
                    ],
                },
                request_id="req-factual-claim-scoped-expert",
            )
        return super()._legacy_chat_json(req, ctx)


class _OverlongClaimScopedExpertOpenAIClient(_ClaimScopedExpertOpenAIClient):
    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/expert_comment" in req.system_prompt:
            self.calls.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"expert_comment":"A supported replacement. An extra claim."}',
                parsed_json={
                    "expert_comment": "A supported replacement. An extra claim.",
                    "claim_provenance": [
                        {
                            "claim": "A supported replacement.",
                            "classification": "interpretive",
                            "evidence_ids": ["f2"],
                        }
                    ],
                },
                request_id="req-overlong-claim",
            )
        return super()._legacy_chat_json(req, ctx)


class _PunctuationClaimScopedExpertOpenAIClient(_ClaimScopedExpertOpenAIClient):
    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/expert_comment" in req.system_prompt:
            self.calls.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"expert_comment":"Repaired middle claim."}',
                parsed_json={
                    "expert_comment": "Repaired middle claim.",
                    "claim_provenance": [
                        {
                            "claim": "Repaired middle claim!",
                            "classification": "interpretive",
                            "evidence_ids": ["f2"],
                        }
                    ],
                },
                request_id="req-punctuation-claim",
            )
        return super()._legacy_chat_json(req, ctx)


class _ClaimScopedSoftCopyOpenAIClient(_ClaimScopedExpertOpenAIClient):
    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/linkedin_post" in req.system_prompt:
            self.calls.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"linkedin_post":"Repaired LinkedIn claim."}',
                parsed_json={
                    "linkedin_post": "Repaired LinkedIn claim.",
                    "claim_provenance": [
                        {
                            "claim": "Repaired LinkedIn claim.",
                            "classification": "interpretive",
                            "evidence_ids": ["f2"],
                        }
                    ],
                },
                request_id="req-claim-scoped-linkedin",
            )
        if "system::report_vs/artifacts/regenerate/summary" in req.system_prompt:
            self.calls.append(req)
            return OpenAIResponseResult(
                schema_version="1.0",
                text='{"summary":{"executive_summary":"Repaired summary claim."}}',
                parsed_json={
                    "summary": {"executive_summary": "Repaired summary claim."},
                    "claim_provenance": [
                        {
                            "claim": "Repaired summary claim.",
                            "classification": "interpretive",
                            "evidence_ids": ["f2"],
                        }
                    ],
                },
                request_id="req-claim-scoped-summary",
            )
        return super()._legacy_chat_json(req, ctx)


class _MultiClaimScopedExpertOpenAIClient(_FakeOpenAIClient):
    """Return a distinct replacement for each bounded claim repair request."""

    def _legacy_chat_json(self, req, ctx):
        if "system::report_vs/artifacts/regenerate/expert_comment" in req.system_prompt:
            self.calls.append(req)
            replacement = (
                "Repaired second claim."
                if len(self.calls) == 1
                else "Repaired third claim."
            )
            evidence_id = "f2" if "second" in replacement else "f3"
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps({"expert_comment": replacement}),
                parsed_json={
                    "expert_comment": replacement,
                    "claim_provenance": [
                        {
                            "claim": replacement,
                            "classification": "interpretive",
                            "evidence_ids": [evidence_id],
                        }
                    ],
                },
                request_id=f"req-{evidence_id}",
            )
        return super()._legacy_chat_json(req, ctx)


def _settings(tmp_path: Path) -> IngestSettings:
    output_dir = tmp_path / "out"
    cache_dir = tmp_path / "cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-5-mini",
        batch_limit=1,
        output_dir=str(output_dir),
        cache_dir=str(cache_dir),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path=str(tmp_path / "cats.yaml"),
        cover_style_path=str(tmp_path / "cover.yaml"),
        ingest_lock_path=str(tmp_path / "lock"),
        temperature=0.0,
        model_pricing={},
        cost_ledger_path=str(output_dir / "cost-ledger.jsonl"),
        cost_daily_path=str(output_dir / "cost-daily.json"),
        llm_execution_policies={
            "report_vs": {
                "schema_version": "1.0",
                "provider": "openai",
                "model": "gpt-5-mini",
                "temperature": 0.0,
                "seed_policy": "inherit",
                "max_output_tokens": 2048,
                "retrieval_mode": "chat_json",
                "timeout_seconds": 30.0,
                "provider_retry_count": 0,
                "structured_output_mode": "json_object",
                "fallback_policy": "same_provider_only",
                "pricing_key": "gpt-5-mini",
            }
        },
    )


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _current_artifacts() -> dict:
    retained_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family=family,
            claim_id=f"soft_copy:{family}:{hashlib.sha256(text.encode()).hexdigest()[:16]}",
            text_hash=hashlib.sha256(text.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(),
            source_spans=(),
            producing_prompt_identity={"namespace": f"report_vs/artifacts/{family}"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for family, text in (
            ("summary", "Old TLDR."),
            ("summary", "Old summary"),
            ("expert_comment", "Old expert"),
            ("linkedin_post", "Old linkedin"),
        )
    ]
    return {
        "schema_version": "3.0",
        "_cache": {
            "prompts": {
                "report_vs/artifacts/insights_final": {"prompt_content_hash": "c" * 64}
            }
        },
        "editorial_plan": {
            "report_thesis": "The report's retained evidence changes planning.",
            "themes": [
                {"theme": "Primary evidence", "priority": 1, "evidence_ids": ["f1"]},
                {"theme": "Margin evidence", "priority": 2, "evidence_ids": ["f2"]},
            ],
        },
        "toc_topics": ["Topic"],
        "summary": {
            "tldr": "Old TLDR.",
            "card_tldr_compact": "Old TLDR.",
            "executive_summary": "Old summary",
            "claim_evidence_map": [
                {
                    "claim": "Old claim",
                    "evidence_id": "f1",
                    "evidence": "Evidence text",
                    "pages": [1],
                }
            ],
        },
        "cover_semantics": {
            "evidence_shape": "trend",
            "direction": "rising",
            "geography_scope": "global",
            "evidence_density": "metric_rich",
            "domain_layer": "grid",
            "selection_reason": "Rising time-series evidence dominates the report.",
        },
        "insights_candidates": [
            {
                "id": "candidate-1",
                "text": "Old candidate",
                "evidence_id": "f1",
                "evidence": "Evidence text",
                "metric": dict(METRIC),
                "pages": [1],
                "score": 1.0,
            }
        ],
        "insights_final": [
            {
                "id": "insight-1",
                "text": "Old final insight",
                "evidence_id": "f1",
                "evidence": "Evidence text",
                "metric": dict(METRIC),
                "pages": [1],
            },
            {
                "id": "insight-2",
                "text": "Old final insight 2",
                "evidence_id": "f2",
                "evidence": "Evidence text 2",
                "metric": dict(METRIC),
                "pages": [2],
            },
            {
                "id": "insight-3",
                "text": "Old final insight 3",
                "evidence_id": "f3",
                "evidence": "Evidence text 3",
                "metric": dict(METRIC),
                "pages": [3],
            },
            {
                "id": "insight-4",
                "text": "Old final insight 4",
                "evidence_id": "f4",
                "evidence": "Evidence text 4",
                "metric": dict(METRIC),
                "pages": [4],
            },
            {
                "id": "insight-5",
                "text": "Old final insight 5",
                "evidence_id": "f5",
                "evidence": "Evidence text 5",
                "metric": dict(METRIC),
                "pages": [5],
            },
        ],
        "quotes_final": [
            {
                "text": "Old quote",
                "speaker": "Speaker",
                "citation": "Section",
                "page": 1,
                "evidence_id": "q1",
                "source_pack": "quote_candidates",
            }
        ],
        "expert_comment": "Old expert",
        "linkedin_post": "Old linkedin",
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            retained_claims
        ),
        "source_status": {
            "schema_version": "1.0",
            "text_density": 100.0,
            "density_threshold": 0.0,
            "pages_sampled": 1,
            "char_count": 100,
            "not_available": False,
            "reason": "",
            "evidence_present": True,
        },
    }


def _evidence_packs() -> dict:
    return {
        "doc_map": {
            "doc_id": "doc-1",
            "title": "Doc title",
            "sections": [
                {
                    "id": "sec-1",
                    "title": "Topic",
                    "summary": "Topic summary",
                    "pages": [1],
                }
            ],
        },
        "findings": {
            "findings": [
                {"id": "f1", "evidence": "Evidence text", "text": "Finding text"},
                {"id": "f2", "evidence": "Evidence text 2", "text": "Second finding"},
            ]
        },
        "quote_candidates": {
            "quote_candidates": [{"id": "q1", "text": "Old quote", "source": "Section"}]
        },
    }


__all__ = [name for name in globals() if not name.startswith("__")]
