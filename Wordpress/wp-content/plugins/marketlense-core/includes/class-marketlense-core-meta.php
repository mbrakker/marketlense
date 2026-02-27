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
    public const META_FILE_ID = 'ml_file_id';

    public const META_PUBLISHER = 'ml_publisher_name';

    public const META_TIME_PERIOD = 'ml_time_period';

    public const META_REGION = 'ml_region';

    private Content_Parser $parser;

    public function __construct(Content_Parser $parser)
    {
        $this->parser = $parser;
    }

    public function register_meta_fields(): void
    {
        $keys = [
            self::META_FILE_ID,
            self::META_PUBLISHER,
            self::META_TIME_PERIOD,
            self::META_REGION,
        ];

        foreach ($keys as $key) {
            register_post_meta(
                Post_Type::POST_TYPE,
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

        if ($post->post_type !== Post_Type::POST_TYPE) {
            return;
        }

        $content = (string) $post->post_content;

        $file_id = $this->parser->extract_file_id($content);
        $publisher = $this->parser->extract_metadata_value($content, 'Publisher');
        $time_period = $this->parser->extract_metadata_value($content, 'Time period');
        $region = $this->parser->extract_metadata_value($content, 'Region');

        if ($publisher === '') {
            $publisher = $this->resolve_existing_publisher($post_id);
        }

        $this->upsert_string_meta($post_id, self::META_FILE_ID, $file_id);
        $this->upsert_string_meta($post_id, self::META_PUBLISHER, $publisher);
        $this->upsert_string_meta($post_id, self::META_TIME_PERIOD, $time_period);
        $this->upsert_string_meta($post_id, self::META_REGION, $region);

        if ($publisher !== '') {
            wp_set_object_terms($post_id, [$publisher], Taxonomies::PUBLISHER_TAXONOMY, false);
        }

        $topic_names = $this->collect_topic_names($post_id);
        if (! empty($topic_names)) {
            wp_set_object_terms($post_id, $topic_names, Taxonomies::TOPIC_TAXONOMY, false);
        }
    }

    private function collect_topic_names(int $post_id): array
    {
        $existing = wp_get_post_terms($post_id, Taxonomies::TOPIC_TAXONOMY, ['fields' => 'names']);
        $tags = wp_get_post_terms($post_id, 'post_tag', ['fields' => 'names']);
        $categories = wp_get_post_terms($post_id, Taxonomies::CATEGORY_TAXONOMY, ['fields' => 'names']);

        if (is_wp_error($existing)) {
            $existing = [];
        }
        if (is_wp_error($tags)) {
            $tags = [];
        }
        if (is_wp_error($categories)) {
            $categories = [];
        }

        $merged = array_unique(
            array_filter(
                array_map(
                    static fn (string $value): string => sanitize_text_field(trim($value)),
                    array_merge($existing, $tags, $categories)
                )
            )
        );

        return array_values($merged);
    }

    private function resolve_existing_publisher(int $post_id): string
    {
        $existing = wp_get_post_terms($post_id, Taxonomies::PUBLISHER_TAXONOMY, ['fields' => 'names']);
        if (is_wp_error($existing) || empty($existing)) {
            return '';
        }

        return sanitize_text_field(trim((string) $existing[0]));
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
