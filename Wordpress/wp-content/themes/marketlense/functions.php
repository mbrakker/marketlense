<?php
/**
 * Theme bootstrap for Market Lense block theme.
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

    register_nav_menus(
        [
            'primary' => __('Primary Navigation', 'marketlense'),
            'footer'  => __('Footer Navigation', 'marketlense'),
        ]
    );
}
add_action('after_setup_theme', 'marketlense_setup');

/**
 * Enqueues frontend assets.
 */
function marketlense_enqueue_assets(): void
{
    $theme = wp_get_theme();
    $version = $theme->get('Version');

    wp_enqueue_style(
        'marketlense',
        get_template_directory_uri() . '/assets/css/theme.css',
        [],
        $version
    );

    if (is_singular('ml_report')) {
        wp_enqueue_script(
            'marketlense-report-interactions',
            get_template_directory_uri() . '/assets/js/report-interactions.js',
            [],
            $version,
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
        ['label' => __('Market Lense Home', 'marketlense')]
    );

    register_block_pattern_category(
        'marketlense-reports',
        ['label' => __('Market Lense Reports', 'marketlense')]
    );

    register_block_pattern_category(
        'marketlense-pages',
        ['label' => __('Market Lense Pages', 'marketlense')]
    );
}
add_action('init', 'marketlense_register_pattern_categories');
