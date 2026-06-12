# Homepage Editorial Ledger Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct report Insights, Quotes, and Topics counters and implement the approved Editorial Ledger homepage treatment with tighter spacing and a vertically aligned line-and-dot header.

**Architecture:** Keep the current WordPress modular boundary. `marketlense-core` computes report presentation data from published post content and WordPress category terms; the `marketlense` block theme owns layout and visual presentation. The existing front-page patterns, shortcode entrypoints, record ordering, and navigation destinations remain unchanged.

**Tech Stack:** PHP 8.3, WordPress block theme markup, CSS, Python 3.12, pytest, browser-use Chromium.

---

## File Map

- Create `tests/fixtures/wordpress/report_view_model_harness.php`: executable WordPress-boundary fixture that invokes the real public `Report_View_Model_Builder::build()` method.
- Create `tests/test_wordpress_report_view_model_runtime.py`: behavior tests for current report markup, legacy markup, and public-category Topics semantics.
- Modify `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php`: support current report sections and count Topics from assigned WordPress categories.
- Modify `tests/test_wordpress_market_bearing_portal.py`: static, scoped CSS contract tests for the approved homepage treatment.
- Modify `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`: add the final scoped Editorial Ledger, spacing, header, hover, focus, responsive, and reduced-motion rules.
- Modify `README_WORDPRESS.md`: document counter semantics and the refreshed homepage behavior.
- Modify `README.md`: update the WordPress feature summary to match the implemented design.

## Task 1: Add Runtime Counter Regression Tests

**Files:**
- Create: `tests/fixtures/wordpress/report_view_model_harness.php`
- Create: `tests/test_wordpress_report_view_model_runtime.py`

- [ ] **Step 1: Create a real public-builder PHP harness**

Create `tests/fixtures/wordpress/report_view_model_harness.php` with a minimal WordPress boundary and no replacement of builder internals:

```php
<?php
declare(strict_types=1);

namespace {
    define('ABSPATH', __DIR__ . '/');

    final class WP_Post
    {
        public int $ID;
        public string $post_content;
        public string $post_excerpt;

        public function __construct(int $id, string $content, string $excerpt = '')
        {
            $this->ID = $id;
            $this->post_content = $content;
            $this->post_excerpt = $excerpt;
        }
    }

    final class WP_Term
    {
        public int $term_id;
        public string $name;
        public string $slug;

        public function __construct(int $term_id, string $name, string $slug)
        {
            $this->term_id = $term_id;
            $this->name = $name;
            $this->slug = $slug;
        }
    }

    $GLOBALS['ml_test_categories'] = [];

    function wp_strip_all_tags(string $value): string
    {
        return strip_tags($value);
    }

    function sanitize_text_field(string $value): string
    {
        return trim((string) preg_replace('/\s+/u', ' ', $value));
    }

    function wp_trim_words(string $value, int $limit, string $more = '...'): string
    {
        $words = preg_split('/\s+/u', trim($value)) ?: [];
        return count($words) <= $limit
            ? implode(' ', $words)
            : implode(' ', array_slice($words, 0, $limit)) . $more;
    }

    function get_post_meta(int $post_id, string $key, bool $single): string
    {
        return '';
    }

    function get_the_terms(int|WP_Post $post, string $taxonomy): array|false
    {
        if ($taxonomy === 'category') {
            return $GLOBALS['ml_test_categories'];
        }
        return false;
    }

    function get_the_title(WP_Post $post): string
    {
        return 'Fixture report';
    }

    function get_permalink(WP_Post $post): string
    {
        return 'https://example.test/reports/fixture/';
    }

    function get_the_date(string $format, WP_Post $post): string
    {
        return 'June 12, 2026';
    }

    function get_post_timestamp(WP_Post $post, string $field): int
    {
        return 1781222400;
    }
}

namespace MarketLense\Core {
    final class Meta
    {
        public const META_PUBLISHER = 'ml_publisher_name';
        public const META_TIME_PERIOD = 'ml_time_period';
        public const META_REGION = 'ml_region';
    }

    final class Taxonomies
    {
        public const CATEGORY_TAXONOMY = 'category';
        public const PUBLISHER_TAXONOMY = 'ml_publisher';
    }
}

namespace {
    require dirname(__DIR__, 3) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-content-parser.php';
    require dirname(__DIR__, 3) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php';

    $payload = json_decode((string) stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
    $GLOBALS['ml_test_categories'] = array_map(
        static fn (array $term): WP_Term => new WP_Term((int) $term['id'], (string) $term['name'], (string) $term['slug']),
        $payload['categories'] ?? []
    );
    $post = new WP_Post(101, (string) $payload['content']);
    $builder = new MarketLense\Core\Report_View_Model_Builder(new MarketLense\Core\Content_Parser());
    $view_model = $builder->build($post);
    echo json_encode([
        'insights_count' => $view_model['insights_count'],
        'quotes_count' => $view_model['quotes_count'],
        'topics_count' => $view_model['topics_count'],
        'citations_count' => $view_model['citations_count'],
    ], JSON_THROW_ON_ERROR);
}
```

