# Archive Browser Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Briefings and Signals use the Reports archive’s compact card geometry, live search, dependent filters, result count, sort controls, pagination, and sticky desktop controls.

**Architecture:** Extract the report archive browser into one private `Archive_Browser` owner in the WordPress plugin. `Shortcodes` remains the public compatibility facade and owns the type-specific card-rendering callback only. The browser owner owns URL state, canonical query constraints, filter facets, controls, pagination, and the shared archive markup. A shared CSS marker applies the Reports archive treatment to all three archives without changing homepage or article cards.

**Tech Stack:** PHP 8.2, WordPress 6.6 shortcodes and `WP_Query`, theme CSS, pytest, WP-CLI smoke test, Playwright CLI.

---

## File Structure

- Create: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-archive-browser.php` — archive query/state and shared markup owner.
- Modify: `Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php` — load the owner before the facade.
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php` — retain public shortcodes and delegate archive rendering.
- Modify: `Wordpress/wp-content/themes/marketlense/assets/css/theme.css` — scope the Reports archive visual contract to the shared marker.
- Create: `tests/test_wordpress_archive_browser_parity.py` — structural parity regression test.
- Modify: `Wordpress/scripts/smoke-test.sh` — runtime smoke checks for both new surfaces.
- Modify: `README_WORDPRESS.md` — record the shared browser contract.

### Task 1: Define the red parity contract

**Files:**

- Create: `tests/test_wordpress_archive_browser_parity.py`
- Modify: `tests/test_wordpress_briefing_cards.py`
- Modify: `tests/test_wordpress_signal_card_renderer.py`

- [ ] **Step 1: Add the focused failing test.**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "Wordpress" / "wp-content" / "plugins" / "marketlense-core"
SHORTCODES = PLUGIN / "includes" / "class-marketlense-core-shortcodes.php"
ARCHIVE_BROWSER = PLUGIN / "includes" / "class-marketlense-core-archive-browser.php"
BOOTSTRAP = PLUGIN / "marketlense-core.php"
THEME_CSS = ROOT / "Wordpress" / "wp-content" / "themes" / "marketlense" / "assets" / "css" / "theme.css"


def test_archives_delegate_to_one_browser_owner() -> None:
    source = SHORTCODES.read_text(encoding="utf-8")

    assert ARCHIVE_BROWSER.exists()
    assert "new Archive_Browser(" in source
    assert "return $this->archive_browser->render($attrs, Archive_Browser::REPORTS" in source
    assert "return $this->archive_browser->render($attrs, Archive_Browser::BRIEFINGS" in source
    assert "return $this->archive_browser->render($attrs, Archive_Browser::SIGNALS" in source
    assert "class-marketlense-core-archive-browser.php" in BOOTSTRAP.read_text(encoding="utf-8")


def test_shared_browser_exposes_controls_and_compact_cards() -> None:
    source = ARCHIVE_BROWSER.read_text(encoding="utf-8")

    assert 'class="ml-archive-browser-page ml-report-browser"' in source
    assert 'data-ml-live-filter-form' in source
    assert 'class="ml-report-browser-summary-value"' in source
    assert 'class="ml-report-sort-controls"' in source
    assert 'class="ml-report-browser-grid"' in source
    assert "$this->briefing_card_renderer->render($briefing, 'small')" in source
    assert "$this->signal_card_renderer->render($signal, 'small')" in source


def test_shared_archive_marker_receives_reports_geometry() -> None:
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".ml-archive-browser-page .ml-report-browser-utility-bar" in css
    assert ".ml-archive-browser-page .ml-report-browser-sidebar" in css
    assert ".ml-archive-browser-page .ml-report-browser-head" in css
    assert ".ml-archive-browser-page .ml-briefing-card--small" in css
    assert ".ml-archive-browser-page .ml-signal-card--small" in css
