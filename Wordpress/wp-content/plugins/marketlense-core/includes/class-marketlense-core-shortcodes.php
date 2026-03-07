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
        'ml_featured_digest' => 'render_featured_digest',
        'ml_intelligence_signals' => 'render_intelligence_signals',
        'ml_strategic_themes' => 'render_strategic_themes',
        'ml_publisher_authority' => 'render_publisher_authority',
        'ml_button_link' => 'render_button_link',
        'ml_inline_link' => 'render_inline_link',
        'ml_primary_nav' => 'render_primary_nav',
        'ml_footer_nav' => 'render_footer_nav',
    ];

    private Report_View_Model_Builder $view_model_builder;

    private Intelligence_Stats $stats;

    public function __construct(
        Report_View_Model_Builder $view_model_builder,
        Intelligence_Stats $stats
    ) {
        $this->view_model_builder = $view_model_builder;
        $this->stats = $stats;
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
        $search_term = $context === 'auto' ? trim((string) get_search_query()) : '';
        $archive_url = get_post_type_archive_link(Post_Type::POST_TYPE);
        if (! is_string($archive_url) || $archive_url === '') {
            $archive_url = home_url('/reports/');
        }

        $selected_topic = $this->selected_topic_slug();
        $selected_publisher = $this->selected_filter_slug('ml_publisher', Taxonomies::PUBLISHER_TAXONOMY);
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
        if ($selected_sort !== 'latest') {
            $active_filters['ml_sort'] = $selected_sort;
        }

        $query_args = [
            'post_type' => Post_Type::POST_TYPE,
            'post_status' => 'publish',
            'posts_per_page' => $per_page,
            'paged' => $current_page,
        ];
        $query_args = $this->apply_sort_to_query_args($query_args, $selected_sort);

        if ($search_term !== '') {
            $query_args['s'] = $search_term;
        }

        if ($active_filters !== []) {
            $tax_query = ['relation' => 'AND'];
            if ($selected_topic !== '') {
                $tax_query[] = [
                    'taxonomy' => Taxonomies::CATEGORY_TAXONOMY,
                    'field' => 'slug',
                    'terms' => [$selected_topic],
                ];
            }
            if ($selected_publisher !== '') {
                $tax_query[] = [
                    'taxonomy' => Taxonomies::PUBLISHER_TAXONOMY,
                    'field' => 'slug',
                    'terms' => [$selected_publisher],
                ];
            }
            $query_args['tax_query'] = $tax_query;
        }

        $query = new \WP_Query($query_args);
        $topic_options = $this->stats->scoped_terms(Taxonomies::CATEGORY_TAXONOMY);
        $publisher_options = $this->stats->scoped_terms(Taxonomies::PUBLISHER_TAXONOMY);
        $form_action = $search_term !== '' ? home_url('/') : $archive_url;

        ob_start();
        ?>
        <section class="ml-report-browser" aria-label="<?php esc_attr_e('Report browser', 'marketlense-core'); ?>">
            <div class="ml-report-browser-layout">
                <?php if ($show_filters) : ?>
                    <aside class="ml-report-browser-sidebar">
                        <div class="ml-report-browser-sidebar-card">
                            <p class="ml-section-kicker"><?php esc_html_e('Refine the view', 'marketlense-core'); ?></p>
                            <h2 class="ml-report-browser-title"><?php esc_html_e('Filter the archive', 'marketlense-core'); ?></h2>
                            <p class="ml-report-browser-copy"><?php esc_html_e('Compare digests by topic, publisher, and sort order without leaving the archive.', 'marketlense-core'); ?></p>

                            <form class="ml-report-filter-form" method="get" action="<?php echo esc_url($form_action); ?>">
                                <?php if ($search_term !== '') : ?>
                                    <input type="hidden" name="s" value="<?php echo esc_attr($search_term); ?>">
                                <?php endif; ?>

                                <div class="ml-report-filter-grid">
                                    <label class="ml-report-filter-field" for="ml_topic_filter">
                                        <span><?php esc_html_e('Topic', 'marketlense-core'); ?></span>
                                        <select id="ml_topic_filter" name="<?php echo esc_attr(self::TOPIC_QUERY_KEY); ?>">
                                            <option value=""><?php esc_html_e('All topics', 'marketlense-core'); ?></option>
                                            <?php foreach ($topic_options as $term) : ?>
                                                <option value="<?php echo esc_attr($term->slug); ?>" <?php selected($selected_topic, $term->slug); ?>>
                                                    <?php echo esc_html($term->name); ?>
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
                                                    <?php echo esc_html($term->name); ?>
                                                </option>
                                            <?php endforeach; ?>
                                        </select>
                                    </label>

                                    <label class="ml-report-filter-field" for="ml_sort_filter">
                                        <span><?php esc_html_e('Sort', 'marketlense-core'); ?></span>
                                        <select id="ml_sort_filter" name="ml_sort">
                                            <option value="latest" <?php selected($selected_sort, 'latest'); ?>><?php esc_html_e('Newest first', 'marketlense-core'); ?></option>
                                            <option value="oldest" <?php selected($selected_sort, 'oldest'); ?>><?php esc_html_e('Oldest first', 'marketlense-core'); ?></option>
                                            <option value="title" <?php selected($selected_sort, 'title'); ?>><?php esc_html_e('Title A-Z', 'marketlense-core'); ?></option>
                                        </select>
                                    </label>
                                </div>

                                <div class="ml-report-filter-actions">
                                    <button type="submit" class="ml-button ml-button-primary">
                                        <?php esc_html_e('Apply filters', 'marketlense-core'); ?>
                                    </button>
                                    <a class="ml-button ml-button-outline" href="<?php echo esc_url($archive_url); ?>">
                                        <?php esc_html_e('Reset', 'marketlense-core'); ?>
                                    </a>
                                </div>
                            </form>

                            <?php if ($active_filters !== []) : ?>
                                <div class="ml-active-filters" aria-label="<?php esc_attr_e('Active filters', 'marketlense-core'); ?>">
                                    <?php if ($selected_topic_term instanceof \WP_Term) : ?>
                                        <?php
                                        $topic_reset = add_query_arg(
                                            [
                                                's' => $search_term !== '' ? $search_term : null,
                                                'ml_publisher' => $selected_publisher !== '' ? $selected_publisher : null,
                                                'ml_sort' => $selected_sort !== 'latest' ? $selected_sort : null,
                                            ],
                                            $archive_url
                                        );
                                        ?>
                                        <a class="ml-filter-chip" href="<?php echo esc_url((string) $topic_reset); ?>">
                                            <?php echo esc_html(sprintf(__('Topic: %s', 'marketlense-core'), $selected_topic_term->name)); ?>
                                        </a>
                                    <?php endif; ?>

                                    <?php if ($selected_publisher_term instanceof \WP_Term) : ?>
                                        <?php
                                        $publisher_reset = add_query_arg(
                                            [
                                                's' => $search_term !== '' ? $search_term : null,
                                                self::TOPIC_QUERY_KEY => $selected_topic !== '' ? $selected_topic : null,
                                                'ml_sort' => $selected_sort !== 'latest' ? $selected_sort : null,
                                            ],
                                            $archive_url
                                        );
                                        ?>
                                        <a class="ml-filter-chip" href="<?php echo esc_url((string) $publisher_reset); ?>">
                                            <?php echo esc_html(sprintf(__('Publisher: %s', 'marketlense-core'), $selected_publisher_term->name)); ?>
                                        </a>
                                    <?php endif; ?>

                                    <?php if ($selected_sort !== 'latest') : ?>
                                        <?php
                                        $sort_reset = add_query_arg(
                                            [
                                                's' => $search_term !== '' ? $search_term : null,
                                                self::TOPIC_QUERY_KEY => $selected_topic !== '' ? $selected_topic : null,
                                                'ml_publisher' => $selected_publisher !== '' ? $selected_publisher : null,
                                            ],
                                            $archive_url
                                        );
                                        ?>
                                        <a class="ml-filter-chip" href="<?php echo esc_url((string) $sort_reset); ?>">
                                            <?php echo esc_html(sprintf(__('Sort: %s', 'marketlense-core'), $this->sort_label($selected_sort))); ?>
                                        </a>
                                    <?php endif; ?>
                                </div>
                            <?php endif; ?>
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
                                            _n('%d digest', '%d digests', (int) $query->found_posts, 'marketlense-core'),
                                            (int) $query->found_posts
                                        )
                                    );
                                    ?>
                                </span>
                                <span class="ml-report-browser-summary-copy"><?php esc_html_e('currently in view', 'marketlense-core'); ?></span>
                            </p>
                            <?php if ($search_term !== '') : ?>
                                <p class="ml-report-browser-context">
                                    <?php echo esc_html(sprintf(__('Search query: "%s"', 'marketlense-core'), $search_term)); ?>
                                </p>
                            <?php elseif ($selected_topic_term instanceof \WP_Term || $selected_publisher_term instanceof \WP_Term) : ?>
                                <p class="ml-report-browser-context"><?php echo esc_html($this->browser_context_copy($selected_topic_term, $selected_publisher_term)); ?></p>
                            <?php endif; ?>
                        </div>
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
                                $this->render_report_card($post, $this->view_model_builder->build($post));
                                ?>
                            <?php endwhile; ?>
                        </div>

                        <?php if ($show_pagination) : ?>
                            <?php
                            $pagination_args = $active_filters;
                            if ($search_term !== '') {
                                $pagination_args['s'] = $search_term;
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
            ],
            $attrs,
            'ml_latest_reports'
        );
        $limit = max(1, min(12, (int) $atts['limit']));

        $query = new \WP_Query(
            [
                'post_type' => Post_Type::POST_TYPE,
                'post_status' => 'publish',
                'posts_per_page' => $limit,
                'orderby' => 'date',
                'order' => 'DESC',
                'no_found_rows' => true,
            ]
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
                    $this->render_report_card($post, $this->view_model_builder->build($post));
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
                    <span class="ml-metric-label"><?php esc_html_e('Digests', 'marketlense-core'); ?></span>
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
                    <span class="ml-metric-value"><?php echo esc_html((string) $metrics['latest_label']); ?></span>
                    <span class="ml-metric-label"><?php esc_html_e('Freshness', 'marketlense-core'); ?></span>
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
        $metrics = $this->stats->homepage_metrics();
        $latest_post = $this->stats->latest_report();
        $latest = $latest_post instanceof \WP_Post
            ? $this->view_model_builder->build($latest_post)
            : null;
        $signal = $this->signal_of_the_day();

        ob_start();
        ?>
        <section class="ml-hero-snapshot" aria-label="<?php esc_attr_e('Current portal snapshot', 'marketlense-core'); ?>">
            <div class="ml-hero-snapshot-card">
                <p class="ml-proof-label"><?php esc_html_e('Portal snapshot', 'marketlense-core'); ?></p>
                <div class="ml-hero-snapshot-grid">
                    <div class="ml-hero-proof-item">
                        <span class="ml-hero-proof-value"><?php echo esc_html((string) $metrics['report_count']); ?></span>
                        <span class="ml-hero-proof-label"><?php esc_html_e('Digests', 'marketlense-core'); ?></span>
                    </div>
                    <div class="ml-hero-proof-item">
                        <span class="ml-hero-proof-value"><?php echo esc_html((string) $metrics['publisher_count']); ?></span>
                        <span class="ml-hero-proof-label"><?php esc_html_e('Publishers', 'marketlense-core'); ?></span>
                    </div>
                    <div class="ml-hero-proof-item">
                        <span class="ml-hero-proof-value"><?php echo esc_html((string) $metrics['topic_count']); ?></span>
                        <span class="ml-hero-proof-label"><?php esc_html_e('Topics', 'marketlense-core'); ?></span>
                    </div>
                    <div class="ml-hero-proof-item">
                        <span class="ml-hero-proof-value"><?php esc_html_e('Live', 'marketlense-core'); ?></span>
                        <span class="ml-hero-proof-label"><?php echo esc_html((string) $metrics['latest_label']); ?></span>
                    </div>
                </div>
            </div>

            <?php if (is_array($latest)) : ?>
                <div class="ml-hero-snapshot-card is-lead">
                    <p class="ml-proof-label"><?php esc_html_e('Latest brief', 'marketlense-core'); ?></p>
                    <p class="ml-hero-snapshot-meta">
                        <?php echo esc_html($this->joined_text([(string) $latest['publisher'], (string) $latest['date']])); ?>
                    </p>
                    <h3 class="ml-hero-snapshot-title">
                        <a href="<?php echo esc_url((string) $latest['permalink']); ?>">
                            <?php echo esc_html((string) $latest['title']); ?>
                        </a>
                    </h3>
                    <?php if ((string) $latest['why_it_matters'] !== '') : ?>
                        <p class="ml-hero-snapshot-copy"><?php echo esc_html((string) $latest['why_it_matters']); ?></p>
                    <?php endif; ?>
                </div>
            <?php endif; ?>

            <?php if (is_array($signal)) : ?>
                <div class="ml-hero-snapshot-card">
                    <p class="ml-proof-label"><?php esc_html_e('Signal of the moment', 'marketlense-core'); ?></p>
                    <p class="ml-hero-snapshot-signal"><?php echo esc_html((string) $signal['insight']); ?></p>
                    <p class="ml-hero-snapshot-source">
                        <a href="<?php echo esc_url((string) $signal['permalink']); ?>">
                            <?php echo esc_html((string) $signal['title']); ?>
                        </a>
                        <?php if ((string) $signal['publisher'] !== '') : ?>
                            <span><?php echo esc_html(' / ' . (string) $signal['publisher']); ?></span>
                        <?php endif; ?>
                    </p>
                </div>
            <?php endif; ?>
        </section>
        <?php

        return (string) ob_get_clean();
    }

    /**
     * @return array{insight:string,title:string,permalink:string,publisher:string}|null
     */
    private function signal_of_the_day(): ?array
    {
        $report_ids = get_posts(
            [
                'post_type' => Post_Type::POST_TYPE,
                'post_status' => 'publish',
                'fields' => 'ids',
                'posts_per_page' => -1,
                'no_found_rows' => true,
                'update_post_meta_cache' => false,
                'update_post_term_cache' => false,
                'orderby' => 'date',
                'order' => 'DESC',
            ]
        );

        if (! is_array($report_ids) || $report_ids === []) {
            return null;
        }

        $candidate_ids = array_values(
            array_filter(
                array_map('intval', $report_ids),
                static fn (int $post_id): bool => $post_id > 0
            )
        );

        if ($candidate_ids === []) {
            return null;
        }

        shuffle($candidate_ids);

        foreach ($candidate_ids as $post_id) {
            $post = get_post($post_id);
            if (! ($post instanceof \WP_Post) || $post->post_type !== Post_Type::POST_TYPE || $post->post_status !== 'publish') {
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

            return [
                'insight' => $metrics[$metric_index],
                'title' => (string) ($report['title'] ?? ''),
                'permalink' => (string) ($report['permalink'] ?? ''),
                'publisher' => (string) ($report['publisher'] ?? ''),
            ];
        }

        return null;
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
        $thumbnail = get_the_post_thumbnail(
            $post,
            'large',
            [
                'loading' => 'eager',
                'fetchpriority' => 'high',
                'sizes' => '(max-width: 720px) 100vw, 42rem',
            ]
        );

        ob_start();
        ?>
        <section class="ml-featured-digest" aria-label="<?php esc_attr_e('Featured digest', 'marketlense-core'); ?>">
            <div class="ml-section-heading">
                <p class="ml-section-kicker"><?php esc_html_e('Editorial lead', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2><?php esc_html_e('Featured Digest', 'marketlense-core'); ?></h2>
                    <a class="ml-inline-link" href="<?php echo esc_url(get_post_type_archive_link(Post_Type::POST_TYPE) ?: home_url('/reports/')); ?>">
                        <?php esc_html_e('Browse all reports', 'marketlense-core'); ?>
                        <span aria-hidden="true">&rarr;</span>
                    </a>
                </div>
            </div>

            <article class="ml-featured-digest-card">
                <a class="ml-featured-media" href="<?php echo esc_url((string) $report['permalink']); ?>">
                    <?php if (is_string($thumbnail) && $thumbnail !== '') : ?>
                        <?php echo $thumbnail; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                    <?php else : ?>
                        <span class="ml-featured-media-fallback">
                            <span class="ml-image-fallback-label"><?php esc_html_e('Latest digest', 'marketlense-core'); ?></span>
                            <strong><?php echo esc_html((string) $report['title']); ?></strong>
                            <span><?php echo esc_html((string) $report['publisher']); ?></span>
                        </span>
                    <?php endif; ?>
                </a>

                <div class="ml-featured-copy">
                    <p class="ml-featured-meta">
                        <?php echo esc_html($this->joined_text([(string) $report['publisher'], (string) $report['time_period'], (string) $report['date']])); ?>
                    </p>
                    <h3>
                        <a href="<?php echo esc_url((string) $report['permalink']); ?>">
                            <?php echo esc_html((string) $report['title']); ?>
                        </a>
                    </h3>

                    <?php if ((string) $report['excerpt'] !== '') : ?>
                        <p class="ml-featured-excerpt"><?php echo esc_html((string) $report['excerpt']); ?></p>
                    <?php endif; ?>

                    <?php if (is_array($report['key_metrics']) && $report['key_metrics'] !== []) : ?>
                        <ul class="ml-featured-metrics">
                            <?php foreach ($report['key_metrics'] as $metric) : ?>
                                <li><?php echo esc_html((string) $metric); ?></li>
                            <?php endforeach; ?>
                        </ul>
                    <?php endif; ?>

                    <?php if ((string) $report['why_it_matters'] !== '') : ?>
                        <p class="ml-featured-why">
                            <strong><?php esc_html_e('Why it matters:', 'marketlense-core'); ?></strong>
                            <?php echo esc_html((string) $report['why_it_matters']); ?>
                        </p>
                    <?php endif; ?>

                    <p class="ml-report-card-link">
                        <a href="<?php echo esc_url((string) $report['permalink']); ?>">
                            <?php esc_html_e('Read digest', 'marketlense-core'); ?>
                            <span aria-hidden="true">&rarr;</span>
                        </a>
                    </p>
                </div>
            </article>
        </section>
        <?php
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
        if (
            $signals['trending_topics'] === []
            && $signals['emerging_themes'] === []
            && (! $show_publishers || $signals['top_publishers'] === [])
        ) {
            return '';
        }

        ob_start();
        ?>
        <section class="ml-intelligence-signals" aria-label="<?php esc_attr_e('This week in intelligence', 'marketlense-core'); ?>">
            <div class="ml-section-heading">
                <p class="ml-section-kicker"><?php esc_html_e('Signals', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2><?php esc_html_e('This Week in Intelligence', 'marketlense-core'); ?></h2>
                    <p class="ml-section-note"><?php echo esc_html((string) $signals['window_label']); ?></p>
                </div>
            </div>

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
            <div class="ml-section-heading">
                <p class="ml-section-kicker"><?php esc_html_e('Discovery', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2><?php esc_html_e('Strategic Themes', 'marketlense-core'); ?></h2>
                    <a class="ml-inline-link" href="<?php echo esc_url(home_url('/topics-directory/')); ?>">
                        <?php esc_html_e('Open topics directory', 'marketlense-core'); ?>
                        <span aria-hidden="true">&rarr;</span>
                    </a>
                </div>
            </div>

            <div class="ml-theme-list">
                <?php foreach ($themes as $theme) : ?>
                    <article class="ml-theme-item">
                        <div>
                            <h3>
                                <?php if ((string) $theme['url'] !== '') : ?>
                                    <a href="<?php echo esc_url((string) $theme['url']); ?>">
                                        <?php echo esc_html((string) $theme['name']); ?>
                                    </a>
                                <?php else : ?>
                                    <?php echo esc_html((string) $theme['name']); ?>
                                <?php endif; ?>
                            </h3>
                            <p><?php echo esc_html(sprintf(_n('%d digest', '%d digests', (int) $theme['count'], 'marketlense-core'), (int) $theme['count'])); ?></p>
                        </div>
                        <?php $this->render_delta_badge($theme['delta'] ?? null); ?>
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
            <div class="ml-section-heading">
                <p class="ml-section-kicker"><?php esc_html_e('Authority', 'marketlense-core'); ?></p>
                <div class="ml-section-heading-row">
                    <h2><?php esc_html_e('Publisher Authority', 'marketlense-core'); ?></h2>
                    <a class="ml-inline-link" href="<?php echo esc_url(home_url('/publishers-directory/')); ?>">
                        <?php esc_html_e('Open publishers directory', 'marketlense-core'); ?>
                        <span aria-hidden="true">&rarr;</span>
                    </a>
                </div>
                <p class="ml-section-note">
                    <?php esc_html_e('Track recurring institutions, consultancies, and specialist publishers shaping the intelligence agenda.', 'marketlense-core'); ?>
                </p>
            </div>

            <div class="ml-authority-wall">
                <?php foreach ($publishers as $publisher) : ?>
                    <article class="ml-authority-item">
                        <div class="ml-authority-name-row">
                            <?php if ((string) $publisher['url'] !== '') : ?>
                                <a href="<?php echo esc_url((string) $publisher['url']); ?>" class="ml-authority-name">
                                    <?php echo esc_html((string) $publisher['name']); ?>
                                </a>
                            <?php else : ?>
                                <span class="ml-authority-name"><?php echo esc_html((string) $publisher['name']); ?></span>
                            <?php endif; ?>
                            <span class="ml-authority-count">
                                <?php echo esc_html(sprintf(_n('%d digest', '%d digests', (int) $publisher['count'], 'marketlense-core'), (int) $publisher['count'])); ?>
                            </span>
                        </div>
                        <?php if ((string) $publisher['homepage'] !== '') : ?>
                            <a class="ml-authority-homepage" href="<?php echo esc_url((string) $publisher['homepage']); ?>" target="_blank" rel="noopener noreferrer">
                                <?php esc_html_e('Homepage', 'marketlense-core'); ?>
                                <span aria-hidden="true">&nearr;</span>
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
        $terms = $this->stats->scoped_terms(Taxonomies::CATEGORY_TAXONOMY, 300, false);
        if ($terms === []) {
            return '<p>' . esc_html__('No topics are available yet.', 'marketlense-core') . '</p>';
        }

        ob_start();
        ?>
        <section class="ml-directory-list ml-topic-directory-list">
            <?php foreach ($terms as $term) : ?>
                <?php $link = get_term_link($term); ?>
                <article class="ml-directory-card">
                    <h3>
                        <?php if (! is_wp_error($link)) : ?>
                            <a href="<?php echo esc_url((string) $link); ?>"><?php echo esc_html($term->name); ?></a>
                        <?php else : ?>
                            <?php echo esc_html($term->name); ?>
                        <?php endif; ?>
                    </h3>
                    <p class="ml-directory-count">
                        <?php echo esc_html(sprintf(_n('%d report', '%d reports', (int) $term->count, 'marketlense-core'), (int) $term->count)); ?>
                    </p>
                    <?php if ($term->description !== '') : ?>
                        <p><?php echo esc_html($term->description); ?></p>
                    <?php endif; ?>
                    <?php if (! is_wp_error($link)) : ?>
                        <div class="ml-directory-actions">
                            <a class="ml-button ml-button-outline" href="<?php echo esc_url((string) $link); ?>">
                                <?php esc_html_e('Explore topic archive', 'marketlense-core'); ?>
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
        $terms = $this->stats->all_terms(Taxonomies::PUBLISHER_TAXONOMY, 300);
        if ($terms === []) {
            return '<p>' . esc_html__('No publishers are available yet.', 'marketlense-core') . '</p>';
        }

        ob_start();
        ?>
        <section class="ml-directory-list ml-publisher-directory-list">
            <?php foreach ($terms as $term) : ?>
                <?php
                $archive_link = get_term_link($term);
                $homepage = (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_HOMEPAGE_META, true);
                $insights_links = $this->publisher_external_urls(
                    (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_INSIGHTS_META, true)
                );
                $description = $this->publisher_description_excerpt($term->description);
                ?>
                <article class="ml-directory-card">
                    <h3>
                        <?php if (! is_wp_error($archive_link)) : ?>
                            <a href="<?php echo esc_url((string) $archive_link); ?>">
                                <?php echo esc_html($term->name); ?>
                            </a>
                        <?php else : ?>
                            <?php echo esc_html($term->name); ?>
                        <?php endif; ?>
                    </h3>
                    <p class="ml-directory-count">
                        <?php echo esc_html(sprintf(_n('%d report', '%d reports', (int) $term->count, 'marketlense-core'), (int) $term->count)); ?>
                    </p>
                    <?php if ($description !== '') : ?>
                        <p class="ml-directory-description"><?php echo esc_html($description); ?></p>
                    <?php endif; ?>
                    <div class="ml-directory-actions">
                        <?php if (! is_wp_error($archive_link)) : ?>
                            <a class="ml-button ml-button-outline" href="<?php echo esc_url((string) $archive_link); ?>">
                                <?php esc_html_e('View publisher archive', 'marketlense-core'); ?>
                            </a>
                        <?php endif; ?>
                        <?php if ($homepage !== '') : ?>
                            <a class="ml-button ml-button-primary" href="<?php echo esc_url($homepage); ?>" target="_blank" rel="noopener noreferrer">
                                <?php esc_html_e('Publisher homepage', 'marketlense-core'); ?>
                            </a>
                        <?php endif; ?>
                        <?php if ($insights_links !== []) : ?>
                            <a class="ml-button ml-button-outline" href="<?php echo esc_url($insights_links[0]); ?>" target="_blank" rel="noopener noreferrer">
                                <?php esc_html_e('Insights', 'marketlense-core'); ?>
                            </a>
                        <?php endif; ?>
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
            <a class="wp-block-button__link wp-element-button" href="<?php echo esc_url($url); ?>">
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
                    <span aria-hidden="true">&rarr;</span>
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
        return $this->render_navigation(
            [
                ['label' => __('Reports', 'marketlense-core'), 'target' => 'reports'],
                ['label' => __('Topics', 'marketlense-core'), 'target' => 'topics-directory'],
                ['label' => __('Publishers', 'marketlense-core'), 'target' => 'publishers-directory'],
                ['label' => __('Methodology', 'marketlense-core'), 'target' => 'methodology'],
                ['label' => __('About', 'marketlense-core'), 'target' => 'about'],
            ],
            'ml-primary-nav',
            __('Primary navigation', 'marketlense-core')
        );
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
                ['label' => __('About', 'marketlense-core'), 'target' => 'about'],
            ];
            $label = __('Footer navigation', 'marketlense-core');
        }

        return $this->render_navigation($items, 'ml-footer-nav', $label);
    }

    /**
     * @param array<string,mixed> $report
     */
    private function render_report_card(\WP_Post $post, array $report): void
    {
        $thumbnail = get_the_post_thumbnail(
            $post,
            'large',
            [
                'loading' => 'lazy',
                'sizes' => '(max-width: 782px) 100vw, (max-width: 1200px) 48vw, 32vw',
            ]
        );
        ?>
        <article class="ml-report-card">
            <a class="ml-report-card-image" href="<?php echo esc_url((string) $report['permalink']); ?>">
                <?php if (is_string($thumbnail) && $thumbnail !== '') : ?>
                    <?php echo $thumbnail; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                <?php else : ?>
                    <span class="ml-report-card-image-fallback">
                        <span class="ml-image-fallback-label"><?php esc_html_e('Digest cover', 'marketlense-core'); ?></span>
                        <strong><?php echo esc_html((string) $report['title']); ?></strong>
                        <span><?php echo esc_html((string) $report['publisher']); ?></span>
                    </span>
                <?php endif; ?>
            </a>

            <p class="ml-report-card-kicker">
                <?php echo esc_html($this->joined_text([(string) $report['date'], (string) $report['time_period']])); ?>
            </p>

            <h3 class="ml-report-card-title">
                <a href="<?php echo esc_url((string) $report['permalink']); ?>">
                    <?php echo esc_html((string) $report['title']); ?>
                </a>
            </h3>

            <p class="ml-report-card-subtitle">
                <?php echo esc_html($this->joined_text([(string) $report['publisher'], (string) $report['geography']])); ?>
            </p>

            <ul class="ml-report-card-meta" aria-label="<?php esc_attr_e('Report highlights', 'marketlense-core'); ?>">
                <?php if ((int) $report['insights_count'] > 0) : ?>
                    <li><?php echo esc_html(sprintf(_n('%d insight', '%d insights', (int) $report['insights_count'], 'marketlense-core'), (int) $report['insights_count'])); ?></li>
                <?php endif; ?>
                <?php if ((int) $report['quotes_count'] > 0) : ?>
                    <li><?php echo esc_html(sprintf(_n('%d quote', '%d quotes', (int) $report['quotes_count'], 'marketlense-core'), (int) $report['quotes_count'])); ?></li>
                <?php endif; ?>
                <?php if ((int) $report['topics_count'] > 0) : ?>
                    <li><?php echo esc_html(sprintf(_n('%d topic', '%d topics', (int) $report['topics_count'], 'marketlense-core'), (int) $report['topics_count'])); ?></li>
                <?php endif; ?>
            </ul>

            <?php if ((string) $report['excerpt'] !== '') : ?>
                <p class="ml-report-card-excerpt"><?php echo esc_html((string) $report['excerpt']); ?></p>
            <?php endif; ?>

            <p class="ml-report-card-link">
                <a href="<?php echo esc_url((string) $report['permalink']); ?>">
                    <?php esc_html_e('Read digest', 'marketlense-core'); ?>
                    <span aria-hidden="true">&rarr;</span>
                </a>
            </p>
        </article>
        <?php
    }

    /**
     * @param array<int,array<string,mixed>> $items
     */
    private function render_signal_column(string $title, array $items, string $class_name = 'ml-signal-column'): void
    {
        ?>
        <section class="<?php echo esc_attr($class_name); ?>">
            <h3><?php echo esc_html($title); ?></h3>
            <?php if ($items === []) : ?>
                <p class="ml-signal-empty"><?php esc_html_e('No recent movement yet.', 'marketlense-core'); ?></p>
            <?php else : ?>
                <ul class="ml-signal-list">
                    <?php foreach ($items as $item) : ?>
                        <li class="ml-signal-item">
                            <div class="ml-signal-item-main">
                                <?php if ((string) $item['url'] !== '') : ?>
                                    <a href="<?php echo esc_url((string) $item['url']); ?>">
                                        <?php echo esc_html((string) $item['name']); ?>
                                    </a>
                                <?php else : ?>
                                    <span><?php echo esc_html((string) $item['name']); ?></span>
                                <?php endif; ?>
                                <span class="ml-signal-count"><?php echo esc_html((string) $item['count']); ?></span>
                            </div>
                            <?php $this->render_delta_badge($item['delta'] ?? null); ?>
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
        $symbol = $delta > 0 ? '+' : '-';
        ?>
        <span class="ml-delta-badge <?php echo esc_attr($class_name); ?>">
            <span aria-hidden="true"><?php echo esc_html($symbol); ?></span>
            <?php echo esc_html((string) abs($delta)); ?>
        </span>
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

    private function selected_sort(): string
    {
        if (! isset($_GET['ml_sort'])) {
            return 'latest';
        }

        $sort = sanitize_key((string) wp_unslash($_GET['ml_sort']));

        return in_array($sort, ['latest', 'oldest', 'title'], true) ? $sort : 'latest';
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

    private function browser_context_copy(?\WP_Term $selected_topic, ?\WP_Term $selected_publisher): string
    {
        if ($selected_topic instanceof \WP_Term && $selected_publisher instanceof \WP_Term) {
            return sprintf(
                __('Focused on %1$s from %2$s.', 'marketlense-core'),
                $selected_topic->name,
                $selected_publisher->name
            );
        }

        if ($selected_topic instanceof \WP_Term) {
            return sprintf(__('Focused on the %s topic.', 'marketlense-core'), $selected_topic->name);
        }

        if ($selected_publisher instanceof \WP_Term) {
            return sprintf(__('Focused on %s coverage.', 'marketlense-core'), $selected_publisher->name);
        }

        return '';
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
            'reports' => (string) (get_post_type_archive_link(Post_Type::POST_TYPE) ?: home_url('/reports/')),
            'topics-directory' => home_url('/topics-directory/'),
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