- [ ] **Step 2: Add Python behavior tests that call the harness**

Create `tests/test_wordpress_report_view_model_runtime.py`:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "fixtures" / "wordpress" / "report_view_model_harness.php"


def _build_view_model(content: str, categories: list[dict[str, object]]) -> dict[str, int]:
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
      <ul class="chip-list"><li>Category A</li><li>Category B</li><li>Tag A</li><li>Tag B</li><li>Tag C</li></ul>
    </section>
    <p>7 evidence references</p>
    """
    categories = [
        {"id": 1, "name": "Advertising Strategy & Media", "slug": "advertising-media"},
        {"id": 2, "name": "Retail & Commerce Media", "slug": "retail-commerce-media"},
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
      <ul class="chip-list"><li>Category A</li><li>Tag A</li><li>Tag B</li><li>Tag C</li></ul>
    </section>
    """

    result = _build_view_model(content, [])

    assert result["topics_count"] == 0
```

- [ ] **Step 3: Run the runtime tests and verify RED**

Run:

```powershell
pytest -q tests/test_wordpress_report_view_model_runtime.py
```

Expected: the current-markup test fails because `insights_count`, `quotes_count`, and `topics_count` are `0`; the legacy test may pass for Insights and Quotes but must fail for category-based Topics until production logic changes.

- [ ] **Step 4: Commit the failing regression tests**

```powershell
git add tests/fixtures/wordpress/report_view_model_harness.php tests/test_wordpress_report_view_model_runtime.py
git commit -m "test: reproduce WordPress report counter regression"
```

## Task 2: Fix Report Counter Semantics

**Files:**
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php`
- Test: `tests/test_wordpress_report_view_model_runtime.py`

- [ ] **Step 1: Pass the post ID into count extraction**

Change the builder call and method signature:

```php
$counts = $this->extract_content_counts($post_id, $content, $insight_texts);
```

```php
private function extract_content_counts(int $post_id, string $content, array $insight_texts): array
```

- [ ] **Step 2: Count current and legacy Insights and Quotes, and category-backed Topics**

Use the current report classes as the primary contract while retaining legacy selectors:

```php
$counts = [
    'insights' => count($insight_texts),
    'quotes' => max(
        $this->count_nodes_by_class($content, 'section-quotes', 'quote-card'),
        $this->count_nodes_by_class($content, 'evidence', 'quote-feature')
            + $this->count_nodes_by_class($content, 'evidence', 'quote-card')
    ),
    'topics' => $this->count_public_topic_terms($post_id),
    'citations' => $this->extract_evidence_reference_count($content),
];
```

Update `extract_insight_texts()` to inspect both current and legacy selectors, normalize text, and deduplicate it:

```php
$queries = [
    $this->section_class_query('findings', 'finding-card'),
    $this->section_class_query('section-insights', 'insight-text'),
];

$items = [];
foreach ($queries as $query) {
    foreach ($xpath->query($query) ?: [] as $node) {
        if (! ($node instanceof \DOMNode)) {
            continue;
        }

        $text = $this->normalize_text($node->textContent);
        if ($text !== '') {
            $items[] = $text;
        }
    }
}

return array_values(array_unique($items));
```

Add a private category counter using the canonical taxonomy boundary:

