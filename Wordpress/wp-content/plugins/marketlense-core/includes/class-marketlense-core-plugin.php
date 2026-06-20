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
        $this->stats = new Intelligence_Stats($this->view_model_builder);
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
        add_action('init', [$this->meta, 'register_meta_fields'], 11);
        add_action('init', [$this->shortcodes, 'register'], 12);
        add_action('init', [$this->meta, 'backfill_report_contracts'], 13);
        add_action('init', [self::class, 'migrate_site_identity'], 14);
        add_action('init', [self::class, 'migrate_public_discovery'], 15);
        add_action('pre_get_posts', [$this->post_type, 'filter_frontend_queries']);
        add_filter('wp_sitemaps_enabled', '__return_true');
        add_filter('wp_robots', [self::class, 'public_robots']);
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
}
