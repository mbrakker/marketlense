from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "wordpress_runtime" / "report_view_model_harness.php"


def _build_view_model(
    content: str, categories: list[dict[str, object]]
) -> dict[str, int]:
    completed = subprocess.run(
        ["php", str(HARNESS)],
        input=json.dumps({"content": content, "categories": categories}),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_current_report_markup_counts_findings_quotes_and_public_categories() -> None:
    content = """
    <section id="findings">
      <article class="finding-card">Finding one</article>
      <article class="finding-card">Finding two</article>
      <article class="finding-card">Finding three</article>
      <article class="finding-card">Finding four</article>
      <article class="finding-card">Finding five</article>
    </section>
    <section id="evidence">
      <figure class="quote-feature"><blockquote>Quote one</blockquote></figure>
      <figure class="quote-card"><blockquote>Quote two</blockquote></figure>
      <figure class="quote-card"><blockquote>Quote three</blockquote></figure>
      <figure class="quote-card"><blockquote>Quote four</blockquote></figure>
    </section>
    <section id="taxonomy">
      <ul class="chip-list">
        <li>Category A</li><li>Category B</li><li>Tag A</li>
        <li>Tag B</li><li>Tag C</li>
      </ul>
    </section>
    <p>7 evidence references</p>
    """
    categories = [
        {
            "id": 1,
            "name": "Advertising Strategy & Media",
            "slug": "advertising-media",
        },
        {
            "id": 2,
            "name": "Retail & Commerce Media",
            "slug": "retail-commerce-media",
        },
    ]

    assert _build_view_model(content, categories) == {
        "insights_count": 5,
        "quotes_count": 4,
        "topics_count": 2,
        "citations_count": 7,
    }


def test_legacy_report_markup_remains_supported() -> None:
    content = """
    <section id="section-insights">
      <p class="insight-text">Legacy insight one</p>
      <p class="insight-text">Legacy insight two</p>
    </section>
    <section id="section-quotes">
      <figure class="quote-card"><blockquote>Legacy quote</blockquote></figure>
    </section>
    """

    result = _build_view_model(
        content,
        [{"id": 7, "name": "Legacy Topic", "slug": "legacy-topic"}],
    )

    assert result["insights_count"] == 2
    assert result["quotes_count"] == 1
    assert result["topics_count"] == 1


def test_embedded_taxonomy_chips_do_not_inflate_public_topic_count() -> None:
    content = """
    <section id="taxonomy">
      <ul class="chip-list">
        <li>Category A</li><li>Tag A</li><li>Tag B</li><li>Tag C</li>
      </ul>
    </section>
    """

    result = _build_view_model(content, [])

    assert result["topics_count"] == 0
