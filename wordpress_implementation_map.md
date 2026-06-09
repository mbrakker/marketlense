# WordPress Implementation Map

This map covers the WordPress front end in:

- `Wordpress/wp-content/themes/marketlense`
- `Wordpress/wp-content/plugins/marketlense-core`
- `Wordpress/scripts`

The WordPress-specific readme is `README_WORDPRESS.md`. The plugin package readme is `Wordpress/wp-content/plugins/marketlense-core/readme.txt`.

## 1. Homepage Patterns And Render Order

The homepage is defined by `Wordpress/wp-content/themes/marketlense/templates/front-page.html`.

Render order:

1. Header template part.
2. `marketlense/hero-institutional`, which leads with native WordPress search, `[ml_hero_snapshot]`, and the full-width `[ml_home_metrics]` trust band.
3. Current evidence band:
   - `marketlense/featured-digest` -> `[ml_featured_digest]`
   - `marketlense/featured-briefing` -> `[ml_featured_briefing]`
4. Signals band:
   - `marketlense/this-week-intelligence` -> `[ml_intelligence_signals show_publishers="1"]`
5. `marketlense/report-grid` -> `[ml_latest_reports limit="6"]`
6. Discovery band:
   - `marketlense/strategic-themes` -> `[ml_strategic_themes limit="6"]`
   - `marketlense/publisher-authority` -> `[ml_publisher_authority limit="12"]`
7. `marketlense/how-it-works`
8. `marketlense/newsletter-cta`
9. Footer template part.

Additional homepage-capable patterns exist but are not rendered by `front-page.html`:

- `marketlense/hero-evidence-led`
- `marketlense/hero-executive-brief`
- `marketlense/home-metrics`

## 2. Archive, Search, Category, And Publisher Templates

The archive and discovery templates live under `Wordpress/wp-content/themes/marketlense/templates`.

- `archive.html` and `archive-ml_report.html` render the same editorial archive hero, dynamic `[ml_archive_metric]`, and `[ml_report_browser per_page="12" show_filters="1" show_pagination="1" context="auto"]`.
- `search.html` renders a search header with the core search block, then calls the same `[ml_report_browser ... context="auto"]`.
- `category.html` renders a strategic theme hero, current-term coverage, and `[ml_report_browser ... context="auto"]`.
- `taxonomy-ml_publisher.html` renders the publisher hero, `[ml_publisher_profile]`, current-term coverage, and `[ml_report_browser ... context="auto"]`.
- `archive-ml_signal.html` calls `[ml_signals_index per_page="12"]`.
- `archive-ml_briefing.html` calls `[ml_briefings_index per_page="12"]`.
- `single.html`, `single-ml_report.html`, `single-ml_signal.html`, and `single-ml_briefing.html` all delegate to `parts/single-content.html`, which renders post content through the ingest report shell.

Page templates with shortcode-driven front-end surfaces:

- `page-signals.html` calls `[ml_signals_index per_page="12"]`.
- `page-briefings.html` calls `[ml_briefings_index per_page="12"]`.
- `page-topics-directory.html` calls `[ml_topics_directory]`.
- `page-publishers-directory.html` calls `[ml_publishers_directory]`.
- `page-about.html` calls `[ml_home_metrics]`.
- `page-contact.html`, `page-submit-a-report.html`, `404.html`, `parts/header.html`, and `parts/footer.html` use `[ml_button_link]`.
- `parts/nav.html` calls `[ml_primary_nav]`.
- `parts/footer.html` calls `[ml_footer_nav]` and `[ml_footer_nav menu="utilities"]`.

## 3. Shortcode Entrypoints And Output Responsibilities

Shortcodes are registered in `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`.

