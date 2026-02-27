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
  - `ml_topic`
  - `ml_publisher`
- Registers publisher term metadata:
  - `ml_publisher_homepage` (REST-exposed, sanitized URL)
- Registers and exposes report metadata keys:
  - `ml_file_id`
  - `ml_publisher_name`
  - `ml_time_period`
  - `ml_region`
- Synchronizes metadata/taxonomy projections from published digest content and existing tags/categories on save.
- Provides shortcodes:
  - `[ml_report_browser]` (URL filters: `ml_topic`, `ml_publisher`)
  - `[ml_topics_directory]`
  - `[ml_publishers_directory]`

## Provision Site IA (Pages + Navigation + Publisher Homepages)

After plugin/theme activation, provision the editorial IA:

```bash
bash Wordpress/scripts/provision-site-structure.sh
bash Wordpress/scripts/seed-publisher-homepages.sh
```

What `provision-site-structure.sh` does:

- Creates/updates required pages (About, Methodology, Topics directory, Publishers directory, Submit a Report, Contact, Privacy, Terms).
- Publishes pages idempotently (no duplicates on rerun).
- If `wp-cli` can access a local WP core (`wp core is-installed`), creates/updates primary and footer menus and assigns them to `primary` / `footer`.
- If `wp-cli` is unavailable in your environment, automatically falls back to REST (`provision-site-structure-rest.py`) and provisions pages only; navigation is already provided by static block-theme template parts (`parts/nav.html`, `parts/footer.html`).

What `seed-publisher-homepages.sh` does:

- Reads `Wordpress/config/publisher-homepages.json`.
- Ensures current publisher terms exist in `ml_publisher`.
- Upserts `ml_publisher_homepage` term meta for each publisher.
- Is idempotent and safe to rerun.
- Falls back to REST (`seed-publisher-homepages-rest.py`) when `wp-cli` cannot access a local WP core.
- In REST mode, if `marketlense-core` is installed but inactive, it auto-activates the plugin before seeding taxonomy terms.

## Build ZIPs For WP Admin Upload

From repo root:

```bash
bash Wordpress/scripts/build-plugin-zip.sh
bash Wordpress/scripts/build-theme-zip.sh
```

Build scripts use `zip` when available and automatically fall back to Python (`python`/`python3`/`py`) or local virtualenv interpreters (`../.venv/Scripts/python.exe`, `../.venv/bin/python`) when `zip` is not installed.

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
- REST endpoints resolve for `ml_report`, `ml_topic`, `ml_publisher`.
- Front page, report archive, and report filter URLs return HTTP `200`.
- Required site pages return HTTP `200`.
- Topics and publishers directory shortcodes render.
- Primary navigation links are present in rendered output.
- A published `ml_report` URL returns HTTP `200` (seeded if missing).

Optional environment controls:

- `WP_CLI_BIN` (default: `wp`)
- `WP_CLI_FLAGS` (example: `--path=/var/www/html --allow-root`)
- `PROVISION_STRUCTURE` (`1|0`, default `1`)
- `SEED_PUBLISHERS` (`1|0`, default `1`)
- `WP_SITE_URL` (required for REST fallback provisioning/seeding)
- `WP_USERNAME` + `WP_APP_PASSWORD` (or `WP_BEARER_TOKEN`) for REST fallback auth

If `wp-cli` is unavailable, smoke test exits with a skip message.

## Archive and Directory UX

- `templates/archive-ml_report.html` now renders `[ml_report_browser]`, which provides server-side taxonomy filtering at `/reports/` via:
  - `?ml_topic=<slug>`
  - `?ml_publisher=<slug>`
- `templates/page-topics-directory.html` renders `[ml_topics_directory]`.
- `templates/page-publishers-directory.html` renders `[ml_publishers_directory]` with publisher homepage CTAs.
- Legacy report posts under default `post` are intentionally not migrated; new publishing remains `ml_report`-first.


## Responsive Layout Defaults

The `marketlense` theme now uses wider responsive layout defaults in `theme.json` so content scales better on laptop/desktop widths while preserving mobile readability:

- `settings.layout.contentSize`: `min(60rem, calc(100vw - 2.5rem))`
- `settings.layout.wideSize`: `min(92rem, calc(100vw - 2.5rem))`

This keeps blocks fluid across breakpoints and avoids the previous narrow desktop appearance.

## `ml_report` Ingest Rendering

Published ingest reports now render in an ingest-first mode in the single template:

- `templates/single-ml_report.html` renders raw `post-content` directly (no theme-level report hero/rail wrappers).
- `templates/single.html` also renders full `post-content` directly, preventing fallback to `index.html` excerpt previews ("Continue reading") for reports published under default `post` type.
- `assets/css/theme.css` contains a scoped parity layer under `.ml-ingest-report-content` that mirrors the generated digest body classes (`.page-shell`, `.report`, `.hero`, `.panel`, carousel/lightbox, sticky section nav).
- `assets/js/report-interactions.js` now covers behavior that is stripped from uploaded HTML body content (panel reveal, prose chunking, section spy, reading progress, and carousel/lightbox interactions), and is enqueued for all singular views to support reports published under either `ml_report` or default `post`.
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

## Maintenance Rule

Any WordPress change in this subproject must update:

- `Wordpress/README_WORDPRESS.md`
- Root `README.md` WordPress section
