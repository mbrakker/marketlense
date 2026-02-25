<?php
/**
 * Theme setup and asset loading for Market Lense theme.
 *
 * @package MarketLenseTheme
 */

if (! defined('ABSPATH')) {
    exit;
}

function marketlense_theme_setup(): void
{
    add_theme_support('title-tag');
    add_theme_support('post-thumbnails');
    add_theme_support('html5', ['search-form', 'comment-form', 'comment-list', 'gallery', 'caption', 'style', 'script']);
    add_theme_support('custom-logo');
    register_nav_menus(
        [
            'primary' => __('Primary Menu', 'marketlense-theme'),
        ]
    );
}
add_action('after_setup_theme', 'marketlense_theme_setup');

function marketlense_enqueue_assets(): void
{
    $theme = wp_get_theme();

    wp_enqueue_style(
        'marketlense-theme-main',
        get_stylesheet_uri(),
        [],
        $theme->get('Version')
    );

    wp_enqueue_style(
        'marketlense-theme-layout',
        get_template_directory_uri() . '/assets/css/main.css',
        ['marketlense-theme-main'],
        $theme->get('Version')
    );
}
add_action('wp_enqueue_scripts', 'marketlense_enqueue_assets');
