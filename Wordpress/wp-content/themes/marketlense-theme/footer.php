<?php
/**
 * Footer template.
 *
 * @package MarketLenseTheme
 */

if (! defined('ABSPATH')) {
    exit;
}
?>
</main>
<footer class="site-footer">
    <p>
        <?php
        echo esc_html(
            sprintf(
                /* translators: %d: current year. */
                __('%d Market Lense. All rights reserved.', 'marketlense-theme'),
                (int) gmdate('Y')
            )
        );
        ?>
    </p>
</footer>
<?php wp_footer(); ?>
</body>
</html>
