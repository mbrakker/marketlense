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

  <!-- wp:query {"queryId":21,"query":{"perPage":"6","pages":0,"offset":0,"postType":"ml_report","order":"desc","orderBy":"date","author":"","search":"","exclude":[],"sticky":"","inherit":false},"displayLayout":{"type":"grid","columns":3},"className":"ml-report-query"} -->
  <div class="wp-block-query ml-report-query">
    <!-- wp:post-template -->
    <!-- wp:group {"className":"ml-report-card","layout":{"type":"constrained"}} -->
    <div class="wp-block-group ml-report-card">
      <!-- wp:post-featured-image {"isLink":true} /-->
      <!-- wp:post-date {"fontSize":"xs","textColor":"ink-soft"} /-->
      <!-- wp:post-title {"isLink":true,"level":3} /-->
      <!-- wp:post-terms {"term":"ml_publisher","className":"ml-chip-terms"} /-->
      <!-- wp:post-excerpt {"moreText":"Read digest"} /-->
    </div>
    <!-- /wp:group -->
    <!-- /wp:post-template -->

    <!-- wp:query-no-results -->
    <!-- wp:paragraph {"className":"ml-query-empty"} -->
    <p class="ml-query-empty">No reports are available yet.</p>
    <!-- /wp:paragraph -->
    <!-- /wp:query-no-results -->
  </div>
  <!-- /wp:query -->
</div>
<!-- /wp:group -->