```php
private function count_public_topic_terms(int $post_id): int
{
    $terms = get_the_terms($post_id, Taxonomies::CATEGORY_TAXONOMY);
    if (! is_array($terms)) {
        return 0;
    }

    $term_ids = [];
    foreach ($terms as $term) {
        if ($term instanceof \WP_Term) {
            $term_ids[(int) $term->term_id] = true;
        }
    }

    return count($term_ids);
}
```

Remove `count_chip_items()` if it has no remaining callers. Do not alter citation logic, cache behavior, publisher resolution, excerpts, or shortcode formatting.

- [ ] **Step 3: Run the runtime tests and verify GREEN**

```powershell
pytest -q tests/test_wordpress_report_view_model_runtime.py
```

Expected: `3 passed`.

- [ ] **Step 4: Run the existing WordPress rendering contracts**

```powershell
pytest -q tests/test_wordpress_market_bearing_portal.py tests/test_wordpress_report_rendering_contract.py
```

Expected: all tests pass with no warnings.

- [ ] **Step 5: Commit the counter fix**

```powershell
git add Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php tests/test_wordpress_report_view_model_runtime.py
git commit -m "fix: derive report counters from current artifacts"
```

## Task 3: Add RED Homepage Design Contracts

**Files:**
- Modify: `tests/test_wordpress_market_bearing_portal.py`

- [ ] **Step 1: Add scoped source-contract tests**

Add a small test-only rule extractor, then append tests that inspect the last scoped override for each selector rather than searching for generic values anywhere in the stylesheet:

```python
import re


def _last_css_rule(css: str, selector: str) -> str:
    matches = list(
        re.finditer(
            rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}",
            css,
            flags=re.DOTALL,
        )
    )
    assert matches, f"Missing CSS rule for {selector}"
    return matches[-1].group("body")


def test_homepage_uses_tighter_editorial_spacing_and_close_section_signals() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    home_shell = _last_css_rule(css, ".ml-home-shell")
    section_rule = _last_css_rule(css, ".ml-home-shell .ml-section-rule")

    assert "--ml-home-section-gap: clamp(3.5rem, 5vw, 4.5rem);" in home_shell
    assert "--ml-home-band-padding: clamp(3rem, 4.5vw, 4rem);" in home_shell
    assert "margin: 0.375rem 0 1rem;" in section_rule


def test_discovery_band_uses_the_approved_editorial_ledger_surface() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    discovery = _last_css_rule(css, ".ml-home-band-frame-discovery")
    themes = _last_css_rule(css, ".ml-home-band-discovery .ml-theme-list")

    assert "border: 1px solid var(--ml-border-subtle);" in discovery
    assert "border-radius: 0.875rem;" in discovery
    assert "box-shadow: 0 1.25rem 3.75rem rgba(8, 43, 84, 0.12);" in discovery
    assert "counter-reset: ml-theme;" in themes
    assert ".ml-home-band-discovery .ml-authority-item" in css


def test_desktop_header_aligns_controls_and_uses_signal_blue_nav_indicator() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")
    nav_stack = _last_css_rule(css, ".ml-header-navigation-stack")
    header_search = _last_css_rule(css, ".ml-header-search")
    nav_line = _last_css_rule(
        css, ".ml-primary-nav .wp-block-navigation-item__content::before"
    )

    assert "grid-template-columns: minmax(0, 1fr) minmax(14rem, 22rem);" in nav_stack
    assert "margin: 0;" in header_search
    assert "background: var(--ml-signal-blue);" in nav_line
    assert "background: transparent !important;" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
```

- [ ] **Step 2: Run the design tests and verify RED**

```powershell
pytest -q tests/test_wordpress_market_bearing_portal.py -k "editorial_spacing or editorial_ledger or aligns_controls"
```

Expected: the three new tests fail because the approved declarations are not present.

- [ ] **Step 3: Commit the failing design contracts**

```powershell
git add tests/test_wordpress_market_bearing_portal.py
git commit -m "test: define homepage editorial ledger contracts"
```

## Task 4: Implement the Editorial Ledger CSS

**Files:**
- Modify: `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`
- Test: `tests/test_wordpress_market_bearing_portal.py`

