=== Market Lense Core ===
Contributors: marketlense
Tags: reports, custom-post-type, taxonomy, api, editorial
Requires at least: 6.6
Tested up to: 6.6
Requires PHP: 8.2
Stable tag: 1.1.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Core WordPress domain plugin for Market Lense.

== Description ==

Market Lense Core provides the WordPress data model required by the Market Lense publishing pipeline and block theme:

* Custom post type: `ml_report`
* Taxonomies: native `category` support for report topics, legacy `ml_topic` projection, and `ml_publisher`
* Publisher term homepage metadata: `ml_publisher_homepage`
* REST exposure for CPT, taxonomies, and core report metadata
* Metadata synchronization from rendered digest content (`ml_file_id`, publisher, time period, region)
* Topic/publisher projection from existing post tags/categories and metadata panels
* Shortcodes:
  * `[ml_report_browser]` (`ml_topic` maps to native category slugs; `ml_publisher` maps to publisher taxonomy slugs)
  * `[ml_topics_directory]`
  * `[ml_publishers_directory]`

This plugin is intended to be used together with the `marketlense` block theme.

== Installation ==

1. Upload the plugin ZIP in WordPress Admin: `Plugins -> Add New -> Upload Plugin`.
2. Activate `Market Lense Core`.
3. Ensure the `marketlense` theme is installed and activated.
4. Confirm that `/wp-json/wp/v2/ml_report` is reachable.

== Changelog ==

= 1.1.1 =
* Switched frontend topic surfaces to native WordPress categories scoped to published `ml_report` posts.
* Added a dedicated category archive template for report-only topic browsing.
* Publisher terms are now assigned directly during publish so archive filters stay aligned with uploaded reports.

= 1.1.0 =
* Added publisher homepage term metadata (`ml_publisher_homepage`) with WP Admin edit fields and REST exposure.
* Added report browser and taxonomy directory shortcodes.

= 1.0.0 =
* Initial release with `ml_report` CPT, `ml_topic` and `ml_publisher` taxonomies, and metadata synchronization.
