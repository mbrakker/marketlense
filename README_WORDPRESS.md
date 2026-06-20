# Market Bearing WordPress Front End

The WordPress subtree is the publication and rendering layer for successfully validated generated HTML artifacts and approved structured metadata/projections.

WordPress does not perform analysis, synthesis, metric extraction, or intelligence generation. Those responsibilities remain in the Python pipeline under `src/`.

## Front-End Shortcodes

Reusable shortcode entrypoints are registered by `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`.

- `[ml_report_browser]`: reusable filtered and paginated report browser with sticky live search, selected-filter chips, pictogram sort controls, and dependent category, region, publisher, and period facets. Filter changes submit immediately without an Apply button and preserve the canonical report-card renderer.
- `[ml_featured_digest]`: homepage Featured Report Brief module backed by the latest published report.
- `[ml_featured_briefing]`: homepage Featured Briefing module. Renders the latest published Briefing or an explicit institutional empty state.
- `[ml_briefings_index]`: canonical Briefings landing surface for `/briefings/`. Renders published Briefings or an explicit institutional empty state.
- `[ml_signals_index]`: canonical Signals landing surface for `/signals/`. Renders published Signals and otherwise reuses source-backed metrics from published report artifacts.
- `[ml_signal_archive]`: compatibility alias for `[ml_signals_index]`; existing custom archive routes should prefer `[ml_signals_index]`.
- `[ml_briefing_archive]`: compatibility alias for `[ml_briefings_index]`; existing custom archive routes should prefer `[ml_briefings_index]`.
- `[ml_home_metrics]`, `[ml_hero_snapshot]`, `[ml_hero_trust]`, `[ml_intelligence_signals]`, `[ml_strategic_themes]`, and `[ml_publisher_authority]`: homepage intelligence and discovery modules sourced from already published WordPress content and metadata. The hero places the latest governed brief below native WordPress search and renders live archive counters plus named top publishers in its trust panel.
- `[ml_brand_logo]`: canonical reusable Market Bearing wordmark for theme template parts.
- `[ml_archive_metric]`: dynamic archive, taxonomy, publisher, signal, and briefing coverage counters for theme-owned editorial heroes.
- `[ml_topics_directory]`, `[ml_publishers_directory]`, and `[ml_publisher_profile]`: taxonomy and publisher discovery surfaces.
- `[ml_button_link]`, `[ml_inline_link]`, `[ml_primary_nav]`, and `[ml_footer_nav]`: navigation and link helpers.

## Dynamic Publishing Model

- Reports publish to `ml_report` and automatically appear in `/reports/`, homepage report modules, topic counts, publisher counts, signals, and trust metrics.
- Briefings publish to `ml_briefing` and automatically appear in `/briefings/` plus the homepage featured briefing.
- Signals publish to `ml_signal` and automatically appear in `/signals/`. When no standalone signals exist, both homepage indicators and the Signals archive are derived from published report artifacts with source links.
- Featured media, excerpts, publishers, periods, topics, findings, quotations, and citation counts are reused from the published WordPress records. Featured report metrics count current finding cards, evidence quote figures, assigned public WordPress categories, and the rendered evidence-reference total; legacy insight and quote markup remains supported. No report or briefing title is hardcoded into the theme or plugin.
- The Reports archive uses a premium editorial hero with a dark dynamic metric console for reports, publishers, topics, and covered regions plus the reusable `[ml_report_browser]` shell. The sticky search toolbar spans the full report frame with selected-filter chips directly below the search row, while compact pictogram sorting and the sticky filter rail stay plugin-owned so archive, search, category, and publisher views share the same live dependent-facet behavior.
- Topic and publisher directories aggregate only entities represented by published reports, briefings, or signals. Legacy sentinel metadata such as `...` and `Not extracted` is omitted from public presentation.
- Topic archives fall back to published report briefs when no reports exist for the selected topic, without merging or rewriting taxonomy identities.
- Public Briefing rendering removes internal evidence identifiers and folds source-map, uncertainty, and evidence appendices into accessible disclosures.
- Public discovery enables native WordPress indexing and sitemaps; certificate trust remains a hosting responsibility.
- Theme version upgrades remove only the known legacy Site Editor header override containing the old site-title block, allowing the canonical MarketBearing wordmark to render.
- The desktop header is sticky and vertically aligns the wordmark, primary navigation, compact native WordPress search, and briefing CTA on one row. Navigation hover, focus, and current-page states remain transparent and reuse the Market Bearing signal-blue line-and-dot motif; mobile retains the disclosure navigation.
- Homepage sections use a tighter editorial rhythm with the line-and-dot signal directly below each title. Strategic Themes and Publisher Authority share the responsive Editorial Ledger surface: numbered theme cards and authority rows are presented inside one elevated, bordered discovery panel.

