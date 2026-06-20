<?php
/**
 * Validates WordPress signal card presentation data.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Signal_Card_View_Model_Builder
{
    /** @return array<string,mixed> */
    public function build(\WP_Post $post): array
    {
        $id = (int) $post->ID;
        $covers = [];
        foreach (['small', 'medium', 'large'] as $size) {
            $media_id = (int) get_post_meta($id, 'ml_signal_card_cover_' . $size . '_id', true);
            $url = $media_id > 0 ? wp_get_attachment_image_url($media_id, 'full') : false;
            $covers[$size] = is_string($url) ? $url : '';
        }
        $terms = get_the_terms($post, Taxonomies::CATEGORY_TAXONOMY);
        $topics = is_array($terms)
            ? array_values(array_filter(array_map(static fn (\WP_Term $term): string => sanitize_text_field($term->name), $terms)))
            : [];
        $timestamp = (int) get_post_timestamp($post, 'date');
        $age = current_time('timestamp', true) - $timestamp;
        $values = [
            'title' => sanitize_text_field(get_the_title($post)),
            'permalink' => (string) get_permalink($post),
            'date' => (string) get_the_date('F j, Y', $post),
            'summary' => sanitize_text_field((string) get_post_meta($id, 'ml_signal_card_summary', true)),
            'uncertainty' => sanitize_text_field((string) get_post_meta($id, 'ml_signal_card_uncertainty', true)),
        ];
        $confidence = (float) get_post_meta($id, 'ml_signal_card_confidence', true);
        $source_count = max(0, (int) get_post_meta($id, 'ml_signal_source_count', true));
        $evidence_count = max(0, (int) get_post_meta($id, 'ml_signal_evidence_count', true));
        $errors = [];
        if ((string) get_post_meta($id, 'ml_signal_card_schema_version', true) !== '1.0') { $errors[] = 'schema_version'; }
        foreach ($values as $key => $value) { if ($value === '') { $errors[] = $key; } }
        if ($confidence < 0 || $confidence > 1) { $errors[] = 'confidence'; }
        if ($source_count < 1) { $errors[] = 'source_count'; }
        if ($evidence_count < 1) { $errors[] = 'evidence_count'; }
        if ($topics === []) { $errors[] = 'topics'; }
        foreach ($covers as $size => $cover) { if ($cover === '') { $errors[] = 'cover_' . $size; } }
        return array_merge($values, [
            'card_contract_valid' => $errors === [], 'card_contract_errors' => $errors,
            'covers' => $covers, 'topics' => $topics, 'confidence' => $confidence,
            'source_count' => $source_count, 'evidence_count' => $evidence_count,
            'is_new' => $age >= 0 && $age < 7 * DAY_IN_SECONDS,
        ]);
    }
}
