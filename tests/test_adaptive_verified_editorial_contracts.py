from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.contracts.run_context import RunContext
from src.generators._artifact_generator.generation import (
    _classify_verified_semantic_recovery,
    generate_artifacts,
)
from src.generators._artifact_generator.storage import (
    build_executive_advisory_artifacts,
)
from src.generators.artifact_normalization import (
    build_expert_synthesis_context,
    validate_substantive_editorial_theme_coverage,
    validate_verified_editorial_plan,
    validate_verified_editorial_plan_revision,
)
from src.generators.report_generation_shared import (
    base_payload,
    merge_artifacts_into_payload,
)
from src.generators.validation.regeneration_candidate import (
    _verified_editorial_obligation_issues,
)
from src.orchestrators._report_analysis_orchestrator.payload import (
    _ensure_report_payload_complete,
)
from src.services._render_service.normalization import _coerce_limitation_items
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from tests._test_artifact_generator._shared import (
    CapturingPromptClient,
    FakeAnalysisStore,
    FakeOpenAI,
    _ctx,
    _settings,
)
from tests._test_artifact_generator.cases_05_docmap_insight_selection import (
    _doc_map,
    _generation_evidence,
    _insight,
)
from tests.test_verified_claims_visual_authority_canary import (
    SOURCE_IDENTITY,
    _candidate,
    _evidence_packs,
    _metric,
    _response,
    _result,
    _verified_admission,
    admit_visual_authority_candidates,
)
from tests.test_verified_claims_visual_authority_snapshot_integrity import (
    _generation_responses,
    _theme_coverage_response,
)


def test_same_id_result_from_a_stale_candidate_snapshot_fails_closed():
    current = _candidate()
    stale = _candidate(
        current["id"],
        evidence_id="finding-2",
        page=7,
        text="A stale candidate proposition.",
        metric=_metric("51%", cohort="repeat buyers"),
    )
    admission = admit_visual_authority_candidates(
        candidates=[current],
        evaluation=_response(_result(stale)),
        source_identity=SOURCE_IDENTITY,
        doc_map={},
        evidence_packs=_evidence_packs(current),
    )
    assert admission.admitted_candidates == []
    assert admission.audit["quarantined"] == [
        {
            "candidate_id": current["id"],
            "reason": "evaluation_candidate_snapshot_mismatch",
        }
    ]


def test_verified_regeneration_cannot_drop_original_essential_plan_evidence():
    original_plan = {
        "report_thesis": "The report connects three source-backed signals.",
        "themes": [
            {
                "theme": "Essential signal",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Retain the essential signal.",
                "evidence_ids": ["verified-fact:f1"],
                "feasible_candidate_ids": ["c1"],
            },
            {
                "theme": "Supporting signal",
                "priority": 2,
                "importance": "essential",
                "coverage_obligation": "Retain the supporting signal.",
                "evidence_ids": ["verified-fact:f2"],
                "feasible_candidate_ids": ["c2"],
            },
            {
                "theme": "Limitation",
                "priority": 3,
                "importance": "optional",
                "coverage_obligation": "Retain the limitation.",
                "evidence_ids": ["verified-fact:f3"],
                "feasible_candidate_ids": ["c3"],
            },
        ],
        "material_limitation_evidence_ids": ["verified-fact:f3"],
    }
    obligations = [
        {
            "theme": theme["theme"],
            "evidence_ids": list(theme["evidence_ids"]),
            "importance": theme["importance"],
            "coverage_obligation": theme["coverage_obligation"],
        }
        for theme in original_plan["themes"]
        if theme["importance"] == "essential"
    ]
    visual_cache = {
        "enabled": True,
        "verified_facts": [
            {"fact_id": "f1"},
            {"fact_id": "f2"},
            {"fact_id": "f3", "qualifiers": ["limited sample"]},
        ],
        "admitted_candidates": [
            {"id": "c1", "evidence_id": "verified-fact:f1"},
            {"id": "c2", "evidence_id": "verified-fact:f2"},
            {"id": "c3", "evidence_id": "verified-fact:f3"},
        ],
        "audit": {
            "editorial_plan_coverage": {
                "original_plan_identity": sha256_json(original_plan),
                "original_editorial_plan": deepcopy(original_plan),
                "original_essential_obligations": deepcopy(obligations),
            }
        },
    }
    current = {
        "_cache": {"visual_authority_canary": visual_cache},
        "editorial_plan": deepcopy(original_plan),
        "insights_candidates": [
            {"id": "c1", "evidence_id": "verified-fact:f1"},
            {"id": "c2", "evidence_id": "verified-fact:f2"},
            {"id": "c3", "evidence_id": "verified-fact:f3"},
        ],
        "insights_final": [
            {"id": "c1", "evidence_id": "verified-fact:f1"},
            {"id": "c2", "evidence_id": "verified-fact:f2"},
            {"id": "c3", "evidence_id": "verified-fact:f3"},
        ],
    }
    candidate = deepcopy(current)
    candidate["editorial_plan"]["themes"] = [
        deepcopy(original_plan["themes"][1]),
        deepcopy(original_plan["themes"][2]),
    ]
    candidate["insights_candidates"] = [
        item for item in candidate["insights_candidates"] if item["id"] != "c1"
    ]
    candidate["insights_final"] = [
        item for item in candidate["insights_final"] if item["id"] != "c1"
    ]

    issues = _verified_editorial_obligation_issues(
        current_artifacts=current,
        candidate_artifacts=candidate,
    )

    assert len(issues) == 1
    assert issues[0].rule_id == "verified_editorial_obligations"


