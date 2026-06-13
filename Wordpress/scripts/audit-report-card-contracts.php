<?php
/**
 * Read-only activation audit for published report-card contracts.
 *
 * Run with: wp eval-file Wordpress/scripts/audit-report-card-contracts.php
 */

if (! defined('ABSPATH')) {
    fwrite(STDERR, "WordPress must be loaded before running this audit.\n");
    exit(1);
}

$required_keys = [
    'ml_card_schema_version',
    'ml_card_title_scale',
    'ml_card_tldr_compact',
    'ml_card_tldr_standard',
    'ml_card_key_insights',
    'ml_card_geography_scope',
    'ml_card_cover_fingerprint',
    'ml_card_cover_small_id',
    'ml_card_cover_medium_id',
    'ml_card_cover_large_id',
];

$geometry_families = [
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

$post_types = class_exists(\MarketLense\Core\Post_Type::class)
    ? \MarketLense\Core\Post_Type::report_post_types()
    : ['ml_report'];
$post_ids = get_posts(
    [
        'post_type' => $post_types,
        'post_status' => 'publish',
        'fields' => 'ids',
        'posts_per_page' => -1,
        'orderby' => 'ID',
        'order' => 'ASC',
        'no_found_rows' => true,
        'meta_query' => [
            'relation' => 'OR',
            [
                'key' => 'ml_file_id',
                'compare' => 'EXISTS',
            ],
            [
                'key' => 'ml_is_digest',
                'value' => '1',
                'compare' => '=',
            ],
        ],
    ]
);

$invalid_count = 0;
foreach (is_array($post_ids) ? $post_ids : [] as $raw_post_id) {
    $post_id = (int) $raw_post_id;
    $post_title = get_the_title($post_id);
    $invalid_keys = [];
    foreach ($required_keys as $key) {
        if (! metadata_exists('post', $post_id, $key)) {
            $invalid_keys[] = $key;
        }
    }

    $schema_version = (string) get_post_meta($post_id, 'ml_card_schema_version', true);
    if ($schema_version !== '1.0') {
        $invalid_keys[] = 'ml_card_schema_version';
    }
    $title_scale = (string) get_post_meta($post_id, 'ml_card_title_scale', true);
    if (! in_array($title_scale, ['short', 'medium', 'long', 'xlong'], true)) {
        $invalid_keys[] = 'ml_card_title_scale';
    }
    foreach (['ml_card_tldr_compact', 'ml_card_tldr_standard'] as $key) {
        if (trim((string) get_post_meta($post_id, $key, true)) === '') {
            $invalid_keys[] = $key;
        }
    }
    $insights = get_post_meta($post_id, 'ml_card_key_insights', true);
    if (
        ! is_array($insights)
        || count($insights) !== 2
        || count(array_filter($insights, static fn ($value): bool => is_string($value) && trim($value) !== '')) !== 2
    ) {
        $invalid_keys[] = 'ml_card_key_insights';
    }
    $geography_scope = (string) get_post_meta($post_id, 'ml_card_geography_scope', true);
    if (! in_array($geography_scope, ['global', 'regional', 'country', 'unknown'], true)) {
        $invalid_keys[] = 'ml_card_geography_scope';
    }
    $fingerprint = get_post_meta($post_id, 'ml_card_cover_fingerprint', true);
    if (
        ! is_array($fingerprint)
        || ! in_array((string) ($fingerprint['geometry_family'] ?? ''), $geometry_families, true)
        || ! is_int($fingerprint['seed'] ?? null)
        || (int) $fingerprint['seed'] < 0
    ) {
        $invalid_keys[] = 'ml_card_cover_fingerprint';
    }
    foreach (
        [
            'ml_card_cover_small_id',
            'ml_card_cover_medium_id',
            'ml_card_cover_large_id',
        ] as $key
    ) {
        $media_id = (int) get_post_meta($post_id, $key, true);
        if ($media_id < 1 || ! wp_attachment_is_image($media_id)) {
            $invalid_keys[] = $key;
        }
    }

    $invalid_keys = array_values(array_unique($invalid_keys));
    sort($invalid_keys, SORT_STRING);
    if ($invalid_keys === []) {
        continue;
    }
    ++$invalid_count;
    echo wp_json_encode(
        [
            'status' => 'invalid',
            'post_id' => $post_id,
            'post_title' => $post_title,
            'invalid_keys' => $invalid_keys,
        ],
        JSON_UNESCAPED_SLASHES
    ) . PHP_EOL;
}

if ($invalid_count > 0) {
    echo wp_json_encode(
        [
            'status' => 'failed',
            'invalid_count' => $invalid_count,
            'message' => $invalid_count . ' invalid published reports',
        ],
        JSON_UNESCAPED_SLASHES
    ) . PHP_EOL;
    exit(1);
}

echo wp_json_encode(
    [
        'status' => 'passed',
        'invalid_count' => 0,
        'message' => '0 invalid published reports',
    ],
    JSON_UNESCAPED_SLASHES
) . PHP_EOL;
