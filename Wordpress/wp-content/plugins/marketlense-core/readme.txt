=== Market Lense Core ===
Contributors: marketlense
Tags: reports, custom-post-type, taxonomy, api, editorial
Requires at least: 6.6
Tested up to: 6.6
Requires PHP: 8.2
Stable tag: 1.2.2
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Core WordPress domain plugin for Market Lense.

== Description ==

Market Lense Core provides the WordPress data model required by the Market Lense publishing pipeline and block theme:

* Custom post type: `ml_report`
* Taxonomies: native `category` support for report topics and `ml_publisher`
* Publisher term homepage metadata: `ml_publisher_homepage`
* REST exposure for the CPT, native categories, publisher taxonomy, and core report metadata
* Metadata synchronization from rendered digest content (`ml_file_id`, publisher, time period, region)
* Publisher projection from digest metadata and taxonomy panels
* Shortcodes:
  * `[ml_report_browser]` (`category` maps to native category slugs; `ml_publisher` maps to publisher taxonomy slugs; legacy `ml_topic` query params remain accepted)
  * `[ml_home_metrics]`
  * `[ml_featured_digest]`
  * `[ml_intelligence_signals]`
  * `[ml_strategic_themes]`
  * `[ml_publisher_authority]`
  * `[ml_topics_directory]`
  * `[ml_publishers_directory]`

This plugin is intended to be used together with the `marketlense` block theme.

== Installation ==

1. Upload the plugin ZIP in WordPress Admin: `Plugins -> Add New -> Upload Plugin`.
2. Activate `Market Lense Core`.
3. Ensure the `marketlense` theme is installed and activated.
4. Confirm that `/wp-json/wp/v2/ml_report` is reachable.

== Changelog ==

= 1.2.2 =
* Fixed publisher/time period/geography extraction for digest HTML that stores metadata in hero subtitle rows instead of the older meta panel markup.
* Re-runs legacy report projection backfill after upgrade so weekly publisher signals and publisher authority surfaces recover for existing reports.

= 1.2.0 =
* Added homepage intelligence shortcodes for editorial portal sections, including metrics, featured digest, weekly signals, strategic themes, and publisher authority.
* Upgraded report-browser cards to use parsed digest metadata, counts, concise excerpts, and executive-style CTAs.
* Added archive-aware filtering support for search and native category archives.

= 1.1.1 =
* Switched frontend topic surfaces to native WordPress categories scoped to published `ml_report` posts.
* Added a dedicated category archive template for report-only topic browsing.
* Publisher terms are now assigned directly during publish so archive filters stay aligned with uploaded reports.

= 1.1.0 =
* Added publisher homepage term metadata (`ml_publisher_homepage`) with WP Admin edit fields and REST exposure.
* Added report browser and taxonomy directory shortcodes.

= 1.0.0 =
* Initial release with `ml_report` CPT, topic/publisher taxonomies, and metadata synchronization.
