# Shared Directory Hero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace five directory/archive hero variants with one configurable WordPress shortcode that renders the approved premium design and four live counters per context.

**Architecture:** Register `ml_archive_hero` on the existing canonical shortcode boundary. The renderer validates one of five closed contexts, owns all shared hero markup and editorial configuration, and delegates every counter to the existing `render_archive_metric()` method. Theme templates become context-only call sites and one neutral CSS namespace owns the complete responsive design.

**Tech Stack:** WordPress 6.9 block theme templates, PHP shortcodes, CSS, pytest source-contract tests, project WordPress CI checker, browser-harness/Chrome CDP.

---

## File Map

- Modify `tests/test_wordpress_market_bearing_portal.py`: enforce component call sites and exact four-counter contracts.
- Modify `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`: register and render the hero while reusing the metric renderer.
- Modify eight files under `Wordpress/wp-content/themes/marketlense/templates/`: replace duplicated hero trees with context shortcode calls.
- Modify `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`: replace page-specific variants with one neutral component.
- Modify `README_WORDPRESS.md`: document contexts, metrics, and customization ownership.
- Create browser evidence under `output/playwright/shared-directory-hero/`.

### Task 1: Establish The Shared Component Contract

**Files:**
- Modify: `tests/test_wordpress_market_bearing_portal.py`
- Test: `tests/test_wordpress_market_bearing_portal.py`

- [ ] **Step 1: Write the failing shared-component contract test**

Add path constants for `page-signals.html` and `page-briefings.html` beside the existing template constants. Replace the legacy hero test with:

```python
def test_archive_templates_use_shared_hero_with_four_dynamic_counts() -> None:
    templates = {
        PUBLISHERS_PAGE: "publishers",
        REPORT_ARCHIVE: "reports",
        GENERIC_ARCHIVE: "reports",
        TOPICS_PAGE: "topics",
        SIGNALS_PAGE: "signals",
        SIGNAL_ARCHIVE: "signals",
        BRIEFINGS_PAGE: "briefings",
        BRIEFING_ARCHIVE: "briefings",
    }

    for template, context in templates.items():
        content = template.read_text(encoding="utf-8")
        assert content.count(f'[ml_archive_hero context="{context}"]') == 1
        assert "ml-directory-hero-frame" not in content
        assert "[ml_archive_metric" not in content

    shortcodes = SHORTCODES.read_text(encoding="utf-8")
    assert "'ml_archive_hero' => 'render_archive_hero'" in shortcodes
    renderer = shortcodes[
        shortcodes.index("public function render_archive_hero") :
        shortcodes.index("public function render_archive_metric")
    ]
    expected_metric_orders = {
        "publishers": ["publishers", "reports", "regions", "topics"],
        "reports": ["reports", "publishers", "topics", "regions"],
        "topics": ["topics", "reports", "publishers", "regions"],
        "signals": ["signals", "reports", "topics", "publishers"],
        "briefings": ["briefings", "reports", "publishers", "topics"],
    }
    for context, entities in expected_metric_orders.items():
        context_start = renderer.index(f"'{context}' => [")
        next_context = renderer.find("\n            ],", context_start)
        context_config = renderer[context_start:next_context]
        positions = [
            context_config.index(f"['entity' => '{entity}'")
            for entity in entities
        ]
        assert positions == sorted(positions)
        assert context_config.count("['entity' =>") == 4
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py::test_archive_templates_use_shared_hero_with_four_dynamic_counts -q
```

Expected: FAIL because templates do not contain `ml_archive_hero` and the shortcode is not registered.

- [ ] **Step 3: Commit the failing test**

```powershell
git add -- tests/test_wordpress_market_bearing_portal.py
git commit -m "test: require shared directory hero"
```

### Task 2: Implement The Canonical Hero Renderer

