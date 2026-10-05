# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_report_regeneration_generator.py"
)

from ._split_support_test_report_regeneration_generator import *  # noqa: F401,F403


def test_summary_repair_rebuilds_key_figures_from_final_atomic_artifacts(tmp_path):
    current = _current_artifacts()
    evidence_packs = _evidence_packs()
    evidence_text = "Retail media adoption reached 42 percent among merchants."
    evidence_packs["findings"]["findings"][0] = {
        "id": "f1",
        "text": evidence_text,
        "evidence": evidence_text,
        "pages": [2],
    }
    current["insights_final"][0].update(
        {
            "text": evidence_text,
            "evidence": "Retail media adoption was reported at 42%.",
            "evidence_spans": [
                {
                    "evidence_id": "f1",
                    "source_pack": "findings",
                    "page": 2,
                    "text": evidence_text,
                }
            ],
            "pages": [2],
            "metric": {
                **METRIC,
                "label": "Retail media adoption",
                "value": "42",
                "unit": "percent",
                "confidence": "high",
                "segment": "merchants",
            },
        }
    )
    current["_cache"] = {
        "prompts": {},
        "producing_prompt_identities": {},
        "regeneration_prompt_requirements": {},
    }
    current["metric_spine"] = derive_metric_spine_from_insights(
        current["insights_final"],
        editorial_plan=current["editorial_plan"],
    )
    normalized_insight = deepcopy(current["insights_final"][0])
    normalized_insight["evidence"] = evidence_text
    normalized_insights = [normalized_insight, *current["insights_final"][1:]]
    current["key_figures"] = build_key_figures(
        metric_spine=current["metric_spine"],
        evidence_packs=evidence_packs,
        summary=current["summary"],
        insights_final=normalized_insights,
        editorial_plan=current["editorial_plan"],
    )
    current["chart_insight_cards"] = build_chart_insight_cards(
        key_figures=current["key_figures"],
        evidence_packs=evidence_packs,
        insights_final=normalized_insights,
    )
    assert [figure["figure"] for figure in current["key_figures"]] == ["42 percent"]
    plan = RegenerationPlan(
        mode="targeted",
        targets=[
            RegenerationTarget(
                target_section="summary",
                regenerate_steps=["summary"],
                prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
                issues=[
                    RegenerationIssue(
                        rule_id="grounding",
                        affected_section="summary.tldr",
                        message="Repair the unsupported summary sentence.",
                        severity="error",
                        evidence_ids=["f1"],
                    )
                ],
                repair_action="REGENERATE_ITEM",
                repair_strategy="current_evidence",
                allowed_paths=["summary.tldr[claim_index=0]"],
            )
        ],
        unmappable_issues=[],
        broad_retry_allowed=False,
    )

    response = _regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
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
    candidate = response.updated_artifacts

    assert candidate["insights_final"][0]["evidence"] == (
        "Retail media adoption was reported at 42%."
    )
    assert candidate["key_figures"] == []
    assert candidate["chart_insight_cards"] == []
    integrity = validate_regeneration_candidate(
        current_artifacts=current,
        candidate_artifacts=candidate,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
        planned_prompt_namespaces=("report_vs/artifacts/regenerate/summary",),
        actual_prompt_namespaces=tuple(response.prompt_namespaces),
    )
    assert not any(
        issue.rule_id == "regeneration_derived_projection"
        and issue.affected_section in {"key_figures", "chart_insight_cards"}
        for issue in integrity.issues
    )
    assert {"key_figures", "chart_insight_cards"} <= integrity.verified_derived_roots
    projection_scope = _scope_validation_report(
        before={
            root: current[root]
            for root in (
                "summary",
                "metric_spine",
                "key_figures",
                "chart_insight_cards",
            )
        },
        after={
            root: candidate[root]
            for root in (
                "summary",
                "metric_spine",
                "key_figures",
                "chart_insight_cards",
            )
        },
        plan=plan,
        verified_derived_roots=integrity.verified_derived_roots,
    )
    assert projection_scope.status == "pass"


