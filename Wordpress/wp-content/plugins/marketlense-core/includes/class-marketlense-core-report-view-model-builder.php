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
    private const FEATURED_EXCERPT_WORDS = 24;

    private const ARCHIVE_EXCERPT_WORDS = 56;

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
        $normalized_summary = $this->normalize_brand_name($this->normalize_text($summary));
        $insight_texts = $this->extract_insight_texts($content);
        $counts = $this->extract_content_counts($post_id, $content, $insight_texts);
        $full_key_metrics = $this->extract_full_key_metrics($insight_texts);
        $timestamp = (int) get_post_timestamp($post, 'date');
        $card_contract = $this->build_card_contract($post_id, $content, $timestamp);

        $view_model = array_merge([
            'post_id' => $post_id,
            'title' => $this->normalize_brand_name($this->normalize_text(get_the_title($post))),
            'permalink' => (string) get_permalink($post),
            'date' => (string) get_the_date('F j, Y', $post),
            'timestamp' => $timestamp,
            'publisher' => $this->resolve_publisher($post_id, $content),
            'time_period' => $this->resolve_metadata_value($post_id, Meta::META_TIME_PERIOD, $content, 'Time period'),
            'insights_count' => $counts['insights'],
            'quotes_count' => $counts['quotes'],
            'topics_count' => $counts['topics'],
            'citations_count' => $counts['citations'],
            'full_excerpt' => $normalized_summary,
            'excerpt' => wp_trim_words($normalized_summary, self::FEATURED_EXCERPT_WORDS, '...'),
            'archive_excerpt' => wp_trim_words($normalized_summary, self::ARCHIVE_EXCERPT_WORDS, '...'),
            'why_it_matters' => $this->extract_first_sentence($normalized_summary),
            'key_metrics' => $this->summarize_key_metrics($full_key_metrics),
            'full_key_metrics' => $full_key_metrics,
        ], $card_contract);

        $this->cache[$post_id] = $view_model;

        return $view_model;
    }

    /**
     * @return array<string,mixed>
     */
    private function build_card_contract(int $post_id, string $content, int $timestamp): array
    {
        $schema_version = $this->meta_text($post_id, Meta::META_CARD_SCHEMA_VERSION);
        $title_scale = $this->meta_text($post_id, Meta::META_CARD_TITLE_SCALE);
        $tldr_compact = $this->meta_text($post_id, Meta::META_CARD_TLDR_COMPACT);
        $tldr_standard = $this->meta_text($post_id, Meta::META_CARD_TLDR_STANDARD);
        $geography_scope = $this->meta_text($post_id, Meta::META_CARD_GEOGRAPHY_SCOPE);
        $raw_insights = get_post_meta($post_id, Meta::META_CARD_KEY_INSIGHTS, true);
        $key_insights = [];
        if (is_array($raw_insights)) {
            foreach ($raw_insights as $insight) {
                if (! is_string($insight)) {
                    continue;
                }
                $normalized = $this->normalize_text($insight);
                if ($normalized !== '') {
                    $key_insights[] = $normalized;
                }
            }
        }
        $raw_fingerprint = get_post_meta($post_id, Meta::META_CARD_COVER_FINGERPRINT, true);
        $fingerprint = is_array($raw_fingerprint) ? $raw_fingerprint : [];
        $cover_ids = [
            'small' => (int) get_post_meta($post_id, Meta::META_CARD_COVER_SMALL_ID, true),
            'medium' => (int) get_post_meta($post_id, Meta::META_CARD_COVER_MEDIUM_ID, true),
            'large' => (int) get_post_meta($post_id, Meta::META_CARD_COVER_LARGE_ID, true),
        ];
        $covers = [];
        foreach ($cover_ids as $size => $media_id) {
            $url = $media_id > 0 ? wp_get_attachment_image_url($media_id, 'full') : false;
            $covers[$size] = is_string($url) ? $url : '';
        }

        $errors = [];
        if ($schema_version !== '1.0') {
            $errors[] = 'schema_version';
        }
        if (! in_array($title_scale, ['short', 'medium', 'long', 'xlong'], true)) {
            $errors[] = 'title_scale';
        }
        if ($tldr_compact === '') {
            $errors[] = 'tldr_compact';
        }
        if ($tldr_standard === '') {
            $errors[] = 'tldr_standard';
        }
        if (count($key_insights) !== 2) {
            $errors[] = 'key_insights';
        }
        if (! in_array($geography_scope, ['global', 'regional', 'country', 'unknown'], true)) {
            $errors[] = 'geography_scope';
        }
        if (! $this->valid_cover_fingerprint($fingerprint)) {
            $errors[] = 'cover_fingerprint';
        }
        foreach ($covers as $size => $url) {
            if ($url === '') {
                $errors[] = 'cover_' . $size;
            }
        }

        $geography = $geography_scope === 'unknown'
            ? ''
            : $this->resolve_metadata_value($post_id, Meta::META_REGION, $content, 'Region');
        $geography_icon = match ($geography_scope) {
            'global' => 'globe',
            'regional', 'country' => 'locator',
            default => '',
        };
        if ($geography_scope !== 'unknown' && $geography === '') {
            $errors[] = 'geography_label';
        }

        $age = current_time('timestamp', true) - $timestamp;

        return [
            'card_contract_valid' => $errors === [],
            'card_contract_errors' => array_values(array_unique($errors)),
            'title_scale' => $title_scale,
            'tldr_compact' => $tldr_compact,
            'tldr_standard' => $tldr_standard,
            'key_insights' => $key_insights,
            'geography' => $geography,
            'geography_scope' => $geography_scope,
            'geography_icon' => $geography_icon,
            'is_new' => $age >= 0 && $age < 7 * DAY_IN_SECONDS,
            'covers' => $covers,
            'cover_fingerprint' => $fingerprint,
        ];
    }

    private function meta_text(int $post_id, string $key): string
    {
        return $this->normalize_text((string) get_post_meta($post_id, $key, true));
    }

    /**
     * @param array<mixed> $fingerprint
     */
    private function valid_cover_fingerprint(array $fingerprint): bool
    {
        return Meta::sanitize_cover_fingerprint($fingerprint) !== [];
    }

    private function resolve_publisher(int $post_id, string $content): string
    {
        $publisher = $this->normalize_text((string) get_post_meta($post_id, Meta::META_PUBLISHER, true));
        if (! $this->is_missing_metadata_value($publisher)) {
            return $publisher;
        }

        $terms = get_the_terms($post_id, Taxonomies::PUBLISHER_TAXONOMY);
        if (! is_array($terms) || $terms === []) {
            return $this->normalize_metadata_value(
                $this->parser->extract_metadata_value($content, 'Publisher')
            );
        }

        $first_term = $terms[0];
        if (! ($first_term instanceof \WP_Term)) {
            return $this->normalize_metadata_value(
                $this->parser->extract_metadata_value($content, 'Publisher')
            );
        }

        return $this->normalize_metadata_value($first_term->name);
    }

    private function resolve_metadata_value(int $post_id, string $meta_key, string $content, string $label): string
    {
        $stored = $this->normalize_metadata_value((string) get_post_meta($post_id, $meta_key, true));
        if ($stored !== '') {
            return $stored;
        }

        return $this->normalize_metadata_value(
            $this->parser->extract_metadata_value($content, $label)
        );
    }

    /**
     * @param list<string> $insight_texts
     * @return array{insights:int,quotes:int,topics:int,citations:int}
     */
    private function extract_content_counts(int $post_id, string $content, array $insight_texts): array
    {
        $counts = [
            'insights' => count($insight_texts),
            'quotes' => max(
                $this->count_nodes_by_class($content, 'section-quotes', 'quote-card'),
                $this->count_nodes_by_class($content, 'evidence', 'quote-feature')
                    + $this->count_nodes_by_class($content, 'evidence', 'quote-card')
            ),
            'topics' => $this->count_public_topic_terms($post_id),
            'citations' => $this->extract_evidence_reference_count($content),
        ];

        $hero_counts = $this->extract_hero_counts($content);
        foreach (['insights', 'quotes', 'topics'] as $key) {
            if ($counts[$key] < 1 && isset($hero_counts[$key])) {
                $counts[$key] = (int) $hero_counts[$key];
            }
        }

        return $counts;
    }

    private function extract_evidence_reference_count(string $content): int
    {
        if (preg_match_all('/(\d+)\s+evidence references/iu', $content, $matches) > 0) {
            return max(array_map('intval', $matches[1]));
        }

        $xpath = $this->load_xpath($content);
        if (! ($xpath instanceof \DOMXPath)) {
            return 0;
        }

        $citation_nodes = $xpath->query(
            "//*[contains(concat(' ', normalize-space(@class), ' '), ' citation-micro ')]"
        );
        $citation_count = 0;
        if ($citation_nodes instanceof \DOMNodeList) {
            foreach ($citation_nodes as $node) {
                if (! ($node instanceof \DOMNode)) {
                    continue;
                }

                $citation_text = preg_replace('/^\s*Evidence:\s*/iu', '', $node->textContent);
                $references = array_filter(
                    array_map('trim', explode(',', (string) $citation_text)),
                    static fn (string $reference): bool => $reference !== ''
                );
                $citation_count += count($references);
            }
        }

        if ($citation_count > 0) {
            return $citation_count;
        }

        $figure_captions = $xpath->query('//figcaption');

        return $figure_captions instanceof \DOMNodeList ? (int) $figure_captions->length : 0;
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

        $queries = [
            $this->section_class_query('findings', 'finding-card'),
            $this->section_class_query('section-insights', 'insight-text'),
        ];
        $items = [];
        foreach ($queries as $query) {
            foreach ($xpath->query($query) ?: [] as $node) {
                if (! ($node instanceof \DOMNode)) {
                    continue;
                }

                $text = $this->normalize_text($node->textContent);
                if ($text !== '') {
                    $items[] = $text;
                }
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

    private function count_public_topic_terms(int $post_id): int
    {
        $terms = get_the_terms($post_id, Taxonomies::CATEGORY_TAXONOMY);
        if (! is_array($terms)) {
            return 0;
        }

        $term_ids = [];
        foreach ($terms as $term) {
            if ($term instanceof \WP_Term) {
                $term_ids[(int) $term->term_id] = true;
            }
        }

        return count($term_ids);
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

    private function normalize_metadata_value(string $value): string
    {
        $normalized = $this->normalize_text($value);

        return $this->is_missing_metadata_value($normalized) ? '' : $normalized;
    }

    private function normalize_brand_name(string $value): string
    {
        return str_replace(
            ['Market Lense', 'MarketLense'],
            ['Market Bearing', 'Market Bearing'],
            $value
        );
    }

    private function is_missing_metadata_value(string $value): bool
    {
        return in_array(
            strtolower(trim($value)),
            ['', '...', '…', 'not extracted', 'Not extracted', 'not specified', 'unknown', 'n/a', 'na', '-'],
            true
        );
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
