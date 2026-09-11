from __future__ import annotations

import hashlib
import json
from copy import deepcopy
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
)
from src.contracts.run_context import RunContext
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_to_payload,
)
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
    validation_issues_from_public_editorial_quality,
)
from src.generators.report_regeneration_generator import (
    _build_regeneration_state,
    _build_grounding_package,
    _build_soft_copy_claim_evidence_package,
    _merge_regenerated_insights_by_stable_id,
    _restore_final_insight_evidence_bindings,
    _restore_missing_final_insight_roster,
    regenerate_artifacts,
)
from src.generators.validation.regeneration_candidate import (
    validate_regeneration_candidate,
)
from src.generators.soft_copy_claim_provenance import (
    retained_soft_copy_claims_cover_text,
)
from src.orchestrators._report_analysis_orchestrator.regeneration_plan import (
    _build_regeneration_plan,
)
from src.utils.errors import AppError

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


def test_restore_missing_final_insight_roster_replaces_duplicate_model_id() -> None:
    prior = [
        {"id": "insight-1", "text": "Prior one", "evidence_id": "f1"},
        {"id": "insight-2", "text": "Prior two", "evidence_id": "f2"},
    ]
    selected = [
        {"id": "insight-2", "text": "Repaired two", "evidence_id": "f3"},
        {"id": "insight-2", "text": "Duplicate model ID", "evidence_id": "f4"},
    ]

    restored = _restore_missing_final_insight_roster(
        selected_insights=selected,
        prior_final_insights=prior,
    )

    assert [item["id"] for item in restored] == ["insight-2", "insight-1"]
    assert restored[0]["text"] == "Repaired two"
    assert restored[1] == prior[0]


def test_grounding_package_quarantines_failed_evidence_and_uses_replacements() -> None:
    target = RegenerationTarget(
        target_section="insights_bundle",
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="insights:attention.so_what",
                message="The claim adds an unsupported causal outcome.",
                severity="error",
                evidence_ids=["failed-evidence"],
                excluded_evidence_ids=["failed-evidence"],
            )
        ],
    )

    package = _build_grounding_package(
        target=target,
        prepared=SimpleNamespace(evidence_windows=[]),
        artifacts={"insights_final": []},
        evidence_packs={
            "findings": [
                {"id": "failed-evidence", "text": "Unsupported source angle."},
                {"id": "approved-evidence", "text": "Supported replacement angle."},
            ]
        },
        doc_map={},
    )

    assert package["quarantined_evidence_ids"] == ["failed-evidence"]
    assert package["evidence_ids"] == ["approved-evidence"]
    assert "failed-evidence" not in json.dumps(package["relevant_evidence"])


def test_grounding_package_selects_retained_evidence_for_soft_copy_without_issue_ids() -> (
    None
):
    package = _build_grounding_package(
        target=RegenerationTarget(
            target_section="expert_comment",
            issues=[
                RegenerationIssue(
                    rule_id="public_editorial_quality.support",
                    affected_section="expert_comment",
                    message="Unsupported operational benefit.",
                    severity="error",
                )
            ],
        ),
        prepared=SimpleNamespace(evidence_windows=[]),
        artifacts={
            "expert_comment": "The retention signal supports a planning choice.",
            "editorial_plan": {"themes": [{"evidence_ids": ["finding-2"]}]},
            "insights_final": [{"evidence_id": "finding-1"}],
        },
        evidence_packs={
            "findings": {
                "findings": [
                    {"id": "finding-1", "text": "Retention improved in the cohort."},
                    {"id": "finding-2", "text": "Margin pressure remains visible."},
                ]
            }
        },
        doc_map={},
    )

    assert package["evidence_ids"] == ["finding-1", "finding-2"]


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


def test_soft_copy_claim_evidence_package_prefers_direct_retained_ids() -> None:
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("f2", "f1")),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs=_evidence_packs(),
        quarantined_evidence_ids=(),
    )

    assert package["evidence_ids"] == ["f2", "f1"]
    assert package["evidence_selection"]["strategy"] == "claim_evidence_ids"


def test_soft_copy_claim_evidence_package_resolves_direct_doc_map_section() -> None:
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("section-checkout",)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs=_evidence_packs(),
        doc_map={
            "sections": [
                {
                    "id": "section-checkout",
                    "title": "Checkout behavior",
                    "summary": "Checkout friction remains material.",
                    "pages": [3, 4],
                }
            ]
        },
        quarantined_evidence_ids=(),
    )

    assert package["evidence_ids"] == ["section-checkout"]
    assert package["relevant_evidence"] == [
        {
            "pack_name": "doc_map",
            "id": "section-checkout",
            "title": "Checkout behavior",
            "summary": "Checkout friction remains material.",
            "pages": [3, 4],
        }
    ]
    assert package["evidence_selection"]["strategy"] == "claim_evidence_ids"


def test_soft_copy_claim_evidence_package_skips_quarantined_doc_map_section() -> None:
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("section-checkout",)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs={},
        doc_map={
            "sections": [
                {
                    "id": "section-checkout",
                    "title": "Checkout behavior",
                    "summary": "Checkout friction remains material.",
                    "pages": [3, 4],
                }
            ]
        },
        quarantined_evidence_ids=("section-checkout",),
    )

    assert package["evidence_ids"] == []
    assert package["evidence_selection"]["strategy"] == "abstain"


def test_soft_copy_claim_evidence_hash_tracks_only_selected_canonical_content() -> None:
    inputs = {
        "claim": _soft_copy_claim(evidence_ids=("f1",)),
        "issue": RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        "artifacts": _current_artifacts(),
        "quarantined_evidence_ids": (),
    }
    original = _build_soft_copy_claim_evidence_package(
        **inputs,
        evidence_packs={
            "findings": [
                {"id": "f1", "text": "Selected evidence.", "pages": [1, 2]},
                {"id": "f2", "text": "Unselected evidence."},
            ]
        },
    )
    reordered = _build_soft_copy_claim_evidence_package(
        **inputs,
        evidence_packs={
            "findings": [
                {"text": "Unselected evidence.", "id": "f2"},
                {"pages": [2, 1], "text": "Selected evidence.", "id": "f1"},
            ]
        },
    )
    selected_changed = _build_soft_copy_claim_evidence_package(
        **inputs,
        evidence_packs={
            "findings": [
                {
                    "id": "f1",
                    "text": "Corrected selected evidence.",
                    "pages": [1, 2],
                },
                {"id": "f2", "text": "Unselected evidence."},
            ]
        },
    )
    unselected_changed = _build_soft_copy_claim_evidence_package(
        **inputs,
        evidence_packs={
            "findings": [
                {"id": "f1", "text": "Selected evidence.", "pages": [1, 2]},
                {"id": "f2", "text": "Changed but unselected evidence."},
            ]
        },
    )

    assert (
        original["evidence_selection"]["package_sha256"]
        == reordered["evidence_selection"]["package_sha256"]
    )
    assert (
        original["evidence_selection"]["package_sha256"]
        != selected_changed["evidence_selection"]["package_sha256"]
    )
    assert (
        original["evidence_selection"]["package_sha256"]
        == unselected_changed["evidence_selection"]["package_sha256"]
    )


