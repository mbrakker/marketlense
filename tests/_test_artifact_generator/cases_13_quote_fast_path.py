# ruff: noqa: F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403,F405


_QUOTE_FAMILY = "report_vs/artifacts/quotes"


def _quote_status(status: str, *, reason: str = "") -> dict:
    return {
        "schema_version": "1.0",
        "family": "quote_candidates",
        "source": "evidence_pack",
        "status": status,
        "confidence_score": 1.0 if status == "generated" else 0.0,
        "policy_action": "keep" if status == "generated" else "abstain",
        "reason": reason,
    }


def _quote_candidate(quote_id: str, text: str, source: str, page: int = 3) -> dict:
    return {"id": quote_id, "text": text, "source": source, "page": page}


def _generate_quote_fixture(
    tmp_path, quote_pack: dict | None, *, missing: bool = False
):
    evidence_packs = _evidence_packs()
    if missing:
        evidence_packs.pop("quote_candidates", None)
    elif quote_pack is not None:
        evidence_packs["quote_candidates"] = quote_pack
    responses = {
        "summary": {
            "summary": {
                "tldr": "Grounded TLDR.",
                "card_tldr_compact": "Grounded TLDR.",
                "executive_summary": "Exec",
                "claim_evidence_map": [
                    {
                        "claim": "Claim",
                        "evidence_id": "f1",
                        "evidence": "E",
                        "pages": [1],
                    }
                ],
            }
        },
        "insights_candidates": {
            "insights_candidates": [
                {
                    "id": "candidate-1",
                    "text": "Insight",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                    "score": 0.9,
                }
            ]
        },
        "insights_final": {
            "insights_final": [
                {
                    "id": "final-1",
                    "text": "Final insight.",
                    "evidence_id": "f1",
                    "evidence": "E",
                    "metric": {},
                    "pages": [1],
                }
            ]
        },
        "quotes": {
            "quotes_final": [
                {
                    "text": "Model-selected quote",
                    "speaker": "Analyst",
                    "citation": "Annual report",
                    "page": 3,
                    "evidence_id": "q1",
                }
            ]
        },
        "cover_semantics": _cover_semantics_response(),
        "expert_comment": {"expert_comment": "Grounded comment."},
        "linkedin_post": {"linkedin_post": "Grounded post."},
    }
    fake_openai = FakeOpenAI(responses)
    payload = generate_artifacts(
        report_id="quote-fast-path",
        report_name="quote-fast-path",
        doc_map=_doc_map(),
        evidence_packs=evidence_packs,
        settings=_settings(tmp_path, artifacts_use_vector_store=True),
        vector_store_id="vs_quote_test",
        categories=[],
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    return payload, fake_openai


@pytest.mark.parametrize("candidate_count", [1, 3])
def test_complete_small_quote_pools_use_verbatim_fast_path(tmp_path, candidate_count):
    candidates = [
        _quote_candidate(
            f"q{index}",
            f"  Verbatim source quote {index}.  ",
            f"Speaker {index}",
            index + 2,
        )
        for index in range(1, candidate_count + 1)
    ]
    pack = {
        "quote_candidates": candidates,
        "family_status": _quote_status("generated"),
    }

    payload, fake_openai = _generate_quote_fixture(tmp_path, pack)

    assert "quotes" not in [call[2] for call in fake_openai.requests]
    assert [quote["text"] for quote in payload["quotes_final"]] == [
        candidate["text"].strip() for candidate in candidates
    ]
    assert [quote["evidence_id"] for quote in payload["quotes_final"]] == [
        candidate["id"] for candidate in candidates
    ]
    assert [quote["page"] for quote in payload["quotes_final"]] == [
        candidate["page"] for candidate in candidates
    ]
    assert [quote["speaker"] for quote in payload["quotes_final"]] == [
        "Unknown" for _ in candidates
    ]
    cache = payload["_cache"]
    assert cache["family_reuse"][_QUOTE_FAMILY]["decision"] == "deterministic"
    assert cache["family_reuse"][_QUOTE_FAMILY]["producer"] == (
        "deterministic_quote_fast_path"
    )
    assert _QUOTE_FAMILY not in cache["producing_prompt_identities"]
    assert (
        cache["family_outputs"][_QUOTE_FAMILY]["quotes_final"]
        == payload["quotes_final"]
    )


def test_complete_empty_quote_pool_is_explicit_abstention_without_model_call(
    tmp_path,
):
    pack = {
        "quote_candidates": [],
        "not_found_reason": "quote_candidates_not_found",
        "family_status": _quote_status(
            "abstained", reason="quote_candidates_not_found"
        ),
    }

    payload, fake_openai = _generate_quote_fixture(tmp_path, pack)

    assert "quotes" not in [call[2] for call in fake_openai.requests]
    assert payload["quotes_final"] == []
    assert payload["_cache"]["family_reuse"][_QUOTE_FAMILY]["decision"] == (
        "complete_empty"
    )


def test_incomplete_quote_pool_is_held_without_claiming_it_is_empty(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="market_lense.artifact_generator")
    failed_pack = {
        "quote_candidates": [],
        "family_status": _quote_status("failed", reason="extraction_failed"),
    }

    payload, fake_openai = _generate_quote_fixture(tmp_path, failed_pack)

    assert "quotes" not in [call[2] for call in fake_openai.requests]
    assert payload["quotes_final"] == []
    assert payload["_cache"]["family_reuse"][_QUOTE_FAMILY]["decision"] == "held"
    assert "artifact_quotes_held_incomplete_candidate_pool" in caplog.text


def test_missing_quote_pool_is_not_treated_as_complete_empty(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="market_lense.artifact_generator")
    payload, fake_openai = _generate_quote_fixture(tmp_path, None, missing=True)

    assert "quotes" not in [call[2] for call in fake_openai.requests]
    assert payload["quotes_final"] == []
    assert payload["_cache"]["family_reuse"][_QUOTE_FAMILY]["decision"] == "held"
    assert "artifact_quotes_held_incomplete_candidate_pool" in caplog.text


def test_larger_quote_pool_uses_semantic_selection(tmp_path):
    pack = {
        "quote_candidates": [
            _quote_candidate(f"q{index}", f"Source quote {index}.", f"Speaker {index}")
            for index in range(1, 5)
        ],
        "family_status": _quote_status("generated"),
    }

    payload, fake_openai = _generate_quote_fixture(tmp_path, pack)

    assert "quotes" in [call[2] for call in fake_openai.requests]
    assert payload["quotes_final"][0]["text"] == "Model-selected quote"


def test_duplicate_quotes_deduplicate_but_conflicting_speakers_use_model(tmp_path):
    same_source_pack = {
        "quote_candidates": [
            _quote_candidate("q1", "Same quote.", "CEO"),
            _quote_candidate("q2", "Same quote.", "CEO"),
        ],
        "family_status": _quote_status("generated"),
    }
    deduplicated, dedupe_client = _generate_quote_fixture(
        tmp_path / "same-source", same_source_pack
    )
    assert "quotes" not in [call[2] for call in dedupe_client.requests]
    assert len(deduplicated["quotes_final"]) == 1

    ambiguous_pack = {
        "quote_candidates": [
            _quote_candidate("q1", "Same quote.", "CEO"),
            _quote_candidate("q2", "Same quote.", "CFO"),
        ],
        "family_status": _quote_status("generated"),
    }
    selected, ambiguous_client = _generate_quote_fixture(
        tmp_path / "conflicting-speakers", ambiguous_pack
    )
    assert "quotes" in [call[2] for call in ambiguous_client.requests]
    assert selected["quotes_final"][0]["text"] == "Model-selected quote"
