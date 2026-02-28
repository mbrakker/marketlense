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

    private Report_View_Model_Builder $view_model_builder;

    private Intelligence_Stats $stats;

    private Shortcodes $shortcodes;

    private function __construct()
    {
        $parser = new Content_Parser();
        $this->post_type = new Post_Type();
        $this->taxonomies = new Taxonomies();
        $this->meta = new Meta($parser);
        $this->view_model_builder = new Report_View_Model_Builder();
        $this->stats = new Intelligence_Stats();
        $this->shortcodes = new Shortcodes($this->view_model_builder, $this->stats);
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
        add_action('save_post_' . Post_Type::POST_TYPE, [$this->meta, 'sync_report_contract'], 20, 3);

        $this->booted = true;
    }

    public static function activate(): void
    {
        $plugin = self::instance();
        $plugin->post_type->register();
        $plugin->taxonomies->register();
        $plugin->meta->register_meta_fields();
        flush_rewrite_rules();
    }

    public static function deactivate(): void
    {
        flush_rewrite_rules();
    }
}