**Files:**
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`
- Test: `tests/test_wordpress_market_bearing_portal.py`

- [ ] **Step 1: Register the shortcode**

Add next to `ml_archive_metric`:

```php
'ml_archive_hero' => 'render_archive_hero',
```

- [ ] **Step 2: Add the closed context renderer before `render_archive_metric()`**

Implement `render_archive_hero(array $attrs = []): string`. Normalize `context` with `sanitize_key`, return `''` for unknown contexts, and define these exact metric arrays:

```php
'publishers' => [
    ['entity' => 'publishers', 'label' => __('Publishers', 'marketlense-core')],
    ['entity' => 'reports', 'label' => __('Reports', 'marketlense-core')],
    ['entity' => 'regions', 'label' => __('Regions', 'marketlense-core')],
    ['entity' => 'topics', 'label' => __('Topics', 'marketlense-core')],
],
'reports' => [
    ['entity' => 'reports', 'label' => __('Reports', 'marketlense-core')],
    ['entity' => 'publishers', 'label' => __('Publishers', 'marketlense-core')],
    ['entity' => 'topics', 'label' => __('Topics', 'marketlense-core')],
    ['entity' => 'regions', 'label' => __('Regions', 'marketlense-core')],
],
'topics' => [
    ['entity' => 'topics', 'label' => __('Topics', 'marketlense-core')],
    ['entity' => 'reports', 'label' => __('Reports', 'marketlense-core')],
    ['entity' => 'publishers', 'label' => __('Publishers', 'marketlense-core')],
    ['entity' => 'regions', 'label' => __('Regions', 'marketlense-core')],
],
'signals' => [
    ['entity' => 'signals', 'label' => __('Signals', 'marketlense-core')],
    ['entity' => 'reports', 'label' => __('Reports', 'marketlense-core')],
    ['entity' => 'topics', 'label' => __('Topics', 'marketlense-core')],
    ['entity' => 'publishers', 'label' => __('Publishers', 'marketlense-core')],
],
'briefings' => [
    ['entity' => 'briefings', 'label' => __('Briefings', 'marketlense-core')],
    ['entity' => 'reports', 'label' => __('Reports', 'marketlense-core')],
    ['entity' => 'publishers', 'label' => __('Publishers', 'marketlense-core')],
    ['entity' => 'topics', 'label' => __('Topics', 'marketlense-core')],
],
```

Preserve the approved existing kicker/title/lead copy for each context. Render one semantic `<section class="ml-archive-hero">`, one frame, one copy `<header>`, one page-level `<h1>` with a context-derived ID, and one `.ml-archive-hero__metrics` group. Generate metrics only by calling `render_archive_metric()` with configured entity, label, and matching icon. Escape every output attribute/text through WordPress helpers.

- [ ] **Step 3: Validate PHP syntax**

```powershell
php -l Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php
```

Expected: `No syntax errors detected`.

### Task 3: Migrate Every Covered Template

**Files:**
- Modify: `page-publishers-directory.html`, `archive-ml_report.html`, `archive.html`, `page-topics-directory.html`, `page-signals.html`, `archive-ml_signal.html`, `page-briefings.html`, and `archive-ml_briefing.html` under `Wordpress/wp-content/themes/marketlense/templates/`.

- [ ] **Step 1: Replace only each inline hero block tree**

Keep header, `main`, content frame, index/browser shortcode, post content, footer, and page classes. Replace the hero tree with:

```html
<!-- wp:shortcode -->
[ml_archive_hero context="reports"]
<!-- /wp:shortcode -->
```

Use the context dictated by the route map. Do not alter downstream content.

- [ ] **Step 2: Run the focused test and verify GREEN**

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py::test_archive_templates_use_shared_hero_with_four_dynamic_counts -q
```

Expected: PASS.

- [ ] **Step 3: Commit test, renderer, and template migration**

```powershell
git add -- tests/test_wordpress_market_bearing_portal.py Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php Wordpress/wp-content/themes/marketlense/templates
git commit -m "feat: add shared directory hero"
```

### Task 4: Consolidate The Premium Visual Component

**Files:**
- Modify: `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`

- [ ] **Step 1: Remove obsolete page-specific hero rules**

Delete Publishers-only hero/background/metrics declarations and Reports-only hero/stats declarations. Preserve Publishers directory/card rules and Reports browser/filter/card rules. Remove obsolete responsive selectors for `.ml-publishers-hero-metrics`, `.ml-reports-hero-stats`, and page-scoped hero typography.

- [ ] **Step 2: Add one neutral component**

Implement the approved visual system under these owners:

```css
.ml-archive-hero {}
.ml-archive-hero::after {}
.ml-archive-hero__frame {}
.ml-archive-hero__copy {}
.ml-archive-hero__kicker {}
.ml-archive-hero__copy h1 {}
.ml-archive-hero__lead {}
.ml-archive-hero__metrics {}
.ml-archive-hero__metrics .ml-directory-principle {}
.ml-archive-hero__metrics .ml-archive-metric-icon {}
.ml-archive-hero__metrics .ml-archive-metric-value {}
.ml-archive-hero__metrics .ml-directory-principle strong {}
```

