# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


def test_safe_removal_of_idless_summary_claim_preserves_exact_siblings(
    tmp_path,
) -> None:
    current = _current_artifacts()
    original_claims = [
        {
            "claim": "First retained map claim.",
            "evidence_id": "f1",
            "evidence": "Evidence text",
            "pages": [1],
        },
        {
            "claim": "Second retained map claim.",
            "evidence_id": "f2",
            "evidence": "Evidence text 2",
            "pages": [2],
        },
        {
            "claim": "Unsupported final map claim.",
            "evidence_id": "f1",
            "evidence": "Evidence text",
            "pages": [1],
        },
    ]
    current["summary"]["claim_evidence_map"] = deepcopy(original_claims)
    issue = RegenerationIssue(
        rule_id="grounding",
        affected_section="summary.claim_evidence_map:3.claim",
        message="The claim is not supported by its retained evidence.",
        severity="error",
        entity_id="summary_claim:3",
        evidence_ids=["f1"],
    )
    allowed_paths = _allowed_paths("summary", [issue], current, "REMOVE_CLAIM")
    target = RegenerationTarget(
        target_section="summary",
        repair_action="REMOVE_CLAIM",
        repair_strategy="safe_removal",
        issues=[issue],
        allowed_paths=allowed_paths,
    )
    plan = RegenerationPlan(
        mode="targeted",
        targets=[target],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )
    evidence_packs = _evidence_packs()
    openai_client = _FakeOpenAIClient()

    response = _regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=3,
            plan=plan,
            current_artifacts=current,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert (
        response.updated_artifacts["summary"]["claim_evidence_map"]
        == (original_claims[:2])
    )
    assert all(
        isinstance(item.get("claim"), str)
        for item in response.updated_artifacts["summary"]["claim_evidence_map"]
    )
    assert openai_client.calls == []
    integrity = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=response.updated_artifacts,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    scope = _scope_validation_report(
        before=current,
        after=response.updated_artifacts,
        plan=plan,
        verified_derived_roots=integrity.verified_derived_roots,
    )
    assert scope.status == "pass", [
        (item.rule_id, item.affected_section) for item in scope.issues
    ]
    assert Path(response.candidate_artifacts_path).is_file()


def test_summary_safe_removal_resolves_numeric_stable_claim_id() -> None:
    summary = {
        "claim_evidence_map": [
            {"id": "123", "claim": "Selected claim."},
            {"id": "456", "claim": "Sibling claim."},
        ]
    }

    assert (
        _summary_claim_map_item_index(
            original_family=summary,
            full_path="summary.claim_evidence_map[item=123]",
        )
        == 0
    )


