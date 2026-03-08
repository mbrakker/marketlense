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
    publisher-profiles.json
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
    build-plugin-zip.ps1
    provision-site-structure.sh
    seed-publisher-homepages.sh
    sync-publisher-profiles.sh
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
  - `ml_publisher_insights_url` (REST-exposed, newline-delimited external insights URLs)
  - `ml_publisher_icon_source` (REST-exposed icon URL, data URI, or emoji source)
  - `ml_publisher_notion_page_id`
  - `ml_publisher_notion_page_url`
- Registers and exposes report metadata keys:
  - `ml_file_id`
  - `ml_publisher_name`
  - `ml_time_period`
  - `ml_region`
- Synchronizes metadata/taxonomy projections from published digest content and existing tags/categories on save.
- Provides shortcodes:
  - `[ml_report_browser]` (URL filters: `category`, `ml_publisher`; legacy `ml_topic` query params still map to categories)
  - `[ml_home_metrics]`
  - `[ml_hero_snapshot]`
  - `[ml_featured_digest]`
  - `[ml_intelligence_signals]` (optional `show_publishers="0"` removes the `Top publishers` column)
  - `[ml_strategic_themes]`
  - `[ml_publisher_authority]`
  - `[ml_topics_directory]`
  - `[ml_publishers_directory]`
  - `[ml_publisher_profile]`

## Theme Contract (`marketlense`)

The block theme is organized as an editorial intelligence portal:

- Full-site editing templates and template parts for header, footer, archives, trust pages, search, and ingest-first singles
- Homepage assembled from reorderable patterns with a consultancy-style hero, proof bands, and discovery bands
- Theme-driven editorial token system in `theme.json` with a constrained reading frame, wider discovery frame, and semantic enterprise-blue tokens mirrored into `assets/css/theme.css` for non-block components
- Sans-first typography roles for display, page titles, section titles, card titles, body copy, metadata, navigation, and buttons are defined centrally in `theme.json` and reinforced in `assets/css/theme.css`
- Homepage chapter anchors are now standardized through reusable heading classes (`.ml-section-anchor`, `.ml-section-eyebrow`, `.ml-section-title`, `.ml-section-rule`) applied in theme patterns and shortcode section headers without changing module internals
- Homepage and shared editorial cards now opt into a reusable premium surface system via `.ml-surface-card` plus standard/compact padding variants, matching border/shadow states, and 24px inter-card gaps across featured digest, reports, signals, themes, authority, and method cards
- The active homepage hero pattern now uses a dedicated `.ml-hero` / `.ml-hero-grid` / `.ml-hero-panel` structure with a native search block and a premium right-side panel while keeping the existing hero copy, CTA targets, and `[ml_hero_snapshot]` shortcode output
- The weekly intelligence shortcode keeps the same data/query flow but now renders lighter single-line signal rows with `.ml-signals-column`, `.ml-signal-row`, `.ml-signal-topic`, and `.ml-signal-indicator` for a cleaner intelligence-list presentation
- The strategic themes shortcode keeps the same taxonomy data/order but now renders premium discovery cards with `.ml-theme-item`, `.ml-theme-title`, `.ml-theme-count`, and `.ml-theme-affordance`, including full-card hover treatment and lighter surface styling
- The publisher authority shortcode keeps the same publisher data/order but now renders institutional source cards with `.ml-authority-item`, `.ml-authority-item-copy`, `.ml-authority-name`, `.ml-authority-count`, and `.ml-publisher-profile-link`, using a stacked name/meta treatment and an internal publisher-profile CTA without changing publisher ordering, counts, or queries
- The latest reports/report-browser cards keep the same query and ordering logic but now use a fixed archive information stack (date, period, title, publisher, metrics, excerpt, CTA) with 4:3 media crops, 18px titles, muted 12px metadata, a longer archive-specific excerpt source, an 8-line reserved TLDR area, and inline digest CTAs
- The featured digest shortcode keeps the same featured-report selection logic but now renders a flagship editorial module with a top-right fixed badge column for insights/quotes/topics aligned to the publish/publisher/period rows, a 260px report-cover column, a stronger 30px title, a compact 3-line summary, limited topic display, and labeled insight bullets sourced from existing report data
- The theme-owned `How It Works` pattern now uses numbered procedural cards (`.ml-process-step`, `.ml-process-title`, `.ml-process-copy`, `.ml-process-intro`) with a tuned premium surface treatment, equal-height columns, and an icon-free institutional presentation while keeping the original methodology copy intact
- `assets/css/theme.css` now includes a final premium-polish layer: subtle node/network motifs in the hero and section rules, normalized chip/badge styling, calmer shared card/button/link transitions, and explicit `prefers-reduced-motion` handling without changing any shortcode/query logic
- Minimal JS only for singular report interaction parity

