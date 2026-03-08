<?php
/**
 * Title: ML - Hero: Institutional
 * Slug: marketlense/hero-institutional
 * Categories: marketlense-home
 * Inserter: yes
 */
?>
<!-- wp:group {"align":"full","className":"ml-hero-band ml-hero reveal","layout":{"type":"default"}} -->
<div class="wp-block-group alignfull ml-hero-band ml-hero reveal">
  <!-- wp:group {"className":"ml-hero-frame ml-hero-grid","layout":{"type":"default"}} -->
  <div class="wp-block-group ml-hero-frame ml-hero-grid">
    <!-- wp:html -->
    <span class="ml-hero-decor ml-hero-decor-left" aria-hidden="true"></span>
    <!-- /wp:html -->

    <!-- wp:html -->
    <span class="ml-hero-decor ml-hero-decor-right" aria-hidden="true"></span>
    <!-- /wp:html -->

    <!-- wp:group {"className":"ml-hero-content","layout":{"type":"default"}} -->
    <div class="wp-block-group ml-hero-content">
      <!-- wp:paragraph {"className":"ml-hero-eyebrow"} -->
      <p class="ml-hero-eyebrow">Market Lense intelligence portal</p>
      <!-- /wp:paragraph -->

      <!-- wp:group {"className":"ml-hero-stack","layout":{"type":"default"}} -->
      <div class="wp-block-group ml-hero-stack">
        <!-- wp:heading {"level":1,"fontSize":"4xl","className":"ml-hero-title"} -->
        <h1 class="wp-block-heading ml-hero-title has-4-xl-font-size">Executive research intelligence with traceable evidence.</h1>
        <!-- /wp:heading -->

        <!-- wp:group {"className":"ml-hero-support","layout":{"type":"default"}} -->
        <div class="wp-block-group ml-hero-support">
          <!-- wp:paragraph {"className":"ml-hero-copy"} -->
          <p class="ml-hero-copy">Market Lense converts long-form market, strategy, and industry reports into concise digests built for strategy, insights, and leadership teams.</p>
          <!-- /wp:paragraph -->

          <!-- wp:paragraph {"className":"ml-hero-credibility"} -->
          <p class="ml-hero-credibility">Validated coverage spanning OECD, Deloitte, Morningstar, Kantar, IAS, and other leading research publishers.</p>
          <!-- /wp:paragraph -->
        </div>
        <!-- /wp:group -->
      </div>
      <!-- /wp:group -->

      <!-- wp:search {"label":"Search Market Lense","showLabel":false,"placeholder":"Search reports, topics, and publishers","buttonPosition":"button-inside","buttonUseIcon":true,"className":"ml-hero-search"} /-->

      <!-- wp:buttons {"className":"ml-hero-actions"} -->
      <div class="wp-block-buttons ml-hero-actions">
        <!-- wp:button -->
        <div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="<?php echo esc_url((string) (get_post_type_archive_link('ml_report') ?: home_url('/reports/'))); ?>">Browse reports</a></div>
        <!-- /wp:button -->
        <!-- wp:button {"className":"is-style-outline"} -->
        <div class="wp-block-button is-style-outline"><a class="wp-block-button__link wp-element-button" href="<?php echo esc_url(home_url('/methodology/')); ?>">Review methodology</a></div>
        <!-- /wp:button -->
      </div>
      <!-- /wp:buttons -->
    </div>
    <!-- /wp:group -->

    <!-- wp:group {"className":"ml-hero-proof ml-hero-panel","layout":{"type":"default"}} -->
    <div class="wp-block-group ml-hero-proof ml-hero-panel">
      <!-- wp:shortcode -->
      [ml_hero_snapshot]
      <!-- /wp:shortcode -->
    </div>
    <!-- /wp:group -->

    <!-- wp:paragraph {"className":"ml-capability-strip"} -->
    <p class="ml-capability-strip">Source-traceable &middot; Claim-linked &middot; Freshly updated &middot; Executive-ready &middot; Figure-indexed</p>
    <!-- /wp:paragraph -->
  </div>
  <!-- /wp:group -->
</div>
<!-- /wp:group -->
