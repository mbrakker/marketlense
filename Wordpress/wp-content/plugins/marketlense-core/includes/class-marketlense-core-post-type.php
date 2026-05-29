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

    public const SIGNAL_POST_TYPE = 'ml_signal';

    public const BRIEFING_POST_TYPE = 'ml_briefing';

    public const CORE_POST_TYPE = 'post';

    /**
     * @return list<string>
     */
    public static function report_post_types(): array
    {
        return [self::POST_TYPE, self::CORE_POST_TYPE];
    }

    public static function is_report_post_type(string $post_type): bool
    {
        return in_array($post_type, self::report_post_types(), true);
    }

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

        register_post_type(
            self::SIGNAL_POST_TYPE,
            [
                'labels' => [
                    'name'               => __('Signals', 'marketlense-core'),
                    'singular_name'      => __('Signal', 'marketlense-core'),
                    'add_new'            => __('Add New Signal', 'marketlense-core'),
                    'add_new_item'       => __('Add New Signal', 'marketlense-core'),
                    'edit_item'          => __('Edit Signal', 'marketlense-core'),
                    'new_item'           => __('New Signal', 'marketlense-core'),
                    'view_item'          => __('View Signal', 'marketlense-core'),
                    'view_items'         => __('View Signals', 'marketlense-core'),
                    'search_items'       => __('Search Signals', 'marketlense-core'),
                    'not_found'          => __('No signals found.', 'marketlense-core'),
                    'not_found_in_trash' => __('No signals found in trash.', 'marketlense-core'),
                    'all_items'          => __('All Signals', 'marketlense-core'),
                    'archives'           => __('Signal Archives', 'marketlense-core'),
                    'attributes'         => __('Signal Attributes', 'marketlense-core'),
                    'menu_name'          => __('Market Lense Signals', 'marketlense-core'),
                ],
                'public'              => true,
                'show_ui'             => true,
                'show_in_menu'        => true,
                'show_in_rest'        => true,
                'rest_base'           => self::SIGNAL_POST_TYPE,
                'menu_position'       => 21,
                'menu_icon'           => 'dashicons-lightbulb',
                'supports'            => ['title', 'editor', 'excerpt', 'revisions', 'author', 'custom-fields'],
                'has_archive'         => true,
                'rewrite'             => [
                    'slug'       => 'signals',
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

        register_post_type(
            self::BRIEFING_POST_TYPE,
            [
                'labels' => [
                    'name'                  => __('Briefings', 'marketlense-core'),
                    'singular_name'         => __('Briefing', 'marketlense-core'),
                    'add_new'               => __('Add New Briefing', 'marketlense-core'),
                    'add_new_item'          => __('Add New Briefing', 'marketlense-core'),
                    'edit_item'             => __('Edit Briefing', 'marketlense-core'),
                    'new_item'              => __('New Briefing', 'marketlense-core'),
                    'view_item'             => __('View Briefing', 'marketlense-core'),
                    'view_items'            => __('View Briefings', 'marketlense-core'),
                    'search_items'          => __('Search Briefings', 'marketlense-core'),
                    'not_found'             => __('No briefings found.', 'marketlense-core'),
                    'not_found_in_trash'    => __('No briefings found in trash.', 'marketlense-core'),
                    'all_items'             => __('All Briefings', 'marketlense-core'),
                    'archives'              => __('Briefing Archives', 'marketlense-core'),
                    'attributes'            => __('Briefing Attributes', 'marketlense-core'),
                    'featured_image'        => __('Briefing Cover Image', 'marketlense-core'),
                    'set_featured_image'    => __('Set cover image', 'marketlense-core'),
                    'remove_featured_image' => __('Remove cover image', 'marketlense-core'),
                    'menu_name'             => __('Market Lense Briefings', 'marketlense-core'),
                ],
                'public'              => true,
                'show_ui'             => true,
                'show_in_menu'        => true,
                'show_in_rest'        => true,
                'rest_base'           => self::BRIEFING_POST_TYPE,
                'menu_position'       => 22,
                'menu_icon'           => 'dashicons-welcome-write-blog',
                'supports'            => ['title', 'editor', 'excerpt', 'thumbnail', 'revisions', 'author', 'custom-fields'],
                'has_archive'         => true,
                'rewrite'             => [
                    'slug'       => 'briefings',
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

    /**
     * Normalizes front-end queries onto the report CPT so native block query
     * loops can inherit the expected result set.
     */
    public function filter_frontend_queries(\WP_Query $query): void
    {
        if (is_admin() || ! $query->is_main_query()) {
            return;
        }

        if (
            $query->is_post_type_archive(self::POST_TYPE)
            || $query->is_tax(Taxonomies::PUBLISHER_TAXONOMY)
            || $query->is_category()
            || $query->is_search()
        ) {
            $digest_query_args = Meta::apply_digest_query_constraints(
                [
                    'post_type' => self::report_post_types(),
                    'meta_query' => $query->get('meta_query'),
                ]
            );

            $query->set('post_type', $digest_query_args['post_type']);
            $query->set('meta_query', $digest_query_args['meta_query']);
            $query->set('orderby', 'date');
            $query->set('order', 'DESC');
        }
    }
}