## Provision Site IA (Pages + Navigation + Publisher Profiles)

After plugin/theme activation, provision the editorial IA:

```bash
bash Wordpress/scripts/provision-site-structure.sh
bash Wordpress/scripts/seed-publisher-homepages.sh
bash Wordpress/scripts/sync-publisher-profiles.sh
```

What `provision-site-structure.sh` does:

- Creates/updates required pages (About, Methodology, Topics directory, Publishers directory, Submit a Report, Contact, Privacy, Terms).
- Publishes pages idempotently (no duplicates on rerun).
- Navigation is provided directly by static block-theme template parts (`parts/nav.html`, `parts/footer.html`) using native block navigation/list markup; the provisioning script does not create classic menu locations.
- The header is a compact two-row filesystem template part: brand plus navigation/briefing CTA on the first row, then a narrower archive search row beneath it. Header and footer both use the same shell/frame width model as the hero and homepage content lane.
- If `wp-cli` is unavailable in your environment, automatically falls back to REST (`provision-site-structure-rest.py`) and provisions the same required pages.

What `seed-publisher-homepages.sh` does:

- Reads `Wordpress/config/publisher-homepages.json`.
- Ensures current publisher terms exist in `ml_publisher`.
- Upserts `ml_publisher_homepage` term meta for each publisher.
- Is idempotent and safe to rerun.
- Falls back to REST (`seed-publisher-homepages-rest.py`) when `wp-cli` cannot access a local WP core.
- In REST mode, if `marketlense-core` is installed but inactive, it auto-activates the plugin before seeding taxonomy terms.

What `sync-publisher-profiles.sh` does:

- Reads `Wordpress/config/publisher-profiles.json`.
- Ensures current publisher terms exist in `ml_publisher`.
- Upserts the full publisher profile contract onto each term:
  - `description` from Notion `Publisher self presentation`
  - `ml_publisher_homepage`
  - `ml_publisher_insights_url`
  - `ml_publisher_icon_source`
  - `ml_publisher_notion_page_id`
  - `ml_publisher_notion_page_url`
- Uses REST (`sync-publisher-profiles-rest.py`) so large icon/data URI payloads and long profile descriptions can be synced safely.
- Inlines remote publisher icons to `data:image/...` payloads when the source is fetchable, and swaps known private Notion-secure icon URLs to public equivalents before sync.
- Is idempotent and safe to rerun after refreshing the Notion-derived JSON snapshot.

`publisher-profiles.json` is generated from the Notion `REPORT SOURCES` database snapshot. It captures, per publisher:

- icon source
- publisher name
- homepage link
- self-presentation text
- insights/report link

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

From PowerShell on Windows, you can build the plugin archive without going through `bash.exe`/WSL:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\build-plugin-zip.ps1
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
   - `bash Wordpress/scripts/sync-publisher-profiles.sh`
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

- `templates/archive-ml_report.html`, `templates/category.html`, `templates/taxonomy-ml_publisher.html`, and `templates/search.html` now route through the richer shortcode-based report browser instead of plain `core/query` grids.
- `templates/taxonomy-ml_publisher.html` now renders `[ml_publisher_profile]` above the archive browser so each publisher term page can expose the imported icon, homepage CTA, and insights CTA.
- Publisher archive/profile icon rendering now falls back to a monogram when a remote image source fails, so taxonomy pages never show a broken image box.
- `[ml_report_browser]` now owns filtering, sort order, result summaries, active-filter chips, and the responsive archive layout for archive/search/topic/publisher views.
- Backward compatibility: older `?ml_topic=<slug>` links remain accepted and are still mapped onto native categories in the browser surface.
- Homepage editorial sections are still backed by shortcode-driven intelligence components where the content is computed rather than directly queryable:
  - `[ml_home_metrics]`
  - `[ml_hero_snapshot]`
  - `[ml_featured_digest]`
  - `[ml_intelligence_signals]`
  - `[ml_latest_reports]`
  - `[ml_strategic_themes]`
  - `[ml_publisher_authority]`
