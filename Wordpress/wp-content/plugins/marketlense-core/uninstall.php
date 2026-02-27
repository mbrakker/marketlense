<?php
/**
 * Plugin uninstall handler.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

if (! defined('WP_UNINSTALL_PLUGIN')) {
    exit;
}

$meta_keys = [
    'ml_file_id',
    'ml_publisher_name',
    'ml_time_period',
    'ml_region',
];

foreach ($meta_keys as $meta_key) {
    delete_post_meta_by_key($meta_key);
}

delete_metadata('term', 0, 'ml_publisher_homepage', '', true);
