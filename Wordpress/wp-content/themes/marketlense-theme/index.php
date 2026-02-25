<?php
/**
 * Main fallback template.
 *
 * @package MarketLenseTheme
 */

if (! defined('ABSPATH')) {
    exit;
}

get_header();

if (have_posts()) {
    while (have_posts()) {
        the_post();
        get_template_part('template-parts/content');
    }

    the_posts_pagination();
} else {
    ?>
    <article>
        <h1><?php esc_html_e('No content found', 'marketlense-theme'); ?></h1>
        <p><?php esc_html_e('Start by creating your first post in WordPress admin.', 'marketlense-theme'); ?></p>
    </article>
    <?php
}

get_footer();
