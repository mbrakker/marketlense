<?php
/**
 * Custom post type registration.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Post_Type
{
    public const POST_TYPE = 'ml_report';

    public function register(): void
    {
        register_post_type(
            self::POST_TYPE,
            [
                'labels' => [
                    'name'                  => __('Reports', 'marketlense-core'),
                    'singular_name'         => __('Report', 'marketlense-core'),
                    'add_new'               => __('Add New Report', 'marketlense-core'),
                    'add_new_item'          => __('Add New Report', 'marketlense-core'),
                    'edit_item'             => __('Edit Report', 'marketlense-core'),
                    'new_item'              => __('New Report', 'marketlense-core'),
                    'view_item'             => __('View Report', 'marketlense-core'),
                    'view_items'            => __('View Reports', 'marketlense-core'),
                    'search_items'          => __('Search Reports', 'marketlense-core'),
                    'not_found'             => __('No reports found.', 'marketlense-core'),
                    'not_found_in_trash'    => __('No reports found in trash.', 'marketlense-core'),
                    'all_items'             => __('All Reports', 'marketlense-core'),
                    'archives'              => __('Report Archives', 'marketlense-core'),
                    'attributes'            => __('Report Attributes', 'marketlense-core'),
                    'featured_image'        => __('Report Cover Image', 'marketlense-core'),
                    'set_featured_image'    => __('Set cover image', 'marketlense-core'),
                    'remove_featured_image' => __('Remove cover image', 'marketlense-core'),
                    'menu_name'             => __('Market Lense Reports', 'marketlense-core'),
                ],
                'public'              => true,
                'show_ui'             => true,
                'show_in_menu'        => true,
                'show_in_rest'        => true,
                'rest_base'           => self::POST_TYPE,
                'menu_position'       => 20,
                'menu_icon'           => 'dashicons-chart-area',
                'supports'            => ['title', 'editor', 'excerpt', 'thumbnail', 'revisions', 'author', 'custom-fields'],
                'has_archive'         => true,
                'rewrite'             => [
                    'slug'       => 'reports',
                    'with_front' => false,
                ],
                'hierarchical'        => false,
                'taxonomies'          => ['category', 'post_tag', Taxonomies::PUBLISHER_TAXONOMY],
                'exclude_from_search' => false,
                'publicly_queryable'  => true,
                'query_var'           => true,
                'capability_type'     => 'post',
                'map_meta_cap'        => true,
            ]
        );
    }
}
