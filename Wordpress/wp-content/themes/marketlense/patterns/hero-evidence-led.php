<?php
/**
 * Title: ML - Hero: Evidence-Led
 * Slug: marketlense/hero-evidence-led
 * Categories: marketlense-home
 * Inserter: yes
 */
?>
<!-- wp:group {"align":"full","className":"ml-hero-band","layout":{"type":"default"}} -->
<div class="wp-block-group alignfull ml-hero-band">
  <!-- wp:group {"className":"ml-hero-frame","layout":{"type":"default"}} -->
  <div class="wp-block-group ml-hero-frame">
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
        <h1 class="wp-block-heading ml-hero-title has-4-xl-font-size">Validated market digests for leaders who need evidence, not noise.</h1>
        <!-- /wp:heading -->

        <!-- wp:paragraph {"className":"ml-hero-copy"} -->
        <p class="ml-hero-copy">Browse a disciplined archive of editorial digests spanning macro outlooks, sector shifts, consumer behavior, and technology adoption.</p>
        <!-- /wp:paragraph -->

        <!-- wp:paragraph {"className":"ml-hero-credibility"} -->
        <p class="ml-hero-credibility">Validated digests from OECD, Deloitte, Morningstar, Kantar, IAS and leading research publishers.</p>
        <!-- /wp:paragraph -->

        <!-- wp:buttons {"className":"ml-hero-actions"} -->
        <div class="wp-block-buttons ml-hero-actions">
          <!-- wp:button -->
          <div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="<?php echo esc_url((string) (get_post_type_archive_link('ml_report') ?: home_url('/reports/'))); ?>">Browse reports</a></div>
          <!-- /wp:button -->
          <!-- wp:button {"className":"is-style-outline"} -->
          <div class="wp-block-button is-style-outline"><a class="wp-block-button__link wp-element-button" href="<?php echo esc_url(home_url('/topics-directory/')); ?>">Explore topics</a></div>
          <!-- /wp:button -->
        </div>
        <!-- /wp:buttons -->
      </div>
      <!-- /wp:group -->
    </div>
    <!-- /wp:group -->

    <!-- wp:paragraph {"className":"ml-capability-strip"} -->
    <p class="ml-capability-strip">Digest-first &middot; Source-traceable &middot; Claim-verified &middot; Executive-ready &middot; Figure-indexed</p>
    <!-- /wp:paragraph -->
  </div>
  <!-- /wp:group -->
</div>
<!-- /wp:group -->
