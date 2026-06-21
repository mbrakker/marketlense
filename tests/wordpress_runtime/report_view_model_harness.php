<?php
declare(strict_types=1);

namespace {
    define('ABSPATH', __DIR__ . '/');
    define('DAY_IN_SECONDS', 86400);

    final class WP_Post
    {
        public int $ID;
        public string $post_content;
        public string $post_excerpt;

        public function __construct(int $id, string $content, string $excerpt = '')
        {
            $this->ID = $id;
            $this->post_content = $content;
            $this->post_excerpt = $excerpt;
        }
    }

    final class WP_Term
    {
        public int $term_id;
        public string $name;
        public string $slug;

        public function __construct(int $term_id, string $name, string $slug)
        {
            $this->term_id = $term_id;
            $this->name = $name;
            $this->slug = $slug;
        }
    }

    $GLOBALS['ml_test_categories'] = [];
    $GLOBALS['ml_test_meta'] = [];
    $GLOBALS['ml_test_meta_registrations'] = [];
    $GLOBALS['ml_test_now'] = 1781308800;
    $GLOBALS['ml_test_post_timestamp'] = 1781222400;
    $GLOBALS['ml_test_attachment_urls'] = [];

    function wp_strip_all_tags(string $value): string
    {
        return strip_tags($value);
    }

    function sanitize_text_field(string $value): string
    {
        return trim((string) preg_replace('/\s+/u', ' ', $value));
    }

    function wp_trim_words(string $value, int $limit, string $more = '...'): string
    {
        $words = preg_split('/\s+/u', trim($value)) ?: [];
        return count($words) <= $limit
            ? implode(' ', $words)
            : implode(' ', array_slice($words, 0, $limit)) . $more;
    }

    function get_post_meta(int $post_id, string $key, bool $single): mixed
    {
        unset($post_id, $single);

        return $GLOBALS['ml_test_meta'][$key] ?? '';
    }

    function register_post_meta(string $post_type, string $key, array $args): bool
    {
        unset($post_type);
        $GLOBALS['ml_test_meta_registrations'][$key] = $args;

        return true;
    }

    function current_user_can(string $capability): bool
    {
        return $capability === 'edit_posts';
    }

    function get_the_terms(int|WP_Post $post, string $taxonomy): array|false
    {
        if ($taxonomy === 'category') {
            return $GLOBALS['ml_test_categories'];
        }
        return false;
    }

    function get_the_title(WP_Post $post): string
    {
        return 'Fixture report';
    }

    function get_permalink(WP_Post $post): string
    {
        return 'https://example.test/reports/fixture/';
    }

    function get_the_date(string $format, WP_Post $post): string
    {
        return 'June 12, 2026';
    }

    function get_post_timestamp(WP_Post $post, string $field): int
    {
        unset($post, $field);

        return (int) $GLOBALS['ml_test_post_timestamp'];
    }

    function current_time(string $type, bool $gmt = false): int
    {
        unset($type, $gmt);

        return (int) $GLOBALS['ml_test_now'];
    }

    function wp_get_attachment_image_url(int $attachment_id, string $size): string|false
    {
        unset($size);

        return $GLOBALS['ml_test_attachment_urls'][$attachment_id] ?? false;
    }
}

namespace MarketLense\Core {
    final class Post_Type
    {
        public const POST_TYPE = 'ml_report';
        public const SIGNAL_POST_TYPE = 'ml_signal';
        public const BRIEFING_POST_TYPE = 'ml_briefing';

        /**
         * @return list<string>
         */
        public static function report_post_types(): array
        {
            return [self::POST_TYPE, 'post'];
        }
    }

    final class Taxonomies
    {
        public const CATEGORY_TAXONOMY = 'category';
        public const PUBLISHER_TAXONOMY = 'ml_publisher';
    }
}

namespace {
    require dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-content-parser.php';
    require dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-meta.php';
    require dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php';

    $payload = json_decode(
        (string) stream_get_contents(STDIN),
        true,
        512,
        JSON_THROW_ON_ERROR
    );
    $GLOBALS['ml_test_meta'] = is_array($payload['meta'] ?? null) ? $payload['meta'] : [];
    $GLOBALS['ml_test_now'] = (int) ($payload['now'] ?? $GLOBALS['ml_test_now']);
    $GLOBALS['ml_test_post_timestamp'] = (int) ($payload['timestamp'] ?? $GLOBALS['ml_test_post_timestamp']);
    $GLOBALS['ml_test_attachment_urls'] = is_array($payload['attachment_urls'] ?? null)
        ? $payload['attachment_urls']
        : [];

    $meta = new MarketLense\Core\Meta(new MarketLense\Core\Content_Parser());
    $meta->register_meta_fields();
    if (($payload['mode'] ?? '') === 'meta_contract') {
        echo json_encode(
            [
                'registrations' => $GLOBALS['ml_test_meta_registrations'],
                'sanitized' => [
                    'insights' => MarketLense\Core\Meta::sanitize_card_insights($payload['insights'] ?? null),
                    'fingerprint' => MarketLense\Core\Meta::sanitize_cover_fingerprint($payload['fingerprint'] ?? null),
                    'media_id' => MarketLense\Core\Meta::sanitize_card_media_id($payload['media_id'] ?? null),
                ],
            ],
            JSON_THROW_ON_ERROR
        );
        exit;
    }
    $GLOBALS['ml_test_categories'] = array_map(
        static fn (array $term): WP_Term => new WP_Term(
            (int) $term['id'],
            (string) $term['name'],
            (string) $term['slug']
        ),
        $payload['categories'] ?? []
    );
    $post = new WP_Post(101, (string) ($payload['content'] ?? ''));
    $builder = new MarketLense\Core\Report_View_Model_Builder(
        new MarketLense\Core\Content_Parser()
    );
    $view_model = $builder->build($post);
    if (($payload['mode'] ?? '') === 'full') {
        echo json_encode($view_model, JSON_THROW_ON_ERROR);
        exit;
    }
    echo json_encode(
        [
            'insights_count' => $view_model['insights_count'],
            'quotes_count' => $view_model['quotes_count'],
            'topics_count' => $view_model['topics_count'],
            'citations_count' => $view_model['citations_count'],
        ],
        JSON_THROW_ON_ERROR
    );
}