def _plan(count: int = 2, *, limitations: list[str] | None = None) -> dict:
    return {
        "report_thesis": "The report contains distinct decision signals.",
        "themes": [
            {
                "theme": f"Theme {index}",
                "priority": index,
                "importance": "essential",
                "coverage_obligation": f"Develop proposition {index}.",
                "evidence_ids": [f"verified-fact:f{index}"],
                "feasible_candidate_ids": [f"candidate-{index}"],
            }
            for index in range(1, count + 1)
        ],
        "material_limitation_evidence_ids": (
            [] if limitations is None else limitations
        ),
    }


def _verified_artifacts(plan: dict, count: int | None = None) -> dict:
    count = count or len(plan["themes"])
    insights = [
        {
            "id": f"candidate-{index}",
            "text": f"Substantive editorial signal {index}.",
            "evidence_id": f"verified-fact:f{index}",
        }
        for index in range(1, count + 1)
    ]
    return {
        "verified_facts": [{"fact_id": f"f{index}"} for index in range(1, count + 1)],
        "editorial_plan": plan,
        "insights_final": insights,
        "family_status": {"insights_bundle": {"status": "generated"}},
        "_cache": {"visual_authority_canary": {"enabled": True}},
    }


@pytest.mark.parametrize("count", [2, 3, 4, 5, 7])
def test_verified_payload_preserves_exact_adaptive_roster(count: int) -> None:
    plan = _plan(count)
    payload = base_payload("Report", 1, "Contents", "contents.png")

    merged = merge_artifacts_into_payload(payload, _verified_artifacts(plan, count))

    assert merged.insights == [
        f"Substantive editorial signal {index}." for index in range(1, count + 1)
    ]


def test_verified_payload_fails_closed_for_missing_or_duplicate_roster() -> None:
    plan = _plan(2)
    artifacts = _verified_artifacts(plan, 2)
    artifacts["insights_final"][1]["id"] = artifacts["insights_final"][0]["id"]
    payload = base_payload("Report", 1, "Contents", "contents.png")

    with pytest.raises(AppError, match="distinct"):
        merge_artifacts_into_payload(payload, artifacts)

    artifacts = _verified_artifacts(plan, 2)
    artifacts["insights_final"][1]["text"] = ""
    with pytest.raises(AppError, match="substantive"):
        merge_artifacts_into_payload(payload, artifacts)


@pytest.mark.parametrize(
    ("insights_final", "plan", "message"),
    [
        ([], _plan(2), "absent or abstained"),
        (["not structured"], _plan(2), "stable identities"),
        (
            [
                {"id": "", "text": "signal"},
                {"id": "candidate-2", "text": "signal 2"},
            ],
            _plan(2),
            "stable candidate IDs",
        ),
        ([_verified_artifacts(_plan(2), 1)["insights_final"][0]], _plan(2), "below"),
    ],
)
def test_verified_payload_rejects_incomplete_adaptive_rosters(
    insights_final: list[object], plan: dict, message: str
) -> None:
    artifacts = _verified_artifacts(plan, max(1, len(insights_final)))
    artifacts["insights_final"] = insights_final
    payload = base_payload("Report", 1, "Contents", "contents.png")

    with pytest.raises(AppError, match=message):
        merge_artifacts_into_payload(payload, artifacts)


