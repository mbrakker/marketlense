# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


_validate_regeneration_candidate = validate_regeneration_candidate


def validate_regeneration_candidate(**kwargs):
    """Supply the warning baseline for pre-existing fixture findings."""

    kwargs.setdefault(
        "baseline_retained_claim_severities",
        _baseline_retained_claim_warnings(
            kwargs["current_artifacts"], kwargs["evidence_packs"]
        ),
    )
    return _validate_regeneration_candidate(**kwargs)


@pytest.mark.parametrize(
    ("replacement", "expected_pass"),
    [
        ("Adjust spend reached 1016.8 million in 2025.", False),
        ("Adjust spend reached 1000.0 million in 2025.", True),
        ("Adjust spend reached 1000.0 million in 2026.", False),
    ],
)
def test_adjust_shaped_factual_repair_requires_selected_numeric_support(
    replacement: str, expected_pass: bool
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    original = "Adjust spend reached 999.0 million in 2025."
    current["expert_comment"] = original
    old_claim = _soft_copy_claim(
        family="expert_comment", text=original, evidence_id="qc_002"
    )
    current["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in current["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + [old_claim]
    candidate = deepcopy(current)
    candidate["expert_comment"] = replacement
    repaired = _soft_copy_claim(
        family="expert_comment", text=replacement, regeneration_attempt=1
    )
    repaired["repaired_from_claim_id"] = old_claim["claim_id"]
    repaired["producing_prompt_identity"]["namespace"] = (
        "report_vs/artifacts/regenerate/expert_comment"
    )
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + [repaired]
    selection = _complete_repair_selection(
        original_claim_id=str(old_claim["claim_id"]),
        repaired_claim_id=str(repaired["claim_id"]),
    )
    selection["strategy"] = "typed_compatibility_fallback"
    selection["direct_evidence_ids"] = ["qc_002"]
    selection["quarantined_evidence_ids"] = ["qc_002"]
    selection["selected_evidence_entries"] = [
        {
            "id": "qc_001",
            "page": 6,
            "text": "Adjust spend reached 1000.0 million in 2025.",
        }
    ]
    _refresh_repair_selection_hash(selection)
    candidate["_repair_evidence_selection"] = {
        f"expert_comment:{old_claim['claim_id']}": selection
    }
    for quote in evidence_packs["quote_candidates"]["quote_candidates"]:
        if quote["id"] in {"qc_001", "qc_002"}:
            source_value = "1000.0" if quote["id"] == "qc_001" else "900.0"
            quote["quote_text"] = (
                f"Adjust spend reached {source_value} million in 2025."
            )

    original_result = validate_retained_claims(current, evidence_packs)
    assert any(
        result.candidate.claim_id == old_claim["claim_id"]
        and result.status == "unsupported"
        and "quantity_not_entailed" in result.reasons
        for result in original_result.results
    )
    number_issues = validate_new_numbers(
        artifacts=current,
        insights=[],
        report=_report(),
        evidence_texts=[
            quote["quote_text"]
            for quote in evidence_packs["quote_candidates"]["quote_candidates"]
            if quote["id"] in {"qc_001", "qc_002"}
        ],
    )
    assert any(
        issue.affected_section == "expert_comment"
        and issue.rule_id == "numbers"
        and issue.entity_id == old_claim["claim_id"]
        for issue in number_issues
    )
    sibling_before = _claim_for_family(current, "linkedin_post")
    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert result.passed is expected_pass
    assert _claim_for_family(candidate, "linkedin_post") == sibling_before
    assert selection["quarantined_evidence_ids"] == ["qc_002"]
    assert repaired["evidence_ids"] == ["qc_001"]
    support_issues = [
        issue
        for issue in result.issues
        if issue.rule_id == "regeneration_claim_support"
    ]
    claim_lineage = next(
        item
        for item in result.evidence_lineage
        if item.entity_kind == "soft_copy_claim"
        and item.entity_id == repaired["claim_id"]
    )
    assert claim_lineage.original_evidence_ids == ["qc_002"]
    assert claim_lineage.candidate_evidence_ids == ["qc_001"]
    assert claim_lineage.original_source_pages == [6]
    assert claim_lineage.candidate_source_pages == [6]
    if expected_pass:
        assert not support_issues
    else:
        assert len(support_issues) == 1
        assert support_issues[0].affected_section == (
            f"expert_comment:{repaired['claim_id']}"
        )
        assert support_issues[0].entity_id == repaired["claim_id"]
        assert support_issues[0].evidence_ids == ["qc_001"]
        assert "regeneration_claim_support" in claim_lineage.validation_issues


def test_interpretive_numeric_repair_does_not_gain_factual_candidate_gate() -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    candidate["expert_comment"] = "Adjust could reach 1016.8 million."
    claim = _soft_copy_claim(
        family="expert_comment",
        text=candidate["expert_comment"],
        regeneration_attempt=1,
    )
    claim["classification"] = "interpretive"
    candidate["soft_copy_claim_provenance"]["claims"] = [
        retained
        for retained in candidate["soft_copy_claim_provenance"]["claims"]
        if retained["artifact_family"] != "expert_comment"
    ] + [claim]

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert result.passed
    assert not any(
        issue.rule_id == "regeneration_claim_support" for issue in result.issues
    )


@pytest.mark.parametrize("family", ["expert_comment", "linkedin_post"])
@pytest.mark.parametrize(
    "strategy", ["claim_evidence_ids", "typed_compatibility_fallback"]
)
def test_candidate_allows_repaired_factual_claim_with_explicit_new_lineage(
    family: str,
    strategy: str,
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    original_claim = _claim_for_family(current, family)
    candidate[family] = "Generation Q developed in digital spaces."
    repaired = _soft_copy_claim(
        family=family,
        text=candidate[family],
        regeneration_attempt=1,
    )
    repaired["producing_prompt_identity"]["namespace"] = (
        f"report_vs/artifacts/regenerate/{family}"
    )
    repaired["repaired_from_claim_id"] = original_claim["claim_id"]
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != family
    ] + [repaired]
    candidate["_repair_evidence_selection"] = {
        f"{family}:{original_claim['claim_id']}": _complete_repair_selection(
            original_claim_id=str(original_claim["claim_id"]),
            repaired_claim_id=str(repaired["claim_id"]),
        )
    }
    selection = candidate["_repair_evidence_selection"][
        f"{family}:{original_claim['claim_id']}"
    ]
    selection["strategy"] = strategy
    _refresh_repair_selection_hash(selection)

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert result.passed


@pytest.mark.parametrize("family", ["expert_comment", "linkedin_post"])
def test_candidate_blocks_repaired_factual_claim_with_missing_or_corrupt_selection_lineage(
    family: str,
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    original_claim = _claim_for_family(current, family)
    candidate[family] = "Generation Q developed in digital spaces."
    repaired = _soft_copy_claim(
        family=family,
        text=candidate[family],
        regeneration_attempt=1,
    )
    repaired["repaired_from_claim_id"] = original_claim["claim_id"]
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != family
    ] + [repaired]

    missing = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    candidate["_repair_evidence_selection"] = {
        f"{family}:{original_claim['claim_id']}": {
            **_complete_repair_selection(
                original_claim_id=str(original_claim["claim_id"]),
                repaired_claim_id=str(repaired["claim_id"]),
            ),
            "repaired_claim_id": "different-repaired-claim",
        }
    }
    corrupt = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not missing.passed
    assert any(
        "missing repair-selection lineage" in issue.message for issue in missing.issues
    )
    assert not corrupt.passed
    assert any(
        "corrupt repair-selection lineage" in issue.message for issue in corrupt.issues
    )


@pytest.mark.parametrize(
    ("family", "mutation"),
    [
        ("expert_comment", "quarantined_evidence_ids"),
        ("linkedin_post", "selected_evidence_ids"),
        ("expert_comment", "selected_evidence_entries"),
        ("linkedin_post", "package_sha256"),
        ("expert_comment", "strategy"),
    ],
)
def test_candidate_rejects_repaired_claim_with_stale_or_missing_selection_hash(
    family: str, mutation: str
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    original_claim = _claim_for_family(current, family)
    candidate[family] = "Generation Q developed in digital spaces."
    repaired = _soft_copy_claim(
        family=family,
        text=candidate[family],
        regeneration_attempt=1,
    )
    repaired["repaired_from_claim_id"] = original_claim["claim_id"]
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != family
    ] + [repaired]
    selection = _complete_repair_selection(
        original_claim_id=str(original_claim["claim_id"]),
        repaired_claim_id=str(repaired["claim_id"]),
    )
    if mutation == "quarantined_evidence_ids":
        selection[mutation] = ["qc_001"]
    elif mutation == "selected_evidence_ids":
        selection[mutation] = ["different-evidence"]
    elif mutation == "selected_evidence_entries":
        selection[mutation] = [{"id": "qc_001", "page": 6, "text": "Changed."}]
    elif mutation == "strategy":
        selection[mutation] = "lexical_fallback"
    else:
        selection.pop("package_sha256")
    candidate["_repair_evidence_selection"] = {
        f"{family}:{original_claim['claim_id']}": selection
    }

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.affected_section == f"{family}:{repaired['claim_id']}"
        and "corrupt repair-selection lineage" in issue.message
        for issue in result.issues
    )


@pytest.mark.parametrize("strategy", ["abstain", "claim_evidence_ids"])
def test_candidate_rejects_factual_repair_without_selected_evidence(
    strategy: str,
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    original_claim = _claim_for_family(current, "expert_comment")
    candidate["expert_comment"] = "Generation Q developed in digital spaces."
    repaired = _soft_copy_claim(
        family="expert_comment",
        text=candidate["expert_comment"],
        regeneration_attempt=1,
    )
    repaired["repaired_from_claim_id"] = original_claim["claim_id"]
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + [repaired]
    selection = _complete_repair_selection(
        original_claim_id=str(original_claim["claim_id"]),
        repaired_claim_id=str(repaired["claim_id"]),
    )
    selection["strategy"] = strategy
    selection["selected_evidence_ids"] = []
    selection["selected_evidence_entries"] = []
    _refresh_repair_selection_hash(selection)
    candidate["_repair_evidence_selection"] = {
        f"expert_comment:{original_claim['claim_id']}": selection
    }

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.affected_section == f"expert_comment:{repaired['claim_id']}"
        and "no selected evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_blocks_repaired_expert_claim_without_new_lineage() -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    candidate["expert_comment"] = "Generation Q developed in digital spaces."
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != "expert_comment"
    ] + [_soft_copy_claim(family="expert_comment", text=candidate["expert_comment"])]

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.affected_section.startswith("expert_comment")
        and "new lineage" in issue.message
        for issue in result.issues
    )


