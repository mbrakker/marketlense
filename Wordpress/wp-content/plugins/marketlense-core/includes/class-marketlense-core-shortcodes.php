<?php
/**
 * Frontend shortcodes for report browsing and taxonomy directories.
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
     * Registers shortcode handlers.
     */
    public function register(): void
    {
        add_shortcode('ml_report_browser', [$this, 'render_report_browser']);
        add_shortcode('ml_topics_directory', [$this, 'render_topics_directory']);
        add_shortcode('ml_publishers_directory', [$this, 'render_publishers_directory']);
    }

    /**
     * Renders browse reports section with URL-based taxonomy filtering.
     *
     * @param array<string,mixed> $attrs Shortcode attributes.
     */
    public function render_report_browser(array $attrs = []): string
    {
        $atts = shortcode_atts(
            [
                'per_page' => (string) self::DEFAULT_PER_PAGE,
            ],
            $attrs,
            'ml_report_browser'
        );

        $per_page = max(1, min(48, (int) $atts['per_page']));
        $current_page = $this->current_page();
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
            'post_type'      => Post_Type::POST_TYPE,
            'post_status'    => 'publish',
            'posts_per_page' => $per_page,
            'paged'          => $current_page,
            'orderby'        => 'date',
            'order'          => 'DESC',
        ];

        if (! empty($active_filters)) {
            $tax_query = ['relation' => 'AND'];
            if ($selected_topic !== '') {
                $tax_query[] = [
                    'taxonomy' => Taxonomies::CATEGORY_TAXONOMY,
                    'field'    => 'slug',
                    'terms'    => [$selected_topic],
                ];
            }
            if ($selected_publisher !== '') {
                $tax_query[] = [
                    'taxonomy' => Taxonomies::PUBLISHER_TAXONOMY,
                    'field'    => 'slug',
                    'terms'    => [$selected_publisher],
                ];
            }
            $query_args['tax_query'] = $tax_query;
        }

        $query = new \WP_Query($query_args);
        $topic_options = $this->report_taxonomy_terms(Taxonomies::CATEGORY_TAXONOMY);
        $publisher_options = $this->report_taxonomy_terms(Taxonomies::PUBLISHER_TAXONOMY);

        ob_start();
        ?>
        <section class="ml-report-browser ml-surface">
            <form class="ml-report-filter-form" method="get" action="<?php echo esc_url($archive_url); ?>">
                <div class="ml-report-filter-grid">
                    <label class="ml-report-filter-field" for="ml_topic_filter">
                        <span><?php esc_html_e('Topic', 'marketlense-core'); ?></span>
                        <select id="ml_topic_filter" name="ml_topic">
                            <option value=""><?php esc_html_e('All topics', 'marketlense-core'); ?></option>
                            <?php foreach ($topic_options as $term) : ?>
                                <option
                                    value="<?php echo esc_attr($term->slug); ?>"
                                    <?php selected($selected_topic, $term->slug); ?>
                                >
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
                                <option
                                    value="<?php echo esc_attr($term->slug); ?>"
                                    <?php selected($selected_publisher, $term->slug); ?>
                                >
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

            <?php if (! empty($active_filters)) : ?>
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
                            <a class="ml-filter-chip" href="<?php echo esc_url($topic_reset); ?>">
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
                            <a class="ml-filter-chip" href="<?php echo esc_url($publisher_reset); ?>">
                                <?php echo esc_html(sprintf(__('Publisher: %s', 'marketlense-core'), $publisher->name)); ?>
                            </a>
                        <?php endif; ?>
                    <?php endif; ?>
                </div>
            <?php endif; ?>

            <?php if ($query->have_posts()) : ?>
                <div class="ml-report-grid ml-report-browser-grid">
                    <?php while ($query->have_posts()) : ?>
                        <?php $query->the_post(); ?>
                        <article class="ml-report-card">
                            <?php if (has_post_thumbnail()) : ?>
                                <a class="ml-report-card-image" href="<?php the_permalink(); ?>">
                                    <?php the_post_thumbnail('large'); ?>
                                </a>
                            <?php endif; ?>

                            <h3 class="ml-report-card-title">
                                <a href="<?php the_permalink(); ?>"><?php the_title(); ?></a>
                            </h3>

                            <p class="ml-report-card-date">
                                <?php echo esc_html(get_the_date()); ?>
                            </p>

                            <div class="ml-chip-terms">
                                <?php
                                $publisher_terms = get_the_term_list(
                                    get_the_ID(),
                                    Taxonomies::PUBLISHER_TAXONOMY,
                                    '',
                                    ' ',
                                    ''
                                );
                                if (is_string($publisher_terms) && $publisher_terms !== '') {
                                    echo wp_kses_post($publisher_terms);
                                }
                                ?>
                            </div>

                            <div class="ml-chip-terms">
                                <?php
                                $topic_terms = get_the_term_list(
                                    get_the_ID(),
                                    Taxonomies::CATEGORY_TAXONOMY,
                                    '',
                                    ' ',
                                    ''
                                );
                                if (is_string($topic_terms) && $topic_terms !== '') {
                                    echo wp_kses_post($topic_terms);
                                }
                                ?>
                            </div>

                            <?php
                            $excerpt = wp_trim_words(
                                wp_strip_all_tags((string) get_the_excerpt()),
                                28
                            );
                            ?>
                            <?php if ($excerpt !== '') : ?>
                                <p><?php echo esc_html($excerpt); ?></p>
                            <?php endif; ?>

                            <p class="ml-report-card-link">
                                <a href="<?php the_permalink(); ?>">
                                    <?php esc_html_e('Open digest', 'marketlense-core'); ?>
                                </a>
                            </p>
                        </article>
                    <?php endwhile; ?>
                </div>

                <?php $this->render_pagination($query, $active_filters); ?>
            <?php else : ?>
                <div class="ml-empty-state">
                    <p><?php esc_html_e('No reports match the current filters.', 'marketlense-core'); ?></p>
                </div>
            <?php endif; ?>
            <?php wp_reset_postdata(); ?>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders topic directory cards.
     */
    public function render_topics_directory(): string
    {
        $terms = $this->report_taxonomy_terms(Taxonomies::CATEGORY_TAXONOMY, false);
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
                        <?php
                        echo esc_html(
                            sprintf(
                                _n('%d report', '%d reports', (int) $term->count, 'marketlense-core'),
                                (int) $term->count
                            )
                        );
                        ?>
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
        $terms = $this->report_taxonomy_terms(Taxonomies::PUBLISHER_TAXONOMY, false);
        if ($terms === []) {
            return '<p>' . esc_html__('No publishers are available yet.', 'marketlense-core') . '</p>';
        }

        ob_start();
        ?>
        <section class="ml-directory-list">
            <?php foreach ($terms as $term) : ?>
                <?php
                $archive_link = get_term_link($term);
                $homepage = (string) get_term_meta(
                    $term->term_id,
                    Taxonomies::PUBLISHER_HOMEPAGE_META,
                    true
                );
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
                        <?php
                        echo esc_html(
                            sprintf(
                                _n('%d report', '%d reports', (int) $term->count, 'marketlense-core'),
                                (int) $term->count
                            )
                        );
                        ?>
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
                            <a
                                class="ml-button ml-button-primary"
                                href="<?php echo esc_url($homepage); ?>"
                                target="_blank"
                                rel="noopener noreferrer"
                            >
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
     * @return array<int,\WP_Term>
     */
    private function report_taxonomy_terms(string $taxonomy, bool $hide_empty = true): array
    {
        $report_ids = get_posts(
            [
                'post_type'              => Post_Type::POST_TYPE,
                'post_status'            => 'publish',
                'fields'                 => 'ids',
                'posts_per_page'         => -1,
                'no_found_rows'          => true,
                'update_post_meta_cache' => false,
                'update_post_term_cache' => false,
                'orderby'                => 'date',
                'order'                  => 'DESC',
            ]
        );

        if (! is_array($report_ids) || $report_ids === []) {
            return [];
        }

        $term_rows = wp_get_object_terms(
            $report_ids,
            $taxonomy,
            [
                'fields' => 'all_with_object_id',
            ]
        );

        if (is_wp_error($term_rows) || ! is_array($term_rows)) {
            return [];
        }

        $terms = [];
        $counts = [];
        foreach ($term_rows as $term) {
            if (! ($term instanceof \WP_Term)) {
                continue;
            }

            $term_id = (int) $term->term_id;
            if ($term_id <= 0) {
                continue;
            }

            if (! isset($terms[$term_id])) {
                $terms[$term_id] = clone $term;
                $counts[$term_id] = [];
            }

            $object_id = isset($term->object_id) ? (int) $term->object_id : 0;
            if ($object_id > 0) {
                $counts[$term_id][$object_id] = true;
            }
        }

        $scoped_terms = [];
        foreach ($terms as $term_id => $term) {
            $term->count = isset($counts[$term_id]) ? count($counts[$term_id]) : 0;
            if ($hide_empty && (int) $term->count < 1) {
                continue;
            }
            $scoped_terms[] = $term;
        }

        usort(
            $scoped_terms,
            static function (\WP_Term $left, \WP_Term $right): int {
                $count_compare = (int) $right->count <=> (int) $left->count;
                if ($count_compare !== 0) {
                    return $count_compare;
                }

                return strcasecmp($left->name, $right->name);
            }
        );

        return array_slice($scoped_terms, 0, 300);
    }

    /**
     * Resolves a validated filter slug from query string.
     */
    private function selected_filter_slug(string $query_key, string $taxonomy): string
    {
        if (! isset($_GET[$query_key])) {
            $archive_slug = $this->current_archive_term_slug($taxonomy);
            if ($archive_slug !== '') {
                return $archive_slug;
            }
            return '';
        }

        $raw = wp_unslash((string) $_GET[$query_key]);
        $slug = sanitize_title($raw);
        if ($slug === '') {
            return '';
        }

        $term = get_term_by('slug', $slug, $taxonomy);
        if (! ($term instanceof \WP_Term)) {
            return $this->current_archive_term_slug($taxonomy);
        }

        return $slug;
    }

    /**
     * Resolves the current archive term slug when viewing a taxonomy archive directly.
     */
    private function current_archive_term_slug(string $taxonomy): string
    {
        if ($taxonomy === Taxonomies::CATEGORY_TAXONOMY) {
            if (! is_category()) {
                return '';
            }
        } elseif (! is_tax($taxonomy)) {
            return '';
        }

        $term = get_queried_object();
        if (! ($term instanceof \WP_Term) || $term->taxonomy !== $taxonomy) {
            return '';
        }

        return sanitize_title($term->slug);
    }

    /**
     * Renders pagination preserving active filter query params.
     *
     * @param \WP_Query          $query Query object.
     * @param array<string,mixed> $active_filters Filter args.
     */
    private function render_pagination(\WP_Query $query, array $active_filters): void
    {
        if ($query->max_num_pages <= 1) {
            return;
        }

        $pagination = paginate_links(
            [
                'base'      => str_replace(999999999, '%#%', (string) esc_url(get_pagenum_link(999999999))),
                'current'   => max(1, $this->current_page()),
                'total'     => (int) $query->max_num_pages,
                'type'      => 'array',
                'mid_size'  => 1,
                'end_size'  => 1,
                'prev_text' => __('Previous', 'marketlense-core'),
                'next_text' => __('Next', 'marketlense-core'),
                'add_args'  => $active_filters,
            ]
        );

        if (! is_array($pagination) || $pagination === []) {
            return;
        }

        echo '<nav class="ml-pagination" aria-label="' . esc_attr__('Pagination', 'marketlense-core') . '">';
        echo '<ul>';
        foreach ($pagination as $item) {
            echo '<li>' . wp_kses_post($item) . '</li>';
        }
        echo '</ul>';
        echo '</nav>';
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
}
