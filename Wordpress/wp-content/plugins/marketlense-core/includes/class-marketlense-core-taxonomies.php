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
    public const CATEGORY_TAXONOMY = 'category';

    public const TOPIC_TAXONOMY = 'ml_topic';

    public const PUBLISHER_TAXONOMY = 'ml_publisher';

    public const PUBLISHER_HOMEPAGE_META = 'ml_publisher_homepage';

    public function register(): void
    {
        register_taxonomy(
            self::TOPIC_TAXONOMY,
            [Post_Type::POST_TYPE],
            [
                'labels' => [
                    'name'          => __('Topics', 'marketlense-core'),
                    'singular_name' => __('Topic', 'marketlense-core'),
                    'search_items'  => __('Search Topics', 'marketlense-core'),
                    'all_items'     => __('All Topics', 'marketlense-core'),
                    'edit_item'     => __('Edit Topic', 'marketlense-core'),
                    'update_item'   => __('Update Topic', 'marketlense-core'),
                    'add_new_item'  => __('Add New Topic', 'marketlense-core'),
                    'new_item_name' => __('New Topic Name', 'marketlense-core'),
                    'menu_name'     => __('Topics', 'marketlense-core'),
                ],
                'public'            => true,
                'show_ui'           => true,
                'show_in_menu'      => true,
                'show_admin_column' => true,
                'show_in_rest'      => true,
                'rest_base'         => self::TOPIC_TAXONOMY,
                'hierarchical'      => false,
                'query_var'         => true,
                'rewrite'           => [
                    'slug'       => 'topic',
                    'with_front' => false,
                ],
            ]
        );

        register_taxonomy(
            self::PUBLISHER_TAXONOMY,
            [Post_Type::POST_TYPE],
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
                    return current_user_can('manage_categories');
                },
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

        register_taxonomy_for_object_type(self::CATEGORY_TAXONOMY, Post_Type::POST_TYPE);
        register_taxonomy_for_object_type('post_tag', Post_Type::POST_TYPE);
    }

    /**
     * Renders publisher taxonomy add form field.
     */
    public function render_publisher_add_fields(): void
    {
        wp_nonce_field('ml_publisher_homepage_nonce', 'ml_publisher_homepage_nonce');
        ?>
        <div class="form-field term-group">
            <label for="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>">
                <?php esc_html_e('Publisher homepage', 'marketlense-core'); ?>
            </label>
            <input
                type="url"
                id="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>"
                name="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>"
                value=""
                placeholder="https://example.com"
            />
            <p>
                <?php
                esc_html_e(
                    'External homepage for this publisher. HTTPS is preferred and added automatically when omitted.',
                    'marketlense-core'
                );
                ?>
            </p>
        </div>
        <?php
    }

    /**
     * Renders publisher taxonomy edit form field.
     *
     * @param \WP_Term $term Term instance.
     */
    public function render_publisher_edit_fields(\WP_Term $term): void
    {
        $value = (string) get_term_meta(
            $term->term_id,
            self::PUBLISHER_HOMEPAGE_META,
            true
        );
        wp_nonce_field('ml_publisher_homepage_nonce', 'ml_publisher_homepage_nonce');
        ?>
        <tr class="form-field term-group-wrap">
            <th scope="row">
                <label for="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>">
                    <?php esc_html_e('Publisher homepage', 'marketlense-core'); ?>
                </label>
            </th>
            <td>
                <input
                    type="url"
                    id="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>"
                    name="<?php echo esc_attr(self::PUBLISHER_HOMEPAGE_META); ?>"
                    value="<?php echo esc_attr($value); ?>"
                    placeholder="https://example.com"
                    class="regular-text"
                />
                <p class="description">
                    <?php
                    esc_html_e(
                        'External homepage for this publisher. HTTPS is preferred and added automatically when omitted.',
                        'marketlense-core'
                    );
                    ?>
                </p>
            </td>
        </tr>
        <?php
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

        if (! current_user_can('manage_categories')) {
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
}
