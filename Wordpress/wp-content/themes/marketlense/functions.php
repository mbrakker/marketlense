<?php
/**
 * Theme bootstrap for Market Bearing block theme.
 *
 * @package MarketLense
 */

declare(strict_types=1);

if (! defined('ABSPATH')) {
    exit;
}

/**
 * Registers core supports used by the block theme.
 */
function marketlense_setup(): void
{
    add_theme_support('wp-block-styles');
    add_theme_support('editor-styles');
    add_theme_support('responsive-embeds');
    add_theme_support('post-thumbnails');

    add_editor_style('assets/css/theme.css');
}
add_action('after_setup_theme', 'marketlense_setup');

/**
 * Shows an admin notice when the companion plugin is unavailable.
 */
function marketlense_require_core_plugin_notice(): void
{
    if (! current_user_can('activate_plugins')) {
        return;
    }

    if (class_exists('\\MarketLense\\Core\\Plugin')) {
        return;
    }

    printf(
        '<div class="notice notice-error"><p>%s</p></div>',
        esc_html__(
            'Market Bearing theme requires the Market Bearing Core plugin for report archives, homepage intelligence sections, and directory shortcodes.',
            'marketlense'
        )
    );
}
add_action('admin_notices', 'marketlense_require_core_plugin_notice');

/**
 * Resolves a cache-busting version for theme assets.
 */
function marketlense_asset_version(string $relative_path): string
{
    $theme = wp_get_theme();
    $theme_version = (string) $theme->get('Version');
    $asset_path = get_theme_file_path($relative_path);
    $modified = @filemtime($asset_path);

    if ($modified === false) {
        return $theme_version;
    }

    return $theme_version . '.' . (string) $modified;
}

/**
 * Enqueues frontend assets.
 */
function marketlense_enqueue_assets(): void
{
    $theme_css_version = marketlense_asset_version('assets/css/theme.css');
    $reveal_js_version = marketlense_asset_version('assets/js/reveal.js');

    wp_enqueue_style(
        'marketlense',
        get_template_directory_uri() . '/assets/css/theme.css',
        [],
        $theme_css_version
    );

    wp_enqueue_script(
        'marketlense-reveal',
        get_template_directory_uri() . '/assets/js/reveal.js',
        [],
        $reveal_js_version,
        true
    );

    if (is_singular(['ml_report', 'ml_briefing', 'post'])) {
        wp_enqueue_script(
            'marketlense-report-interactions',
            get_template_directory_uri() . '/assets/js/report-interactions.js',
            [],
            marketlense_asset_version('assets/js/report-interactions.js'),
            true
        );
    }
}
add_action('wp_enqueue_scripts', 'marketlense_enqueue_assets');

/**
 * Registers block pattern categories used by the theme.
 */
function marketlense_register_pattern_categories(): void
{
    register_block_pattern_category(
        'marketlense-home',
        ['label' => __('Market Bearing Home', 'marketlense')]
    );

    register_block_pattern_category(
        'marketlense-reports',
        ['label' => __('Market Bearing Reports', 'marketlense')]
    );

    register_block_pattern_category(
        'marketlense-pages',
        ['label' => __('Market Bearing Pages', 'marketlense')]
    );
}
add_action('init', 'marketlense_register_pattern_categories');

/**
 * Removes the known legacy Site Editor header override so the theme file can render.
 */
function marketlense_refresh_legacy_header_override(): void
{
    $migration_version = '2026-06-06-market-bearing-header';
    if ((string) get_option('marketlense_header_override_version', '') === $migration_version) {
        return;
    }

    $headers = get_posts(
        [
            'post_type' => 'wp_template_part',
            'post_status' => ['publish', 'draft'],
            'name' => 'header',
            'posts_per_page' => -1,
            'no_found_rows' => true,
            'tax_query' => [
                [
                    'taxonomy' => 'wp_theme',
                    'field' => 'slug',
                    'terms' => ['marketlense'],
                ],
            ],
        ]
    );

    foreach ($headers as $header) {
        if (! ($header instanceof \WP_Post)) {
            continue;
        }

        $content = (string) $header->post_content;
        $is_legacy = str_contains($content, 'wp:site-title')
            || str_contains($content, 'Market Lense');
        if ($is_legacy && ! str_contains($content, '[ml_brand_logo]')) {
            wp_delete_post($header->ID, true);
        }
    }

    update_option('marketlense_header_override_version', $migration_version, false);
}
add_action('init', 'marketlense_refresh_legacy_header_override', 30);
