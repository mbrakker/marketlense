<?php
/**
 * Front page template.
 *
 * @package MarketLenseTheme
 */

if (! defined('ABSPATH')) {
    exit;
}

get_header();
?>
<section>
    <h1><?php bloginfo('name'); ?></h1>
    <p><?php bloginfo('description'); ?></p>
</section>

<?php
if (have_posts()) {
    while (have_posts()) {
        the_post();
        get_template_part('template-parts/content');
    }
}

get_footer();