- [ ] **Step 1: Add scoped spacing variables and tighter homepage rhythm**

Append one final documented override section after the existing sticky-header rules:

```css
/* Homepage Editorial Ledger refresh: approved 2026-06-12. */
.ml-home-shell {
  --ml-home-section-gap: clamp(3.5rem, 5vw, 4.5rem);
  --ml-home-band-padding: clamp(3rem, 4.5vw, 4rem);
}

.ml-home-shell > .ml-home-band,
.ml-home-shell > .ml-home-section {
  margin-top: var(--ml-home-section-gap);
}

.ml-home-shell > .ml-home-band {
  padding-block: var(--ml-home-band-padding);
}

.ml-home-shell .ml-section-rule {
  margin: 0.375rem 0 1rem;
}
```

Keep the hero's first-child spacing intact with a scoped first-child reset if the cascade adds a gap above it.

- [ ] **Step 2: Align the desktop header into one visual row**

Override the final desktop header rules without changing `parts/header.html`:

```css
@media (min-width: 783px) {
  .ml-header-top {
    align-items: center;
    padding-block: 0.75rem;
  }

  .ml-header-top > p:first-child,
  .ml-header-cta {
    align-self: center;
    padding-top: 0;
  }

  .ml-header-navigation-stack {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) minmax(14rem, 22rem);
    align-items: center;
    gap: clamp(1rem, 2vw, 2rem);
  }

  .ml-header-search {
    width: 100%;
    margin: 0;
  }
}
```

At the existing `783px-1100px` range, reduce the search column to `minmax(12rem, 18rem)` if browser verification shows crowding. Preserve the existing hidden CTA behavior below `1100px` and the mobile disclosure behavior below `783px`.

- [ ] **Step 3: Refine the navigation line-and-dot interaction**

Use signal blue, a thin line, and no highlight fill:

```css
.ml-primary-nav .wp-block-navigation-item__content::before {
  height: 1px;
  background: var(--ml-signal-blue);
  transform: scaleX(0);
}

.ml-primary-nav .wp-block-navigation-item__content::after {
  inset-inline-end: -0.2rem;
  inset-block-end: -0.15rem;
  width: 0.375rem !important;
  height: 0.375rem !important;
  background: var(--ml-signal-blue) !important;
  transform: scale(0);
}

.ml-primary-nav .wp-block-navigation-item__content:hover,
.ml-primary-nav .wp-block-navigation-item__content:focus-visible,
.ml-primary-nav .wp-block-navigation-item.current-menu-item .wp-block-navigation-item__content,
.ml-primary-nav .wp-block-navigation-item__content[aria-current="page"] {
  color: var(--ml-brand-navy);
  background: transparent !important;
}
```

Retain the existing opacity/scale activation selector and visible keyboard focus behavior.

- [ ] **Step 4: Implement the shared elevated discovery surface**

Style the existing frame as the single Editorial Ledger surface:

```css
.ml-home-band-frame-discovery {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: clamp(2rem, 4vw, 4rem);
  padding: clamp(1.5rem, 3vw, 2.5rem);
  border: 1px solid var(--ml-border-subtle);
  border-radius: 0.875rem;
  background: #fff;
  box-shadow: 0 1.25rem 3.75rem rgba(8, 43, 84, 0.12);
}

.ml-home-band-frame-discovery > .ml-home-section {
  min-width: 0;
  margin: 0;
}

.ml-home-band-discovery .ml-theme-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  counter-reset: ml-theme;
}

.ml-home-band-discovery .ml-theme-item {
  position: relative;
  min-height: 5rem;
  padding: 1rem 3rem 1rem 1rem;
  border: 1px solid var(--ml-border-subtle);
  border-radius: 0.5rem;
  background: #fff;
  counter-increment: ml-theme;
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}

.ml-home-band-discovery .ml-theme-item::after {
  content: counter(ml-theme, decimal-leading-zero);
  position: absolute;
  inset-inline-end: 1rem;
  inset-block-start: 1rem;
  color: var(--ml-signal-blue);
  font-family: var(--ml-font-editorial);
  font-size: 0.75rem;
  font-weight: 700;
}

.ml-home-band-discovery .ml-theme-item:hover,
.ml-home-band-discovery .ml-theme-item:focus-within {
  border-color: color-mix(in srgb, var(--ml-signal-blue) 38%, var(--ml-border-subtle));
  box-shadow: 0 0.75rem 1.75rem rgba(8, 43, 84, 0.09);
  transform: translateY(-2px);
}

.ml-home-band-discovery .ml-theme-affordance {
  display: none;
}
```

