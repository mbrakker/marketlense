# WordPress Rendering Subproject

This folder contains the WordPress rendering layer for Market Lense:

- Block theme: `wp-content/themes/marketlense`
- Core domain plugin: `wp-content/plugins/marketlense-core`
- Packaging and smoke scripts: `Wordpress/scripts/*`

## Scope

Included:

- FSE block theme templates/parts/patterns for editorial rendering
- WordPress plugin for `ml_report` CPT + taxonomy/meta domain model
- Zip packaging scripts for backoffice installation
- `wp-cli` smoke test script

Excluded:

- Docker runtime stack
- Python publish/orchestration logic in `src/`

## Runtime Expectation

This repo does not ship a local WordPress runtime. Use an existing local or hosted WordPress 6.6+ / PHP 8.2 environment, then install the packaged plugin/theme ZIPs through WP Admin.

## Current Structure

```text
Wordpress/
  config/
    publisher-homepages.json
  wp-content/
    themes/
      marketlense/
        style.css
        theme.json
        functions.php
        screenshot.png
        assets/{css,js}
        templates/*
        parts/*
        patterns/*
    plugins/
      marketlense-core/
        marketlense-core.php
        uninstall.php
        readme.txt
        includes/*
  scripts/
    build-theme-zip.sh
    build-plugin-zip.sh
    provision-site-structure.sh
    seed-publisher-homepages.sh
    smoke-test.sh
  dist/
```

## Plugin Contract (`marketlense-core`)

Plugin slug: `marketlense-core`  
Primary responsibilities:

- Registers custom post type `ml_report` (`show_in_rest=true`, REST base `ml_report`)
- Registers taxonomies:
  - native WordPress `category` support on `ml_report` for public topic/archive/filter UX
  - `ml_publisher`
- keeps legacy `ml_topic` taxonomy data internal only for backward compatibility; it is not a public archive/filter surface
- Registers publisher term metadata:
  - `ml_publisher_homepage` (REST-exposed, sanitized URL)
- Registers and exposes report metadata keys:
  - `ml_file_id`
  - `ml_publisher_name`
  - `ml_time_period`
  - `ml_region`
- Synchronizes metadata/taxonomy projections from published digest content and existing tags/categories on save.
- Provides shortcodes:
  - `[ml_report_browser]` (URL filters: `category`, `ml_publisher`; legacy `ml_topic` query params still map to categories)
  - `[ml_home_metrics]`
  - `[ml_featured_digest]`
  - `[ml_intelligence_signals]`
  - `[ml_strategic_themes]`
  - `[ml_publisher_authority]`
  - `[ml_topics_directory]`
  - `[ml_publishers_directory]`

## Theme Contract (`marketlense`)

The block theme is organized as an editorial intelligence portal:

- Full-site editing templates and template parts for header, footer, archives, search, and ingest-first singles
- Homepage assembled from reorderable patterns
- Theme-driven editorial token system in `theme.json`
- Minimal JS only for singular report interaction parity

## Provision Site IA (Pages + Navigation + Publisher Homepages)

After plugin/theme activation, provision the editorial IA:

```bash
bash Wordpress/scripts/provision-site-structure.sh
bash Wordpress/scripts/seed-publisher-homepages.sh
```

What `provision-site-structure.sh` does:

- Creates/updates required pages (About, Methodology, Topics directory, Publishers directory, Submit a Report, Contact, Privacy, Terms).
- Publishes pages idempotently (no duplicates on rerun).
- Navigation is provided directly by static block-theme template parts (`parts/nav.html`, `parts/footer.html`); the provisioning script does not create classic menu locations.
- If `wp-cli` is unavailable in your environment, automatically falls back to REST (`provision-site-structure-rest.py`) and provisions the same required pages.

What `seed-publisher-homepages.sh` does:

- Reads `Wordpress/config/publisher-homepages.json`.
- Ensures current publisher terms exist in `ml_publisher`.
- Upserts `ml_publisher_homepage` term meta for each publisher.
- Is idempotent and safe to rerun.
- Falls back to REST (`seed-publisher-homepages-rest.py`) when `wp-cli` cannot access a local WP core.
- In REST mode, if `marketlense-core` is installed but inactive, it auto-activates the plugin before seeding taxonomy terms.

## Local Windows Workflow

If your local WordPress runtime cannot safely follow theme symlinks, keep the local theme/plugin as real directories and sync from the repo instead of linking.

One-shot sync:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\sync-local-wordpress.ps1 `
  -LocalWpPath 'C:\Users\name\Studio\marker-lense'
```

