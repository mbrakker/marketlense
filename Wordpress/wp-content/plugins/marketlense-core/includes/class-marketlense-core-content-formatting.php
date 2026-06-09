<?php
/**
 * Frontend content formatting controls for ingested report HTML.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Content_Formatting
{
    private bool $restore_registered = false;

    public function register(): void
    {
        add_filter('the_content', [$this, 'suspend_auto_paragraphs_for_reports'], 9);
        add_filter('the_content', [$this, 'format_briefing_for_readers'], 12);
    }

    public function suspend_auto_paragraphs_for_reports(string $content): string
    {
        $post = get_post();
        if (! $post instanceof \WP_Post) {
            return $content;
        }

        if (! in_array((string) $post->post_type, Post_Type::report_post_types(), true)) {
            return $content;
        }

        remove_filter('the_content', 'wpautop');
        remove_filter('the_content', 'shortcode_unautop');

        if (! $this->restore_registered) {
            add_filter('the_content', [$this, 'restore_auto_paragraphs'], 99);
            $this->restore_registered = true;
        }

        return $content;
    }

    public function restore_auto_paragraphs(string $content): string
    {
        if (! has_filter('the_content', 'wpautop')) {
            add_filter('the_content', 'wpautop');
        }
        if (! has_filter('the_content', 'shortcode_unautop')) {
            add_filter('the_content', 'shortcode_unautop');
        }

        return $content;
    }

    /**
     * Removes internal evidence identifiers and folds technical appendices into disclosures.
     */
    public function format_briefing_for_readers(string $content): string
    {
        $post = get_post();
        if (
            ! ($post instanceof \WP_Post)
            || $post->post_type !== Post_Type::BRIEFING_POST_TYPE
            || trim($content) === ''
            || ! class_exists('\DOMDocument')
        ) {
            return $content;
        }

        $document = new \DOMDocument('1.0', 'UTF-8');
        $previous = libxml_use_internal_errors(true);
        $loaded = $document->loadHTML(
            '<?xml encoding="UTF-8"><div id="ml-briefing-root">' . $content . '</div>',
            LIBXML_HTML_NOIMPLIED | LIBXML_HTML_NODEFDTD
        );
        libxml_clear_errors();
        libxml_use_internal_errors($previous);
        if (! $loaded) {
            return $content;
        }

        $xpath = new \DOMXPath($document);
        $text_nodes = $xpath->query(
            '//*[@id="ml-briefing-root"]//text()[not(ancestor::script) and not(ancestor::style)]'
        );
        if ($text_nodes instanceof \DOMNodeList) {
            foreach ($text_nodes as $text_node) {
                $cleaned = preg_replace(
                    '/[A-Za-z0-9_-]{15,}:(?:finding|quote|claim|metric):[A-Za-z0-9_-]+/i',
                    'source evidence',
                    (string) $text_node->nodeValue
                );
                $cleaned = preg_replace(
                    '/\s*\([^()]*\b(?:finding|quote|claim|metric):[^()]*\)/iu',
                    '',
                    is_string($cleaned) ? $cleaned : (string) $text_node->nodeValue
                );
                $cleaned = preg_replace(
                    '/\b(?:finding|quote|claim|metric):[A-Za-z0-9_-]+(?:-[A-Za-z0-9_-]+)?\b/iu',
                    '',
                    is_string($cleaned) ? $cleaned : (string) $text_node->nodeValue
                );
                $cleaned = preg_replace(
                    '/\b(?:findings?|quotes?|claims?|metrics?)\s+[FQ]\d+(?:[–-][FQ]?\d+)?\b/iu',
                    '',
                    is_string($cleaned) ? $cleaned : (string) $text_node->nodeValue
                );
                $cleaned = preg_replace(
                    '/\s+([,.;:])/',
                    '$1',
                    is_string($cleaned) ? $cleaned : (string) $text_node->nodeValue
                );
                if (is_string($cleaned)) {
                    $text_node->nodeValue = $cleaned;
                }
            }
        }

        $citation_nodes = $xpath->query(
            '//*[@id="ml-briefing-root"]//*[contains(concat(" ", normalize-space(@class), " "), " citation-micro ")]'
        );
        if ($citation_nodes instanceof \DOMNodeList) {
            $nodes_to_remove = [];
            foreach ($citation_nodes as $citation_node) {
                $nodes_to_remove[] = $citation_node;
            }
            foreach ($nodes_to_remove as $citation_node) {
                if ($citation_node->parentNode instanceof \DOMNode) {
                    $citation_node->parentNode->removeChild($citation_node);
                }
            }
        }

        foreach (
            [
                'section-sources' => __('Source report map', 'marketlense-core'),
                'section-uncertainty' => __('Uncertainty and divergence notes', 'marketlense-core'),
                'section-evidence' => __('Evidence references', 'marketlense-core'),
            ] as $section_id => $label
        ) {
            $section = $document->getElementById($section_id);
            if (! ($section instanceof \DOMElement) || ! ($section->parentNode instanceof \DOMNode)) {
                continue;
            }

            $details = $document->createElement('details');
            $details->setAttribute('class', 'ml-briefing-appendix');
            $summary = $document->createElement('summary', $label);
            $details->appendChild($summary);
            $section->parentNode->replaceChild($details, $section);
            $details->appendChild($section);
        }

        $root = $document->getElementById('ml-briefing-root');
        if (! ($root instanceof \DOMElement)) {
            return $content;
        }

        $formatted = '';
        foreach ($root->childNodes as $child) {
            $formatted .= (string) $document->saveHTML($child);
        }

        return $formatted !== '' ? $formatted : $content;
    }
}
