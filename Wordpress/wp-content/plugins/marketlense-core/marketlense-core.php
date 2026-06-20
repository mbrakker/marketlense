<?php
/**
 * Plugin Name: Market Bearing Core
 * Plugin URI: https://marketlense.local
 * Description: Core WordPress domain layer for governed reports, signals, briefings, taxonomies, and evidence counters.
 * Version: 1.6.6
 * Author: Market Bearing
 * Author URI: https://marketlense.local
 * Requires at least: 6.6
 * Requires PHP: 8.2
 * Text Domain: marketlense-core
 * License: GPLv2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

if (! defined('ABSPATH')) {
    exit;
}

define('MARKETLENSE_CORE_VERSION', '1.6.6');
define('MARKETLENSE_CORE_PATH', plugin_dir_path(__FILE__));
define('MARKETLENSE_CORE_URL', plugin_dir_url(__FILE__));

require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-plugin.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-post-type.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-taxonomies.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-content-parser.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-content-formatting.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-meta.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-media-proxy.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-report-view-model-builder.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-intelligence-stats.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-report-card-renderer.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-briefing-card-view-model-builder.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-briefing-card-renderer.php';
require_once MARKETLENSE_CORE_PATH . 'includes/class-marketlense-core-shortcodes.php';

register_activation_hook(__FILE__, ['\\MarketLense\\Core\\Plugin', 'activate']);
register_deactivation_hook(__FILE__, ['\\MarketLense\\Core\\Plugin', 'deactivate']);

add_action(
    'plugins_loaded',
    static function (): void {
        \MarketLense\Core\Plugin::instance()->boot();
    }
);