Use the approved navy gradient/grid, existing signal-blue accent and font tokens, restrained radii, translucent cards, and no JS/motion. Add distinct CSS-only `signals` and `briefings` icon variants. At existing breakpoints, stack copy above metrics, then move metric cards from four columns to two and finally one while preserving DOM order.

- [ ] **Step 3: Run WordPress checks**

```powershell
python scripts/ci/check_wordpress_subproject.py
```

Expected: exit 0.

- [ ] **Step 4: Commit styling**

```powershell
git add -- Wordpress/wp-content/themes/marketlense/assets/css/theme.css
git commit -m "style: unify directory heroes"
```

### Task 5: Document The Customization Boundary

**Files:**
- Modify: `README_WORDPRESS.md`

- [ ] **Step 1: Update documentation**

Document `[ml_archive_hero context="..."]`, the five supported contexts, exact counter ordering, and ownership: structure/configuration in `render_archive_hero()`, shared presentation in `.ml-archive-hero`. Replace Reports-only and Publishers-only hero descriptions.

- [ ] **Step 2: Run focused regressions**

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py -q
python scripts/ci/check_wordpress_subproject.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 3: Commit documentation**

```powershell
git add -- README_WORDPRESS.md
git commit -m "docs: describe shared archive hero"
```

### Task 6: Browser Verification And Refinement

**Files:**
- Create: `output/playwright/shared-directory-hero/*.png`
- Create: `output/playwright/shared-directory-hero/verification.json`
- Modify only on observed defects: shared renderer, shared CSS, or covered templates.

- [ ] **Step 1: Resolve the active local WordPress URL safely**

Use existing Chrome tabs with `browser-harness`, or approved local configuration without printing credentials. Open a new tab and preserve the user's current tab.

- [ ] **Step 2: Verify all five destinations at four widths**

At 1440x1000, 1024x900, 768x1024, and 390x844, verify Publishers, Reports, Topics, Signals, and Briefings. For each route, capture a screenshot and record:

```javascript
({
  h1: document.querySelector('.ml-archive-hero h1')?.textContent.trim(),
  metricCount: document.querySelectorAll('.ml-archive-hero .ml-archive-metric').length,
  labels: [...document.querySelectorAll('.ml-archive-hero .ml-archive-metric strong')].map(node => node.textContent.trim()),
  values: [...document.querySelectorAll('.ml-archive-hero .ml-archive-metric-value')].map(node => node.textContent.trim()),
  overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
})
```

Require one visible hero `h1`, four metric cards, four numeric visible values, and `overflow === false`.

- [ ] **Step 3: Verify resilience states**

Check visible keyboard focus in the header, reduced-motion emulation, 200% zoom, and text-spacing overrides. Reject clipping, overlap, truncated counter labels, or horizontal scrolling.

- [ ] **Step 4: Compare Publishers with the baseline**

Compare against `output/playwright/report-card-system/publishers-1440x1000.png`, `publishers-768x1024.png`, and `publishers-390x844.png`. Preserve the navy grid, white hierarchy, metric card elevation, and stacking behavior. Fix only the shared component if a regression appears.

- [ ] **Step 5: Store sanitized evidence**

Write `verification.json` with route, viewport, final URL, h1, metric labels/values, overflow, and screenshot path. Never store cookies, tokens, headers, or credentials.

### Task 7: Final Verification

- [ ] **Step 1: Run fresh affected gates**

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py -q
python scripts/ci/check_wordpress_subproject.py
git diff --check
git status --short
```

Expected: tests/checker pass, diff check is clean, and only intentional browser evidence remains uncommitted.

- [ ] **Step 2: Audit scope**

Confirm no changes to stats calculations, report cards, filters, listings, publishing behavior, routes, taxonomies, homepage, search, taxonomy-detail, or single-content heroes.

- [ ] **Step 3: Commit retained browser evidence**

```powershell
git add -- output/playwright/shared-directory-hero
git commit -m "test: verify shared directory heroes"
```

Skip only when repository ignore/convention makes evidence local-only; report the gap explicitly.

