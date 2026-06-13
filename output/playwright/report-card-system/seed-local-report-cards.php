<?php

if (! defined('ABSPATH')) {
    exit(1);
}

require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/image.php';

$manifest_paths = array_values(
    array_filter(
        array_map('trim', explode(';', (string) getenv('ML_CARD_MANIFESTS')))
    )
);
if (count($manifest_paths) < 3) {
    fwrite(STDERR, "Expected at least three manifest paths.\n");
    exit(1);
}

/**
 * @param array<string,mixed> $asset
 */
function ml_import_fixture_cover(string $manifest_path, array $asset, int $post_id): int
{
    $output_path = (string) ($asset['output_path'] ?? '');
    $source = preg_match('/^[A-Za-z]:[\\\\\/]/', $output_path) === 1
        ? $output_path
        : rtrim((string) getenv('ML_REPO_ROOT'), '\\/') . DIRECTORY_SEPARATOR . $output_path;
    if (! is_file($source)) {
        throw new RuntimeException('Missing cover asset: ' . $source);
    }

    $temporary = wp_tempnam(basename($source));
    if (! is_string($temporary) || ! copy($source, $temporary)) {
        throw new RuntimeException('Could not stage cover asset: ' . $source);
    }

    $attachment_id = media_handle_sideload(
        [
            'name' => basename($source),
            'tmp_name' => $temporary,
        ],
        $post_id,
        ''
    );
    if (is_wp_error($attachment_id)) {
        throw new RuntimeException($attachment_id->get_error_message());
    }

    return (int) $attachment_id;
}

foreach (array_slice($manifest_paths, 0, 3) as $index => $manifest_path) {
    $payload = json_decode(
        (string) file_get_contents($manifest_path),
        true,
        512,
        JSON_THROW_ON_ERROR
    );
    $fixture_key = 'report-card-browser-' . $index;
    $existing = get_posts(
        [
            'post_type' => 'ml_report',
            'post_status' => 'any',
            'meta_key' => '_ml_local_fixture_key',
            'meta_value' => $fixture_key,
            'fields' => 'ids',
            'posts_per_page' => 1,
        ]
    );
    $post_date = $index === 1
        ? gmdate('Y-m-d H:i:s', time() - 8 * DAY_IN_SECONDS)
        : gmdate('Y-m-d H:i:s', time() - $index * HOUR_IN_SECONDS);
    $post_id = wp_insert_post(
        [
            'ID' => isset($existing[0]) ? (int) $existing[0] : 0,
            'post_type' => 'ml_report',
            'post_status' => 'publish',
            'post_title' => (string) $payload['title'],
            'post_date' => $post_date,
            'post_date_gmt' => $post_date,
            'post_excerpt' => (string) $payload['tldr_standard'],
            'post_content' => sprintf(
                '<section id="section-summary"><p class="summary-copy">%s</p></section>',
                esc_html((string) $payload['tldr_standard'])
            ),
        ],
        true
    );
    if (is_wp_error($post_id)) {
        throw new RuntimeException($post_id->get_error_message());
    }
    $post_id = (int) $post_id;

    $cover_ids = [];
    foreach (['small', 'medium', 'large'] as $size) {
        $cover_ids[$size] = ml_import_fixture_cover(
            $manifest_path,
            (array) $payload['covers'][$size],
            $post_id
        );
    }

    update_post_meta($post_id, '_ml_local_fixture_key', $fixture_key);
    update_post_meta($post_id, 'ml_file_id', $fixture_key);
    update_post_meta($post_id, 'ml_publisher_name', (string) $payload['publisher']);
    update_post_meta($post_id, 'ml_time_period', (string) $payload['covered_period']);
    update_post_meta($post_id, 'ml_region', (string) $payload['geography_label']);
    update_post_meta($post_id, 'ml_card_schema_version', (string) $payload['schema_version']);
    update_post_meta($post_id, 'ml_card_title_scale', (string) $payload['title_scale']);
    update_post_meta($post_id, 'ml_card_tldr_compact', (string) $payload['tldr_compact']);
    update_post_meta($post_id, 'ml_card_tldr_standard', (string) $payload['tldr_standard']);
    update_post_meta($post_id, 'ml_card_key_insights', (array) $payload['key_insights']);
    update_post_meta($post_id, 'ml_card_geography_scope', (string) $payload['geography_scope']);
    update_post_meta($post_id, 'ml_card_cover_fingerprint', (array) $payload['fingerprint']);
    update_post_meta($post_id, 'ml_card_cover_small_id', $cover_ids['small']);
    update_post_meta($post_id, 'ml_card_cover_medium_id', $cover_ids['medium']);
    update_post_meta($post_id, 'ml_card_cover_large_id', $cover_ids['large']);
    wp_set_object_terms($post_id, ['Technology & Media'], 'category');
    wp_set_object_terms($post_id, [(string) $payload['publisher']], 'ml_publisher');

    fwrite(STDOUT, sprintf("SEEDED post_id=%d title=%s\n", $post_id, (string) $payload['title']));
}
