<?php
/**
 * Metadata and taxonomy synchronization.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Meta
{
    private const PROJECTION_BACKFILL_OPTION = 'marketlense_core_projection_backfill_version';

    private const PROJECTION_BACKFILL_VERSION = '2026-03-10-core-post-digest-contract';

    public const META_FILE_ID = 'ml_file_id';

    public const META_DIGEST_FLAG = 'ml_is_digest';

    public const META_PUBLISHER = 'ml_publisher_name';

    public const META_TIME_PERIOD = 'ml_time_period';

    public const META_REGION = 'ml_region';

    public const META_PUBLIC_INTELLIGENCE = 'ml_public_intelligence';

    public const META_CARD_SCHEMA_VERSION = 'ml_card_schema_version';

    public const META_CARD_TITLE_SCALE = 'ml_card_title_scale';

    public const META_CARD_TLDR_COMPACT = 'ml_card_tldr_compact';

    public const META_CARD_TLDR_STANDARD = 'ml_card_tldr_standard';

    public const META_CARD_KEY_INSIGHTS = 'ml_card_key_insights';

    public const META_CARD_GEOGRAPHY_SCOPE = 'ml_card_geography_scope';

    public const META_CARD_COVER_FINGERPRINT = 'ml_card_cover_fingerprint';

    public const META_CARD_COVER_SMALL_ID = 'ml_card_cover_small_id';

    public const META_CARD_COVER_MEDIUM_ID = 'ml_card_cover_medium_id';

    public const META_CARD_COVER_LARGE_ID = 'ml_card_cover_large_id';

    private Content_Parser $parser;

    public function __construct(Content_Parser $parser)
    {
        $this->parser = $parser;
    }

    public function register_meta_fields(): void
    {
        $keys = [
            self::META_FILE_ID,
            self::META_DIGEST_FLAG,
            self::META_PUBLISHER,
            self::META_TIME_PERIOD,
            self::META_REGION,
            self::META_PUBLIC_INTELLIGENCE,
        ];

        foreach (Post_Type::report_post_types() as $post_type) {
            foreach ($keys as $key) {
                register_post_meta(
                    $post_type,
                    $key,
                    [
                        'single'            => true,
                        'type'              => 'string',
                        'show_in_rest'      => true,
                        'sanitize_callback' => 'sanitize_text_field',
                        'auth_callback'     => static function (): bool {
                            return current_user_can('edit_posts');
                        },
                    ]
                );
            }

            foreach (
                [
                    self::META_CARD_SCHEMA_VERSION,
                    self::META_CARD_TITLE_SCALE,
                    self::META_CARD_TLDR_COMPACT,
                    self::META_CARD_TLDR_STANDARD,
                    self::META_CARD_GEOGRAPHY_SCOPE,
                ] as $key
            ) {
                register_post_meta(
                    $post_type,
                    $key,
                    [
                        'single' => true,
                        'type' => 'string',
                        'show_in_rest' => true,
                        'sanitize_callback' => 'sanitize_text_field',
                        'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
                    ]
                );
            }

            register_post_meta(
                $post_type,
                self::META_CARD_KEY_INSIGHTS,
                [
                    'single' => true,
                    'type' => 'array',
                    'show_in_rest' => [
                        'schema' => [
                            'type' => 'array',
                            'minItems' => 2,
                            'maxItems' => 2,
                            'items' => ['type' => 'string'],
                        ],
                    ],
                    'sanitize_callback' => [self::class, 'sanitize_card_insights'],
                    'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
                ]
            );

            register_post_meta(
                $post_type,
                self::META_CARD_COVER_FINGERPRINT,
                [
                    'single' => true,
                    'type' => 'object',
                    'show_in_rest' => [
                        'schema' => [
                            'type' => 'object',
                            'required' => ['geometry_family', 'seed'],
                            'properties' => [
                                'geometry_family' => ['type' => 'string'],
                                'seed' => ['type' => 'integer'],
                            ],
                            'additionalProperties' => true,
                        ],
                    ],
                    'sanitize_callback' => [self::class, 'sanitize_cover_fingerprint'],
                    'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
                ]
            );

            foreach (
                [
                    self::META_CARD_COVER_SMALL_ID,
                    self::META_CARD_COVER_MEDIUM_ID,
                    self::META_CARD_COVER_LARGE_ID,
                ] as $key
            ) {
                register_post_meta(
                    $post_type,
                    $key,
                    [
                        'single' => true,
                        'type' => 'integer',
                        'show_in_rest' => [
                            'schema' => [
                                'type' => 'integer',
                                'minimum' => 1,
                            ],
                        ],
                        'sanitize_callback' => [self::class, 'sanitize_card_media_id'],
                        'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
                    ]
                );
            }
        }

        foreach (['ml_briefing_card_schema_version', 'ml_briefing_card_summary_compact', 'ml_briefing_card_summary_standard', 'ml_briefing_card_decision_focus'] as $key) {
            register_post_meta(Post_Type::BRIEFING_POST_TYPE, $key, [
                'single' => true, 'type' => 'string', 'show_in_rest' => true,
                'sanitize_callback' => 'sanitize_text_field',
                'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
            ]);
        }
        foreach (['ml_briefing_source_count', 'ml_briefing_evidence_count', 'ml_briefing_card_cover_small_id', 'ml_briefing_card_cover_medium_id', 'ml_briefing_card_cover_large_id'] as $key) {
            register_post_meta(Post_Type::BRIEFING_POST_TYPE, $key, [
                'single' => true, 'type' => 'integer', 'show_in_rest' => true,
                'sanitize_callback' => [self::class, 'sanitize_card_media_id'],
                'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
            ]);
        }
        register_post_meta(Post_Type::BRIEFING_POST_TYPE, 'ml_briefing_card_takeaways', [
            'single' => true, 'type' => 'array', 'show_in_rest' => ['schema' => ['type' => 'array', 'minItems' => 2, 'maxItems' => 2, 'items' => ['type' => 'string']]],
            'sanitize_callback' => [self::class, 'sanitize_card_insights'],
            'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
        ]);

        foreach (['ml_signal_card_schema_version', 'ml_signal_card_summary', 'ml_signal_card_uncertainty'] as $key) {
            register_post_meta(Post_Type::SIGNAL_POST_TYPE, $key, [
                'single' => true, 'type' => 'string', 'show_in_rest' => true,
                'sanitize_callback' => 'sanitize_text_field',
                'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
            ]);
        }
        register_post_meta(Post_Type::SIGNAL_POST_TYPE, 'ml_signal_card_confidence', [
            'single' => true, 'type' => 'number', 'show_in_rest' => true,
            'sanitize_callback' => static fn (mixed $value): float => max(0.0, min(1.0, (float) $value)),
            'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
        ]);
        foreach (['ml_signal_source_count', 'ml_signal_evidence_count', 'ml_signal_card_cover_small_id', 'ml_signal_card_cover_medium_id', 'ml_signal_card_cover_large_id'] as $key) {
            register_post_meta(Post_Type::SIGNAL_POST_TYPE, $key, [
                'single' => true, 'type' => 'integer', 'show_in_rest' => true,
                'sanitize_callback' => [self::class, 'sanitize_card_media_id'],
                'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
            ]);
        }
    }

    /**
     * @param mixed $value Raw REST meta value.
     * @return list<string>
     */
    public static function sanitize_card_insights(mixed $value): array
    {
        if (! is_array($value) || count($value) !== 2) {
            return [];
        }

        $sanitized = [];
        foreach (array_values($value) as $insight) {
            if (! is_string($insight)) {
                return [];
            }
            $text = sanitize_text_field($insight);
            if ($text === '') {
                return [];
            }
            $sanitized[] = $text;
        }

        return $sanitized;
    }

    /**
     * @param mixed $value Raw REST meta value.
     * @return array{geometry_family:string,seed:int}|array{}
     */
    public static function sanitize_cover_fingerprint(mixed $value): array
    {
        if (is_string($value)) {
            $decoded = json_decode($value, true);
            $value = is_array($decoded) ? $decoded : [];
        }
        if (! is_array($value)) {
            return [];
        }

        $geometry_family = sanitize_text_field((string) ($value['geometry_family'] ?? ''));
        $allowed_families = [
            'ascending_trajectory',
            'descending_trajectory',
            'volatility_corridor',
            'convergence_funnel',
            'divergence_fan',
            'parallel_bands',
            'ranked_strata',
            'distribution_field',
            'concentration_core',
            'flow_channels',
            'network_constellation',
            'hierarchy_terraces',
            'cycle_orbit',
            'forecast_horizon',
            'uncertainty_envelope',
            'system_matrix',
        ];
        $seed = filter_var($value['seed'] ?? null, FILTER_VALIDATE_INT);
        if (! in_array($geometry_family, $allowed_families, true) || $seed === false || $seed < 0) {
            return [];
        }

        return [
            'geometry_family' => $geometry_family,
            'seed' => (int) $seed,
        ];
    }

    /**
     * @param mixed $value Raw REST meta value.
     */
    public static function sanitize_card_media_id(mixed $value): int
    {
        $media_id = filter_var($value, FILTER_VALIDATE_INT);

        return $media_id !== false && $media_id > 0 ? (int) $media_id : 0;
    }

    /**
     * @param array<string,mixed> $query_args
     * @return array<string,mixed>
     */
    public static function apply_digest_query_constraints(array $query_args): array
    {
        $query_args['post_type'] = Post_Type::report_post_types();
        $digest_contract_query = [
            'relation' => 'OR',
            [
                'key' => self::META_FILE_ID,
                'compare' => 'EXISTS',
            ],
            [
                'key' => self::META_DIGEST_FLAG,
                'value' => '1',
                'compare' => '=',
            ],
        ];

        $meta_query = $query_args['meta_query'] ?? [];
        if (! is_array($meta_query) || $meta_query === []) {
            $query_args['meta_query'] = $digest_contract_query;
            return $query_args;
        }

        $query_args['meta_query'] = [
            'relation' => 'AND',
            $meta_query,
            $digest_contract_query,
        ];

        return $query_args;
    }

    /**
     * Limits report-card listings to posts migrated to the canonical card contract.
     *
     * @param array<string,mixed> $query_args
     * @return array<string,mixed>
     */
    public static function apply_report_card_query_constraints(array $query_args): array
    {
        $query_args = self::apply_digest_query_constraints($query_args);
        $card_contract_query = [
            'key' => self::META_CARD_SCHEMA_VERSION,
            'value' => '1.0',
            'compare' => '=',
        ];
        $meta_query = $query_args['meta_query'] ?? [];
        $query_args['meta_query'] = [
            'relation' => 'AND',
            $meta_query,
            $card_contract_query,
        ];

        return $query_args;
    }

    /**
     * Backfills metadata and publisher term projections for legacy reports.
     */
    public function backfill_report_contracts(): void
    {
        $completed_version = (string) get_option(self::PROJECTION_BACKFILL_OPTION, '');
        if ($completed_version === self::PROJECTION_BACKFILL_VERSION) {
            return;
        }

        $post_ids = get_posts(
            [
                'post_type' => Post_Type::report_post_types(),
                'post_status' => 'publish',
                'fields' => 'ids',
                'posts_per_page' => -1,
                'no_found_rows' => true,
                'update_post_meta_cache' => false,
                'update_post_term_cache' => false,
            ]
        );

        if (is_array($post_ids)) {
            foreach ($post_ids as $post_id) {
                $normalized_post_id = (int) $post_id;
                if ($normalized_post_id < 1 || ! $this->needs_contract_sync($normalized_post_id)) {
                    continue;
                }

                $post = get_post($normalized_post_id);
                if ($post instanceof \WP_Post) {
                    $this->sync_report_contract($normalized_post_id, $post, true);
                }
            }
        }

        update_option(self::PROJECTION_BACKFILL_OPTION, self::PROJECTION_BACKFILL_VERSION, false);
    }

    /**
     * Synchronize core metadata contract and taxonomy projections from report content.
     *
     * @param int      $post_id Post identifier.
     * @param \WP_Post $post    Post object.
     * @param bool     $update  Update flag provided by WordPress.
     */
    public function sync_report_contract(int $post_id, \WP_Post $post, bool $update): void
    {
        unset($update);

        if (wp_is_post_autosave($post_id) || wp_is_post_revision($post_id)) {
            return;
        }

        $content = (string) $post->post_content;

        if (! $this->should_sync_report_post($post_id, $post, $content)) {
            return;
        }

        $file_id = $this->parser->extract_file_id($content);
        $publisher = $this->parser->extract_metadata_value($content, 'Publisher');
        $time_period = $this->parser->extract_metadata_value($content, 'Time period');
        $region = $this->extract_region_value($content);
        $has_public_intelligence = $this->content_has_public_intelligence($content) ? '1' : '0';

        if ($publisher === '') {
            $publisher = $this->resolve_existing_publisher($post_id);
        }

        $this->upsert_string_meta($post_id, self::META_FILE_ID, $file_id);
        $this->upsert_string_meta($post_id, self::META_DIGEST_FLAG, '1');
        $this->upsert_string_meta($post_id, self::META_PUBLISHER, $publisher);
        $this->upsert_string_meta($post_id, self::META_TIME_PERIOD, $time_period);
        $this->upsert_string_meta($post_id, self::META_REGION, $region);
        $this->upsert_string_meta($post_id, self::META_PUBLIC_INTELLIGENCE, $has_public_intelligence);

        if ($publisher !== '') {
            wp_set_object_terms($post_id, [$publisher], Taxonomies::PUBLISHER_TAXONOMY, false);
        }
    }

    private function resolve_existing_publisher(int $post_id): string
    {
        $existing = wp_get_post_terms($post_id, Taxonomies::PUBLISHER_TAXONOMY, ['fields' => 'names']);
        if (is_wp_error($existing) || empty($existing)) {
            return '';
        }

        return sanitize_text_field(trim((string) $existing[0]));
    }

    private function content_has_public_intelligence(string $content): bool
    {
        return str_contains($content, 'report-intelligence-panel')
            || str_contains($content, 'id="report-intelligence"')
            || str_contains($content, "id='report-intelligence'");
    }

    private function should_sync_report_post(int $post_id, \WP_Post $post, string $content): bool
    {
        if (! Post_Type::is_report_post_type($post->post_type)) {
            return false;
        }

        if ($post->post_type === Post_Type::POST_TYPE) {
            return true;
        }

        if ($this->parser->extract_file_id($content) !== '') {
            return true;
        }

        if ($this->has_digest_flag($post_id) || $this->has_digest_content_signature($content)) {
            return true;
        }

        foreach ([self::META_FILE_ID, self::META_PUBLISHER, self::META_TIME_PERIOD, self::META_REGION] as $meta_key) {
            if (trim((string) get_post_meta($post_id, $meta_key, true)) !== '') {
                return true;
            }
        }

        $publisher_terms = wp_get_post_terms($post_id, Taxonomies::PUBLISHER_TAXONOMY, ['fields' => 'ids']);

        return ! is_wp_error($publisher_terms) && $publisher_terms !== [];
    }

    private function needs_contract_sync(int $post_id): bool
    {
        if (! $this->has_digest_flag($post_id)) {
            return true;
        }

        $publisher = trim((string) get_post_meta($post_id, self::META_PUBLISHER, true));
        if ($publisher === '') {
            return true;
        }

        $publisher_terms = wp_get_post_terms($post_id, Taxonomies::PUBLISHER_TAXONOMY, ['fields' => 'ids']);
        if (is_wp_error($publisher_terms) || $publisher_terms === []) {
            return true;
        }

        return false;
    }

    private function extract_region_value(string $content): string
    {
        $region = $this->parser->extract_metadata_value($content, 'Region');
        if ($region !== '') {
            return $region;
        }

        return $this->parser->extract_metadata_value($content, 'Geography');
    }

    private function has_digest_flag(int $post_id): bool
    {
        return trim((string) get_post_meta($post_id, self::META_DIGEST_FLAG, true)) === '1';
    }

    private function has_digest_content_signature(string $content): bool
    {
        $publisher = $this->parser->extract_metadata_value($content, 'Publisher');
        $time_period = $this->parser->extract_metadata_value($content, 'Time period');
        $region = $this->extract_region_value($content);
        $normalized_content = strtolower($content);
        $has_digest_shell = str_contains($normalized_content, 'market lense report digest')
            || str_contains($normalized_content, 'class="page-shell"')
            || str_contains($normalized_content, "class='page-shell'")
            || str_contains($normalized_content, 'class="report"')
            || str_contains($normalized_content, "class='report'");

        if ($publisher !== '' && ($time_period !== '' || $region !== '')) {
            return true;
        }

        return $publisher !== '' && $has_digest_shell;
    }

    private function upsert_string_meta(int $post_id, string $meta_key, string $meta_value): void
    {
        if ($meta_value === '') {
            delete_post_meta($post_id, $meta_key);
            return;
        }

        update_post_meta($post_id, $meta_key, $meta_value);
    }
}
