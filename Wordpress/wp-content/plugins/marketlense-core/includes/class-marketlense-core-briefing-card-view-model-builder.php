<?php
/**
 * Validates WordPress briefing card presentation data.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Briefing_Card_View_Model_Builder
{
    /** @return array<string,mixed> */
    public function build(\WP_Post $post): array
    {
        $id = (int) $post->ID;
        $covers = [];
        foreach (['small', 'medium', 'large'] as $size) {
            $media_id = (int) get_post_meta($id, 'ml_briefing_card_cover_' . $size . '_id', true);
            $url = $media_id > 0 ? wp_get_attachment_image_url($media_id, 'full') : false;
            $covers[$size] = is_string($url) ? $url : '';
        }
        $takeaways = get_post_meta($id, 'ml_briefing_card_takeaways', true);
        $takeaways = is_array($takeaways) ? array_values(array_filter(array_map('sanitize_text_field', $takeaways))) : [];
        $timestamp = (int) get_post_timestamp($post, 'date');
        $age = current_time('timestamp', true) - $timestamp;
        $values = [
            'title' => sanitize_text_field(get_the_title($post)),
            'permalink' => (string) get_permalink($post),
            'date' => (string) get_the_date('F j, Y', $post),
            'summary_compact' => sanitize_text_field((string) get_post_meta($id, 'ml_briefing_card_summary_compact', true)),
            'summary_standard' => sanitize_text_field((string) get_post_meta($id, 'ml_briefing_card_summary_standard', true)),
            'decision_focus' => sanitize_text_field((string) get_post_meta($id, 'ml_briefing_card_decision_focus', true)),
        ];
        $errors = [];
        if ((string) get_post_meta($id, 'ml_briefing_card_schema_version', true) !== '1.0') { $errors[] = 'schema_version'; }
        foreach ($values as $key => $value) { if ($value === '') { $errors[] = $key; } }
        if (count($takeaways) !== 2) { $errors[] = 'takeaways'; }
        foreach ($covers as $size => $cover) { if ($cover === '') { $errors[] = 'cover_' . $size; } }
        $source_count = max(0, (int) get_post_meta($id, 'ml_briefing_source_count', true));
        $evidence_count = max(0, (int) get_post_meta($id, 'ml_briefing_evidence_count', true));
        if ($source_count < 1) { $errors[] = 'source_count'; }
        return array_merge($values, [
            'card_contract_valid' => $errors === [], 'card_contract_errors' => $errors,
            'covers' => $covers, 'takeaways' => $takeaways,
            'source_count' => $source_count, 'evidence_count' => $evidence_count,
            'is_new' => $age >= 0 && $age < 7 * DAY_IN_SECONDS,
        ]);
    }
}
