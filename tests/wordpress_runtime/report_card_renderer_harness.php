<?php
declare(strict_types=1);

namespace {
    define('ABSPATH', __DIR__ . '/');

    $GLOBALS['ml_test_boundary_events'] = [];
    $GLOBALS['ml_test_boundary_status'] = null;

    function is_admin(): bool
    {
        return false;
    }

    function wp_generate_uuid4(): string
    {
        return '123e4567-e89b-42d3-a456-426614174000';
    }

    function wp_json_encode(mixed $value): string
    {
        return (string) json_encode($value, JSON_THROW_ON_ERROR);
    }

    function status_header(int $status): void
    {
        $GLOBALS['ml_test_boundary_status'] = $status;
    }

    function nocache_headers(): void
    {
    }

    function get_queried_object(): null
    {
        return null;
    }

    function sanitize_key(string $value): string
    {
        return strtolower((string) preg_replace('/[^a-z0-9_-]/i', '', $value));
    }

    function do_action(string $hook, array $event): void
    {
        if ($hook === 'marketlense_public_render_failure') {
            $GLOBALS['ml_test_boundary_events'][] = $event;
        }
    }

    function esc_attr(string $value): string
    {
        return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    }

    function esc_html(string $value): string
    {
        return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
    }

    function esc_url(string $value): string
    {
        return esc_attr($value);
    }

    function esc_html__(string $value, string $domain): string
    {
        unset($domain);

        return $value;
    }
}

namespace {
    require dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-public-render-boundary.php';
    require dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-card-renderer.php';

    $payload = json_decode(
        (string) stream_get_contents(STDIN),
        true,
        512,
        JSON_THROW_ON_ERROR
    );

    if (($payload['mode'] ?? '') === 'public_boundary') {
        $_SERVER['REQUEST_URI'] = (string) ($payload['route'] ?? '/publisher/not-extracted/');
        $boundary = new MarketLense\Core\Public_Render_Boundary();
        $html = $boundary->render_shortcode(
            (string) ($payload['shortcode'] ?? 'ml_report_browser'),
            static function () use ($payload): string {
                if (($payload['throw'] ?? false) === true) {
                    throw new RuntimeException(
                        (string) ($payload['message'] ?? 'C:\\private\\plugin.php on line 99')
                    );
                }

                return (string) ($payload['html'] ?? '');
            }
        );
        echo json_encode(
            [
                'html' => $html,
                'status' => $GLOBALS['ml_test_boundary_status'],
                'events' => $GLOBALS['ml_test_boundary_events'],
            ],
            JSON_THROW_ON_ERROR
        );
        exit;
    }

    $renderer = new MarketLense\Core\Report_Card_Renderer();
    try {
        echo json_encode(
            [
                'html' => $renderer->render(
                    is_array($payload['report'] ?? null) ? $payload['report'] : [],
                    (string) ($payload['variant'] ?? '')
                ),
                'error' => '',
            ],
            JSON_THROW_ON_ERROR
        );
    } catch (Throwable $error) {
        echo json_encode(
            [
                'html' => '',
                'error' => get_class($error) . ': ' . $error->getMessage(),
            ],
            JSON_THROW_ON_ERROR
        );
    }
}