def _complete_payload(insights: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        title="Report",
        tldr="tldr",
        commentary="commentary",
        insights=insights,
        quote=SimpleNamespace(text="quote"),
        figure=SimpleNamespace(title="figure", evidence="evidence"),
    )


def test_verified_report_payload_requires_exact_adaptive_roster() -> None:
    plan = _plan(2)
    artifacts = _verified_artifacts(plan, 2)
    expected = [item["text"] for item in artifacts["insights_final"]]
    ctx = RunContext("1.0", "run", "analysis", "span")

    _ensure_report_payload_complete(
        _complete_payload(expected),
        artifacts=artifacts,
        ctx=ctx,
        file_id="file-1",
        stage="initial",
    )

    with pytest.raises(AppError) as error:
        _ensure_report_payload_complete(
            _complete_payload(["wrong editorial text", ""]),
            artifacts=artifacts,
            ctx=ctx,
            file_id="file-1",
            stage="initial",
        )

    assert error.value.context["missing_fields"] == ["insights", "insights[1]"]


def test_verified_report_payload_uses_conservative_fallback_for_invalid_plan() -> None:
    artifacts = _verified_artifacts(_plan(2), 5)
    artifacts["editorial_plan"] = {}
    expected = [item["text"] for item in artifacts["insights_final"]]

    _ensure_report_payload_complete(
        _complete_payload(expected),
        artifacts=artifacts,
        ctx=RunContext("1.0", "run", "analysis", "span"),
        file_id="file-1",
        stage="initial",
    )


def test_verified_plan_requires_executable_adaptive_bindings() -> None:
    plan = _plan(2)
    assert (
        validate_verified_editorial_plan(
            plan,
            canonical_evidence_ids={"verified-fact:f1", "verified-fact:f2"},
            admitted_candidate_ids={"candidate-1", "candidate-2"},
            admitted_limitation_evidence_ids=set(),
        )["themes"][0]["importance"]
        == "essential"
    )

    missing = _plan(2)
    del missing["themes"][0]["coverage_obligation"]
    with pytest.raises(AppError, match="coverage obligation"):
        validate_verified_editorial_plan(
            missing,
            canonical_evidence_ids={"verified-fact:f1", "verified-fact:f2"},
            admitted_candidate_ids={"candidate-1", "candidate-2"},
            admitted_limitation_evidence_ids=set(),
        )


@pytest.mark.parametrize(
    "case",
    [
        "missing_limitation_contract",
        "no_essential_theme",
        "unknown_candidate",
        "missing_factual_anchor",
        "unknown_limitation",
    ],
)
def test_verified_plan_rejects_ambiguous_or_unadmitted_bindings(case: str) -> None:
    plan = _plan(2)
    canonical_ids = {"verified-fact:f1", "verified-fact:f2"}
    admitted_ids = {"candidate-1", "candidate-2"}
    limitations: set[str] = set()
    candidate_bindings: dict[str, set[str]] | None = None
    if case == "missing_limitation_contract":
        del plan["material_limitation_evidence_ids"]
    elif case == "no_essential_theme":
        for theme in plan["themes"]:
            theme["importance"] = "optional"
    elif case == "unknown_candidate":
        plan["themes"][0]["feasible_candidate_ids"] = ["candidate-unknown"]
    elif case == "missing_factual_anchor":
        candidate_bindings = {
            "candidate-1": {"verified-fact:other"},
            "candidate-2": {"verified-fact:f2"},
        }
    elif case == "unknown_limitation":
        plan["material_limitation_evidence_ids"] = ["verified-fact:missing"]
        canonical_ids.add("verified-fact:missing")
    with pytest.raises(AppError):
        validate_verified_editorial_plan(
            plan,
            canonical_evidence_ids=canonical_ids,
            admitted_candidate_ids=admitted_ids,
            admitted_limitation_evidence_ids=limitations,
            admitted_candidate_evidence_ids=candidate_bindings,
        )


