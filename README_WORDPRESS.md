# Market Lense WordPress Front End

The WordPress subtree is the publication and rendering layer for successfully validated generated HTML artifacts and approved structured metadata/projections.

WordPress does not perform analysis, synthesis, metric extraction, or intelligence generation. Those responsibilities remain in the Python pipeline under `src/`.

## Front-End Shortcodes

Reusable shortcode entrypoints are registered by `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`.

- `[ml_report_browser]`: filtered and paginated report browser.
- `[ml_featured_digest]`: homepage Featured Digest module.
- `[ml_featured_briefing]`: homepage Featured Briefing module. Renders the latest published Briefing or an explicit institutional empty state.
- `[ml_briefings_index]`: canonical Briefings landing surface for `/briefings/`. Renders published Briefings or an explicit institutional empty state.
- `[ml_signals_index]`: canonical Signals landing surface for `/signals/`. Renders published Signals or an explicit institutional empty state.
- `[ml_signal_archive]`: compatibility alias for `[ml_signals_index]`; existing custom archive routes should prefer `[ml_signals_index]`.
- `[ml_briefing_archive]`: compatibility alias for `[ml_briefings_index]`; existing custom archive routes should prefer `[ml_briefings_index]`.
- `[ml_home_metrics]`, `[ml_hero_snapshot]`, `[ml_intelligence_signals]`, `[ml_strategic_themes]`, and `[ml_publisher_authority]`: homepage intelligence and discovery modules sourced from already published WordPress content and metadata.
- `[ml_topics_directory]`, `[ml_publishers_directory]`, and `[ml_publisher_profile]`: taxonomy and publisher discovery surfaces.
- `[ml_button_link]`, `[ml_inline_link]`, `[ml_primary_nav]`, and `[ml_footer_nav]`: navigation and link helpers.

## Verification

Run the WordPress subproject checks after shortcode or template changes:

```bash
python scripts/ci/check_wordpress_subproject.py
```

The smoke test remains optional and requires `RUN_WORDPRESS_SMOKE=1` plus a configured WP-CLI environment:

```bash
RUN_WORDPRESS_SMOKE=1 python scripts/ci/check_wordpress_subproject.py
```