## Canonical Report Cards

All report placements use one renderer with three reusable variants:

- `small`: report browser, archive, taxonomy, publisher, search, and latest-report grids; minimal metadata plus the complete compact TLDR.
- `medium`: homepage hero/snapshot placements; additional report facts plus the complete standard TLDR.
- `large`: featured report placement; vertical hero cover, complete standard TLDR, and exactly two key insights.

Card grids reserve consistent content zones so cards stay aligned when report names occupy two or three lines and TLDR lengths vary. Copy is never visually truncated. Compact TLDRs are limited to 18 words and standard TLDRs to 45 words.

Every report has one deterministic cover identity selected from 16 geometry families using report-content differentiators. The persisted fingerprint records `geometry_family`, `primary_signal`, `secondary_signal`, and `seed`. The same identity is rendered at `1600x900` for small cards, `1200x1500` for medium cards, and `1200x1600` for large cards. Covers use the restrained project palette and fixed zones for the complete report name, publisher, and covered period.

Report facts use pictograms for publication date, geography, and covered period. Global reports use a globe; regional and country-specific reports use a locator. The `New` badge appears only when a report was published less than 7 days before the current request.

## Verification

### Report Card Backfill Gate

Before activating the reusable report-card renderers, regenerate only reports with missing or invalid card manifests, republish their WordPress metadata, and run the read-only contract audit:

```bash
python -m src.cli ingest --force-report-cards
python -m src.cli publish-wp --force-report-cards
wp eval-file Wordpress/scripts/audit-report-card-contracts.php
```

Plugin `1.6.5` keeps report and publisher archive pagination limited to canonical report-card contracts, safely omits any malformed migrated contract, selects the newest valid report for hero placements, and adds live dependent archive filtering. The Reports archive hero renders icon-backed dynamic metrics for reports, publishers, topics, and covered regions, while the reusable browser keeps search, selected filters, pictogram sorting, and the compact filter rail sticky without an Apply button. The forced publication command updates matched WordPress posts in place, synchronizes covered-period and geography metadata from the manifest, and does not create replacements. Run the backfill and forced publication commands before the audit so every published report becomes visible in canonical card placements. The final command must print `0 invalid published reports`; invalid rows are emitted as JSON lines containing the WordPress post ID, title, and failing card keys.

Browser verification covers the homepage, report archive, topic archive, publisher archive, and search at desktop, tablet, and mobile widths. Check horizontal overflow, title/TLDR completeness, aligned card actions, keyboard focus, 200% zoom/text spacing, and reduced-motion behavior.

Run the WordPress subproject checks after shortcode or template changes:

```bash
python scripts/ci/check_wordpress_subproject.py
```

The smoke test remains optional and requires `RUN_WORDPRESS_SMOKE=1` plus a configured WP-CLI environment:

```bash
RUN_WORDPRESS_SMOKE=1 python scripts/ci/check_wordpress_subproject.py
```

Build the release archives only after verification:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\build-plugin-zip.ps1
bash Wordpress/scripts/build-theme-zip.sh
```
