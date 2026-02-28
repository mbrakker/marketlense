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
    /**
     * @var array<string,string>
     */
    private const SHORTCODE_METHODS = [
        'ml_report_browser' => 'render_report_browser',
        'ml_topics_directory' => 'render_topics_directory',
        'ml_publishers_directory' => 'render_publishers_directory',
        'ml_home_metrics' => 'render_home_metrics',
        'ml_featured_digest' => 'render_featured_digest',
        'ml_intelligence_signals' => 'render_intelligence_signals',
        'ml_strategic_themes' => 'render_strategic_themes',
        'ml_publisher_authority' => 'render_publisher_authority',
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
        $block_name = isset($block['blockName']) && is_string($block['blockName'])
            ? $block['blockName']
            : '';

        if ($block_name !== 'core/shortcode' || $block_content === '' || ! str_contains($block_content, '[ml_')) {
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
        $archive_url = get_post_type_archive_link(Post_Type::POST_TYPE);
        if (! is_string($archive_url) || $archive_url === '') {
            $archive_url = home_url('/reports/');
        }

        $selected_topic = $this->selected_filter_slug('ml_topic', Taxonomies::CATEGORY_TAXONOMY);
        $selected_publisher = $this->selected_filter_slug('ml_publisher', Taxonomies::PUBLISHER_TAXONOMY);
        $active_filters = [];
        if ($selected_topic !== '') {
            $active_filters['ml_topic'] = $selected_topic;
        }
        if ($selected_publisher !== '') {
            $active_filters['ml_publisher'] = $selected_publisher;
        }

        $query_args = [
            'post_type' => Post_Type::POST_TYPE,
            'post_status' => 'publish',
            'posts_per_page' => $per_page,
            'paged' => $current_page,
            'orderby' => 'date',
            'order' => 'DESC',
        ];

        if ($context === 'auto') {
            $search_term = trim((string) get_search_query());
            if ($search_term !== '') {
                $query_args['s'] = $search_term;
            }
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

        ob_start();
        ?>
        <section class="ml-report-browser" aria-label="<?php esc_attr_e('Report browser', 'marketlense-core'); ?>">
            <?php if ($show_filters) : ?>
                <form class="ml-report-filter-form" method="get" action="<?php echo esc_url($archive_url); ?>">
                    <div class="ml-report-filter-grid">
                        <label class="ml-report-filter-field" for="ml_topic_filter">
                            <span><?php esc_html_e('Topic', 'marketlense-core'); ?></span>
                            <select id="ml_topic_filter" name="ml_topic">
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
            <?php endif; ?>

            <?php if ($active_filters !== []) : ?>
                <div class="ml-active-filters" aria-label="<?php esc_attr_e('Active filters', 'marketlense-core'); ?>">
                    <?php if ($selected_topic !== '') : ?>
                        <?php $topic = get_term_by('slug', $selected_topic, Taxonomies::CATEGORY_TAXONOMY); ?>
                        <?php if ($topic instanceof \WP_Term) : ?>
                            <?php
                            $topic_reset = add_query_arg(
                                ['ml_publisher' => $selected_publisher !== '' ? $selected_publisher : null],
                                $archive_url
                            );
                            ?>
                            <a class="ml-filter-chip" href="<?php echo esc_url((string) $topic_reset); ?>">
                                <?php echo esc_html(sprintf(__('Topic: %s', 'marketlense-core'), $topic->name)); ?>
                            </a>
                        <?php endif; ?>
                    <?php endif; ?>

                    <?php if ($selected_publisher !== '') : ?>
                        <?php $publisher = get_term_by('slug', $selected_publisher, Taxonomies::PUBLISHER_TAXONOMY); ?>
                        <?php if ($publisher instanceof \WP_Term) : ?>
                            <?php
                            $publisher_reset = add_query_arg(
                                ['ml_topic' => $selected_topic !== '' ? $selected_topic : null],
                                $archive_url
                            );
                            ?>
                            <a class="ml-filter-chip" href="<?php echo esc_url((string) $publisher_reset); ?>">
                                <?php echo esc_html(sprintf(__('Publisher: %s', 'marketlense-core'), $publisher->name)); ?>
                            </a>
                        <?php endif; ?>
                    <?php endif; ?>
                </div>
            <?php endif; ?>

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
                    if (isset($query_args['s']) && is_string($query_args['s']) && $query_args['s'] !== '') {
                        $pagination_args['s'] = $query_args['s'];
                    }
                    ?>
                    <?php $this->render_pagination($query, $pagination_args); ?>
                <?php endif; ?>
            <?php else : ?>
                <div class="ml-empty-state">
                    <p><?php esc_html_e('No reports match the current view.', 'marketlense-core'); ?></p>
                </div>
            <?php endif; ?>
            <?php wp_reset_postdata(); ?>
        </section>
        <?php
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
                        <span class="ml-featured-media-fallback"><?php esc_html_e('No preview available', 'marketlense-core'); ?></span>
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
    public function render_intelligence_signals(): string
    {
        $signals = $this->stats->weekly_signals();
        if (
            $signals['trending_topics'] === []
            && $signals['emerging_themes'] === []
            && $signals['top_publishers'] === []
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

            <div class="ml-signal-columns">
                <?php $this->render_signal_column(__('Trending topics', 'marketlense-core'), $signals['trending_topics']); ?>
                <?php $this->render_signal_column(__('Emerging themes', 'marketlense-core'), $signals['emerging_themes']); ?>
                <?php $this->render_signal_column(__('Top publishers', 'marketlense-core'), $signals['top_publishers']); ?>
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
        <section class="ml-directory-list">
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
        $terms = $this->stats->scoped_terms(Taxonomies::PUBLISHER_TAXONOMY, 300, false);
        if ($terms === []) {
            return '<p>' . esc_html__('No publishers are available yet.', 'marketlense-core') . '</p>';
        }

        ob_start();
        ?>
        <section class="ml-directory-list">
            <?php foreach ($terms as $term) : ?>
                <?php
                $archive_link = get_term_link($term);
                $homepage = (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_HOMEPAGE_META, true);
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
                    <?php if ($term->description !== '') : ?>
                        <p><?php echo esc_html($term->description); ?></p>
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
                    </div>
                </article>
            <?php endforeach; ?>
        </section>
        <?php
        return (string) ob_get_clean();
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
                    <span class="ml-report-card-image-fallback"><?php esc_html_e('No preview available', 'marketlense-core'); ?></span>
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
    private function render_signal_column(string $title, array $items): void
    {
        ?>
        <section class="ml-signal-column">
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
     * Resolves the current archive term slug when viewing a taxonomy archive directly.
     */
    private function current_archive_term_slug(string $query_key, string $taxonomy): string
    {
        if ($query_key === 'ml_topic' && is_tax(Taxonomies::TOPIC_TAXONOMY)) {
            $term = get_queried_object();
            if ($term instanceof \WP_Term) {
                return sanitize_title($term->slug);
            }
        }

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
                'base' => str_replace(999999999, '%#%', (string) esc_url(get_pagenum_link(999999999))),
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

    private function to_bool_flag(mixed $value): bool
    {
        return in_array((string) $value, ['1', 'true', 'yes', 'on'], true);
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
}
