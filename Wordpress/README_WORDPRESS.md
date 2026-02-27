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
- Registers and exposes report metadata keys:
  - `ml_file_id`
  - `ml_publisher_name`
  - `ml_time_period`
  - `ml_region`
- Synchronizes metadata/taxonomy projections from published digest content and existing tags/categories on save.

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

## Smoke Test

If `wp-cli` is available:

```bash
bash Wordpress/scripts/smoke-test.sh
```

What it validates:

- Plugin `marketlense-core` is installed and can activate.
- Theme `marketlense` is installed and can activate.
- Required theme templates exist.
- Front page returns HTTP `200`.
- A published `ml_report` URL returns HTTP `200` (seeded if missing).

Optional environment controls:

- `WP_CLI_BIN` (default: `wp`)
- `WP_CLI_FLAGS` (example: `--path=/var/www/html --allow-root`)

If `wp-cli` is unavailable, smoke test exits with a skip message.


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
