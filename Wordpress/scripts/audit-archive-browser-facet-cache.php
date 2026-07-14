<?php
/**
 * Isolated behavioral regression guard for archive facet query memoization.
 *
 * It supplies only the WordPress query boundary and executes the real private
 * method through reflection, proving equal facet arguments issue one query.
 */

declare(strict_types=1);

namespace {
    define('ABSPATH', __DIR__);

    function wp_json_encode(mixed $value): string|false
    {
        return json_encode($value);
    }

    final class WP_Query
    {
        public static int $calls = 0;
        /** @var list<int> */
        public array $posts;

        /** @param array<string,mixed> $args */
        public function __construct(array $args)
        {
            self::$calls++;
            $this->posts = [self::$calls];
        }
    }
}

namespace MarketLense\Core {
    final class Report_View_Model_Builder {}
    final class Report_Card_Renderer {}
    final class Briefing_Card_View_Model_Builder {}
    final class Briefing_Card_Renderer {}
    final class Signal_Card_View_Model_Builder {}
    final class Signal_Card_Renderer {}
    final class Meta
    {
        public const META_TIME_PERIOD = 'ml_time_period';
        public const META_REGION = 'ml_region';
        public const META_PUBLIC_INTELLIGENCE = 'ml_public_intelligence';
    }

    require dirname(__DIR__) . '/wp-content/plugins/marketlense-core/includes/class-marketlense-core-archive-browser.php';

    $browser = new Archive_Browser(
        new Report_View_Model_Builder(),
        new Report_Card_Renderer(),
        new Briefing_Card_View_Model_Builder(),
        new Briefing_Card_Renderer(),
        new Signal_Card_View_Model_Builder(),
        new Signal_Card_Renderer()
    );
    $method = new \ReflectionMethod($browser, 'facet_ids');
    $definition = [
        'slug' => 'briefing',
        'post_type' => 'ml_briefing',
        'schema_key' => 'ml_briefing_card_schema_version',
        'singular' => 'briefing',
        'plural' => 'briefings',
        'browser_label' => 'Briefing browser',
    ];
    $filters = [
        'topic' => '',
        'publisher' => '',
        'period' => '',
        'region' => '',
        'intelligence' => '',
        'search' => '',
    ];
    foreach (['topic', 'publisher', 'period', 'region', 'intelligence'] as $exclude) {
        $method->invoke($browser, $definition, $filters, $exclude);
    }
    if (\WP_Query::$calls !== 1) {
        fwrite(STDERR, "archive_browser_facet_cache_duplicate_query\n");
        exit(1);
    }
    $filters['search'] = 'retained evidence';
    $method->invoke($browser, $definition, $filters, 'topic');
    if (\WP_Query::$calls !== 2) {
        fwrite(STDERR, "archive_browser_facet_cache_key_collision\n");
        exit(1);
    }
    echo "archive_browser_facet_cache_ok\n";
}