def test_verified_plan_revision_preserves_all_original_essential_bindings() -> None:
    original = _plan(2)
    revised = {
        "report_thesis": original["report_thesis"],
        "themes": [
            {
                "theme": "Merged decision",
                "priority": 1,
                "importance": "essential",
                "coverage_obligation": "Develop both propositions together.",
                "evidence_ids": ["verified-fact:f1", "verified-fact:f2"],
                "feasible_candidate_ids": ["candidate-1", "candidate-2"],
            },
            {
                "theme": "Optional context",
                "priority": 2,
                "importance": "optional",
                "coverage_obligation": "Retain only if distinct.",
                "evidence_ids": ["verified-fact:f1"],
                "feasible_candidate_ids": [],
            },
        ],
        "material_limitation_evidence_ids": [],
    }
    assert (
        validate_verified_editorial_plan_revision(
            original,
            revised,
            canonical_evidence_ids={"verified-fact:f1", "verified-fact:f2"},
            admitted_candidate_ids={"candidate-1", "candidate-2"},
            admitted_limitation_evidence_ids=set(),
        )
        is None
    )

    dropped = {
        **revised,
        "themes": [
            {**revised["themes"][0], "evidence_ids": ["verified-fact:f1"]},
            dict(revised["themes"][1]),
        ],
    }
    with pytest.raises(AppError, match="drop or downgrade"):
        validate_verified_editorial_plan_revision(
            original,
            dropped,
            canonical_evidence_ids={"verified-fact:f1", "verified-fact:f2"},
            admitted_candidate_ids={"candidate-1", "candidate-2"},
            admitted_limitation_evidence_ids=set(),
        )


def test_verified_plan_revision_preserves_original_limitations() -> None:
    original = _plan(2, limitations=["verified-fact:f1"])
    revised = deepcopy(original)
    revised["material_limitation_evidence_ids"] = []

    with pytest.raises(AppError, match="material limitations"):
        validate_verified_editorial_plan_revision(
            original,
            revised,
            canonical_evidence_ids={"verified-fact:f1", "verified-fact:f2"},
            admitted_candidate_ids={"candidate-1", "candidate-2"},
            admitted_limitation_evidence_ids={"verified-fact:f1"},
        )


def _coverage_plan() -> dict:
    plan = _plan(2)
    plan["themes"][1]["importance"] = "optional"
    return plan


def _coverage_payload(*assessments: dict, **extra: object) -> dict:
    return {
        "theme_coverage": list(assessments),
        "report_completeness": "complete",
        "diagnosis": "planned_theme_execution",
        "recovery_action": "none",
        **extra,
    }


def _assessment(theme: str, *, status: str, resolution: str, ids: list[str]) -> dict:
    return {
        "theme": theme,
        "status": status,
        "resolution": resolution,
        "supporting_insight_ids": ids,
        "explanation": f"The final prose addresses {theme}.",
    }


def test_verified_coverage_matrix_accepts_retained_and_optional_omitted() -> None:
    result = validate_substantive_editorial_theme_coverage(
        payload=_coverage_payload(
            _assessment("Theme 1", status="covered", resolution="retained", ids=["i1"]),
            _assessment("Theme 2", status="uncovered", resolution="omitted", ids=[]),
        ),
        editorial_plan=_coverage_plan(),
        final_insights=[
            {"id": "i1", "text": "Signal one.", "evidence_id": "verified-fact:f1"}
        ],
    )
    assert result["omitted_themes"] == ["Theme 2"]