@pytest.mark.parametrize("family", ["expert_comment", "linkedin_post"])
def test_candidate_blocks_factual_soft_copy_claim_using_quarantined_evidence(
    family: str,
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    claim = _claim_for_family(candidate, family)
    candidate["_repair_evidence_selection"] = {
        f"{family}:{claim['claim_id']}": {
            "quarantined_evidence_ids": ["qc_001"],
        }
    }

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.affected_section == f"{family}:{claim['claim_id']}"
        and "quarantined" in issue.message
        for issue in result.issues
    )


@pytest.mark.parametrize("family", ["expert_comment", "linkedin_post"])
def test_candidate_blocks_factual_soft_copy_claim_without_evidence_id(
    family: str,
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    _claim_for_family(candidate, family)["evidence_ids"] = []

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.affected_section
        == f"{family}:{_claim_for_family(candidate, family)['claim_id']}"
        and "missing_material_evidence" in issue.message
        for issue in result.issues
    )


@pytest.mark.parametrize("family", ["expert_comment", "linkedin_post"])
def test_candidate_blocks_factual_soft_copy_claim_with_unknown_evidence_id(
    family: str,
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    claim = _claim_for_family(candidate, family)
    claim["evidence_ids"] = ["missing-soft-copy-evidence"]
    claim["source_spans"][0]["evidence_id"] = "missing-soft-copy-evidence"

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any("hallucinated_evidence_id" in issue.message for issue in result.issues)


@pytest.mark.parametrize("family", ["expert_comment", "linkedin_post"])
def test_candidate_blocks_factual_soft_copy_claim_with_wrong_source_page(
    family: str,
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    _claim_for_family(candidate, family)["source_spans"][0]["page"] = 99

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.rule_id == "regeneration_source_page"
        and issue.affected_section.startswith(family)
        for issue in result.issues
    )


@pytest.mark.parametrize("family", ["expert_comment", "linkedin_post"])
def test_candidate_blocks_unchanged_factual_soft_copy_claim_that_loses_lineage(
    family: str,
) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != family
    ]

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.affected_section.startswith(family)
        and "claim provenance" in issue.message
        for issue in result.issues
    )


