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

    private Intelligence_Projection $intelligence_projection;

    public function __construct(
        Report_View_Model_Builder $view_model_builder,
        Intelligence_Projection $intelligence_projection
    )
    {
        $this->view_model_builder = $view_model_builder;
        $this->intelligence_projection = $intelligence_projection;
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
        $projection = $this->intelligence_projection->current();
        if (is_array($projection) && is_array($projection['homepage_metrics'] ?? null)) {
            return $projection['homepage_metrics'];
        }

        return $this->neutral_homepage_metrics();
    }

    /**
     * Returns a deliberately neutral state when the pipeline has not approved a projection.
     *
     * @return array<string,int|string>
     */
    private function neutral_homepage_metrics(): array
    {
        return [
            'report_count' => 0,
            'publisher_count' => 0,
            'topic_count' => 0,
            'briefing_count' => 0,
            'signal_count' => 0,
            'signal_label' => __('Published signals', 'marketlense-core'),
            'citation_count' => 0,
            'latest_label' => '',
        ];
    }

    /**
     * @return array{window_label:string,trending_topics:list<array<string,mixed>>,emerging_themes:list<array<string,mixed>>,top_publishers:list<array<string,mixed>>}
     */
    private function neutral_weekly_signals(): array
    {
        return [
            'window_label' => '',
            'trending_topics' => [],
            'emerging_themes' => [],
            'top_publishers' => [],
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
        $projection = $this->intelligence_projection->current();
        $signals = is_array($projection) && is_array($projection['weekly_signals'] ?? null)
            ? $projection['weekly_signals']
            : $this->neutral_weekly_signals();

        return [
            'window_label' => (string) ($signals['window_label'] ?? ''),
            'trending_topics' => array_slice((array) ($signals['trending_topics'] ?? []), 0, $limit),
            'emerging_themes' => array_slice((array) ($signals['emerging_themes'] ?? []), 0, $limit),
            'top_publishers' => array_slice((array) ($signals['top_publishers'] ?? []), 0, $limit),
        ];
    }

    /**
     * @return array<int,array<string,mixed>>
     */
    public function strategic_themes(int $limit = 6): array
    {
        $projection = $this->intelligence_projection->current();
        $themes = is_array($projection) ? (array) ($projection['strategic_themes'] ?? []) : [];
        return array_slice($themes, 0, $limit);
    }

    /**
     * @return array<int,array<string,mixed>>
     */
    public function publisher_authority(int $limit = 12): array
    {
        $projection = $this->intelligence_projection->current();
        $publishers = is_array($projection) ? (array) ($projection['publisher_authority'] ?? []) : [];
        return array_slice($publishers, 0, $limit);
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
