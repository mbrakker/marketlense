from __future__ import annotations

from types import SimpleNamespace

from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import UiRunSummary
from src.ui.app_pages import strategy_outputs


def test_feature_coverage_rows_include_new_strategy_surfaces() -> None:
    rows = strategy_outputs.build_feature_coverage_rows()

    by_feature = {row["feature"]: row for row in rows}

    assert by_feature["Cross-report briefings"]["status"] == "New in UI"
    assert by_feature["Durable Signal candidates"]["streamlit_surface"] == (
        "Strategy Outputs"
    )
    assert by_feature["Signal posts"]["codebase_surface"] == "signal_post_orchestrator"
    assert by_feature["UI-run replay"]["operator_outcome"]
    assert strategy_outputs.build_status_count_rows(rows) == [
        {"status": "Covered", "feature_count": 7},
        {"status": "New in UI", "feature_count": 4},
    ]


def test_build_cross_report_run_payload_normalizes_controls() -> None:
    payload = strategy_outputs.build_cross_report_run_payload(
        topic=" AI commerce ",
        auto_theme=False,
        category_filters=["Retail"],
        tag_filters=["AI"],
        publisher_filters=["Publisher A"],
        date_range_start="2026-05-01",
        date_range_end="2026-05-31",
        max_source_reports=3,
        max_evidence_items=12,
        max_prompt_chars=50000,
        publication_mode="publish_dry_run",
        request_id=" custom-request ",
        diagnostic=True,
        override_publishability=True,
    )

    assert payload == {
        "topic": "AI commerce",
        "auto_theme": False,
        "category_filters": ["Retail"],
        "tag_filters": ["AI"],
        "publisher_filters": ["Publisher A"],
        "date_range_start": "2026-05-01",
        "date_range_end": "2026-05-31",
        "max_source_reports": 3,
        "max_evidence_items": 12,
        "max_prompt_chars": 50000,
        "publication_mode": "publish_dry_run",
        "output_root": "",
        "idempotency_db": "",
        "request_id": "custom-request",
        "diagnostic": True,
        "override_publishability": True,
    }


def test_build_signal_payloads_use_structured_filters() -> None:
    candidate_payload = strategy_outputs.build_signal_candidate_run_payload(
        topic=" Loyalty risk ",
        category_filters=["Retail"],
        tag_filters=["Loyalty"],
        publisher_filters=["Publisher B"],
        date_range_start=None,
        date_range_end=None,
        max_source_reports=4,
        max_evidence_items=8,
        max_signals=5,
        signal_store_db=" state/signals.sqlite ",
        extraction_request_id=" extract-loyalty ",
    )
    post_payload = strategy_outputs.build_signal_post_run_payload(
        topic=" Loyalty risk ",
        category_filters=["Retail"],
        tag_filters=["Loyalty"],
        publisher_filters=["Publisher B"],
        date_range_start="2026-06-01",
        date_range_end="2026-06-04",
        max_source_reports=3,
        max_evidence_items=6,
        minimum_source_reports=2,
        minimum_evidence_items=2,
        publication_mode="generate_only",
        output_root=" out ",
        signal_store_db=" state/signals.sqlite ",
        request_id=" signal-post ",
    )

    assert candidate_payload["topic"] == "Loyalty risk"
    assert candidate_payload["signal_store_db"] == "state/signals.sqlite"
    assert candidate_payload["extraction_request_id"] == "extract-loyalty"
    assert post_payload["publication_mode"] == "generate_only"
    assert post_payload["output_root"] == "out"
    assert post_payload["request_id"] == "signal-post"


def test_replay_run_rows_use_summary_contract_without_artifact_paths() -> None:
    summary = UiRunSummary(
        schema_version="1.0",
        run_id=RunId("run-12345678"),
        run_type="cross_report_analysis",
        display_name="Cross-report analysis",
        status="succeeded",
        created_at_utc="2026-07-03T00:00:00Z",
    )

    assert strategy_outputs.build_replay_run_rows([summary]) == [
        {
            "run_id": "run-12345678",
            "workflow": "Cross-report analysis",
            "status": "succeeded",
            "created_at_utc": "2026-07-03T00:00:00Z",
        }
    ]


def test_projection_and_signal_chart_rows_are_semantic() -> None:
    projected = SimpleNamespace(
        source_candidates=[
            SimpleNamespace(
                publisher="Publisher A",
                category_labels=["Retail"],
                tags=["AI"],
            ),
            SimpleNamespace(
                publisher="Publisher A",
                category_labels=["Retail", "Commerce"],
                tags=["AI", "Search"],
            ),
            SimpleNamespace(
                publisher="Publisher B",
                category_labels=["Commerce"],
                tags=["Search"],
            ),
        ],
        evidence=[
            SimpleNamespace(content_class="claim"),
            SimpleNamespace(content_class="finding"),
            SimpleNamespace(content_class="claim"),
        ],
        raw_metrics=[SimpleNamespace()],
    )
    signal_response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                title="AI search signal",
                candidate_type="market_signal",
                support_level="multi_report_convergent",
                confidence=0.8,
                strength=0.7,
                validation_status="approved",
                source_report_ids=["a", "b"],
                evidence_ids=["e1", "e2"],
            )
        ],
        groups=[SimpleNamespace()],
    )

    assert strategy_outputs.build_projection_publisher_rows(projected) == [
        {"publisher": "Publisher A", "projected_reports": 2},
        {"publisher": "Publisher B", "projected_reports": 1},
    ]
    assert strategy_outputs.build_evidence_class_rows(projected) == [
        {"content_class": "claim", "item_count": 2},
        {"content_class": "finding", "item_count": 1},
        {"content_class": "metric", "item_count": 1},
    ]
    candidate_rows = strategy_outputs.build_signal_candidate_rows(signal_response)
    assert candidate_rows[0]["confidence"] == 0.8
    assert candidate_rows[0]["reports"] == 2
    assert strategy_outputs.build_signal_support_rows(candidate_rows) == [
        {"support": "multi_report_convergent", "candidate_count": 1}
    ]