Watch mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\sync-local-wordpress.ps1 `
  -LocalWpPath 'C:\Users\name\Studio\marker-lense' `
  -Watch
```

Notes:

- The script mirrors repo changes into the local theme/plugin directories with `robocopy /MIR`.
- `-SyncTarget theme` or `-SyncTarget plugin` limits sync to one side.
- The local target directories must be real directories, not symlinks/junctions.
- This avoids block-theme `theme.json` failures caused by local stacks that resolve symlinks through `/internal/symlinks/...`.

## Build ZIPs For WP Admin Upload

From repo root:

```bash
bash Wordpress/scripts/build-plugin-zip.sh
bash Wordpress/scripts/build-theme-zip.sh
```

Build scripts use `zip` when available and automatically fall back to Python (`python`/`python3`/`py`) or local virtualenv interpreters (`../.venv/Scripts/python.exe`, `../.venv/bin/python`) when `zip` is not installed.

On Windows in this workspace, repo-local helper shims are also available under `tools/`: `php`, `composer`, and `wp` point to `tools/php82/php.exe` plus the user-space PHAR installs in `%USERPROFILE%\\.local\\bin`.

Outputs:

```text
Wordpress/dist/marketlense-core.zip
Wordpress/dist/marketlense.zip
```

Install order in WordPress Admin:

1. `Plugins -> Add New -> Upload Plugin` -> upload `marketlense-core.zip` -> activate.
2. `Appearance -> Themes -> Add New -> Upload Theme` -> upload `marketlense.zip` -> activate.
3. Run IA/data provisioning from this repo:
   - `bash Wordpress/scripts/provision-site-structure.sh`
   - `bash Wordpress/scripts/seed-publisher-homepages.sh`
   These scripts auto-select `wp-cli` mode when available, otherwise REST mode.

## Smoke Test

If `wp-cli` is available:

```bash
bash Wordpress/scripts/smoke-test.sh
```

What it validates:

- Plugin `marketlense-core` is installed and can activate.
- Theme `marketlense` is installed and can activate.
- Required theme templates exist.
- REST endpoints resolve for `ml_report` and `ml_publisher`.
- Front page, report archive, and report filter URLs return HTTP `200`.
- Required site pages return HTTP `200`.
- Topics and publishers directory shortcodes render.
- Primary navigation links are present in rendered output.
- Front page editorial sections render (`Featured Digest`, `This Week in Intelligence`, `Weekly Executive Intelligence Briefing`, header search).
- A published `ml_report` URL returns HTTP `200` (seeded if missing).

Optional environment controls:

- `WP_CLI_BIN` (default: `wp`)
- `WP_PATH` (preferred on Windows/local installs; example: `C:\Users\name\Studio\marker-lense`)
- `WP_CLI_FLAGS` (example: `--path=/var/www/html --allow-root`)
- On Windows Bash environments (`bash.exe`, Git Bash, WSL calling Windows `cmd.exe`), the provisioning and publisher-seeding scripts now detect `wp.bat`/`wp.cmd` via `cmd.exe` automatically, so `WP_CLI_BIN=wp` continues to work for local installs.
- `PROVISION_STRUCTURE` (`1|0`, default `1`)
- `SEED_PUBLISHERS` (`1|0`, default `1`)
- `WP_SITE_URL` (required for REST fallback provisioning/seeding)
- `WP_USERNAME` + `WP_APP_PASSWORD` (or `WP_BEARER_TOKEN`) for REST fallback auth

If `wp-cli` is unavailable, smoke test exits with a skip message.

## Automated Verification

The repo now includes a minimal WordPress verification harness for CI and local use:

```bash
python scripts/ci/check_wordpress_subproject.py
```

What it validates:

- no hardcoded root-relative internal links remain in theme `parts/`, `patterns/`, or `templates/`
- no public `taxonomy-ml_topic.html` template is shipped
- PHP syntax for theme/plugin PHP files
- shell syntax for `Wordpress/scripts/*.sh`
- optional live smoke test only when `RUN_WORDPRESS_SMOKE=1` and `wp-cli` is available

The main CI workflow runs this harness automatically after installing PHP CLI.

## Archive and Directory UX

- `templates/archive-ml_report.html` now renders `[ml_report_browser]`, which provides server-side report filtering at `/reports/` via:
  - `?category=<category-slug>` mapped to native WordPress categories assigned to published `ml_report` posts
  - `?ml_publisher=<slug>` mapped to the `ml_publisher` taxonomy
- Backward compatibility: older `?ml_topic=<slug>` links are still accepted and normalized onto the same native category filter.
- Homepage editorial sections are backed by shortcode-driven intelligence components:
  - `[ml_home_metrics]`
  - `[ml_featured_digest]`
  - `[ml_intelligence_signals]`
  - `[ml_strategic_themes]`
  - `[ml_publisher_authority]`
- Theme dependency: shortcode-backed homepage/archive/directory surfaces are owned by `marketlense-core`; the theme expects the plugin to be active and shows an admin notice when it is missing instead of duplicating shortcode/business logic in theme PHP.
- Block-template compatibility: `marketlense-core` also applies its registered `ml_*` shortcodes during block rendering when template/pattern output leaves a raw shortcode string unresolved, so theme patterns built with `core/shortcode` blocks still render on the front end.
- `templates/page-topics-directory.html` renders `[ml_topics_directory]`.
- `templates/page-publishers-directory.html` renders `[ml_publishers_directory]` with publisher homepage CTAs.
- `templates/category.html` routes native category archives through the same report browser, so topic archive pages stay limited to uploaded reports instead of falling back to generic site-wide category queries.
- No dedicated `taxonomy-ml_topic.html` template is shipped; topic browsing is category-first.
- Legacy report posts under default `post` are intentionally not migrated; new publishing remains `ml_report`-first.


## Responsive Layout Defaults

The `marketlense` theme now uses full-width layout defaults in `theme.json` and constrains the actual editorial content in CSS so pages still read deliberately on both mobile and laptop widths:

- `settings.layout.contentSize`: `100%`
- `settings.layout.wideSize`: `100%`

This lets the UI take over the full screen on any device while preserving a controlled internal editorial frame for hero copy, cards, and process/briefing sections.

The homepage hero follows the same rule: the visual background and decorative circles live on the full-width outer hero band, while the inner hero frame stays transparent and constrained for readable copy width.
The hero now uses the shared home frame with the gutter carried by the outer band, not an extra inner inset, so both left and right edges stay in lockstep with the metrics, featured digest, and other homepage sections.
The desktop hero frame also no longer reserves an unused split column, which keeps the hero from appearing visually narrower on the right than the sections below it.
The headline itself also no longer carries a separate desktop `max-width`, so the `h1` aligns with the hero stack instead of stopping short inside the correct frame.
The process-section note copy also no longer carries its own narrower `max-width`, so it aligns to the same width as the section heading container.
The hero body copy and credibility line also no longer carry separate desktop `max-width` caps, so both lines align with the same hero stack width.
Other reusable theme copy blocks now follow their parent containers for the same reason: `ml-page-lead`, generic `ml-section-note`, featured digest excerpts, and ingest report hero subtitles no longer carry separate text-width caps.

## `ml_report` Ingest Rendering

Published ingest reports now render in an ingest-first mode in the single template:

- `parts/single-content.html` is the single source of truth for singular report content rendering.
- `templates/single-ml_report.html` and `templates/single.html` both route through that shared template part, preventing template drift while still covering `ml_report` and legacy default `post` entries.
- `assets/css/theme.css` contains a scoped parity layer under `.ml-ingest-report-content` that mirrors the generated digest body classes (`.page-shell`, `.report`, `.hero`, `.panel`, carousel/lightbox, sticky section nav).
- `assets/js/report-interactions.js` covers behavior that is stripped from uploaded HTML body content (panel reveal, prose chunking, section spy, reading progress, and carousel/lightbox interactions), and is enqueued only for `ml_report` and legacy default `post` singular views.
- Reveal panels are fail-open: content remains visible even if JS does not execute.
- Publish HTML source rewriting now updates both `img src` and `img srcset` URLs, preventing broken preview images after upload.
- Legacy safety: if an older post has absolute `src` but relative `srcset`, frontend JS removes the broken `srcset` so the image still renders.

This ensures the WordPress article view matches the latest ingest-generated HTML report styling and behavior as closely as possible after upload.

## Pipeline Integration

Publishing remains controlled by Python orchestration in `src/`:

```powershell
python -m src.cli publish-wp
python -m src.cli update-wp-categories
```

WordPress credentials and publish controls come from root `.env`/`app.yaml`:

- `WP_SITE_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD` or `WP_BEARER_TOKEN`
- `WP_POST_STATUS` (optional override)
- `WP_POST_TYPE` (optional override, default `ml_report`)

During publish, the pipeline now writes:

- native category IDs for report topics
- `ml_publisher` term IDs for report publishers

through the WordPress REST API so archive filters and directory pages stay aligned with uploaded reports.

## Maintenance Rule

Any WordPress change in this subproject must update:

- `Wordpress/README_WORDPRESS.md`
- Root `README.md` WordPress section
