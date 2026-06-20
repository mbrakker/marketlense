<?php
/**
 * Intelligence aggregates for homepage and archive surfaces.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Intelligence_Stats
{
    private const MIN_RECENT_REPORTS = 5;

    /**
     * @var array<string,list<int>>
     */
    private array $published_ids_cache = [];

    /**
     * @var array<string,array<int,\WP_Term>>
     */
    private array $term_cache = [];

    private Report_View_Model_Builder $view_model_builder;

    public function __construct(Report_View_Model_Builder $view_model_builder)
    {
        $this->view_model_builder = $view_model_builder;
    }

    /**
     * Returns the latest published Market Bearing report.
     */
    public function latest_report(): ?\WP_Post
    {
        foreach ($this->published_report_ids() as $post_id) {
            $post = get_post($post_id);
            if (! ($post instanceof \WP_Post)) {
                continue;
            }

            $report = $this->view_model_builder->build($post);
            if (($report['card_contract_valid'] ?? false) === true) {
                return $post;
            }
        }

        return null;
    }

    /**
     * @return array<string,mixed>
     */
    public function homepage_metrics(): array
    {
        $latest = $this->latest_report();
        $report_ids = $this->published_report_ids();
        $latest_label = __('No reports yet', 'marketlense-core');

        if ($latest instanceof \WP_Post) {
            $timestamp = get_post_timestamp($latest, 'date');
            if (is_int($timestamp) && $timestamp > 0) {
                $age = current_time('timestamp') - $timestamp;
                $latest_label = $age <= \DAY_IN_SECONDS
                    ? __('Updated today', 'marketlense-core')
                    : sprintf(
                        /* translators: %s is a formatted date. */
                        __('Updated %s', 'marketlense-core'),
                        wp_date('F j, Y', $timestamp)
                    );
            }
        }

        $citation_count = 0;
        $derived_signal_count = 0;
        foreach ($report_ids as $report_id) {
            $post = get_post($report_id);
            if (! ($post instanceof \WP_Post)) {
                continue;
            }

            $report = $this->view_model_builder->build($post);
            $citation_count += max(0, (int) ($report['citations_count'] ?? 0));
            if (! empty($report['full_key_metrics'])) {
                $derived_signal_count++;
            }
        }

        $published_signal_count = $this->published_post_type_count(Post_Type::SIGNAL_POST_TYPE);

        return [
            'report_count' => count($report_ids),
            'publisher_count' => count($this->content_backed_terms(Taxonomies::PUBLISHER_TAXONOMY)),
            'topic_count' => count($this->content_backed_terms(Taxonomies::CATEGORY_TAXONOMY)),
            'briefing_count' => $this->published_post_type_count(Post_Type::BRIEFING_POST_TYPE),
            'signal_count' => $published_signal_count > 0 ? $published_signal_count : $derived_signal_count,
            'signal_label' => $published_signal_count > 0
                ? __('Published signals', 'marketlense-core')
                : __('Report signals', 'marketlense-core'),
            'citation_count' => $citation_count,
            'latest_label' => $latest_label,
        ];
    }

    /**
     * Returns taxonomy entities represented by published intelligence.
     *
     * @return array<int,array{term:\WP_Term,reports:int,briefings:int,signals:int,total:int}>
     */
    public function content_backed_terms(string $taxonomy, int $limit = 300): array
    {
        $cache_key = 'content:' . $taxonomy . ':' . $limit;
        if (isset($this->term_cache[$cache_key])) {
            return $this->term_cache[$cache_key];
        }

        $sources = [
            'reports' => $this->published_report_ids(),
            'briefings' => $this->published_ids_for_post_type(Post_Type::BRIEFING_POST_TYPE),
            'signals' => $this->published_ids_for_post_type(Post_Type::SIGNAL_POST_TYPE),
        ];
        $items = [];

        foreach ($sources as $source => $post_ids) {
            foreach ($this->count_terms_for_posts($post_ids, $taxonomy) as $row) {
                $term = $row['term'];
                if (! ($term instanceof \WP_Term)) {
                    continue;
                }
                if ($this->is_placeholder_term($term->name)) {
                    continue;
                }

                $term_id = (int) $term->term_id;
                if (! isset($items[$term_id])) {
                    $items[$term_id] = [
                        'term' => clone $term,
                        'reports' => 0,
                        'briefings' => 0,
                        'signals' => 0,
                        'total' => 0,
                    ];
                }

                $count = max(0, (int) $row['count']);
                $items[$term_id][$source] = $count;
                $items[$term_id]['total'] += $count;
            }
        }

        $items = array_values(
            array_filter(
                $items,
                static fn (array $item): bool => (int) $item['total'] > 0
            )
        );
        usort(
            $items,
            static function (array $left, array $right): int {
                $count_compare = (int) $right['total'] <=> (int) $left['total'];
                if ($count_compare !== 0) {
                    return $count_compare;
                }

                return strcasecmp((string) $left['term']->name, (string) $right['term']->name);
            }
        );

        $result = array_slice($items, 0, $limit);
        $this->term_cache[$cache_key] = $result;

        return $result;
    }

    /**
     * Returns non-empty report periods used by published report records.
     *
     * @return list<string>
     */
    public function report_periods(): array
    {
        $periods = [];
        foreach ($this->published_report_ids() as $post_id) {
            $period = trim((string) get_post_meta($post_id, Meta::META_TIME_PERIOD, true));
            if (! $this->is_placeholder_term($period)) {
                $periods[$period] = true;
            }
        }

        $values = array_keys($periods);
        natcasesort($values);

        return array_values($values);
    }

    /**
     * Returns non-empty report regions used by published report records.
     *
     * @return list<string>
     */
    public function report_regions(): array
    {
        $regions = [];
        foreach ($this->published_report_ids() as $post_id) {
            $region = trim((string) get_post_meta($post_id, Meta::META_REGION, true));
            if (! $this->is_placeholder_term($region)) {
                $regions[$region] = true;
            }
        }

        $values = array_keys($regions);
        natcasesort($values);

        return array_values($values);
    }

    private function published_post_type_count(string $post_type): int
    {
        $counts = wp_count_posts($post_type);
        if (! is_object($counts) || ! isset($counts->publish)) {
            return 0;
        }

        return max(0, (int) $counts->publish);
    }

    /**
     * @return list<int>
     */
    private function published_ids_for_post_type(string $post_type): array
    {
        $post_ids = get_posts(
            [
                'post_type' => $post_type,
                'post_status' => 'publish',
                'fields' => 'ids',
                'posts_per_page' => -1,
                'no_found_rows' => true,
                'update_post_meta_cache' => false,
                'update_post_term_cache' => false,
            ]
        );
        if (! is_array($post_ids)) {
            return [];
        }

        return array_values(
            array_filter(
                array_map('intval', $post_ids),
                static fn (int $post_id): bool => $post_id > 0
            )
        );
    }

    /**
     * @return array<int,\WP_Term>
     */
    public function scoped_terms(string $taxonomy, int $limit = 300, bool $hide_empty = true): array
    {
        $cache_key = $taxonomy . ':' . $limit . ':' . ($hide_empty ? '1' : '0');
        if (isset($this->term_cache[$cache_key])) {
            return $this->term_cache[$cache_key];
        }

        $report_ids = $this->published_report_ids();
        if ($report_ids === []) {
            $this->term_cache[$cache_key] = [];

            return [];
        }

        $counts = $this->count_terms_for_posts($report_ids, $taxonomy);
        if ($hide_empty) {
            $counts = array_values(
                array_filter(
                    $counts,
                    static fn (array $item): bool => (int) $item['count'] > 0
                )
            );
        }

        usort(
            $counts,
            static function (array $left, array $right): int {
                $count_compare = (int) $right['count'] <=> (int) $left['count'];
                if ($count_compare !== 0) {
                    return $count_compare;
                }

                return strcasecmp((string) $left['term']->name, (string) $right['term']->name);
            }
        );

        $terms = [];
        foreach (array_slice($counts, 0, $limit) as $item) {
            $term = $item['term'];
            if ($term instanceof \WP_Term) {
                $term->count = (int) $item['count'];
                $terms[] = $term;
            }
        }

        $this->term_cache[$cache_key] = $terms;

        return $terms;
    }

    /**
     * Returns every term in the taxonomy while keeping counts scoped to published reports.
     *
     * @return array<int,\WP_Term>
     */
    public function all_terms(string $taxonomy, int $limit = 300): array
    {
        $cache_key = 'all:' . $taxonomy . ':' . $limit;
        if (isset($this->term_cache[$cache_key])) {
            return $this->term_cache[$cache_key];
        }

        $raw_terms = get_terms(
            [
                'taxonomy' => $taxonomy,
                'hide_empty' => false,
            ]
        );

        if (is_wp_error($raw_terms) || ! is_array($raw_terms) || $raw_terms === []) {
            $this->term_cache[$cache_key] = [];

            return [];
        }

        $count_map = [];
        foreach ($this->count_terms_for_posts($this->published_report_ids(), $taxonomy) as $item) {
            $term = $item['term'];
            if ($term instanceof \WP_Term) {
                $count_map[(int) $term->term_id] = (int) $item['count'];
            }
        }

        usort(
            $raw_terms,
            static function (\WP_Term $left, \WP_Term $right) use ($count_map): int {
                $left_count = $count_map[(int) $left->term_id] ?? 0;
                $right_count = $count_map[(int) $right->term_id] ?? 0;
                $count_compare = $right_count <=> $left_count;
                if ($count_compare !== 0) {
                    return $count_compare;
                }

                return strcasecmp($left->name, $right->name);
            }
        );

        $terms = [];
        foreach (array_slice($raw_terms, 0, $limit) as $term) {
            if (! ($term instanceof \WP_Term)) {
                continue;
            }

            $scoped_term = clone $term;
            $scoped_term->count = $count_map[(int) $term->term_id] ?? 0;
            $terms[] = $scoped_term;
        }

        $this->term_cache[$cache_key] = $terms;

        return $terms;
    }

    /**
     * @return array<string,mixed>
     */
    public function weekly_signals(int $limit = 5): array
    {
        $window = $this->selected_window();
        $current_topic_counts = $this->count_terms_for_posts($window['current_ids'], Taxonomies::CATEGORY_TAXONOMY);
        $previous_topic_map = $this->counts_to_slug_map(
            $this->count_terms_for_posts($window['previous_ids'], Taxonomies::CATEGORY_TAXONOMY)
        );
        $current_publisher_counts = $this->count_terms_for_posts($window['current_ids'], Taxonomies::PUBLISHER_TAXONOMY);
        $previous_publisher_map = $this->counts_to_slug_map(
            $this->count_terms_for_posts($window['previous_ids'], Taxonomies::PUBLISHER_TAXONOMY)
        );

        $trending_topics = $this->decorate_term_counts($current_topic_counts, $previous_topic_map, $limit, true);
        $emerging_themes = array_values(
            array_filter(
                $trending_topics,
                static fn (array $item): bool => isset($item['delta']) && (int) $item['delta'] > 0
            )
        );

        usort(
            $emerging_themes,
            static function (array $left, array $right): int {
                $delta_compare = ((int) ($right['delta'] ?? 0)) <=> ((int) ($left['delta'] ?? 0));
                if ($delta_compare !== 0) {
                    return $delta_compare;
                }

                return ((int) $right['count']) <=> ((int) $left['count']);
            }
        );

        if ($emerging_themes === []) {
            $emerging_themes = array_slice($trending_topics, 0, $limit);
        } else {
            $emerging_themes = array_slice($emerging_themes, 0, $limit);
        }

        return [
            'window_label' => sprintf(
                /* translators: %d is a day count. */
                __('Past %d days', 'marketlense-core'),
                $window['days']
            ),
            'trending_topics' => array_slice($trending_topics, 0, $limit),
            'emerging_themes' => $emerging_themes,
            'top_publishers' => array_slice(
                $this->decorate_term_counts($current_publisher_counts, $previous_publisher_map, $limit, false),
                0,
                $limit
            ),
        ];
    }

    /**
     * @return array<int,array<string,mixed>>
     */
    public function strategic_themes(int $limit = 6): array
    {
        $overall = $this->count_terms_for_posts($this->published_report_ids(), Taxonomies::CATEGORY_TAXONOMY);
        $window = $this->selected_window();
        $current_map = $this->counts_to_slug_map(
            $this->count_terms_for_posts($window['current_ids'], Taxonomies::CATEGORY_TAXONOMY)
        );
        $previous_map = $this->counts_to_slug_map(
            $this->count_terms_for_posts($window['previous_ids'], Taxonomies::CATEGORY_TAXONOMY)
        );

        return array_slice(
            $this->decorate_term_counts($overall, $previous_map, $limit, true, $current_map),
            0,
            $limit
        );
    }

    /**
     * @return array<int,array<string,mixed>>
     */
    public function publisher_authority(int $limit = 12): array
    {
        $counts = $this->count_terms_for_posts($this->published_report_ids(), Taxonomies::PUBLISHER_TAXONOMY);
        $items = [];
        foreach (array_slice($counts, 0, $limit) as $item) {
            $term = $item['term'];
            if (! ($term instanceof \WP_Term)) {
                continue;
            }

            $items[] = [
                'name' => $term->name,
                'count' => (int) $item['count'],
                'url' => $this->safe_term_link($term),
                'homepage' => (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_HOMEPAGE_META, true),
            ];
        }

        return $items;
    }

    /**
     * @return list<int>
     */
    private function published_report_ids(array $extra_args = []): array
    {
        $cache_key = md5(wp_json_encode($extra_args));
        if (isset($this->published_ids_cache[$cache_key])) {
            return $this->published_ids_cache[$cache_key];
        }

        $post_ids = get_posts(
            Meta::apply_digest_query_constraints(
                array_merge(
                    [
                        'post_status' => 'publish',
                        'fields' => 'ids',
                        'posts_per_page' => -1,
                        'no_found_rows' => true,
                        'update_post_meta_cache' => false,
                        'update_post_term_cache' => false,
                        'orderby' => 'date',
                        'order' => 'DESC',
                    ],
                    $extra_args
                )
            )
        );

        if (! is_array($post_ids)) {
            $this->published_ids_cache[$cache_key] = [];

            return [];
        }

        $normalized = array_values(
            array_filter(
                array_map('intval', $post_ids),
                static fn (int $post_id): bool => $post_id > 0
            )
        );
        $this->published_ids_cache[$cache_key] = $normalized;

        return $normalized;
    }

    /**
     * @return array{days:int,current_ids:list<int>,previous_ids:list<int>}
     */
    private function selected_window(): array
    {
        $seven_day_ids = $this->window_post_ids(7);
        if (count($seven_day_ids) >= self::MIN_RECENT_REPORTS) {
            return [
                'days' => 7,
                'current_ids' => $seven_day_ids,
                'previous_ids' => $this->window_post_ids(7, 7),
            ];
        }

        return [
            'days' => 30,
            'current_ids' => $this->window_post_ids(30),
            'previous_ids' => $this->window_post_ids(30, 30),
        ];
    }

    /**
     * @return list<int>
     */
    private function window_post_ids(int $days, int $offset_days = 0): array
    {
        $after_timestamp = current_time('timestamp', true) - (($days + $offset_days) * \DAY_IN_SECONDS);
        $before_timestamp = $offset_days > 0
            ? current_time('timestamp', true) - ($offset_days * \DAY_IN_SECONDS)
            : null;

        $date_query = [
            [
                'column' => 'post_date_gmt',
                'after' => gmdate('Y-m-d H:i:s', $after_timestamp),
                'inclusive' => true,
            ],
        ];

        if ($before_timestamp !== null) {
            $date_query[0]['before'] = gmdate('Y-m-d H:i:s', $before_timestamp);
            $date_query[0]['inclusive'] = false;
        }

        return $this->published_report_ids(
            [
                'date_query' => $date_query,
            ]
        );
    }

    /**
     * @param list<int> $post_ids
     * @return array<int,array{term:\WP_Term,count:int}>
     */
    private function count_terms_for_posts(array $post_ids, string $taxonomy): array
    {
        if ($post_ids === []) {
            return [];
        }

        $term_rows = wp_get_object_terms(
            $post_ids,
            $taxonomy,
            [
                'fields' => 'all_with_object_id',
            ]
        );

        if (is_wp_error($term_rows) || ! is_array($term_rows)) {
            return [];
        }

        $terms = [];
        foreach ($term_rows as $term) {
            if (! ($term instanceof \WP_Term)) {
                continue;
            }

            $term_id = (int) $term->term_id;
            if ($term_id < 1) {
                continue;
            }

            if (! isset($terms[$term_id])) {
                $terms[$term_id] = [
                    'term' => clone $term,
                    'objects' => [],
                ];
            }

            $object_id = isset($term->object_id) ? (int) $term->object_id : 0;
            if ($object_id > 0) {
                $terms[$term_id]['objects'][$object_id] = true;
            }
        }

        $counts = [];
        foreach ($terms as $row) {
            $term = $row['term'];
            if (! ($term instanceof \WP_Term)) {
                continue;
            }

            $counts[] = [
                'term' => $term,
                'count' => count($row['objects']),
            ];
        }

        usort(
            $counts,
            static function (array $left, array $right): int {
                $count_compare = (int) $right['count'] <=> (int) $left['count'];
                if ($count_compare !== 0) {
                    return $count_compare;
                }

                return strcasecmp((string) $left['term']->name, (string) $right['term']->name);
            }
        );

        return $counts;
    }

    /**
     * @param array<int,array{term:\WP_Term,count:int}> $counts
     * @return array<string,int>
     */
    private function counts_to_slug_map(array $counts): array
    {
        $map = [];
        foreach ($counts as $item) {
            $term = $item['term'];
            if (! ($term instanceof \WP_Term)) {
                continue;
            }

            $map[$term->slug] = (int) $item['count'];
        }

        return $map;
    }

    /**
     * @param array<int,array{term:\WP_Term,count:int}> $counts
     * @param array<string,int> $previous_map
     * @param array<string,int>|null $current_map_override
     * @return array<int,array<string,mixed>>
     */
    private function decorate_term_counts(
        array $counts,
        array $previous_map,
        int $limit,
        bool $include_delta,
        ?array $current_map_override = null
    ): array {
        $items = [];
        foreach (array_slice($counts, 0, $limit) as $item) {
            $term = $item['term'];
            if (! ($term instanceof \WP_Term)) {
                continue;
            }

            $current_count = is_array($current_map_override)
                ? ($current_map_override[$term->slug] ?? 0)
                : (int) $item['count'];
            $previous_count = $previous_map[$term->slug] ?? 0;
            $delta = $include_delta ? ($current_count - $previous_count) : null;
            $items[] = [
                'name' => $term->name,
                'count' => (int) $item['count'],
                'delta' => $delta === 0 ? null : $delta,
                'url' => $this->safe_term_link($term),
            ];
        }

        return $items;
    }

    private function safe_term_link(\WP_Term $term): string
    {
        $link = get_term_link($term);

        return is_wp_error($link) ? '' : (string) $link;
    }

    private function is_placeholder_term(string $value): bool
    {
        return in_array(
            strtolower(trim($value)),
            ['', '...', '…', 'not extracted', 'not specified', 'unknown', 'n/a', 'na', '-'],
            true
        );
    }
}