def test_summary_safe_removal_replaces_only_the_target_with_retained_claim(
    tmp_path,
) -> None:
    current = _current_artifacts()
    current["summary"]["tldr"] = "Unsupported single sentence."
    current["summary"]["card_tldr_compact"] = "Keep compact summary."
    current["summary"]["executive_summary"] = (
        "Supported retained claim. Keep executive summary."
    )
    current["summary"]["claim_evidence_map"] = [
        {
            "claim": "Supported retained claim.",
            "evidence_id": "f1",
            "evidence": "Evidence text",
            "pages": [1],
        }
    ]
    evidence_packs = _evidence_packs()
    evidence_packs["doc_map"]["sections"] = [
        {
            "id": "f1",
            "title": "Retained evidence",
            "summary": "Supported retained claim.",
            "pages": [1],
        }
    ]
    evidence_packs["findings"]["findings"] = [
        {
            "id": "f1",
            "text": "Supported retained claim.",
            "evidence": "Evidence text",
            "pages": [1],
        }
    ]
    summary_claims = build_soft_copy_claim_provenance(
        artifact_family="summary",
        text=soft_copy_public_text("summary", current["summary"]),
        declared_claims=[
            {
                "claim": sentence,
                "classification": "factual",
                "evidence_ids": ["f1"],
            }
            for sentence in (
                "Unsupported single sentence.",
                "Keep compact summary.",
                "Supported retained claim.",
                "Keep executive summary.",
            )
        ],
        evidence_span_index=artifact_evidence_span_index(
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
        ),
        producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    non_summary_claims = [
        claim
        for claim in soft_copy_claim_provenance_from_payload(
            current["soft_copy_claim_provenance"]
        )
        if claim.artifact_family != "summary"
    ]
    current["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [*non_summary_claims, *summary_claims]
    )
    unsupported_claim_hash = hashlib.sha256(b"Unsupported single sentence.").hexdigest()
    target = RegenerationTarget(
        target_section="summary",
        repair_action="REMOVE_CLAIM",
        repair_strategy="safe_removal",
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="summary.tldr",
                message="The single sentence is unsupported.",
                severity="error",
                repair_target="summary",
                entity_id=f"soft_copy:summary:{unsupported_claim_hash[:16]}",
            )
        ],
        allowed_paths=["summary.tldr[claim_index=0]"],
    )
    plan = RegenerationPlan(
        mode="targeted",
        targets=[target],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )

    response = _regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=3,
            plan=plan,
            current_artifacts=current,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )

    summary = response.updated_artifacts["summary"]
    assert summary["tldr"] == "Supported retained claim."
    assert summary["card_tldr_compact"] == "Keep compact summary."
    assert summary["executive_summary"] == (
        "Supported retained claim. Keep executive summary."
    )
    assert summary["claim_evidence_map"][0]["claim"] == "Supported retained claim."
    assert summary["claim_evidence_map"][0]["evidence_id"] == "f1"