- Theme dependency: computed homepage and directory surfaces remain owned by `marketlense-core`; the header/footer now consume plugin shortcodes for navigation/CTA resolution while the theme keeps layout control.
- Block-template compatibility: `marketlense-core` also applies its registered `ml_*` shortcodes during block rendering when template/pattern output leaves a raw shortcode string unresolved, so theme patterns built with `core/shortcode` blocks still render on the front end.
- Legacy projection safety: on activation and on the first runtime after upgrade, `marketlense-core` backfills missing report metadata and publisher taxonomy projections for existing `ml_report` posts so publisher counts, authority sections, and latest-report cards recover without manually re-saving reports. Current parser support includes digest hero subtitle metadata rows such as `Publisher`, `Time Period`, and `Geography`, which are now used during backfill as well.
- `templates/page-topics-directory.html` renders `[ml_topics_directory]`.
- `templates/page-publishers-directory.html` renders `[ml_publishers_directory]` with publisher homepage CTAs, trimmed self-presentation copy, and optional insights links.
- The publishers directory is term-driven, so synced publishers remain visible even before they have published reports attached.
- In WP Admin, publisher management now uses a dedicated `Market Lense Reports -> Publishers` screen instead of relying on the native taxonomy `edit-tags.php` UI.
- That custom Publishers manager ships with page-scoped admin styling so long profile fields and action links remain readable without panel overflow.
- `templates/category.html` routes native category archives through the same report browser, so topic archive pages stay limited to uploaded reports instead of falling back to generic site-wide category queries.
- No dedicated `taxonomy-ml_topic.html` template is shipped; topic browsing is category-first.
- Legacy report posts under default `post` are intentionally not migrated; new publishing remains `ml_report`-first.


## Responsive Layout Defaults

The `marketlense` theme now uses an explicit reading frame and a wider discovery frame in `theme.json` so the site feels more like a consultancy-quality portal than a stretched content dump:

- `settings.layout.contentSize`: `48rem`
- `settings.layout.wideSize`: `82rem`

This keeps narrative copy readable while giving discovery, archive, and homepage proof sections enough horizontal room to feel intentional on larger screens.

The homepage hero now uses a two-column proof-led composition: the left side carries the message and core CTAs, while the right side is a live proof rail rendered by `[ml_hero_snapshot]`.
That hero proof rail is the only homepage portal snapshot surface; the separate metrics strip is no longer rendered beneath the hero on the front page.
Homepage sections are grouped into proof and discovery bands so the page reads as a sequence of distinct consultancy-style surfaces instead of one long stack of interchangeable cards. Those bands now use the same shell/frame model as the hero and latest-reports sections, one canonical home-frame token (`--ml-frame-home`), explicit guards against legacy `is-layout-constrained` homepage markup, and no duplicate inner gutters inside band sections.
On the front page, the `This Week in Intelligence` pattern now renders `[ml_intelligence_signals show_publishers="0"]`, so the homepage focuses that band on topic and theme movement without the `Top publishers` column.
The header and footer now use the same home frame width as the hero and homepage section bands, with shell padding on the outer container and an unpadded inner frame so all major surfaces align predictably across breakpoints.
Trust and conversion templates (`About`, `Methodology`, `Contact`, `Submit a Report`) were also redesigned around the same frame so the visual language stays consistent once a visitor leaves the homepage.

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

The checked-in `publish.wp.site_url` value now targets `https://marketlense.medianewsonline.com` so publish flows and follow-on tooling stop reinforcing the legacy `http` scheme.

During publish, the pipeline now writes:

- native category IDs for report topics
- `ml_publisher` term IDs for report publishers

through the WordPress REST API so archive filters and directory pages stay aligned with uploaded reports.

## Maintenance Rule

Any WordPress change in this subproject must update:

- `Wordpress/README_WORDPRESS.md`
- Root `README.md` WordPress section
