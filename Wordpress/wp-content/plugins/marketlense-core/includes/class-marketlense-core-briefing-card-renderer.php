<?php
/**
 * Canonical briefing card markup.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Briefing_Card_Renderer
{
    private const VARIANTS = ['small', 'medium', 'large'];

    /** @param array<string,mixed> $briefing */
    public function render(array $briefing, string $variant): string
    {
        if (! in_array($variant, self::VARIANTS, true)) {
            throw new \InvalidArgumentException('Unsupported briefing card variant: ' . $variant);
        }
        if (($briefing['card_contract_valid'] ?? false) !== true) {
            throw new \UnexpectedValueException('A valid briefing card contract is required');
        }
        $cover = trim((string) (($briefing['covers'][$variant] ?? '')));
        if ($cover === '') {
            throw new \UnexpectedValueException('The briefing card cover is missing for variant: ' . $variant);
        }
        $title = $this->text($briefing, 'title');
        $summary = $this->text($briefing, $variant === 'small' ? 'summary_compact' : 'summary_standard');
        ob_start(); ?>
        <article class="ml-briefing-card ml-briefing-card--<?php echo esc_attr($variant); ?>">
            <a class="ml-briefing-card__link" href="<?php echo esc_url($this->text($briefing, 'permalink')); ?>">
                <div class="ml-briefing-card__media">
                    <img class="ml-briefing-card__cover" src="<?php echo esc_url($cover); ?>" alt="" loading="lazy" decoding="async">
                    <?php if (($briefing['is_new'] ?? false) === true) : ?><span class="ml-briefing-card__badge"><?php esc_html_e('New', 'marketlense-core'); ?></span><?php endif; ?>
                </div>
                <div class="ml-briefing-card__body">
                    <p class="ml-briefing-card__meta"><?php echo esc_html($this->text($briefing, 'date')); ?></p>
                    <h3 class="ml-briefing-card__title"><?php echo esc_html($title); ?></h3>
                    <p class="ml-briefing-card__summary"><?php echo esc_html($summary); ?></p>
                    <?php if ($variant !== 'small') : ?><p class="ml-briefing-card__focus"><strong><?php esc_html_e('Decision focus', 'marketlense-core'); ?></strong><?php echo esc_html($this->text($briefing, 'decision_focus')); ?></p><?php endif; ?>
                    <?php if ($variant === 'large') : ?><ul class="ml-briefing-card__takeaways"><?php foreach ($briefing['takeaways'] as $takeaway) : ?><li><?php echo esc_html((string) $takeaway); ?></li><?php endforeach; ?></ul><?php endif; ?>
                    <ul class="ml-briefing-card__counters">
                        <li><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="13" height="15" rx="2"></rect><path d="M8 9h5M8 13h5M8 17h3M17 8h3v11a1 1 0 0 1-1 1h-2"></path></svg><span><?php echo esc_html(sprintf(_n('%d source report', '%d source reports', (int) $briefing['source_count'], 'marketlense-core'), (int) $briefing['source_count'])); ?></span></li>
                        <li><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4.5 7.2v9.6L12 21l7.5-4.2V7.2L12 3Z"></path><path d="m8.5 12 2.2 2.2 4.8-4.8"></path></svg><span><?php echo esc_html(sprintf(_n('%d evidence item', '%d evidence items', (int) $briefing['evidence_count'], 'marketlense-core'), (int) $briefing['evidence_count'])); ?></span></li>
                    </ul>
                    <span class="ml-briefing-card__action"><?php esc_html_e('Read briefing', 'marketlense-core'); ?> &rarr;</span>
                </div>
            </a>
        </article>
        <?php return trim((string) ob_get_clean());
    }

    /** @param array<string,mixed> $briefing */
    private function text(array $briefing, string $key): string
    {
        $value = trim((string) ($briefing[$key] ?? ''));
        if ($value === '') {
            throw new \UnexpectedValueException('Missing required briefing card value: ' . $key);
        }
        return $value;
    }
}
