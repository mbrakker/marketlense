import json
from pathlib import Path

import pytest

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.services._render_service.normalization import _extract_fieldwork_dates
from src.services.render_service import render_report
from src.utils.time_period import normalize_time_period


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2023", "2023"),
        ("2023, 2024", "2023, 2024"),
        ("2023 to 2025", "2023\u20132025"),
    ],
)
def test_public_period_projects_clean_year_values(raw: str, expected: str) -> None:
    assert normalize_time_period(raw) == expected


def test_public_period_projects_the_only_year_from_surrounding_prose() -> None:
    raw = "2023\u521d\u81f32023\u5e74\u672b covered in report (2023)"

    assert (
        normalize_time_period(raw) == "2023"
    )


def test_public_period_projects_a_source_year_range_from_surrounding_prose() -> None:
    raw = "2024-2028, with 2024 consumer and market baseline data and 2028 forecasts"

    assert normalize_time_period(raw) == "2024–2028"


def test_public_period_prefers_an_explicit_fiscal_year_over_parenthetical_history(
) -> None:
    raw = "Fiscal year 2024 (with historical comparisons spanning 2020–2024)"

    assert (
        normalize_time_period(raw) == "FY2024"
    )


def test_public_period_omits_malformed_mixed_language_value_with_multiple_years(
) -> None:
    raw = "2023\u521d\u81f32024\u5e74\u672b covered in report"

    assert normalize_time_period(raw) is None


def test_public_period_omits_value_without_a_usable_temporal_expression() -> None:
    assert normalize_time_period("Current and future consumer behaviour") is None


def test_public_period_projects_explicit_date_range() -> None:
    assert (
        normalize_time_period("December 16, 2024 to January 2, 2025")
        == "December 16, 2024 to January 2, 2025"
    )


def test_fieldwork_extracts_only_the_explicit_date_range() -> None:
    assert (
        _extract_fieldwork_dates(
            "Fieldwork was conducted from December 16, 2024 to January 2, 2025."
        )
        == "December 16, 2024 to January 2, 2025"
    )


def test_fieldwork_does_not_include_the_remaining_sentence() -> None:
    assert (
        _extract_fieldwork_dates(
            "Fieldwork: December 16, 2024 to January 2, 2025; trust, regulation, "
            "and the full executive summary follow."
        )
        == "December 16, 2024 to January 2, 2025"
    )


def test_omnisend_public_metadata_regression_fixture_renders_a_clean_period(
    tmp_path: Path,
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "editorial_temporal"
    omnisend = json.loads(
        (fixture_dir / "omnisend_public_metadata.json").read_text("utf-8")
    )

    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": omnisend["report_title"],
                "publisher": omnisend["publisher"],
                "time_period": omnisend["time_period"],
                "artifacts": {"summary": {"tldr": "Source-backed summary."}},
            },
            doc_name="omnisend.pdf",
            file_id="omnisend",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    html = Path(response.html_path).read_text(encoding="utf-8")

    assert f"Period: {omnisend['expected_period']}" in html
    assert omnisend["time_period"] not in html


def test_yougov_public_metadata_regression_fixture_bounds_fieldwork(
    tmp_path: Path,
) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "editorial_temporal"
    yougov = json.loads(
        (fixture_dir / "yougov_public_metadata.json").read_text("utf-8")
    )

    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": yougov["report_title"],
                "publisher": yougov["publisher"],
                "time_period": yougov["time_period"],
                "evidence_packs": {"doc_map": {"methodology": yougov["methodology"]}},
                "artifacts": {
                    "summary": {
                        "tldr": "Source-backed summary.",
                        "executive_summary": yougov["executive_summary"],
                    }
                },
            },
            doc_name="yougov.pdf",
            file_id="yougov",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s"),
    )
    html = Path(response.html_path).read_text(encoding="utf-8")

    assert f"Fieldwork: {yougov['expected_fieldwork']}" in html
    assert "Period:" not in html
    assert "Fieldwork: Fieldwork" not in html
    assert "Fieldwork: December 16, 2024 to January 2, 2025. Trust" not in html