def test_regeneration_state_restores_only_valid_private_evidence_selections() -> None:
    retained_selection = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("f1",)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs={"findings": [{"id": "f1", "text": "Evidence."}]},
        quarantined_evidence_ids=(),
    )["evidence_selection"]
    mismatched_hash = {**retained_selection, "package_sha256": "a" * 64}
    retained_key = f"expert_comment:{retained_selection['claim_id']}"
    linked_selection = {
        **retained_selection,
        "repaired_claim_id": "soft_copy:expert_comment:repaired",
    }
    state = _build_regeneration_state(
        safe_artifacts={
            **_current_artifacts(),
            "_repair_evidence_selection": {
                retained_key: linked_selection,
                f"stale:{retained_selection['claim_id']}": mismatched_hash,
                "bad": {"arbitrary": "data"},
            },
        },
        fallback_toc_bundle={
            "toc_entries": [],
            "toc_topics": [],
            "toc_topics_expanded": [],
        },
        source_status={"not_available": False, "reason": ""},
    )

    assert state.soft_copy_evidence_selections == {retained_key: linked_selection}


def test_soft_copy_claim_evidence_package_uses_parent_insight_before_fallback() -> None:
    artifacts = _current_artifacts()
    artifacts["insights_final"] = [
        {
            "id": "insight-margin",
            "text": "Margin pressure is material.",
            "evidence_id": "f2",
        }
    ]
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(source_spans=({"insight_id": "insight-margin"},)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=artifacts,
        evidence_packs=_evidence_packs(),
        quarantined_evidence_ids=(),
    )

    assert package["evidence_ids"] == ["f2"]
    assert package["evidence_selection"]["strategy"] == "parent_insight_or_theme"


def test_soft_copy_claim_evidence_package_uses_text_matched_parent_theme() -> None:
    artifacts = _current_artifacts()
    artifacts["editorial_plan"] = {
        "themes": [
            {"theme": "Retention performance", "evidence_ids": ["f1"]},
            {"theme": "Margin pressure", "evidence_ids": ["f2"]},
        ]
    }
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Margin pressure claim is unsupported.",
            severity="error",
        ),
        artifacts=artifacts,
        evidence_packs=_evidence_packs(),
        quarantined_evidence_ids=(),
        claim_text="Margin pressure affects planning.",
    )

    assert package["evidence_ids"] == ["f2"]
    assert package["evidence_selection"]["strategy"] == "parent_insight_or_theme"


def test_soft_copy_claim_evidence_package_excludes_quarantined_entries() -> None:
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(evidence_ids=("f2",)),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs=_evidence_packs(),
        quarantined_evidence_ids=("f2",),
    )

    assert package["evidence_ids"] == []
    assert package["evidence_selection"]["strategy"] == "abstain"


def test_soft_copy_claim_evidence_package_uses_only_bounded_lexical_fallback() -> None:
    evidence_packs = {
        "findings": {
            "findings": [
                {"id": f"relevant-{index}", "text": "Retention planning signal."}
                for index in range(6)
            ]
            + [{"id": "irrelevant", "text": "Unrelated commodity price."}]
        }
    }
    package = _build_soft_copy_claim_evidence_package(
        claim=_soft_copy_claim(),
        issue=RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Retention planning claim is unsupported.",
            severity="error",
        ),
        artifacts=_current_artifacts(),
        evidence_packs=evidence_packs,
        quarantined_evidence_ids=(),
    )

    assert package["evidence_ids"] == [
        "relevant-0",
        "relevant-1",
        "relevant-2",
        "relevant-3",
    ]
    assert package["evidence_selection"]["strategy"] == "lexical_fallback"


