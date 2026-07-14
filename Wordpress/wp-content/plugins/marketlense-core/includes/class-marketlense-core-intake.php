<?php
/**
 * Minimal public briefing, correction, and source-submission intake.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Intake
{
    private const POST_TYPE = 'ml_intake';

    private const ACTION = 'marketlense_submit_intake';

    /**
     * Registers the private operator inbox, shortcodes, and public form handler.
     */
    public function register(): void
    {
        register_post_type(
            self::POST_TYPE,
            [
                'labels' => [
                    'name' => __('Intake requests', 'marketlense-core'),
                    'singular_name' => __('Intake request', 'marketlense-core'),
                    'menu_name' => __('Intake', 'marketlense-core'),
                    'all_items' => __('Intake requests', 'marketlense-core'),
                ],
                'public' => false,
                'show_ui' => true,
                'show_in_menu' => true,
                'show_in_rest' => false,
                'exclude_from_search' => true,
                'publicly_queryable' => false,
                'capability_type' => 'post',
                'map_meta_cap' => true,
                'supports' => ['title'],
                'menu_position' => 23,
                'menu_icon' => 'dashicons-feedback',
            ]
        );

        add_shortcode('ml_intake_form', [$this, 'render_form']);
        add_action('admin_post_' . self::ACTION, [$this, 'submit']);
        add_action('admin_post_nopriv_' . self::ACTION, [$this, 'submit']);
    }

    /**
     * @param array<string,string> $attributes
     */
    public function render_form(array $attributes = []): string
    {
        $type = $this->normalize_type($attributes['type'] ?? '');
        if ($type === '') {
            return '';
        }

        $status = sanitize_key((string) ($_GET['ml_intake_status'] ?? ''));
        $fields = $this->fields_for($type);
        $html = '<section class="ml-intake" aria-labelledby="ml-intake-' . esc_attr($type) . '">';
        $html .= '<h2 id="ml-intake-' . esc_attr($type) . '">' . esc_html($this->heading_for($type)) . '</h2>';
        $html .= $this->render_status($status);
        $html .= '<form class="ml-intake__form" method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
        $html .= '<input type="hidden" name="action" value="' . esc_attr(self::ACTION) . '">';
        $html .= '<input type="hidden" name="intake_type" value="' . esc_attr($type) . '">';
        $html .= '<input type="hidden" name="return_url" value="' . esc_url($this->current_url()) . '">';
        $html .= wp_nonce_field('marketlense_intake_' . $type, 'marketlense_intake_nonce', true, false);
        $html .= '<p class="ml-intake__honeypot" aria-hidden="true"><label>' . esc_html__('Leave this field empty', 'marketlense-core') . '<input type="text" name="website" tabindex="-1" autocomplete="off"></label></p>';

        foreach ($fields as $name => $field) {
            $id = 'ml-intake-' . $type . '-' . $name;
            $required = $field['required'] ? ' required' : '';
            $html .= '<p class="ml-intake__field"><label for="' . esc_attr($id) . '">' . esc_html($field['label']);
            if ($field['required']) {
                $html .= ' <span aria-hidden="true">*</span>';
            }
            $html .= '</label>';
            if ($field['kind'] === 'textarea') {
                $html .= '<textarea id="' . esc_attr($id) . '" name="' . esc_attr($name) . '" rows="5"' . $required . '></textarea>';
            } else {
                $html .= '<input id="' . esc_attr($id) . '" name="' . esc_attr($name) . '" type="' . esc_attr($field['kind']) . '"' . $required . '>';
            }
            $html .= '</p>';
        }

        $html .= '<p><button class="wp-block-button__link wp-element-button ml-button" type="submit">' . esc_html($this->submit_label_for($type)) . '</button></p>';
        $html .= '</form></section>';

        return $html;
    }

    /**
     * Persists a validated request as a private WordPress record and redirects safely.
     */
    public function submit(): void
    {
        $type = $this->normalize_type((string) ($_POST['intake_type'] ?? ''));
        $return_url = $this->safe_return_url((string) ($_POST['return_url'] ?? ''));
        if ($type === '' || ! isset($_POST['marketlense_intake_nonce']) || ! wp_verify_nonce(sanitize_text_field(wp_unslash((string) $_POST['marketlense_intake_nonce'])), 'marketlense_intake_' . $type)) {
            $this->redirect($return_url, 'invalid_request');
        }
        if (trim((string) wp_unslash($_POST['website'] ?? '')) !== '') {
            $this->log('rejected', $type, 0, 'spam');
            $this->redirect($return_url, 'spam_rejected');
        }

        $values = $this->sanitize_values($type);
        if (! is_email($values['email'])) {
            $this->redirect($return_url, 'invalid_email');
        }
        foreach ($this->fields_for($type) as $name => $field) {
            if ($field['required'] && $values[$name] === '') {
                $this->redirect($return_url, 'missing_fields');
            }
        }
        foreach (['report_url', 'source_url'] as $url_field) {
            if ($values[$url_field] !== '' && ! wp_http_validate_url($values[$url_field])) {
                $this->redirect($return_url, 'invalid_url');
            }
        }

        $request_id = wp_insert_post(
            [
                'post_type' => self::POST_TYPE,
                'post_status' => 'private',
                'post_title' => sprintf('%s: %s', ucfirst($type), $values['name']),
                'meta_input' => [
                    '_ml_intake_schema_version' => '1.0',
                    '_ml_intake_type' => $type,
                    '_ml_intake_email' => $values['email'],
                    '_ml_intake_organization' => $values['organization'],
                    '_ml_intake_report_url' => $values['report_url'],
                    '_ml_intake_source_url' => $values['source_url'],
                    '_ml_intake_publisher' => $values['publisher'],
                    '_ml_intake_request' => $values['request'],
                    '_ml_intake_received_at_utc' => gmdate('c'),
                ],
            ],
            true
        );
        if (is_wp_error($request_id)) {
            $this->log('failed', $type, 0, 'persistence_failed');
            $this->redirect($return_url, 'request_failed');
        }
        $this->log('received', $type, (int) $request_id, 'persisted');
        $this->redirect($return_url, 'received');
    }

    /**
     * @return array<string,array{label:string,kind:string,required:bool}>
     */
    private function fields_for(string $type): array
    {
        $base = [
            'name' => ['label' => __('Name', 'marketlense-core'), 'kind' => 'text', 'required' => true],
            'email' => ['label' => __('Work email', 'marketlense-core'), 'kind' => 'email', 'required' => true],
            'organization' => ['label' => __('Organisation', 'marketlense-core'), 'kind' => 'text', 'required' => false],
        ];
        if ($type === 'correction') {
            return $base + [
                'report_url' => ['label' => __('Report URL', 'marketlense-core'), 'kind' => 'url', 'required' => true],
                'request' => ['label' => __('Correction and source support', 'marketlense-core'), 'kind' => 'textarea', 'required' => true],
            ];
        }
        if ($type === 'submission') {
            return $base + [
                'source_url' => ['label' => __('Report or source URL', 'marketlense-core'), 'kind' => 'url', 'required' => true],
                'publisher' => ['label' => __('Publisher', 'marketlense-core'), 'kind' => 'text', 'required' => false],
                'request' => ['label' => __('Why this matters now', 'marketlense-core'), 'kind' => 'textarea', 'required' => true],
            ];
        }
        return $base + [
            'request' => ['label' => __('Briefing goal and timing', 'marketlense-core'), 'kind' => 'textarea', 'required' => true],
        ];
    }

    /** @return array{name:string,email:string,organization:string,report_url:string,source_url:string,publisher:string,request:string} */
    private function sanitize_values(string $type): array
    {
        $fields = $this->fields_for($type);
        $values = ['name' => '', 'email' => '', 'organization' => '', 'report_url' => '', 'source_url' => '', 'publisher' => '', 'request' => ''];
        foreach (array_keys($fields) as $name) {
            $raw = wp_unslash((string) ($_POST[$name] ?? ''));
            $values[$name] = in_array($name, ['request'], true) ? sanitize_textarea_field($raw) : sanitize_text_field($raw);
            if (in_array($name, ['report_url', 'source_url'], true)) {
                $values[$name] = esc_url_raw($raw, ['http', 'https']);
            }
        }
        return $values;
    }

    private function normalize_type(string $type): string
    {
        $normalized = sanitize_key($type);
        return in_array($normalized, ['briefing', 'correction', 'submission'], true) ? $normalized : '';
    }

    private function heading_for(string $type): string
    {
        return match ($type) {
            'correction' => __('Send an editorial correction', 'marketlense-core'),
            'submission' => __('Submit a source for review', 'marketlense-core'),
            default => __('Request a briefing', 'marketlense-core'),
        };
    }

    private function submit_label_for(string $type): string
    {
        return $type === 'correction' ? __('Send correction', 'marketlense-core') : ($type === 'submission' ? __('Submit for review', 'marketlense-core') : __('Request briefing', 'marketlense-core'));
    }

    private function render_status(string $status): string
    {
        if ($status === 'received') {
            return '<p class="ml-intake__status ml-intake__status--success" role="status">' . esc_html__('Thank you. Your request has been received and is now available to the appropriate team.', 'marketlense-core') . '</p>';
        }
        $messages = [
            'invalid_request' => __('Please reload the page and try again.', 'marketlense-core'),
            'spam_rejected' => __('We could not accept that request. Please contact us directly if this was unexpected.', 'marketlense-core'),
            'invalid_email' => __('Enter a valid work email address.', 'marketlense-core'),
            'invalid_url' => __('Enter a valid public URL.', 'marketlense-core'),
            'missing_fields' => __('Complete the required fields and try again.', 'marketlense-core'),
            'request_failed' => __('We could not save the request. Please try again shortly.', 'marketlense-core'),
        ];
        return isset($messages[$status]) ? '<p class="ml-intake__status ml-intake__status--error" role="alert">' . esc_html($messages[$status]) . '</p>' : '';
    }

    private function current_url(): string
    {
        $request_uri = isset($_SERVER['REQUEST_URI']) ? wp_unslash((string) $_SERVER['REQUEST_URI']) : '/';
        return home_url(strtok($request_uri, '?') ?: '/');
    }

    private function safe_return_url(string $url): string
    {
        return wp_validate_redirect($url, home_url('/contact/'));
    }

    private function redirect(string $url, string $status): void
    {
        wp_safe_redirect(add_query_arg('ml_intake_status', $status, $url));
        exit;
    }

    private function log(string $event, string $type, int $request_id, string $outcome): void
    {
        error_log((string) wp_json_encode([
            'event' => 'marketlense_intake_' . $event,
            'request_id' => $request_id,
            'request_type' => $type,
            'outcome' => $outcome,
        ]));
    }
}
