<?php
/**
 * Title: ML - Latest Reports
 * Slug: marketlense/report-grid
 * Categories: marketlense-home, marketlense-reports
 * Inserter: yes
 */
?>
<!-- wp:group {"className":"ml-home-section ml-latest-reports reveal","layout":{"type":"constrained"}} -->
<div class="wp-block-group ml-home-section ml-latest-reports reveal">
  <!-- wp:group {"className":"ml-section-heading","layout":{"type":"flex","justifyContent":"space-between","flexWrap":"wrap","verticalAlignment":"center"}} -->
  <div class="wp-block-group ml-section-heading">
    <!-- wp:group {"layout":{"type":"constrained"}} -->
    <div class="wp-block-group">
      <!-- wp:paragraph {"className":"ml-section-kicker"} -->
      <p class="ml-section-kicker">Latest coverage</p>
      <!-- /wp:paragraph -->
      <!-- wp:heading {"level":2} -->
      <h2 class="wp-block-heading">Latest Reports</h2>
      <!-- /wp:heading -->
    </div>
    <!-- /wp:group -->

    <!-- wp:paragraph {"className":"ml-inline-link"} -->
    <p class="ml-inline-link"><a href="<?php echo esc_url((string) (get_post_type_archive_link('ml_report') ?: home_url('/reports/'))); ?>">View all reports <span aria-hidden="true">&rarr;</span></a></p>
    <!-- /wp:paragraph -->
  </div>
  <!-- /wp:group -->

  <!-- wp:shortcode -->
  [ml_report_browser per_page="6" show_filters="0" show_pagination="0" context="auto"]
  <!-- /wp:shortcode -->
</div>
<!-- /wp:group -->