def test_soft_copy_claim_evidence_package_abstains_and_is_repeatable_without_support() -> (
    None
):
    inputs = {
        "claim": _soft_copy_claim(),
        "issue": RegenerationIssue(
            rule_id="grounding",
            affected_section="expert_comment",
            message="Bad claim",
            severity="error",
        ),
        "artifacts": _current_artifacts(),
        "evidence_packs": {"findings": [{"id": "f1", "text": "Different topic."}]},
        "quarantined_evidence_ids": (),
    }

    first = _build_soft_copy_claim_evidence_package(**inputs)
    second = _build_soft_copy_claim_evidence_package(**inputs)

    assert first["evidence_ids"] == []
    assert first["evidence_selection"]["strategy"] == "abstain"
    assert first == second
    assert (
        first["evidence_selection"]["package_sha256"]
        == second["evidence_selection"]["package_sha256"]
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
    def openai_chat_json(self, req, ctx):
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
        return super().openai_chat_json(req, ctx)


class _ClaimScopedExpertOpenAIClient(_FakeOpenAIClient):
    def openai_chat_json(self, req, ctx):
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
        return super().openai_chat_json(req, ctx)


class _FactualClaimScopedExpertOpenAIClient(_ClaimScopedExpertOpenAIClient):
    def openai_chat_json(self, req, ctx):
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
        return super().openai_chat_json(req, ctx)


class _ClaimScopedSoftCopyOpenAIClient(_ClaimScopedExpertOpenAIClient):
    def openai_chat_json(self, req, ctx):
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
        return super().openai_chat_json(req, ctx)


class _MultiClaimScopedExpertOpenAIClient(_FakeOpenAIClient):
    """Return a distinct replacement for each bounded claim repair request."""

    def openai_chat_json(self, req, ctx):
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
        return super().openai_chat_json(req, ctx)


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


def test_regenerate_artifacts_insights_bundle_uses_targeted_steps_and_preserves_untouched_sections(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="insights_bundle",
                        regenerate_steps=["insights_candidates", "insights_final"],
                        prompt_namespaces=[
                            "report_vs/artifacts/regenerate/insights_candidates",
                            "report_vs/artifacts/regenerate/insights_final",
                        ],
                        issues=[
                            RegenerationIssue(
                                rule_id="metrics",
                                affected_section="insights:insight-1",
                                message="[metrics] Unsupported insight value",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["insights_candidates", "insights_final"]
    prompts = response.updated_artifacts["_cache"]["prompts"]
    assert prompts["report_vs/artifacts/insights_final"] == {
        "prompt_content_hash": "c" * 64
    }
    assert (
        prompts["report_vs/artifacts/regenerate/insights_candidates"][
            "prompt_content_hash"
        ]
        == "c" * 64
    )
    assert prompts["report_vs/artifacts/regenerate/insights_final"][
        "execution_identity"
    ]
    assert len(response.updated_artifacts["insights_candidates"]) == 4
    assert len(response.updated_artifacts["insights_final"]) == 5
    assert (
        response.updated_artifacts["family_status"]["insights_bundle"]["status"]
        == "generated"
    )
    assert [call.path for call in response.updated_artifacts and []] == []
    assert response.artifacts_path == ""
    assert Path(response.candidate_artifacts_path).is_file()
    assert not (
        tmp_path / "out" / "report-1" / "report_analysis" / "artifacts.json"
    ).exists()

    rendered_paths = [call["path"] for call in prompt_client.render_calls]
    assert rendered_paths == [
        "report_vs/artifacts/regenerate/insights_candidates/system.yaml",
        "report_vs/artifacts/regenerate/insights_candidates/user.yaml",
        "report_vs/artifacts/regenerate/insights_final/system.yaml",
        "report_vs/artifacts/regenerate/insights_final/user.yaml",
    ]
    first_user_prompt = openai_client.calls[0].user_prompt
    assert "Unsupported insight value" in first_user_prompt
    assert "Evidence text" in first_user_prompt
    candidate_variables = prompt_client.render_calls[1]["variables"]
    assert json.loads(candidate_variables["editorial_plan_json"]) == {
        "report_thesis": "The report's retained evidence changes planning.",
        "themes": [
            {"theme": "Primary evidence", "priority": 1, "evidence_ids": ["f1"]},
            {"theme": "Margin evidence", "priority": 2, "evidence_ids": ["f2"]},
        ],
    }
    final_variables = prompt_client.render_calls[3]["variables"]
    assert final_variables["final_insight_target_count"] == 5


def test_final_insight_reuses_same_id_candidate_evidence_when_model_omits_it() -> None:
    final_insights = [
        {
            "id": "insight-email-automation",
            "text": "The repaired wording remains specific to automation.",
            "evidence_id": "",
            "evidence": "",
            "evidence_spans": [],
            "pages": [],
            "metric": dict(METRIC),
        }
    ]
    candidates = [
        {
            "id": "insight-email-automation",
            "text": "Candidate wording.",
            "evidence_id": "finding-5",
            "evidence": "Automated messages drove the reported result.",
            "evidence_spans": [
                {
                    "evidence_id": "finding-5",
                    "source_pack": "findings",
                    "page": 8,
                    "text": "Automated messages drove the reported result.",
                }
            ],
            "pages": [8],
            "metric": dict(METRIC),
        }
    ]

    restored = _restore_final_insight_evidence_bindings(
        final_insights=final_insights,
        candidate_insights=candidates,
        prior_final_insights=[],
    )

    assert restored[0]["text"] == (
        "The repaired wording remains specific to automation."
    )
    assert restored[0]["evidence_id"] == "finding-5"
    assert restored[0]["evidence"] == "Automated messages drove the reported result."
    assert restored[0]["pages"] == [8]


def test_regeneration_keeps_unreplaced_insight_evidence_records() -> None:
    current = [
        {"id": "insight-one", "text": "Existing evidence one.", "evidence_id": "f1"},
        {"id": "insight-two", "text": "Existing evidence two.", "evidence_id": "f2"},
    ]
    regenerated = [
        {"id": "insight-one", "text": "Repaired evidence one.", "evidence_id": "f1"},
        {
            "id": "new-unstable-id",
            "text": "Unrelated replacement.",
            "evidence_id": "f3",
        },
    ]

    merged = _merge_regenerated_insights_by_stable_id(
        current_insights=current,
        regenerated_insights=regenerated,
        append_new=True,
    )

    assert [item["id"] for item in merged] == [
        "insight-one",
        "insight-two",
        "new-unstable-id",
    ]
    assert merged[0]["text"] == "Repaired evidence one."
    assert merged[1]["evidence_id"] == "f2"


def test_regenerate_artifacts_dispatches_summary_via_target_section_registry(tmp_path):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="summary",
                        regenerate_steps=["summary"],
                        prompt_namespaces=["report_vs/artifacts/regenerate/wrong"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="executive_summary",
                                message="[grounding] Unsupported summary claim",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["summary"]
    assert response.prompt_namespaces == ["report_vs/artifacts/regenerate/summary"]
    assert [call["path"] for call in prompt_client.render_calls] == [
        "report_vs/artifacts/regenerate/summary/system.yaml",
        "report_vs/artifacts/regenerate/summary/user.yaml",
    ]


def test_regenerate_artifacts_refreshes_cover_semantics_from_retained_analysis(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="cover_semantics",
                        regenerate_steps=["cover_semantics"],
                        prompt_namespaces=["report_vs/artifacts/cover_semantics"],
                        issues=[],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["cover_semantics"]
    assert response.updated_artifacts["cover_semantics"]["selection_reason"] == (
        "A rising time series is the strongest visual story."
    )
    assert response.prompt_namespaces == ["report_vs/artifacts/cover_semantics"]


def test_regenerate_artifacts_expert_comment_uses_grounded_synthesis_context(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()
    current_artifacts["insights_final"][0]["so_what"] = (
        "The primary finding changes the operating tradeoff."
    )
    current_artifacts["insights_final"][1]["coverage_role"] = "counter_signal"
    evidence_packs = _evidence_packs()
    evidence_packs["limitations"] = {
        "limitations": [
            {
                "description": "The report does not compare segments.",
                "evidence_id": "f1",
            }
        ]
    }

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        prompt_namespaces=[
                            "report_vs/artifacts/regenerate/expert_comment"
                        ],
                        issues=[],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.prompt_namespaces == [
        "report_vs/artifacts/regenerate/expert_comment"
    ]
    variables = prompt_client.render_calls[0]["variables"]
    assert "summary_json" not in variables
    context = json.loads(variables["expert_synthesis_context_json"])
    assert [theme["theme"] for theme in context["themes"]] == [
        "Primary evidence",
        "Margin evidence",
    ]
    assert context["insight_implications"] == [
        {
            "evidence_id": "f1",
            "so_what": "The primary finding changes the operating tradeoff.",
        }
    ]
    assert context["limitations"] == [
        {"evidence_id": "f1", "text": "The report does not compare segments."}
    ]


def test_regenerate_artifacts_linkedin_post_receives_editorial_plan(tmp_path):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="linkedin_post",
                        regenerate_steps=["linkedin_post"],
                        prompt_namespaces=[
                            "report_vs/artifacts/regenerate/linkedin_post"
                        ],
                        issues=[],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.prompt_namespaces == [
        "report_vs/artifacts/regenerate/linkedin_post"
    ]
    assert json.loads(
        prompt_client.render_calls[0]["variables"]["editorial_plan_json"]
    ) == {
        "report_thesis": "The report's retained evidence changes planning.",
        "themes": [
            {"theme": "Primary evidence", "priority": 1, "evidence_ids": ["f1"]},
            {"theme": "Margin evidence", "priority": 2, "evidence_ids": ["f2"]},
        ],
    }


def test_regenerated_soft_copy_claim_gets_new_provenance_and_untouched_claim_is_retained(
    tmp_path,
) -> None:
    current_artifacts = _current_artifacts()
    retained_linkedin_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="linkedin_post",
        claim_id="soft_copy:linkedin_post:retained",
        text_hash=hashlib.sha256(b"Old linkedin").hexdigest(),
        classification="interpretive",
        evidence_ids=("f1",),
        source_spans=(),
        producing_prompt_identity={"namespace": "old/linkedin"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "linkedin_post"
    ] + soft_copy_claim_provenance_to_payload([retained_linkedin_claim])["claims"]

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    claims = response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    regenerated = next(
        item for item in claims if item["artifact_family"] == "expert_comment"
    )
    retained = next(
        item for item in claims if item["artifact_family"] == "linkedin_post"
    )
    assert regenerated["classification"] == "interpretive"
    assert regenerated["evidence_ids"] == ["f1", "f2"]
    assert regenerated["regeneration_attempt"] == 2
    assert regenerated["producing_prompt_identity"]["namespace"] == (
        "report_vs/artifacts/regenerate/expert_comment"
    )
    assert (
        retained
        == soft_copy_claim_provenance_to_payload([retained_linkedin_claim])["claims"][0]
    )


def test_regeneration_repairs_only_the_failed_expert_claim_and_retains_sibling_provenance(
    tmp_path,
) -> None:
    """Removing claim-scoped reconstruction makes this assertion fail."""
    current_artifacts = _current_artifacts()
    sentences = [
        "First supported sentence stays.",
        "Bad sentence needs repair.",
        "Third supported sentence stays.",
    ]
    current_artifacts["expert_comment"] = "  ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].append(
        {"id": "f3", "evidence": "Third supported evidence."}
    )
    current_artifacts["_repair_evidence_selection"] = {
        f"expert_comment:{original_claims[1].claim_id}": {
            "schema_version": "1.0",
            "claim_id": original_claims[1].claim_id,
            "strategy": "claim_evidence_ids",
            "direct_evidence_ids": ["f1"],
            "parent_evidence_ids": [],
            "quarantined_evidence_ids": [],
            "selected_evidence_ids": ["f1"],
            "package_sha256": "a" * 64,
        }
    }

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported middle sentence.",
                                severity="error",
                                evidence_ids=["f2"],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=_ClaimScopedExpertOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == (
        "First supported sentence stays.  Repaired middle claim.  "
        "Third supported sentence stays."
    )
    selection = response.updated_artifacts["_repair_evidence_selection"][
        f"expert_comment:{original_claims[1].claim_id}"
    ]
    assert selection["strategy"] == "claim_evidence_ids"
    assert selection["selected_evidence_ids"] == ["f2"]
    assert len(selection["package_sha256"]) == 64
    assert selection["package_sha256"] != "a" * 64
    claims = response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    by_id = {claim["claim_id"]: claim for claim in claims}
    assert (
        by_id[original_claims[0].claim_id]
        == soft_copy_claim_provenance_to_payload([original_claims[0]])["claims"][0]
    )
    assert (
        by_id[original_claims[2].claim_id]
        == soft_copy_claim_provenance_to_payload([original_claims[2]])["claims"][0]
    )
    repaired = next(
        claim
        for claim in claims
        if claim["text_hash"] == hashlib.sha256(b"Repaired middle claim.").hexdigest()
    )
    assert repaired["regeneration_attempt"] == 2
    assert repaired["producing_prompt_identity"]["namespace"] == (
        "report_vs/artifacts/regenerate/expert_comment"
    )


def test_claim_scoped_repair_bridges_quarantine_to_rewritten_factual_claim(
    tmp_path,
) -> None:
    """A rewritten claim must keep the exact selection that scoped its repair."""
    current_artifacts = _current_artifacts()
    original_text = "Original factual claim."
    sibling_text = "Unchanged sibling interpretation."
    original_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:original-factual",
        text_hash=hashlib.sha256(original_text.encode()).hexdigest(),
        classification="factual",
        evidence_ids=("f2",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    sibling_claim = SoftCopyClaimProvenance(
        schema_version="1.0",
        artifact_family="expert_comment",
        claim_id="soft_copy:expert_comment:unchanged-sibling",
        text_hash=hashlib.sha256(sibling_text.encode()).hexdigest(),
        classification="interpretive",
        evidence_ids=("f2",),
        source_spans=(),
        producing_prompt_identity={"namespace": "report_vs/artifacts/expert_comment"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    current_artifacts["expert_comment"] = f"{original_text} {sibling_text}"
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload([original_claim, sibling_claim])["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].extend(
        {"id": f"f{index}", "evidence": f"Supporting finding {index}."}
        for index in (3, 4, 5)
    )

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Original factual claim is unsupported.",
                                severity="error",
                                entity_id=original_claim.claim_id,
                                evidence_ids=["f2"],
                                excluded_evidence_ids=["f1"],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=_FactualClaimScopedExpertOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    repaired = next(
        claim
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["text_hash"] == hashlib.sha256(b"Repaired middle claim.").hexdigest()
    )
    selection = response.updated_artifacts["_repair_evidence_selection"][
        f"expert_comment:{original_claim.claim_id}"
    ]

    assert repaired["claim_id"] != original_claim.claim_id
    assert repaired["repaired_from_claim_id"] == original_claim.claim_id
    assert selection["repaired_claim_id"] == repaired["claim_id"]
    assert validate_regeneration_candidate(
        current_artifacts=current_artifacts,
        candidate_artifacts=response.updated_artifacts,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    ).passed

    quarantined_candidate = deepcopy(response.updated_artifacts)
    rewritten_claim = next(
        claim
        for claim in quarantined_candidate["soft_copy_claim_provenance"]["claims"]
        if claim["claim_id"] == repaired["claim_id"]
    )
    rewritten_claim["evidence_ids"] = ["f1"]
    rewritten_claim["source_spans"] = [{"evidence_id": "f1", "source_pack": "findings"}]

    result = validate_regeneration_candidate(
        current_artifacts=current_artifacts,
        candidate_artifacts=quarantined_candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any("quarantined" in issue.message for issue in result.issues)


def test_public_validator_to_plan_to_claim_repair_preserves_sibling_provenance(
    tmp_path,
) -> None:
    """Exercise retained claim ID propagation through the real deterministic path."""
    current_artifacts = _current_artifacts()
    sentences = [
        "First supported sibling.",
        "{{TODO}} failed middle claim.",
        "Last supported sibling.",
    ]
    current_artifacts["expert_comment"] = "  ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:validator-flow:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=({"page": index},),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].append(
        {"id": "f3", "evidence": "Third supported evidence."}
    )
    validation_issues = validation_issues_from_public_editorial_quality(
        evaluate_public_editorial_quality(
            report_id="validator-flow", artifacts=current_artifacts
        )
    )
    failed_issue = next(
        issue
        for issue in validation_issues
        if issue.entity_id == original_claims[1].claim_id
    )
    plan = _build_regeneration_plan(
        issues=[failed_issue], artifacts=current_artifacts, broad_retry_available=False
    )

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=plan,
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=_ClaimScopedExpertOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert failed_issue.entity_id == original_claims[1].claim_id
    assert plan.targets[0].issues[0].evidence_ids == ["f2"]
    assert response.updated_artifacts["expert_comment"] == (
        "First supported sibling.  Last supported sibling."
    )
    by_id = {
        claim["claim_id"]: claim
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    for claim in (original_claims[0], original_claims[2]):
        assert (
            by_id[claim.claim_id]
            == soft_copy_claim_provenance_to_payload([claim])["claims"][0]
        )
    assert original_claims[1].claim_id not in by_id


def test_ambiguous_soft_copy_issue_uses_existing_family_regeneration(tmp_path) -> None:
    current_artifacts = _current_artifacts()
    sentences = ["First sibling.", "Second ambiguous claim.", "Third ambiguous claim."]
    current_artifacts["expert_comment"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:ambiguous:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=("f2" if index > 1 else "f1",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    evidence_packs = _evidence_packs()
    openai_client = _ClaimScopedExpertOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported retained claim.",
                                severity="error",
                                evidence_ids=["f2"],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == "Repaired middle claim."
    assert len(openai_client.calls) == 1


def test_regeneration_abstains_only_an_unsupported_expert_claim_without_model_call(
    tmp_path,
) -> None:
    """The unsupported claim is removed while valid prose and provenance remain."""
    current_artifacts = _current_artifacts()
    sentences = [
        "First supported sentence.",
        "Unsupported sentence.",
        "Last supported sentence.",
    ]
    current_artifacts["expert_comment"] = " ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:unsupported:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="factual",
            evidence_ids=(evidence_id,),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, (sentence, evidence_id) in enumerate(
            zip(sentences, ("f1", "missing", "f2"), strict=True), start=1
        )
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    openai_client = _ClaimScopedExpertOpenAIClient()
    evidence_packs = _evidence_packs()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported sentence.",
                                severity="error",
                                evidence_ids=["missing"],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == (
        "First supported sentence. Last supported sentence."
    )
    assert openai_client.calls == []
    claim_ids = {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    assert original_claims[0].claim_id in claim_ids
    assert original_claims[1].claim_id not in claim_ids
    assert original_claims[2].claim_id in claim_ids


def test_regeneration_repairs_multiple_exact_claim_ids_without_churning_siblings(
    tmp_path,
) -> None:
    """Two precise failures are repaired independently and reconstructed in place."""
    current_artifacts = _current_artifacts()
    sentences = [
        "First sibling remains byte-identical.",
        "Bad second claim.",
        "Bad third claim.",
        "Last sibling remains byte-identical.",
    ]
    original_text = "  ".join(sentences)
    current_artifacts["expert_comment"] = original_text
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:multi:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].extend(
        [
            {"id": "f3", "evidence": "Third supported evidence."},
            {"id": "f4", "evidence": "Fourth supported evidence."},
        ]
    )
    openai_client = _MultiClaimScopedExpertOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported second claim.",
                                severity="error",
                                entity_id=original_claims[1].claim_id,
                                evidence_ids=["f2"],
                            ),
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported third claim.",
                                severity="error",
                                entity_id=original_claims[2].claim_id,
                                evidence_ids=["f3"],
                            ),
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == (
        "First sibling remains byte-identical.  Repaired second claim.  "
        "Repaired third claim.  Last sibling remains byte-identical."
    )
    assert len(openai_client.calls) == 2
    by_id = {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == "expert_comment"
    }
    assert original_claims[0].claim_id in by_id
    assert original_claims[3].claim_id in by_id
    assert original_claims[1].claim_id not in by_id
    assert original_claims[2].claim_id not in by_id
    repaired_claims = [
        SoftCopyClaimProvenance(
            schema_version=item["schema_version"],
            artifact_family=item["artifact_family"],
            claim_id=item["claim_id"],
            text_hash=item["text_hash"],
            classification=item["classification"],
            evidence_ids=tuple(item["evidence_ids"]),
            source_spans=tuple(item["source_spans"]),
            producing_prompt_identity=item["producing_prompt_identity"],
            generation_attempt=item["generation_attempt"],
            regeneration_attempt=item["regeneration_attempt"],
        )
        for item in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
        if item["artifact_family"] == "expert_comment"
    ]
    assert retained_soft_copy_claims_cover_text(
        text=response.updated_artifacts["expert_comment"], claims=repaired_claims
    )


def test_multi_claim_regeneration_repairs_supported_claim_and_abstains_unsupported_one(
    tmp_path,
) -> None:
    sentences = [
        "First sibling.",
        "Bad second claim.",
        "Bad third claim.",
        "Last sibling.",
    ]
    current_artifacts = _current_artifacts()
    current_artifacts["expert_comment"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:mixed:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    evidence_packs = _evidence_packs()
    openai_client = _MultiClaimScopedExpertOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported second claim.",
                                severity="error",
                                entity_id=claims[1].claim_id,
                                evidence_ids=["f2"],
                            ),
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported third claim.",
                                severity="error",
                                entity_id=claims[2].claim_id,
                                evidence_ids=["f3"],
                            ),
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["expert_comment"] == (
        "First sibling. Repaired second claim. Last sibling."
    )
    assert len(openai_client.calls) == 1
    provenance_ids = {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    assert claims[0].claim_id in provenance_ids
    assert claims[3].claim_id in provenance_ids
    assert claims[2].claim_id not in provenance_ids


def test_multi_claim_repair_keeps_quarantine_scoped_to_its_failed_claim(
    tmp_path,
) -> None:
    current_artifacts = _current_artifacts()
    sentences = ["Bad first claim.", "Bad second claim."]
    current_artifacts["expert_comment"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:quarantine:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    evidence_packs = _evidence_packs()

    prompt_client = _FakePromptClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=2,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="expert_comment",
                        regenerate_steps=["expert_comment"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported first claim.",
                                severity="error",
                                entity_id=claims[0].claim_id,
                                evidence_ids=["f1"],
                                excluded_evidence_ids=["f1"],
                            ),
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="expert_comment",
                                message="Unsupported second claim.",
                                severity="error",
                                entity_id=claims[1].claim_id,
                                evidence_ids=["f2"],
                            ),
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=False,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
        ),
        openai_client=_MultiClaimScopedExpertOpenAIClient(),
        prompt_client=prompt_client,
    )

    selections = response.updated_artifacts["_repair_evidence_selection"]
    first = selections[f"expert_comment:{claims[0].claim_id}"]
    second = selections[f"expert_comment:{claims[1].claim_id}"]
    assert first["selected_evidence_ids"] == []
    assert first["quarantined_evidence_ids"] == ["f1"]
    assert second["selected_evidence_ids"] == ["f2"]
    assert second["quarantined_evidence_ids"] == []
    scoped_prompt = next(
        call
        for call in prompt_client.render_calls
        if call["path"] == "report_vs/artifacts/regenerate/expert_comment/user.yaml"
    )
    assert (
        json.loads(scoped_prompt["variables"]["grounding_package_json"])[
            "quarantined_evidence_ids"
        ]
        == []
    )
    assert response.updated_artifacts["expert_comment"] == "Repaired second claim."


def test_sequential_claim_repairs_preserve_prior_selection_provenance(tmp_path) -> None:
    current_artifacts = _current_artifacts()
    sentences = ["First bad claim.", "Second bad claim."]
    current_artifacts["expert_comment"] = " ".join(sentences)
    claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="expert_comment",
            claim_id=f"soft_copy:expert_comment:sequential:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={
                "namespace": "report_vs/artifacts/expert_comment"
            },
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + soft_copy_claim_provenance_to_payload(claims)["claims"]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].append(
        {"id": "f3", "evidence": "Third repair evidence."}
    )
    openai_client = _MultiClaimScopedExpertOpenAIClient()

    def repair(artifacts: dict, claim: SoftCopyClaimProvenance, attempt: int):
        return regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=attempt,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="expert_comment",
                            regenerate_steps=["expert_comment"],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="expert_comment",
                                    message="Unsupported claim.",
                                    severity="error",
                                    entity_id=claim.claim_id,
                                    evidence_ids=list(claim.evidence_ids),
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=False,
                ),
                current_artifacts=artifacts,
                doc_map=evidence_packs["doc_map"],
                evidence_packs=evidence_packs,
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=artifacts["source_status"],
                categories=["Category"],
            ),
            openai_client=openai_client,
            prompt_client=_FakePromptClient(),
        )

    first = repair(current_artifacts, claims[0], 1)
    first_selection = first.updated_artifacts["_repair_evidence_selection"][
        f"expert_comment:{claims[0].claim_id}"
    ]
    second = repair(first.updated_artifacts, claims[1], 2)

    selections = second.updated_artifacts["_repair_evidence_selection"]
    assert selections[f"expert_comment:{claims[0].claim_id}"] == first_selection
    assert selections[f"expert_comment:{claims[1].claim_id}"][
        "selected_evidence_ids"
    ] == ["f2"]


@pytest.mark.parametrize(
    ("family", "section", "expected", "field"),
    [
        (
            "linkedin_post",
            "linkedin_post",
            (
                "First linkedin_post claim. Repaired LinkedIn claim. "
                "Last linkedin_post claim."
            ),
            None,
        ),
        (
            "summary",
            "summary.executive_summary",
            "First summary claim. Repaired summary claim. Last summary claim.",
            "executive_summary",
        ),
    ],
)
def test_regeneration_claim_scope_preserves_unrelated_soft_copy_on_repeat(
    tmp_path, family: str, section: str, expected: str, field: str | None
) -> None:
    """A repeated isolated failure must not churn sibling copy or its provenance."""
    current_artifacts = _current_artifacts()
    sentences = [
        f"First {family} claim.",
        f"Bad {family} claim.",
        f"Last {family} claim.",
    ]
    if field is None:
        current_artifacts[family] = " ".join(sentences)
    else:
        current_artifacts["summary"][field] = " ".join(sentences)
    original_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family=family,
            claim_id=f"soft_copy:{family}:repeat:{index}",
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="interpretive",
            evidence_ids=(f"f{index}",),
            source_spans=(),
            producing_prompt_identity={"namespace": f"report_vs/artifacts/{family}"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for index, sentence in enumerate(sentences, start=1)
    ]
    current_artifacts["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current_artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != family
    ] + (
        [
            claim
            for claim in _current_artifacts()["soft_copy_claim_provenance"]["claims"]
            if family == "summary"
            and claim["artifact_family"] == "summary"
            and claim["text_hash"] == hashlib.sha256(b"Old TLDR.").hexdigest()
        ]
        + soft_copy_claim_provenance_to_payload(original_claims)["claims"]
    )
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].append(
        {"id": "f3", "evidence": "Last supported evidence."}
    )

    def regenerate(current: dict, attempt_index: int):
        return regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=attempt_index,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section=family,
                            regenerate_steps=[family],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section=section,
                                    message="Unsupported middle claim.",
                                    severity="error",
                                    evidence_ids=["f2"],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=False,
                ),
                current_artifacts=current,
                doc_map=evidence_packs["doc_map"],
                evidence_packs=evidence_packs,
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=current["source_status"],
                categories=["Category"],
            ),
            openai_client=_ClaimScopedSoftCopyOpenAIClient(),
            prompt_client=_FakePromptClient(),
        )

    first = regenerate(current_artifacts, 1)
    second = regenerate(first.updated_artifacts, 2)
    value = (
        second.updated_artifacts[family]
        if field is None
        else second.updated_artifacts["summary"][field]
    )
    assert value == expected
    claims = {
        claim["claim_id"]: claim
        for claim in second.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    for claim in (original_claims[0], original_claims[2]):
        assert (
            claims[claim.claim_id]
            == soft_copy_claim_provenance_to_payload([claim])["claims"][0]
        )
    first_claims = {
        claim["claim_id"]: claim
        for claim in first.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    repaired = next(
        claim
        for claim in first_claims.values()
        if claim.get("repaired_from_claim_id") == original_claims[1].claim_id
    )
    selection = first.updated_artifacts["_repair_evidence_selection"][
        f"{family}:{original_claims[1].claim_id}"
    ]
    assert selection["repaired_claim_id"] == repaired["claim_id"]


def test_regenerate_artifacts_summary_only_keeps_other_sections_unchanged(tmp_path):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="summary",
                        regenerate_steps=["summary"],
                        prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
                        issues=[
                            RegenerationIssue(
                                rule_id="grounding",
                                affected_section="executive_summary",
                                message="[grounding] Unsupported summary claim",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["summary"]
    assert response.updated_artifacts["summary"]["tldr"] == "Repaired TLDR."
    assert (
        response.updated_artifacts["summary"]["card_tldr_compact"] == "Repaired TLDR."
    )
    assert (
        response.updated_artifacts["insights_final"][0]["text"] == "Old final insight"
    )
    assert response.updated_artifacts["quotes_final"][0]["text"] == "Old quote"


def test_regeneration_repairs_a_source_proven_lost_quarterly_comparison(tmp_path):
    source = "Share fell from 43% in Q1 2025 to 41% in Q2 2025."
    current_artifacts = _current_artifacts()
    current_artifacts["summary"].update(
        {
            "tldr": "Share fell from 43% in 2025 to 41% in 2025.",
            "executive_summary": "Share fell from 43% in 2025 to 41% in 2025.",
            "claim_evidence_map": [
                {
                    "claim": "Share fell from 43% in 2025 to 41% in 2025.",
                    "evidence_id": "f1",
                    "evidence": source,
                    "pages": [1],
                }
            ],
        }
    )
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"][0]["evidence"] = source

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="activate-2026",
            report_name="Activate 2026",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="summary",
                        regenerate_steps=["summary"],
                        prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
                        issues=[
                            RegenerationIssue(
                                rule_id="public_editorial_quality.temporal_integrity",
                                affected_section="summary.tldr",
                                message="lost distinct source-proven comparative temporal qualifiers",
                                severity="error",
                                evidence_ids=["f1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=_TemporalSummaryOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    assert response.regenerated_sections == ["summary"]
    assert response.updated_artifacts["summary"]["tldr"] == source
    assert not any(
        issue.rule_id == "public_editorial_quality.temporal_integrity"
        for issue in evaluate_public_editorial_quality(
            report_id="activate-2026", artifacts=response.updated_artifacts
        ).issues
    )


def test_regenerate_artifacts_applies_family_policy_to_unsupported_quotes(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    evidence_packs = _evidence_packs()
    evidence_packs["quote_candidates"] = {"quote_candidates": []}
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="quotes",
                        regenerate_steps=["quotes"],
                        prompt_namespaces=["report_vs/artifacts/regenerate/quotes"],
                        issues=[
                            RegenerationIssue(
                                rule_id="quotes",
                                affected_section="quotes:1",
                                message="[quotes] Quote not verbatim",
                                severity="error",
                                evidence_ids=["sec-1"],
                                pages=[1],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=_current_artifacts(),
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=_current_artifacts()["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["quotes"]
    assert response.updated_artifacts["quotes_final"] == []
    assert (
        response.updated_artifacts["family_status"]["quotes"]["status"] == "abstained"
    )
    assert (
        response.updated_artifacts["family_status"]["quotes"]["reason"]
        == "quotes_missing_verbatim_source"
    )


def test_regenerate_artifacts_topics_rebuilds_topic_briefs_without_model_calls(
    tmp_path,
):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()
    current_artifacts["toc_topics"] = [
        "Media brand ad equity",
        "Sentiments on generative AI",
    ]
    current_artifacts["toc_topics_expanded"] = [
        {
            "topic": "Media brand ad equity",
            "summary": "Wrong summary",
            "key_points": [],
            "section_id": "section-4",
            "section_title": "Sentiments on GenAI: How do APAC consumers perceive AI?",
            "pages": [25],
        },
        {
            "topic": "Sentiments on generative AI",
            "summary": "Wrong summary",
            "key_points": [],
            "section_id": "section-5",
            "section_title": "Implications for marketers",
            "pages": [27],
        },
    ]
    evidence_packs = _evidence_packs()
    evidence_packs["doc_map"] = {
        "doc_id": "doc-1",
        "title": "Media Reactions",
        "sections": [
            {
                "id": "section-3",
                "title": "Media brands: How do brands interact with people?",
                "summary": "Media-brand Ad Equity rankings with Netflix and OTT platforms leading.",
                "key_points": [
                    "Netflix is the #1 media brand for Ad Equity.",
                    "OTT platforms dominate the rankings.",
                ],
                "pages": [17, 18],
            },
            {
                "id": "section-4",
                "title": "Sentiments on GenAI: How do APAC consumers perceive AI?",
                "summary": "Consumer and marketer attitudes to generative AI in advertising.",
                "key_points": [
                    "Consumers worry about fake content.",
                    "Marketers use generative AI for creativity and efficiency.",
                ],
                "pages": [25],
            },
            {
                "id": "section-5",
                "title": "Implications for marketers",
                "summary": "Budget priorities and investment plans for marketers.",
                "key_points": [
                    "Online video and streaming remain top priorities.",
                ],
                "pages": [27],
            },
        ],
    }
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="topics",
                        regenerate_steps=[
                            "toc_entries",
                            "toc_topics",
                            "toc_topics_expanded",
                        ],
                        prompt_namespaces=[],
                        issues=[
                            RegenerationIssue(
                                rule_id="toc_integrity",
                                affected_section="toc_entries:section-3",
                                message="[toc_integrity] TOC coverage is missing section 'Media brands: How do brands interact with people?'.",
                                severity="error",
                                repair_target="topics",
                                entity_id="section-3",
                                evidence_ids=["section-4"],
                                pages=[25],
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == [
        "toc_entries",
        "toc_topics",
        "toc_topics_expanded",
    ]
    assert response.updated_artifacts["toc_entries"][0]["section_id"] == "section-3"
    assert (
        response.updated_artifacts["toc_entries"][0]["display_title"] == "Media brands"
    )
    assert (
        response.updated_artifacts["toc_topics_expanded"][0]["section_id"]
        == "section-3"
    )
    assert (
        response.updated_artifacts["toc_topics_expanded"][0]["section_title"]
        == "Media brands: How do brands interact with people?"
    )
    assert (
        response.updated_artifacts["toc_topics_expanded"][1]["section_title"]
        == "Sentiments on GenAI: How do APAC consumers perceive AI?"
    )


def test_regenerate_artifacts_rebuilds_only_key_figures_without_model_calls(tmp_path):
    prompt_client = _FakePromptClient()
    openai_client = _FakeOpenAIClient()
    current_artifacts = _current_artifacts()
    current_artifacts["insights_final"][0].update(
        {
            "text": "Retail-media teams are using AI in campaign workflows.",
            "evidence": "In 2026, 75% of Europe retail-media teams use AI in campaign workflows.",
            "metric": {
                **METRIC,
                "label": "Retail-media teams using AI in campaign workflows",
                "value": "75%",
                "timeframe": "2026",
                "geography": "Europe",
                "segment": "retail-media teams",
                "confidence": "high",
            },
        }
    )
    current_artifacts["key_figures"] = [
        {
            "figure_id": "bad-figure",
            "label": "Retail-media teams using AI in campaign workflows",
            "figure": "70%",
            "evidence_id": "f1",
        }
    ]
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"][0]["evidence"] = current_artifacts[
        "insights_final"
    ][0]["evidence"]

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[
                    RegenerationTarget(
                        target_section="key_figures",
                        regenerate_steps=["key_figures"],
                        prompt_namespaces=[],
                        issues=[
                            RegenerationIssue(
                                rule_id="public_editorial_quality.metric_label_relationship",
                                affected_section="key_figures:0.figure",
                                message="The selected figure conflicts with its evidence.",
                                severity="error",
                                evidence_ids=["f1"],
                                repair_target="key_figures",
                            )
                        ],
                    )
                ],
                unmappable_issues=[],
                broad_retry_allowed=True,
            ),
            current_artifacts=current_artifacts,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current_artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=prompt_client,
    )

    assert response.regenerated_sections == ["key_figures"]
    assert response.updated_artifacts["key_figures"][0]["figure"] == "75%"
    assert response.updated_artifacts["summary"]["tldr"] == "Old TLDR."
    assert response.updated_artifacts["summary"]["executive_summary"] == "Old summary"
    assert [item["text"] for item in response.updated_artifacts["insights_final"]] == [
        item["text"] for item in current_artifacts["insights_final"]
    ]
    assert [item["text"] for item in response.updated_artifacts["quotes_final"]] == [
        "Old quote"
    ]
    assert (
        response.updated_artifacts["expert_comment"]
        == current_artifacts["expert_comment"]
    )
    assert (
        response.updated_artifacts["linkedin_post"]
        == current_artifacts["linkedin_post"]
    )
    assert openai_client.calls == []
    assert prompt_client.render_calls == []
    assert openai_client.calls == []
    assert prompt_client.render_calls == []


def test_regenerate_artifacts_propagates_retryable_app_error(
    tmp_path, assert_app_error
):
    class _RetryingOpenAI(_FakeOpenAIClient):
        def openai_chat_json(self, req, ctx):
            del req, ctx
            raise AppError(
                code="openai_chat_failed",
                message="retry later",
                retryable=True,
            )

    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="summary",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_RetryingOpenAI(),
            prompt_client=_FakePromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="openai_chat_failed",
        retryable=True,
        severity="error",
    )


def test_regenerate_artifacts_propagates_non_retryable_prompt_error(
    tmp_path,
    assert_app_error,
):
    class _FailingPromptClient(_FakePromptClient):
        def load_prompt_set(self, req, ctx):
            del req, ctx
            raise AppError(
                code="prompt_not_found",
                message="missing prompt",
                retryable=False,
            )

    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="summary",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FailingPromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="prompt_not_found",
        retryable=False,
        severity="error",
    )


def test_regenerate_artifacts_rejects_unknown_target_section(
    tmp_path,
    assert_app_error,
):
    with pytest.raises(AppError) as exc_info:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[
                        RegenerationTarget(
                            target_section="unsupported_section",
                            regenerate_steps=["summary"],
                            prompt_namespaces=[
                                "report_vs/artifacts/regenerate/summary"
                            ],
                            issues=[
                                RegenerationIssue(
                                    rule_id="grounding",
                                    affected_section="executive_summary",
                                    message="[grounding] Unsupported summary claim",
                                    severity="error",
                                    evidence_ids=["f1"],
                                    pages=[1],
                                )
                            ],
                        )
                    ],
                    unmappable_issues=[],
                    broad_retry_allowed=True,
                ),
                current_artifacts=_current_artifacts(),
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=_current_artifacts()["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FakePromptClient(),
        )

    assert_app_error(
        exc_info.value,
        code="artifact_regeneration_target_unsupported",
        retryable=False,
        severity="error",
    )
