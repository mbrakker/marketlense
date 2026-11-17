from __future__ import annotations

import pytest

from src.generators.evidence_pack_generator import generate_evidence_packs
from src.utils.errors import AppError
from tests._test_evidence_pack_generator._shared import (
    FakeAnalysisStore,
    FakePromptClient,
    RoutedOpenAIClient,
    _ctx,
    _settings,
    substantive_doc_map,
)


def test_findings_without_source_fail_before_storage(tmp_path):
    store = FakeAnalysisStore()
    client = RoutedOpenAIClient(
        {
            "doc_map": substantive_doc_map(),
            "findings": {
                "findings": [{"id": "f1", "text": "Revenue grew 18%.", "pages": [1]}]
            },
        }
    )

    with pytest.raises(AppError) as exc:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(
                tmp_path, evidence_pack_registry=["doc_map", "findings"]
            ),
            ctx=_ctx(),
            openai_client=client,
            prompt_client=FakePromptClient(),
            analysis_store=store,
        )

    assert exc.value.code == "findings_source_evidence_unavailable"
    assert not any(name == "findings" for _, name, _ in store.stored)


def test_empty_findings_without_source_can_abstain(tmp_path):
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_registry=["doc_map", "findings"]),
        ctx=_ctx(),
        openai_client=RoutedOpenAIClient(
            {
                "doc_map": substantive_doc_map(),
                "findings": {"not_found_reason": "source_has_no_findings"},
            }
        ),
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )

    assert packs["findings"]["findings"] == []
    assert packs["findings"]["family_status"]["status"] == "abstained"


def test_quotes_without_source_fail_before_storage(tmp_path):
    store = FakeAnalysisStore()
    with pytest.raises(AppError) as exc:
        generate_evidence_packs(
            report_id="r1",
            report_name="report",
            vector_store_id="vs_1",
            settings=_settings(
                tmp_path, evidence_pack_registry=["doc_map", "quote_candidates"]
            ),
            ctx=_ctx(),
            openai_client=RoutedOpenAIClient(
                {
                    "doc_map": substantive_doc_map(),
                    "quote_candidates": {
                        "quote_candidates": [
                            {"id": "q1", "text": "A quotation.", "page": 1}
                        ]
                    },
                }
            ),
            prompt_client=FakePromptClient(),
            analysis_store=store,
        )
    assert exc.value.code == "quote_candidates_source_evidence_unavailable"
    assert not any(name == "quote_candidates" for _, name, _ in store.stored)