```

- [ ] **Step 2: Run the test to prove the missing owner fails.**

Run: `python -m pytest tests/test_wordpress_archive_browser_parity.py -q`

Expected: FAIL because the archive owner and facade delegations do not exist.

- [ ] **Step 3: Extend the type-specific archive tests.**

Add these assertions to the existing briefing/signal test modules:

```python
source = (ROOT / "Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-archive-browser.php").read_text(encoding="utf-8")
assert "Archive_Browser::BRIEFINGS" in source
assert "$this->briefing_card_renderer->render($briefing, 'small')" in source
assert "Archive_Browser::SIGNALS" in source
assert "$this->signal_card_renderer->render($signal, 'small')" in source
```

- [ ] **Step 4: Capture the complete red baseline.**

Run: `python -m pytest tests/test_wordpress_archive_browser_parity.py tests/test_wordpress_briefing_cards.py tests/test_wordpress_signal_card_renderer.py -q`

Expected: only the new owner/delegation assertions fail.

- [ ] **Step 5: Commit the red test contract.**

```powershell
git add tests/test_wordpress_archive_browser_parity.py tests/test_wordpress_briefing_cards.py tests/test_wordpress_signal_card_renderer.py
git commit -m "test: define archive browser parity contract"
```

### Task 2: Implement one private archive-browser owner

**Files:**

- Create: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-archive-browser.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`

- [ ] **Step 1: Create the typed owner and its injected canonical card collaborators.**

```php
final class Archive_Browser
{
    public const REPORTS = 'reports';
    public const BRIEFINGS = 'briefings';
    public const SIGNALS = 'signals';

    public function __construct(
        private Report_View_Model_Builder $report_view_model_builder,
        private Report_Card_Renderer $report_card_renderer,
        private Briefing_Card_View_Model_Builder $briefing_card_view_model_builder,
        private Briefing_Card_Renderer $briefing_card_renderer,
        private Signal_Card_View_Model_Builder $signal_card_view_model_builder,
        private Signal_Card_Renderer $signal_card_renderer
    ) {
    }

    /** @param array<string,mixed> $attrs */
    public function render(array $attrs, string $content_type): string
    {
        $definition = $this->definition($content_type);
        $filters = $this->selected_filters($definition);
        $query = new \WP_Query($this->query_args($definition, $filters, $attrs));
        return $this->render_shell($definition, $filters, $query);
    }
}
```

`definition()` must contain the exact post type, archive URL fallback, singular/plural labels, empty copy, and canonical schema metadata for each type. Reports use `Meta::apply_report_card_query_constraints()`; Briefings require `ml_briefing_card_schema_version=1.0`; Signals require `ml_signal_card_schema_version=1.0`. All types filter the registered category and `ml_publisher` taxonomies. Render period/region selects only when the canonical constrained query has non-sentinel values for that type.

- [ ] **Step 2: Move the existing browser mechanics, preserving Reports semantics.**

Move the browser’s current query-state normalization, sorting, dependent facet counting, active-filter chips, sort controls, pagination, and filter-JavaScript enqueue from `Shortcodes` to `Archive_Browser`. The owner must emit this unchanged structural contract:

```php
<section class="ml-archive-browser-page ml-report-browser" aria-label="<?php echo esc_attr($definition['browser_label']); ?>">
    <div class="ml-report-browser-utility-bar"><?php echo $this->render_utility_bar($definition, $filters); ?></div>
    <div class="ml-report-browser-layout">
        <aside class="ml-report-browser-sidebar"><?php echo $this->render_filter_rail($definition, $filters); ?></aside>
        <div class="ml-report-browser-results">
            <div class="ml-report-browser-head">
                <span class="ml-report-browser-summary-value"><?php echo esc_html($count_label); ?></span>
                <?php $this->render_sort_controls($archive_url, $preserved_state_args, $selected_sort); ?>
            </div>
            <div class="ml-report-browser-grid"><?php echo $this->render_cards($query, $content_type); ?></div>
        </div>
    </div>
</section>
```

- [ ] **Step 3: Render each card with its existing renderer at small density.**

```php
private function render_card(WP_Post $post, string $content_type): string
{
    return match ($content_type) {
        self::REPORTS => $this->render_report_card($post),
        self::BRIEFINGS => $this->render_briefing_card($post),
        self::SIGNALS => $this->render_signal_card($post),
        default => '',
    };
}

private function render_briefing_card(WP_Post $post): string
{
    $briefing = $this->briefing_card_view_model_builder->build($post);
    return ($briefing['card_contract_valid'] ?? false) === true
        ? $this->briefing_card_renderer->render($briefing, 'small')
        : '';
}

private function render_signal_card(WP_Post $post): string
{
    $signal = $this->signal_card_view_model_builder->build($post);
    return ($signal['card_contract_valid'] ?? false) === true
        ? $this->signal_card_renderer->render($signal, 'small')
        : '';
}
```

