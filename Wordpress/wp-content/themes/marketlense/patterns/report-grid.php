<?php
/**
 * Title: ML - Latest Reports
 * Slug: marketlense/report-grid
 * Categories: marketlense-home, marketlense-reports
 * Inserter: yes
 */
?>
<!-- wp:group {"className":"ml-home-section ml-latest-reports reveal","layout":{"type":"default"}} -->
<div class="wp-block-group ml-home-section ml-latest-reports reveal">
  <!-- wp:group {"className":"ml-section-heading","layout":{"type":"flex","justifyContent":"space-between","flexWrap":"wrap","verticalAlignment":"center"}} -->
  <div class="wp-block-group ml-section-heading">
    <!-- wp:group {"className":"ml-section-anchor","layout":{"type":"default"}} -->
    <div class="wp-block-group ml-section-anchor">
      <!-- wp:paragraph {"className":"ml-section-kicker ml-section-eyebrow"} -->
      <p class="ml-section-kicker ml-section-eyebrow">ARCHIVE</p>
      <!-- /wp:paragraph -->
      <!-- wp:heading {"level":2,"className":"ml-section-title"} -->
      <h2 class="wp-block-heading ml-section-title">Latest Reports</h2>
      <!-- /wp:heading -->
      <!-- wp:html -->
      <span class="ml-section-rule" aria-hidden="true"></span>
      <!-- /wp:html -->
    </div>
    <!-- /wp:group -->

    <!-- wp:paragraph {"className":"ml-inline-link"} -->
    <p class="ml-inline-link"><a href="<?php echo esc_url((string) (get_post_type_archive_link('ml_report') ?: home_url('/reports/'))); ?>">View all reports <span class="ml-link-arrow" aria-hidden="true">&rarr;</span></a></p>
    <!-- /wp:paragraph -->
  </div>
  <!-- /wp:group -->

  <!-- wp:shortcode -->
  [ml_latest_reports limit="6"]
  <!-- /wp:shortcode -->
</div>
<!-- /wp:group -->