- `[ml_report_browser]`: filtered and paginated report browser for `ml_report` plus digest-like core posts, with search, category, publisher, period, and sort handling.
- `[ml_latest_reports]`: latest report card grid.
- `[ml_home_metrics]`: report, publisher, topic, briefing, signal, and citation counters derived from published records.
- `[ml_hero_snapshot]`: current portal snapshot used in the homepage hero panel.
- `[ml_featured_digest]`: latest report feature card.
- `[ml_featured_briefing]`: homepage Featured Briefing card. Uses published Briefing content only and renders an explicit institutional empty state when no validated Briefing is available.
- `[ml_intelligence_signals]`: weekly topic and publisher signal columns.
- `[ml_strategic_themes]`: top category or theme cards.
- `[ml_publisher_authority]`: top publisher authority cards.
- `[ml_signals_index]`: canonical Signals landing surface for published Signals, with source-backed report-signal fallback.
- `[ml_briefings_index]`: canonical Briefings landing surface for published Briefings, with institutional empty state fallback.
- `[ml_topics_directory]`: category directory cards.
- `[ml_publishers_directory]`: publisher directory cards with archive, homepage, and insights links.
- `[ml_publisher_profile]`: publisher taxonomy profile block.
- `[ml_signal_archive]`: legacy compatibility alias for `[ml_signals_index]`.
- `[ml_briefing_archive]`: legacy compatibility alias for `[ml_briefings_index]`.
- `[ml_button_link]`: internal CTA button helper.
- `[ml_inline_link]`: internal inline link helper.
- `[ml_brand_logo]`: canonical Market Bearing wordmark shared by the header and footer.
- `[ml_archive_metric]`: dynamic global or current-term coverage metric used by archive heroes.
- `[ml_primary_nav]`: static primary navigation renderer.
- `[ml_footer_nav]`: static footer navigation renderer.

The shortcode class also hooks `render_block` so unresolved Market Bearing shortcodes in block template output are rendered before response output.

## 4. CSS Systems And Reusable Card/Surface Classes

The visual system is split between:

- `Wordpress/wp-content/themes/marketlense/theme.json` for WordPress design tokens, palettes, typography, spacing, radii, shadows, gradients, and template parts.
- `Wordpress/wp-content/themes/marketlense/assets/css/theme.css` for the main front-end CSS system.
- `Wordpress/wp-content/themes/marketlense/style.css` for the theme header metadata.

Reusable class families:

- Layout shells: `ml-shell`, `ml-home-shell`, `ml-page-frame`, `ml-home-band`, `ml-home-band-frame`.
- Section typography: `ml-section-heading`, `ml-section-anchor`, `ml-section-kicker`, `ml-section-title`, `ml-section-note`, `ml-section-rule`.
- Shared surfaces: `ml-surface-card`, `ml-surface-card--standard`, `ml-surface-card--compact`, `ml-card`, `ml-surface-stack`.
- Cards: `ml-report-card`, `ml-featured-digest-card`, `ml-theme-item`, `ml-authority-item`, `ml-process-card`, `ml-directory-card`, `ml-page-card`, `ml-hero-panel`.
- Controls and chips: `ml-button`, `ml-button-primary`, `ml-button-outline`, `ml-chip`, `ml-filter-chip`, `ml-pagination`.
- Header and footer systems: `ml-site-header`, `ml-header-*`, `ml-primary-nav`, `ml-site-footer`, `ml-footer-*`.

Template parts also include local front-end behavior:

- `parts/header.html` uses the canonical wordmark and native shortcode navigation without local CSS.
- `functions.php` enqueues `assets/css/theme.css`, `assets/js/reveal.js`, and `assets/js/report-interactions.js` for singular `ml_report` and core `post` pages.

## 5. Smoke And Verification Scripts Coupled To Template Changes

Update these scripts when template names, page slugs, shortcode output classes, nav targets, or homepage section copy change.

- `Wordpress/scripts/smoke-test.sh` is the main template-sensitive verifier. It checks required template filenames, front page and archive HTTP 200s, report filters, required pages, key rendered class names, direct rendering for `[ml_featured_briefing]`, `[ml_briefings_index]`, and `[ml_signals_index]`, homepage section text, nav URLs, and raw shortcode leakage.
- `Wordpress/scripts/provision-site-structure.sh` creates or updates the required static pages through WP-CLI.
- `Wordpress/scripts/provision-site-structure-rest.py` creates or updates the same static pages through REST fallback and warns if the `marketlense` theme is not active.
- `Wordpress/scripts/sync-local-wordpress.ps1` syncs the theme and plugin source trees into a local WordPress install and must stay aligned with source paths.
- `Wordpress/scripts/build-theme-zip.sh`, `Wordpress/scripts/build-plugin-zip.sh`, and `Wordpress/scripts/build-plugin-zip.ps1` package the front-end artifacts and should be reviewed when packaging-relevant files move.

## Validation

- This audit covers homepage patterns, archive/search/category/publisher templates, shortcode entrypoints, CSS systems, and smoke/verification scripts.
- This document is documentation-only and does not modify WordPress runtime behavior.
- Python ingestion and orchestration under `src/` are outside the scope of this map.
