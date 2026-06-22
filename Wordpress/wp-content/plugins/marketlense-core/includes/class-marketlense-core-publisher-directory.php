<?php
/**
 * Publisher directory presentation built from canonical report archive filters.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Publisher_Directory
{
    public function __construct(
        private Archive_Browser $browser,
        private Intelligence_Stats $stats
    ) {
    }

    public function render(): string
    {
        $context = $this->browser->publisher_directory_context();
        $items = $context['has_active_filters']
            ? $this->matching_publisher_items($context['post_ids'])
            : $this->all_publisher_items($context['post_ids']);
        $directory_url = get_permalink();
        if (! is_string($directory_url) || $directory_url === '') {
            $directory_url = home_url('/publishers/');
        }

        ob_start();
        ?>
        <section class="ml-archive-browser-page ml-reports-archive-page ml-publisher-browser ml-report-browser" aria-label="<?php esc_attr_e('Publisher directory', 'marketlense-core'); ?>">
            <?php echo $this->browser->render_publisher_directory_utility_bar($context, $directory_url); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
            <div class="ml-report-browser-layout">
                <?php echo $this->browser->render_publisher_directory_filter_sidebar($context, $directory_url); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                <div class="ml-report-browser-results ml-publisher-directory-results">
                <div class="ml-report-browser-head">
                    <p class="ml-report-browser-summary">
                        <span class="ml-report-browser-summary-value"><?php echo esc_html((string) count($items)); ?> <?php esc_html_e('publishers', 'marketlense-core'); ?></span>
                        <span class="ml-report-browser-summary-copy"><?php echo esc_html($context['has_active_filters'] ? __('with matching reports', 'marketlense-core') : __('represented across the archive', 'marketlense-core')); ?></span>
                    </p>
                </div>
                <?php if ($items === []) : ?>
                    <div class="ml-empty-state"><p><?php esc_html_e('No publishers match the current report filters.', 'marketlense-core'); ?></p></div>
                <?php else : ?>
                    <div class="ml-directory-list ml-publisher-directory-list">
                        <?php foreach ($items as $rank => $item) : ?>
                            <?php $this->render_card($item, $rank + 1, $context['has_active_filters']); ?>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
                </div>
            </div>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * @param list<int> $report_ids
     * @return list<array{term:\WP_Term,reports:int,briefings:int,signals:int,total:int,matching_reports:int,categories:array<string,int>}>
     */
    private function all_publisher_items(array $report_ids): array
    {
        $report_data = $this->report_data_by_publisher($report_ids);
        $items = [];

        foreach ($this->stats->content_backed_terms(Taxonomies::PUBLISHER_TAXONOMY, 300) as $item) {
            $term = $item['term'];
            if (! $term instanceof \WP_Term) {
                continue;
            }
            $details = $report_data[$term->term_id] ?? ['count' => 0, 'categories' => []];
            $items[] = [
                'term' => $term,
                'reports' => (int) $item['reports'],
                'briefings' => (int) $item['briefings'],
                'signals' => (int) $item['signals'],
                'total' => (int) $item['total'],
                'matching_reports' => $details['count'],
                'categories' => $details['categories'],
            ];
        }

        return $items;
    }

    /**
     * @param list<int> $report_ids
     * @return list<array{term:\WP_Term,reports:int,briefings:int,signals:int,total:int,matching_reports:int,categories:array<string,int>}>
     */
    private function matching_publisher_items(array $report_ids): array
    {
        $items = [];
        foreach ($this->report_data_by_publisher($report_ids) as $term_id => $details) {
            $term = get_term($term_id, Taxonomies::PUBLISHER_TAXONOMY);
            if (! $term instanceof \WP_Term) {
                continue;
            }
            $items[] = [
                'term' => $term,
                'reports' => $details['count'],
                'briefings' => 0,
                'signals' => 0,
                'total' => $details['count'],
                'matching_reports' => $details['count'],
                'categories' => $details['categories'],
            ];
        }

        usort(
            $items,
            static fn (array $left, array $right): int =>
                $right['matching_reports'] <=> $left['matching_reports'] ?: strcasecmp($left['term']->name, $right['term']->name)
        );

        return $items;
    }

    /**
     * @param list<int> $report_ids
     * @return array<int,array{count:int,categories:array<string,int>}>
     */
    private function report_data_by_publisher(array $report_ids): array
    {
        $items = [];
        foreach ($report_ids as $report_id) {
            $publishers = get_the_terms($report_id, Taxonomies::PUBLISHER_TAXONOMY);
            if (! is_array($publishers)) {
                continue;
            }
            $categories = get_the_terms($report_id, Taxonomies::CATEGORY_TAXONOMY);
            foreach ($publishers as $publisher) {
                if (! $publisher instanceof \WP_Term) {
                    continue;
                }
                if (! isset($items[$publisher->term_id])) {
                    $items[$publisher->term_id] = ['count' => 0, 'categories' => []];
                }
                $items[$publisher->term_id]['count']++;
                if (! is_array($categories)) {
                    continue;
                }
                foreach ($categories as $category) {
                    if ($category instanceof \WP_Term) {
                        $items[$publisher->term_id]['categories'][$category->name] = ($items[$publisher->term_id]['categories'][$category->name] ?? 0) + 1;
                    }
                }
            }
        }

        return $items;
    }

    /** @param array{term:\WP_Term,reports:int,briefings:int,signals:int,total:int,matching_reports:int,categories:array<string,int>} $item */
    private function render_card(array $item, int $rank, bool $is_filtered): void
    {
        $term = $item['term'];
        $profile_url = get_term_link($term);
        $logo = (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_ICON_META, true);
        $score = get_term_meta($term->term_id, Taxonomies::PUBLISHER_REPORT_VALUE_SCORE_META, true);
        $band = (string) get_term_meta($term->term_id, Taxonomies::PUBLISHER_REPORT_VALUE_BAND_META, true);
        $sample = (int) get_term_meta($term->term_id, Taxonomies::PUBLISHER_REPORT_VALUE_SAMPLE_SIZE_META, true);
        $categories = $item['categories'];
        arsort($categories);
        $key_categories = array_slice(array_keys($categories), 0, 3);
        $additional_categories = max(0, count($categories) - count($key_categories));
        ?>
        <article class="ml-directory-card ml-publisher-directory-card ml-publisher-directory-card--small">
            <div class="ml-publisher-directory-card-topline">
                <div>
                    <p class="ml-publisher-directory-eyebrow"><?php esc_html_e('Research publisher', 'marketlense-core'); ?></p>
                    <p class="ml-directory-count"><?php echo esc_html($is_filtered ? sprintf(_n('%d matching report', '%d matching reports', $item['matching_reports'], 'marketlense-core'), $item['matching_reports']) : sprintf(_n('%d published report', '%d published reports', $item['reports'], 'marketlense-core'), $item['reports'])); ?></p>
                </div>
                <span class="ml-publisher-directory-rank">#<?php echo esc_html((string) $rank); ?></span>
            </div>
            <div class="ml-publisher-directory-card-identity">
                <div class="ml-publisher-directory-mark" aria-hidden="true">
                    <span><?php echo esc_html($this->monogram($term->name)); ?></span>
                    <?php if ($logo !== '') : ?>
                        <img src="<?php echo esc_url($logo); ?>" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.remove();">
                    <?php endif; ?>
                </div>
                <div>
                    <h2><?php if (! is_wp_error($profile_url)) : ?><a href="<?php echo esc_url((string) $profile_url); ?>"><?php endif; ?><?php echo esc_html($term->name); ?><?php if (! is_wp_error($profile_url)) : ?></a><?php endif; ?></h2>
                    <?php if ($term->description !== '') : ?><p class="ml-directory-description"><?php echo esc_html(wp_trim_words(wp_strip_all_tags($term->description), 22, '…')); ?></p><?php endif; ?>
                </div>
            </div>
            <ul class="ml-publisher-directory-facts" aria-label="<?php esc_attr_e('Represented content', 'marketlense-core'); ?>">
                <li><strong><?php echo esc_html(number_format_i18n($item['reports'])); ?></strong><span><?php esc_html_e('Reports', 'marketlense-core'); ?></span></li>
                <li><strong><?php echo esc_html(number_format_i18n($item['briefings'])); ?></strong><span><?php esc_html_e('Briefings', 'marketlense-core'); ?></span></li>
                <li><strong><?php echo esc_html(number_format_i18n($item['signals'])); ?></strong><span><?php esc_html_e('Signals', 'marketlense-core'); ?></span></li>
            </ul>
            <?php if (is_numeric($score) && $band !== '' && $sample > 0) : ?>
                <p class="ml-publisher-quality"><strong><?php echo esc_html(number_format_i18n((float) $score, 1)); ?></strong><span><?php echo esc_html(sprintf(__('%1$s report value · %2$d assessed', 'marketlense-core'), ucfirst($band), $sample)); ?></span></p>
            <?php endif; ?>
            <?php if ($key_categories !== []) : ?>
                <div class="ml-publisher-categories" aria-label="<?php esc_attr_e('Key report categories', 'marketlense-core'); ?>">
                    <?php foreach ($key_categories as $category) : ?><span><?php echo esc_html($category); ?></span><?php endforeach; ?>
                    <?php if ($additional_categories > 0) : ?><span>+<?php echo esc_html((string) $additional_categories); ?></span><?php endif; ?>
                </div>
            <?php endif; ?>
            <div class="ml-publisher-directory-card__footer">
                <?php if (! is_wp_error($profile_url)) : ?><a class="ml-text-link ml-publisher-directory-link" href="<?php echo esc_url((string) $profile_url); ?>"><?php esc_html_e('View publisher profile', 'marketlense-core'); ?><span aria-hidden="true">→</span></a><?php endif; ?>
            </div>
        </article>
        <?php
    }

    private function monogram(string $name): string
    {
        $parts = preg_split('/\s+/', trim(wp_strip_all_tags($name))) ?: [];
        $letters = '';
        foreach ($parts as $part) {
            if ($part !== '') {
                $letters .= strtoupper(substr($part, 0, 1));
            }
            if (strlen($letters) === 2) {
                break;
            }
        }
        return $letters !== '' ? $letters : strtoupper(substr(trim($name), 0, 2));
    }
}
