# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_artifact_cache_isolated_by_retrieval_mode(tmp_path):
    responses = {
        "toc": {"toc_topics": ["Topic"]},
        "summary": {
            "summary": {
                "tldr": "TLDR",
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
    assert len(chat_openai.requests) == 6
    assert len([req for req in chat_openai.requests if req[0] == "chat"]) == 6

    vector_settings = _settings(tmp_path, artifacts_use_vector_store=True)
    vector_openai = FakeOpenAI(responses)
    generate_artifacts(
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
    assert len(vector_openai.requests) == 6
    assert len([req for req in vector_openai.requests if req[0] == "vector"]) == 6

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
    assert cached["family_status"]["summary"]["status"] == "generated"

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
        "summary": {
            "tldr": "",
            "executive_summary": "",
            "claim_evidence_map": [],
        },
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
                "tldr": "TLDR",
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
    assert len(fake_openai.requests) == 6

__all__ = [
    "test_artifact_cache_isolated_by_retrieval_mode",
    "test_load_cached_artifacts_rejects_schema_invalid_payload",
    "test_load_cached_artifacts_refreshes_derived_family_status",
    "test_load_cached_artifacts_clears_doc_map_only_quotes_after_policy_refresh",
    "test_generate_artifacts_with_auto_context_preserves_input_evidence",
]