def test_summary_claim_map_repair_changes_only_the_identified_claim(tmp_path):
    class _ClaimMapOpenAIClient(_FakeOpenAIClient):
        def _legacy_chat_json(self, req, ctx):
            del ctx
            self.calls.append(req)
            assert "claim_map_item" in req.user_prompt
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(
                    {
                        "summary": {
                            "claim_evidence_map": [
                                {
                                    "id": "claim-one",
                                    "claim": "Corrected retained claim.",
                                    "evidence_id": "untrusted-change",
                                },
                                {
                                    "id": "claim-two",
                                    "claim": "Altered sibling claim.",
                                },
                            ]
                        }
                    }
                ),
                parsed_json={
                    "summary": {
                        "claim_evidence_map": [
                            {
                                "id": "claim-one",
                                "claim": "Corrected retained claim.",
                                "evidence_id": "untrusted-change",
                            },
                            {
                                "id": "claim-two",
                                "claim": "Altered sibling claim.",
                            },
                        ]
                    }
                },
                request_id="req-claim-map-atomic",
            )

    artifacts = _current_artifacts()
    artifacts["summary"]["claim_evidence_map"] = [
        {
            "id": "claim-one",
            "claim": "Unsupported original claim.",
            "evidence_id": "f1",
            "evidence": "Evidence text",
            "pages": [1],
        },
        {
            "id": "claim-two",
            "claim": "Untouched sibling claim.",
            "evidence_id": "f2",
            "evidence": "Evidence text 2",
            "pages": [2],
        },
    ]
    before_claims = deepcopy(artifacts["summary"]["claim_evidence_map"])
    before_executive_summary = artifacts["summary"]["executive_summary"]
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                rule_id="retained_claim.number_value_unit_match",
                affected_section="summary.claim_evidence_map:claim-one.claim",
                message="[retained_claim.number_value_unit_match] repair claim",
                severity="error",
                entity_id="summary_claim:claim-one",
                evidence_ids=["f1"],
            )
        ],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    assert plan.targets[0].allowed_paths == [
        "summary.claim_evidence_map[item=claim-one].claim"
    ]
    openai_client = _ClaimMapOpenAIClient()

    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    claims = response.updated_artifacts["summary"]["claim_evidence_map"]
    assert len(openai_client.calls) == 1
    request_variables = json.loads(openai_client.calls[0].user_prompt.split("|", 1)[1])
    claim_scope = json.loads(request_variables["claim_repair_scope_json"])
    repair_context = json.loads(request_variables["repair_context_json"])
    assert claim_scope["claim_id"] == "claim-one"
    assert repair_context["allowed_paths"] == [
        "summary.claim_evidence_map[item=claim-one].claim"
    ]
    assert (
        len(json.loads(request_variables["current_section_json"])["claim_evidence_map"])
        == 1
    )
    assert claims[0]["claim"] == "Corrected retained claim."
    assert claims[0]["evidence_id"] == before_claims[0]["evidence_id"]
    assert claims[1] == before_claims[1]
    assert response.updated_artifacts["summary"]["executive_summary"] == (
        before_executive_summary
    )
    assert response.repair_decisions[0].changed_paths == [
        "summary.claim_evidence_map[item=claim-one].claim"
    ]


def test_summary_claim_map_repair_resolves_idless_claim_by_stable_index(tmp_path):
    original_claims = [
        {
            "claim": "Supported sibling claim.",
            "evidence_id": "f1",
            "evidence": "Evidence text 1",
            "pages": [1],
        },
        {
            "claim": "Unsupported target claim.",
            "evidence_id": "f2",
            "evidence": "Evidence text 2",
            "pages": [2],
        },
    ]

    class _IdlessClaimMapOpenAIClient(_FakeOpenAIClient):
        def _legacy_chat_json(self, req, ctx):
            del ctx
            self.calls.append(req)
            variables = _parse_fixture_variables(req.user_prompt)
            assert variables is not None
            claim_scope = json.loads(variables["claim_repair_scope_json"])
            repair_context = json.loads(variables["repair_context_json"])
            assert claim_scope["claim_id"] == "2"
            assert repair_context["allowed_paths"] == [
                "summary.claim_evidence_map[1].claim"
            ]
            repaired_claims = deepcopy(original_claims)
            repaired_claims[1]["claim"] = "Corrected supported target claim."
            payload = {
                "summary": {"claim_evidence_map": repaired_claims},
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="req-idless-claim-map-target",
            )

    artifacts = _current_artifacts()
    artifacts["summary"]["claim_evidence_map"] = deepcopy(original_claims)
    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                rule_id="grounding",
                affected_section="summary.claim_evidence_map:2.claim",
                message="[grounding] Unsupported summary claim",
                severity="error",
                entity_id="summary_claim:2",
                evidence_ids=["f2"],
            )
        ],
        artifacts=artifacts,
        broad_retry_available=False,
    )
    assert plan.targets[0].allowed_paths == ["summary.claim_evidence_map[1].claim"]

    openai_client = _IdlessClaimMapOpenAIClient()
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=plan,
            current_artifacts=artifacts,
            doc_map=_evidence_packs()["doc_map"],
            evidence_packs=_evidence_packs(),
            settings=_settings(tmp_path),
            ctx=_ctx(),
            source_status=artifacts["source_status"],
            categories=["Category"],
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=openai_client,
        prompt_client=_FakePromptClient(),
    )

    repaired_claims = response.updated_artifacts["summary"]["claim_evidence_map"]
    assert len(openai_client.calls) == 1
    assert repaired_claims[0] == original_claims[0]
    assert repaired_claims[1]["claim"] == "Corrected supported target claim."
    assert response.repair_decisions[0].changed_paths == [
        "summary.claim_evidence_map[1].claim"
    ]


