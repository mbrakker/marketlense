<?php
/**
 * Public rendering failure boundary for Market Bearing shortcode surfaces.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Public_Render_Boundary
{
    private const EVENT_NAME = 'marketlense_public_render_failure';

    /**
     * Executes one registered public shortcode without exposing internal failures.
     *
     * @param callable():string $renderer
     */
    public function render_shortcode(string $shortcode, callable $renderer): string
    {
        try {
            return $renderer();
        } catch (\Throwable $exception) {
            if (is_admin()) {
                throw $exception;
            }

            $correlation_id = 'ML-' . wp_generate_uuid4();
            $context = $this->context($shortcode, $correlation_id);
            $this->log_failure($context, $exception);

            if (! headers_sent()) {
                status_header(500);
                nocache_headers();
            }

            return $this->safe_markup($correlation_id);
        }
    }

    /**
     * @return array{correlation_id:string,route:string,entity_type:string,entity_identifier:string,shortcode:string}
     */
    private function context(string $shortcode, string $correlation_id): array
    {
        $route = $this->route();
        $entity = get_queried_object();
        $identifier = '';
        if ($entity instanceof \WP_Term) {
            $identifier = (string) $entity->term_id;
        } elseif ($entity instanceof \WP_Post) {
            $identifier = (string) $entity->ID;
        }

        if ($identifier === '') {
            $identifier = (string) basename(trim($route, '/'));
        }

        return [
            'correlation_id' => $correlation_id,
            'route' => $route,
            'entity_type' => $this->entity_type($shortcode),
            'entity_identifier' => $this->sanitize_identifier($identifier),
            'shortcode' => sanitize_key($shortcode),
        ];
    }

    private function route(): string
    {
        $request_uri = isset($_SERVER['REQUEST_URI']) ? (string) $_SERVER['REQUEST_URI'] : '/';
        $path = parse_url($request_uri, PHP_URL_PATH);

        return is_string($path) && $path !== '' ? $path : '/';
    }

    private function entity_type(string $shortcode): string
    {
        return match ($shortcode) {
            'ml_report_browser', 'ml_latest_reports', 'ml_featured_digest' => 'report',
            'ml_publishers_directory', 'ml_publisher_profile', 'ml_publisher_authority' => 'publisher',
            'ml_signals_index', 'ml_signal_cards', 'ml_signal_archive', 'ml_briefings_index', 'ml_briefing_archive' => 'archive',
            default => 'shortcode',
        };
    }

    private function sanitize_identifier(string $identifier): string
    {
        $normalized = sanitize_key($identifier);

        return substr($normalized, 0, 96);
    }

    /**
     * @param array{correlation_id:string,route:string,entity_type:string,entity_identifier:string,shortcode:string} $context
     */
    private function log_failure(array $context, \Throwable $exception): void
    {
        $event = [
            'event' => self::EVENT_NAME,
            'severity' => 'error',
            'run_id' => $context['correlation_id'],
            'task_id' => $context['shortcode'],
            'span_id' => $context['correlation_id'],
            'role' => 'public_render_boundary',
            'module' => self::class,
            ...$context,
            'exception_type' => get_class($exception),
            'exception_message' => $exception->getMessage(),
            'exception_file' => $exception->getFile(),
            'exception_line' => $exception->getLine(),
            'exception_trace' => $exception->getTraceAsString(),
        ];

        error_log((string) wp_json_encode($event));
        do_action(self::EVENT_NAME, $event);
    }

    private function safe_markup(string $correlation_id): string
    {
        return sprintf(
            '<section class="ml-safe-render-error" data-marketlense-safe-error><p class="ml-safe-render-error__eyebrow">%1$s</p><h2>%2$s</h2><p>%3$s</p><p class="ml-safe-render-error__reference">%4$s <code>%5$s</code></p></section>',
            esc_html__('Market Bearing', 'marketlense-core'),
            esc_html__('This section is temporarily unavailable.', 'marketlense-core'),
            esc_html__('Please refresh the page or try again shortly.', 'marketlense-core'),
            esc_html__('Reference:', 'marketlense-core'),
            esc_html($correlation_id)
        );
    }
}
