<?php
/**
 * Shared public archive browser for canonical intelligence cards.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Archive_Browser
{
    public const REPORTS = 'reports';

    public const BRIEFINGS = 'briefings';

    public const SIGNALS = 'signals';

    private const DEFAULT_PER_PAGE = 12;

    /**
     * @param array<string,mixed> $attrs
     */
    public function __construct(
        private Report_View_Model_Builder $report_view_model_builder,
        private Report_Card_Renderer $report_card_renderer,
        private Briefing_Card_View_Model_Builder $briefing_card_view_model_builder,
        private Briefing_Card_Renderer $briefing_card_renderer,
        private Signal_Card_View_Model_Builder $signal_card_view_model_builder,
        private Signal_Card_Renderer $signal_card_renderer
    ) {
    }

    /**
     * @param array<string,mixed> $attrs
     */
    public function render(array $attrs, string $content_type): string
    {
        $definition = $this->definition($content_type);
        $atts = shortcode_atts(
            [
                'per_page' => (string) self::DEFAULT_PER_PAGE,
                'show_filters' => '1',
                'show_pagination' => '1',
                'card_size' => 'small',
            ],
            $attrs,
            'ml_' . $definition['slug'] . '_index'
        );
        $per_page = max(1, min(48, (int) $atts['per_page']));
        $show_filters = $this->to_bool_flag($atts['show_filters']);
        $show_pagination = $this->to_bool_flag($atts['show_pagination']);
        $card_size = in_array($atts['card_size'], ['small', 'medium', 'large'], true) ? $atts['card_size'] : 'small';
        $filters = $this->selected_publisher_directory_filters();
        $sort = $this->selected_sort();
        $archive_url = $this->archive_url($definition);
        $query = new \WP_Query($this->query_args($definition, $filters, $per_page, $this->current_page(), $sort));
        $topic_options = $this->facet_terms($definition, $filters, 'topic');
        $publisher_options = $this->facet_terms($definition, $filters, 'publisher');
        $period_options = $this->facet_meta_values($definition, $filters, Meta::META_TIME_PERIOD, 'period');
        $region_options = $this->facet_meta_values($definition, $filters, Meta::META_REGION, 'region');

        if ($show_filters) {
            $this->enqueue_filter_assets();
        }

        ob_start();
        ?>
        <section class="ml-archive-browser-page ml-reports-archive-page ml-report-browser" aria-label="<?php echo esc_attr($definition['browser_label']); ?>">
            <?php if ($show_filters) : ?>
                <div class="ml-report-browser-utility-bar">
                    <form class="ml-report-search-form" method="get" action="<?php echo esc_url($archive_url); ?>" data-ml-live-filter-form>
                        <span class="screen-reader-text" data-ml-filter-status aria-live="polite"></span>
                        <?php $this->render_hidden_inputs($this->filter_args($filters, ['search'])); ?>
                        <label class="ml-report-search-field" for="ml_<?php echo esc_attr($definition['slug']); ?>_search">
                            <span><?php echo esc_html(sprintf(__('Search %s archive', 'marketlense-core'), $definition['plural'])); ?></span>
                            <input id="ml_<?php echo esc_attr($definition['slug']); ?>_search" name="s" type="search" value="<?php echo esc_attr($filters['search']); ?>" placeholder="<?php echo esc_attr(sprintf(__('Search %s', 'marketlense-core'), strtolower($definition['plural']))); ?>" data-ml-live-filter-input>
                        </label>
                    </form>
                    <?php $this->render_active_filters($archive_url, $filters, $sort); ?>
                </div>
            <?php endif; ?>
            <div class="ml-report-browser-layout">
                <?php if ($show_filters) : ?>
                    <aside class="ml-report-browser-sidebar">
                        <div class="ml-report-browser-sidebar-card">
                            <details class="ml-report-filter-panel" open>
                                <summary class="ml-report-filter-summary"><?php echo esc_html(sprintf(__('Filter %s', 'marketlense-core'), strtolower($definition['plural']))); ?></summary>
                                <div class="ml-report-filter-body">
                                    <div class="ml-report-filter-header"><div><p class="ml-section-kicker"><?php esc_html_e('Filters', 'marketlense-core'); ?></p><h2 class="ml-report-browser-title"><?php echo esc_html(sprintf(__('Refine %s', 'marketlense-core'), strtolower($definition['plural']))); ?></h2></div></div>
                                    <form class="ml-report-filter-form" method="get" action="<?php echo esc_url($archive_url); ?>" data-ml-live-filter-form>
                                        <span class="screen-reader-text" data-ml-filter-status aria-live="polite"></span>
                                        <?php $this->render_hidden_inputs($this->filter_args($filters, ['topic', 'publisher', 'period', 'region'])); ?>
                                        <div class="ml-report-filter-grid">
                                            <?php $this->render_term_select('ml_topic_filter', 'category', __('Category', 'marketlense-core'), __('All categories', 'marketlense-core'), $filters['topic'], $topic_options); ?>
                                            <?php $this->render_term_select('ml_publisher_filter', 'ml_publisher', __('Publisher', 'marketlense-core'), __('All publishers', 'marketlense-core'), $filters['publisher'], $publisher_options); ?>
                                            <?php $this->render_value_select('ml_period_filter', 'ml_period', __('Period', 'marketlense-core'), __('All periods', 'marketlense-core'), $filters['period'], $period_options); ?>
                                            <?php $this->render_value_select('ml_region_filter', 'ml_region', __('Region', 'marketlense-core'), __('All regions', 'marketlense-core'), $filters['region'], $region_options); ?>
                                        </div>
                                    </form>
                                </div>
                            </details>
                        </div>
                    </aside>
                <?php endif; ?>
                <div class="ml-report-browser-results">
                    <div class="ml-report-browser-head">
                        <p class="ml-report-browser-summary"><span class="ml-report-browser-summary-value"><?php echo esc_html(sprintf(_n('%1$d %2$s', '%1$d %3$s', (int) $query->found_posts, 'marketlense-core'), (int) $query->found_posts, $definition['singular'], $definition['plural'])); ?></span><span class="ml-report-browser-summary-copy"><?php esc_html_e('currently in view', 'marketlense-core'); ?></span></p>
                        <?php $this->render_sort_controls($archive_url, $filters, $sort, $definition['plural']); ?>
                    </div>
                    <?php if ($query->have_posts()) : ?>
                        <div class="ml-report-browser-grid">
                            <?php while ($query->have_posts()) : $query->the_post(); $post = get_post(); ?>
                                <?php if ($post instanceof \WP_Post) : echo $this->render_card($post, $content_type, $card_size); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                                <?php endif; ?>
                            <?php endwhile; ?>
                        </div>
                        <?php if ($show_pagination) : $this->render_pagination($query, $filters); endif; ?>
                    <?php else : ?>
                        <div class="ml-empty-state"><p><?php echo esc_html(sprintf(__('No %s match the current view.', 'marketlense-core'), strtolower($definition['plural']))); ?></p></div>
                    <?php endif; ?>
                </div>
            </div>
            <?php wp_reset_postdata(); ?>
        </section>
        <?php
        return (string) ob_get_clean();
    }

    /** @return array{filters:array{topic:string,publisher:string,period:string,region:string,search:string},post_ids:list<int>,topics:list<\WP_Term>,periods:list<array{value:string,count:int}>,regions:list<array{value:string,count:int}>,has_active_filters:bool} */
    public function publisher_directory_context(): array
    {
        $definition = $this->definition(self::REPORTS);
        $filters = $this->selected_filters();
        $filters['publisher'] = '';
        $post_ids = $this->facet_ids($definition, $filters, 'publisher');
        $this->enqueue_filter_assets();
        return [
            'filters' => $filters,
            'post_ids' => $post_ids,
            'topics' => $this->facet_terms($definition, $filters, 'topic'),
            'periods' => $this->facet_meta_values($definition, $filters, Meta::META_TIME_PERIOD, 'period'),
            'regions' => $this->facet_meta_values($definition, $filters, Meta::META_REGION, 'region'),
            'has_active_filters' => $filters['topic'] !== '' || $filters['period'] !== '' || $filters['region'] !== '' || $filters['search'] !== '',
        ];
    }

    /**
     * Renders the report archive filter components for the publisher directory.
     * Publishers are intentionally omitted: the remaining filters select publishers
     * through their matching reports.
     *
     * @param array{filters:array{topic:string,publisher:string,period:string,region:string,search:string},post_ids:list<int>,topics:list<\WP_Term>,periods:list<array{value:string,count:int}>,regions:list<array{value:string,count:int}>,has_active_filters:bool} $context
     */
    public function render_publisher_directory_utility_bar(array $context, string $directory_url): string
    {
        $filters = $context['filters'];
        ob_start();
        ?>
        <div class="ml-report-browser-utility-bar">
            <form class="ml-report-search-form" method="get" action="<?php echo esc_url($directory_url); ?>" data-ml-live-filter-form>
                <span class="screen-reader-text" data-ml-filter-status aria-live="polite"></span>
                <?php $this->render_hidden_inputs($this->publisher_directory_filter_args($filters, ['search'])); ?>
                <label class="ml-report-search-field" for="ml_publisher_directory_search">
                    <span><?php esc_html_e('Search reports', 'marketlense-core'); ?></span>
                    <input id="ml_publisher_directory_search" name="ml_publisher_search" type="search" value="<?php echo esc_attr($filters['search']); ?>" placeholder="<?php esc_attr_e('Search reports', 'marketlense-core'); ?>" data-ml-live-filter-input>
                </label>
            </form>
            <?php $this->render_active_publisher_directory_filters($directory_url, $filters); ?>
        </div>
        <?php
        return (string) ob_get_clean();
    }

    /**
     * Renders the report archive filter sidebar for the publisher directory.
     *
     * @param array{filters:array{topic:string,publisher:string,period:string,region:string,search:string},post_ids:list<int>,topics:list<\WP_Term>,periods:list<array{value:string,count:int}>,regions:list<array{value:string,count:int}>,has_active_filters:bool} $context
     */
    public function render_publisher_directory_filter_sidebar(array $context, string $directory_url): string
    {
        $filters = $context['filters'];
        ob_start();
        ?>
        <aside class="ml-report-browser-sidebar ml-publisher-directory-sidebar">
            <div class="ml-report-browser-sidebar-card">
                <details class="ml-report-filter-panel" open>
                    <summary class="ml-report-filter-summary"><?php esc_html_e('Filter publishers', 'marketlense-core'); ?></summary>
                    <div class="ml-report-filter-body">
                        <div class="ml-report-filter-header"><div><p class="ml-section-kicker"><?php esc_html_e('Filters', 'marketlense-core'); ?></p><h2 class="ml-report-browser-title"><?php esc_html_e('Refine publishers', 'marketlense-core'); ?></h2></div></div>
                        <form class="ml-report-filter-form" method="get" action="<?php echo esc_url($directory_url); ?>" data-ml-live-filter-form>
                            <span class="screen-reader-text" data-ml-filter-status aria-live="polite"></span>
                            <?php $this->render_hidden_inputs($this->publisher_directory_filter_args($filters, ['topic', 'period', 'region'])); ?>
                            <div class="ml-report-filter-grid">
                                <?php $this->render_term_select('ml_publisher_directory_topic', 'ml_publisher_topic', __('Category', 'marketlense-core'), __('All categories', 'marketlense-core'), $filters['topic'], $context['topics']); ?>
                                <?php $this->render_value_select('ml_publisher_directory_period', 'ml_publisher_period', __('Period', 'marketlense-core'), __('All periods', 'marketlense-core'), $filters['period'], $context['periods']); ?>
                                <?php $this->render_value_select('ml_publisher_directory_region', 'ml_publisher_region', __('Region', 'marketlense-core'), __('All regions', 'marketlense-core'), $filters['region'], $context['regions']); ?>
                            </div>
                        </form>
                    </div>
                </details>
            </div>
        </aside>
        <?php
        return (string) ob_get_clean();
    }

    /** @return array{slug:string,post_type:string|list<string>,schema_key:string,singular:string,plural:string,browser_label:string} */
    private function definition(string $content_type): array
    {
        return match ($content_type) {
            self::REPORTS => ['slug' => 'report', 'post_type' => Post_Type::report_post_types(), 'schema_key' => Meta::META_CARD_SCHEMA_VERSION, 'singular' => __('report', 'marketlense-core'), 'plural' => __('reports', 'marketlense-core'), 'browser_label' => __('Report browser', 'marketlense-core')],
            self::BRIEFINGS => ['slug' => 'briefing', 'post_type' => Post_Type::BRIEFING_POST_TYPE, 'schema_key' => 'ml_briefing_card_schema_version', 'singular' => __('briefing', 'marketlense-core'), 'plural' => __('briefings', 'marketlense-core'), 'browser_label' => __('Briefing browser', 'marketlense-core')],
            self::SIGNALS => ['slug' => 'signal', 'post_type' => Post_Type::SIGNAL_POST_TYPE, 'schema_key' => 'ml_signal_card_schema_version', 'singular' => __('signal', 'marketlense-core'), 'plural' => __('signals', 'marketlense-core'), 'browser_label' => __('Signal browser', 'marketlense-core')],
            default => throw new \InvalidArgumentException('Unknown archive browser content type.'),
        };
    }

    /** @return array{topic:string,publisher:string,period:string,region:string,search:string} */
    private function selected_filters(): array
    {
        return ['topic' => sanitize_title((string) ($_GET['category'] ?? '')), 'publisher' => sanitize_title((string) ($_GET['ml_publisher'] ?? '')), 'period' => sanitize_text_field((string) ($_GET['ml_period'] ?? '')), 'region' => sanitize_text_field((string) ($_GET['ml_region'] ?? '')), 'search' => sanitize_text_field((string) ($_GET['s'] ?? ''))];
    }

    /** @return array{topic:string,publisher:string,period:string,region:string,search:string} */
    private function selected_publisher_directory_filters(): array
    {
        return ['topic' => sanitize_title((string) ($_GET['ml_publisher_topic'] ?? '')), 'publisher' => '', 'period' => sanitize_text_field((string) ($_GET['ml_publisher_period'] ?? '')), 'region' => sanitize_text_field((string) ($_GET['ml_publisher_region'] ?? '')), 'search' => sanitize_text_field((string) ($_GET['ml_publisher_search'] ?? ''))];
    }

    /** @param array{slug:string,post_type:string|list<string>,schema_key:string,singular:string,plural:string,browser_label:string} $definition @param array{topic:string,publisher:string,period:string,region:string,search:string} $filters @return array<string,mixed> */
    private function query_args(array $definition, array $filters, int $per_page, int $paged, string $sort, string $exclude = ''): array
    {
        $args = ['post_type' => $definition['post_type'], 'post_status' => 'publish', 'posts_per_page' => $per_page, 'paged' => $paged, 'orderby' => $sort === 'title' ? 'title' : 'date', 'order' => $sort === 'oldest' ? 'ASC' : 'DESC'];
        if ($filters['search'] !== '') { $args['s'] = $filters['search']; }
        $meta_query = [['key' => $definition['schema_key'], 'value' => '1.0', 'compare' => '=']];
        foreach (['period' => Meta::META_TIME_PERIOD, 'region' => Meta::META_REGION] as $key => $meta_key) {
            if ($exclude !== $key && $filters[$key] !== '') { $meta_query[] = ['key' => $meta_key, 'value' => $filters[$key], 'compare' => '=']; }
        }
        $args['meta_query'] = count($meta_query) > 1 ? array_merge(['relation' => 'AND'], $meta_query) : $meta_query;
        $tax_query = ['relation' => 'AND'];
        if ($exclude !== 'topic' && $filters['topic'] !== '') { $tax_query[] = ['taxonomy' => Taxonomies::CATEGORY_TAXONOMY, 'field' => 'slug', 'terms' => [$filters['topic']]]; }
        if ($exclude !== 'publisher' && $filters['publisher'] !== '') { $tax_query[] = ['taxonomy' => Taxonomies::PUBLISHER_TAXONOMY, 'field' => 'slug', 'terms' => [$filters['publisher']]]; }
        if (count($tax_query) > 1) { $args['tax_query'] = $tax_query; }
        return $definition['slug'] === 'report' ? Meta::apply_report_card_query_constraints($args) : $args;
    }

    private function archive_url(array $definition): string
    {
        $post_type = is_array($definition['post_type']) ? Post_Type::POST_TYPE : $definition['post_type'];
        $url = get_post_type_archive_link($post_type);
        return is_string($url) && $url !== '' ? $url : home_url('/' . $definition['slug'] . 's/');
    }

    private function render_card(\WP_Post $post, string $content_type, string $card_size): string
    {
        if ($content_type === self::REPORTS) { $report = $this->report_view_model_builder->build($post); return ($report['card_contract_valid'] ?? false) === true ? $this->report_card_renderer->render($report, $card_size) : ''; }
        if ($content_type === self::BRIEFINGS) { $briefing = $this->briefing_card_view_model_builder->build($post); return ($briefing['card_contract_valid'] ?? false) === true ? $this->briefing_card_renderer->render($briefing, $card_size) : ''; }
        $signal = $this->signal_card_view_model_builder->build($post);
        return ($signal['card_contract_valid'] ?? false) === true ? $this->signal_card_renderer->render($signal, $card_size) : '';
    }

    private function facet_ids(array $definition, array $filters, string $exclude): array { $args = $this->query_args($definition, $filters, -1, 1, 'latest', $exclude); $args['fields'] = 'ids'; $args['no_found_rows'] = true; $query = new \WP_Query($args); return array_map('intval', $query->posts); }
    private function facet_terms(array $definition, array $filters, string $exclude): array
    {
        $items = [];
        $taxonomy = $exclude === 'topic'
            ? Taxonomies::CATEGORY_TAXONOMY
            : Taxonomies::PUBLISHER_TAXONOMY;

        foreach ($this->facet_ids($definition, $filters, $exclude) as $id) {
            $terms = get_the_terms($id, $taxonomy);
            if (! is_array($terms)) {
                continue;
            }

            foreach ($terms as $term) {
                if (! ($term instanceof \WP_Term)) {
                    continue;
                }
                if (! isset($items[$term->term_id])) {
                    $items[$term->term_id] = clone $term;
                    $items[$term->term_id]->count = 0;
                }
                $items[$term->term_id]->count++;
            }
        }

        $terms = array_values($items);
        usort(
            $terms,
            static fn (\WP_Term $left, \WP_Term $right): int =>
                ((int) $right->count <=> (int) $left->count) ?: strcasecmp($left->name, $right->name)
        );

        return $terms;
    }
    private function facet_meta_values(array $definition, array $filters, string $meta_key, string $exclude): array { $values = []; foreach ($this->facet_ids($definition, $filters, $exclude) as $id) { $value = trim((string) get_post_meta($id, $meta_key, true)); if ($value !== '' && $value !== '...' && strcasecmp($value, 'not extracted') !== 0) { $values[$value] = ($values[$value] ?? 0) + 1; } } ksort($values, SORT_NATURAL | SORT_FLAG_CASE); return array_map(static fn(string $value, int $count): array => ['value' => $value, 'count' => $count], array_keys($values), $values); }
    private function render_term_select(string $id, string $name, string $label, string $all_label, string $selected, array $terms): void { ?><label class="ml-report-filter-field" for="<?php echo esc_attr($id); ?>"><span><?php echo esc_html($label); ?></span><select id="<?php echo esc_attr($id); ?>" name="<?php echo esc_attr($name); ?>"><option value=""><?php echo esc_html($all_label); ?></option><?php foreach ($terms as $term) : ?><option value="<?php echo esc_attr($term->slug); ?>" <?php selected($selected, $term->slug); ?>><?php echo esc_html(sprintf('%1$s (%2$d)', $term->name, (int) $term->count)); ?></option><?php endforeach; ?></select></label><?php }
    private function render_value_select(string $id, string $name, string $label, string $all_label, string $selected, array $values): void { ?><label class="ml-report-filter-field" for="<?php echo esc_attr($id); ?>"><span><?php echo esc_html($label); ?></span><select id="<?php echo esc_attr($id); ?>" name="<?php echo esc_attr($name); ?>"><option value=""><?php echo esc_html($all_label); ?></option><?php foreach ($values as $item) : ?><option value="<?php echo esc_attr($item['value']); ?>" <?php selected($selected, $item['value']); ?>><?php echo esc_html(sprintf('%1$s (%2$d)', $item['value'], $item['count'])); ?></option><?php endforeach; ?></select></label><?php }
    private function render_hidden_inputs(array $args): void { foreach ($args as $key => $value) { if ($value !== '') { printf('<input type="hidden" name="%1$s" value="%2$s">', esc_attr($key), esc_attr($value)); } } }
    private function filter_args(array $filters, array $exclude): array { $args = ['category' => $filters['topic'], 'ml_publisher' => $filters['publisher'], 'ml_period' => $filters['period'], 'ml_region' => $filters['region'], 's' => $filters['search']]; foreach ($exclude as $key) { unset($args[$key === 'topic' ? 'category' : ($key === 'publisher' ? 'ml_publisher' : ($key === 'search' ? 's' : 'ml_' . $key))]); } return $args; }
    private function publisher_directory_filter_args(array $filters, array $exclude): array { $args = ['ml_publisher_topic' => $filters['topic'], 'ml_publisher_period' => $filters['period'], 'ml_publisher_region' => $filters['region'], 'ml_publisher_search' => $filters['search']]; foreach ($exclude as $key) { unset($args['ml_publisher_' . ($key === 'topic' ? 'topic' : ($key === 'search' ? 'search' : $key))]); } return $args; }
    private function render_active_filters(string $archive_url, array $filters, string $sort): void { $active = array_filter($filters); if ($active === []) { return; } ?><div class="ml-active-filters" aria-label="<?php esc_attr_e('Active filters', 'marketlense-core'); ?>"><span class="ml-active-filters-label"><?php esc_html_e('Selected', 'marketlense-core'); ?></span><?php foreach ($active as $key => $value) : ?><a class="ml-filter-chip" href="<?php echo esc_url(add_query_arg($this->filter_args($filters, [$key]), $archive_url)); ?>"><?php echo esc_html(ucfirst($key) . ': ' . $value); ?></a><?php endforeach; ?><a class="ml-filter-chip ml-filter-chip-clear" href="<?php echo esc_url($archive_url); ?>"><?php esc_html_e('Clear all', 'marketlense-core'); ?></a></div><?php }
    private function render_active_publisher_directory_filters(string $directory_url, array $filters): void { $active = array_filter($filters); if ($active === []) { return; } ?><div class="ml-active-filters" aria-label="<?php esc_attr_e('Active filters', 'marketlense-core'); ?>"><span class="ml-active-filters-label"><?php esc_html_e('Selected', 'marketlense-core'); ?></span><?php foreach ($active as $key => $value) : ?><a class="ml-filter-chip" href="<?php echo esc_url(add_query_arg($this->publisher_directory_filter_args($filters, [$key]), $directory_url)); ?>"><?php echo esc_html(ucfirst($key) . ': ' . $value); ?></a><?php endforeach; ?><a class="ml-filter-chip ml-filter-chip-clear" href="<?php echo esc_url($directory_url); ?>"><?php esc_html_e('Clear all', 'marketlense-core'); ?></a></div><?php }
    private function render_sort_controls(string $archive_url, array $filters, string $selected_sort, string $plural): void { ?><nav class="ml-report-sort-controls" aria-label="<?php echo esc_attr(sprintf(__('Sort %s', 'marketlense-core'), strtolower($plural))); ?>"><?php foreach (['latest' => __('Newest', 'marketlense-core'), 'oldest' => __('Oldest', 'marketlense-core'), 'title' => __('A-Z', 'marketlense-core')] as $sort => $label) : ?><a class="ml-report-sort-control <?php echo $selected_sort === $sort ? 'is-active' : ''; ?>" href="<?php echo esc_url(add_query_arg(array_merge($this->filter_args($filters, []), $sort === 'latest' ? [] : ['ml_sort' => $sort]), $archive_url)); ?>"><span class="ml-report-sort-icon ml-report-sort-icon--<?php echo esc_attr($sort); ?>" aria-hidden="true"></span><span class="ml-report-sort-tooltip"><?php echo esc_html($label); ?></span></a><?php endforeach; ?></nav><?php }
    private function render_pagination(\WP_Query $query, array $filters): void { if ($query->max_num_pages <= 1) { return; } $links = paginate_links(['base' => str_replace('999999999', '%#%', (string) esc_url(get_pagenum_link(999999999))), 'current' => $this->current_page(), 'total' => $query->max_num_pages, 'type' => 'array', 'add_args' => $this->filter_args($filters, [])]); if (! is_array($links)) { return; } echo '<nav class="ml-pagination" aria-label="' . esc_attr__('Pagination', 'marketlense-core') . '"><ul>'; foreach ($links as $link) { echo '<li>' . wp_kses_post($link) . '</li>'; } echo '</ul></nav>'; }
    private function selected_sort(): string { $sort = sanitize_key((string) ($_GET['ml_sort'] ?? 'latest')); return in_array($sort, ['latest', 'oldest', 'title'], true) ? $sort : 'latest'; }
    private function current_page(): int { return max(1, (int) (get_query_var('paged') ?: get_query_var('page') ?: ($_GET['paged'] ?? 1))); }
    private function to_bool_flag(mixed $value): bool { return in_array((string) $value, ['1', 'true', 'yes', 'on'], true); }
    private function enqueue_filter_assets(): void { wp_enqueue_script('marketlense-core-report-filters', MARKETLENSE_CORE_URL . 'assets/js/report-filters.js', [], MARKETLENSE_CORE_VERSION, true); }
}