@pytest.mark.parametrize("map_text_matches_copy", [True, False])
@pytest.mark.parametrize("copy_has_sibling", [True, False])
def test_summary_safe_removal_combines_map_and_copy_issues_with_stale_provenance(
    tmp_path, map_text_matches_copy: bool, copy_has_sibling: bool
) -> None:
    current = _current_artifacts()
    current["summary"]["executive_summary"] = "Unsupported ledger-linked copy."
    if copy_has_sibling:
        current["summary"]["executive_summary"] += " Keep executive copy."
    current["summary"]["claim_evidence_map"] = [
        {
            "claim": (
                "Unsupported ledger-linked copy."
                if map_text_matches_copy
                else "Different claim text."
            ),
            "evidence_id": "f1",
            "evidence": "Evidence text",
            "pages": [1],
        }
    ]
    if copy_has_sibling:
        current["summary"]["claim_evidence_map"].append(
            {
                "claim": "Keep executive copy.",
                "evidence_id": "f2",
                "evidence": "Evidence text 2",
                "pages": [2],
            }
        )
    evidence_packs = _evidence_packs()
    evidence_span_index = artifact_evidence_span_index(
        doc_map=evidence_packs["doc_map"],
        evidence_packs=evidence_packs,
    )
    summary_text = soft_copy_public_text("summary", current["summary"])
    summary_sentences = soft_copy_material_sentences(summary_text)
    summary_claims = build_soft_copy_claim_provenance(
        artifact_family="summary",
        text=summary_text,
        declared_claims=[
            {
                "claim": sentence,
                "classification": "factual",
                "evidence_ids": ["f1"],
            }
            for sentence in summary_sentences
        ],
        evidence_span_index=evidence_span_index,
        producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
        generation_attempt=1,
        regeneration_attempt=0,
    )
    target_text = "Unsupported ledger-linked copy."
    target_hash = hashlib.sha256(target_text.encode("utf-8")).hexdigest()
    stale_text_hash = hashlib.sha256(b"Stale prior summary sentence.").hexdigest()
    target_claim = next(
        claim for claim in summary_claims if claim.text_hash == target_hash
    )
    stale_claim = replace(
        target_claim,
        claim_id=f"soft_copy:summary:{stale_text_hash[:16]}",
        text_hash=stale_text_hash,
    )
    other_claims = [
        claim
        for claim in soft_copy_claim_provenance_from_payload(
            current["soft_copy_claim_provenance"]
        )
        if claim.artifact_family != "summary"
    ]
    current["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [
            *other_claims,
            *[
                stale_claim if claim.claim_id == target_claim.claim_id else claim
                for claim in summary_claims
            ],
        ]
    )
    target = RegenerationTarget(
        target_section="summary",
        repair_action="REMOVE_CLAIM",
        repair_strategy="safe_removal",
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="summary.executive_summary",
                message=f"Unsupported copy: {target_text}",
                severity="error",
                entity_id=stale_claim.claim_id,
            ),
            RegenerationIssue(
                rule_id="grounding",
                affected_section="summary.claim_evidence_map:1.claim",
                message=f"Unsupported map claim: {target_text}",
                severity="error",
                entity_id=stale_claim.claim_id,
            ),
        ],
        allowed_paths=[
            "summary.executive_summary[claim_index=0]",
            "summary.claim_evidence_map[0].claim",
        ],
    )
    openai_client = _FakeOpenAIClient()

    request = ArtifactRegenerationRequest(
        report_id="report-1",
        report_name="report-1",
        attempt_index=3,
        plan=RegenerationPlan(
            mode="targeted",
            targets=[target],
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
        vector_store_id=None,
        md5="md5",
    )
    if not map_text_matches_copy:
        with pytest.raises(AppError) as error:
            _regenerate_artifacts(
                request,
                openai_client=openai_client,
                prompt_client=_FakePromptClient(),
            )
        assert error.value.code == "summary_safe_removal_target_unresolved"
        assert openai_client.calls == []
        return

    response = _regenerate_artifacts(
        request,
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    summary = response.updated_artifacts["summary"]
    assert summary["tldr"] == current["summary"]["tldr"]
    assert summary["executive_summary"] == (
        "Keep executive copy." if copy_has_sibling else ""
    )
    assert summary["claim_evidence_map"] == (
        [current["summary"]["claim_evidence_map"][1]] if copy_has_sibling else []
    )
    assert openai_client.calls == []
    assert not any(
        claim["claim_id"] == stale_claim.claim_id
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    )
    assert_retained_soft_copy_claims_match_public_copy(response.updated_artifacts)


@pytest.mark.parametrize("has_claim_specific_issue", [True, False])
def test_summary_safe_removal_requires_claim_identity_for_family_quality_issue(
    tmp_path, has_claim_specific_issue: bool
) -> None:
    current = _current_artifacts()
    evidence_packs = _evidence_packs()
    claims = soft_copy_claim_provenance_from_payload(
        current["soft_copy_claim_provenance"]
    )
    failed_claim = next(
        claim
        for claim in claims
        if claim.artifact_family == "summary"
        and claim.text_hash == hashlib.sha256(b"Old summary").hexdigest()
    )
    issues = [
        RegenerationIssue(
            rule_id="artifact_quality",
            affected_section="summary.executive_summary",
            message="The executive summary needs quality review.",
            severity="warning",
            entity_id="summary.executive_summary",
        )
    ]
    if has_claim_specific_issue:
        issues.append(
            RegenerationIssue(
                rule_id="grounding",
                affected_section="executive_summary",
                message="A specific executive-summary claim is unsupported.",
                severity="warning",
                entity_id=failed_claim.claim_id,
            )
        )
    target = RegenerationTarget(
        target_section="summary",
        repair_action="REMOVE_CLAIM",
        repair_strategy="safe_removal",
        issues=issues,
        allowed_paths=["summary.executive_summary[claim_index=0]"],
    )
    openai_client = _FakeOpenAIClient()

    request = ArtifactRegenerationRequest(
        report_id="report-1",
        report_name="report-1",
        attempt_index=3,
        plan=RegenerationPlan(
            mode="targeted",
            targets=[target],
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
        vector_store_id=None,
        md5="md5",
    )
    if not has_claim_specific_issue:
        with pytest.raises(AppError) as error:
            _regenerate_artifacts(
                request,
                openai_client=openai_client,
                prompt_client=_FakePromptClient(),
            )
        assert error.value.code == "summary_safe_removal_target_unresolved"
        assert openai_client.calls == []
        return

    response = _regenerate_artifacts(
        request,
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    assert response.updated_artifacts["summary"]["executive_summary"] == ""
    assert response.updated_artifacts["summary"]["tldr"] == current["summary"]["tldr"]
    assert (
        response.updated_artifacts["summary"]["claim_evidence_map"]
        == current["summary"]["claim_evidence_map"]
    )
    assert not any(
        claim["claim_id"] == failed_claim.claim_id
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    )
    assert openai_client.calls == []
    assert_retained_soft_copy_claims_match_public_copy(response.updated_artifacts)


def test_summary_safe_removal_without_retained_replacement_fails_typed(tmp_path):
    current = _current_artifacts()
    current["summary"]["tldr"] = "Unsupported only sentence."
    claim_hash = hashlib.sha256(b"Unsupported only sentence.").hexdigest()
    old_claims = soft_copy_claim_provenance_from_payload(
        current["soft_copy_claim_provenance"]
    )
    unsupported_claim = replace(
        next(claim for claim in old_claims if claim.artifact_family == "summary"),
        claim_id=f"soft_copy:summary:{claim_hash[:16]}",
        text_hash=claim_hash,
    )
    current["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [
            claim
            for claim in old_claims
            if not (
                claim.artifact_family == "summary"
                and claim.text_hash == hashlib.sha256(b"Old TLDR.").hexdigest()
            )
        ]
        + [unsupported_claim]
    )
    plan = RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="summary",
                repair_action="REMOVE_CLAIM",
                repair_strategy="safe_removal",
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="summary.tldr",
                        message="The only TLDR sentence is unsupported.",
                        severity="error",
                        entity_id=f"soft_copy:summary:{claim_hash[:16]}",
                    )
                ],
                allowed_paths=["summary.tldr[claim_index=0]"],
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )

    with pytest.raises(AppError) as error:
        _regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=3,
                plan=plan,
                current_artifacts=current,
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=current["source_status"],
                categories=["Category"],
                vector_store_id=None,
                md5="md5",
            ),
            openai_client=_FakeOpenAIClient(),
            prompt_client=_FakePromptClient(),
        )

    assert error.value.code == "summary_safe_removal_no_supported_replacement"


