<?php
declare(strict_types=1);

namespace {
    define('ABSPATH', __DIR__ . '/');

    function esc_attr(string $value): string { return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
    function esc_html(string $value): string { return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
    function esc_url(string $value): string { return esc_attr($value); }
    function esc_html__(string $value, string $domain): string { unset($domain); return $value; }
    function esc_html_e(string $value, string $domain): void { unset($domain); echo esc_html($value); }
    function _n(string $single, string $plural, int $count, string $domain): string { unset($domain); return $count === 1 ? $single : $plural; }
}

namespace {
    $renderer_path = dirname(__DIR__, 2) . '/Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-signal-card-renderer.php';
    if (! file_exists($renderer_path)) {
        echo json_encode(['html' => '', 'error' => 'renderer_missing'], JSON_THROW_ON_ERROR);
        exit;
    }

    require $renderer_path;
    $payload = json_decode((string) stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
    $renderer = new MarketLense\Core\Signal_Card_Renderer();
    try {
        echo json_encode([
            'html' => $renderer->render(is_array($payload['signal'] ?? null) ? $payload['signal'] : [], (string) ($payload['variant'] ?? '')),
            'error' => '',
        ], JSON_THROW_ON_ERROR);
    } catch (Throwable $error) {
        echo json_encode(['html' => '', 'error' => get_class($error) . ': ' . $error->getMessage()], JSON_THROW_ON_ERROR);
    }
}
