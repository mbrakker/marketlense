<?php
/**
 * Plugin bootstrapper.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Plugin
{
    private static ?Plugin $instance = null;

    private bool $booted = false;

    private Post_Type $post_type;

    private Taxonomies $taxonomies;

    private Meta $meta;

    private Media_Proxy $media_proxy;

    private Content_Formatting $content_formatting;

    private Report_View_Model_Builder $view_model_builder;

    private Intelligence_Stats $stats;

    private Intelligence_Projection $intelligence_projection;

    private Intake $intake;

    private Report_Card_Renderer $report_card_renderer;

    private Briefing_Card_View_Model_Builder $briefing_card_view_model_builder;

    private Briefing_Card_Renderer $briefing_card_renderer;

    private Signal_Card_View_Model_Builder $signal_card_view_model_builder;

    private Signal_Card_Renderer $signal_card_renderer;

    private Shortcodes $shortcodes;

    private function __construct()
    {
        $parser = new Content_Parser();
        $this->post_type = new Post_Type();
        $this->taxonomies = new Taxonomies();
        $this->meta = new Meta($parser);
        $this->media_proxy = new Media_Proxy();
        $this->content_formatting = new Content_Formatting();
        $this->view_model_builder = new Report_View_Model_Builder($parser);
        $this->intelligence_projection = new Intelligence_Projection();
        $this->intake = new Intake();
        $this->stats = new Intelligence_Stats($this->view_model_builder, $this->intelligence_projection);
        $this->report_card_renderer = new Report_Card_Renderer();
        $this->briefing_card_view_model_builder = new Briefing_Card_View_Model_Builder();
        $this->briefing_card_renderer = new Briefing_Card_Renderer();
        $this->signal_card_view_model_builder = new Signal_Card_View_Model_Builder();
        $this->signal_card_renderer = new Signal_Card_Renderer();
        $this->shortcodes = new Shortcodes(
            $this->view_model_builder,
            $this->stats,
            $this->report_card_renderer,
            $this->briefing_card_view_model_builder,
            $this->briefing_card_renderer,
            $this->signal_card_view_model_builder,
            $this->signal_card_renderer
        );
    }

    public static function instance(): Plugin
    {
        if (self::$instance === null) {
            self::$instance = new self();
        }

        return self::$instance;
    }

    public function boot(): void
    {
        if ($this->booted) {
            return;
        }

        add_action('init', [$this->post_type, 'register'], 5);
        add_action('init', [$this->taxonomies, 'register'], 8);
        add_action('template_redirect', [$this->taxonomies, 'render_not_found_for_unextracted_publisher'], 0);
        add_action('init', [$this->meta, 'register_meta_fields'], 11);
        $this->meta->register_rest_file_id_query();
        add_action('init', [$this->intake, 'register'], 11);
        add_action('init', [$this->shortcodes, 'register'], 12);
        $this->intelligence_projection->register();
        add_action('init', [$this->meta, 'backfill_report_contracts'], 13);
        add_action('init', [self::class, 'migrate_site_identity'], 14);
        add_action('init', [self::class, 'migrate_public_discovery'], 15);
        add_action('pre_get_posts', [$this->post_type, 'filter_frontend_queries']);
        add_filter('wp_sitemaps_enabled', '__return_true');
        add_filter('wp_robots', [self::class, 'public_robots']);
        add_filter('the_content', [self::class, 'redact_publication_operator_metadata'], 8);
        add_action('wp_head', [self::class, 'render_public_metadata'], 1);
        $this->media_proxy->register();
        $this->content_formatting->register();

        foreach (Post_Type::report_post_types() as $post_type) {
            add_action('save_post_' . $post_type, [$this->meta, 'sync_report_contract'], 20, 3);
        }

        $this->booted = true;
    }

    public static function activate(): void
    {
        $plugin = self::instance();
        $plugin->post_type->register();
        $plugin->taxonomies->register();
        $plugin->meta->register_meta_fields();
        $plugin->meta->backfill_report_contracts();
        flush_rewrite_rules();
    }

    public static function deactivate(): void
    {
        flush_rewrite_rules();
    }

    /**
     * Migrates only known legacy project identity values.
     */
    public static function migrate_site_identity(): void
    {
        $legacy_names = [
            'Market Lense',
            'Market Lense – Your Market Insights Navigator',
            'Market Lense - Your Market Insights Navigator',
        ];
        $current_name = trim((string) get_option('blogname', ''));
        if (in_array($current_name, $legacy_names, true)) {
            update_option('blogname', 'Market Bearing');
        }

        $current_tagline = trim((string) get_option('blogdescription', ''));
        if ($current_tagline === '' || $current_tagline === 'Your Market Insights Navigator') {
            update_option(
                'blogdescription',
                'The governed intelligence layer for published market research.'
            );
        }
    }

    /**
     * Restores public indexing for the production research portal.
     */
    public static function migrate_public_discovery(): void
    {
        $migration = '2026-06-07-public-discovery';
        if ((string) get_option('marketlense_public_discovery_version', '') === $migration) {
            return;
        }

        update_option('blog_public', '1');
        update_option('marketlense_public_discovery_version', $migration, false);
    }

    /**
     * @param array<string,bool> $robots
     * @return array<string,bool>
     */
    public static function public_robots(array $robots): array
    {
        unset($robots['noindex'], $robots['nofollow']);
        $robots['index'] = true;
        $robots['follow'] = true;

        return $robots;
    }

    /**
     * Keeps legacy publish bookkeeping out of public entity content while preserving it for editors.
     */
    public static function redact_publication_operator_metadata(string $content): string
    {
        if (is_admin() || ! in_array(get_post_type(get_the_ID()), Post_Type::report_post_types(), true)) {
            return $content;
        }

        $redacted = preg_replace(
            [
                '#<script\\b[^>]*\\bdata-market-lense-(?:publish-entity|cross-report-metadata)=["\\\']true["\\\'][^>]*>.*?</script>#is',
                '#<p\\b[^>]*\\bhidden(?:=[^\\s>]*)?[^>]*>\\s*Drive fileId:\\s*[^<]+</p>#is',
                '#<footer\\b[^>]*\\bclass=["\\\'][^"\\\']*\\bfooter\\b[^"\\\']*["\\\'][^>]*>\\s*Generated by Market Lense\\.\\s*File ID:\\s*<code>[^<]+</code>\\.\\s*</footer>#is',
                '#\\s*Drive fileId:\\s*[A-Za-z0-9._:-]+#i',
            ],
            '',
            $content
        );

        return is_string($redacted) ? $redacted : $content;
    }

    /**
     * Emits public SEO and social metadata for first-party pages and entity surfaces.
     */
    public static function render_public_metadata(): void
    {
        if (is_admin() || is_feed() || is_robots() || is_trackback()) {
            return;
        }

        $metadata = self::public_metadata();
        if ($metadata['description'] === '' || $metadata['canonical'] === '') {
            return;
        }

        echo "\n" . '<meta name="description" content="' . esc_attr($metadata['description']) . '">' . "\n";
        echo '<link rel="canonical" href="' . esc_url($metadata['canonical']) . '">' . "\n";
        echo '<meta property="og:type" content="' . esc_attr($metadata['type']) . '">' . "\n";
        echo '<meta property="og:title" content="' . esc_attr($metadata['title']) . '">' . "\n";
        echo '<meta property="og:description" content="' . esc_attr($metadata['description']) . '">' . "\n";
        echo '<meta property="og:url" content="' . esc_url($metadata['canonical']) . '">' . "\n";
        echo '<meta property="og:site_name" content="' . esc_attr(get_bloginfo('name')) . '">' . "\n";
        if ($metadata['image'] !== '') {
            echo '<meta property="og:image" content="' . esc_url($metadata['image']) . '">' . "\n";
        }
        echo '<meta name="twitter:card" content="' . esc_attr($metadata['image'] !== '' ? 'summary_large_image' : 'summary') . '">' . "\n";
        echo '<meta name="twitter:title" content="' . esc_attr($metadata['title']) . '">' . "\n";
        echo '<meta name="twitter:description" content="' . esc_attr($metadata['description']) . '">' . "\n";
        if ($metadata['image'] !== '') {
            echo '<meta name="twitter:image" content="' . esc_url($metadata['image']) . '">' . "\n";
        }
    }

    /**
     * @return array{title:string,description:string,canonical:string,type:string,image:string}
     */
    private static function public_metadata(): array
    {
        $site_name = trim((string) get_bloginfo('name'));
        $site_description = self::trim_description((string) get_bloginfo('description'));
        $title = trim((string) wp_get_document_title());
        $description = $site_description;
        $canonical = self::current_canonical_url();
        $type = 'website';
        $image = '';

        if (is_front_page() || is_home()) {
            $title = $site_name;
            $description = $site_description !== '' ? $site_description : __('Governed market research, signals, and executive briefings.', 'marketlense-core');
            $canonical = home_url('/');
        } elseif (is_post_type_archive(Post_Type::POST_TYPE)) {
            $title = __('Reports', 'marketlense-core') . ' - ' . $site_name;
            $description = __('Browse governed market research reports with publisher, topic, region, and period filters.', 'marketlense-core');
            $archive = get_post_type_archive_link(Post_Type::POST_TYPE);
            $canonical = is_string($archive) ? $archive : $canonical;
        } elseif (is_post_type_archive(Post_Type::BRIEFING_POST_TYPE)) {
            $title = __('Briefings', 'marketlense-core') . ' - ' . $site_name;
            $description = __('Read executive briefings synthesized from governed market research evidence.', 'marketlense-core');
            $archive = get_post_type_archive_link(Post_Type::BRIEFING_POST_TYPE);
            $canonical = is_string($archive) ? $archive : $canonical;
        } elseif (is_post_type_archive(Post_Type::SIGNAL_POST_TYPE)) {
            $title = __('Signals', 'marketlense-core') . ' - ' . $site_name;
            $description = __('Track market signals backed by source-linked evidence and confidence metadata.', 'marketlense-core');
            $archive = get_post_type_archive_link(Post_Type::SIGNAL_POST_TYPE);
            $canonical = is_string($archive) ? $archive : $canonical;
        } elseif (is_category()) {
            $term = get_queried_object();
            if ($term instanceof \WP_Term) {
                $title = $term->name . ' - ' . $site_name;
                $term_description = self::trim_description((string) term_description($term->term_id, $term->taxonomy));
                $description = $term_description !== '' ? $term_description : sprintf(__('Market research for %s.', 'marketlense-core'), $term->name);
                $term_link = get_term_link($term);
                if (is_string($term_link)) {
                    $canonical = $term_link;
                }
            }
        } elseif (is_singular()) {
            $post = get_post();
            if ($post instanceof \WP_Post) {
                $title = get_the_title($post) . ' - ' . $site_name;
                $description = self::post_public_description($post, $site_description);
                $canonical = (string) get_permalink($post);
                $type = in_array($post->post_type, [Post_Type::POST_TYPE, Post_Type::BRIEFING_POST_TYPE, Post_Type::SIGNAL_POST_TYPE, Post_Type::CORE_POST_TYPE], true) ? 'article' : 'website';
                $image = self::post_social_image($post);
            }
        }

        return [
            'title' => self::trim_description($title, 90),
            'description' => self::trim_description($description),
            'canonical' => $canonical,
            'type' => $type,
            'image' => $image,
        ];
    }

    private static function post_public_description(\WP_Post $post, string $fallback): string
    {
        $excerpt = trim((string) get_the_excerpt($post));
        if ($excerpt !== '') {
            return self::trim_description($excerpt);
        }
        $content = wp_strip_all_tags(strip_shortcodes((string) $post->post_content));
        if (trim($content) !== '') {
            return self::trim_description($content);
        }
        return self::trim_description($fallback);
    }

    private static function post_social_image(\WP_Post $post): string
    {
        if (! has_post_thumbnail($post)) {
            return '';
        }
        $image = wp_get_attachment_image_url((int) get_post_thumbnail_id($post), 'large');
        return is_string($image) ? $image : '';
    }

    private static function trim_description(string $value, int $max_length = 160): string
    {
        $text = trim(preg_replace('/\s+/', ' ', wp_strip_all_tags($value)) ?: '');
        if (strlen($text) <= $max_length) {
            return $text;
        }
        return rtrim(substr($text, 0, $max_length - 3)) . '...';
    }

    private static function current_canonical_url(): string
    {
        $canonical = wp_get_canonical_url();
        if (is_string($canonical) && $canonical !== '') {
            return $canonical;
        }
        global $wp;
        $request = isset($wp->request) ? (string) $wp->request : '';
        return $request !== '' ? home_url('/' . ltrim($request, '/')) : home_url('/');
    }
}