@pytest.mark.parametrize("family", ["expert_comment", "linkedin_post"])
def test_candidate_allows_explicit_soft_copy_family_abstention(family: str) -> None:
    current, candidate, evidence_packs = _soft_copy_artifacts()
    candidate[family] = ""
    candidate["soft_copy_claim_provenance"]["claims"] = [
        claim
        for claim in candidate["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] != family
    ]
    candidate["family_status"] = build_artifact_family_status(
        summary=candidate.get("summary", {}),
        insights_candidates=candidate.get("insights_candidates", []),
        insights_final=candidate.get("insights_final", []),
        quotes_final=candidate.get("quotes_final", []),
        expert_comment=candidate.get("expert_comment", ""),
        linkedin_post=candidate.get("linkedin_post", ""),
    )

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert result.passed


def test_candidate_blocks_lost_and_hallucinated_evidence_ids() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    lost = deepcopy(current)
    lost["insights_final"][0]["evidence_id"] = ""
    hallucinated = deepcopy(current)
    hallucinated["insights_final"][0]["evidence_id"] = "invented-evidence-id"

    lost_result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=lost,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    hallucinated_result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=hallucinated,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not lost_result.passed
    assert any(
        "missing_material_evidence" in issue.message for issue in lost_result.issues
    )
    assert not hallucinated_result.passed
    assert any(
        "hallucinated_evidence_id" in issue.message
        for issue in hallucinated_result.issues
    )


def test_candidate_allows_known_evidence_remapping_and_abstention() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    remapped = deepcopy(current)
    remapped["quotes_final"][0]["evidence_id"] = "quote_3"
    normalize_artifact_evidence_ids(
        summary=remapped["summary"],
        insights_candidates=remapped["insights_candidates"],
        insights_final=remapped["insights_final"],
        quotes_final=remapped["quotes_final"],
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
    )
    abstained = deepcopy(current)
    abstained["quotes_final"] = []
    abstained["family_status"] = build_artifact_family_status(
        summary=abstained.get("summary", {}),
        insights_candidates=abstained.get("insights_candidates", []),
        insights_final=abstained.get("insights_final", []),
        quotes_final=abstained.get("quotes_final", []),
        expert_comment=abstained.get("expert_comment", ""),
        linkedin_post=abstained.get("linkedin_post", ""),
    )

    remapped_result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=remapped,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    abstained_result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=abstained,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert remapped["quotes_final"][0]["evidence_id"] == "qc_003"
    assert remapped_result.passed
    assert abstained_result.passed


def test_candidate_normalizes_a_known_namespaced_quote_evidence_id() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    candidate["quotes_final"][0]["evidence_id"] = "evidence:quote_candidates:quote_001"

    normalize_artifact_evidence_ids(
        summary=candidate["summary"],
        insights_candidates=candidate["insights_candidates"],
        insights_final=candidate["insights_final"],
        quotes_final=candidate["quotes_final"],
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
    )

    assert candidate["quotes_final"][0]["evidence_id"] == "qc_001"


def test_artifact_insight_drops_a_calendar_phrase_as_a_public_metric() -> None:
    insight = normalize_artifact_insights(
        [
            {
                "id": "identity-transition",
                "text": (
                    "Third-party cookies are expected to be eliminated by the end "
                    "of 2021."
                ),
                "metric": {
                    "label": "Cookie elimination timing",
                    "value": "by the end of 2021",
                    "unit": "",
                },
            }
        ],
        prefix="insight",
    )[0]

    assert insight["metric"]["value"] == ""
    assert insight["metric"]["label"] == ""


def test_quote_sanitizer_drops_location_only_evidence_and_spans() -> None:
    quotes = discard_location_only_quotes(
        [
            {"text": "Retained quote", "evidence_id": "quote_001"},
            {"text": "Unbound quote", "evidence_id": "source:page:3"},
            {
                "text": "Supported quote",
                "evidence_id": "quote_002",
                "evidence_spans": [
                    {"evidence_id": "quote_002", "page": 2},
                    {"evidence_id": "source:page:3", "page": 3},
                ],
            },
        ]
    )

    assert [quote["text"] for quote in quotes] == ["Retained quote", "Supported quote"]
    assert quotes[1]["evidence_spans"] == [{"evidence_id": "quote_002", "page": 2}]


def test_insight_sanitizer_drops_location_only_evidence_and_spans() -> None:
    insights = discard_location_only_insights(
        [
            {"id": "retained", "text": "Retained", "evidence_id": "finding_001"},
            {"id": "unbound", "text": "Unbound", "evidence_id": "source:page:2"},
            {
                "id": "supported",
                "text": "Supported",
                "evidence_id": "finding_002",
                "evidence_spans": [
                    {"evidence_id": "finding_002", "page": 2},
                    {"evidence_id": "source:page:2", "page": 2},
                ],
            },
        ]
    )

    assert [insight["id"] for insight in insights] == ["retained", "supported"]
    assert insights[1]["evidence_spans"] == [{"evidence_id": "finding_002", "page": 2}]


def test_candidate_allows_a_unique_same_family_evidence_continuity_when_id_changes() -> (
    None
):
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id"

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert result.passed
    assert not any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_keeps_identifier_continuity_blocked_when_evidence_match_is_ambiguous() -> (
    None
):
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id-1"
    duplicate = deepcopy(candidate["insights_candidates"][0])
    duplicate["id"] = "normalized-candidate-id-2"
    candidate["insights_candidates"].append(duplicate)

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_keeps_identifier_continuity_blocked_without_source_pages() -> None:
    current, evidence_packs = _retained_artifact_and_evidence()
    candidate = deepcopy(current)
    original = current["insights_candidates"][0]
    original["pages"] = []
    original["evidence_spans"] = []
    candidate["insights_candidates"][0]["id"] = "normalized-candidate-id"
    candidate["insights_candidates"][0]["pages"] = []
    candidate["insights_candidates"][0]["evidence_spans"] = []

    result = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )

    assert not result.passed
    assert any(
        issue.entity_id == original["id"]
        and "lost the original material evidence" in issue.message
        for issue in result.issues
    )


def test_candidate_blocks_unsupported_more_than_doubled_language() -> None:
    artifacts, _ = _retained_artifact_and_evidence()
    insight = deepcopy(artifacts["insights_final"][0])
    insight["text"] = "The reported spending power more than doubled."

    issues = validate_insight_metrics(
        insights=[insight],
        evidence_map={insight["evidence_id"]: insight["evidence"]},
    )

    assert any(
        issue.severity == "error" and "more than doubled" in issue.message
        for issue in issues
    )


__all__ = [name for name in globals() if name.startswith("test_")]
