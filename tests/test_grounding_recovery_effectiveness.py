"""Deterministic recovery and fallback-boundary regressions.

These tests exercise the production grounding orchestration with injected
provider responses.  They deliberately do not replace the coverage validator;
the injected responses must pass the same validator used by the workflow.
"""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.protected_facts import PROTECTED_FACT_DIMENSIONS
from src.generators.claim_validation_generator import (
    retained_claim_semantic_inputs,
    validate_retained_claims,
)
from src.generators.validation.grounding import (
    _validate_grounding_check_coverage,
    grounding_payload,
    run_grounding_check,
)
from src.utils.errors import AppError
from tests._test_validation_generator._shared import (
    FakePromptClient,
    _ctx,
    _settings,
)
from tests.test_retained_claim_grounding import _retained_request


def _claim_request(count: int = 5):
    labels = ("alpha", "bravo", "charlie", "delta", "echo")[:count]
    claims = [
        f"The source describes payment operations from the {label} perspective."
        for label in labels
    ]
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": f"finding-{index}",
                    "text": f"The source discusses the {label} perspective.",
                    "evidence": (
                        "The source discusses payment operations from the "
                        f"{label} perspective."
                    ),
                }
                for index, label in enumerate(labels)
            ]
        }
    }
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": f"claim-{index}",
                    "claim": claim,
                    "evidence_id": f"finding-{index}",
                }
                for index, claim in enumerate(claims)
            ]
        }
    }
    request = replace(
        _retained_request(),
        report_id=f"grounding-recovery-{count}",
        source_id="source-grounding-recovery",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
    )
    package = validate_retained_claims(
        artifacts,
        evidence_packs,
        source_identity=request.source_id,
    )
    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity=request.source_id,
    )
    payload = grounding_payload(
        request,
        artifacts,
        retained_claim_inputs=semantic_inputs,
    )
    return request, package, semantic_inputs, payload


def _check(item_id: str, text: str) -> dict[str, object]:
    return {
        "item_id": item_id,
        "section": "summary.claim_evidence_map",
        "text": text,
        "classification": "factual_claim",
        "entailment_outcome": "entailed",
        "proposition_status": "compatible",
        "protected_facts": {
            dimension: {
                "claim_value": None,
                "evidence_value": None,
                "status": "unknown",
            }
            for dimension in PROTECTED_FACT_DIMENSIONS
        },
        "reason": "The linked source evidence supports the retained claim.",
    }


class _SubdivisionProvider:
    def __init__(self, entries: list[dict[str, object]], *, fail_split: bool):
        self.entries = entries
        self.fail_split = fail_split
        self.calls: list[tuple[str, str]] = []

    def openai_chat_json(self, request, ctx):
        task_id = str(ctx.task_id)
        self.calls.append((task_id, str(request.stage)))
        if ":batch:01_split1_split1:" in task_id:
            selected = self.entries[:1]
        elif ":batch:01_split1_split2:" in task_id:
            # Deliberately return the first claim for the second leaf.  The
            # leaf cannot be split further, so the parent must fail closed.
            selected = self.entries[:1]
        elif ":batch:01_split1:" in task_id:
            selected = self.entries[:2]
            if self.fail_split:
                selected = selected[:1]
        elif ":batch:01_split2:" in task_id:
            selected = self.entries[2:4]
        elif ":batch:01:" in task_id:
            # The full four-claim batch omits one claim for every bounded
            # provider attempt, forcing the existing subdivision path.
            selected = self.entries[:3]
        elif ":batch:02:" in task_id:
            selected = self.entries[4:]
        else:
            raise AssertionError(f"unexpected grounding task: {task_id}")
        response = {
            "unsupported": [],
            "checks": [_check(entry["item_id"], entry["text"]) for entry in selected],
        }
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(response),
            parsed_json=response,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=request.model,
        )