- [ ] **Step 4: Preserve public shortcode and fallback behavior.**

```php
public function render_report_browser(array $attrs = []): string
{
    return $this->archive_browser->render($attrs, Archive_Browser::REPORTS);
}

public function render_briefings_index(array $attrs = []): string
{
    return $this->archive_browser->render($attrs, Archive_Browser::BRIEFINGS);
}

public function render_signals_index(array $attrs = []): string
{
    return $this->archive_browser->render($attrs, Archive_Browser::SIGNALS);
}
```

Keep `render_briefing_archive()` and `render_signal_archive()` as their current aliases. When no standalone signals exist, retain the source-backed report signal fallback but render it in the shared browser shell using the Reports query/card definition so its controls, count, and layout remain consistent.

- [ ] **Step 5: Load the owner and run the green test/syntax gate.**

```php
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-archive-browser.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-shortcodes.php';
```

Run:

```powershell
php -l Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-archive-browser.php
php -l Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php
php -l Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php
python -m pytest tests/test_wordpress_archive_browser_parity.py tests/test_wordpress_briefing_cards.py tests/test_wordpress_signal_card_renderer.py -q
```

Expected: every command passes.

- [ ] **Step 6: Commit the owner/facade change.**

```powershell
git add Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-archive-browser.php Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php
git commit -m "feat: unify report briefing and signal archives"
```

### Task 3: Share Reports card geometry and sticky behavior

**Files:**

- Modify: `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`
- Test: `tests/test_wordpress_archive_browser_parity.py`

- [ ] **Step 1: Apply the current Reports archive selector group to the shared marker.**

Replace the final Reports archive block selector prefix with the shared marker, retaining each existing declaration and breakpoint:

```css
:is(.ml-reports-archive-page, .ml-archive-browser-page) .ml-report-browser-utility-bar { position: sticky; top: 4.75rem; z-index: 30; }
:is(.ml-reports-archive-page, .ml-archive-browser-page) .ml-report-browser-sidebar { position: sticky; top: 11.5rem; z-index: 18; }
:is(.ml-reports-archive-page, .ml-archive-browser-page) .ml-report-browser-head { position: sticky; top: 11.5rem; z-index: 20; }
:is(.ml-reports-archive-page, .ml-archive-browser-page) .ml-report-browser-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.25rem; }
```

- [ ] **Step 2: Apply the compact Reports card surface only inside the shared archive.**

```css
.ml-archive-browser-page .ml-briefing-card--small,
.ml-archive-browser-page .ml-signal-card--small {
  border-radius: 0.5rem;
  box-shadow: 0 1px 2px rgba(8, 31, 61, 0.04), 0 0.625rem 1.75rem rgba(8, 31, 61, 0.08);
}

.ml-archive-browser-page .ml-briefing-card--small .ml-briefing-card__media,
.ml-archive-browser-page .ml-signal-card--small .ml-signal-card__media {
  aspect-ratio: 16 / 9;
  border-radius: 0.5rem 0.5rem 0 0;
}
```

Do not change medium/large styles or homepage selectors.

- [ ] **Step 3: Run source and WordPress gates.**

Run:

```powershell
python -m pytest tests/test_wordpress_archive_browser_parity.py -q
python scripts/ci/check_wordpress_subproject.py
```

Expected: PASS.

- [ ] **Step 4: Commit the visual parity change.**

```powershell
git add Wordpress/wp-content/themes/marketlense/assets/css/theme.css tests/test_wordpress_archive_browser_parity.py
git commit -m "style: align briefing and signal archive cards"
```

### Task 4: Add live-smoke coverage and document the common surface

**Files:**

- Modify: `Wordpress/scripts/smoke-test.sh`
- Modify: `README_WORDPRESS.md`

- [ ] **Step 1: Assert the shared browser controls are rendered for both routes.**

