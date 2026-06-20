<?php
/**
 * Frontend shortcodes for report browsing and editorial intelligence surfaces.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Shortcodes
{
    private const DEFAULT_PER_PAGE = 12;

    private const TOPIC_QUERY_KEY = 'category';

    private const LEGACY_TOPIC_QUERY_KEY = 'ml_topic';
    /**
     * @var array<string,string>
     */
    private const SHORTCODE_METHODS = [
        'ml_report_browser' => 'render_report_browser',
        'ml_latest_reports' => 'render_latest_reports',
        'ml_topics_directory' => 'render_topics_directory',
        'ml_publishers_directory' => 'render_publishers_directory',
        'ml_publisher_profile' => 'render_publisher_profile',
        'ml_home_metrics' => 'render_home_metrics',
        'ml_hero_snapshot' => 'render_hero_snapshot',
        'ml_hero_trust' => 'render_hero_trust',
        'ml_featured_digest' => 'render_featured_digest',
        'ml_featured_briefing' => 'render_featured_briefing',
        'ml_intelligence_signals' => 'render_intelligence_signals',
        'ml_strategic_themes' => 'render_strategic_themes',
        'ml_publisher_authority' => 'render_publisher_authority',
        'ml_signals_index' => 'render_signals_index',
        'ml_briefings_index' => 'render_briefings_index',
        'ml_signal_archive' => 'render_signal_archive',
        'ml_briefing_archive' => 'render_briefing_archive',
        'ml_button_link' => 'render_button_link',
        'ml_inline_link' => 'render_inline_link',
        'ml_archive_metric' => 'render_archive_metric',
        'ml_brand_logo' => 'render_brand_logo',
        'ml_primary_nav' => 'render_primary_nav',
        'ml_footer_nav' => 'render_footer_nav',
    ];

    private Report_View_Model_Builder $view_model_builder;

    private Intelligence_Stats $stats;

    private Report_Card_Renderer $report_card_renderer;

    public function __construct(
        Report_View_Model_Builder $view_model_builder,
        Intelligence_Stats $stats,
        Report_Card_Renderer $report_card_renderer
    ) {
        $this->view_model_builder = $view_model_builder;
        $this->stats = $stats;
        $this->report_card_renderer = $report_card_renderer;
    }

    /**
     * Registers shortcode handlers.
     */
    public function register(): void
    {
        foreach (self::SHORTCODE_METHODS as $tag => $method) {
            add_shortcode($tag, [$this, $method]);
        }

        add_filter('render_block', [$this, 'render_registered_shortcodes_in_block'], 10, 2);
    }

    /**
     * Renders plugin shortcodes when block-template output leaves them unresolved.
     *
     * @param array<string,mixed> $block Parsed block data.
     */
    public function render_registered_shortcodes_in_block(string $block_content, array $block): string
    {
        if ($block_content === '' || ! str_contains($block_content, '[ml_')) {
            return $block_content;
        }

        foreach (array_keys(self::SHORTCODE_METHODS) as $tag) {
            if (! shortcode_exists($tag) || ! has_shortcode($block_content, $tag)) {
                continue;
            }

            return do_shortcode(shortcode_unautop($block_content));
        }

        return $block_content;
    }

    /**
     * Renders browse reports section with optional URL-based taxonomy filtering.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_report_browser(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'per_page' => (string) self::DEFAULT_PER_PAGE,
                'show_filters' => '1',
                'show_pagination' => '1',
                'context' => 'auto',
            ],
            $attrs,
            'ml_report_browser'
        );

        $per_page = max(1, min(48, (int) $atts['per_page']));
        $show_filters = $this->to_bool_flag($atts['show_filters']);
        $show_pagination = $this->to_bool_flag($atts['show_pagination']);
        $context = sanitize_key((string) $atts['context']);
        $current_page = $show_pagination ? $this->current_page() : 1;
        $search_term = $context === 'auto' ? $this->selected_search_term() : '';
        $archive_url = get_post_type_archive_link(Post_Type::POST_TYPE);
        if (! is_string($archive_url) || $archive_url === '') {
            $archive_url = home_url('/reports/');
        }

        $selected_topic = $this->selected_topic_slug();
        $selected_publisher = $this->selected_filter_slug('ml_publisher', Taxonomies::PUBLISHER_TAXONOMY);
        $all_period_options = $this->stats->report_periods();
        $selected_period = $this->selected_period($all_period_options);
        $all_region_options = $this->stats->report_regions();
        $selected_region = $this->selected_region($all_region_options);
        $selected_sort = $this->selected_sort();
        $selected_topic_term = null;
        if ($selected_topic !== '') {
            $topic_term = get_term_by('slug', $selected_topic, Taxonomies::CATEGORY_TAXONOMY);
            $selected_topic_term = $topic_term instanceof \WP_Term ? $topic_term : null;
        }
        $selected_publisher_term = null;
        if ($selected_publisher !== '') {
            $publisher_term = get_term_by('slug', $selected_publisher, Taxonomies::PUBLISHER_TAXONOMY);
            $selected_publisher_term = $publisher_term instanceof \WP_Term ? $publisher_term : null;
        }
        $active_filters = [];
        if ($selected_topic !== '') {
            $active_filters[self::TOPIC_QUERY_KEY] = $selected_topic;
        }
        if ($selected_publisher !== '') {
            $active_filters['ml_publisher'] = $selected_publisher;
        }
        if ($selected_period !== '') {
            $active_filters['ml_period'] = $selected_period;
        }
        if ($selected_region !== '') {
            $active_filters['ml_region'] = $selected_region;
        }
        $preserved_state_args = $active_filters;
        if ($search_term !== '') {
            $preserved_state_args['s'] = $search_term;
        }
        if ($selected_sort !== 'latest') {
            $preserved_state_args['ml_sort'] = $selected_sort;
        }

        $facet_context = [
            'topic' => $selected_topic,
            'publisher' => $selected_publisher,
            'period' => $selected_period,
            'region' => $selected_region,
            'search' => $search_term,
        ];

        $query_args = $this->report_browser_query_args($facet_context, $per_page, $current_page);
        $query_args = $this->apply_sort_to_query_args($query_args, $selected_sort);
        $query = new \WP_Query($query_args);
        $is_topic_fallback = false;
        if (
            (int) $query->found_posts === 0
            && $selected_topic_term instanceof \WP_Term
            && is_category()
        ) {
            $fallback_query = $this->topic_entity_fallback_query(
                $selected_topic,
                $search_term,
                $per_page,
                $current_page,
                $selected_sort
            );
            if ((int) $fallback_query->found_posts > 0) {
                $query = $fallback_query;
                $is_topic_fallback = true;
            }
        }
        $topic_options = $this->report_facet_terms(Taxonomies::CATEGORY_TAXONOMY, $facet_context, 'topic');
        $publisher_options = $this->report_facet_terms(Taxonomies::PUBLISHER_TAXONOMY, $facet_context, 'publisher');
        $period_options = $this->report_facet_meta_values(Meta::META_TIME_PERIOD, $facet_context, 'period');
        $region_options = $this->report_facet_meta_values(Meta::META_REGION, $facet_context, 'region');
        $form_action = $archive_url;
        if ($show_filters) {
            $this->enqueue_report_filter_assets();
        }

        ob_start();
        ?>
        <section class="ml-report-browser" aria-label="<?php esc_attr_e('Report browser', 'marketlense-core'); ?>">
            <?php if ($show_filters) : ?>
                <div class="ml-report-browser-utility-bar">
                    <form class="ml-report-search-form" method="get" action="<?php echo esc_url($form_action); ?>" data-ml-live-filter-form>
                        <span class="screen-reader-text" data-ml-filter-status aria-live="polite"></span>
                        <?php
                        $this->render_hidden_query_inputs($active_filters);
                        if ($selected_sort !== 'latest') {
                            $this->render_hidden_query_inputs(['ml_sort' => $selected_sort]);
                        }
                        ?>
                        <label class="ml-report-search-field" for="ml_report_search">
                            <span><?php esc_html_e('Search report archive', 'marketlense-core'); ?></span>
                            <input id="ml_report_search" name="s" type="search" value="<?php echo esc_attr($search_term); ?>" placeholder="<?php esc_attr_e('Search by report title, publisher, topic, or signal', 'marketlense-core'); ?>" data-ml-live-filter-input>
                        </label>
                    </form>
                    <?php $this->render_active_filter_chips($archive_url, $active_filters, $search_term, $selected_sort, $selected_topic_term, $selected_publisher_term, $selected_period, $selected_region); ?>
                </div>
            <?php endif; ?>
            <div class="ml-report-browser-layout">
                <?php if ($show_filters) : ?>
                    <aside class="ml-report-browser-sidebar">
                        <div class="ml-report-browser-sidebar-card">
                            <details class="ml-report-filter-panel" open>
                                <summary class="ml-report-filter-summary"><?php esc_html_e('Filter reports', 'marketlense-core'); ?></summary>
                                <div class="ml-report-filter-body">
                                    <div class="ml-report-filter-header">
                                        <div>
                                            <p class="ml-section-kicker"><?php esc_html_e('Filters', 'marketlense-core'); ?></p>
                                            <h2 class="ml-report-browser-title"><?php esc_html_e('Refine reports', 'marketlense-core'); ?></h2>
                                        </div>
                                    </div>
                                    <p class="ml-report-browser-copy"><?php esc_html_e('Each facet only shows options with matching reports in the current view.', 'marketlense-core'); ?></p>

                                    <form class="ml-report-filter-form" method="get" action="<?php echo esc_url($form_action); ?>" data-ml-live-filter-form>
                                        <span class="screen-reader-text" data-ml-filter-status aria-live="polite"></span>
                                        <?php
                                        $filter_form_state = [];
                                        if ($search_term !== '') {
                                            $filter_form_state['s'] = $search_term;
                                        }
                                        if ($selected_sort !== 'latest') {
                                            $filter_form_state['ml_sort'] = $selected_sort;
                                        }
                                        $this->render_hidden_query_inputs($filter_form_state);
                                        ?>
                                        <div class="ml-report-filter-grid">
                                            <label class="ml-report-filter-field" for="ml_topic_filter">
                                                <span><?php esc_html_e('Category', 'marketlense-core'); ?></span>
                                                <select id="ml_topic_filter" name="<?php echo esc_attr(self::TOPIC_QUERY_KEY); ?>">
                                                    <option value=""><?php esc_html_e('All categories', 'marketlense-core'); ?></option>
                                                    <?php foreach ($topic_options as $term) : ?>
                                                        <option value="<?php echo esc_attr($term->slug); ?>" <?php selected($selected_topic, $term->slug); ?>>
                                                            <?php echo esc_html(sprintf('%1$s (%2$d)', $term->name, (int) $term->count)); ?>
                                                        </option>
                                                    <?php endforeach; ?>
                                                </select>
                                            </label>

                                            <label class="ml-report-filter-field" for="ml_region_filter">
                                                <span><?php esc_html_e('Region', 'marketlense-core'); ?></span>
                                                <select id="ml_region_filter" name="ml_region">
                                                    <option value=""><?php esc_html_e('All regions', 'marketlense-core'); ?></option>
                                                    <?php foreach ($region_options as $region) : ?>
                                                        <option value="<?php echo esc_attr($region['value']); ?>" <?php selected($selected_region, $region['value']); ?>>
                                                            <?php echo esc_html(sprintf('%1$s (%2$d)', $region['value'], (int) $region['count'])); ?>
                                                        </option>
                                                    <?php endforeach; ?>
                                                </select>
                                            </label>

                                            <label class="ml-report-filter-field" for="ml_publisher_filter">
                                                <span><?php esc_html_e('Publisher', 'marketlense-core'); ?></span>
                                                <select id="ml_publisher_filter" name="ml_publisher">
                                                    <option value=""><?php esc_html_e('All publishers', 'marketlense-core'); ?></option>
                                                    <?php foreach ($publisher_options as $term) : ?>
                                                        <option value="<?php echo esc_attr($term->slug); ?>" <?php selected($selected_publisher, $term->slug); ?>>
                                                            <?php echo esc_html(sprintf('%1$s (%2$d)', $term->name, (int) $term->count)); ?>
                                                        </option>
                                                    <?php endforeach; ?>
                                                </select>
                                            </label>

                                            <label class="ml-report-filter-field" for="ml_period_filter">
                                                <span><?php esc_html_e('Period', 'marketlense-core'); ?></span>
                                                <select id="ml_period_filter" name="ml_period">
                                                    <option value=""><?php esc_html_e('All periods', 'marketlense-core'); ?></option>
                                                    <?php foreach ($period_options as $period) : ?>
                                                        <option value="<?php echo esc_attr($period['value']); ?>" <?php selected($selected_period, $period['value']); ?>>
                                                            <?php echo esc_html(sprintf('%1$s (%2$d)', $period['value'], (int) $period['count'])); ?>
                                                        </option>
                                                    <?php endforeach; ?>
                                                </select>
                                            </label>
                                        </div>
                                    </form>

                                </div>
                            </details>
                        </div>
                    </aside>
                <?php endif; ?>

                <div class="ml-report-browser-results">
                    <div class="ml-report-browser-head">
                        <div>
                            <p class="ml-report-browser-summary">
                                <span class="ml-report-browser-summary-value">
                                    <?php
                                    echo esc_html(
                                        sprintf(
                                            _n('%d report', '%d reports', (int) $query->found_posts, 'marketlense-core'),
                                            (int) $query->found_posts
                                        )
                                    );
                                    ?>
                                </span>
                                <span class="ml-report-browser-summary-copy"><?php esc_html_e('currently in view', 'marketlense-core'); ?></span>
                            </p>
                            <?php if ($is_topic_fallback) : ?>
                                <p class="ml-report-browser-context"><strong><?php esc_html_e('Report briefs in this topic', 'marketlense-core'); ?></strong></p>
                            <?php elseif ($search_term !== '') : ?>
                                <p class="ml-report-browser-context">
                                    <?php echo esc_html(sprintf(__('Search query: "%s"', 'marketlense-core'), $search_term)); ?>
                                </p>
                            <?php elseif ($selected_topic_term instanceof \WP_Term || $selected_publisher_term instanceof \WP_Term || $selected_period !== '' || $selected_region !== '') : ?>
                                <p class="ml-report-browser-context"><?php echo esc_html($this->browser_context_copy($selected_topic_term, $selected_publisher_term, $selected_period, $selected_region)); ?></p>
                            <?php endif; ?>
                        </div>
                        <?php $this->render_report_sort_controls($archive_url, $preserved_state_args, $selected_sort); ?>
                    </div>

                    <?php if ($query->have_posts()) : ?>
                        <div class="ml-report-browser-grid">
                            <?php while ($query->have_posts()) : ?>
                                <?php
                                $query->the_post();
                                $post = get_post();
                                if (! ($post instanceof \WP_Post)) {
                                    continue;
                                }
                                if ($is_topic_fallback) {
                                    $this->render_entity_card($post, __('Read report brief', 'marketlense-core'));
                                } else {
                                    $report = $this->view_model_builder->build($post);
                                    if (($report['card_contract_valid'] ?? false) !== true) {
                                        continue;
                                    }
                                    echo $this->report_card_renderer->render($report, 'small'); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                                }
                                ?>
                            <?php endwhile; ?>
                        </div>

                        <?php if ($show_pagination) : ?>
                            <?php
                            $pagination_args = $active_filters;
                            if ($search_term !== '') {
                                $pagination_args['s'] = $search_term;
                            }
                            if ($selected_sort !== 'latest') {
                                $pagination_args['ml_sort'] = $selected_sort;
                            }
                            ?>
                            <?php $this->render_pagination($query, $pagination_args); ?>
                        <?php endif; ?>
                    <?php else : ?>
                        <div class="ml-empty-state">
                            <p><?php esc_html_e('No reports match the current view.', 'marketlense-core'); ?></p>
                        </div>
                    <?php endif; ?>
                </div>
            </div>
            <?php wp_reset_postdata(); ?>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders the latest report card grid for the homepage.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_latest_reports(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'limit' => '6',
                'variant' => 'small',
            ],
            $attrs,
            'ml_latest_reports'
        );
        $limit = max(1, min(12, (int) $atts['limit']));
        $variant = sanitize_key((string) $atts['variant']);
        if (! in_array($variant, ['small', 'medium', 'large'], true)) {
            throw new \InvalidArgumentException('Unsupported report card variant: ' . $variant);
        }

        $query = new \WP_Query(
            Meta::apply_report_card_query_constraints(
                [
                    'post_status' => 'publish',
                    'posts_per_page' => $limit,
                    'orderby' => 'date',
                    'order' => 'DESC',
                    'no_found_rows' => true,
                ]
            )
        );

        ob_start();
        if ($query->have_posts()) :
            ?>
            <div class="ml-report-browser-grid ml-latest-report-grid">
                <?php while ($query->have_posts()) : ?>
                    <?php
                    $query->the_post();
                    $post = get_post();
                    if (! ($post instanceof \WP_Post)) {
                        continue;
                    }
                    $report = $this->view_model_builder->build($post);
                    if (($report['card_contract_valid'] ?? false) !== true) {
                        continue;
                    }
                    echo $this->report_card_renderer->render($report, $variant); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
                    ?>
                <?php endwhile; ?>
            </div>
            <?php
        else :
            ?>
            <p class="ml-query-empty"><?php esc_html_e('No reports are available yet.', 'marketlense-core'); ?></p>
            <?php
        endif;

        wp_reset_postdata();

        return (string) ob_get_clean();
    }

    /**
     * Renders the home metrics strip.
     */
    public function render_home_metrics(): string
    {
        $metrics = $this->stats->homepage_metrics();

        ob_start();
        ?>
        <section class="ml-home-metrics" aria-label="<?php esc_attr_e('Intelligence metrics', 'marketlense-core'); ?>">
            <div class="ml-home-metrics-grid">
                <article class="ml-metric-item">
                    <span class="ml-metric-value"><?php echo esc_html((string) $metrics['report_count']); ?></span>
                    <span class="ml-metric-label"><?php esc_html_e('Reports', 'marketlense-core'); ?></span>
                </article>
                <article class="ml-metric-item">
                    <span class="ml-metric-value"><?php echo esc_html((string) $metrics['publisher_count']); ?></span>
                    <span class="ml-metric-label"><?php esc_html_e('Publishers', 'marketlense-core'); ?></span>
                </article>
                <article class="ml-metric-item">
                    <span class="ml-metric-value"><?php echo esc_html((string) $metrics['topic_count']); ?></span>
                    <span class="ml-metric-label"><?php esc_html_e('Topics', 'marketlense-core'); ?></span>
                </article>
                <article class="ml-metric-item">
                    <span class="ml-metric-value"><?php echo esc_html((string) $metrics['briefing_count']); ?></span>
                    <span class="ml-metric-label"><?php esc_html_e('Executive briefings', 'marketlense-core'); ?></span>
                </article>
                <article class="ml-metric-item">
                    <span class="ml-metric-value"><?php echo esc_html((string) $metrics['signal_count']); ?></span>
                    <span class="ml-metric-label"><?php echo esc_html((string) $metrics['signal_label']); ?></span>
                </article>
                <article class="ml-metric-item">
                    <span class="ml-metric-value"><?php echo esc_html((string) $metrics['citation_count']); ?></span>
                    <span class="ml-metric-label"><?php esc_html_e('Citations & evidence links', 'marketlense-core'); ?></span>
                </article>
            </div>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders the hero proof rail.
     */
    public function render_hero_snapshot(): string
    {
        $latest_post = $this->stats->latest_report();
        $latest = $latest_post instanceof \WP_Post
            ? $this->view_model_builder->build($latest_post)
            : null;
        if (
            ! is_array($latest)
            || ($latest['card_contract_valid'] ?? false) !== true
        ) {
            return '';
        }

        ob_start();
        ?>
        <section class="ml-hero-snapshot" aria-label="<?php esc_attr_e('Latest governed brief', 'marketlense-core'); ?>">
            <?php echo $this->report_card_renderer->render($latest, 'medium'); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
        </section>
        <?php

        return (string) ob_get_clean();
    }

    /**
     * Renders the right-side trust block from published WordPress records.
     */
    public function render_hero_trust(): string
    {
        $metrics = $this->stats->homepage_metrics();
        $publishers = $this->stats->publisher_authority(5);
        $trust_metrics = [
            [(int) $metrics['report_count'], __('Reports', 'marketlense-core')],
            [(int) $metrics['publisher_count'], __('Publishers', 'marketlense-core')],
            [(int) $metrics['topic_count'], __('Topics', 'marketlense-core')],
            [(int) $metrics['briefing_count'], __('Briefings', 'marketlense-core')],
            [(int) $metrics['signal_count'], (string) $metrics['signal_label']],
            [(int) $metrics['citation_count'], __('Citations', 'marketlense-core')],
        ];

        ob_start();
        ?>
        <section class="ml-hero-trust" aria-label="<?php esc_attr_e('Market Bearing trust indicators', 'marketlense-core'); ?>">
            <div class="ml-hero-trust-heading">
                <p class="ml-proof-label"><?php esc_html_e('Governed archive', 'marketlense-core'); ?></p>
                <h2><?php esc_html_e('Trust at a glance', 'marketlense-core'); ?></h2>
            </div>
            <div class="ml-hero-trust-grid">
                <?php foreach ($trust_metrics as [$value, $label]) : ?>
                    <article class="ml-hero-trust-metric">
                        <strong><?php echo esc_html((string) $value); ?></strong>
                        <span><?php echo esc_html($label); ?></span>
                    </article>
                <?php endforeach; ?>
            </div>
            <?php if ($publishers !== []) : ?>
                <div class="ml-hero-trust-publishers">
                    <p class="ml-proof-label"><?php esc_html_e('Top publishers', 'marketlense-core'); ?></p>
                    <ul>
                        <?php foreach ($publishers as $publisher) : ?>
                            <li>
                                <?php if ((string) $publisher['url'] !== '') : ?>
                                    <a href="<?php echo esc_url((string) $publisher['url']); ?>"><?php echo esc_html((string) $publisher['name']); ?></a>
                                <?php else : ?>
                                    <span><?php echo esc_html((string) $publisher['name']); ?></span>
                                <?php endif; ?>
                                <small><?php echo esc_html(sprintf(_n('%d report', '%d reports', (int) $publisher['count'], 'marketlense-core'), (int) $publisher['count'])); ?></small>
                            </li>
                        <?php endforeach; ?>
                    </ul>
                </div>
            <?php endif; ?>
        </section>
        <?php

        return (string) ob_get_clean();
    }

    /**
     * Selects evidence-backed metrics from distinct published reports.
     *
     * @return array<int,array{insight:string,title:string,permalink:string,publisher:string}>
     */
    private function source_backed_signals(int $limit): array
    {
        $limit = max(1, min(6, $limit));
        $report_ids = get_posts(
            Meta::apply_digest_query_constraints(
                [
                    'post_status' => 'publish',
                    'fields' => 'ids',
                    'posts_per_page' => -1,
                    'no_found_rows' => true,
                    'update_post_meta_cache' => false,
                    'update_post_term_cache' => false,
                    'orderby' => 'date',
                    'order' => 'DESC',
                ]
            )
        );

        if (! is_array($report_ids) || $report_ids === []) {
            return [];
        }

        $candidate_ids = array_values(
            array_filter(
                array_map('intval', $report_ids),
                static fn (int $post_id): bool => $post_id > 0
            )
        );

        if ($candidate_ids === []) {
            return [];
        }

        shuffle($candidate_ids);
        $signals = [];

        foreach ($candidate_ids as $post_id) {
            $post = get_post($post_id);
            if (
                ! ($post instanceof \WP_Post)
                || ! Post_Type::is_report_post_type($post->post_type)
                || $post->post_status !== 'publish'
                || trim((string) get_post_meta($post_id, Meta::META_FILE_ID, true)) === ''
            ) {
                continue;
            }

            $report = $this->view_model_builder->build($post);
            $metrics = array_values(
                array_filter(
                    array_map(
                        static fn ($metric): string => trim((string) $metric),
                        is_array($report['full_key_metrics'] ?? null) ? $report['full_key_metrics'] : []
                    ),
                    static fn (string $metric): bool => $metric !== ''
                )
            );

            if ($metrics === []) {
                continue;
            }

            $metric_index = count($metrics) > 1 ? wp_rand(0, count($metrics) - 1) : 0;

            $signals[] = [
                'insight' => $metrics[$metric_index],
                'title' => (string) ($report['title'] ?? ''),
                'permalink' => (string) ($report['permalink'] ?? ''),
                'publisher' => (string) ($report['publisher'] ?? ''),
            ];
            if (count($signals) >= $limit) {
                break;
            }
        }

        return $signals;
    }

    /**
     * Renders the featured digest lead story.
     */
    public function render_featured_digest(): string
    {
        $post = $this->stats->latest_report();
        if (! ($post instanceof \WP_Post)) {
            return '';
        }

        $report = $this->view_model_builder->build($post);
        if (($report['card_contract_valid'] ?? false) !== true) {
            return '';
        }

        ob_start();
        ?>
        <section class="ml-featured-digest" aria-label="<?php esc_attr_e('Featured report brief', 'marketlense-core'); ?>">
            <div class="ml-section-heading ml-section-anchor">
                <p class="ml-section-kicker ml-section-eyebrow"><?php esc_html_e('EDITORIAL', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2 class="ml-section-title"><?php esc_html_e('Featured Report Brief', 'marketlense-core'); ?></h2>
                    <a class="ml-inline-link" href="<?php echo esc_url(get_post_type_archive_link(Post_Type::POST_TYPE) ?: home_url('/reports/')); ?>">
                        <?php esc_html_e('Browse all reports', 'marketlense-core'); ?>
                        <span class="ml-link-arrow" aria-hidden="true">&rarr;</span>
                    </a>
                </div>
                <span class="ml-section-rule" aria-hidden="true"></span>
            </div>

            <?php echo $this->report_card_renderer->render($report, 'large'); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders the latest approved Briefing for homepage placement.
     */
    public function render_featured_briefing(): string
    {
        $query = new \WP_Query(
            [
                'post_type' => Post_Type::BRIEFING_POST_TYPE,
                'post_status' => 'publish',
                'posts_per_page' => 1,
                'orderby' => 'date',
                'order' => 'DESC',
                'no_found_rows' => true,
            ]
        );

        $post = null;
        if ($query->have_posts()) {
            $query->the_post();
            $candidate = get_post();
            $post = $candidate instanceof \WP_Post ? $candidate : null;
        }

        ob_start();
        ?>
        <section class="ml-featured-briefing" aria-label="<?php esc_attr_e('Featured Briefing', 'marketlense-core'); ?>">
            <div class="ml-section-heading ml-section-anchor">
                <p class="ml-section-kicker ml-section-eyebrow"><?php esc_html_e('BRIEFINGS', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2 class="ml-section-title"><?php esc_html_e('Featured Briefing', 'marketlense-core'); ?></h2>
                    <a class="ml-inline-link" href="<?php echo esc_url($this->post_type_archive_url(Post_Type::BRIEFING_POST_TYPE, '/briefings/')); ?>">
                        <?php esc_html_e('Open Briefings', 'marketlense-core'); ?>
                        <span class="ml-link-arrow" aria-hidden="true">&rarr;</span>
                    </a>
                </div>
                <span class="ml-section-rule" aria-hidden="true"></span>
            </div>

            <?php if ($post instanceof \WP_Post) : ?>
                <?php $this->render_featured_entity_card($post, __('Read Briefing', 'marketlense-core')); ?>
            <?php else : ?>
                <?php $this->render_institutional_empty_state(__('No validated Briefings are available yet. Briefings appear here after approved Briefings have been published.', 'marketlense-core')); ?>
            <?php endif; ?>
        </section>
        <?php
        wp_reset_postdata();

        return (string) ob_get_clean();
    }

    /**
     * Renders the weekly intelligence signals panel.
     */
    public function render_intelligence_signals(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'show_publishers' => '1',
            ],
            $attrs,
            'ml_intelligence_signals'
        );
        $show_publishers = $this->to_bool_flag($atts['show_publishers']);
        $signals = $this->stats->weekly_signals();
        $source_signals = $this->source_backed_signals(3);
        if (
            $source_signals === []
            &&
            $signals['trending_topics'] === []
            && $signals['emerging_themes'] === []
            && (! $show_publishers || $signals['top_publishers'] === [])
        ) {
            return '';
        }

        ob_start();
        ?>
        <section class="ml-intelligence-signals" aria-label="<?php esc_attr_e('This week in intelligence', 'marketlense-core'); ?>">
            <div class="ml-section-heading ml-section-anchor">
                <p class="ml-section-kicker ml-section-eyebrow"><?php esc_html_e('SIGNALS', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2 class="ml-section-title"><?php esc_html_e('This Week in Intelligence', 'marketlense-core'); ?></h2>
                    <p class="ml-section-note"><?php echo esc_html((string) $signals['window_label']); ?></p>
                </div>
                <span class="ml-section-rule" aria-hidden="true"></span>
            </div>

            <?php if ($source_signals !== []) : ?>
                <div class="ml-source-signal-strip" aria-label="<?php esc_attr_e('Source-backed report signals', 'marketlense-core'); ?>">
                    <?php foreach ($source_signals as $source_signal) : ?>
                        <article class="ml-source-signal">
                            <p class="ml-proof-label"><?php esc_html_e('Source-backed signal', 'marketlense-core'); ?></p>
                            <h3><?php echo esc_html($source_signal['insight']); ?></h3>
                            <p>
                                <a href="<?php echo esc_url($source_signal['permalink']); ?>"><?php echo esc_html($source_signal['title']); ?></a>
                                <?php if ($source_signal['publisher'] !== '') : ?>
                                    <span><?php echo esc_html(' / ' . $source_signal['publisher']); ?></span>
                                <?php endif; ?>
                            </p>
                        </article>
                    <?php endforeach; ?>
                </div>
            <?php endif; ?>

            <div class="ml-signals-layout">
                <div class="ml-signals-stack">
                    <?php $this->render_signal_column(__('Trending topics', 'marketlense-core'), $signals['trending_topics'], 'ml-signal-column ml-signal-column--topics'); ?>
                    <?php $this->render_signal_column(__('Emerging themes', 'marketlense-core'), $signals['emerging_themes'], 'ml-signal-column ml-signal-column--themes'); ?>
                </div>
                <?php if ($show_publishers) : ?>
                    <?php $this->render_signal_column(__('Top publishers', 'marketlense-core'), $signals['top_publishers'], 'ml-signal-column ml-signal-column--publishers'); ?>
                <?php endif; ?>
            </div>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders durable Signals on the public Signals landing surface.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_signals_index(array $attrs = []): string
    {
        $counts = wp_count_posts(Post_Type::SIGNAL_POST_TYPE);
        $published_count = is_object($counts) && isset($counts->publish)
            ? max(0, (int) $counts->publish)
            : 0;
        if ($published_count === 0) {
            return $this->render_report_signal_archive($attrs);
        }

        return $this->render_entity_archive(
            $attrs,
            'ml_signals_index',
            Post_Type::SIGNAL_POST_TYPE,
            __('Published Signals', 'marketlense-core'),
            __('No validated Signals are available yet. Signals appear here after approved Signals have been published.', 'marketlense-core'),
            __('Read Signal', 'marketlense-core')
        );
    }

    /**
     * Renders the legacy Signal archive shortcode through the canonical index surface.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_signal_archive(array $attrs = []): string
    {
        return $this->render_signals_index($attrs);
    }

    /**
     * Renders Briefing posts on the public Briefings landing surface.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_briefings_index(array $attrs = []): string
    {
        return $this->render_entity_archive(
            $attrs,
            'ml_briefings_index',
            Post_Type::BRIEFING_POST_TYPE,
            __('Published Briefings', 'marketlense-core'),
            __('No validated Briefings are available yet. Briefings appear here after approved Briefings have been published.', 'marketlense-core'),
            __('Read Briefing', 'marketlense-core')
        );
    }

    /**
     * Renders the legacy Briefing archive shortcode through the canonical index surface.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_briefing_archive(array $attrs = []): string
    {
        return $this->render_briefings_index($attrs);
    }

    /**
     * Renders strategic themes section.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_strategic_themes(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'limit' => '6',
            ],
            $attrs,
            'ml_strategic_themes'
        );
        $limit = max(1, min(12, (int) $atts['limit']));
        $themes = $this->stats->strategic_themes($limit);
        if ($themes === []) {
            return '';
        }

        ob_start();
        ?>
        <section class="ml-strategic-themes" aria-label="<?php esc_attr_e('Strategic themes', 'marketlense-core'); ?>">
            <div class="ml-section-heading ml-section-anchor">
                <p class="ml-section-kicker ml-section-eyebrow"><?php esc_html_e('DISCOVER', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2 class="ml-section-title"><?php esc_html_e('Strategic Themes', 'marketlense-core'); ?></h2>
                    <a class="ml-inline-link" href="<?php echo esc_url(home_url('/topics-directory/')); ?>">
                        <?php esc_html_e('Open topics directory', 'marketlense-core'); ?>
                        <span class="ml-link-arrow" aria-hidden="true">&rarr;</span>
                    </a>
                </div>
                <span class="ml-section-rule" aria-hidden="true"></span>
            </div>

            <div class="ml-theme-list">
                <?php foreach ($themes as $theme) : ?>
                    <?php $theme_has_url = (string) $theme['url'] !== ''; ?>
                    <article class="ml-theme-item ml-surface-card ml-surface-card--compact ml-card<?php echo $theme_has_url ? ' ml-theme-item--linked' : ''; ?>">
                        <div class="ml-theme-item-copy">
                            <h3 class="ml-theme-title">
                                <?php if ((string) $theme['url'] !== '') : ?>
                                    <a href="<?php echo esc_url((string) $theme['url']); ?>">
                                        <?php echo esc_html((string) $theme['name']); ?>
                                    </a>
                                <?php else : ?>
                                    <?php echo esc_html((string) $theme['name']); ?>
                                <?php endif; ?>
                            </h3>
                            <p class="ml-theme-count"><?php echo esc_html(sprintf(_n('%d report', '%d reports', (int) $theme['count'], 'marketlense-core'), (int) $theme['count'])); ?></p>
                        </div>
                        <span class="ml-theme-affordance" aria-hidden="true">&rarr;</span>
                    </article>
                <?php endforeach; ?>
            </div>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders publisher authority wall.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_publisher_authority(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'limit' => '12',
            ],
            $attrs,
            'ml_publisher_authority'
        );
        $limit = max(1, min(18, (int) $atts['limit']));
        $publishers = $this->stats->publisher_authority($limit);
        if ($publishers === []) {
            return '';
        }

        ob_start();
        ?>
        <section class="ml-publisher-authority" aria-label="<?php esc_attr_e('Publisher authority', 'marketlense-core'); ?>">
            <div class="ml-section-heading ml-section-anchor">
                <p class="ml-section-kicker ml-section-eyebrow"><?php esc_html_e('AUTHORITY', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2 class="ml-section-title"><?php esc_html_e('Publisher Authority', 'marketlense-core'); ?></h2>
                    <a class="ml-inline-link" href="<?php echo esc_url(home_url('/publishers-directory/')); ?>">
                        <?php esc_html_e('Open publishers directory', 'marketlense-core'); ?>
                        <span class="ml-link-arrow" aria-hidden="true">&rarr;</span>
                    </a>
                </div>
                <span class="ml-section-rule" aria-hidden="true"></span>
                <p class="ml-section-note">
                    <?php esc_html_e('Track recurring institutions, consultancies, and specialist publishers shaping the intelligence agenda.', 'marketlense-core'); ?>
                </p>
            </div>

            <div class="ml-authority-wall">
                <?php foreach ($publishers as $publisher) : ?>
                    <article class="ml-authority-item ml-surface-card ml-surface-card--compact ml-card">
                        <div class="ml-authority-item-copy">
                            <?php if ((string) $publisher['url'] !== '') : ?>
                                <a href="<?php echo esc_url((string) $publisher['url']); ?>" class="ml-authority-name">
                                    <?php echo esc_html((string) $publisher['name']); ?>
                                </a>
                            <?php else : ?>
                                <span class="ml-authority-name"><?php echo esc_html((string) $publisher['name']); ?></span>
                            <?php endif; ?>
                            <span class="ml-authority-count">
                                <?php echo esc_html(sprintf(_n('%d report', '%d reports', (int) $publisher['count'], 'marketlense-core'), (int) $publisher['count'])); ?>
                            </span>
                        </div>
                        <?php if ((string) $publisher['url'] !== '') : ?>
                            <a class="ml-authority-homepage ml-publisher-profile-link ml-chip" href="<?php echo esc_url((string) $publisher['url']); ?>">
                                <?php esc_html_e('View profile', 'marketlense-core'); ?>
                                <span class="ml-link-arrow" aria-hidden="true">&rarr;</span>
                            </a>
                        <?php endif; ?>
                    </article>
                <?php endforeach; ?>
            </div>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders topic directory cards.
     */
    public function render_topics_directory(): string
    {
        $items = $this->stats->content_backed_terms(Taxonomies::CATEGORY_TAXONOMY, 300);
        if ($items === []) {
            return '<p>' . esc_html__('No topics are available yet.', 'marketlense-core') . '</p>';
        }

        ob_start();
        ?>
        <section class="ml-directory-list ml-topic-directory-list">
            <?php foreach ($items as $item) : ?>
                <?php $term = $item['term']; ?>
                <?php $link = get_term_link($term); ?>
                <article class="ml-directory-card">
                    <span class="ml-directory-card-index" aria-hidden="true"><?php echo esc_html(str_pad((string) $item['total'], 2, '0', STR_PAD_LEFT)); ?></span>
                    <h2>
                        <?php if (! is_wp_error($link)) : ?>
                            <a href="<?php echo esc_url((string) $link); ?>"><?php echo esc_html($term->name); ?></a>
                        <?php else : ?>
                            <?php echo esc_html($term->name); ?>
                        <?php endif; ?>
                    </h2>
                    <?php if ($term->description !== '') : ?>
                        <p><?php echo esc_html($term->description); ?></p>
                    <?php endif; ?>
                    <p class="ml-directory-count"><?php echo esc_html($this->content_count_line($item)); ?></p>
                    <?php if (! is_wp_error($link) && (int) $item['reports'] > 0) : ?>
                        <div class="ml-directory-actions">
                            <a class="ml-text-link" href="<?php echo esc_url((string) $link); ?>">
                                <?php esc_html_e('Explore related research', 'marketlense-core'); ?>
                                <span aria-hidden="true">&rarr;</span>
                            </a>
                        </div>
                    <?php endif; ?>
                </article>
            <?php endforeach; ?>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders publisher directory cards with homepage links.
     */
    public function render_publishers_directory(): string
    {
        $items = $this->stats->content_backed_terms(Taxonomies::PUBLISHER_TAXONOMY, 300);
        if ($items === []) {
            return '<p>' . esc_html__('No publishers are available yet.', 'marketlense-core') . '</p>';
        }

        ob_start();
        ?>
        <section class="ml-directory-list ml-publisher-directory-list">
            <?php foreach ($items as $item) : ?>
                <?php
                $term = $item['term'];
                $archive_link = get_term_link($term);
                $homepage = (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_HOMEPAGE_META, true);
                $insights_links = $this->publisher_external_urls(
                    (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_INSIGHTS_META, true)
                );
                $description = $this->publisher_description_excerpt($term->description);
                ?>
                <article class="ml-directory-card ml-publisher-directory-card">
                    <div class="ml-publisher-directory-mark" aria-hidden="true"><?php echo esc_html($this->publisher_monogram($term->name)); ?></div>
                    <div class="ml-publisher-directory-copy">
                        <p class="ml-directory-count"><?php echo esc_html($this->content_count_line($item)); ?></p>
                        <h2>
                            <?php if (! is_wp_error($archive_link) && (int) $item['reports'] > 0) : ?>
                                <a href="<?php echo esc_url((string) $archive_link); ?>">
                                    <?php echo esc_html($term->name); ?>
                                </a>
                            <?php else : ?>
                                <?php echo esc_html($term->name); ?>
                            <?php endif; ?>
                        </h2>
                        <?php if ($description !== '') : ?>
                            <p class="ml-directory-description"><?php echo esc_html($description); ?></p>
                        <?php endif; ?>
                        <div class="ml-directory-actions">
                            <?php if (! is_wp_error($archive_link)) : ?>
                                <a href="<?php echo esc_url((string) $archive_link); ?>">
                                    <?php esc_html_e('View represented research', 'marketlense-core'); ?>
                                </a>
                            <?php endif; ?>
                            <?php if ($homepage !== '') : ?>
                                <a href="<?php echo esc_url($homepage); ?>" target="_blank" rel="noopener noreferrer">
                                    <?php esc_html_e('Homepage', 'marketlense-core'); ?>
                                </a>
                            <?php endif; ?>
                            <?php if ($insights_links !== []) : ?>
                                <a href="<?php echo esc_url($insights_links[0]); ?>" target="_blank" rel="noopener noreferrer">
                                    <?php esc_html_e('Research hub', 'marketlense-core'); ?>
                                </a>
                            <?php endif; ?>
                        </div>
                    </div>
                </article>
            <?php endforeach; ?>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders current publisher profile metadata on taxonomy archive pages.
     */
    public function render_publisher_profile(): string
    {
        if (! is_tax(Taxonomies::PUBLISHER_TAXONOMY)) {
            return '';
        }

        $term = get_queried_object();
        if (! ($term instanceof \WP_Term)) {
            return '';
        }

        $homepage_links = $this->publisher_external_urls(
            (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_HOMEPAGE_META, true)
        );
        $insight_links = $this->publisher_external_urls(
            (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_INSIGHTS_META, true)
        );
        $icon_source = trim(
            (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_ICON_META, true)
        );

        if ($homepage_links === [] && $insight_links === [] && $icon_source === '') {
            return '';
        }

        ob_start();
        ?>
        <section class="ml-publisher-profile" aria-label="<?php esc_attr_e('Publisher profile', 'marketlense-core'); ?>">
            <div class="ml-publisher-profile-shell">
                <?php if ($icon_source !== '') : ?>
                    <div class="ml-publisher-profile-icon">
                        <?php echo $this->publisher_icon_markup($icon_source, $term->name); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                    </div>
                <?php endif; ?>
                <div class="ml-publisher-profile-content">
                    <p class="ml-publisher-profile-label"><?php esc_html_e('Publisher profile', 'marketlense-core'); ?></p>
                    <div class="ml-publisher-profile-actions">
                        <?php if ($homepage_links !== []) : ?>
                            <a class="ml-button ml-button-primary" href="<?php echo esc_url($homepage_links[0]); ?>" target="_blank" rel="noopener noreferrer">
                                <?php esc_html_e('Visit homepage', 'marketlense-core'); ?>
                            </a>
                        <?php endif; ?>
                        <?php foreach ($insight_links as $index => $url) : ?>
                            <a class="ml-button ml-button-outline" href="<?php echo esc_url($url); ?>" target="_blank" rel="noopener noreferrer">
                                <?php
                                echo esc_html(
                                    $index === 0
                                        ? __('Open insights', 'marketlense-core')
                                        : sprintf(__('Open insights %d', 'marketlense-core'), $index + 1)
                                );
                                ?>
                            </a>
                        <?php endforeach; ?>
                    </div>
                </div>
            </div>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders a deploy-safe internal CTA button.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_button_link(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'target' => '',
                'label' => '',
                'style' => 'primary',
            ],
            $attrs,
            'ml_button_link'
        );

        $url = $this->resolve_internal_url((string) $atts['target']);
        $label = trim((string) $atts['label']);
        $style = sanitize_key((string) $atts['style']);
        if ($url === '' || $label === '') {
            return '';
        }

        $wrapper_class = $style === 'outline'
            ? 'wp-block-button is-style-outline'
            : 'wp-block-button';

        ob_start();
        ?>
        <div class="<?php echo esc_attr($wrapper_class); ?>">
            <a class="wp-block-button__link wp-element-button ml-button" href="<?php echo esc_url($url); ?>">
                <?php echo esc_html($label); ?>
            </a>
        </div>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders a deploy-safe inline link.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_inline_link(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'target' => '',
                'label' => '',
                'show_arrow' => '1',
            ],
            $attrs,
            'ml_inline_link'
        );

        $url = $this->resolve_internal_url((string) $atts['target']);
        $label = trim((string) $atts['label']);
        if ($url === '' || $label === '') {
            return '';
        }

        ob_start();
        ?>
        <p class="ml-inline-link">
            <a href="<?php echo esc_url($url); ?>">
                <?php echo esc_html($label); ?>
                <?php if ($this->to_bool_flag($atts['show_arrow'])) : ?>
                    <span class="ml-link-arrow" aria-hidden="true">&rarr;</span>
                <?php endif; ?>
            </a>
        </p>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders the primary site navigation.
     */
    public function render_primary_nav(): string
    {
        $items = [
            ['label' => __('Reports', 'marketlense-core'), 'target' => 'reports'],
            ['label' => __('Topics', 'marketlense-core'), 'target' => 'topics-directory'],
            ['label' => __('Publishers', 'marketlense-core'), 'target' => 'publishers-directory'],
            ['label' => __('Signals', 'marketlense-core'), 'target' => 'signals'],
            ['label' => __('Briefings', 'marketlense-core'), 'target' => 'briefings'],
            ['label' => __('Methodology', 'marketlense-core'), 'target' => 'methodology'],
        ];

        return $this->render_navigation(
            $items,
            'ml-primary-nav',
            __('Primary navigation', 'marketlense-core')
        ) . $this->render_mobile_navigation($items);
    }

    /**
     * Renders a footer navigation column.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_footer_nav(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'menu' => 'navigate',
            ],
            $attrs,
            'ml_footer_nav'
        );

        $menu = sanitize_key((string) $atts['menu']);
        if ($menu === 'utilities') {
            $items = [
                ['label' => __('Methodology', 'marketlense-core'), 'target' => 'methodology'],
                ['label' => __('Contact', 'marketlense-core'), 'target' => 'contact'],
                ['label' => __('Privacy', 'marketlense-core'), 'target' => 'privacy'],
                ['label' => __('Terms', 'marketlense-core'), 'target' => 'terms'],
            ];
            $label = __('Footer utilities', 'marketlense-core');
        } else {
            $items = [
                ['label' => __('Reports', 'marketlense-core'), 'target' => 'reports'],
                ['label' => __('Topics', 'marketlense-core'), 'target' => 'topics-directory'],
                ['label' => __('Publishers', 'marketlense-core'), 'target' => 'publishers-directory'],
                ['label' => __('Signals', 'marketlense-core'), 'target' => 'signals'],
                ['label' => __('Briefings', 'marketlense-core'), 'target' => 'briefings'],
                ['label' => __('About', 'marketlense-core'), 'target' => 'about'],
            ];
            $label = __('Footer navigation', 'marketlense-core');
        }

        return $this->render_navigation($items, 'ml-footer-nav', $label);
    }

    /**
     * Renders a dynamic archive coverage metric for theme-owned page heroes.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_archive_metric(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'entity' => 'reports',
                'label' => __('Archive coverage', 'marketlense-core'),
                'icon' => '',
            ],
            $attrs,
            'ml_archive_metric'
        );
        $entity = sanitize_key((string) $atts['entity']);
        $label = sanitize_text_field((string) $atts['label']);
        $icon = sanitize_key((string) $atts['icon']);
        $metrics = $this->stats->homepage_metrics();

        $values = [
            'reports' => [
                (int) $metrics['report_count'],
                __('published report', 'marketlense-core'),
                __('published reports', 'marketlense-core'),
            ],
            'topics' => [
                count($this->stats->content_backed_terms(Taxonomies::CATEGORY_TAXONOMY)),
                __('content-backed topic', 'marketlense-core'),
                __('content-backed topics', 'marketlense-core'),
            ],
            'publishers' => [
                count($this->stats->content_backed_terms(Taxonomies::PUBLISHER_TAXONOMY)),
                __('represented publisher', 'marketlense-core'),
                __('represented publishers', 'marketlense-core'),
            ],
            'regions' => [
                count($this->stats->report_regions()),
                __('covered region', 'marketlense-core'),
                __('covered regions', 'marketlense-core'),
            ],
            'signals' => [
                (int) $metrics['signal_count'],
                (string) $metrics['signal_label'] === __('Published signals', 'marketlense-core')
                    ? __('published signal', 'marketlense-core')
                    : __('report signal', 'marketlense-core'),
                strtolower((string) $metrics['signal_label']),
            ],
            'briefings' => [
                (int) $metrics['briefing_count'],
                __('executive briefing', 'marketlense-core'),
                __('executive briefings', 'marketlense-core'),
            ],
        ];
        if ($entity === 'current-term') {
            $term = get_queried_object();
            if (! ($term instanceof \WP_Term)) {
                return '';
            }
            $values[$entity] = [
                max(0, (int) $term->count),
                __('published record', 'marketlense-core'),
                __('published records', 'marketlense-core'),
            ];
        }
        if (! isset($values[$entity])) {
            return '';
        }

        [$count, $singular, $plural] = $values[$entity];
        $count_label = sprintf(_n('%1$d %2$s', '%1$d %3$s', $count, 'marketlense-core'), $count, $singular, $plural);

        return sprintf(
            '<div class="ml-directory-principle ml-archive-metric" aria-label="%1$s"><span class="ml-archive-metric-icon ml-archive-metric-icon--%2$s" aria-hidden="true"></span><span class="ml-archive-metric-content"><span class="ml-archive-metric-value">%3$s</span><strong>%4$s</strong></span></div>',
            esc_attr($count_label),
            esc_attr($icon !== '' ? $icon : $entity),
            esc_html(number_format_i18n($count)),
            esc_html($label)
        );
    }

    /**
     * @param array<string,mixed> $attrs
     */
    private function render_entity_archive(
        array $attrs,
        string $shortcode,
        string $post_type,
        string $aria_label,
        string $empty_copy,
        string $link_label
    ): string {
        $atts = shortcode_atts(
            [
                'per_page' => (string) self::DEFAULT_PER_PAGE,
            ],
            $attrs,
            $shortcode
        );
        $per_page = max(1, min(48, (int) $atts['per_page']));
        $query = new \WP_Query(
            [
                'post_type' => $post_type,
                'post_status' => 'publish',
                'posts_per_page' => $per_page,
                'orderby' => 'date',
                'order' => 'DESC',
                'no_found_rows' => true,
            ]
        );

        ob_start();
        ?>
        <section class="ml-entity-archive ml-report-browser-results" aria-label="<?php echo esc_attr($aria_label); ?>">
            <?php if ($query->have_posts()) : ?>
                <div class="ml-report-browser-grid">
                    <?php while ($query->have_posts()) : ?>
                        <?php
                        $query->the_post();
                        $post = get_post();
                        if (! ($post instanceof \WP_Post)) {
                            continue;
                        }
                        $this->render_entity_card($post, $link_label);
                        ?>
                    <?php endwhile; ?>
                </div>
            <?php else : ?>
                <?php $this->render_institutional_empty_state($empty_copy); ?>
            <?php endif; ?>
            <?php wp_reset_postdata(); ?>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Uses source-backed report metrics as signals until standalone Signal posts exist.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    private function render_report_signal_archive(array $attrs): string
    {
        $atts = shortcode_atts(
            ['per_page' => (string) self::DEFAULT_PER_PAGE],
            $attrs,
            'ml_signals_index'
        );
        $per_page = max(1, min(48, (int) $atts['per_page']));
        $posts = get_posts(
            Meta::apply_digest_query_constraints(
                [
                    'post_status' => 'publish',
                    'posts_per_page' => $per_page,
                    'orderby' => 'date',
                    'order' => 'DESC',
                ]
            )
        );

        ob_start();
        ?>
        <section class="ml-signal-directory" aria-label="<?php esc_attr_e('Published report signals', 'marketlense-core'); ?>">
            <?php foreach ($posts as $post) : ?>
                <?php
                if (! ($post instanceof \WP_Post)) {
                    continue;
                }
                $record = $this->view_model_builder->build($post);
                $metrics = array_values(
                    array_filter(
                        is_array($record['full_key_metrics'] ?? null) ? $record['full_key_metrics'] : [],
                        static fn ($metric): bool => trim((string) $metric) !== ''
                    )
                );
                $metric_index = count($metrics) > 1
                    ? wp_rand(0, count($metrics) - 1)
                    : 0;
                $signal = $metrics !== [] ? trim((string) $metrics[$metric_index]) : '';
                if ($signal === '') {
                    continue;
                }
                $permalink = get_permalink($post);
                ?>
                <article class="ml-report-signal-card" aria-label="<?php esc_attr_e('Report signal', 'marketlense-core'); ?>">
                    <p class="ml-section-kicker"><?php esc_html_e('Source-backed signal', 'marketlense-core'); ?></p>
                    <h2><?php echo esc_html($signal); ?></h2>
                    <p class="ml-report-signal-source">
                        <strong><?php esc_html_e('Source report:', 'marketlense-core'); ?></strong>
                        <?php echo esc_html(get_the_title($post)); ?>
                        <span aria-hidden="true"> / </span>
                        <?php echo esc_html($this->joined_text([(string) ($record['publisher'] ?? ''), (string) ($record['date'] ?? '')])); ?>
                    </p>
                    <?php $this->render_evidence_counts($record); ?>
                    <a class="ml-text-link" href="<?php echo esc_url(is_string($permalink) ? $permalink : ''); ?>">
                        <?php esc_html_e('Review source context', 'marketlense-core'); ?>
                        <span aria-hidden="true">&rarr;</span>
                    </a>
                </article>
            <?php endforeach; ?>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders the canonical Market Bearing wordmark.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_brand_logo(array $attrs = []): string
    {
        $atts = shortcode_atts(
            ['mode' => 'header'],
            $attrs,
            'ml_brand_logo'
        );
        $mode = sanitize_key((string) $atts['mode']);
        $class_name = $mode === 'footer'
            ? 'ml-brand-logo ml-brand-logo--footer'
            : 'ml-brand-logo';

        return sprintf(
            '<a class="%1$s" href="%2$s" aria-label="%3$s"><span class="ml-brand-mark">Market<span>Bearing</span></span><span class="ml-brand-rule" aria-hidden="true"></span></a>',
            esc_attr($class_name),
            esc_url(home_url('/')),
            esc_attr__('Market Bearing home', 'marketlense-core')
        );
    }

    private function render_entity_card(\WP_Post $post, string $link_label): void
    {
        $permalink = get_permalink($post);
        $record = $this->view_model_builder->build($post);
        $excerpt = $this->public_editorial_text((string) ($record['archive_excerpt'] ?? ''));
        ?>
        <article class="ml-report-card ml-surface-card ml-surface-card--standard ml-card">
            <div class="ml-report-card-body">
                <p class="ml-report-card-kicker"><?php echo esc_html((string) get_the_date('', $post)); ?></p>
                <h3 class="ml-report-card-title">
                    <a href="<?php echo esc_url(is_string($permalink) ? $permalink : ''); ?>">
                        <?php echo esc_html(get_the_title($post)); ?>
                    </a>
                </h3>
                <?php if ($excerpt !== '') : ?>
                    <p class="ml-report-card-excerpt"><?php echo esc_html($excerpt); ?></p>
                <?php endif; ?>
                <?php $this->render_evidence_counts($record); ?>
                <p class="ml-report-card-link">
                    <a href="<?php echo esc_url(is_string($permalink) ? $permalink : ''); ?>">
                        <?php echo esc_html($link_label); ?>
                        <span class="ml-link-arrow" aria-hidden="true">&rarr;</span>
                    </a>
                </p>
            </div>
        </article>
        <?php
    }

    private function render_featured_entity_card(\WP_Post $post, string $link_label): void
    {
        $permalink = get_permalink($post);
        $excerpt = $this->public_editorial_text((string) get_the_excerpt($post));
        $record = $this->view_model_builder->build($post);
        $thumbnail = get_the_post_thumbnail(
            $post,
            'large',
            [
                'loading' => 'eager',
                'fetchpriority' => 'high',
                'sizes' => '(max-width: 720px) 100vw, 42rem',
            ]
        );
        ?>
        <article class="ml-featured-digest-card ml-featured-briefing-card ml-surface-card ml-surface-card--standard ml-card">
            <?php if (is_string($thumbnail) && $thumbnail !== '') : ?>
                <a class="ml-featured-media" href="<?php echo esc_url(is_string($permalink) ? $permalink : ''); ?>">
                    <?php echo $thumbnail; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                </a>
            <?php endif; ?>

            <div class="ml-featured-copy ml-featured-content">
                <div class="ml-featured-header">
                    <div class="ml-featured-meta ml-featured-meta-block">
                        <p class="ml-featured-meta-line ml-featured-meta-date">
                            <strong><?php esc_html_e('Publish date:', 'marketlense-core'); ?></strong>
                            <span><?php echo esc_html((string) get_the_date('', $post)); ?></span>
                        </p>
                    </div>
                </div>
                <h3 class="ml-featured-title">
                    <a href="<?php echo esc_url(is_string($permalink) ? $permalink : ''); ?>">
                        <?php echo esc_html(get_the_title($post)); ?>
                    </a>
                </h3>

                <?php if ($excerpt !== '') : ?>
                    <p class="ml-featured-excerpt"><?php echo esc_html($excerpt); ?></p>
                <?php endif; ?>
                <?php $this->render_evidence_counts($record); ?>

                <p class="ml-report-card-link ml-featured-link">
                    <a href="<?php echo esc_url(is_string($permalink) ? $permalink : ''); ?>">
                        <?php echo esc_html($link_label); ?>
                        <span class="ml-link-arrow" aria-hidden="true">&rarr;</span>
                    </a>
                </p>
            </div>
        </article>
        <?php
    }

    /**
     * @param array<string,mixed> $record
     */
    private function render_evidence_counts(array $record): void
    {
        $items = [
            sprintf(_n('%d finding', '%d findings', (int) ($record['insights_count'] ?? 0), 'marketlense-core'), (int) ($record['insights_count'] ?? 0)),
            sprintf(_n('%d quote', '%d quotes', (int) ($record['quotes_count'] ?? 0), 'marketlense-core'), (int) ($record['quotes_count'] ?? 0)),
            sprintf(_n('%d citation', '%d citations', (int) ($record['citations_count'] ?? 0), 'marketlense-core'), (int) ($record['citations_count'] ?? 0)),
        ];
        $items = array_values(
            array_filter(
                $items,
                static fn (string $item): bool => ! str_starts_with($item, '0 ')
            )
        );
        if ($items === []) {
            return;
        }
        ?>
        <p class="ml-card-citations"><?php echo esc_html(implode(' / ', $items)); ?></p>
        <?php
    }

    private function public_editorial_text(string $text): string
    {
        $clean = wp_strip_all_tags($text);
        $clean = (string) preg_replace(
            '/\b[A-Za-z0-9_-]{12,}:(?:finding|quote|claim|metric):[A-Za-z0-9_-]+\b/i',
            __('source evidence', 'marketlense-core'),
            $clean
        );
        $clean = (string) preg_replace('/\s+/', ' ', $clean);

        return trim($clean);
    }

    private function render_institutional_empty_state(string $copy): void
    {
        ?>
        <div class="ml-empty-state ml-institutional-empty-state">
            <p><?php echo esc_html($copy); ?></p>
        </div>
        <?php
    }

    /**
     * @param array<int,array<string,mixed>> $items
     */
    private function render_signal_column(string $title, array $items, string $class_name = 'ml-signal-column'): void
    {
        ?>
        <section class="<?php echo esc_attr(trim($class_name . ' ml-signals-column ml-surface-card ml-surface-card--compact ml-card')); ?>">
            <h3 class="ml-signals-column-title"><?php echo esc_html($title); ?></h3>
            <?php if ($items === []) : ?>
                <p class="ml-signal-empty"><?php esc_html_e('No recent movement yet.', 'marketlense-core'); ?></p>
            <?php else : ?>
                <ul class="ml-signal-list">
                    <?php foreach ($items as $item) : ?>
                        <li class="ml-signal-item ml-signal-row">
                            <div class="ml-signal-item-main">
                                <?php if ((string) $item['url'] !== '') : ?>
                                    <a class="ml-signal-topic" href="<?php echo esc_url((string) $item['url']); ?>">
                                        <?php echo esc_html((string) $item['name']); ?>
                                    </a>
                                <?php else : ?>
                                    <span class="ml-signal-topic"><?php echo esc_html((string) $item['name']); ?></span>
                                <?php endif; ?>
                            </div>
                            <span class="ml-signal-indicator">
                                <?php $this->render_delta_badge($item['delta'] ?? null); ?>
                                <span class="ml-signal-count"><?php echo esc_html((string) $item['count']); ?></span>
                            </span>
                        </li>
                    <?php endforeach; ?>
                </ul>
            <?php endif; ?>
        </section>
        <?php
    }

    /**
     * @param int|null $delta
     */
    private function render_delta_badge($delta): void
    {
        if (! is_int($delta) || $delta === 0) {
            return;
        }

        $class_name = $delta > 0 ? 'is-up' : 'is-down';
        $symbol = $delta > 0 ? "\u{25B2}" : "\u{2022}";
        ?>
        <span class="ml-delta-badge ml-signal-trend <?php echo esc_attr($class_name); ?>" aria-hidden="true"><?php echo esc_html($symbol); ?></span>
        <?php
    }

    /**
     * Resolves a validated filter slug from query string.
     */
    private function selected_filter_slug(string $query_key, string $taxonomy): string
    {
        if (! isset($_GET[$query_key])) {
            return $this->current_archive_term_slug($query_key, $taxonomy);
        }

        $raw = wp_unslash((string) $_GET[$query_key]);
        $slug = sanitize_title($raw);
        if ($slug === '') {
            return '';
        }

        $term = get_term_by('slug', $slug, $taxonomy);
        if (! ($term instanceof \WP_Term)) {
            return $this->current_archive_term_slug($query_key, $taxonomy);
        }

        return $slug;
    }

    /**
     * Resolves the canonical topic filter slug from category archives or query string.
     */
    private function selected_topic_slug(): string
    {
        $slug = $this->selected_filter_slug(self::TOPIC_QUERY_KEY, Taxonomies::CATEGORY_TAXONOMY);
        if ($slug !== '') {
            return $slug;
        }

        if (! isset($_GET[self::LEGACY_TOPIC_QUERY_KEY])) {
            return '';
        }

        $raw = wp_unslash((string) $_GET[self::LEGACY_TOPIC_QUERY_KEY]);
        $legacy_slug = sanitize_title($raw);
        if ($legacy_slug === '') {
            return '';
        }

        $term = get_term_by('slug', $legacy_slug, Taxonomies::CATEGORY_TAXONOMY);

        return $term instanceof \WP_Term ? $legacy_slug : '';
    }

    /**
     * Resolves the current archive term slug when viewing a taxonomy archive directly.
     */
    private function current_archive_term_slug(string $query_key, string $taxonomy): string
    {
        if ($taxonomy === Taxonomies::CATEGORY_TAXONOMY) {
            if (! is_category()) {
                return '';
            }
        } elseif (! is_tax($taxonomy)) {
            return '';
        }

        $term = get_queried_object();
        if (! ($term instanceof \WP_Term)) {
            return '';
        }

        return sanitize_title($term->slug);
    }

    /**
     * Renders pagination preserving active query params.
     *
     * @param \WP_Query            $query Query object.
     * @param array<string,string> $active_args Active query args.
     */
    private function render_pagination(\WP_Query $query, array $active_args): void
    {
        if ($query->max_num_pages <= 1) {
            return;
        }

        $pagination = paginate_links(
            [
                'base' => str_replace('999999999', '%#%', (string) esc_url(get_pagenum_link(999999999))),
                'current' => max(1, $this->current_page()),
                'total' => (int) $query->max_num_pages,
                'type' => 'array',
                'mid_size' => 1,
                'end_size' => 1,
                'prev_text' => __('Previous', 'marketlense-core'),
                'next_text' => __('Next', 'marketlense-core'),
                'add_args' => $active_args,
            ]
        );

        if (! is_array($pagination) || $pagination === []) {
            return;
        }

        echo '<nav class="ml-pagination" aria-label="' . esc_attr__('Pagination', 'marketlense-core') . '"><ul>';
        foreach ($pagination as $item) {
            echo '<li>' . wp_kses_post($item) . '</li>';
        }
        echo '</ul></nav>';
    }

    /**
     * Resolves current pagination index for archive/page contexts.
     */
    private function current_page(): int
    {
        $paged = (int) get_query_var('paged');
        if ($paged > 0) {
            return $paged;
        }

        $page = (int) get_query_var('page');
        if ($page > 0) {
            return $page;
        }

        if (isset($_GET['paged'])) {
            $query_paged = (int) sanitize_text_field(wp_unslash((string) $_GET['paged']));
            if ($query_paged > 0) {
                return $query_paged;
            }
        }

        return 1;
    }

    private function enqueue_report_filter_assets(): void
    {
        wp_enqueue_script(
            'marketlense-core-report-filters',
            MARKETLENSE_CORE_URL . 'assets/js/report-filters.js',
            [],
            MARKETLENSE_CORE_VERSION,
            true
        );
    }

    /**
     * @param array{topic:string,publisher:string,period:string,region:string,search:string} $filters
     * @return array<string,mixed>
     */
    private function report_browser_query_args(array $filters, int $posts_per_page, int $paged = 1, string $exclude = ''): array
    {
        $query_args = [
            'post_status' => 'publish',
            'posts_per_page' => $posts_per_page,
            'paged' => $paged,
        ];

        if ($filters['search'] !== '') {
            $query_args['s'] = $filters['search'];
        }

        $meta_filters = [];
        if ($exclude !== 'period' && $filters['period'] !== '') {
            $meta_filters[] = [
                'key' => Meta::META_TIME_PERIOD,
                'value' => $filters['period'],
                'compare' => '=',
            ];
        }
        if ($exclude !== 'region' && $filters['region'] !== '') {
            $meta_filters[] = [
                'key' => Meta::META_REGION,
                'value' => $filters['region'],
                'compare' => '=',
            ];
        }
        if ($meta_filters !== []) {
            $query_args['meta_query'] = count($meta_filters) > 1
                ? array_merge(['relation' => 'AND'], $meta_filters)
                : $meta_filters;
        }

        $tax_query = ['relation' => 'AND'];
        if ($exclude !== 'topic' && $filters['topic'] !== '') {
            $tax_query[] = [
                'taxonomy' => Taxonomies::CATEGORY_TAXONOMY,
                'field' => 'slug',
                'terms' => [$filters['topic']],
            ];
        }
        if ($exclude !== 'publisher' && $filters['publisher'] !== '') {
            $tax_query[] = [
                'taxonomy' => Taxonomies::PUBLISHER_TAXONOMY,
                'field' => 'slug',
                'terms' => [$filters['publisher']],
            ];
        }
        if (count($tax_query) > 1) {
            $query_args['tax_query'] = $tax_query;
        }

        return Meta::apply_report_card_query_constraints($query_args);
    }

    /**
     * @param array{topic:string,publisher:string,period:string,region:string,search:string} $filters
     * @return list<int>
     */
    private function report_facet_post_ids(array $filters, string $exclude): array
    {
        $query_args = $this->report_browser_query_args($filters, -1, 1, $exclude);
        $query_args['fields'] = 'ids';
        $query_args['no_found_rows'] = true;

        $query = new \WP_Query($query_args);
        $ids = array_values(
            array_filter(
                array_map('intval', $query->posts),
                static fn (int $post_id): bool => $post_id > 0
            )
        );
        wp_reset_postdata();

        return $ids;
    }

    /**
     * @param array{topic:string,publisher:string,period:string,region:string,search:string} $filters
     * @return list<\WP_Term>
     */
    private function report_facet_terms(string $taxonomy, array $filters, string $exclude): array
    {
        $post_ids = $this->report_facet_post_ids($filters, $exclude);
        $items = [];
        foreach ($post_ids as $post_id) {
            $terms = get_the_terms($post_id, $taxonomy);
            if (! is_array($terms)) {
                continue;
            }
            foreach ($terms as $term) {
                if (! ($term instanceof \WP_Term)) {
                    continue;
                }
                if (! isset($items[$term->term_id])) {
                    $items[$term->term_id] = clone $term;
                    $items[$term->term_id]->count = 0;
                }
                $items[$term->term_id]->count++;
            }
        }

        $terms = array_values($items);
        usort(
            $terms,
            static function (\WP_Term $left, \WP_Term $right): int {
                $count_compare = (int) $right->count <=> (int) $left->count;
                if ($count_compare !== 0) {
                    return $count_compare;
                }

                return strcasecmp($left->name, $right->name);
            }
        );

        return $terms;
    }

    /**
     * @param array{topic:string,publisher:string,period:string,region:string,search:string} $filters
     * @return list<array{value:string,count:int}>
     */
    private function report_facet_meta_values(string $meta_key, array $filters, string $exclude): array
    {
        $post_ids = $this->report_facet_post_ids($filters, $exclude);
        $counts = [];
        foreach ($post_ids as $post_id) {
            $value = trim((string) get_post_meta($post_id, $meta_key, true));
            if ($value === '' || $value === '...' || strcasecmp($value, 'not extracted') === 0) {
                continue;
            }
            $counts[$value] = ($counts[$value] ?? 0) + 1;
        }

        ksort($counts, SORT_NATURAL | SORT_FLAG_CASE);
        $values = [];
        foreach ($counts as $value => $count) {
            $values[] = [
                'value' => (string) $value,
                'count' => (int) $count,
            ];
        }

        return $values;
    }

    /**
     * @param array<string,string> $args
     */
    private function render_hidden_query_inputs(array $args): void
    {
        foreach ($args as $name => $value) {
            if ($value === '') {
                continue;
            }
            printf(
                '<input type="hidden" name="%1$s" value="%2$s">',
                esc_attr($name),
                esc_attr($value)
            );
        }
    }

    /**
     * @param array<string,string> $active_filters
     */
    private function render_active_filter_chips(
        string $archive_url,
        array $active_filters,
        string $search_term,
        string $selected_sort,
        ?\WP_Term $selected_topic_term,
        ?\WP_Term $selected_publisher_term,
        string $selected_period,
        string $selected_region
    ): void {
        if ($active_filters === [] && $search_term === '') {
            return;
        }

        $sort_arg = $selected_sort !== 'latest' ? $selected_sort : null;
        ?>
        <div class="ml-active-filters" aria-label="<?php esc_attr_e('Active filters', 'marketlense-core'); ?>">
            <span class="ml-active-filters-label"><?php esc_html_e('Selected', 'marketlense-core'); ?></span>
            <?php if ($search_term !== '') : ?>
                <?php
                $search_reset = add_query_arg(
                    [
                        self::TOPIC_QUERY_KEY => $active_filters[self::TOPIC_QUERY_KEY] ?? null,
                        'ml_publisher' => $active_filters['ml_publisher'] ?? null,
                        'ml_period' => $active_filters['ml_period'] ?? null,
                        'ml_region' => $active_filters['ml_region'] ?? null,
                        'ml_sort' => $sort_arg,
                    ],
                    $archive_url
                );
                ?>
                <a class="ml-filter-chip" href="<?php echo esc_url((string) $search_reset); ?>">
                    <?php echo esc_html(sprintf(__('Search: %s', 'marketlense-core'), $search_term)); ?>
                </a>
            <?php endif; ?>
            <?php if ($selected_topic_term instanceof \WP_Term) : ?>
                <?php
                $topic_reset = add_query_arg(
                    [
                        's' => $search_term !== '' ? $search_term : null,
                        'ml_publisher' => $active_filters['ml_publisher'] ?? null,
                        'ml_period' => $active_filters['ml_period'] ?? null,
                        'ml_region' => $active_filters['ml_region'] ?? null,
                        'ml_sort' => $sort_arg,
                    ],
                    $archive_url
                );
                ?>
                <a class="ml-filter-chip" href="<?php echo esc_url((string) $topic_reset); ?>">
                    <?php echo esc_html(sprintf(__('Category: %s', 'marketlense-core'), $selected_topic_term->name)); ?>
                </a>
            <?php endif; ?>
            <?php if ($selected_publisher_term instanceof \WP_Term) : ?>
                <?php
                $publisher_reset = add_query_arg(
                    [
                        's' => $search_term !== '' ? $search_term : null,
                        self::TOPIC_QUERY_KEY => $active_filters[self::TOPIC_QUERY_KEY] ?? null,
                        'ml_period' => $active_filters['ml_period'] ?? null,
                        'ml_region' => $active_filters['ml_region'] ?? null,
                        'ml_sort' => $sort_arg,
                    ],
                    $archive_url
                );
                ?>
                <a class="ml-filter-chip" href="<?php echo esc_url((string) $publisher_reset); ?>">
                    <?php echo esc_html(sprintf(__('Publisher: %s', 'marketlense-core'), $selected_publisher_term->name)); ?>
                </a>
            <?php endif; ?>
            <?php if ($selected_period !== '') : ?>
                <?php
                $period_reset = add_query_arg(
                    [
                        's' => $search_term !== '' ? $search_term : null,
                        self::TOPIC_QUERY_KEY => $active_filters[self::TOPIC_QUERY_KEY] ?? null,
                        'ml_publisher' => $active_filters['ml_publisher'] ?? null,
                        'ml_region' => $active_filters['ml_region'] ?? null,
                        'ml_sort' => $sort_arg,
                    ],
                    $archive_url
                );
                ?>
                <a class="ml-filter-chip" href="<?php echo esc_url((string) $period_reset); ?>">
                    <?php echo esc_html(sprintf(__('Period: %s', 'marketlense-core'), $selected_period)); ?>
                </a>
            <?php endif; ?>
            <?php if ($selected_region !== '') : ?>
                <?php
                $region_reset = add_query_arg(
                    [
                        's' => $search_term !== '' ? $search_term : null,
                        self::TOPIC_QUERY_KEY => $active_filters[self::TOPIC_QUERY_KEY] ?? null,
                        'ml_publisher' => $active_filters['ml_publisher'] ?? null,
                        'ml_period' => $active_filters['ml_period'] ?? null,
                        'ml_sort' => $sort_arg,
                    ],
                    $archive_url
                );
                ?>
                <a class="ml-filter-chip" href="<?php echo esc_url((string) $region_reset); ?>">
                    <?php echo esc_html(sprintf(__('Region: %s', 'marketlense-core'), $selected_region)); ?>
                </a>
            <?php endif; ?>
            <a class="ml-filter-chip ml-filter-chip-clear" href="<?php echo esc_url($archive_url); ?>">
                <?php esc_html_e('Clear all', 'marketlense-core'); ?>
            </a>
        </div>
        <?php
    }

    /**
     * @param array<string,string> $state_args
     */
    private function render_report_sort_controls(string $archive_url, array $state_args, string $selected_sort): void
    {
        $sort_options = [
            'latest' => [
                'label' => __('Newest', 'marketlense-core'),
                'title' => __('Newest first', 'marketlense-core'),
                'icon' => 'latest',
            ],
            'oldest' => [
                'label' => __('Oldest', 'marketlense-core'),
                'title' => __('Oldest first', 'marketlense-core'),
                'icon' => 'oldest',
            ],
            'title' => [
                'label' => __('A-Z', 'marketlense-core'),
                'title' => __('Title A-Z', 'marketlense-core'),
                'icon' => 'title',
            ],
        ];
        ?>
        <nav class="ml-report-sort-controls" aria-label="<?php esc_attr_e('Sort reports', 'marketlense-core'); ?>">
            <?php foreach ($sort_options as $sort => $option) : ?>
                <?php
                $sort_args = $state_args;
                if ($sort === 'latest') {
                    unset($sort_args['ml_sort']);
                } else {
                    $sort_args['ml_sort'] = $sort;
                }
                $sort_url = add_query_arg($sort_args, $archive_url);
                ?>
                <a class="ml-report-sort-control <?php echo $selected_sort === $sort ? 'is-active' : ''; ?>" href="<?php echo esc_url((string) $sort_url); ?>" aria-label="<?php echo esc_attr((string) $option['title']); ?>" title="<?php echo esc_attr((string) $option['title']); ?>">
                    <span class="ml-report-sort-icon ml-report-sort-icon--<?php echo esc_attr((string) $option['icon']); ?>" aria-hidden="true"></span>
                    <span class="ml-report-sort-tooltip"><?php echo esc_html((string) $option['label']); ?></span>
                </a>
            <?php endforeach; ?>
        </nav>
        <?php
    }

    private function selected_sort(): string
    {
        if (! isset($_GET['ml_sort'])) {
            return 'latest';
        }

        $sort = sanitize_key((string) wp_unslash($_GET['ml_sort']));

        return in_array($sort, ['latest', 'oldest', 'title'], true) ? $sort : 'latest';
    }

    private function selected_search_term(): string
    {
        if (! isset($_GET['s'])) {
            return trim((string) get_search_query());
        }

        return sanitize_text_field(wp_unslash((string) $_GET['s']));
    }

    /**
     * @param list<string> $period_options
     */
    private function selected_period(array $period_options): string
    {
        if (! isset($_GET['ml_period'])) {
            return '';
        }

        $period = sanitize_text_field(wp_unslash((string) $_GET['ml_period']));

        return in_array($period, $period_options, true) ? $period : '';
    }

    /**
     * @param list<string> $region_options
     */
    private function selected_region(array $region_options): string
    {
        if (! isset($_GET['ml_region'])) {
            return '';
        }

        $region = sanitize_text_field(wp_unslash((string) $_GET['ml_region']));

        return in_array($region, $region_options, true) ? $region : '';
    }

    /**
     * @param array<string,mixed> $query_args
     * @return array<string,mixed>
     */
    private function apply_sort_to_query_args(array $query_args, string $sort): array
    {
        return match ($sort) {
            'oldest' => array_merge($query_args, ['orderby' => 'date', 'order' => 'ASC']),
            'title' => array_merge($query_args, ['orderby' => 'title', 'order' => 'ASC']),
            default => array_merge($query_args, ['orderby' => 'date', 'order' => 'DESC']),
        };
    }

    private function sort_label(string $sort): string
    {
        return match ($sort) {
            'oldest' => __('Oldest first', 'marketlense-core'),
            'title' => __('Title A-Z', 'marketlense-core'),
            default => __('Newest first', 'marketlense-core'),
        };
    }

    private function browser_context_copy(
        ?\WP_Term $selected_topic,
        ?\WP_Term $selected_publisher,
        string $selected_period = '',
        string $selected_region = ''
    ): string
    {
        $context_suffix = [];
        if ($selected_period !== '') {
            $context_suffix[] = sprintf(__('Period: %s.', 'marketlense-core'), $selected_period);
        }
        if ($selected_region !== '') {
            $context_suffix[] = sprintf(__('Region: %s.', 'marketlense-core'), $selected_region);
        }
        $suffix = $context_suffix === [] ? '' : ' ' . implode(' ', $context_suffix);

        if ($selected_topic instanceof \WP_Term && $selected_publisher instanceof \WP_Term) {
            return sprintf(
                __('Focused on %1$s from %2$s.', 'marketlense-core'),
                $selected_topic->name,
                $selected_publisher->name
            ) . $suffix;
        }

        if ($selected_topic instanceof \WP_Term) {
            return sprintf(__('Focused on the %s topic.', 'marketlense-core'), $selected_topic->name) . $suffix;
        }

        if ($selected_publisher instanceof \WP_Term) {
            return sprintf(__('Focused on %s coverage.', 'marketlense-core'), $selected_publisher->name) . $suffix;
        }

        if ($context_suffix !== []) {
            return trim(implode(' ', $context_suffix));
        }

        return '';
    }

    private function topic_entity_fallback_query(
        string $topic_slug,
        string $search_term,
        int $per_page,
        int $current_page,
        string $sort
    ): \WP_Query {
        $query_args = $this->apply_sort_to_query_args(
            [
                'post_type' => Post_Type::BRIEFING_POST_TYPE,
                'post_status' => 'publish',
                'posts_per_page' => $per_page,
                'paged' => $current_page,
                'tax_query' => [
                    [
                        'taxonomy' => Taxonomies::CATEGORY_TAXONOMY,
                        'field' => 'slug',
                        'terms' => [$topic_slug],
                    ],
                ],
            ],
            $sort
        );
        if ($search_term !== '') {
            $query_args['s'] = $search_term;
        }

        return new \WP_Query($query_args);
    }

    /**
     * @param array{reports:int,briefings:int,signals:int,total:int} $item
     */
    private function content_count_line(array $item): string
    {
        $parts = [];
        foreach (
            [
                'reports' => [__('report', 'marketlense-core'), __('reports', 'marketlense-core')],
                'briefings' => [__('briefing', 'marketlense-core'), __('briefings', 'marketlense-core')],
                'signals' => [__('signal', 'marketlense-core'), __('signals', 'marketlense-core')],
            ] as $key => [$singular, $plural]
        ) {
            $count = max(0, (int) ($item[$key] ?? 0));
            if ($count === 0) {
                continue;
            }
            $parts[] = sprintf(_n('%1$d %2$s', '%1$d %3$s', $count, 'marketlense-core'), $count, $singular, $plural);
        }

        return implode(' / ', $parts);
    }

    private function to_bool_flag(mixed $value): bool
    {
        return in_array((string) $value, ['1', 'true', 'yes', 'on'], true);
    }

    /**
     * @return array<int,string>
     */
    private function publisher_external_urls(string $value): array
    {
        $trimmed = trim($value);
        if ($trimmed === '') {
            return [];
        }

        preg_match_all(
            '/(?i)\b(?:https?:\/\/|www\.)[^\s,]+|(?<!@)\b[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:\/[^\s,]+)?/',
            $trimmed,
            $matches
        );
        $candidates = is_array($matches[0] ?? null) ? $matches[0] : [];
        $urls = [];
        foreach ($candidates as $candidate) {
            $normalized = $this->normalize_external_url(rtrim((string) $candidate, '.,;)'));
            if ($normalized !== '' && ! in_array($normalized, $urls, true)) {
                $urls[] = $normalized;
            }
            if (count($urls) >= 3) {
                break;
            }
        }

        return $urls;
    }

    private function publisher_description_excerpt(string $description): string
    {
        $trimmed = trim(wp_strip_all_tags($description));
        if ($trimmed === '') {
            return '';
        }

        return wp_trim_words($trimmed, 28, '...');
    }

    private function publisher_icon_markup(string $icon_source, string $publisher_name): string
    {
        $trimmed = trim($icon_source);
        if ($trimmed === '') {
            return '';
        }

        $alt_text = sprintf(__('%s logo', 'marketlense-core'), $publisher_name);
        $fallback = sprintf(
            '<span class="ml-publisher-profile-monogram" aria-hidden="true">%s</span>',
            esc_html($this->publisher_monogram($publisher_name))
        );

        if (preg_match('/^data:image\/[a-z0-9.+-]+;base64,[a-z0-9+\/=]+$/i', $trimmed) === 1) {
            return $this->publisher_image_markup(esc_attr($trimmed), $alt_text, $fallback);
        }

        $url = $this->normalize_external_url($trimmed);
        if ($url !== '') {
            return $this->publisher_image_markup(esc_url($url), $alt_text, $fallback);
        }

        return sprintf(
            '<span class="ml-publisher-profile-emoji" aria-hidden="true">%s</span>',
            esc_html($trimmed)
        );
    }

    private function publisher_image_markup(string $source, string $alt_text, string $fallback): string
    {
        return sprintf(
            '<span class="ml-publisher-profile-icon-media"><img src="%1$s" alt="%2$s" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.parentNode.classList.add(\'is-fallback\');this.remove();" />%3$s</span>',
            $source,
            esc_attr($alt_text),
            $fallback
        );
    }

    private function publisher_monogram(string $publisher_name): string
    {
        $parts = preg_split('/\s+/', trim(wp_strip_all_tags($publisher_name))) ?: [];
        $initials = '';

        foreach ($parts as $part) {
            if ($part === '') {
                continue;
            }

            $initials .= strtoupper(substr($part, 0, 1));
            if (strlen($initials) >= 2) {
                break;
            }
        }

        if ($initials !== '') {
            return $initials;
        }

        return strtoupper(substr(trim($publisher_name), 0, 2));
    }

    /**
     * @param array<int,string> $parts
     */
    private function joined_text(array $parts): string
    {
        $values = array_values(
            array_filter(
                array_map(
                    static fn ($value): string => trim((string) $value),
                    $parts
                ),
                static fn (string $value): bool => $value !== ''
            )
        );

        return implode(' / ', $values);
    }

    /**
     * @param array<int,array{label:string,target:string}> $items
     */
    private function render_navigation(array $items, string $class_name, string $aria_label): string
    {
        $links = [];
        foreach ($items as $item) {
            $url = $this->resolve_internal_url($item['target']);
            if ($url === '') {
                continue;
            }

            $is_current = $this->is_current_url($url);
            $item_class = $is_current
                ? 'wp-block-navigation-item current-menu-item'
                : 'wp-block-navigation-item';
            $aria_current = $is_current ? ' aria-current="page"' : '';
            $links[] = sprintf(
                '<li class="%1$s"><a class="wp-block-navigation-item__content" href="%2$s"%3$s>%4$s</a></li>',
                esc_attr($item_class),
                esc_url($url),
                $aria_current,
                esc_html($item['label'])
            );
        }

        if ($links === []) {
            return '';
        }

        return sprintf(
            '<nav class="wp-block-navigation %1$s" aria-label="%2$s"><ul class="wp-block-navigation__container">%3$s</ul></nav>',
            esc_attr($class_name),
            esc_attr($aria_label),
            implode('', $links)
        );
    }

    private function resolve_internal_url(string $target): string
    {
        $normalized = sanitize_key($target);

        return match ($normalized) {
            'home' => home_url('/'),
            'reports' => $this->post_type_archive_url(Post_Type::POST_TYPE, '/reports/'),
            'topics-directory' => home_url('/topics-directory/'),
            'signals' => $this->post_type_archive_url(Post_Type::SIGNAL_POST_TYPE, '/signals/'),
            'briefings' => $this->post_type_archive_url(Post_Type::BRIEFING_POST_TYPE, '/briefings/'),
            'publishers-directory' => home_url('/publishers-directory/'),
            'methodology' => home_url('/methodology/'),
            'about' => home_url('/about/'),
            'submit-a-report' => home_url('/submit-a-report/'),
            'contact' => home_url('/contact/'),
            'privacy' => home_url('/privacy/'),
            'terms' => home_url('/terms/'),
            default => '',
        };
    }

    /**
     * @param array<int,array{label:string,target:string}> $items
     */
    private function render_mobile_navigation(array $items): string
    {
        $navigation = $this->render_navigation(
            $items,
            'ml-mobile-nav-links',
            __('Mobile navigation', 'marketlense-core')
        );
        if ($navigation === '') {
            return '';
        }

        return sprintf(
            '<details class="ml-mobile-nav"><summary>%1$s</summary>%2$s</details>',
            esc_html__('Menu', 'marketlense-core'),
            $navigation
        );
    }

    private function post_type_archive_url(string $post_type, string $fallback_path): string
    {
        $archive_url = get_post_type_archive_link($post_type);

        return is_string($archive_url) && $archive_url !== '' ? $archive_url : home_url($fallback_path);
    }

    private function normalize_external_url(string $value): string
    {
        $trimmed = trim($value);
        if ($trimmed === '') {
            return '';
        }

        if (preg_match('/^[a-z][a-z0-9+\-.]*:\/\//i', $trimmed) !== 1) {
            $trimmed = 'https://' . $trimmed;
        }

        $validated = esc_url_raw($trimmed, ['https', 'http']);
        if ($validated === '' || ! wp_http_validate_url($validated)) {
            return '';
        }

        if (stripos($validated, 'http://') === 0) {
            $https_candidate = 'https://' . substr($validated, 7);
            if (wp_http_validate_url($https_candidate)) {
                $validated = $https_candidate;
            }
        }

        return (string) esc_url_raw($validated, ['https', 'http']);
    }

    private function is_current_url(string $url): bool
    {
        global $wp;

        if (! isset($wp) || ! isset($wp->request) || ! is_string($wp->request)) {
            return false;
        }

        $current_url = home_url('/' . ltrim($wp->request, '/') . '/');

        return untrailingslashit($current_url) === untrailingslashit($url);
    }
}