def test_summary_safe_removal_reuses_other_retained_supported_sentences(tmp_path):
    current = _current_artifacts()
    failed_tldr = "Unsupported broad summary claim."
    failed_compact = "Unsupported compact summary claim."
    supported_tldr = "A retained source finding changed during the measured period."
    supported_compact = "Another retained finding describes buyer priorities."
    current["summary"].update(
        {
            "tldr": failed_tldr,
            "card_tldr_compact": failed_compact,
            "executive_summary": f"{supported_tldr} {supported_compact}",
            "claim_evidence_map": [
                {
                    "claim": failed_tldr,
                    "evidence_id": "f1",
                    "evidence": "Evidence text",
                    "pages": [1],
                },
                {
                    "claim": failed_compact,
                    "evidence_id": "f2",
                    "evidence": "Evidence text 2",
                    "pages": [2],
                },
            ],
        }
    )
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].extend(
        [
            {"id": "f3", "evidence": "Evidence text 3", "pages": [3]},
            {"id": "f4", "evidence": "Evidence text 4", "pages": [4]},
        ]
    )
    span_index = artifact_evidence_span_index(
        doc_map=evidence_packs["doc_map"], evidence_packs=evidence_packs
    )

    def provenance(text: str, evidence_id: str) -> SoftCopyClaimProvenance:
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="summary",
            claim_id=f"soft_copy:summary:{text_hash[:16]}",
            text_hash=text_hash,
            classification="factual",
            evidence_ids=(evidence_id,),
            source_spans=tuple(
                dict(span) for span in span_index[evidence_id.casefold()]
            ),
            producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
            generation_attempt=1,
            regeneration_attempt=0,
        )

    retained = soft_copy_claim_provenance_from_payload(
        current["soft_copy_claim_provenance"]
    )
    retained = [claim for claim in retained if claim.artifact_family != "summary"]
    retained.extend(
        [
            provenance(failed_tldr, "f1"),
            provenance(failed_compact, "f2"),
            provenance(supported_tldr, "f3"),
            provenance(supported_compact, "f4"),
        ]
    )
    current["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        retained
    )
    issues = [
        RegenerationIssue(
            rule_id="grounding",
            affected_section="summary.tldr",
            message="The TLDR claim is unsupported.",
            severity="error",
            entity_id=provenance(failed_tldr, "f1").claim_id,
        ),
        RegenerationIssue(
            rule_id="grounding",
            affected_section="summary.card_tldr_compact",
            message="The compact TLDR claim is unsupported.",
            severity="error",
            entity_id=provenance(failed_compact, "f2").claim_id,
        ),
    ]
    target = RegenerationTarget(
        target_section="summary",
        repair_action="REMOVE_CLAIM",
        repair_strategy="safe_removal",
        issues=issues,
        allowed_paths=[
            "summary.tldr[claim_index=0]",
            "summary.card_tldr_compact[claim_index=0]",
        ],
    )
    plan = RegenerationPlan(
        mode="targeted",
        targets=[target],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )
    openai_client = _FakeOpenAIClient()

    response = _regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=3,
            plan=plan,
            current_artifacts=current,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    summary = response.updated_artifacts["summary"]
    assert summary["tldr"] == supported_tldr
    assert summary["card_tldr_compact"] == supported_compact
    assert failed_tldr not in summary["tldr"]
    assert failed_compact not in summary["card_tldr_compact"]
    retained_ids = {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"][
            "claims"
        ]
    }
    assert provenance(failed_tldr, "f1").claim_id not in retained_ids
    assert provenance(failed_compact, "f2").claim_id not in retained_ids
    assert openai_client.calls == []
    assert_retained_soft_copy_claims_match_public_copy(response.updated_artifacts)


