<?php
/**
 * Stores pipeline-approved intelligence projections and exposes their source entities.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Intelligence_Projection
{
    public const SCHEMA_VERSION = '1.0';

    public const PROJECTION_VERSION = 'wordpress_intelligence_projection.v1';

    private const OPTION_NAME = 'marketlense_intelligence_projection';

    /**
     * Registers the authenticated pipeline source and projection-write routes.
     */
    public function register(): void
    {
        add_action('rest_api_init', [$this, 'register_routes']);
    }

    public function register_routes(): void
    {
        register_rest_route(
            'marketlense/v1',
            '/intelligence-source',
            [
                'methods' => \WP_REST_Server::READABLE,
                'callback' => [$this, 'read_source'],
                'permission_callback' => static fn (): bool => current_user_can('edit_posts'),
            ]
        );
        register_rest_route(
            'marketlense/v1',
            '/intelligence-projection',
            [
                'methods' => \WP_REST_Server::CREATABLE,
                'callback' => [$this, 'write_projection'],
                'permission_callback' => static fn (): bool => current_user_can('manage_options'),
                'args' => [
                    'projection' => [
                        'required' => true,
                        'type' => 'object',
                        'validate_callback' => [$this, 'validate_projection'],
                    ],
                ],
            ]
        );
    }

    /**
     * Returns raw approved entity data. The Python pipeline owns all aggregation.
     */
    public function read_source(\WP_REST_Request $request): \WP_REST_Response
    {
        unset($request);
        return rest_ensure_response([
            'schema_version' => self::SCHEMA_VERSION,
            'entities' => $this->published_entities(),
        ]);
    }

    /**
     * Stores a validated pipeline projection without deriving facts from WordPress counts.
     */
    public function write_projection(\WP_REST_Request $request): \WP_REST_Response|\WP_Error
    {
        $projection = $request->get_param('projection');
        if (! is_array($projection) || ! $this->validate_projection($projection, $request, 'projection')) {
            return new \WP_Error(
                'marketlense_invalid_intelligence_projection',
                __('The intelligence projection does not match the approved schema.', 'marketlense-core'),
                ['status' => 400]
            );
        }

        $normalized = $this->normalize_projection($projection);
        update_option(self::OPTION_NAME, $normalized, false);

        return rest_ensure_response([
            'schema_version' => self::SCHEMA_VERSION,
            'projection_version' => self::PROJECTION_VERSION,
            'generated_at_utc' => $normalized['generated_at_utc'],
            'status' => 'stored',
        ]);
    }

    /**
     * Returns the latest valid pipeline projection, or null for a neutral public state.
     *
     * @return array<string,mixed>|null
     */
    public function current(): ?array
    {
        $projection = get_option(self::OPTION_NAME, null);
        if (! is_array($projection) || ! $this->validate_projection($projection, null, 'projection')) {
            return null;
        }

        return $projection;
    }

    /**
     * @param mixed $value
     */
    public function validate_projection($value, $request = null, $param = ''): bool
    {
        unset($request, $param);
        if (! is_array($value)) {
            return false;
        }
        if (($value['schema_version'] ?? '') !== self::SCHEMA_VERSION
            || ($value['projection_version'] ?? '') !== self::PROJECTION_VERSION
            || trim((string) ($value['generated_at_utc'] ?? '')) === '') {
            return false;
        }
        $metrics = $value['homepage_metrics'] ?? null;
        if (! is_array($metrics)) {
            return false;
        }
        foreach (['report_count', 'publisher_count', 'topic_count', 'briefing_count', 'signal_count', 'citation_count'] as $key) {
            if (! isset($metrics[$key]) || filter_var($metrics[$key], FILTER_VALIDATE_INT) === false || (int) $metrics[$key] < 0) {
                return false;
            }
        }
        foreach (['weekly_signals', 'strategic_themes', 'publisher_authority'] as $key) {
            if (! isset($value[$key]) || ! is_array($value[$key])) {
                return false;
            }
        }

        return true;
    }

    /**
     * @return list<array<string,mixed>>
     */
    private function published_entities(): array
    {
        $entities = [];
        foreach ([Post_Type::POST_TYPE, Post_Type::BRIEFING_POST_TYPE, Post_Type::SIGNAL_POST_TYPE] as $post_type) {
            $posts = get_posts([
                'post_type' => $post_type,
                'post_status' => 'publish',
                'posts_per_page' => -1,
                'orderby' => 'date',
                'order' => 'DESC',
                'no_found_rows' => true,
                'update_post_meta_cache' => false,
                'update_post_term_cache' => false,
            ]);
            foreach ($posts as $post) {
                if (! $post instanceof \WP_Post) {
                    continue;
                }
                $entities[] = [
                    'entity_id' => (string) $post->ID,
                    'entity_type' => $post_type,
                    'published_at_utc' => get_post_time('c', true, $post),
                    'url' => (string) get_permalink($post),
                    'publishers' => $this->term_source($post->ID, Taxonomies::PUBLISHER_TAXONOMY),
                    'topics' => $this->term_source($post->ID, Taxonomies::CATEGORY_TAXONOMY),
                ];
            }
        }

        return $entities;
    }

    /**
     * @return list<array{name:string,url:string,homepage:string}>
     */
    private function term_source(int $post_id, string $taxonomy): array
    {
        $terms = wp_get_object_terms($post_id, $taxonomy);
        if (is_wp_error($terms) || ! is_array($terms)) {
            return [];
        }
        $result = [];
        foreach ($terms as $term) {
            if (! $term instanceof \WP_Term) {
                continue;
            }
            $link = get_term_link($term);
            $result[] = [
                'name' => $term->name,
                'url' => is_wp_error($link) ? '' : (string) $link,
                'homepage' => $taxonomy === Taxonomies::PUBLISHER_TAXONOMY
                    ? (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_HOMEPAGE_META, true)
                    : '',
            ];
        }
        return $result;
    }

    /**
     * @param array<string,mixed> $projection
     * @return array<string,mixed>
     */
    private function normalize_projection(array $projection): array
    {
        $metrics = is_array($projection['homepage_metrics'] ?? null) ? $projection['homepage_metrics'] : [];
        return [
            'schema_version' => self::SCHEMA_VERSION,
            'projection_version' => self::PROJECTION_VERSION,
            'generated_at_utc' => sanitize_text_field((string) $projection['generated_at_utc']),
            'homepage_metrics' => [
                'report_count' => max(0, (int) ($metrics['report_count'] ?? 0)),
                'publisher_count' => max(0, (int) ($metrics['publisher_count'] ?? 0)),
                'topic_count' => max(0, (int) ($metrics['topic_count'] ?? 0)),
                'briefing_count' => max(0, (int) ($metrics['briefing_count'] ?? 0)),
                'signal_count' => max(0, (int) ($metrics['signal_count'] ?? 0)),
                'signal_label' => sanitize_text_field((string) ($metrics['signal_label'] ?? __('Published signals', 'marketlense-core'))),
                'citation_count' => max(0, (int) ($metrics['citation_count'] ?? 0)),
                'latest_label' => sanitize_text_field((string) ($metrics['latest_label'] ?? '')),
            ],
            'weekly_signals' => $this->normalize_weekly_signals($projection['weekly_signals']),
            'strategic_themes' => $this->normalize_term_items($projection['strategic_themes'], true),
            'publisher_authority' => $this->normalize_term_items($projection['publisher_authority'], false),
        ];
    }

    /** @param array<string,mixed> $value @return array<string,mixed> */
    private function normalize_weekly_signals(array $value): array
    {
        return [
            'window_label' => sanitize_text_field((string) ($value['window_label'] ?? '')),
            'trending_topics' => $this->normalize_term_items($value['trending_topics'] ?? [], true),
            'emerging_themes' => $this->normalize_term_items($value['emerging_themes'] ?? [], true),
            'top_publishers' => $this->normalize_term_items($value['top_publishers'] ?? [], false),
        ];
    }

    /** @param mixed $items @return list<array<string,mixed>> */
    private function normalize_term_items($items, bool $include_delta): array
    {
        if (! is_array($items)) {
            return [];
        }
        $normalized = [];
        foreach (array_slice($items, 0, 12) as $item) {
            if (! is_array($item)) {
                continue;
            }
            $name = sanitize_text_field((string) ($item['name'] ?? ''));
            if ($name === '') {
                continue;
            }
            $normalized_item = [
                'name' => $name,
                'count' => max(0, (int) ($item['count'] ?? 0)),
                'url' => esc_url_raw((string) ($item['url'] ?? ''), ['https', 'http']),
                'homepage' => esc_url_raw((string) ($item['homepage'] ?? ''), ['https', 'http']),
            ];
            if ($include_delta) {
                $delta = isset($item['delta']) && $item['delta'] !== null ? (int) $item['delta'] : null;
                $normalized_item['delta'] = $delta === 0 ? null : $delta;
            }
            $normalized[] = $normalized_item;
        }
        return $normalized;
    }
}