class _RecursiveSubdivisionProvider(_SubdivisionProvider):
    def openai_chat_json(self, request, ctx):
        task_id = str(ctx.task_id)
        self.calls.append((task_id, str(request.stage)))
        if ":batch:01_split1_split1:" in task_id:
            selected = self.entries[:1]
        elif ":batch:01_split1_split2:" in task_id:
            selected = self.entries[1:2]
        elif ":batch:01_split1:" in task_id:
            selected = self.entries[:1]
        elif ":batch:01_split2:" in task_id:
            selected = self.entries[2:4]
        elif ":batch:01:" in task_id:
            selected = self.entries[:3]
        elif ":batch:02:" in task_id:
            selected = self.entries[4:]
        else:
            raise AssertionError(f"unexpected grounding task: {task_id}")
        response = {
            "unsupported": [],
            "checks": [_check(entry["item_id"], entry["text"]) for entry in selected],
        }
        return OpenAIResponseResult(
            schema_version="1.0",
            text=json.dumps(response),
            parsed_json=response,
            input_tokens=0,
            output_tokens=0,
            tool_calls=0,
            model=request.model,
        )


def _run_with_provider(tmp_path, provider: _SubdivisionProvider):
    request, package, semantic_inputs, payload = _claim_request()
    entries = payload["retained_claims_to_ground"]
    assert isinstance(entries, list)
    provider.entries = entries
    settings = _settings(tmp_path)
    settings = replace(
        settings,
        validation_grounding_global_max_in_flight=1,
        validation_grounding_global_min_interval_ms=0,
    )
    captured_packages = []
    issues = run_grounding_check(
        request=request,
        settings=settings,
        grounding_use_vector_store=False,
        evidence_texts=["General source evidence."],
        evidence_windows=[],
        prompt_client=FakePromptClient(),
        openai_client=provider,
        ctx=_ctx(),
        source_id=request.source_id,
        prompt_family_reuse_reader=lambda *_args: SimpleNamespace(
            reusable=False,
            output_payload=None,
            reason="test",
        ),
        prompt_family_materializer=lambda *_args: None,
        retained_claim_package=package,
        retained_claim_inputs=semantic_inputs,
        retained_claim_validation_sink=captured_packages.append,
    )
    return issues, captured_packages


def test_grounding_subdivision_recovers_a_missing_claim_without_relaxing_coverage(
    tmp_path,
):
    provider = _SubdivisionProvider([], fail_split=False)

    issues, captured_packages = _run_with_provider(tmp_path, provider)

    assert issues == []
    assert captured_packages
    assert sum(":batch:01:" in task_id for task_id, _stage in provider.calls) == 3
    assert (
        sum(":batch:01_split1:" in task_id for task_id, _stage in provider.calls)
        == 1
    )
    assert (
        sum(":batch:01_split2:" in task_id for task_id, _stage in provider.calls)
        == 1
    )
    assert sum(":batch:02:" in task_id for task_id, _stage in provider.calls) == 1


def test_grounding_subdivision_fails_closed_and_does_not_promote_siblings(tmp_path):
    provider = _SubdivisionProvider([], fail_split=True)

    issues, captured_packages = _run_with_provider(tmp_path, provider)

    assert len(issues) == 1
    assert issues[0].rule_id == "grounding"
    assert "grounding_claim_check_coverage_invalid" in issues[0].message
    assert captured_packages == []
    assert not any(":batch:02:" in task_id for task_id, _stage in provider.calls)


def test_grounding_subdivision_recurses_for_complex_coverage_failure(tmp_path):
    provider = _RecursiveSubdivisionProvider([], fail_split=False)

    issues, captured_packages = _run_with_provider(tmp_path, provider)

    assert issues == []
    assert captured_packages
    assert any(
        ":batch:01_split1_split1:" in task_id
        for task_id, _stage in provider.calls
    )
    assert any(
        ":batch:01_split1_split2:" in task_id
        for task_id, _stage in provider.calls
    )


def test_grounding_coverage_reports_invalid_retained_classification():
    _request, _package, semantic_inputs, payload = _claim_request(1)
    claim = semantic_inputs[0].candidate
    item_id = payload["retained_claims_to_ground"][0]["item_id"]
    with pytest.raises(AppError) as exc_info:
        _validate_grounding_check_coverage(
            {
                "checks": [
                    {
                        **_check(item_id, claim.text),
                        "classification": "analyst_interpretation",
                    }
                ],
                "unsupported": [],
            },
            semantic_inputs,
            {claim.claim_id: item_id},
        )

    assert exc_info.value.code == "grounding_claim_check_coverage_invalid"
    assert exc_info.value.context["missing_claim_ids"] == [item_id]
