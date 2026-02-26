<?php
/**
 * Digest parsing helpers.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Content_Parser
{
    /**
     * Extract Drive file identifier from rendered digest HTML.
     */
    public function extract_file_id(string $content): string
    {
        $patterns = [
            '/File ID:\s*<code>\s*([^<\s]+)\s*<\/code>/i',
            '/Drive fileId:\s*([A-Za-z0-9\-_]+)/i',
            '/data-file-id=["\']([^"\']+)["\']/i',
        ];

        foreach ($patterns as $pattern) {
            if (preg_match($pattern, $content, $matches) === 1) {
                return $this->normalize_text($matches[1]);
            }
        }

        return '';
    }

    /**
     * Extract a metadata value from the report metadata panel by label.
     */
    public function extract_metadata_value(string $content, string $label): string
    {
        $quoted_label = preg_quote($label, '/');
        $patterns = [
            '/<span[^>]*class=["\'][^"\']*meta-label[^"\']*["\'][^>]*>\s*' . $quoted_label . '\s*<\/span>\s*<p[^>]*class=["\'][^"\']*meta-value[^"\']*["\'][^>]*>(.*?)<\/p>/is',
            '/<strong>\s*' . $quoted_label . '\s*:\s*<\/strong>\s*([^<\r\n]+)/i',
        ];

        foreach ($patterns as $pattern) {
            if (preg_match($pattern, $content, $matches) === 1) {
                return $this->normalize_text($matches[1]);
            }
        }

        return '';
    }

    private function normalize_text(string $value): string
    {
        $decoded = html_entity_decode($value, ENT_QUOTES | ENT_HTML5, 'UTF-8');
        $plain = wp_strip_all_tags($decoded);
        $single_spaced = preg_replace('/\s+/u', ' ', $plain);
        return sanitize_text_field(trim((string) $single_spaced));
    }
}