- [ ] **Step 5: Implement Publisher Authority ledger rows and responsive stacking**

```css
.ml-home-band-discovery .ml-publisher-authority .ml-section-note {
  max-width: 42rem;
  margin-bottom: 1rem;
}

.ml-home-band-discovery .ml-authority-wall {
  display: grid;
  gap: 0;
}

.ml-home-band-discovery .ml-authority-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 1rem;
  min-height: 3.5rem;
  padding: 0.75rem 0;
  border-width: 0 0 1px;
  border-color: var(--ml-border-subtle);
  background: transparent;
  transition: background-color 180ms ease, padding-inline 180ms ease;
}

.ml-home-band-discovery .ml-authority-item:hover,
.ml-home-band-discovery .ml-authority-item:focus-within {
  padding-inline: 0.75rem;
  background: var(--ml-background-cool);
}

.ml-home-band-discovery .ml-authority-homepage {
  white-space: nowrap;
}

@media (max-width: 980px) {
  .ml-home-band-frame-discovery {
    grid-template-columns: 1fr;
    gap: 2rem;
  }

  .ml-publisher-authority-shell {
    padding-top: 2rem;
    border-top: 1px solid var(--ml-border-subtle);
  }
}

@media (max-width: 640px) {
  .ml-home-shell {
    --ml-home-section-gap: 2.5rem;
    --ml-home-band-padding: 2.25rem;
  }

  .ml-home-band-discovery .ml-theme-list {
    grid-template-columns: 1fr;
  }

  .ml-home-band-discovery .ml-authority-item {
    grid-template-columns: minmax(0, 1fr);
    gap: 0.5rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ml-home-band-discovery .ml-theme-item,
  .ml-home-band-discovery .ml-authority-item,
  .ml-primary-nav .wp-block-navigation-item__content::before,
  .ml-primary-nav .wp-block-navigation-item__content::after {
    transition: none;
  }

  .ml-home-band-discovery .ml-theme-item:hover,
  .ml-home-band-discovery .ml-theme-item:focus-within {
    transform: none;
  }
}
```

- [ ] **Step 6: Run the design tests and the WordPress subproject check**

```powershell
pytest -q tests/test_wordpress_market_bearing_portal.py
python scripts/ci/check_wordpress_subproject.py
```

Expected: all checks pass. The WP-CLI smoke portion may report a documented skip when the local runtime is unavailable.

- [ ] **Step 7: Commit the approved visual implementation**

```powershell
git add Wordpress/wp-content/themes/marketlense/assets/css/theme.css tests/test_wordpress_market_bearing_portal.py
git commit -m "feat: apply homepage editorial ledger design"
```

## Task 5: Document the Implemented Contracts

**Files:**
- Modify: `README_WORDPRESS.md`
- Modify: `README.md`

- [ ] **Step 1: Update WordPress-specific documentation**

Add the following facts to `README_WORDPRESS.md` under Dynamic Publishing Model:

