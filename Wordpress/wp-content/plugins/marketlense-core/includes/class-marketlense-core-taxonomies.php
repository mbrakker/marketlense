<?php
/**
 * Taxonomy registration.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Taxonomies
{
    public const TOPIC_TAXONOMY = 'ml_topic';

    public const PUBLISHER_TAXONOMY = 'ml_publisher';

    public function register(): void
    {
        register_taxonomy(
            self::TOPIC_TAXONOMY,
            [Post_Type::POST_TYPE],
            [
                'labels' => [
                    'name'          => __('Topics', 'marketlense-core'),
                    'singular_name' => __('Topic', 'marketlense-core'),
                    'search_items'  => __('Search Topics', 'marketlense-core'),
                    'all_items'     => __('All Topics', 'marketlense-core'),
                    'edit_item'     => __('Edit Topic', 'marketlense-core'),
                    'update_item'   => __('Update Topic', 'marketlense-core'),
                    'add_new_item'  => __('Add New Topic', 'marketlense-core'),
                    'new_item_name' => __('New Topic Name', 'marketlense-core'),
                    'menu_name'     => __('Topics', 'marketlense-core'),
                ],
                'public'            => true,
                'show_ui'           => true,
                'show_in_menu'      => true,
                'show_admin_column' => true,
                'show_in_rest'      => true,
                'rest_base'         => self::TOPIC_TAXONOMY,
                'hierarchical'      => false,
                'query_var'         => true,
                'rewrite'           => [
                    'slug'       => 'topic',
                    'with_front' => false,
                ],
            ]
        );

        register_taxonomy(
            self::PUBLISHER_TAXONOMY,
            [Post_Type::POST_TYPE],
            [
                'labels' => [
                    'name'          => __('Publishers', 'marketlense-core'),
                    'singular_name' => __('Publisher', 'marketlense-core'),
                    'search_items'  => __('Search Publishers', 'marketlense-core'),
                    'all_items'     => __('All Publishers', 'marketlense-core'),
                    'edit_item'     => __('Edit Publisher', 'marketlense-core'),
                    'update_item'   => __('Update Publisher', 'marketlense-core'),
                    'add_new_item'  => __('Add New Publisher', 'marketlense-core'),
                    'new_item_name' => __('New Publisher Name', 'marketlense-core'),
                    'menu_name'     => __('Publishers', 'marketlense-core'),
                ],
                'public'            => true,
                'show_ui'           => true,
                'show_in_menu'      => true,
                'show_admin_column' => true,
                'show_in_rest'      => true,
                'rest_base'         => self::PUBLISHER_TAXONOMY,
                'hierarchical'      => false,
                'query_var'         => true,
                'rewrite'           => [
                    'slug'       => 'publisher',
                    'with_front' => false,
                ],
            ]
        );

        register_taxonomy_for_object_type('category', Post_Type::POST_TYPE);
        register_taxonomy_for_object_type('post_tag', Post_Type::POST_TYPE);
    }
}
