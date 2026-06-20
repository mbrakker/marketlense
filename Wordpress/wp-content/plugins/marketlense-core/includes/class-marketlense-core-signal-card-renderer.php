<?php
/**
 * Canonical signal card markup.
 *
 * @package MarketLenseCore
 */

declare(strict_types=1);

namespace MarketLense\Core;

if (! defined('ABSPATH')) {
    exit;
}

final class Signal_Card_Renderer
{
    private const VARIANTS = ['small', 'medium', 'large'];

    /** @param array<string,mixed> $signal */
    public function render(array $signal, string $variant): string
    {
        if (! in_array($variant, self::VARIANTS, true)) {
            throw new \InvalidArgumentException('Unsupported signal card variant: ' . $variant);
        }
        if (($signal['card_contract_valid'] ?? false) !== true) {
            throw new \UnexpectedValueException('A valid signal card contract is required');
        }

        $cover = trim((string) (($signal['covers'][$variant] ?? '')));
        if ($cover === '') {
            throw new \UnexpectedValueException('The signal card cover is missing for variant: ' . $variant);
        }

        $title = $this->text($signal, 'title');
        $summary = $this->text($signal, 'summary');
        $confidence = (float) ($signal['confidence'] ?? -1);
        if ($confidence < 0 || $confidence > 1) {
            throw new \UnexpectedValueException('Signal card confidence is invalid');
        }
        $source_count = (int) ($signal['source_count'] ?? 0);
        $evidence_count = (int) ($signal['evidence_count'] ?? 0);
        if ($source_count < 1 || $evidence_count < 1) {
            throw new \UnexpectedValueException('Signal card proof counts are invalid');
        }

        ob_start();
        ?>
        <article class="ml-signal-card ml-signal-card--<?php echo esc_attr($variant); ?>">
            <a class="ml-signal-card__link" href="<?php echo esc_url($this->text($signal, 'permalink')); ?>">
                <div class="ml-signal-card__media">
                    <img class="ml-signal-card__cover" src="<?php echo esc_url($cover); ?>" alt="" loading="lazy" decoding="async">
                    <?php if (($signal['is_new'] ?? false) === true) : ?>
                        <span class="ml-signal-card__badge"><?php esc_html_e('New', 'marketlense-core'); ?></span>
                    <?php endif; ?>
                </div>
                <div class="ml-signal-card__body">
                    <p class="ml-signal-card__meta">
                        <span><?php echo esc_html($this->text($signal, 'date')); ?></span>
                        <span class="ml-signal-card__confidence"><?php echo esc_html((string) round($confidence * 100)); ?>% <?php esc_html_e('confidence', 'marketlense-core'); ?></span>
                    </p>
                    <h3 class="ml-signal-card__title"><?php echo esc_html($title); ?></h3>
                    <p class="ml-signal-card__summary"><?php echo esc_html($summary); ?></p>
                    <?php if ($variant !== 'small') : ?>
                        <?php $this->render_topics($signal['topics'] ?? null); ?>
                    <?php endif; ?>
                    <?php if ($variant === 'large') : ?>
                        <div class="ml-signal-card__condition">
                            <strong><?php esc_html_e('Evidence condition', 'marketlense-core'); ?></strong>
                            <span><?php echo esc_html($this->text($signal, 'uncertainty')); ?></span>
                        </div>
                    <?php endif; ?>
                    <ul class="ml-signal-card__proof">
                        <li><?php echo esc_html(sprintf(_n('%d source report', '%d source reports', $source_count, 'marketlense-core'), $source_count)); ?></li>
                        <li><?php echo esc_html(sprintf(_n('%d evidence item', '%d evidence items', $evidence_count, 'marketlense-core'), $evidence_count)); ?></li>
                    </ul>
                    <span class="ml-signal-card__action"><?php esc_html_e('Read signal', 'marketlense-core'); ?> &rarr;</span>
                </div>
            </a>
        </article>
        <?php
        return trim((string) ob_get_clean());
    }

    /** @param array<string,mixed> $signal */
    private function text(array $signal, string $key): string
    {
        $value = trim((string) ($signal[$key] ?? ''));
        if ($value === '') {
            throw new \UnexpectedValueException('Missing required signal card value: ' . $key);
        }
        return $value;
    }

    private function render_topics(mixed $value): void
    {
        if (! is_array($value) || $value === []) {
            throw new \UnexpectedValueException('Medium and large signal cards require topics');
        }
        $topics = array_values(array_filter(array_map('trim', array_map('strval', $value))));
        if ($topics === []) {
            throw new \UnexpectedValueException('Medium and large signal card topics must be complete');
        }
        ?>
        <ul class="ml-signal-card__topics">
            <?php foreach (array_slice($topics, 0, 3) as $topic) : ?>
                <li><?php echo esc_html($topic); ?></li>
            <?php endforeach; ?>
        </ul>
        <?php
    }
}
