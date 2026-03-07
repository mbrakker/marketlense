<?php
/**
 * Report presentation view-model builder.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Report_View_Model_Builder
{
    private Content_Parser $parser;

    /**
     * @var array<int,array<string,mixed>>
     */
    private array $cache = [];

    public function __construct(Content_Parser $parser)
    {
        $this->parser = $parser;
    }

    /**
     * Builds normalized presentation data for a published report.
     *
     * @return array<string,mixed>
     */
    public function build(\WP_Post $post): array
    {
        $post_id = (int) $post->ID;
        if (isset($this->cache[$post_id])) {
            return $this->cache[$post_id];
        }

        $content = (string) $post->post_content;
        $summary = $this->first_non_empty(
            $this->extract_section_text($content, 'section-summary'),
            $this->extract_section_text($content, 'section-executive'),
            wp_strip_all_tags((string) $post->post_excerpt),
            wp_strip_all_tags($content)
        );
        $normalized_summary = $this->normalize_text($summary);
        $insight_texts = $this->extract_insight_texts($content);
        $counts = $this->extract_content_counts($content, $insight_texts);
        $full_key_metrics = $this->extract_full_key_metrics($insight_texts);

        $view_model = [
            'post_id' => $post_id,
            'title' => $this->normalize_text(get_the_title($post)),
            'permalink' => (string) get_permalink($post),
            'date' => (string) get_the_date('F j, Y', $post),
            'timestamp' => get_post_timestamp($post, 'date'),
            'publisher' => $this->resolve_publisher($post_id, $content),
            'geography' => $this->resolve_metadata_value($post_id, Meta::META_REGION, $content, 'Region'),
            'time_period' => $this->resolve_metadata_value($post_id, Meta::META_TIME_PERIOD, $content, 'Time period'),
            'insights_count' => $counts['insights'],
            'quotes_count' => $counts['quotes'],
            'topics_count' => $counts['topics'],
            'excerpt' => wp_trim_words($normalized_summary, 24, '...'),
            'why_it_matters' => $this->extract_first_sentence($normalized_summary),
            'key_metrics' => $this->summarize_key_metrics($full_key_metrics),
            'full_key_metrics' => $full_key_metrics,
        ];

        $this->cache[$post_id] = $view_model;

        return $view_model;
    }

    private function resolve_publisher(int $post_id, string $content): string
    {
        $publisher = $this->normalize_text((string) get_post_meta($post_id, Meta::META_PUBLISHER, true));
        if ($publisher !== '') {
            return $publisher;
        }

        $terms = get_the_terms($post_id, Taxonomies::PUBLISHER_TAXONOMY);
        if (! is_array($terms) || $terms === []) {
            return $this->normalize_text($this->parser->extract_metadata_value($content, 'Publisher'));
        }

        $first_term = $terms[0];
        if (! ($first_term instanceof \WP_Term)) {
            return $this->normalize_text($this->parser->extract_metadata_value($content, 'Publisher'));
        }

        return $this->normalize_text($first_term->name);
    }

    private function resolve_metadata_value(int $post_id, string $meta_key, string $content, string $label): string
    {
        $stored = $this->normalize_text((string) get_post_meta($post_id, $meta_key, true));
        if ($stored !== '') {
            return $stored;
        }

        return $this->normalize_text($this->parser->extract_metadata_value($content, $label));
    }

    /**
     * @param list<string> $insight_texts
     * @return array{insights:int,quotes:int,topics:int}
     */
    private function extract_content_counts(string $content, array $insight_texts): array
    {
        $counts = [
            'insights' => count($insight_texts),
            'quotes' => $this->count_nodes_by_class($content, 'section-quotes', 'quote-card'),
            'topics' => max(
                $this->count_nodes_by_class($content, 'section-topics', 'topic-brief-card'),
                $this->count_chip_items($content, 'section-topics')
            ),
        ];

        $hero_counts = $this->extract_hero_counts($content);
        foreach (['insights', 'quotes', 'topics'] as $key) {
            if ($counts[$key] < 1 && isset($hero_counts[$key])) {
                $counts[$key] = (int) $hero_counts[$key];
            }
        }

        return $counts;
    }

    /**
     * @return list<string>
     */
    private function extract_insight_texts(string $content): array
    {
        $xpath = $this->load_xpath($content);
        if (! ($xpath instanceof \DOMXPath)) {
            return [];
        }

        $items = [];
        foreach ($xpath->query($this->section_class_query('section-insights', 'insight-text')) ?: [] as $node) {
            if (! ($node instanceof \DOMNode)) {
                continue;
            }

            $text = $this->normalize_text($node->textContent);
            if ($text !== '') {
                $items[] = $text;
            }
        }

        return array_values(array_unique($items));
    }

    /**
     * @param list<string> $insight_texts
     * @return list<string>
     */
    private function extract_full_key_metrics(array $insight_texts, int $limit = 3): array
    {
        $metrics = [];
        foreach ($insight_texts as $text) {
            if (preg_match('/\d/u', $text) !== 1) {
                continue;
            }

            $metrics[] = $text;
            if (count($metrics) >= $limit) {
                break;
            }
        }

        return array_values(array_unique($metrics));
    }

    /**
     * @param list<string> $metrics
     * @return list<string>
     */
    private function summarize_key_metrics(array $metrics, int $word_limit = 12): array
    {
        return array_values(
            array_unique(
                array_map(
                    static fn (string $metric): string => wp_trim_words($metric, $word_limit, '...'),
                    $metrics
                )
            )
        );
    }

    private function extract_section_text(string $content, string $section_id): string
    {
        $xpath = $this->load_xpath($content);
        if (! ($xpath instanceof \DOMXPath)) {
            return '';
        }

        $preferred = $xpath->query(
            sprintf("//*[@id='%s']//*[contains(concat(' ', normalize-space(@class), ' '), ' summary-copy ')]", $section_id)
        );
        if ($preferred instanceof \DOMNodeList && $preferred->length > 0) {
            $node = $preferred->item(0);
            if ($node instanceof \DOMNode) {
                return $this->normalize_text($node->textContent);
            }
        }

        $paragraphs = $xpath->query(sprintf("//*[@id='%s']//p", $section_id));
        if (! ($paragraphs instanceof \DOMNodeList) || $paragraphs->length < 1) {
            return '';
        }

        $parts = [];
        foreach ($paragraphs as $paragraph) {
            if (! ($paragraph instanceof \DOMNode)) {
                continue;
            }

            $text = $this->normalize_text($paragraph->textContent);
            if ($text !== '') {
                $parts[] = $text;
            }
        }

        return implode(' ', $parts);
    }

    /**
     * @return array<string,int>
     */
    private function extract_hero_counts(string $content): array
    {
        $counts = [];
        if (preg_match_all('/<li>\s*(\d+)\s+(insights|quotes|topics)\s*<\/li>/iu', $content, $matches, \PREG_SET_ORDER) !== 1 && empty($matches)) {
            return $counts;
        }

        foreach ($matches as $match) {
            $counts[strtolower((string) $match[2])] = (int) $match[1];
        }

        return $counts;
    }

    private function count_nodes_by_class(string $content, string $section_id, string $class_name): int
    {
        $xpath = $this->load_xpath($content);
        if (! ($xpath instanceof \DOMXPath)) {
            return 0;
        }

        $nodes = $xpath->query($this->section_class_query($section_id, $class_name));

        return $nodes instanceof \DOMNodeList ? (int) $nodes->length : 0;
    }

    private function count_chip_items(string $content, string $section_id): int
    {
        $xpath = $this->load_xpath($content);
        if (! ($xpath instanceof \DOMXPath)) {
            return 0;
        }

        $nodes = $xpath->query(
            sprintf(
                "//*[@id='%s']//ul[contains(concat(' ', normalize-space(@class), ' '), ' chip-list ')]/li",
                $section_id
            )
        );

        return $nodes instanceof \DOMNodeList ? (int) $nodes->length : 0;
    }

    private function section_class_query(string $section_id, string $class_name): string
    {
        return sprintf(
            "//*[@id='%s']//*[contains(concat(' ', normalize-space(@class), ' '), ' %s ')]",
            $section_id,
            $class_name
        );
    }

    private function extract_first_sentence(string $text): string
    {
        if ($text === '') {
            return '';
        }

        if (preg_match('/^(.+?[.!?])(?:\s|$)/u', $text, $matches) === 1) {
            return $this->normalize_text($matches[1]);
        }

        return wp_trim_words($text, 22, '...');
    }

    private function first_non_empty(string ...$values): string
    {
        foreach ($values as $value) {
            $normalized = $this->normalize_text($value);
            if ($normalized !== '') {
                return $normalized;
            }
        }

        return '';
    }

    private function normalize_text(string $value): string
    {
        $decoded = html_entity_decode($value, \ENT_QUOTES | \ENT_HTML5, 'UTF-8');
        $plain = wp_strip_all_tags($decoded);
        $single_spaced = preg_replace('/\s+/u', ' ', $plain);

        return trim((string) $single_spaced);
    }

    private function load_xpath(string $content): ?\DOMXPath
    {
        if ($content === '' || ! class_exists(\DOMDocument::class)) {
            return null;
        }

        $document = new \DOMDocument('1.0', 'UTF-8');
        $previous_state = libxml_use_internal_errors(true);
        $loaded = $document->loadHTML(
            '<?xml encoding="utf-8" ?><!DOCTYPE html><html><body>' . $content . '</body></html>'
        );
        libxml_clear_errors();
        libxml_use_internal_errors($previous_state);

        if (! $loaded) {
            return null;
        }

        return new \DOMXPath($document);
    }
}
