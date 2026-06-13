<?php
declare(strict_types=1);

namespace {
    define('ABSPATH', __DIR__ . '/');

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
    require dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-card-renderer.php';

    $payload = json_decode(
        (string) stream_get_contents(STDIN),
        true,
        512,
        JSON_THROW_ON_ERROR
    );

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
