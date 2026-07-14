<?php
/**
 * Taxonomy registration.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Taxonomies
{
    private const PUBLISHER_MANAGE_CAPABILITY = 'edit_posts';

    private const PUBLISHER_ADMIN_SLUG = 'ml-publisher-manager';

    public const CATEGORY_TAXONOMY = 'category';

    public const TOPIC_TAXONOMY = 'ml_topic';

    public const PUBLISHER_TAXONOMY = 'ml_publisher';

    public const TOPIC_DEFINITION_META = 'ml_topic_definition';

    public const TOPIC_INCLUDE_WHEN_META = 'ml_topic_include_when';

    public const TOPIC_EXCLUDE_WHEN_META = 'ml_topic_exclude_when';

    public const TOPIC_SCHEMA_VERSION_META = 'ml_topic_schema_version';

    public const PUBLISHER_HOMEPAGE_META = 'ml_publisher_homepage';

    public const PUBLISHER_INSIGHTS_META = 'ml_publisher_insights_url';

    public const PUBLISHER_ICON_META = 'ml_publisher_icon_source';

    public const PUBLISHER_NOTION_PAGE_ID_META = 'ml_publisher_notion_page_id';

    public const PUBLISHER_NOTION_PAGE_URL_META = 'ml_publisher_notion_page_url';

    public const PUBLISHER_REPORT_VALUE_SCORE_META = 'ml_publisher_report_value_score';
    public const PUBLISHER_REPORT_VALUE_BAND_META = 'ml_publisher_report_value_band';
    public const PUBLISHER_REPORT_VALUE_SAMPLE_SIZE_META = 'ml_publisher_report_value_sample_size';

    private const UNEXTRACTED_PUBLISHER_SLUGS = ['not-extracted'];

    public function register(): void
    {
        register_taxonomy(
            self::TOPIC_TAXONOMY,
            [Post_Type::POST_TYPE],
            [
                'labels' => [
                    'name'          => __('Legacy Topics', 'marketlense-core'),
                    'singular_name' => __('Legacy Topic', 'marketlense-core'),
                ],
                'public'            => false,
                'show_ui'           => false,
                'show_in_menu'      => false,
                'show_admin_column' => false,
                'show_in_rest'      => false,
                'rest_base'         => self::TOPIC_TAXONOMY,
                'hierarchical'      => false,
                'query_var'         => false,
                'rewrite'           => false,
            ]
        );

        register_taxonomy(
            self::PUBLISHER_TAXONOMY,
            [
                Post_Type::POST_TYPE,
                Post_Type::CORE_POST_TYPE,
                Post_Type::SIGNAL_POST_TYPE,
                Post_Type::BRIEFING_POST_TYPE,
            ],
            [
                'labels' => [
                    'name'          => __('Publishers', 'marketlense-core'),
                    'singular_name' => __('Publisher', 'marketlense-core'),
                    'search_items'  => __('Search Publishers', 'marketlense-core'),
                    'all_items'     => __('All Publishers', 'marketlense-core'),
                    'edit_item'     => __('Edit Publisher', 'marketlense-core'),
                    'update_item'   => __('Update Publisher', 'marketlense-core'),
                    'add_new_item'  => __('Add New Publisher', 'marketlense-core'),
                    'new_item_name' => __('New Publisher Name', 'marketlense-core'),
                    'menu_name'     => __('Publishers', 'marketlense-core'),
                ],
                'public'            => true,
                'show_ui'           => true,
                'show_in_menu'      => true,
                'show_admin_column' => true,
                'show_in_rest'      => true,
                'rest_base'         => self::PUBLISHER_TAXONOMY,
                'hierarchical'      => false,
                'query_var'         => true,
                'capabilities'      => [
                    'manage_terms' => self::PUBLISHER_MANAGE_CAPABILITY,
                    'edit_terms'   => self::PUBLISHER_MANAGE_CAPABILITY,
                    'delete_terms' => self::PUBLISHER_MANAGE_CAPABILITY,
                    'assign_terms' => self::PUBLISHER_MANAGE_CAPABILITY,
                ],
                'rewrite'           => [
                    'slug'       => 'publisher',
                    'with_front' => false,
                ],
            ]
        );

        register_term_meta(
            self::PUBLISHER_TAXONOMY,
            self::PUBLISHER_HOMEPAGE_META,
            [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => [$this, 'sanitize_homepage_meta'],
                'auth_callback'     => static function (): bool {
                    return current_user_can(self::PUBLISHER_MANAGE_CAPABILITY);
                },
            ]
        );
        register_term_meta(
            self::PUBLISHER_TAXONOMY,
            self::PUBLISHER_INSIGHTS_META,
            [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => [$this, 'sanitize_multi_url_meta'],
                'auth_callback'     => static function (): bool {
                    return current_user_can(self::PUBLISHER_MANAGE_CAPABILITY);
                },
            ]
        );
        register_term_meta(
            self::PUBLISHER_TAXONOMY,
            self::PUBLISHER_ICON_META,
            [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => [$this, 'sanitize_icon_meta'],
                'auth_callback'     => static function (): bool {
                    return current_user_can(self::PUBLISHER_MANAGE_CAPABILITY);
                },
            ]
        );
        register_term_meta(
            self::PUBLISHER_TAXONOMY,
            self::PUBLISHER_NOTION_PAGE_ID_META,
            [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => [$this, 'sanitize_notion_page_id_meta'],
                'auth_callback'     => static function (): bool {
                    return current_user_can(self::PUBLISHER_MANAGE_CAPABILITY);
                },
            ]
        );
        register_term_meta(
            self::PUBLISHER_TAXONOMY,
            self::PUBLISHER_NOTION_PAGE_URL_META,
            [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => [$this, 'sanitize_homepage_meta'],
                'auth_callback'     => static function (): bool {
                    return current_user_can(self::PUBLISHER_MANAGE_CAPABILITY);
                },
            ]
        );
        foreach ([
            self::PUBLISHER_REPORT_VALUE_SCORE_META => 'number',
            self::PUBLISHER_REPORT_VALUE_BAND_META => 'string',
            self::PUBLISHER_REPORT_VALUE_SAMPLE_SIZE_META => 'integer',
        ] as $key => $type) {
            register_term_meta(self::PUBLISHER_TAXONOMY, $key, [
                'type' => $type, 'single' => true, 'show_in_rest' => true,
                'sanitize_callback' => $type === 'string' ? 'sanitize_key' : static fn ($value) => $type === 'integer' ? max(0, (int) $value) : max(0.0, min(100.0, (float) $value)),
                'auth_callback' => static fn (): bool => current_user_can(self::PUBLISHER_MANAGE_CAPABILITY),
            ]);
        }

        register_term_meta(
            self::CATEGORY_TAXONOMY,
            self::TOPIC_DEFINITION_META,
            [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => 'sanitize_textarea_field',
                'auth_callback'     => static fn (): bool => current_user_can(self::PUBLISHER_MANAGE_CAPABILITY),
            ]
        );
        foreach ([self::TOPIC_INCLUDE_WHEN_META, self::TOPIC_EXCLUDE_WHEN_META] as $topic_rules_meta) {
            register_term_meta(
                self::CATEGORY_TAXONOMY,
                $topic_rules_meta,
                [
                    'type'              => 'array',
                    'single'            => true,
                    'show_in_rest'      => [
                        'schema' => [
                            'type'  => 'array',
                            'items' => ['type' => 'string'],
                        ],
                    ],
                    'sanitize_callback' => [$this, 'sanitize_topic_rule_list_meta'],
                    'auth_callback'     => static fn (): bool => current_user_can(self::PUBLISHER_MANAGE_CAPABILITY),
                ]
            );
        }
        register_term_meta(
            self::CATEGORY_TAXONOMY,
            self::TOPIC_SCHEMA_VERSION_META,
            [
                'type'              => 'string',
                'single'            => true,
                'show_in_rest'      => true,
                'sanitize_callback' => 'sanitize_text_field',
                'auth_callback'     => static fn (): bool => current_user_can(self::PUBLISHER_MANAGE_CAPABILITY),
            ]
        );

        add_action(
            self::PUBLISHER_TAXONOMY . '_add_form_fields',
            [$this, 'render_publisher_add_fields']
        );
        add_action(
            self::PUBLISHER_TAXONOMY . '_edit_form_fields',
            [$this, 'render_publisher_edit_fields']
        );
        add_action(
            'created_' . self::PUBLISHER_TAXONOMY,
            [$this, 'save_publisher_fields']
        );
        add_action(
            'edited_' . self::PUBLISHER_TAXONOMY,
            [$this, 'save_publisher_fields']
        );
        add_action('admin_menu', [$this, 'register_publisher_admin_menu'], 20);
        add_action('admin_init', [$this, 'redirect_native_publisher_admin_screen']);
        add_action('admin_enqueue_scripts', [$this, 'enqueue_publisher_admin_assets']);

        register_taxonomy_for_object_type(self::CATEGORY_TAXONOMY, Post_Type::POST_TYPE);
        register_taxonomy_for_object_type('post_tag', Post_Type::POST_TYPE);
        register_taxonomy_for_object_type(self::PUBLISHER_TAXONOMY, Post_Type::CORE_POST_TYPE);
    }

    /**
     * Converts legacy publisher projection sentinels into normal public 404 responses.
     */
    public function render_not_found_for_unextracted_publisher(): void
    {
        if (! is_tax(self::PUBLISHER_TAXONOMY)) {
            return;
        }

        $term = get_queried_object();
        if (! $term instanceof \WP_Term || ! in_array($term->slug, self::UNEXTRACTED_PUBLISHER_SLUGS, true)) {
            return;
        }

        global $wp_query;
        if ($wp_query instanceof \WP_Query) {
            $wp_query->set_404();
        }

        status_header(404);
        nocache_headers();
    }

    /**
     * Renders publisher taxonomy add form field.
     */
    public function render_publisher_add_fields(): void
    {
        wp_nonce_field('ml_publisher_homepage_nonce', 'ml_publisher_homepage_nonce');
        $this->render_publisher_add_input(
            self::PUBLISHER_HOMEPAGE_META,
            __('Publisher homepage', 'marketlense-core'),
            'https://example.com',
            __(
                'External homepage for this publisher. HTTPS is preferred and added automatically when omitted.',
                'marketlense-core'
            )
        );
        $this->render_publisher_add_input(
            self::PUBLISHER_INSIGHTS_META,
            __('Insights URL', 'marketlense-core'),
            'https://example.com/insights',
            __(
                'One or more publisher insights/report URLs. Multiple URLs can be separated with new lines in REST sync payloads.',
                'marketlense-core'
            ),
            'textarea'
        );
        $this->render_publisher_add_input(
            self::PUBLISHER_ICON_META,
            __('Icon source', 'marketlense-core'),
            'https://example.com/icon.png or 📊',
            __(
                'Supports HTTPS URLs, data:image URIs, or a short emoji/icon string.',
                'marketlense-core'
            ),
            'text'
        );
    }

    /**
     * Renders publisher taxonomy edit form field.
     *
     * @param \WP_Term $term Term instance.
     */
    public function render_publisher_edit_fields(\WP_Term $term): void
    {
        wp_nonce_field('ml_publisher_homepage_nonce', 'ml_publisher_homepage_nonce');
        $this->render_publisher_edit_input(
            $term->term_id,
            self::PUBLISHER_HOMEPAGE_META,
            __('Publisher homepage', 'marketlense-core'),
            'https://example.com',
            __(
                'External homepage for this publisher. HTTPS is preferred and added automatically when omitted.',
                'marketlense-core'
            )
        );
        $this->render_publisher_edit_input(
            $term->term_id,
            self::PUBLISHER_INSIGHTS_META,
            __('Insights URL', 'marketlense-core'),
            'https://example.com/insights',
            __(
                'One or more publisher insights/report URLs. Multiple URLs can be separated with new lines in REST sync payloads.',
                'marketlense-core'
            ),
            'textarea'
        );
        $this->render_publisher_edit_input(
            $term->term_id,
            self::PUBLISHER_ICON_META,
            __('Icon source', 'marketlense-core'),
            'https://example.com/icon.png or 📊',
            __(
                'Supports HTTPS URLs, data:image URIs, or a short emoji/icon string.',
                'marketlense-core'
            ),
            'text'
        );
    }

    /**
     * Saves publisher taxonomy extra fields.
     *
     * @param int $term_id Term identifier.
     */
    public function save_publisher_fields(int $term_id): void
    {
        if (! isset($_POST['ml_publisher_homepage_nonce'])) {
            return;
        }

        $nonce = sanitize_text_field(
            wp_unslash((string) $_POST['ml_publisher_homepage_nonce'])
        );
        if (! wp_verify_nonce($nonce, 'ml_publisher_homepage_nonce')) {
            return;
        }

        if (! current_user_can(self::PUBLISHER_MANAGE_CAPABILITY)) {
            return;
        }

        $raw_value = isset($_POST[self::PUBLISHER_HOMEPAGE_META])
            ? (string) wp_unslash($_POST[self::PUBLISHER_HOMEPAGE_META])
            : '';

        $normalized = $this->sanitize_homepage_meta($raw_value);
        if ($normalized === '') {
            delete_term_meta($term_id, self::PUBLISHER_HOMEPAGE_META);
            return;
        }

        update_term_meta($term_id, self::PUBLISHER_HOMEPAGE_META, $normalized);

        $raw_insights = isset($_POST[self::PUBLISHER_INSIGHTS_META])
            ? (string) wp_unslash($_POST[self::PUBLISHER_INSIGHTS_META])
            : '';
        $normalized_insights = $this->sanitize_multi_url_meta($raw_insights);
        if ($normalized_insights === '') {
            delete_term_meta($term_id, self::PUBLISHER_INSIGHTS_META);
        } else {
            update_term_meta($term_id, self::PUBLISHER_INSIGHTS_META, $normalized_insights);
        }

        $raw_icon = isset($_POST[self::PUBLISHER_ICON_META])
            ? (string) wp_unslash($_POST[self::PUBLISHER_ICON_META])
            : '';
        $normalized_icon = $this->sanitize_icon_meta($raw_icon);
        if ($normalized_icon === '') {
            delete_term_meta($term_id, self::PUBLISHER_ICON_META);
        } else {
            update_term_meta($term_id, self::PUBLISHER_ICON_META, $normalized_icon);
        }
    }

    /**
     * Sanitizes publisher homepage values before persistence.
     *
     * @param mixed $value Raw value.
     */
    public function sanitize_homepage_meta($value): string
    {
        $raw = sanitize_text_field((string) $value);
        $trimmed = trim($raw);
        if ($trimmed === '') {
            return '';
        }

        if (preg_match('/^[a-z][a-z0-9+\-.]*:\/\//i', $trimmed) !== 1) {
            $trimmed = 'https://' . $trimmed;
        }

        $validated = esc_url_raw($trimmed, ['https', 'http']);
        if ($validated === '' || ! wp_http_validate_url($validated)) {
            return '';
        }

        if (stripos($validated, 'http://') === 0) {
            $https_candidate = 'https://' . substr($validated, 7);
            if (wp_http_validate_url($https_candidate)) {
                $validated = $https_candidate;
            }
        }

        return (string) esc_url_raw($validated, ['https', 'http']);
    }

    /**
     * Sanitizes topic rule-list term metadata before REST persistence.
     *
     * @param mixed $value Raw REST/meta value.
     *
     * @return array<int, string>
     */
    public function sanitize_topic_rule_list_meta($value): array
    {
        $items = is_array($value) ? $value : [];
        $sanitized = [];
        foreach ($items as $item) {
            $text = trim(sanitize_text_field((string) $item));
            if ($text !== '') {
                $sanitized[] = $text;
            }
        }

        return array_values($sanitized);
    }

    /**
     * @param mixed $value Raw value.
     */
    public function sanitize_icon_meta($value): string
    {
        $trimmed = trim((string) $value);
        if ($trimmed === '') {
            return '';
        }

        if (preg_match('/^data:image\/[a-z0-9.+-]+;base64,[a-z0-9+\/=]+$/i', $trimmed) === 1) {
            return $trimmed;
        }

        $url = $this->sanitize_homepage_meta($trimmed);
        if ($url !== '') {
            return $url;
        }

        return sanitize_text_field($trimmed);
    }

    /**
     * @param mixed $value Raw value.
     */
    public function sanitize_multi_url_meta($value): string
    {
        $raw = trim((string) $value);
        if ($raw === '') {
            return '';
        }

        $segments = preg_split('/[\r\n]+/', $raw) ?: [];
        $normalized = [];
        foreach ($segments as $segment) {
            $url = $this->sanitize_homepage_meta($segment);
            if ($url !== '' && ! in_array($url, $normalized, true)) {
                $normalized[] = $url;
            }
        }

        return implode("\n", $normalized);
    }

    /**
     * @param mixed $value Raw value.
     */
    public function sanitize_notion_page_id_meta($value): string
    {
        $trimmed = strtolower(trim((string) $value));
        if ($trimmed === '') {
            return '';
        }

        if (preg_match('/^[0-9a-f-]{36}$/', $trimmed) !== 1) {
            return '';
        }

        return $trimmed;
    }

    public function register_publisher_admin_menu(): void
    {
        $parent_slug = 'edit.php?post_type=' . Post_Type::POST_TYPE;
        $native_slug = 'edit-tags.php?taxonomy=' . self::PUBLISHER_TAXONOMY . '&post_type=' . Post_Type::POST_TYPE;

        remove_submenu_page($parent_slug, $native_slug);
        add_submenu_page(
            $parent_slug,
            __('Publishers', 'marketlense-core'),
            __('Publishers', 'marketlense-core'),
            self::PUBLISHER_MANAGE_CAPABILITY,
            self::PUBLISHER_ADMIN_SLUG,
            [$this, 'render_publisher_admin_page']
        );
    }

    public function enqueue_publisher_admin_assets(string $hook_suffix): void
    {
        if (! $this->is_publisher_admin_screen($hook_suffix)) {
            return;
        }

        wp_register_style('marketlense-core-publisher-admin', false, [], MARKETLENSE_CORE_VERSION);
        wp_enqueue_style('marketlense-core-publisher-admin');
        wp_add_inline_style('marketlense-core-publisher-admin', $this->publisher_admin_css());
    }

    public function redirect_native_publisher_admin_screen(): void
    {
        if (! is_admin()) {
            return;
        }

        global $pagenow;
        if (! is_string($pagenow) || ! in_array($pagenow, ['edit-tags.php', 'term.php'], true)) {
            return;
        }

        $taxonomy = isset($_GET['taxonomy'])
            ? sanitize_key((string) wp_unslash($_GET['taxonomy']))
            : '';
        $post_type = isset($_GET['post_type'])
            ? sanitize_key((string) wp_unslash($_GET['post_type']))
            : '';

        if ($taxonomy !== self::PUBLISHER_TAXONOMY || $post_type !== Post_Type::POST_TYPE) {
            return;
        }

        if (! current_user_can(self::PUBLISHER_MANAGE_CAPABILITY)) {
            return;
        }

        $query_args = [];
        $term_id = isset($_GET['tag_ID']) ? (int) $_GET['tag_ID'] : 0;
        if ($term_id > 0) {
            $query_args['action'] = 'edit';
            $query_args['term_id'] = $term_id;
        }

        wp_safe_redirect(add_query_arg($query_args, $this->publisher_admin_base_url()));
        exit;
    }

    public function render_publisher_admin_page(): void
    {
        if (! current_user_can(self::PUBLISHER_MANAGE_CAPABILITY)) {
            wp_die(esc_html__('You are not allowed to manage publishers.', 'marketlense-core'));
        }

        $this->handle_publisher_admin_request();

        $editing_term = $this->selected_publisher_term();
        $terms = get_terms(
            [
                'taxonomy' => self::PUBLISHER_TAXONOMY,
                'hide_empty' => false,
                'orderby' => 'name',
                'order' => 'ASC',
            ]
        );
        $terms = is_wp_error($terms) || ! is_array($terms) ? [] : $terms;

        $notice = isset($_GET['ml_notice'])
            ? sanitize_key((string) wp_unslash($_GET['ml_notice']))
            : '';
        $form_action = $this->publisher_admin_base_url();

        ?>
        <div class="wrap ml-publisher-admin">
            <h1><?php esc_html_e('Publishers', 'marketlense-core'); ?></h1>
            <?php $this->render_publisher_admin_notice($notice); ?>

            <div class="ml-publisher-admin__layout">
                <form method="post" action="<?php echo esc_url($form_action); ?>" class="ml-publisher-admin__panel ml-publisher-admin__panel-editor">
                    <h2 class="ml-publisher-admin__heading">
                        <?php
                        echo esc_html(
                            $editing_term instanceof \WP_Term
                                ? __('Edit publisher', 'marketlense-core')
                                : __('Add publisher', 'marketlense-core')
                        );
                        ?>
                    </h2>
                    <?php wp_nonce_field('ml_manage_publisher_admin', 'ml_manage_publisher_admin_nonce'); ?>
                    <input type="hidden" name="ml_publisher_admin_action" value="save">
                    <input type="hidden" name="term_id" value="<?php echo esc_attr($editing_term instanceof \WP_Term ? (string) $editing_term->term_id : '0'); ?>">

                    <div class="ml-publisher-admin__fields">
                        <div class="ml-publisher-admin__field">
                            <label class="ml-publisher-admin__label" for="ml_publisher_name"><?php esc_html_e('Name', 'marketlense-core'); ?></label>
                            <input class="regular-text" type="text" id="ml_publisher_name" name="ml_publisher_name" value="<?php echo esc_attr($editing_term instanceof \WP_Term ? $editing_term->name : ''); ?>" required>
                        </div>

                        <div class="ml-publisher-admin__field">
                            <label class="ml-publisher-admin__label" for="ml_publisher_slug"><?php esc_html_e('Slug', 'marketlense-core'); ?></label>
                            <input class="regular-text" type="text" id="ml_publisher_slug" name="ml_publisher_slug" value="<?php echo esc_attr($editing_term instanceof \WP_Term ? $editing_term->slug : ''); ?>">
                            <p class="description"><?php esc_html_e('Optional. Leave empty to auto-generate from the name.', 'marketlense-core'); ?></p>
                        </div>

                        <div class="ml-publisher-admin__field">
                            <label class="ml-publisher-admin__label" for="ml_publisher_description"><?php esc_html_e('Self presentation', 'marketlense-core'); ?></label>
                            <textarea class="large-text" rows="7" id="ml_publisher_description" name="ml_publisher_description"><?php echo esc_textarea($editing_term instanceof \WP_Term ? $editing_term->description : ''); ?></textarea>
                        </div>

                        <div class="ml-publisher-admin__field">
                            <label class="ml-publisher-admin__label" for="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>"><?php esc_html_e('Homepage', 'marketlense-core'); ?></label>
                            <input class="regular-text" type="text" id="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>" name="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>" value="<?php echo esc_attr($editing_term instanceof \WP_Term ? (string) get_term_meta($editing_term->term_id, self::PUBLISHER_HOMEPAGE_META, true) : ''); ?>">
                        </div>

                        <div class="ml-publisher-admin__field">
                            <label class="ml-publisher-admin__label" for="<?php echo esc_attr(self::PUBLISHER_INSIGHTS_META); ?>"><?php esc_html_e('Insights URLs', 'marketlense-core'); ?></label>
                            <textarea class="large-text" rows="5" id="<?php echo esc_attr(self::PUBLISHER_INSIGHTS_META); ?>" name="<?php echo esc_attr(self::PUBLISHER_INSIGHTS_META); ?>"><?php echo esc_textarea($editing_term instanceof \WP_Term ? (string) get_term_meta($editing_term->term_id, self::PUBLISHER_INSIGHTS_META, true) : ''); ?></textarea>
                            <p class="description"><?php esc_html_e('One URL per line.', 'marketlense-core'); ?></p>
                        </div>

                        <div class="ml-publisher-admin__field">
                            <label class="ml-publisher-admin__label" for="<?php echo esc_attr(self::PUBLISHER_ICON_META); ?>"><?php esc_html_e('Icon source', 'marketlense-core'); ?></label>
                            <textarea class="large-text code" rows="4" id="<?php echo esc_attr(self::PUBLISHER_ICON_META); ?>" name="<?php echo esc_attr(self::PUBLISHER_ICON_META); ?>"><?php echo esc_textarea($editing_term instanceof \WP_Term ? (string) get_term_meta($editing_term->term_id, self::PUBLISHER_ICON_META, true) : ''); ?></textarea>
                            <p class="description"><?php esc_html_e('Supports HTTPS URLs, data:image URIs, or emoji/text.', 'marketlense-core'); ?></p>
                        </div>
                    </div>

                    <p class="submit ml-publisher-admin__submit">
                        <button type="submit" class="button button-primary">
                            <?php
                            echo esc_html(
                                $editing_term instanceof \WP_Term
                                    ? __('Update publisher', 'marketlense-core')
                                    : __('Add publisher', 'marketlense-core')
                            );
                            ?>
                        </button>
                        <?php if ($editing_term instanceof \WP_Term) : ?>
                            <a class="button" href="<?php echo esc_url($form_action); ?>"><?php esc_html_e('Cancel', 'marketlense-core'); ?></a>
                        <?php endif; ?>
                    </p>
                </form>

                <div class="ml-publisher-admin__panel ml-publisher-admin__panel-list">
                    <div class="ml-publisher-admin__list-header">
                        <h2 class="ml-publisher-admin__heading"><?php esc_html_e('All publishers', 'marketlense-core'); ?></h2>
                        <p class="ml-publisher-admin__meta"><?php echo esc_html(sprintf(_n('%d publisher', '%d publishers', count($terms), 'marketlense-core'), count($terms))); ?></p>
                    </div>
                    <div class="ml-publisher-admin__table-wrap">
                    <table class="widefat striped fixed ml-publisher-admin__table">
                        <thead>
                            <tr>
                                <th class="ml-publisher-admin__col-name"><?php esc_html_e('Name', 'marketlense-core'); ?></th>
                                <th class="ml-publisher-admin__col-count"><?php esc_html_e('Reports', 'marketlense-core'); ?></th>
                                <th class="ml-publisher-admin__col-homepage"><?php esc_html_e('Homepage', 'marketlense-core'); ?></th>
                                <th class="ml-publisher-admin__col-actions"><?php esc_html_e('Actions', 'marketlense-core'); ?></th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php if ($terms === []) : ?>
                                <tr><td colspan="4"><?php esc_html_e('No publishers found.', 'marketlense-core'); ?></td></tr>
                            <?php else : ?>
                                <?php foreach ($terms as $term) : ?>
                                    <?php if (! ($term instanceof \WP_Term)) { continue; } ?>
                                    <?php
                                    $homepage = (string) get_term_meta($term->term_id, self::PUBLISHER_HOMEPAGE_META, true);
                                    $archive_link = get_term_link($term);
                                    $edit_url = add_query_arg(
                                        [
                                            'action' => 'edit',
                                            'term_id' => $term->term_id,
                                        ],
                                        $form_action
                                    );
                                    $delete_url = wp_nonce_url(
                                        add_query_arg(
                                            [
                                                'action' => 'delete',
                                                'term_id' => $term->term_id,
                                            ],
                                            $form_action
                                        ),
                                        'ml_delete_publisher_' . $term->term_id
                                    );
                                    ?>
                                    <tr>
                                        <td class="ml-publisher-admin__cell-name"><strong><?php echo esc_html($term->name); ?></strong></td>
                                        <td class="ml-publisher-admin__cell-count"><?php echo esc_html((string) $term->count); ?></td>
                                        <td class="ml-publisher-admin__cell-homepage">
                                            <?php if ($homepage !== '') : ?>
                                                <a href="<?php echo esc_url($homepage); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html($homepage); ?></a>
                                            <?php else : ?>
                                                <span aria-hidden="true">-</span>
                                            <?php endif; ?>
                                        </td>
                                        <td class="ml-publisher-admin__cell-actions">
                                            <div class="ml-publisher-admin__actions">
                                            <a href="<?php echo esc_url($edit_url); ?>"><?php esc_html_e('Edit', 'marketlense-core'); ?></a>
                                            <?php if (! is_wp_error($archive_link)) : ?>
                                                <a href="<?php echo esc_url((string) $archive_link); ?>" target="_blank" rel="noopener noreferrer"><?php esc_html_e('View', 'marketlense-core'); ?></a>
                                            <?php endif; ?>
                                            <a href="<?php echo esc_url($delete_url); ?>" onclick="return confirm('<?php echo esc_js(__('Delete this publisher?', 'marketlense-core')); ?>');"><?php esc_html_e('Delete', 'marketlense-core'); ?></a>
                                            </div>
                                        </td>
                                    </tr>
                                <?php endforeach; ?>
                            <?php endif; ?>
                        </tbody>
                    </table>
                    </div>
                </div>
            </div>
        </div>
        <?php
    }

    private function handle_publisher_admin_request(): void
    {
        $action = isset($_REQUEST['action'])
            ? sanitize_key((string) wp_unslash($_REQUEST['action']))
            : '';

        if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['ml_publisher_admin_action'])) {
            $nonce = isset($_POST['ml_manage_publisher_admin_nonce'])
                ? sanitize_text_field((string) wp_unslash($_POST['ml_manage_publisher_admin_nonce']))
                : '';
            if (! wp_verify_nonce($nonce, 'ml_manage_publisher_admin')) {
                wp_die(esc_html__('Invalid publisher request.', 'marketlense-core'));
            }

            $term_id = isset($_POST['term_id']) ? (int) $_POST['term_id'] : 0;
            $name = sanitize_text_field((string) wp_unslash($_POST['ml_publisher_name'] ?? ''));
            $slug = sanitize_title((string) wp_unslash($_POST['ml_publisher_slug'] ?? ''));
            $description = wp_kses_post((string) wp_unslash($_POST['ml_publisher_description'] ?? ''));

            if ($name === '') {
                wp_safe_redirect(add_query_arg('ml_notice', 'missing-name', $this->publisher_admin_base_url()));
                exit;
            }

            $term_args = [
                'description' => $description,
            ];
            if ($slug !== '') {
                $term_args['slug'] = $slug;
            }

            if ($term_id > 0) {
                $result = wp_update_term($term_id, self::PUBLISHER_TAXONOMY, array_merge(['name' => $name], $term_args));
            } else {
                $result = wp_insert_term($name, self::PUBLISHER_TAXONOMY, $term_args);
            }

            if (is_wp_error($result)) {
                wp_safe_redirect(add_query_arg('ml_notice', 'save-error', $this->publisher_admin_base_url()));
                exit;
            }

            $saved_term_id = $term_id > 0
                ? $term_id
                : (int) ((is_array($result) && isset($result['term_id'])) ? $result['term_id'] : 0);

            if ($saved_term_id > 0) {
                $this->persist_publisher_admin_meta($saved_term_id);
            }

            wp_safe_redirect(add_query_arg('ml_notice', 'saved', $this->publisher_admin_base_url()));
            exit;
        }

        if ($action !== 'delete') {
            return;
        }

        $term_id = isset($_GET['term_id']) ? (int) $_GET['term_id'] : 0;
        if ($term_id < 1) {
            return;
        }

        check_admin_referer('ml_delete_publisher_' . $term_id);
        wp_delete_term($term_id, self::PUBLISHER_TAXONOMY);
        wp_safe_redirect(add_query_arg('ml_notice', 'deleted', $this->publisher_admin_base_url()));
        exit;
    }

    private function persist_publisher_admin_meta(int $term_id): void
    {
        $homepage = $this->sanitize_homepage_meta((string) wp_unslash($_POST[self::PUBLISHER_HOMEPAGE_META] ?? ''));
        if ($homepage === '') {
            delete_term_meta($term_id, self::PUBLISHER_HOMEPAGE_META);
        } else {
            update_term_meta($term_id, self::PUBLISHER_HOMEPAGE_META, $homepage);
        }

        $insights = $this->sanitize_multi_url_meta((string) wp_unslash($_POST[self::PUBLISHER_INSIGHTS_META] ?? ''));
        if ($insights === '') {
            delete_term_meta($term_id, self::PUBLISHER_INSIGHTS_META);
        } else {
            update_term_meta($term_id, self::PUBLISHER_INSIGHTS_META, $insights);
        }

        $icon = $this->sanitize_icon_meta((string) wp_unslash($_POST[self::PUBLISHER_ICON_META] ?? ''));
        if ($icon === '') {
            delete_term_meta($term_id, self::PUBLISHER_ICON_META);
        } else {
            update_term_meta($term_id, self::PUBLISHER_ICON_META, $icon);
        }
    }

    private function selected_publisher_term(): ?\WP_Term
    {
        $action = isset($_GET['action'])
            ? sanitize_key((string) wp_unslash($_GET['action']))
            : '';
        $term_id = isset($_GET['term_id']) ? (int) $_GET['term_id'] : 0;

        if ($action !== 'edit' || $term_id < 1) {
            return null;
        }

        $term = get_term($term_id, self::PUBLISHER_TAXONOMY);

        return $term instanceof \WP_Term ? $term : null;
    }

    private function render_publisher_admin_notice(string $notice): void
    {
        $messages = [
            'saved' => __('Publisher saved.', 'marketlense-core'),
            'deleted' => __('Publisher deleted.', 'marketlense-core'),
            'missing-name' => __('Publisher name is required.', 'marketlense-core'),
            'save-error' => __('Publisher could not be saved.', 'marketlense-core'),
        ];

        if (! isset($messages[$notice])) {
            return;
        }

        $class = in_array($notice, ['missing-name', 'save-error'], true)
            ? 'notice notice-error'
            : 'notice notice-success is-dismissible';

        printf(
            '<div class="%1$s"><p>%2$s</p></div>',
            esc_attr($class),
            esc_html($messages[$notice])
        );
    }

    private function publisher_admin_base_url(): string
    {
        return add_query_arg(
            [
                'post_type' => Post_Type::POST_TYPE,
                'page' => self::PUBLISHER_ADMIN_SLUG,
            ],
            admin_url('edit.php')
        );
    }

    private function is_publisher_admin_screen(string $hook_suffix): bool
    {
        if (str_contains($hook_suffix, self::PUBLISHER_ADMIN_SLUG)) {
            return true;
        }

        $page = isset($_GET['page'])
            ? sanitize_key((string) wp_unslash($_GET['page']))
            : '';

        return $page === self::PUBLISHER_ADMIN_SLUG;
    }

    private function publisher_admin_css(): string
    {
        return <<<'CSS'
.ml-publisher-admin {
  --ml-admin-border: #d0d6dc;
  --ml-admin-panel: #ffffff;
  --ml-admin-muted: #59636e;
  --ml-admin-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}

.ml-publisher-admin__layout {
  display: grid;
  grid-template-columns: minmax(320px, 34rem) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.ml-publisher-admin__panel {
  background: var(--ml-admin-panel);
  border: 1px solid var(--ml-admin-border);
  box-shadow: var(--ml-admin-shadow);
  padding: 24px;
}

.ml-publisher-admin__panel-editor {
  position: sticky;
  top: 46px;
}

.ml-publisher-admin__heading {
  margin: 0 0 18px;
}

.ml-publisher-admin__fields {
  display: grid;
  gap: 18px;
}

.ml-publisher-admin__field {
  display: grid;
  gap: 8px;
}

.ml-publisher-admin__label {
  font-weight: 600;
  color: #1d2327;
}

.ml-publisher-admin__field input[type="text"],
.ml-publisher-admin__field textarea {
  width: 100%;
  max-width: none;
  margin: 0;
}

.ml-publisher-admin__field textarea.code {
  font-family: Consolas, Monaco, monospace;
}

.ml-publisher-admin__field .description {
  margin: 0;
  color: var(--ml-admin-muted);
}

.ml-publisher-admin__submit {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin: 20px 0 0;
}

.ml-publisher-admin__list-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-end;
  margin-bottom: 18px;
}

.ml-publisher-admin__meta {
  margin: 0;
  color: var(--ml-admin-muted);
}

.ml-publisher-admin__table-wrap {
  overflow-x: auto;
}

.ml-publisher-admin__table {
  table-layout: fixed;
}

.ml-publisher-admin__table th,
.ml-publisher-admin__table td {
  vertical-align: top;
}

.ml-publisher-admin__col-name {
  width: 28%;
}

.ml-publisher-admin__col-count {
  width: 72px;
}

.ml-publisher-admin__col-actions {
  width: 148px;
}

.ml-publisher-admin__cell-homepage a {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.ml-publisher-admin__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}

@media (max-width: 1180px) {
  .ml-publisher-admin__layout {
    grid-template-columns: 1fr;
  }

  .ml-publisher-admin__panel-editor {
    position: static;
  }
}
CSS;
    }

    private function render_publisher_add_input(
        string $meta_key,
        string $label,
        string $placeholder,
        string $description,
        string $type = 'url'
    ): void {
        ?>
        <div class="form-field term-group">
            <label for="<?php echo esc_attr($meta_key); ?>">
                <?php echo esc_html($label); ?>
            </label>
            <?php if ($type === 'textarea') : ?>
                <textarea
                    id="<?php echo esc_attr($meta_key); ?>"
                    name="<?php echo esc_attr($meta_key); ?>"
                    rows="3"
                    placeholder="<?php echo esc_attr($placeholder); ?>"
                ></textarea>
            <?php else : ?>
                <input
                    type="<?php echo esc_attr($type); ?>"
                    id="<?php echo esc_attr($meta_key); ?>"
                    name="<?php echo esc_attr($meta_key); ?>"
                    value=""
                    placeholder="<?php echo esc_attr($placeholder); ?>"
                />
            <?php endif; ?>
            <p><?php echo esc_html($description); ?></p>
        </div>
        <?php
    }

    private function render_publisher_edit_input(
        int $term_id,
        string $meta_key,
        string $label,
        string $placeholder,
        string $description,
        string $type = 'url'
    ): void {
        $value = (string) get_term_meta($term_id, $meta_key, true);
        ?>
        <tr class="form-field term-group-wrap">
            <th scope="row">
                <label for="<?php echo esc_attr($meta_key); ?>">
                    <?php echo esc_html($label); ?>
                </label>
            </th>
            <td>
                <?php if ($type === 'textarea') : ?>
                    <textarea
                        id="<?php echo esc_attr($meta_key); ?>"
                        name="<?php echo esc_attr($meta_key); ?>"
                        rows="3"
                        placeholder="<?php echo esc_attr($placeholder); ?>"
                        class="large-text"
                    ><?php echo esc_textarea($value); ?></textarea>
                <?php else : ?>
                    <input
                        type="<?php echo esc_attr($type); ?>"
                        id="<?php echo esc_attr($meta_key); ?>"
                        name="<?php echo esc_attr($meta_key); ?>"
                        value="<?php echo esc_attr($value); ?>"
                        placeholder="<?php echo esc_attr($placeholder); ?>"
                        class="regular-text"
                    />
                <?php endif; ?>
                <p class="description"><?php echo esc_html($description); ?></p>
            </td>
        </tr>
        <?php
    }
}
