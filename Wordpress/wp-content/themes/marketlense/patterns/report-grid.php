<?php
/**
 * Title: Report grid
 * Slug: marketlense/report-grid
 * Categories: marketlense-reports
 * Inserter: yes
 */
?>
<!-- wp:group {"layout":{"type":"constrained"}} -->
<div class="wp-block-group">
  <!-- wp:group {"layout":{"type":"flex","justifyContent":"space-between","verticalAlignment":"center"}} -->
  <div class="wp-block-group">
    <!-- wp:heading {"level":2} -->
    <h2 class="wp-block-heading">Latest reports</h2>
    <!-- /wp:heading -->
    <!-- wp:button {"className":"is-style-outline"} -->
    <div class="wp-block-button is-style-outline"><a class="wp-block-button__link wp-element-button" href="/ml_report/">View all</a></div>
    <!-- /wp:button -->
  </div>
  <!-- /wp:group -->

  <!-- wp:query {"queryId":11,"query":{"perPage":"9","pages":0,"offset":0,"postType":"ml_report","order":"desc","orderBy":"date","author":"","search":"","exclude":[],"sticky":"","inherit":false},"className":"ml-report-grid"} -->
  <div class="wp-block-query ml-report-grid">
    <!-- wp:post-template -->
    <!-- wp:group {"className":"ml-report-card","layout":{"type":"constrained"}} -->
    <div class="wp-block-group ml-report-card">
      <!-- wp:post-featured-image {"isLink":true} /-->
      <!-- wp:post-title {"isLink":true,"level":3} /-->
      <!-- wp:post-date {"fontSize":"xs"} /-->
      <!-- wp:post-terms {"term":"ml_publisher","className":"ml-chip-terms"} /-->
      <!-- wp:post-terms {"term":"ml_topic","className":"ml-chip-terms"} /-->
      <!-- wp:post-excerpt {"moreText":"Open digest","showMoreOnNewLine":false} /-->
    </div>
    <!-- /wp:group -->
    <!-- /wp:post-template -->

    <!-- wp:query-no-results -->
    <!-- wp:paragraph -->
    <p>No reports have been published yet.</p>
    <!-- /wp:paragraph -->
    <!-- /wp:query-no-results -->
  </div>
  <!-- /wp:query -->
</div>
<!-- /wp:group -->
