# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.contracts.prompt_family_materialization import (
    PromptFamilyMaterializationRequest,
    PromptFamilyReuseResponse,
)
from src.services.prompt_family_materialization_service import materialize_prompt_family

from ._shared import *  # noqa: F401,F403


def test_artifact_cache_isolated_by_retrieval_mode(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic"]},
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "Support",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Candidate 1",
                    "evidence_id": "f1",
                    "evidence": "Support",
                    "metric": {},
                    "pages": [1],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "f1",
                    "text": "Final",
                    "evidence_id": "f1",
                    "evidence": "Support",
                    "metric": {},
                    "pages": [1],
                }
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Quote",
                    "speaker": "Analyst",
                    "citation": "",
                    "page": 1,
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Post"},
    }
    report_id = "cache_mode_report"
    report_name = "cache mode report"
    md5 = "md5-cache-mode"

    chat_settings = _settings(tmp_path, artifacts_use_vector_store=False)
    chat_openai = FakeOpenAI(responses)
    generate_artifacts(
        report_id=report_id,
        report_name=report_name,
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=chat_settings,
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=chat_openai,
        prompt_client=FakePromptClient(),
        md5=md5,
    )
    assert len(chat_openai.requests) == 8
    assert len([req for req in chat_openai.requests if req[0] == "chat"]) == 8

    vector_settings = _settings(tmp_path, artifacts_use_vector_store=True)
    vector_openai = FakeOpenAI(responses)
    vector_payload = generate_artifacts(
        report_id=report_id,
        report_name=report_name,
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=vector_settings,
        vector_store_id="vs_1",
        ctx=_ctx(),
        openai_client=vector_openai,
        prompt_client=FakePromptClient(),
        md5=md5,
    )
    assert len(vector_openai.requests) == 8
    assert len([req for req in vector_openai.requests if req[0] == "vector"]) == 8
    assert set(
        vector_payload["_cache"]["family_reuse_telemetry"][
            "regeneration_reasons"
        ].values()
    ) == {"vector_store_provenance_missing"}


def test_load_cached_artifacts_rejects_schema_invalid_payload(tmp_path):
    report_name = "artifact cache invalid"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "artifacts.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"_cache": {"key": "cache-key"}}),
        encoding="utf-8",
    )

    cached = _load_cached_artifacts(
        output_dir=str(tmp_path),
        report_id="artifact-cache-invalid",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is None


def test_load_cached_artifacts_rejects_v2_without_cover_semantics(
    tmp_path, caplog, assert_logs_have_required_fields
):
    caplog.set_level(logging.INFO, logger="market_lense.artifact_generator")
    report_name = "artifact cache v2 without cover semantics"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "artifacts.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "_cache": {"key": "cache-key"},
            }
        ),
        encoding="utf-8",
    )

    cached = _load_cached_artifacts(
        output_dir=str(tmp_path),
        report_id="artifact-cache-v2-without-cover-semantics",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is None
    invalid_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.artifact_generator"
        and json.loads(record.message).get("event") == "artifact_cache_invalid"
    ]
    assert len(invalid_events) == 1
    assert invalid_events[0]["fields"]["code"] == "cover_fingerprint_invalid"
    assert_logs_have_required_fields(invalid_events)