@pytest.mark.parametrize("attempt_index", [2, 3])
def test_later_no_prompt_repair_does_not_add_empty_prompt_requirements_to_cache(
    tmp_path,
    attempt_index: int,
) -> None:
    current = _current_artifacts()
    current["_cache"] = {
        "prompts": {},
        "producing_prompt_identities": {},
    }
    evidence_packs = _evidence_packs()
    plan = RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="linkedin_post",
                repair_action="REMOVE_CLAIM",
                repair_strategy="safe_removal",
                allowed_paths=["linkedin_post[claim_index=0]"],
                issues=[
                    RegenerationIssue(
                        rule_id="numbers",
                        affected_section="linkedin_post",
                        message="Unsupported numeric claim.",
                        severity="error",
                        entity_id=current["soft_copy_claim_provenance"]["claims"][-1][
                            "claim_id"
                        ],
                        evidence_ids=["f1"],
                    )
                ],
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )

    response = _regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=attempt_index,
            plan=plan,
            current_artifacts=current,
            doc_map=evidence_packs["doc_map"],
            evidence_packs=evidence_packs,
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=current["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=_FakeOpenAIClient(),
        prompt_client=_FakePromptClient(),
    )
    candidate = deepcopy(current)
    candidate["_cache"] = deepcopy(response.updated_artifacts["_cache"])
    assert "regeneration_prompt_requirements" not in candidate["_cache"]

    integrity = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
    )
    scope = _scope_validation_report(
        before=current,
        after=candidate,
        plan=plan,
        verified_derived_roots=integrity.verified_derived_roots,
    )
    assert scope.status == "pass", [
        (issue.rule_id, issue.affected_section) for issue in scope.issues
    ]
