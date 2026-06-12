<?php
declare(strict_types=1);

namespace {
    define('ABSPATH', __DIR__ . '/');

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

    function get_post_meta(int $post_id, string $key, bool $single): string
    {
        return '';
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
        return 1781222400;
    }
}

namespace MarketLense\Core {
    final class Meta
    {
        public const META_PUBLISHER = 'ml_publisher_name';
        public const META_TIME_PERIOD = 'ml_time_period';
        public const META_REGION = 'ml_region';
    }

    final class Taxonomies
    {
        public const CATEGORY_TAXONOMY = 'category';
        public const PUBLISHER_TAXONOMY = 'ml_publisher';
    }
}

namespace {
    require dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-content-parser.php';
    require dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php';

    $payload = json_decode(
        (string) stream_get_contents(STDIN),
        true,
        512,
        JSON_THROW_ON_ERROR
    );
    $GLOBALS['ml_test_categories'] = array_map(
        static fn (array $term): WP_Term => new WP_Term(
            (int) $term['id'],
            (string) $term['name'],
            (string) $term['slug']
        ),
        $payload['categories'] ?? []
    );
    $post = new WP_Post(101, (string) $payload['content']);
    $builder = new MarketLense\Core\Report_View_Model_Builder(
        new MarketLense\Core\Content_Parser()
    );
    $view_model = $builder->build($post);
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