def test_load_cached_artifacts_refreshes_derived_family_status(tmp_path):
    report_name = "artifact cache status"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "artifacts.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "_cache": {"key": "cache-key"},
        "toc_entries": [],
        "toc_topics": [],
        "toc_topics_expanded": [],
        "editorial_plan": {
            "report_thesis": "Engagement changes planning.",
            "themes": [
                {"theme": "Engagement", "priority": 1, "evidence_ids": ["sec-07"]},
                {"theme": "Practice", "priority": 2, "evidence_ids": ["sec-07"]}
            ]
        },
        "summary": {
            "tldr": "Grounded TLDR.",
            "executive_summary": "Grounded executive summary.",
            "claim_evidence_map": [
                {
                    "claim": "Engagement drove measurable practice changes.",
                    "evidence_id": "sec-07",
                    "evidence": "The report says engagement led to tangible changes.",
                    "pages": [16],
                }
            ],
        },
        "cover_semantics": _cover_semantics(),
        "insights_candidates": [],
        "insights_final": [],
        "quotes_final": [],
        "expert_comment": "",
        "linkedin_post": "",
        "source_status": {"not_available": False, "reason": ""},
        "family_status": {
            "summary": {
                "schema_version": "1.0",
                "family": "summary",
                "source": "artifact",
                "status": "abstained",
                "confidence_score": 0.64,
                "policy_action": "regenerate",
                "reason": "summary_claim_span_missing",
            }
        },
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    cached = _load_cached_artifacts(
        output_dir=str(tmp_path),
        report_id="artifact-cache-status",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is not None
    assert cached["schema_version"] == "3.0"
    assert cached["summary"]["card_tldr_compact"] == "Grounded TLDR."
    assert cached["family_status"]["summary"]["status"] == "generated"


def test_load_cached_artifacts_rejects_legacy_tldr_that_cannot_be_compact(tmp_path):
    report_name = "artifact cache long legacy tldr"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "artifacts.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "_cache": {"key": "cache-key"},
        "toc_entries": [],
        "toc_topics": [],
        "toc_topics_expanded": [],
        "editorial_plan": {
            "report_thesis": "Forest-risk engagement changes planning.",
            "themes": [
                {"theme": "Forest risk", "priority": 1, "evidence_ids": ["sec-10"]},
                {"theme": "Engagement", "priority": 2, "evidence_ids": ["sec-10"]}
            ]
        },
        "summary": {
            "tldr": (
                "One two three four five six seven eight nine ten eleven twelve "
                "thirteen fourteen fifteen sixteen seventeen eighteen nineteen."
            ),
            "executive_summary": "Grounded executive summary.",
            "claim_evidence_map": [
                {
                    "claim": "Engagement drove measurable practice changes.",
                    "evidence_id": "sec-07",
                    "evidence": "The report says engagement led to tangible changes.",
                    "pages": [16],
                }
            ],
        },
        "cover_semantics": _cover_semantics(),
        "insights_candidates": [],
        "insights_final": [],
        "quotes_final": [],
        "expert_comment": "",
        "linkedin_post": "",
        "source_status": {"not_available": False, "reason": ""},
        "family_status": {},
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    cached = _load_cached_artifacts(
        output_dir=str(tmp_path),
        report_id="artifact-cache-long-tldr",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is None


def test_load_cached_artifacts_clears_doc_map_only_quotes_after_policy_refresh(
    tmp_path,
):
    report_name = "artifact cache unsupported quotes"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "artifacts.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "_cache": {"key": "cache-key"},
        "toc_entries": [],
        "toc_topics": [],
        "toc_topics_expanded": [],
        "editorial_plan": {
            "report_thesis": "Forest-risk engagement changes planning.",
            "themes": [
                {"theme": "Forest risk", "priority": 1, "evidence_ids": ["sec-10"]},
                {"theme": "Engagement", "priority": 2, "evidence_ids": ["sec-10"]}
            ]
        },
        "summary": {
            "tldr": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        },
        "cover_semantics": _cover_semantics(),
        "insights_candidates": [],
        "insights_final": [],
        "quotes_final": [
            {
                "text": "Expanded program includes forest-risk commodities.",
                "speaker": "Unknown",
                "citation": "Deforestation",
                "page": 40,
                "evidence_id": "sec-10",
                "evidence_spans": [
                    {
                        "evidence_id": "sec-10",
                        "source_pack": "doc_map",
                        "page": 40,
                        "text": "Describes the expanded forest-risk engagement program.",
                    }
                ],
            }
        ],
        "expert_comment": "",
        "linkedin_post": "",
        "source_status": {"not_available": False, "reason": ""},
        "family_status": {
            "quotes": {
                "schema_version": "1.0",
                "family": "quotes",
                "source": "artifact",
                "status": "generated",
                "confidence_score": 1.0,
                "policy_action": "keep",
                "reason": "",
            }
        },
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")

    cached = _load_cached_artifacts(
        output_dir=str(tmp_path),
        report_id="artifact-cache-unsupported-quotes",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is not None
    assert cached["quotes_final"] == []
    assert cached["family_status"]["quotes"]["status"] == "abstained"
    assert (
        cached["family_status"]["quotes"]["reason"] == "quotes_missing_verbatim_source"
    )


def test_generate_artifacts_with_auto_context_preserves_input_evidence(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic"]},
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "Support",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "c1",
                    "text": "Candidate 1",
                    "evidence_id": "f1",
                    "evidence": "Support",
                    "metric": {},
                    "pages": [1],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "f1",
                    "text": "Final",
                    "evidence_id": "f1",
                    "evidence": "Support",
                    "metric": {},
                    "pages": [1],
                }
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Quote",
                    "speaker": "Analyst",
                    "citation": "",
                    "page": 1,
                    "evidence_id": "q1",
                }
            ]
        },
        "expert_comment": {"expert_comment": "Comment"},
        "linkedin_post": {"linkedin_post": "Post"},
    }
    fake_openai = FakeOpenAI(responses)
    payload = generate_artifacts(
        report_id="auto_ctx",
        report_name="auto context report",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        vector_store_id=None,
        ctx=None,
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert payload["source_status"]["evidence_present"] is True
    assert payload["source_status"]["not_available"] is False
    assert len(fake_openai.requests) == 8


def test_compatible_retained_families_make_zero_model_calls(tmp_path) -> None:
    fresh_client = FakeOpenAI(
        {
            "summary": {
                "summary": {
                    "tldr": "Grounded TLDR.",
                    "card_tldr_compact": "Grounded TLDR.",
                    "executive_summary": "Executive summary.",
                    "claim_evidence_map": [],
                }
            },
            "insights_candidates": {"insights_candidates": []},
            "quotes": {"quotes_final": []},
            "insights_final": {"insights_final": []},
            "cover_semantics": _cover_semantics_response(),
            "expert_comment": {"expert_comment": "Grounded comment."},
            "linkedin_post": {"linkedin_post": "Grounded LinkedIn post."},
        },
        input_tokens=100,
        output_tokens=20,
    )
    first = generate_artifacts(
        report_id="family-reuse",
        report_name="Family Reuse",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        md5="family-reuse-md5",
        openai_client=fresh_client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    retained = {
        "report_vs/artifacts/editorial_plan": first["editorial_plan"],
        "report_vs/artifacts/summary": first["summary"],
        "report_vs/artifacts/insights_candidates": first["insights_candidates"],
        "report_vs/artifacts/quotes": first["quotes_final"],
        "report_vs/artifacts/insights_final": first["insights_final"],
        "report_vs/artifacts/cover_semantics": first["cover_semantics"],
        "report_vs/artifacts/expert_comment": first["expert_comment"],
        "report_vs/artifacts/linkedin_post": first["linkedin_post"],
    }

    def reuse_reader(request, _ctx):
        return PromptFamilyReuseResponse(
            schema_version="1.0",
            reusable=True,
            reason="reused",
            output_payload=retained[request.family_id],
            artifact_id="retained:" + request.family_id,
            output_hash="retained-hash",
        )

    replay_client = FakeOpenAI({})
    replay = generate_artifacts(
        report_id="family-reuse",
        report_name="Family Reuse",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        md5="family-reuse-md5",
        openai_client=replay_client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
        prompt_family_reuse_reader=reuse_reader,
    )

    assert replay_client.requests == [], {
        "telemetry": replay["_cache"]["family_reuse_telemetry"],
        "first": first["_cache"]["family_reuse"],
        "replay": replay["_cache"]["family_reuse"],
    }
    assert replay["summary"] == first["summary"]
    assert first["_cache"]["family_reuse_telemetry"] == {
        **first["_cache"]["family_reuse_telemetry"],
        "actual_model_calls": 8,
        "input_tokens": 800,
        "output_tokens": 160,
        "estimated_cost_usd": 0.00336,
    }
    assert replay["_cache"]["family_reuse_telemetry"] == {
        **replay["_cache"]["family_reuse_telemetry"],
        "actual_model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "model_calls_avoided": 8,
    }
    assert replay["_cache"]["family_reuse_telemetry"]["reused_families"] == sorted(
        retained
    )


def test_vector_store_identity_is_part_of_family_reuse_proof(tmp_path) -> None:
    retained = {
        "report_vs/artifacts/editorial_plan": _default_editorial_plan(),
        "report_vs/artifacts/summary": {
            "tldr": "Grounded TLDR.",
            "card_tldr_compact": "Grounded TLDR.",
            "executive_summary": "Executive summary.",
            "claim_evidence_map": [],
        },
        "report_vs/artifacts/insights_candidates": [],
        "report_vs/artifacts/quotes": [],
        "report_vs/artifacts/insights_final": [],
        "report_vs/artifacts/cover_semantics": _cover_semantics(),
        "report_vs/artifacts/expert_comment": "Grounded comment.",
        "report_vs/artifacts/linkedin_post": "Grounded LinkedIn post.",
    }
    summary_input_hashes = []

    def reuse_reader(request, _ctx):
        if request.family_id == "report_vs/artifacts/summary":
            summary_input_hashes.append(request.relevant_input_hash)
        return PromptFamilyReuseResponse(
            schema_version="1.0",
            reusable=True,
            reason="reused",
            output_payload=retained[request.family_id],
            artifact_id="retained:" + request.family_id,
            output_hash="retained-hash",
        )

    settings = _settings(tmp_path, artifacts_use_vector_store=True)
    for vector_store_content_hash in (
        "vector-content-original",
        "vector-content-reindexed",
    ):
        generate_artifacts(
            report_id="vector-store-reuse-proof",
            report_name="Vector Store Reuse Proof",
            doc_map=_doc_map(),
            evidence_packs=_evidence_packs(),
            settings=settings,
            md5="vector-store-reuse-proof-md5",
            vector_store_id="vs-retained",
            vector_store_content_hash=vector_store_content_hash,
            openai_client=FakeOpenAI({}),
            prompt_client=FakePromptClient(),
            analysis_store=FakeAnalysisStore(),
            prompt_family_reuse_reader=reuse_reader,
        )

    assert len(summary_input_hashes) == 2
    assert summary_input_hashes[0] != summary_input_hashes[1]


def test_persisted_compatible_families_replay_without_model_calls(tmp_path) -> None:
    settings = _settings(tmp_path)
    fresh_client = FakeOpenAI(
        {
            "summary": {
                "summary": {
                    "tldr": "TLDR.",
                    "card_tldr_compact": "TLDR.",
                    "executive_summary": "Executive.",
                    "claim_evidence_map": [],
                }
            },
            "insights_candidates": {"insights_candidates": []},
            "quotes": {"quotes_final": []},
            "insights_final": {"insights_final": []},
            "cover_semantics": _cover_semantics_response(),
            "expert_comment": {"expert_comment": "Comment."},
            "linkedin_post": {"linkedin_post": "Post."},
        }
    )
    first = generate_artifacts(
        report_id="persisted-family-reuse",
        report_name="Persisted Family Reuse",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=settings,
        md5="persisted-family-reuse-md5",
        openai_client=fresh_client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    family_outputs = first["_cache"]["family_outputs"]
    for family_id, output in family_outputs.items():
        identity = first["_cache"]["family_reuse"][family_id]
        materialize_prompt_family(
            PromptFamilyMaterializationRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                output_dir=settings.output_dir,
                report_id="persisted-family-reuse",
                report_slug="Persisted Family Reuse",
                source_id="persisted-family-reuse-md5",
                family_id=family_id,
                family_schema_version=identity["family_schema_version"],
                processing_version=identity["processing_version"],
                output_payload=output,
                prompt_content_hash=identity["prompt_content_hash"],
                prompt_dependency_manifest=identity["prompt_dependency_manifest"],
                execution_identity=identity["execution_identity"],
                execution_identity_manifest=identity["execution_identity_manifest"],
                prompt_policy_version=identity["prompt_content_hash"],
                model_name=identity["model_name"],
                model_provider=identity["model_provider"],
                model_policy_namespace=identity["model_policy_namespace"],
                routing_policy_version=identity["routing_policy_version"],
                relevant_input_hash=identity["relevant_input_hash"],
                configuration_policy_hash=identity["configuration_policy_hash"],
                validator_version=identity["validator_version"],
                validation_status="pass",
            ),
            _ctx(),
        )

    replay_client = FakeOpenAI({})
    replay = generate_artifacts(
        report_id="persisted-family-reuse",
        report_name="Persisted Family Reuse",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=settings,
        md5="persisted-family-reuse-md5",
        openai_client=replay_client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert replay_client.requests == [], {
        "telemetry": replay["_cache"]["family_reuse_telemetry"],
        "first": first["_cache"]["family_reuse"],
        "replay": replay["_cache"]["family_reuse"],
    }
    assert replay["summary"] == first["summary"]


def test_invalidating_one_family_calls_only_its_model_route(tmp_path) -> None:
    retained = {
        "report_vs/artifacts/editorial_plan": _default_editorial_plan(),
        "report_vs/artifacts/summary": {
            "tldr": "Grounded TLDR.",
            "card_tldr_compact": "Grounded TLDR.",
            "executive_summary": "Executive summary.",
            "claim_evidence_map": [],
        },
        "report_vs/artifacts/insights_candidates": [],
        "report_vs/artifacts/quotes": [],
        "report_vs/artifacts/insights_final": [],
        "report_vs/artifacts/cover_semantics": _cover_semantics(),
        "report_vs/artifacts/expert_comment": "Grounded comment.",
        "report_vs/artifacts/linkedin_post": "Grounded LinkedIn post.",
    }

    def reuse_reader(request, _ctx):
        if request.family_id == "report_vs/artifacts/summary":
            return PromptFamilyReuseResponse(
                schema_version="1.0", reusable=False, reason="input_hash_changed"
            )
        return PromptFamilyReuseResponse(
            schema_version="1.0",
            reusable=True,
            reason="reused",
            output_payload=retained[request.family_id],
            artifact_id="retained:" + request.family_id,
            output_hash="retained-hash",
        )

    client = FakeOpenAI(
        {"summary": {"summary": retained["report_vs/artifacts/summary"]}}
    )
    replay = generate_artifacts(
        report_id="single-family-repair",
        report_name="Single Family Repair",
        doc_map=_doc_map(),
        evidence_packs=_evidence_packs(),
        settings=_settings(tmp_path),
        md5="single-family-repair-md5",
        openai_client=client,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
        prompt_family_reuse_reader=reuse_reader,
    )

    assert [request[2] for request in client.requests] == ["summary"]
    telemetry = replay["_cache"]["family_reuse_telemetry"]
    assert telemetry["regenerated_families"] == ["report_vs/artifacts/summary"]
    assert telemetry["reused_families"] == sorted(
        set(retained) - {"report_vs/artifacts/summary"}
    )


__all__ = [
    "test_artifact_cache_isolated_by_retrieval_mode",
    "test_load_cached_artifacts_rejects_schema_invalid_payload",
    "test_load_cached_artifacts_rejects_v2_without_cover_semantics",
    "test_load_cached_artifacts_refreshes_derived_family_status",
    "test_load_cached_artifacts_clears_doc_map_only_quotes_after_policy_refresh",
    "test_generate_artifacts_with_auto_context_preserves_input_evidence",
    "test_compatible_retained_families_make_zero_model_calls",
    "test_vector_store_identity_is_part_of_family_reuse_proof",
    "test_persisted_compatible_families_replay_without_model_calls",
    "test_invalidating_one_family_calls_only_its_model_route",
]
