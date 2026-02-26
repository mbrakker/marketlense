<?php
/**
 * Header template.
 *
 * @package MarketLenseTheme
 */

if (! defined('ABSPATH')) {
    exit;
}
?><!doctype html>
<html <?php language_attributes(); ?>>
<head>
    <meta charset="<?php bloginfo('charset'); ?>">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>
<header class="site-header">
    <div class="site-branding">
        <a href="<?php echo esc_url(home_url('/')); ?>" rel="home"><?php bloginfo('name'); ?></a>
        <p><?php bloginfo('description'); ?></p>
    </div>
    <nav class="site-navigation" aria-label="<?php esc_attr_e('Primary menu', 'marketlense-theme'); ?>">
        <?php
        wp_nav_menu(
            [
                'theme_location' => 'primary',
                'fallback_cb' => false,
                'container' => false,
            ]
        );
        ?>
    </nav>
</header>
<main class="site-main">