```markdown
- Report card counters are derived from rendered report artifacts and public WordPress relationships: Insights count current `#findings .finding-card` records with legacy insight support, Quotes count current `#evidence` quote figures with legacy quote support, Topics count assigned public category terms, and Citations preserve evidence-reference counting.
- The homepage discovery band uses the Editorial Ledger treatment: Strategic Themes and Publisher Authority remain separate dynamic shortcode sections inside one elevated shared surface, with compact theme cards and publisher ledger rows.
- Homepage bands use a tighter vertical rhythm, section line-and-dot signals sit directly below headings, and desktop header navigation/search/briefing controls align on one visual centerline.
```

- [ ] **Step 2: Update the main README theme highlights**

Replace superseded Strategic Themes, Publisher Authority, and header bullets in `README.md` with concise descriptions of the Editorial Ledger surface, corrected counter semantics, tighter spacing, and signal-blue line-and-dot navigation state. Do not duplicate implementation details already in `README_WORDPRESS.md`.

- [ ] **Step 3: Run documentation and repository hygiene checks**

```powershell
pytest -q tests/test_repository_hygiene_gate.py tests/test_wordpress_market_bearing_portal.py tests/test_wordpress_report_view_model_runtime.py
```

Expected: all tests pass.

- [ ] **Step 4: Commit documentation**

```powershell
git add README.md README_WORDPRESS.md
git commit -m "docs: describe homepage counter and ledger contracts"
```

## Task 6: Verify Browser Behavior And Full Regression Scope

**Files:**
- No production edits expected. If verification finds a defect, return to the owning task and add a failing test before changing code.

- [ ] **Step 1: Run targeted automated tests**

```powershell
pytest -q tests/test_wordpress_report_view_model_runtime.py tests/test_wordpress_market_bearing_portal.py tests/test_wordpress_report_rendering_contract.py tests/test_wordpress_public_navigation.py
```

Expected: all tests pass.

- [ ] **Step 2: Run format, syntax, and WordPress checks**

```powershell
php -l Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php
php -l tests/fixtures/wordpress/report_view_model_harness.php
python scripts/ci/check_wordpress_subproject.py
```

Expected: both PHP files report no syntax errors and the WordPress checks pass or explicitly skip only unavailable WP-CLI smoke checks.

- [ ] **Step 3: Open the available homepage target in Chromium**

Prefer a configured local WordPress URL when available. Otherwise deploy the changed theme/plugin through the repository's existing deployment path and use the production URL only after deployment is confirmed.

```powershell
$env:PYTHONIOENCODING='utf-8'
browser-use open '<verified-homepage-url>'
browser-use state
```

- [ ] **Step 4: Verify desktop at 1440px and 1024px**

Use browser evaluation or Python mode to set the viewport and assert:

```javascript
({
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  header: ['.ml-brand-logo', '.ml-primary-nav', '.ml-header-search', '.ml-header-cta'].map(selector => {
    const element = document.querySelector(selector);
    const rect = element?.getBoundingClientRect();
    return {selector, centerY: rect ? Math.round(rect.top + rect.height / 2) : null};
  }),
  discoveryColumns: getComputedStyle(document.querySelector('.ml-home-band-frame-discovery')).gridTemplateColumns,
  featuredBadges: document.querySelector('.ml-featured-report')?.textContent.match(/\d{2}\s+(Insights|Quotes|Topics|Citations)/g),
})
```

Expected:

- `overflow` is `0`;
- logo, search, and CTA center lines are visually aligned;
- discovery surface has two columns at 1440px and a valid non-overflowing layout at 1024px;
- featured badges include `05 Insights`, `04 Quotes`, `02 Topics`, and `07 Citations` for the known production featured report.

Capture full-page screenshots at both widths.

- [ ] **Step 5: Verify mobile at 768px and 390px**

Expected:

- no horizontal overflow;
- mobile disclosure navigation remains usable;
- discovery sections stack within one shared surface;
- theme cards use one column at 390px;
- publisher names, counts, and profile actions do not overlap;
- section signals remain close to headings.

Capture full-page screenshots at both widths.

- [ ] **Step 6: Verify interactions and console**

Hover and keyboard-focus a primary navigation item and confirm:

- no filled highlight appears;
- the signal-blue line and terminal dot appear;
- focus remains visible;
- no console errors or warnings are produced.

Hover and focus a theme card and publisher row, confirming subtle elevation/background feedback. Repeat with reduced motion emulation if supported and confirm transforms are disabled.

- [ ] **Step 7: Run the full default test suite**

```powershell
pytest -q
```

Expected: the full non-integration suite passes. Report unrelated pre-existing failures separately without modifying unrelated code.

- [ ] **Step 8: Inspect final diff and commit any verification-only corrections**

```powershell
git diff --check
git status --short
git log -5 --oneline
```

If a verification correction was required, commit only the corrected owning files with a focused message. Do not add `.superpowers/` brainstorming artifacts.
