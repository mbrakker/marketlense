# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_strip_json_fence_requires_closing_fence():
    raw = '```json\n{"key":1}\n'
    assert _strip_json_fence(raw) == raw.strip()


def test_strip_json_fence_strips_allowed_json_fence():
    raw = '```json\n{"key":1}\n```'
    assert _strip_json_fence(raw) == '{"key":1}'


def test_resolve_pack_steps_prepends_doc_map_when_missing():
    settings = SimpleNamespace(
        evidence_pack_registry=["scope", "methods"],
    )
    steps = _resolve_pack_steps(settings)
    assert all(isinstance(strategy, EvidencePackStrategy) for strategy in steps)
    assert [strategy.pack_name for strategy in steps][:3] == [
        "doc_map",
        "scope",
        "methods",
    ]


def test_resolve_pack_steps_excludes_retired_specialist_families():
    settings = SimpleNamespace(
        evidence_pack_registry=[
            "doc_map",
            "findings",
            "key_metrics",
            "risk_register",
            "recommendations",
            "contradictions",
        ],
    )

    steps = _resolve_pack_steps(settings)

    assert [strategy.pack_name for strategy in steps] == ["doc_map", "findings"]


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
                    "title": "Legacy Retail Outlook",
                    "summary": "Examines retail demand and measurement changes.",
                    "sections": [
                        {
                            "heading": "Retail demand trends",
                            "summary": (
                                "Describes consumer demand changes across retail "
                                "categories."
                            ),
                        }
                    ],
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
    assert cached["title"] == "Legacy Retail Outlook"
    assert cached["sections"][0]["title"] == "Retail demand trends"
    assert cached["sections"][0]["id"]


def test_load_cached_evidence_pack_rejects_identifier_only_doc_map(tmp_path):
    report_name = "identifier only cached report"
    cache_path = tmp_path / slugify(report_name) / "report_analysis" / "doc_map.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "_cache": {"key": "cache-key"},
                "doc_id": "identifier-only-report",
                "title": "doc_map",
                "summary": "identifier-only-report | vs_123 | doc_map",
                "sections": [
                    {
                        "id": "s1",
                        "title": "Metadata",
                        "summary": (
                            "Key metadata fields extracted from source evidence."
                        ),
                        "key_points": ["report_name: identifier-only-report"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cached = _load_cached_pack(
        output_dir=str(tmp_path),
        report_id="identifier-only-report",
        pack_name="doc_map",
        report_name=report_name,
        cache_key="cache-key",
        ctx=_ctx(),
        analysis_store=None,
    )

    assert cached is None


__all__ = [
    "test_strip_json_fence_requires_closing_fence",
    "test_strip_json_fence_strips_allowed_json_fence",
    "test_resolve_pack_steps_prepends_doc_map_when_missing",
    "test_resolve_pack_steps_excludes_retired_specialist_families",
    "test_pack_strategy_registry_exposes_expected_prompt_and_schema_metadata",
    "test_load_cached_evidence_pack_normalizes_legacy_payload_before_validation",
    "test_load_cached_evidence_pack_rejects_identifier_only_doc_map",
]
