# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_identity_and_failures.py"
)

from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIResponseResult
from src.contracts.regeneration import (
    ArtifactRegenerationRequest,
    FailureFingerprint,
    RegenerationIssue,
    RegenerationPlan,
    RegenerationTarget,
    RepairDelta,
    repair_strategy_fingerprint,
)
from src.contracts.validation import ValidationIssue
from src.generators.report_regeneration_generator import regenerate_artifacts
from src.orchestrators._report_analysis_orchestrator.validation import (
    _preflight_empty_grounding_strategies,
)
from src.utils.errors import AppError
from tests.test_report_regeneration_generator import (
    METRIC,
    _build_regeneration_plan,
    _ctx,
    _current_artifacts,
    _evidence_packs,
    _FakeOpenAIClient,
    _FakePromptClient,
    _settings,
)

from ._shared import (
    _source_backed_artifacts,
)


class _NoModelCallsAllowed:
    """Fail the test the moment a repair attempts a model call."""

    def __init__(self) -> None:
        self.calls: list = []

    def openai_chat_json(self, req, ctx):
        self.calls.append(req)
        raise AssertionError("Deterministic repair must not call the model")

    def openai_chat_json_with_images(self, req, ctx):
        self.calls.append(req)
        raise AssertionError("Deterministic repair must not call the model")

    def openai_respond(self, req, ctx):
        self.calls.append(req)
        raise AssertionError("Deterministic repair must not call the model")

    def openai_respond_with_vector_store(self, req, ctx):
        self.calls.append(req)
        raise AssertionError("Deterministic repair must not call the model")


def _identity_plan() -> RegenerationPlan:
    return RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="report_identity",
                regenerate_steps=[],
                prompt_namespaces=[],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="metadata.title",
                        message=(
                            "[factual_claim|unsupported_factual_claim] The summary "
                            "title is not supported by retained evidence."
                        ),
                        severity="error",
                    )
                ],
                repair_action="COPY_CANONICAL_SOURCE_VALUE",
                repair_strategy="canonical_identity",
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )


def _quotes_plan() -> RegenerationPlan:
    return RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="quotes",
                regenerate_steps=["quotes"],
                prompt_namespaces=["report_vs/artifacts/regenerate/quotes"],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="quotes:q1",
                        message=(
                            "[factual_claim|misattributed_quote] Quote text is not "
                            "verbatim: A drifted paraphrase of the source."
                        ),
                        severity="error",
                        evidence_ids=["q1"],
                    )
                ],
                repair_action="COPY_CANONICAL_SOURCE_VALUE",
                repair_strategy="canonical_quote_restore",
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
