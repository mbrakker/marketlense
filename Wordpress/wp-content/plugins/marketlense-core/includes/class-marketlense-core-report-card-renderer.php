<?php
/**
 * Canonical report card markup.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Report_Card_Renderer
{
    private const VARIANTS = ['small', 'medium', 'large'];

    /**
     * Renders a validated report view model at one canonical density.
     *
     * @param array<string,mixed> $report
     */
    public function render(array $report, string $variant): string
    {
        if (! in_array($variant, self::VARIANTS, true)) {
            throw new \InvalidArgumentException('Unsupported report card variant: ' . $variant);
        }
        if (($report['card_contract_valid'] ?? false) !== true) {
            return '';
        }

        $title = $this->required_text($report, 'title');
        $permalink = $this->required_text($report, 'permalink');
        $publisher = $this->required_text($report, 'publisher');
        $title_scale = $this->required_text($report, 'title_scale');
        if (in_array('', [$title, $permalink, $publisher, $title_scale], true)) {
            return '';
        }
        $covers = is_array($report['covers'] ?? null) ? $report['covers'] : [];
        $cover_url = trim((string) ($covers[$variant] ?? ''));
        if ($cover_url === '') {
            return '';
        }

        $tldr_key = $variant === 'small' ? 'tldr_compact' : 'tldr_standard';
        $tldr = $this->required_text($report, $tldr_key);
        if ($tldr === '') {
            return '';
        }
        if ($variant === 'large' && ! $this->has_complete_insights($report['key_insights'] ?? null)) {
            return '';
        }
        $date = trim((string) ($report['date'] ?? ''));
        $geography = trim((string) ($report['geography'] ?? ''));
        $geography_icon = trim((string) ($report['geography_icon'] ?? ''));
        $time_period = trim((string) ($report['time_period'] ?? ''));
        $is_new = ($report['is_new'] ?? false) === true;

        ob_start();
        ?>
        <article class="ml-card ml-card--<?php echo esc_attr($variant); ?> ml-card--title-<?php echo esc_attr($title_scale); ?>">
            <a class="ml-card__link" href="<?php echo esc_url($permalink); ?>">
                <div class="ml-card__media">
                    <img
                        class="ml-card__cover"
                        src="<?php echo esc_url($cover_url); ?>"
                        alt=""
                        loading="lazy"
                        decoding="async"
                    >
                    <?php if ($is_new) : ?>
                        <span class="ml-card__badge"><?php echo esc_html__('New', 'marketlense-core'); ?></span>
                    <?php endif; ?>
                </div>
                <div class="ml-card__body">
                    <p class="ml-card__publisher"><?php echo esc_html($publisher); ?></p>
                    <h3 class="ml-card__title"><?php echo esc_html($title); ?></h3>
                    <?php $this->render_facts($date, $geography, $geography_icon, $time_period); ?>
                    <p class="ml-card__tldr"><?php echo esc_html($tldr); ?></p>
                    <?php if ($variant === 'large') : ?>
                        <?php $this->render_insights($report['key_insights'] ?? null); ?>
                    <?php endif; ?>
                    <span class="ml-card__action">
                        <?php echo esc_html__('Read report', 'marketlense-core'); ?>
                        <?php echo $this->icon('arrow'); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                    </span>
                </div>
            </a>
        </article>
        <?php

        return trim((string) ob_get_clean());
    }

    /**
     * @param array<string,mixed> $report
     */
    private function required_text(array $report, string $key): string
    {
        $value = trim((string) ($report[$key] ?? ''));
        if ($value === '') {
            return '';
        }

        return $value;
    }

    private function render_facts(
        string $date,
        string $geography,
        string $geography_icon,
        string $time_period
    ): void {
        $facts = [];
        if ($date !== '') {
            $facts[] = ['calendar', $date];
        }
        if ($geography !== '' && in_array($geography_icon, ['globe', 'locator'], true)) {
            $facts[] = [$geography_icon, $geography];
        }
        if ($time_period !== '') {
            $facts[] = ['period', $time_period];
        }
        if ($facts === []) {
            return;
        }
        ?>
        <ul class="ml-card__facts" aria-label="<?php echo esc_attr(esc_html__('Report details', 'marketlense-core')); ?>">
            <?php foreach ($facts as [$icon, $label]) : ?>
                <li>
                    <?php echo $this->icon($icon); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
                    <span><?php echo esc_html($label); ?></span>
                </li>
            <?php endforeach; ?>
        </ul>
        <?php
    }

    private function render_insights(mixed $value): void
    {
        $insights = array_map(
            static fn (mixed $insight): string => trim((string) $insight),
            array_values($value)
        );
        ?>
        <ul class="ml-card__insights">
            <?php foreach ($insights as $insight) : ?>
                <li><?php echo esc_html($insight); ?></li>
            <?php endforeach; ?>
        </ul>
        <?php
    }

    private function has_complete_insights(mixed $value): bool
    {
        if (! is_array($value) || count($value) !== 2) {
            return false;
        }
        foreach ($value as $insight) {
            if (trim((string) $insight) === '') {
                return false;
            }
        }

        return true;
    }

    private function icon(string $name): string
    {
        return match ($name) {
            'calendar' => '<svg class="ml-card__icon ml-card__icon--calendar" aria-hidden="true" viewBox="0 0 24 24"><path d="M7 2v3M17 2v3M3.5 9h17M5 4h14a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/></svg>',
            'globe' => '<svg class="ml-card__icon ml-card__icon--globe" aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
            'locator' => '<svg class="ml-card__icon ml-card__icon--locator" aria-hidden="true" viewBox="0 0 24 24"><path d="M12 22s7-6.2 7-13a7 7 0 1 0-14 0c0 6.8 7 13 7 13Z"/><circle cx="12" cy="9" r="2.5"/></svg>',
            'period' => '<svg class="ml-card__icon ml-card__icon--period" aria-hidden="true" viewBox="0 0 24 24"><path d="M4 7h16M7 4v6M17 4v6M5 5h14a2 2 0 0 1 2 2v12H3V7a2 2 0 0 1 2-2Z"/><path d="m8 15 2 2 5-5"/></svg>',
            'arrow' => '<svg class="ml-card__action-icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M5 12h14M14 7l5 5-5 5"/></svg>',
            default => '',
        };
    }
}