@pytest.mark.parametrize("shared_evidence_binding", [False, True])
def test_summary_copy_removal_retires_only_uniquely_bound_claim_map_row(
    tmp_path, shared_evidence_binding: bool
):
    artifacts = _current_artifacts()
    summary_sentences = [
        ("tldr", "A supported lead claim.", "f1"),
        ("card_tldr_compact", "A supported compact claim.", "f2"),
        (
            "executive_summary",
            "A retained executive claim.",
            "f4" if shared_evidence_binding else "f3",
        ),
        ("executive_summary", "An unsupported forecast claim.", "f4"),
    ]
    artifacts["summary"]["tldr"] = summary_sentences[0][1]
    artifacts["summary"]["card_tldr_compact"] = summary_sentences[1][1]
    artifacts["summary"]["executive_summary"] = " ".join(
        sentence for family, sentence, _evidence_id in summary_sentences
        if family == "executive_summary"
    )
    artifacts["summary"]["claim_evidence_map"] = [
        {
            "claim": sentence,
            "evidence_id": evidence_id,
            "evidence": f"Evidence for {evidence_id}",
            "pages": [index],
        }
        for index, (_family, sentence, evidence_id) in enumerate(
            summary_sentences, start=1
        )
    ]
    summary_claims = [
        SoftCopyClaimProvenance(
            schema_version="1.0",
            artifact_family="summary",
            claim_id=(
                "soft_copy:summary:"
                f"{hashlib.sha256(sentence.encode()).hexdigest()[:16]}"
            ),
            text_hash=hashlib.sha256(sentence.encode()).hexdigest(),
            classification="factual",
            evidence_ids=(evidence_id,),
            source_spans=(),
            producing_prompt_identity={"namespace": "report_vs/artifacts/summary"},
            generation_attempt=1,
            regeneration_attempt=0,
        )
        for _family, sentence, evidence_id in summary_sentences
    ]
    other_claims = [
        claim
        for claim in soft_copy_claim_provenance_from_payload(
            artifacts["soft_copy_claim_provenance"]
        )
        if claim.artifact_family != "summary"
    ]
    artifacts["soft_copy_claim_provenance"] = soft_copy_claim_provenance_to_payload(
        [*other_claims, *summary_claims]
    )
    failed_claim = summary_claims[-1]

    class _RemoveSummarySentenceClient:
        def openai_chat_json(self, req, ctx):
            del ctx
            variables = _parse_fixture_variables(req.user_prompt)
            assert variables is not None
            repair_context = json.loads(variables["repair_context_json"])
            path = "summary.executive_summary[claim_index=1]"
            assert repair_context["allowed_paths"] == [path]
            payload = {
                "repair_decision": {
                    "schema_version": "1.0",
                    "repair_action": repair_context["repair_action"],
                    "repair_strategy": repair_context["repair_strategy"],
                    "evidence_ids_used": [],
                    "changed_paths": [path],
                    "minimal_patch": [
                        {"op": "replace", "path": path, "value": ""}
                    ],
                }
            }
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="req-remove-summary-copy-claim",
            )

    target = RegenerationTarget(
        target_section="summary",
        regenerate_steps=["summary"],
        prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=["summary.executive_summary[claim_index=1]"],
        issues=[
            RegenerationIssue(
                rule_id="grounding",
                affected_section="summary.executive_summary",
                message="The retained forecast claim is unsupported.",
                severity="error",
                entity_id=failed_claim.claim_id,
                evidence_ids=["f4"],
            )
        ],
    )
    evidence_packs = _evidence_packs()
    evidence_packs["findings"]["findings"].extend(
        {"id": evidence_id, "evidence": sentence, "text": sentence}
        for _family, sentence, evidence_id in summary_sentences[2:]
    )
    response = regenerate_artifacts(
        ArtifactRegenerationRequest(
            report_id="report-1",
            report_name="report-1",
            attempt_index=1,
            plan=RegenerationPlan(
                mode="targeted",
                targets=[target],
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
            vector_store_id=None,
            md5="md5",
        ),
        openai_client=_RemoveSummarySentenceClient(),
        prompt_client=_FakePromptClient(),
    )

    repaired_summary = response.updated_artifacts["summary"]
    assert repaired_summary["executive_summary"] == "A retained executive claim."
    assert failed_claim.claim_id not in {
        claim["claim_id"]
        for claim in response.updated_artifacts["soft_copy_claim_provenance"]["claims"]
    }
    expected_map = (
        summary_sentences
        if shared_evidence_binding
        else summary_sentences[:-1]
    )
    assert [item["claim"] for item in repaired_summary["claim_evidence_map"]] == [
        sentence for _family, sentence, _evidence_id in expected_map
    ]


def test_summary_claim_map_issue_uses_map_path_before_soft_copy_provenance_path():
    artifacts = _current_artifacts()
    artifacts["summary"]["executive_summary"] = (
        "Summary sentence one. Summary sentence two. Summary sentence three. "
        "Summary sentence four. Old summary"
    )
    artifacts["summary"]["claim_evidence_map"] = [
        {"claim": f"Claim {index}.", "evidence_id": f"f{index}"}
        for index in range(1, 6)
    ]
    soft_copy_claim_id = next(
        claim.claim_id
        for claim in soft_copy_claim_provenance_from_payload(
            artifacts["soft_copy_claim_provenance"]
        )
        if claim.artifact_family == "summary"
        and claim.text_hash == hashlib.sha256("Old summary".encode()).hexdigest()
    )

    plan = _build_regeneration_plan(
        issues=[
            ValidationIssue(
                rule_id="retained_claim.number_value_unit_match",
                affected_section="summary.claim_evidence_map:5.claim",
                message="[retained_claim.number_value_unit_match] repair claim",
                severity="error",
                entity_id=soft_copy_claim_id,
                evidence_ids=["f5"],
            )
        ],
        artifacts=artifacts,
        broad_retry_available=False,
    )

    assert plan.targets[0].allowed_paths == ["summary.claim_evidence_map[4].claim"]


def test_summary_claim_map_repair_rejects_model_patches_to_public_copy_siblings(
    tmp_path,
) -> None:
    class _OverbroadSummaryOpenAIClient:
        def __init__(self) -> None:
            self.calls = []

        def openai_chat_json(self, req, ctx):
            del ctx
            self.calls.append(req)
            variables = _parse_fixture_variables(req.user_prompt)
            assert variables is not None
            repair_context = json.loads(variables["repair_context_json"])
            assert repair_context["allowed_paths"] == [
                "summary.claim_evidence_map[item=claim-one].claim"
            ]
            unauthorized_path = "summary.executive_summary[claim_index=0]"
            path = repair_context["allowed_paths"][0]
            decision = {
                "schema_version": "1.0",
                "repair_action": repair_context["repair_action"],
                "repair_strategy": repair_context["repair_strategy"],
                "evidence_ids_used": ["f1"],
                "changed_paths": [path, unauthorized_path],
                "minimal_patch": [
                    {
                        "op": "replace",
                        "path": path,
                        "value": "Corrected retained claim.",
                    },
                    {
                        "op": "replace",
                        "path": unauthorized_path,
                        "value": "Rewritten sibling summary claim.",
                    },
                ],
            }
            payload = {"repair_decision": decision}
            return OpenAIResponseResult(
                schema_version="1.0",
                text=json.dumps(payload),
                parsed_json=payload,
                request_id="req-summary-overbroad-patch",
            )

    artifacts = _current_artifacts()
    artifacts["summary"]["claim_evidence_map"] = [
        {
            "id": "claim-one",
            "claim": "Unsupported original claim.",
            "evidence_id": "f1",
            "evidence": "Evidence text",
            "pages": [1],
        },
        {
            "id": "claim-two",
            "claim": "Untouched sibling claim.",
            "evidence_id": "f2",
            "evidence": "Evidence text 2",
            "pages": [2],
        },
    ]
    target = RegenerationTarget(
        target_section="summary",
        regenerate_steps=["summary"],
        prompt_namespaces=["report_vs/artifacts/regenerate/summary"],
        issues=[
            RegenerationIssue(
                rule_id="retained_claim.number_value_unit_match",
                affected_section="summary.claim_evidence_map:claim-one.claim",
                message="[retained_claim.number_value_unit_match] repair claim",
                severity="error",
                entity_id="summary_claim:claim-one",
                evidence_ids=["f1"],
            )
        ],
        repair_action="REGENERATE_ITEM",
        repair_strategy="current_evidence",
        allowed_paths=["summary.claim_evidence_map[item=claim-one].claim"],
    )
    openai_client = _OverbroadSummaryOpenAIClient()

    with pytest.raises(AppError) as error:
        regenerate_artifacts(
            ArtifactRegenerationRequest(
                report_id="report-1",
                report_name="report-1",
                attempt_index=1,
                plan=RegenerationPlan(
                    mode="targeted",
                    targets=[target],
                    unmappable_issues=[],
                    broad_retry_allowed=False,
                ),
                current_artifacts=artifacts,
                doc_map=_evidence_packs()["doc_map"],
                evidence_packs=_evidence_packs(),
                settings=_settings(tmp_path),
                ctx=_ctx(),
                source_status=artifacts["source_status"],
                categories=["Category"],
            ),
            openai_client=openai_client,
            prompt_client=_FakePromptClient(),
        )

    assert error.value.context["reason"] == "changed_path_outside_allowed_paths"
    assert len(openai_client.calls) == 1


def test_regeneration_repairs_a_source_proven_lost_quarterly_comparison(tmp_path):
    source = "Share fell from 43% in Q1 2025 to 41% in Q2 2025."
    current_artifacts = _current_artifacts()
    current_artifacts["summary"].update(
        {
            "tldr": "Share fell from 43% in 2025 to 41% in 2025.",
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
    assert response.repair_decisions[0].minimal_patch[0].value == source
    assert response.updated_artifacts["summary"]["tldr"] == source
    assert response.updated_artifacts["summary"]["executive_summary"] == "Old summary"
    assert response.updated_artifacts["summary"]["card_tldr_compact"] == "Old TLDR."
    assert not any(
        issue.rule_id == "public_editorial_quality.temporal_integrity"
        for issue in evaluate_public_editorial_quality(
            report_id="activate-2026", artifacts=response.updated_artifacts
        ).issues
    )


def test_quote_leaf_repair_preserves_metadata_and_candidate_rejects_unsupported_text(
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
    original_quote = _current_artifacts()["quotes_final"][0]
    repaired_quote = response.updated_artifacts["quotes_final"][0]
    assert repaired_quote["text"] == "A paraphrased section summary"
    assert {key: value for key, value in repaired_quote.items() if key != "text"} == {
        key: value for key, value in original_quote.items() if key != "text"
    }
    assert response.repair_decisions[0].changed_paths == ["quotes_final[0].text"]

    candidate_result = validate_regeneration_candidate(
        current_artifacts=_current_artifacts(),
        candidate_artifacts=response.updated_artifacts,
        evidence_packs=evidence_packs,
        ctx=_ctx(),
        planned_prompt_namespaces=("report_vs/artifacts/regenerate/quotes",),
        actual_prompt_namespaces=tuple(response.prompt_namespaces),
    )
    issue = next(
        issue
        for issue in candidate_result.issues
        if issue.rule_id == "retained_claim.evidence_reference_completeness"
        and issue.affected_section.startswith("quotes:")
    )
    expected_quote_id = normalize_artifact_quotes([repaired_quote])[0]["id"]
    assert issue.affected_section == f"quotes:{expected_quote_id}.text"
