# Methodology Shared Hero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Methodology to the existing shared archive hero with four live archive-coverage counters while preserving all page body content.

**Architecture:** Extend the closed `render_archive_hero()` context map and migrate the Methodology block template to the existing shortcode. Reuse `render_archive_metric()` and `.ml-archive-hero` without new rendering or styling paths.

**Tech Stack:** WordPress 6.9 block templates, PHP shortcode renderer, pytest source-contract tests, Playwright CLI browser verification.

---

### Task 1: Establish The Methodology Contract

**Files:**
- Modify: `tests/test_wordpress_market_bearing_portal.py`
- Test: `tests/test_wordpress_market_bearing_portal.py`

- [ ] **Step 1: Add Methodology to the shared-hero test**

Add:

```python
METHODOLOGY_PAGE = THEME / "templates" / "page-methodology.html"
```

Extend the existing template map with:

```python
METHODOLOGY_PAGE: "methodology",
```

Extend `expected_metric_orders` after `briefings` with:

```python
"methodology": ["reports", "publishers", "topics", "regions"],
```

Add assertions that the migrated Methodology template still contains every numbered step from `1. Ingest` through `6. Observe` and `Quality controls`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py::test_archive_templates_use_shared_hero_with_four_dynamic_counts -q
```

Expected: FAIL because `page-methodology.html` does not call `ml_archive_hero`.

### Task 2: Add The Context And Migrate The Template

**Files:**
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`
- Modify: `Wordpress/wp-content/themes/marketlense/templates/page-methodology.html`
- Test: `tests/test_wordpress_market_bearing_portal.py`

- [ ] **Step 1: Add the Methodology context**

Append this context after `briefings` in `render_archive_hero()`:

```php
'methodology' => [
    'kicker' => __('Methodology', 'marketlense-core'),
    'title' => __('How Market Bearing keeps published research connected to its evidence', 'marketlense-core'),
    'lead' => __('The pipeline combines deterministic extraction, typed validation, and structured editorial shaping so every published report brief is reproducible, reviewable, and source-aware.', 'marketlense-core'),
    'metrics_label' => __('Methodology archive coverage', 'marketlense-core'),
    'metrics' => [
        ['entity' => 'reports', 'label' => __('Reports', 'marketlense-core')],
        ['entity' => 'publishers', 'label' => __('Publishers', 'marketlense-core')],
        ['entity' => 'topics', 'label' => __('Topics', 'marketlense-core')],
        ['entity' => 'regions', 'label' => __('Regions', 'marketlense-core')],
    ],
],
```

- [ ] **Step 2: Migrate the Methodology template**

Change the main element to:

```html
<!-- wp:group {"tagName":"main","anchor":"main-content","className":"ml-directory-page","layout":{"type":"default"}} -->
<main id="main-content" class="wp-block-group ml-directory-page">
  <!-- wp:shortcode -->
  [ml_archive_hero context="methodology"]
  <!-- /wp:shortcode -->

  <!-- wp:group {"className":"ml-directory-content-frame ml-shell ml-page-frame","layout":{"type":"constrained"}} -->
  <div class="wp-block-group ml-directory-content-frame ml-shell ml-page-frame">
```

Move the existing two methodology grids, quality-controls section, and post-content block unchanged inside that content-frame group, then close the group before `</main>`. Remove only the old `ml-taxonomy-header` block.

- [ ] **Step 3: Verify GREEN and syntax**

Run:

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py::test_archive_templates_use_shared_hero_with_four_dynamic_counts -q
php -l Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php
```

Expected: focused test passes and PHP reports no syntax errors.

- [ ] **Step 4: Commit implementation**

```powershell
git add -- tests/test_wordpress_market_bearing_portal.py Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php Wordpress/wp-content/themes/marketlense/templates/page-methodology.html
git commit -m "feat: migrate methodology to shared hero"
```

### Task 3: Document, Verify, And Package

**Files:**
- Modify: `README_WORDPRESS.md`
- Create: `output/playwright/shared-directory-hero/methodology-1440x1000.png`
- Create: `output/playwright/shared-directory-hero/methodology-768x1024.png`
- Create: `output/playwright/shared-directory-hero/methodology-390x844.png`
- Modify: `output/playwright/shared-directory-hero/verification.json`
- Modify: `Wordpress/dist/marketlense-core.zip`
- Modify: `Wordpress/dist/marketlense.zip`

- [ ] **Step 1: Update canonical documentation**

Add Methodology to the supported-context sentence and document its counter order as `reports`, `publishers`, `topics`, `regions`.

- [ ] **Step 2: Run browser verification**

Extend the ignored local production-component harness with the exact Methodology copy and metric order. Capture 1440x1000, 768x1024, and 390x844 screenshots using Playwright. Assert one visible heading, four metric cards, numeric values, cards contained inside the hero, and no horizontal overflow.

- [ ] **Step 3: Run full regression gates**

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py -q
python scripts/ci/check_wordpress_subproject.py
php -l Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php
git diff --check
```

Expected: all tests and checks pass.

- [ ] **Step 4: Rebuild tracked release archives**

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\build-plugin-zip.ps1
bash Wordpress/scripts/build-theme-zip.sh
```

Confirm both ZIPs contain the modified shortcode/template files.

- [ ] **Step 5: Commit documentation, evidence, and packages**

```powershell
git add -- README_WORDPRESS.md output/playwright/shared-directory-hero Wordpress/dist/marketlense-core.zip Wordpress/dist/marketlense.zip
git commit -m "test: verify methodology shared hero"
```

- [ ] **Step 6: Verify clean final state**

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py -q
python scripts/ci/check_wordpress_subproject.py
git status --short
```

Expected: all checks pass and the working tree is clean.

