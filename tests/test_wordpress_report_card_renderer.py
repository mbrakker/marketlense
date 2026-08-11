from __future__ import annotations

import json
import re
import subprocess
from html import unescape
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "wordpress_runtime" / "report_card_renderer_harness.php"


def _report(*, is_new: bool = True, geography_icon: str = "globe") -> dict[str, object]:
    return {
        "card_contract_valid": True,
        "title": "A Complete Three Line Report Title That Must Never Be Shortened",
        "title_scale": "xlong",
        "permalink": "https://example.test/reports/complete-report/",
        "publisher": "Market Research Institute",
        "date": "June 12, 2026",
        "geography": "Global" if geography_icon == "globe" else "Europe",
        "geography_scope": "global" if geography_icon == "globe" else "regional",
        "geography_icon": geography_icon,
        "time_period": "2024-2026",
        "tldr_compact": "Compact intelligence remains complete.",
        "tldr_standard": (
            "This complete standard TLDR can occupy two or three lines without "
            "being clipped, shortened, or replaced."
        ),
        "key_insights": [
            "The first complete key insight remains visible.",
            "The second complete key insight remains visible.",
        ],
        "is_new": is_new,
        "covers": {
            "small": "https://example.test/media/report-small.png",
            "medium": "https://example.test/media/report-medium.png",
            "large": "https://example.test/media/report-large.png",
        },
    }


def _render(variant: str, **report_overrides: object) -> dict[str, str]:
    report = _report()
    report.update(report_overrides)
    completed = subprocess.run(
        ["php", str(HARNESS)],
        input=json.dumps({"variant": variant, "report": report}),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize("variant", ("small", "medium", "large"))
def test_renderer_emits_only_canonical_variant_root_and_cover(variant: str) -> None:
    result = _render(variant)
    html = result["html"]

    assert result["error"] == ""
    assert f'class="ml-card ml-card--{variant} ml-card--title-xlong"' in html
    assert f"https://example.test/media/report-{variant}.png" in html
    assert html.count('href="https://example.test/reports/complete-report/"') == 1
    assert 'alt=""' in html


def test_small_card_uses_complete_compact_tldr_without_insights() -> None:
    html = _render("small")["html"]

    assert "Compact intelligence remains complete." in html
    assert "This complete standard TLDR" not in html
    assert "ml-card__insights" not in html


def test_medium_card_uses_complete_standard_tldr_without_insights() -> None:
    html = _render("medium")["html"]

    assert "This complete standard TLDR" in html
    assert "Compact intelligence remains complete." not in html
    assert "ml-card__insights" not in html


def test_large_card_uses_complete_standard_tldr_and_exactly_two_insights() -> None:
    html = _render("large")["html"]
    insights_match = re.search(
        r'<ul class="ml-card__insights">(.*?)</ul>',
        html,
        flags=re.DOTALL,
    )

    assert "This complete standard TLDR" in html
    assert insights_match is not None
    assert insights_match.group(1).count("<li>") == 2
    assert "The first complete key insight remains visible." in html
    assert "The second complete key insight remains visible." in html


@pytest.mark.parametrize(("is_new", "expected"), ((True, True), (False, False)))
def test_new_badge_matches_view_model_boundary(is_new: bool, expected: bool) -> None:
    html = _render("small", is_new=is_new)["html"]

    assert ('class="ml-card__badge">New</span>' in html) is expected


@pytest.mark.parametrize(
    ("icon", "expected_class", "unexpected_class"),
    (
        ("globe", "ml-card__icon--globe", "ml-card__icon--locator"),
        ("locator", "ml-card__icon--locator", "ml-card__icon--globe"),
    ),
)
def test_geography_uses_scope_specific_pictogram(
    icon: str,
    expected_class: str,
    unexpected_class: str,
) -> None:
    report = _report(geography_icon=icon)
    completed = subprocess.run(
        ["php", str(HARNESS)],
        input=json.dumps({"variant": "small", "report": report}),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    html = json.loads(completed.stdout)["html"]

    assert expected_class in html
    assert unexpected_class not in html
    assert "ml-card__icon--calendar" in html
    assert "ml-card__icon--period" in html


@pytest.mark.parametrize("variant", ("small", "medium", "large"))
def test_renderer_preserves_full_title_and_tldr_without_clamp_markup(
    variant: str,
) -> None:
    html = unescape(_render(variant)["html"])
    report = _report()
    expected_tldr = (
        report["tldr_compact"] if variant == "small" else report["tldr_standard"]
    )

    assert report["title"] in html
    assert expected_tldr in html
    assert "line-clamp" not in html
    assert "ellipsis" not in html


@pytest.mark.parametrize("variant", ("small", "medium", "large"))
def test_renderer_truncates_overflowing_title_and_exposes_full_hover_text(
    variant: str,
) -> None:
    title = (
        "Evidence-led regional transition pathways "
        + "with validated market signals " * 5
    ).strip()
    html = unescape(_render(variant, title=title)["html"])
    title_match = re.search(
        r'<h3 class="ml-card__title" title="([^"]+)" aria-label="([^"]+)">([^<]+)</h3>',
        html,
    )

    assert title_match is not None
    assert title_match.group(1) == title
    assert title_match.group(2) == title
    assert title_match.group(3) == title[:137].rstrip() + "..."


def test_renderer_rejects_noncanonical_variant() -> None:
    result = _render("compact")

    assert result["html"] == ""
    assert result["error"].startswith("InvalidArgumentException:")


def test_renderer_fails_closed_without_a_required_public_field() -> None:
    result = _render("small", publisher="")

    assert result == {"html": "", "error": ""}
