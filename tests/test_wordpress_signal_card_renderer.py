from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "wordpress_runtime" / "signal_card_renderer_harness.php"


def _signal() -> dict[str, object]:
    return {
        "card_contract_valid": True,
        "title": "AI shopping is turning checkout into a trust layer.",
        "permalink": "https://example.test/signals/ai-shopping-trust/",
        "date": "June 20, 2026",
        "summary": (
            "Product certainty, fulfilment transparency, and payment controls are "
            "converging into one conversion condition."
        ),
        "confidence": 0.84,
        "source_count": 5,
        "evidence_count": 14,
        "topics": ["AI commerce", "Customer trust", "Checkout"],
        "uncertainty": (
            "Evidence is strongest in retail and technology publishers; validate "
            "the pattern against category-specific conversion data."
        ),
        "is_new": True,
        "covers": {
            "small": "https://example.test/media/signal-small.png",
            "medium": "https://example.test/media/signal-medium.png",
            "large": "https://example.test/media/signal-large.png",
        },
    }


def _render(variant: str, **overrides: object) -> dict[str, str]:
    signal = _signal()
    signal.update(overrides)
    completed = subprocess.run(
        ["php", str(HARNESS)],
        input=json.dumps({"variant": variant, "signal": signal}),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize("variant", ("small", "medium", "large"))
def test_signal_renderer_uses_only_the_three_canonical_variants(variant: str) -> None:
    result = _render(variant)

    assert result["error"] == ""
    assert f'class="ml-signal-card ml-signal-card--{variant}"' in result["html"]
    assert f"signal-{variant}.png" in result["html"]
    assert 'alt=""' in result["html"]


def test_small_signal_card_keeps_proof_counts_without_medium_or_large_details() -> None:
    html = _render("small")["html"]

    assert "84% confidence" in html
    assert "5 source reports" in html
    assert "14 evidence items" in html
    assert "AI commerce" not in html
    assert "Evidence condition" not in html


def test_medium_signal_card_adds_topics_without_the_evidence_condition() -> None:
    html = _render("medium")["html"]

    assert "AI commerce" in html
    assert "Customer trust" in html
    assert "Evidence condition" not in html


def test_large_signal_card_exposes_the_evidence_condition() -> None:
    html = _render("large")["html"]

    assert "Evidence condition" in html
    assert "validate the pattern against category-specific conversion data" in html


def test_signal_renderer_rejects_incomplete_contracts_and_unknown_variants() -> None:
    assert _render("small", card_contract_valid=False)["error"].startswith(
        "UnexpectedValueException:"
    )
    assert _render("compact")["error"].startswith("InvalidArgumentException:")


def test_signals_archive_uses_the_compact_card_variant_from_the_shared_browser() -> None:
    source = (
        ROOT
        / "Wordpress"
        / "wp-content"
        / "plugins"
        / "marketlense-core"
        / "includes"
        / "class-marketlense-core-archive-browser.php"
    ).read_text(encoding="utf-8")

    assert "public const SIGNALS = 'signals';" in source
    assert "$this->signal_card_renderer->render($signal, 'small')" in source
