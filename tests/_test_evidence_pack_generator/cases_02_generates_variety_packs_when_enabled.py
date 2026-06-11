# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_generate_evidence_packs_generates_variety_packs_when_enabled(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            },
            "scope": {"scope": "Scope summary"},
            "methods": {"methods": ["Survey"]},
            "findings": {
                "findings": [{"id": "f1", "text": "Finding", "evidence": "Evidence"}]
            },
            "limitations": {"limitations": ["Small sample"]},
            "quote_candidates": {
                "quote_candidates": [
                    {"id": "q1", "text": "Quote", "source": "CEO", "page": 2}
                ]
            },
            "key_metrics": {
                "key_metrics": [
                    {
                        "id": "m1",
                        "metric": "Growth",
                        "value": "10",
                        "unit": "%",
                        "evidence_id": "f1",
                        "pages": [2],
                    }
                ]
            },
            "risk_register": {
                "risk_register": [
                    {
                        "id": "r1",
                        "risk": "Churn risk",
                        "impact": "Revenue",
                        "likelihood": "Medium",
                        "mitigation": "Retention",
                        "evidence_id": "f1",
                    }
                ]
            },
            "recommendations": {
                "recommendations": [
                    {
                        "id": "rec1",
                        "recommendation": "Invest in retention",
                        "rationale": "Churn pressure",
                        "evidence_id": "f1",
                    }
                ]
            },
            "contradictions": {
                "contradictions": [
                    {
                        "id": "c1",
                        "statement_a": "Demand up",
                        "statement_b": "Conversion down",
                        "explanation": "Segment split",
                        "evidence_ids": ["f1"],
                    }
                ]
            },
        }
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(tmp_path, evidence_pack_enable_new_variety_packs=True),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert "key_metrics" in packs
    assert "risk_register" in packs
    assert "recommendations" in packs
    assert "contradictions" in packs
    assert packs["key_metrics"]["key_metrics"][0]["id"] == "m1"
    assert packs["risk_register"]["risk_register"][0]["id"] == "r1"
    assert packs["recommendations"]["recommendations"][0]["id"] == "rec1"
    assert packs["contradictions"]["contradictions"][0]["id"] == "c1"

def test_generate_evidence_packs_variety_pack_non_json_falls_back_with_reason(tmp_path):
    fake_openai = RoutedOpenAIClient(
        payloads_by_pack={
            "doc_map": {
                "doc_id": "d1",
                "title": "title",
                "sections": [{"title": "Overview"}],
            },
            "key_metrics": None,
        },
        text_by_pack={
            "key_metrics": "not-json",
        },
    )
    packs = generate_evidence_packs(
        report_id="r1",
        report_name="report",
        vector_store_id="vs_1",
        settings=_settings(
            tmp_path,
            evidence_pack_registry=["doc_map", "key_metrics"],
            evidence_pack_enable_new_variety_packs=True,
        ),
        ctx=_ctx(),
        openai_client=fake_openai,
        prompt_client=FakePromptClient(),
        analysis_store=FakeAnalysisStore(),
    )
    assert packs["key_metrics"]["key_metrics"] == []
    assert packs["key_metrics"]["not_found_reason"] == "model_returned_no_json"

def test_strip_json_fence_requires_closing_fence():
    raw = '```json\n{"key":1}\n'
    assert _strip_json_fence(raw) == raw.strip()

def test_strip_json_fence_strips_allowed_json_fence():
    raw = '```json\n{"key":1}\n```'
    assert _strip_json_fence(raw) == '{"key":1}'

def test_resolve_pack_steps_prepends_doc_map_when_missing():
    settings = SimpleNamespace(
        evidence_pack_registry=["scope", "methods"],
        evidence_pack_enable_new_variety_packs=False,
    )
    steps = _resolve_pack_steps(settings)
    assert all(isinstance(strategy, EvidencePackStrategy) for strategy in steps)
    assert [strategy.pack_name for strategy in steps][:3] == [
        "doc_map",
        "scope",
        "methods",
    ]

def test_pack_strategy_registry_exposes_expected_prompt_and_schema_metadata():
    expected = {
        "doc_map": ("doc_map", "doc_map"),
        "scope": ("evidence_packs/scope", "scope_pack"),
        "methods": ("evidence_packs/methods", "methods_pack"),
        "findings": ("evidence_packs/findings", "findings_pack"),
        "limitations": ("evidence_packs/limitations", "limitations_pack"),
        "quote_candidates": (
            "evidence_packs/quote_candidates",
            "quote_candidates_pack",
        ),
        "key_metrics": ("evidence_packs/key_metrics", "key_metrics_pack"),
        "risk_register": ("evidence_packs/risk_register", "risk_register_pack"),
        "recommendations": (
            "evidence_packs/recommendations",
            "recommendations_pack",
        ),
        "contradictions": ("evidence_packs/contradictions", "contradictions_pack"),
    }
    assert set(PACK_STRATEGIES.keys()) == set(expected.keys())
    for pack_name, (prompt_ns, schema_name) in expected.items():
        strategy = PACK_STRATEGIES[pack_name]
        assert strategy.prompt_namespace_suffix == prompt_ns
        assert strategy.schema_name == schema_name

def test_load_cached_evidence_pack_normalizes_legacy_payload_before_validation(
    tmp_path,
):
    report_name = "evidence cache invalid"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "doc_map.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "_cache": {"key": "cache-key"},
                "doc_map": {
                    "title": "Legacy title",
                    "sections": [{"heading": "Overview"}],
                },
            }
        ),
        encoding="utf-8",
    )

    cached = _load_cached_pack(
        output_dir=str(tmp_path),
        report_id="evidence-cache-invalid",
        pack_name="doc_map",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is not None
    assert cached["doc_id"] == "evidence-cache-invalid"
    assert cached["title"] == "Legacy title"
    assert cached["sections"][0]["title"] == "Overview"
    assert cached["sections"][0]["id"]

__all__ = [
    "test_generate_evidence_packs_generates_variety_packs_when_enabled",
    "test_generate_evidence_packs_variety_pack_non_json_falls_back_with_reason",
    "test_strip_json_fence_requires_closing_fence",
    "test_strip_json_fence_strips_allowed_json_fence",
    "test_resolve_pack_steps_prepends_doc_map_when_missing",
    "test_pack_strategy_registry_exposes_expected_prompt_and_schema_metadata",
    "test_load_cached_evidence_pack_normalizes_legacy_payload_before_validation",
]
