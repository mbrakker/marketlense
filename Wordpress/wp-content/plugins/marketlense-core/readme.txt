=== Market Bearing Core ===
Contributors: marketlense
Tags: reports, custom-post-type, taxonomy, api, editorial
Requires at least: 6.6
Tested up to: 6.9
Requires PHP: 8.2
Stable tag: 1.7.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Core WordPress domain plugin for Market Bearing.

== Description ==

Market Bearing Core provides the WordPress data model required by the Market Bearing publishing pipeline and block theme:

* Custom post types: `ml_report`, `ml_signal`, and `ml_briefing`
* Taxonomies: native `category` support for report topics and `ml_publisher`
* Publisher term profile metadata:
  * `ml_publisher_homepage`
  * `ml_publisher_insights_url`
  * `ml_publisher_icon_source`
  * `ml_publisher_notion_page_id`
  * `ml_publisher_notion_page_url`
* REST exposure for the CPTs, native categories, publisher taxonomy, and core report metadata
* Metadata synchronization from rendered digest content (`ml_file_id`, publisher, time period, region)
* Publisher projection from digest metadata and taxonomy panels
* Homepage hero snapshot includes a rotating `Signal of the moment` card sourced from a random report full-text key-data insight with linked report attribution
* Shortcodes:
  * `[ml_report_browser]` (live search/category/region/publisher/period/sort filters; `category` maps to native category slugs; `ml_publisher` maps to publisher taxonomy slugs; legacy `ml_topic` query params remain accepted)
  * `[ml_home_metrics]`
  * `[ml_featured_digest]`
  * `[ml_featured_briefing]`
  * `[ml_intelligence_signals]` (optional `show_publishers="0"` removes the Top publishers column)
  * `[ml_strategic_themes]`
  * `[ml_publisher_authority]`
  * `[ml_signals_index]`
  * `[ml_signal_cards variant="small|medium|large" per_page="1..48"]` (reusable validated Signal cards; small shows the grounded statement and proof counts, medium adds topics, large adds the evidence condition)
  * `[ml_briefings_index]`
  * `[ml_signal_archive]` (legacy alias for `[ml_signals_index]`)
  * `[ml_briefing_archive]` (legacy alias for `[ml_briefings_index]`)
  * `[ml_topics_directory]`
  * `[ml_publishers_directory]`
  * `[ml_publisher_profile]`
* `[ml_archive_metric]`
  * `[ml_intake_form type="briefing|correction|submission"]` (nonce-protected public intake persisted privately for operator review)

This plugin is intended to be used together with the `marketlense` block theme.

== Installation ==

1. Upload the plugin ZIP in WordPress Admin: `Plugins -> Add New -> Upload Plugin`.
2. Activate `Market Bearing Core`.
3. Ensure the `marketlense` theme is installed and activated.
4. Confirm that `/wp-json/wp/v2/ml_report`, `/wp-json/wp/v2/ml_signal`, and `/wp-json/wp/v2/ml_briefing` are reachable.

== Changelog ==

= 1.7.0 =
* Adds private, nonce-protected briefing, correction, and source-submission intake with validation, honeypot rejection, and redacted event logging.
* Makes malformed legacy report-card models fail closed rather than producing a public PHP error.

= 1.6.9 =
* Emits public meta descriptions, canonical URLs, Open Graph tags, and Twitter card metadata for homepage, archives, categories, report/detail entities, and trust pages.

= 1.6.8 =
* Writes governed Topic semantics from native WordPress categories, including definitions, inclusion rules, exclusion rules, and schema version term metadata.
* Extends live REST verification to cover `ml_report`, `ml_briefing`, and `ml_signal` draft create/readback evidence.

= 1.6.7 =
* Adds canonical small, medium, and large Signal cards with validated statement, confidence, source/evidence counts, topics, uncertainty condition, and three deterministic deep-petrol cover assets.
* Adds `[ml_signal_cards]` as the reusable Signal-card shortcode and upgrades the Signals index to use the canonical card contract when Signal posts exist.

= 1.6.6 =
* Adds canonical small, medium, and large Briefing cards with validated metadata, semantic covers, source/evidence counters, and seven-day New badges.
* Supports in-place Briefing card-contract migration and keeps the Briefings archive in one responsive card grid.