```bash
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/signals/'))), 'ml-archive-browser-page') !== false ? '1' : '0';" "Signals shared archive browser rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/signals/'))), 'ml-report-filter-form') !== false ? '1' : '0';" "Signals archive filter UI rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/signals/'))), 'ml-report-browser-summary-value') !== false ? '1' : '0';" "Signals archive count rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/briefings/'))), 'ml-archive-browser-page') !== false ? '1' : '0';" "Briefings shared archive browser rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/briefings/'))), 'ml-report-filter-form') !== false ? '1' : '0';" "Briefings archive filter UI rendered"
require_php_true "echo strpos((string) wp_remote_retrieve_body(wp_remote_get(home_url('/briefings/'))), 'ml-report-browser-summary-value') !== false ? '1' : '0';" "Briefings archive count rendered"
```

- [ ] **Step 2: State the public contract in `README_WORDPRESS.md`.**

Add: “`[ml_report_browser]`, `[ml_briefings_index]`, and `[ml_signals_index]` render the common filtered archive browser: sticky live search, selected-filter chips, compact sort controls, dependent facets, current-view count, pagination, and the canonical compact card variant for the selected content type.”

- [ ] **Step 3: Run the source/documentation check.**

Run:

```powershell
python scripts/ci/check_wordpress_subproject.py
git diff --check
```

Expected: PASS with no whitespace errors.

- [ ] **Step 4: Commit runtime/documentation coverage.**

```powershell
git add Wordpress/scripts/smoke-test.sh README_WORDPRESS.md
git commit -m "docs: document shared archive browser"
```

### Task 5: Verify, deploy, and confirm in real browsers

**Files:**

- Create: `output/playwright/archive-browser-parity-desktop.png`
- Create: `output/playwright/archive-browser-parity-mobile.png`

- [ ] **Step 1: Run the complete focused local gate.**

Run:

```powershell
python -m pytest tests/test_wordpress_archive_browser_parity.py tests/test_wordpress_briefing_cards.py tests/test_wordpress_signal_card_renderer.py tests/test_wordpress_report_card_migration.py -q
python scripts/ci/check_wordpress_subproject.py
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 2: Run the optional WP-CLI integration smoke when its configured runtime is available.**

```powershell
$env:RUN_WORDPRESS_SMOKE = '1'
python scripts/ci/check_wordpress_subproject.py
```

Expected: `Smoke test passed.` If WP-CLI is unavailable, explicitly record that this local integration gate did not run.

- [ ] **Step 3: Build the authorized deployable artifacts.**

```powershell
Wordpress/scripts/build-plugin-zip.ps1
Wordpress/scripts/build-theme-zip.ps1
```

Expected: both scripts print their ZIP artifact paths.

- [ ] **Step 4: Install those ZIPs through the authorized WordPress administration channel and purge the site cache.**

Upload only the freshly built plugin/theme ZIPs; do not upload source directories or alter content. Confirm that the active theme/plugin versions are current before browser validation.

- [ ] **Step 5: Validate desktop behavior with a real browser.**

Use a fresh snapshot before each interaction:

```powershell
$pw = 'C:\Users\Михаил\.codex\skills\playwright\scripts\playwright_cli.sh'
bash $pw open http://marketlense.medianewsonline.com/reports/ --headed
bash $pw snapshot
bash $pw open http://marketlense.medianewsonline.com/briefings/ --headed
bash $pw snapshot
bash $pw open http://marketlense.medianewsonline.com/signals/ --headed
bash $pw snapshot
```

For all three routes, confirm search, filters, count, sort controls, a three-column compact grid, 16:9 small-card media, and sticky utility/sidebar/result controls after scroll. Submit a real search on Briefings and Signals and confirm count/context changes. Save full-page desktop screenshots.

- [ ] **Step 6: Validate mobile behavior at 390px width.**

Refresh Briefings and Signals and confirm one column, no horizontal scroll, static controls, 16:9 images, and retained query state. Save `output/playwright/archive-browser-parity-mobile.png`.

- [ ] **Step 7: Commit source/test/documentation changes only.**

```powershell
git status --short
git add Wordpress/wp-content/plugins/marketlense-core Wordpress/wp-content/themes/marketlense/assets/css/theme.css Wordpress/scripts/smoke-test.sh README_WORDPRESS.md tests
git commit -m "feat: align intelligence archive browsers"
```

Expected: only intentionally ignored browser screenshots and ZIPs remain untracked.
