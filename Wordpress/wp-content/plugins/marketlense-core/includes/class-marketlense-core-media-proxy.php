<?php
/**
 * Frontend proxy for media URLs that are blocked when served directly from uploads.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Media_Proxy
{
    private const QUERY_KEY = 'ml_media';

    public function register(): void
    {
        add_action('template_redirect', [$this, 'maybe_serve_media'], 0);
        add_filter('the_content', [$this, 'rewrite_content_media_urls'], 20);
        add_filter('wp_get_attachment_url', [$this, 'filter_attachment_url'], 20, 2);
        add_filter('wp_get_attachment_image_attributes', [$this, 'filter_attachment_image_attributes'], 20, 3);
    }

    public function maybe_serve_media(): void
    {
        $attachment_id = isset($_GET[self::QUERY_KEY])
            ? absint(wp_unslash($_GET[self::QUERY_KEY]))
            : 0;

        if ($attachment_id < 1) {
            return;
        }

        $attachment = get_post($attachment_id);
        if (! ($attachment instanceof \WP_Post) || $attachment->post_type !== 'attachment') {
            status_header(404);
            exit;
        }

        $file_path = get_attached_file($attachment_id);
        if (! is_string($file_path) || $file_path === '' || ! is_readable($file_path)) {
            status_header(404);
            exit;
        }

        $mime_type = get_post_mime_type($attachment_id);
        if (! is_string($mime_type) || $mime_type === '') {
            $filetype = wp_check_filetype($file_path);
            $mime_type = is_array($filetype) && is_string($filetype['type'] ?? null) && $filetype['type'] !== ''
                ? $filetype['type']
                : 'application/octet-stream';
        }

        while (ob_get_level() > 0) {
            ob_end_clean();
        }

        status_header(200);
        header('Content-Type: ' . $mime_type);
        header('Content-Length: ' . (string) filesize($file_path));
        header('Content-Disposition: inline; filename="' . wp_basename($file_path) . '"');
        header('Cache-Control: public, max-age=' . \DAY_IN_SECONDS);
        header('X-Content-Type-Options: nosniff');

        readfile($file_path);
        exit;
    }

    public function rewrite_content_media_urls(string $content): string
    {
        if ($content === '' || ! $this->should_proxy_frontend_urls() || ! str_contains($content, '/wp-content/uploads/')) {
            return $content;
        }

        $pattern = '#https?://[^"\'\s>]+/wp-content/uploads/[^"\'\s<]+#i';
        $rewritten = preg_replace_callback(
            $pattern,
            function (array $matches): string {
                $raw_url = html_entity_decode((string) ($matches[0] ?? ''), \ENT_QUOTES);
                $attachment_id = attachment_url_to_postid($raw_url);
                if ($attachment_id < 1) {
                    return (string) ($matches[0] ?? '');
                }

                return esc_url($this->proxy_url($attachment_id));
            },
            $content
        );

        return is_string($rewritten) ? $rewritten : $content;
    }

    public function filter_attachment_url(string $url, int $attachment_id): string
    {
        if ($attachment_id < 1 || ! $this->should_proxy_frontend_urls()) {
            return $url;
        }

        return $this->proxy_url($attachment_id);
    }

    /**
     * @param array<string,string> $attr
     * @param mixed                $size
     * @return array<string,string>
     */
    public function filter_attachment_image_attributes(array $attr, \WP_Post $attachment, $size): array
    {
        unset($size);

        $attachment_id = (int) $attachment->ID;
        if ($attachment_id < 1 || ! $this->should_proxy_frontend_urls()) {
            return $attr;
        }

        $attr['src'] = esc_url($this->proxy_url($attachment_id));
        unset($attr['srcset'], $attr['sizes']);

        return $attr;
    }

    private function proxy_url(int $attachment_id): string
    {
        return add_query_arg(
            [
                self::QUERY_KEY => $attachment_id,
            ],
            home_url('/')
        );
    }

    private function should_proxy_frontend_urls(): bool
    {
        if (is_admin() || wp_doing_ajax()) {
            return false;
        }

        return ! (defined('REST_REQUEST') && REST_REQUEST);
    }
}