= 1.6.5 =
* Moved report archive search, selected filters, and sort controls out of the filter rail into sticky premium archive controls.
* Added dependent report facets so each filter only shows options that still have matching reports in the current result set.

= 1.6.4 =
* Added icon-backed dynamic archive metrics including covered regions.
* Upgraded the reusable live report filter rail with a professional header, clear action, and elevated native controls.

= 1.6.3 =
* Added reusable live report-browser filtering without an Apply button.
* Added region filtering backed by report geography metadata.

= 1.6.2 =
* Report and publisher archives now paginate only canonical report-card contracts instead of producing empty grids from skipped legacy posts.
* Forced report-card publication now synchronizes covered-period and geography metadata from the card manifest.

= 1.6.1 =
* Prevented incomplete legacy report-card contracts from causing fatal errors during migration.
* Report lists now omit invalid card contracts, while hero placements select the newest valid report.

= 1.6.0 =
* Added canonical small, medium, and large report cards across all report placements.
* Added deterministic semantic cover families with separate landscape and vertical assets.
* Added complete TLDR, geography, period, key-insight, freshness, and cover-fingerprint metadata.
* Added fail-closed manifest backfill and published-contract audit support.

= 1.5.1 =
* Reworked the homepage hero around a horizontal latest governed brief and a dynamic trust panel.
* Added live archive counters and named top publishers to the hero trust panel.

= 1.5.0 =
* Added source-backed rotating report signals to homepage and Signals surfaces.
* Added topic archive fallback to published report briefs when a topic has no reports.
* Removed internal evidence identifiers from public Briefing output and collapsed technical appendices.
* Enabled public indexing and native WordPress sitemaps through a guarded discovery migration.
* Added native mobile navigation and compact report archive filter behavior.

= 1.4.0 =
* Added dynamic archive coverage metrics and editorial archive heroes for Reports, Topics, Publishers, Signals, and Briefings.
* Added report search and period filtering to the native report archive.
* Taxonomy directories now include only publishers and topics represented by published reports, briefings, or signals, with per-content-type counts.
* Signals now reuse source-backed metrics from published report artifacts when no standalone Signal posts exist.
* Added guarded migration from the legacy Market Lense site identity and filtered legacy metadata sentinels from public cards.

= 1.2.10 =
* Added reusable Briefings and Signals shortcode entrypoints for homepage and landing-page rendering: `[ml_featured_briefing]`, `[ml_briefings_index]`, and `[ml_signals_index]`.
* Briefings and Signals surfaces now render explicit institutional empty states when published validated content is unavailable.

= 1.2.9 =
* Restored digest visibility for generated core `post` entries by persisting a dedicated `ml_is_digest` contract during metadata backfill instead of requiring `ml_file_id` to exist up front.
* Added `Geography` fallback parsing for region metadata and preserved hidden `Drive fileId` markers from the Python publisher so digest lookup/backfill remain deterministic.
* Added a frontend media proxy that rewrites digest image URLs away from blocked `/wp-content/uploads/...` paths so uploaded covers render publicly on hosts with direct-upload restrictions.

= 1.2.7 =
* Finalized the premium homepage/theme integration pass with release-safe visual cleanup, consistent card/chip interaction styling, and synchronized plugin/theme versioning.

= 1.2.6 =
* Refined the custom Publishers manager layout in WP Admin so the editor form, long icon source values, and action links stay inside their panels and remain readable on narrower screens.

= 1.2.5 =
* Replaced the fragile native `edit-tags.php` publisher admin path with a dedicated Publishers manager under `Market Bearing Reports`.
* Redirects the old `edit-tags.php?taxonomy=ml_publisher&post_type=ml_report` URL into the custom manager so the Reports menu no longer dead-ends on hosts that block the native taxonomy screen.

= 1.2.4 =
* Fixed the publisher admin taxonomy screen capability mapping so report editors can open and manage publisher terms without the category-capability mismatch.
* Fixed the publishers directory to include synced publisher terms even when they do not yet have published reports.
* Added publisher logo fallbacks and sync-time icon inlining for remote/private sources so broken image boxes no longer appear on publisher archive pages.

= 1.2.3 =
* Added full publisher profile term metadata for Notion-driven homepage, insights, icon, and source-page sync.
* Added `[ml_publisher_profile]` for publisher archive pages and trimmed directory-card rendering for longer publisher descriptions.

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