@pytest.mark.parametrize(
    ("status", "resolution"),
    [("covered", "omitted"), ("partial", "unresolved"), ("uncovered", "retained")],
)
def test_verified_coverage_matrix_rejects_incoherent_resolution(
    status: str, resolution: str
) -> None:
    with pytest.raises(AppError):
        validate_substantive_editorial_theme_coverage(
            payload=_coverage_payload(
                _assessment("Theme 1", status=status, resolution=resolution, ids=[]),
                _assessment(
                    "Theme 2", status="covered", resolution="retained", ids=["i2"]
                ),
            ),
            editorial_plan=_coverage_plan(),
            final_insights=[
                {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"}
            ],
        )


def test_verified_coverage_requires_complete_contract_fields() -> None:
    payload = {
        "theme_coverage": [
            _assessment("Theme 1", status="covered", resolution="retained", ids=["i1"]),
            _assessment("Theme 2", status="covered", resolution="retained", ids=["i2"]),
        ],
        "report_completeness": "complete",
    }
    with pytest.raises(AppError, match="diagnosis|recovery"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=_coverage_plan(),
            final_insights=[
                {"id": "i1", "text": "Signal one.", "evidence_id": "verified-fact:f1"},
                {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"},
            ],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("diagnosis", "unrecognised_diagnosis"),
        ("recovery_action", "unrecognised_action"),
        ("report_completeness", "unrecognised_completeness"),
    ],
)
def test_verified_coverage_rejects_invalid_recovery_contract_values(
    field: str, value: str
) -> None:
    payload = _coverage_payload(
        _assessment("Theme 1", status="covered", resolution="retained", ids=["i1"]),
        _assessment("Theme 2", status="covered", resolution="retained", ids=["i2"]),
    )
    payload[field] = value
    with pytest.raises(AppError):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=_coverage_plan(),
            final_insights=[
                {"id": "i1", "text": "Signal one.", "evidence_id": "verified-fact:f1"},
                {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"},
            ],
        )


def test_verified_coverage_quarantine_and_unsupported_resolution_fail_closed() -> None:
    with pytest.raises(AppError, match="Quarantined"):
        validate_substantive_editorial_theme_coverage(
            payload=_coverage_payload(
                _assessment(
                    "Theme 1", status="uncovered", resolution="quarantined", ids=[]
                ),
                _assessment(
                    "Theme 2", status="covered", resolution="retained", ids=["i2"]
                ),
            ),
            editorial_plan=_coverage_plan(),
            final_insights=[
                {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"}
            ],
        )

    with pytest.raises(AppError, match="supporting"):
        validate_substantive_editorial_theme_coverage(
            payload=_coverage_payload(
                _assessment(
                    "Theme 1", status="uncovered", resolution="unresolved", ids=["i1"]
                ),
                _assessment(
                    "Theme 2", status="covered", resolution="retained", ids=["i2"]
                ),
            ),
            editorial_plan=_coverage_plan(),
            final_insights=[
                {"id": "i1", "text": "Signal one.", "evidence_id": "verified-fact:f1"},
                {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"},
            ],
        )


def test_verified_coverage_requires_original_obligation_list_after_replan() -> None:
    with pytest.raises(AppError, match="original essential obligation"):
        validate_substantive_editorial_theme_coverage(
            payload=_coverage_payload(
                _assessment(
                    "Theme 1", status="covered", resolution="retained", ids=["i1"]
                ),
                _assessment(
                    "Theme 2", status="covered", resolution="retained", ids=["i2"]
                ),
            ),
            editorial_plan=_coverage_plan(),
            final_insights=[
                {"id": "i1", "text": "Signal one.", "evidence_id": "verified-fact:f1"},
                {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"},
            ],
            original_essential_obligations=[
                {
                    "theme": "Theme 1",
                    "evidence_ids": ["verified-fact:f1"],
                }
            ],
            require_original_obligation_assessment=True,
        )


@pytest.mark.parametrize(
    "case",
    [
        "missing_assessment_list",
        "malformed_assessment",
        "ambiguous_assessment",
        "unauthorized_supporting_id",
        "covered_without_support",
        "covered_with_omitted_resolution",
        "partial_with_retained_resolution",
        "uncovered_with_retained_resolution",
        "optional_omission_without_complete_report",
        "omitted_theme_with_supporting_id",
        "supporting_fact_not_bound_to_theme",
        "missing_planned_theme",
    ],
)
def test_verified_coverage_rejects_contract_matrix_edges(case: str) -> None:
    complete_one = _assessment(
        "Theme 1", status="covered", resolution="retained", ids=["i1"]
    )
    complete_two = _assessment(
        "Theme 2", status="covered", resolution="retained", ids=["i2"]
    )
    final_insights = [
        {"id": "i1", "text": "Signal one.", "evidence_id": "verified-fact:f1"},
        {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"},
    ]
    payload = _coverage_payload(complete_one, complete_two)
    if case == "missing_assessment_list":
        del payload["theme_coverage"]
    elif case == "malformed_assessment":
        payload["theme_coverage"] = [None, complete_two]
    elif case == "ambiguous_assessment":
        payload["theme_coverage"] = [
            {**complete_one, "resolution": "not-a-resolution"},
            complete_two,
        ]
    elif case == "unauthorized_supporting_id":
        payload["theme_coverage"] = [
            {**complete_one, "supporting_insight_ids": ["unknown"]},
            complete_two,
        ]
    elif case == "covered_without_support":
        payload["theme_coverage"] = [
            {**complete_one, "supporting_insight_ids": []},
            complete_two,
        ]
    elif case == "covered_with_omitted_resolution":
        payload["theme_coverage"] = [
            {**complete_one, "resolution": "omitted"},
            complete_two,
        ]
    elif case == "partial_with_retained_resolution":
        payload["theme_coverage"] = [
            {**complete_one, "status": "partial", "resolution": "retained"},
            complete_two,
        ]
    elif case == "uncovered_with_retained_resolution":
        payload["theme_coverage"] = [
            {
                **complete_one,
                "status": "uncovered",
                "resolution": "retained",
                "supporting_insight_ids": [],
            },
            complete_two,
        ]
    elif case == "optional_omission_without_complete_report":
        payload["report_completeness"] = "incomplete"
        payload["theme_coverage"] = [
            complete_one,
            _assessment("Theme 2", status="uncovered", resolution="omitted", ids=[]),
        ]
    elif case == "omitted_theme_with_supporting_id":
        payload["theme_coverage"] = [
            complete_one,
            _assessment(
                "Theme 2", status="uncovered", resolution="omitted", ids=["i2"]
            ),
        ]
    elif case == "supporting_fact_not_bound_to_theme":
        payload["theme_coverage"] = [
            {**complete_one, "supporting_insight_ids": ["i2"]},
            complete_two,
        ]
    elif case == "missing_planned_theme":
        payload["theme_coverage"] = [complete_one]
    with pytest.raises(AppError):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=_coverage_plan(),
            final_insights=final_insights,
        )


@pytest.mark.parametrize(
    "case",
    [
        "malformed_obligation",
        "incomplete_obligation",
        "invalid_supporting_id",
        "unlinked_supporting_fact",
        "unresolved_obligation",
    ],
)
def test_verified_replan_rejects_incomplete_original_obligation_assessment(
    case: str,
) -> None:
    obligations = [
        {
            "theme": "Theme 1",
            "evidence_ids": ["verified-fact:f1"],
            "importance": "essential",
            "coverage_obligation": "Develop proposition 1.",
        }
    ]
    payload = _coverage_payload(
        _assessment("Theme 1", status="covered", resolution="retained", ids=["i1"]),
        _assessment("Theme 2", status="covered", resolution="retained", ids=["i2"]),
    )
    assessment: object = {
        "theme": "Theme 1",
        "evidence_ids": ["verified-fact:f1"],
        "status": "covered",
        "supporting_insight_ids": ["i1"],
        "explanation": "The original obligation remains explicit.",
    }
    if case == "malformed_obligation":
        assessment = None
    elif case == "incomplete_obligation":
        assessment = {"theme": "Theme 1", "evidence_ids": ["verified-fact:f1"]}
    elif case == "invalid_supporting_id":
        assessment = {**assessment, "supporting_insight_ids": ["unknown"]}
    elif case == "unlinked_supporting_fact":
        assessment = {
            **assessment,
            "supporting_insight_ids": ["i2"],
        }
    elif case == "unresolved_obligation":
        assessment = {**assessment, "status": "partial"}
    payload["original_essential_obligation_assessments"] = [assessment]
    with pytest.raises(AppError):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=_coverage_plan(),
            final_insights=[
                {"id": "i1", "text": "Signal one.", "evidence_id": "verified-fact:f1"},
                {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"},
            ],
            original_essential_obligations=obligations,
            require_original_obligation_assessment=True,
        )


def test_verified_limitation_contract_preserves_explicit_empty_selection() -> None:
    assert (
        _coerce_limitation_items(
            {
                "limitations": {
                    "limitations": [
                        {"text": "A source limitation.", "evidence_id": "f1"}
                    ]
                },
                "verified_facts": {
                    "verified_facts": [
                        {"fact_id": "f1", "qualifiers": ["A source limitation."]}
                    ]
                },
            },
            verified_mode=True,
            artifacts={
                "editorial_plan": {"material_limitation_evidence_ids": []},
                "insights_final": [],
            },
        )
        == []
    )


def test_verified_limitation_fallback_preserves_all_selected_qualifiers() -> None:
    rows = _coerce_limitation_items(
        {
            "verified_facts": {
                "verified_facts": [
                    {"fact_id": "f1", "qualifiers": ["First limitation."]},
                    {"fact_id": "f2", "qualifiers": ["Second limitation."]},
                ]
            }
        },
        verified_mode=True,
        artifacts={
            "editorial_plan": {
                "material_limitation_evidence_ids": [
                    "verified-fact:f2",
                    "verified-fact:f1",
                ]
            },
            "insights_final": [],
        },
    )
    assert {row["text"] for row in rows} == {
        "First limitation.",
        "Second limitation.",
    }


def test_verified_expert_context_preserves_selected_limitation_order_and_fallback() -> (
    None
):
    plan = {
        "report_thesis": "The report contains a bounded decision signal.",
        "themes": [
            {
                "theme": "Decision signal",
                "priority": 1,
                "evidence_ids": ["verified-fact:f1"],
            },
            {
                "theme": "Context",
                "priority": 2,
                "evidence_ids": ["verified-fact:f2"],
            },
        ],
        "material_limitation_evidence_ids": [
            "verified-fact:f2",
            "verified-fact:f1",
        ],
    }
    context = build_expert_synthesis_context(
        editorial_plan=plan,
        insights_final=[],
        doc_map={},
        evidence_packs={
            "limitations": {
                "limitations": [
                    {"text": "First limitation.", "evidence_id": "verified-fact:f1"},
                    {"text": "Second limitation.", "evidence_id": "verified-fact:f2"},
                ]
            }
        },
    )
    assert [row["text"] for row in context["limitations"]] == [
        "Second limitation.",
        "First limitation.",
    ]

    malformed = build_expert_synthesis_context(
        editorial_plan=plan,
        insights_final=[],
        doc_map={},
        evidence_packs={"verified_facts": {"verified_facts": "malformed"}},
    )
    assert malformed["limitations"] == []

    sparse = build_expert_synthesis_context(
        editorial_plan=plan,
        insights_final=[],
        doc_map={},
        evidence_packs={
            "verified_facts": {
                "verified_facts": [
                    None,
                    {"fact_id": "", "qualifiers": ["ignored"]},
                    {"fact_id": "f1", "qualifiers": ["Recovered qualifier."]},
                ]
            }
        },
    )
    assert sparse["limitations"] == [
        {"evidence_id": "verified-fact:f1", "text": "Recovered qualifier."}
    ]


def test_verified_advisory_does_not_truncate_selected_limitations() -> None:
    limitations = [
        {"text": f"Limitation {index}.", "evidence_id": f"f{index}"}
        for index in range(1, 7)
    ]
    advisory = build_executive_advisory_artifacts(
        summary={},
        insights_final=[],
        quotes_final=[],
        metric_spine=[],
        evidence_packs={"limitations": {"limitations": limitations}},
        editorial_plan={
            "material_limitation_evidence_ids": [f"f{index}" for index in range(1, 7)]
        },
    )
    assert advisory["decision_brief"]["watchouts"] == [
        f"Limitation {index}." for index in range(1, 7)
    ]

    empty_selection = build_executive_advisory_artifacts(
        summary={},
        insights_final=[],
        quotes_final=[],
        metric_spine=[],
        evidence_packs={"limitations": {"limitations": limitations}},
        editorial_plan={"material_limitation_evidence_ids": []},
    )
    assert empty_selection["decision_brief"]["watchouts"] == []


def test_post_replan_coverage_explicitly_confirms_original_obligations() -> None:
    obligations = [
        {
            "theme": "Theme 1",
            "evidence_ids": ["verified-fact:f1"],
            "importance": "essential",
            "coverage_obligation": "Develop proposition 1.",
        }
    ]
    payload = _coverage_payload(
        _assessment("Theme 1", status="covered", resolution="retained", ids=["i1"]),
        _assessment("Theme 2", status="covered", resolution="retained", ids=["i2"]),
        original_essential_obligation_assessments=[
            {
                "theme": "Theme 1",
                "evidence_ids": ["verified-fact:f1"],
                "status": "covered",
                "supporting_insight_ids": ["i1"],
                "explanation": "The original proposition remains explicit.",
            }
        ],
    )
    result = validate_substantive_editorial_theme_coverage(
        payload=payload,
        editorial_plan=_coverage_plan(),
        final_insights=[
            {"id": "i1", "text": "Signal one.", "evidence_id": "verified-fact:f1"},
            {"id": "i2", "text": "Signal two.", "evidence_id": "verified-fact:f2"},
        ],
        original_essential_obligations=obligations,
        require_original_obligation_assessment=True,
    )
    assert result["original_essential_obligation_assessments"][0]["status"] == (
        "covered"
    )

    payload["original_essential_obligation_assessments"] = []
    with pytest.raises(AppError, match="every original essential obligation"):
        validate_substantive_editorial_theme_coverage(
            payload=payload,
            editorial_plan=_coverage_plan(),
            final_insights=[
                {
                    "id": "i1",
                    "text": "Signal one.",
                    "evidence_id": "verified-fact:f1",
                },
                {
                    "id": "i2",
                    "text": "Signal two.",
                    "evidence_id": "verified-fact:f2",
                },
            ],
            original_essential_obligations=obligations,
            require_original_obligation_assessment=True,
        )


@pytest.mark.parametrize(
    ("diagnosis", "action", "expected"),
    [
        ("planned_theme_execution", "targeted_rewrite", "targeted_rewrite"),
        ("infeasible_plan", "replan", "replan"),
        ("insufficient_evidence", "quarantine", "quarantine"),
    ],
)
def test_semantic_recovery_classifier_uses_explicit_assessment(
    diagnosis: str, action: str, expected: str
) -> None:
    assert (
        _classify_verified_semantic_recovery(
            assessment={"diagnosis": diagnosis, "recovery_action": action},
            error_context={},
        )
        == expected
    )


def test_semantic_recovery_classifier_fails_closed_on_contract_error() -> None:
    assert (
        _classify_verified_semantic_recovery(
            assessment={"diagnosis": "infeasible_plan", "recovery_action": "replan"},
            error_context={"assessment_contract_failure": True},
        )
        == "fail_closed"
    )


def test_verified_generation_materializes_downstream_insights_from_snapshot(
    tmp_path,
) -> None:
    candidates = [
        _insight("f1", score=0.99),
        _insight("f2", score=0.98),
        _insight("f3", score=0.97),
        _insight("f4", score=0.96),
        _insight("f5", score=0.95),
    ]

    def admit(shortlisted):
        admission = _verified_admission(shortlisted, digest="s" * 64)
        admission.admitted_candidates[0]["text"] = "Stale projection wording."
        admission.admitted_candidates[0]["metric"] = {
            **admission.admitted_candidates[0]["metric"],
            "value": "999%",
        }
        return admission

    responses = _generation_responses(candidates, plan_evidence_ids=["f1", "f2"])
    responses["insights_final"] = {
        "insights_final": [
            {
                **deepcopy(candidate),
                "evidence_id": f"verified-fact:{candidate['id']}",
                "evidence_spans": [],
            }
            for candidate in candidates
        ]
    }
    responses["summary"]["summary"]["claim_evidence_map"][0]["evidence_id"] = (
        "verified-fact:insight-f1-0.99"
    )
    responses["editorial_theme_coverage"] = _theme_coverage_response(
        candidates,
        ["f1", "f2"],
        covered_evidence_ids={"f1", "f2"},
    )
    payload = generate_artifacts(
        report_id="visual-authority-snapshot-materialization",
        report_name="Visual Authority Snapshot Materialization",
        doc_map=_doc_map(5),
        evidence_packs=_generation_evidence(5),
        settings=_settings(tmp_path),
        ctx=_ctx(),
        openai_client=FakeOpenAI(responses),
        prompt_client=CapturingPromptClient(),
        analysis_store=FakeAnalysisStore(),
        visual_authority_admitter=admit,
    )
    assert all(item["metric"]["value"] != "999%" for item in payload["insights_final"])
    assert all(item["metric"]["value"] == "10" for item in payload["insights_final"])
    assert payload["verified_facts"][0]["metric"]["value"] == "10"
