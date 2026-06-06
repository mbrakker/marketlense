<?php
/**
 * Frontend content formatting controls for ingested report HTML.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Content_Formatting
{
    private bool $restore_registered = false;

    public function register(): void
    {
        add_filter('the_content', [$this, 'suspend_auto_paragraphs_for_reports'], 9);
    }

    public function suspend_auto_paragraphs_for_reports(string $content): string
    {
        $post = get_post();
        if (! $post instanceof \WP_Post) {
            return $content;
        }

        if (! in_array((string) $post->post_type, Post_Type::report_post_types(), true)) {
            return $content;
        }

        remove_filter('the_content', 'wpautop');
        remove_filter('the_content', 'shortcode_unautop');

        if (! $this->restore_registered) {
            add_filter('the_content', [$this, 'restore_auto_paragraphs'], 99);
            $this->restore_registered = true;
        }

        return $content;
    }

    public function restore_auto_paragraphs(string $content): string
    {
        if (! has_filter('the_content', 'wpautop')) {
            add_filter('the_content', 'wpautop');
        }
        if (! has_filter('the_content', 'shortcode_unautop')) {
            add_filter('the_content', 'shortcode_unautop');
        }

        return $content;
    }
}
