"""Shared browser-evaluation script builders for publisher inventory discovery.

This module keeps the canonical publisher inventory service boundary stable while
moving raw DOM script text into one capability-focused internal namespace.
"""

from __future__ import annotations

import json


def _browser_named_control_selector() -> str:
    return (
        "button, "
        '[role="button"], '
        'a[role="button"], '
        "a.button, "
        "a.btn, "
        "a.wp-block-button__link, "
        "a.cursor-pointer, "
        'a[class*="btn"], '
        'input[type="button"], '
        'input[type="submit"], '
        ".load-more"
    )


def _browser_dom_helper_bundle(*, lower_case: bool) -> str:
    normalize_body = (
        "String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase()"
        if lower_case
        else "String(value ?? '').replace(/\\s+/g, ' ').trim()"
    )
    return f"""
        const normalize = (value) => {normalize_body};
        const isVisible = (element) => {{
            if (!element) return false;
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
        }};
        const isEnabled = (element) => {{
            if (!element) return false;
            const ariaDisabled = normalize(element.getAttribute('aria-disabled')).toLowerCase();
            const className = normalize(element.className || '').toLowerCase();
            return !element.disabled && ariaDisabled !== 'true' && !/\\bdisabled\\b/.test(className);
        }};
    """


def _browser_scroll_to_ratio_script() -> str:
    return """(ratio) => {
        const value = Number(ratio || 0);
        const maxY = Math.max(
            0,
            Math.max(
                document.body ? document.body.scrollHeight : 0,
                document.documentElement ? document.documentElement.scrollHeight : 0
            ) - window.innerHeight
        );
        const clamped = Math.max(0, Math.min(1, value));
        window.scrollTo(0, Math.round(maxY * clamped));
        return true;
    }"""


def _browser_inventory_growth_probe_script() -> str:
    return """() => JSON.stringify({
        pageUrl: window.location.href || '',
        anchorCount: document.querySelectorAll('a[href]').length || 0,
    })"""


def _browser_inventory_settle_probe_script() -> str:
    return """() => JSON.stringify({
        readyState: document.readyState || '',
        title: document.title || '',
        anchorCount: document.querySelectorAll('a[href]').length || 0,
    })"""


def _browser_inventory_state_script() -> str:
    named_control_selector = json.dumps(_browser_named_control_selector())
    helper_bundle = _browser_dom_helper_bundle(lower_case=False)
    script = """() => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        __HELPER_BUNDLE__
        const anchors = Array.from(document.querySelectorAll('a[href]')).map((anchor) => {
            const image = anchor.querySelector('img');
            const card = anchor.closest('article, li, section, div');
            const heading = card ? card.querySelector('h1, h2, h3, h4, h5, h6') : null;
            return {
                href: normalize(anchor.href || anchor.getAttribute('href') || ''),
                text: normalize(anchor.textContent),
                rel: normalize(anchor.getAttribute('rel')),
                aria_label: normalize(anchor.getAttribute('aria-label')),
                title_attr: normalize(anchor.getAttribute('title')),
                img_alt: normalize(image ? image.getAttribute('alt') : ''),
                heading_text: normalize(heading ? heading.textContent : ''),
                context_text: normalize(card ? card.textContent : ''),
                visible: isVisible(anchor),
            };
        }).filter((item) => item.href && item.visible);
        const collectLabels = (elements) => elements
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''))
            .filter((label) => label);
        const controlEntries = Array.from(document.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => ({
                element,
                label: normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''),
            }))
            .filter((entry) => entry.label);
        const paginationContainerSelector = '[aria-label*="pagination" i], [class*="pagination" i], [data-testid*="pagination" i], nav, ul, ol';
        const isPaginationNextLabel = (label) => /^(next|next page|>|>>|»)$/i.test(label);
        const pageCountText = Array.from(document.querySelectorAll('body *'))
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || ''))
            .filter((text) => /^page\\s+\\d+\\s+of\\s+\\d+$/i.test(text))
            .pop() || '';
        const pageCountMatch = pageCountText.match(/^page\\s+(\\d+)\\s+of\\s+(\\d+)$/i);
        const visibleContainerLabels = (container) => Array.from(container.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''))
            .filter((label) => label);
        const paginationContainers = Array.from(new Set(
            controlEntries
                .map((entry) => entry.element.closest(paginationContainerSelector))
                .filter((container) => container)
        ));
        const hasPaginationNext = paginationContainers.some((container) => {
            const labels = visibleContainerLabels(container);
            return labels.some((label) => /^\\d+$/.test(label)) && labels.some((label) => isPaginationNextLabel(label));
        }) || (
            controlEntries.some((entry) => /^\\d+$/.test(entry.label)) &&
            controlEntries.some((entry) => isPaginationNextLabel(entry.label))
        ) || (
            Boolean(pageCountMatch) &&
            controlEntries.some((entry) => isPaginationNextLabel(entry.label))
        );
        const loadMoreLabels = collectLabels(
            Array.from(document.querySelectorAll(namedControlSelector))
                .filter((element) => /(^|\\b)(load|show|view|see)\\b.*\\b(more|all|next)\\b|^more$/i.test(normalize(element.textContent || element.getAttribute('aria-label') || element.value || '')))
        );
        const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
        const tabLabels = tabs
            .filter((tab) => isVisible(tab))
            .map((tab) => normalize(tab.textContent || tab.getAttribute('aria-label') || ''))
            .filter((label) => label);
        const activeTab = tabs.find((tab) => (tab.getAttribute('aria-selected') || '').toLowerCase() === 'true');
        const reportLink = Array.from(document.querySelectorAll('a[href]'))
            .find((anchor) => {
                const href = normalize(anchor.href || anchor.getAttribute('href') || '');
                const label = normalize(anchor.textContent || anchor.getAttribute('aria-label') || '');
                if (!href || !label) return false;
                if (href.replace(/\\/$/, '') === window.location.href.replace(/\\/$/, '')) return false;
                return (
                    (href.includes('/insights/report/') && /report/i.test(label || href)) ||
                    (
                        /(explore|view|see|browse|open|discover)( all)?/i.test(label) &&
                        /(report|reports|research|resource|resources|library|white paper|whitepaper|ebook)/i.test(label)
                    ) ||
                    (
                        /(report|reports|research|resource library|resource center|white paper|whitepaper|ebook)/i.test(label) &&
                        /\\/(reports?|resources?|resource-library|knowledge-hub|library)\\//i.test(href)
                    )
                );
            });
        const reportFilter = Array.from(document.querySelectorAll('label, button, div, span')).some((element) => {
            const label = normalize(element.textContent || element.getAttribute('aria-label') || '');
            return label === 'Report' || label === 'Reports';
        });
        const applyButton = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'))
            .some((element) => /^apply$/i.test(normalize(element.textContent || element.value || element.getAttribute('aria-label') || '')) && isVisible(element));
        const emptyResultsVisible = Array.from(document.querySelectorAll('body *'))
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || ''))
            .some((text) => /couldn't find any matches|no matches|no results|no resources found|try adjusting your filters|clear(?:ing)? your filters/i.test(text));
        const resetFilterLabels = collectLabels(
            Array.from(document.querySelectorAll(namedControlSelector))
                .filter((element) => /^(reset|clear)( all)? filters?$|^reset all$|^clear all$/i.test(normalize(element.textContent || element.getAttribute('aria-label') || element.value || '')))
        );
        const resultRangeText = Array.from(document.querySelectorAll('body *'))
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || ''))
            .filter((text) => /\\d+\\s*-\\s*\\d+\\s+of\\s+\\d+\\s+results/i.test(text))
            .pop() || '';
        const resultRangeMatch = resultRangeText.match(/(\\d+)\\s*-\\s*(\\d+)\\s+of\\s+(\\d+)\\s+results/i);
        return {
            page_url: window.location.href,
            page_title: document.title,
            anchors,
            load_more_labels: loadMoreLabels,
            tab_labels: tabLabels,
            active_tab_label: normalize(activeTab ? activeTab.textContent || activeTab.getAttribute('aria-label') || '' : ''),
            report_link_url: reportLink ? normalize(reportLink.href || reportLink.getAttribute('href') || '') : '',
            empty_results_visible: emptyResultsVisible,
            reset_filter_labels: resetFilterLabels,
            has_report_filter: reportFilter,
            has_apply_button: applyButton,
            has_pagination_next: hasPaginationNext,
            result_range_end: resultRangeMatch ? Number(resultRangeMatch[2]) : 0,
            result_range_total: resultRangeMatch ? Number(resultRangeMatch[3]) : 0,
            page_index_hint: pageCountMatch ? Number(pageCountMatch[1]) : 0,
            page_total_hint: pageCountMatch ? Number(pageCountMatch[2]) : 0,
        };
    }"""
    return (
        script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)
        .replace("__HELPER_BUNDLE__", helper_bundle)
    )


def _browser_rendered_html_script() -> str:
    return """() => document.documentElement ? document.documentElement.outerHTML : ''"""


def _browser_click_named_control_script() -> str:
    named_control_selector = json.dumps(_browser_named_control_selector())
    helper_bundle = _browser_dom_helper_bundle(lower_case=True)
    script = """(payloadOrLabels) => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        __HELPER_BUNDLE__
        const payload = Array.isArray(payloadOrLabels)
            ? { labels: payloadOrLabels, candidate_urls: [] }
            : (payloadOrLabels || {});
        const wanted = Array.isArray(payload.labels) ? payload.labels.map((item) => normalize(item)).filter((item) => item) : [];
        const requireCandidateSurface = payload.require_candidate_surface === true;
        const normalizeHref = (value) => {
            const raw = String(value ?? '').trim();
            if (!raw) return '';
            try {
                const parsed = new URL(raw, window.location.href);
                parsed.hash = '';
                return parsed.href.replace(/\\/$/, '');
            } catch (_error) {
                return normalize(raw);
            }
        };
        const candidateUrls = new Set(
            (Array.isArray(payload.candidate_urls) ? payload.candidate_urls : [])
                .map((item) => normalizeHref(String(item || '')))
                .filter((item) => item)
        );
        const collectVisibleAnchorHrefs = (container) => {
            if (!container || typeof container.querySelectorAll !== 'function') return [];
            return Array.from(container.querySelectorAll('a[href]'))
                .filter((anchor) => isVisible(anchor))
                .map((anchor) => normalizeHref(anchor.href || anchor.getAttribute('href') || ''))
                .filter((href) => href);
        };
        const scoreElement = (element, index) => {
            let bestExactHits = 0;
            let bestAnchorCount = Number.MAX_SAFE_INTEGER;
            let node = element;
            let depth = 0;
            while (node && depth < 8) {
                if (node instanceof Element) {
                    const hrefs = collectVisibleAnchorHrefs(node);
                    const exactHits = hrefs.filter((href) => candidateUrls.has(href)).length;
                    if (exactHits > bestExactHits) {
                        bestExactHits = exactHits;
                        bestAnchorCount = hrefs.length || Number.MAX_SAFE_INTEGER;
                    } else if (exactHits > 0 && exactHits === bestExactHits) {
                        bestAnchorCount = Math.min(bestAnchorCount, hrefs.length || Number.MAX_SAFE_INTEGER);
                    }
                }
                node = node.parentElement;
                depth += 1;
            }
            return {
                element,
                index,
                exactHits: bestExactHits,
                anchorCount: bestAnchorCount,
                top: Math.round(element.getBoundingClientRect().top || 0),
            };
        };
        const elements = Array.from(document.querySelectorAll(namedControlSelector));
        const matches = [];
        for (const [index, element] of elements.entries()) {
            const label = normalize(element.textContent || element.getAttribute('aria-label') || element.value || '');
            if (!label || !isVisible(element) || !isEnabled(element)) continue;
            if (wanted.some((candidate) => label === candidate || label.includes(candidate))) {
                matches.push({ label, ...scoreElement(element, index) });
            }
        }
        matches.sort((left, right) => {
            if (right.exactHits !== left.exactHits) return right.exactHits - left.exactHits;
            if (left.exactHits > 0 && left.anchorCount !== right.anchorCount) {
                return left.anchorCount - right.anchorCount;
            }
            if (right.top !== left.top) return right.top - left.top;
            return right.index - left.index;
        });
        const target = matches[0];
        if (!target) return false;
        const minRelevantHits = candidateUrls.size > 0
            ? (candidateUrls.size > 4 ? Math.min(3, Math.ceil(candidateUrls.size / 4)) : 1)
            : 0;
        if (requireCandidateSurface && candidateUrls.size > 0 && target.exactHits < minRelevantHits) {
            return 'not_relevant';
        }
        if (typeof target.element.scrollIntoView === 'function') {
            target.element.scrollIntoView({ block: 'center', inline: 'center' });
        }
        target.element.click();
        return true;
    }"""
    return (
        script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)
        .replace("__HELPER_BUNDLE__", helper_bundle)
    )


def _browser_click_cookie_banner_script() -> str:
    named_control_selector = json.dumps(_browser_named_control_selector())
    helper_bundle = _browser_dom_helper_bundle(lower_case=True)
    script = """() => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        __HELPER_BUNDLE__
        const wanted = [
            'accept all cookies',
            'accept all',
            'accept',
            'agree',
            'ok',
            'close',
            'continue',
        ];
        const bannerSelector = [
            '[id*="cookie" i]',
            '[class*="cookie" i]',
            '[id*="consent" i]',
            '[class*="consent" i]',
            '[id*="onetrust" i]',
            '[class*="onetrust" i]',
            '[aria-label*="cookie" i]',
            '[aria-label*="consent" i]',
            '[role="dialog"]',
            '[role="region"]'
        ].join(', ');
        const containers = Array.from(document.querySelectorAll(bannerSelector))
            .filter((element) => isVisible(element))
            .filter((element) => {
                const descriptor = normalize([
                    element.id || '',
                    element.className || '',
                    element.getAttribute('aria-label') || '',
                    element.textContent || '',
                ].join(' '));
                return /(cookie|consent|privacy|onetrust)/i.test(descriptor);
            });
        for (const container of containers) {
            const controls = Array.from(container.querySelectorAll(namedControlSelector))
                .filter((element) => isVisible(element) && isEnabled(element))
                .map((element) => ({
                    element,
                    label: normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''),
                }))
                .filter((entry) => entry.label);
            const target = controls.find((entry) => wanted.some((label) => entry.label === label || entry.label.includes(label)));
            if (!target) continue;
            if (typeof target.element.scrollIntoView === 'function') {
                target.element.scrollIntoView({ block: 'center', inline: 'center' });
            }
            target.element.click();
            return true;
        }
        return false;
    }"""
    return (
        script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)
        .replace("__HELPER_BUNDLE__", helper_bundle)
    )


def _browser_click_pagination_next_script() -> str:
    named_control_selector = json.dumps(_browser_named_control_selector())
    helper_bundle = _browser_dom_helper_bundle(lower_case=True)
    script = """() => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        __HELPER_BUNDLE__
        const paginationContainerSelector = '[aria-label*="pagination" i], [class*="pagination" i], [data-testid*="pagination" i], nav, ul, ol';
        const isPaginationNextLabel = (label) => /^(next|next page|>|>>|»)$/i.test(label);
        const pageCountText = Array.from(document.querySelectorAll('body *'))
            .filter((element) => isVisible(element))
            .map((element) => normalize(element.textContent || ''))
            .filter((text) => /^page\\s+\\d+\\s+of\\s+\\d+$/i.test(text))
            .pop() || '';
        const pageCountMatch = pageCountText.match(/^page\\s+(\\d+)\\s+of\\s+(\\d+)$/i);
        const controlEntries = Array.from(document.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => ({
                element,
                label: normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''),
            }))
            .filter((entry) => entry.label);
        const visibleContainerEntries = (container) => Array.from(container.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element) && isEnabled(element))
            .map((element) => ({
                element,
                label: normalize(element.textContent || element.getAttribute('aria-label') || element.value || ''),
            }))
            .filter((entry) => entry.label);
        const paginationContainers = Array.from(new Set(
            controlEntries
                .map((entry) => entry.element.closest(paginationContainerSelector))
                .filter((container) => container)
        ));
        for (const container of paginationContainers) {
            const entries = visibleContainerEntries(container);
            if (!entries.some((entry) => /^\\d+$/.test(entry.label))) continue;
            const nextEntry = entries.find((entry) => isPaginationNextLabel(entry.label));
            if (!nextEntry) continue;
            if (typeof nextEntry.element.scrollIntoView === 'function') {
                nextEntry.element.scrollIntoView({ block: 'center', inline: 'center' });
            }
            nextEntry.element.click();
            return true;
        }
        if (pageCountMatch) {
            const nextEntry = controlEntries.find((entry) => isPaginationNextLabel(entry.label));
            if (nextEntry) {
                if (typeof nextEntry.element.scrollIntoView === 'function') {
                    nextEntry.element.scrollIntoView({ block: 'center', inline: 'center' });
                }
                nextEntry.element.click();
                return true;
            }
        }
        if (controlEntries.some((entry) => /^\\d+$/.test(entry.label))) {
            const nextEntry = controlEntries.find((entry) => isPaginationNextLabel(entry.label));
            if (nextEntry) {
                if (typeof nextEntry.element.scrollIntoView === 'function') {
                    nextEntry.element.scrollIntoView({ block: 'center', inline: 'center' });
                }
                nextEntry.element.click();
                return true;
            }
        }
        return false;
    }"""
    return (
        script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)
        .replace("__HELPER_BUNDLE__", helper_bundle)
    )


def _browser_click_archive_expander_script() -> str:
    helper_bundle = _browser_dom_helper_bundle(lower_case=True)
    named_control_selector = json.dumps(
        "button, [role=\"button\"], a[role=\"button\"], a.button, a.btn, "
        "a.wp-block-button__link, a.cursor-pointer, a[class*=\"btn\"], "
        "a[href], input[type=\"button\"], input[type=\"submit\"]"
    )
    script = """() => {
        const namedControlSelector = __NAMED_CONTROL_SELECTOR__;
        __HELPER_BUNDLE__
        const controls = Array.from(document.querySelectorAll(namedControlSelector))
            .filter((element) => isVisible(element))
            .map((element) => {
                const label = normalize(element.textContent || element.value || element.getAttribute('aria-label') || '');
                const href = normalize(element.getAttribute('href') || '');
                let score = 0;
                if (/(view|explore|see|show|browse|open)( all)?/.test(label)) score += 3;
                if (/(library|archive|entries|items|reports?|resources?|research|collection)/.test(label)) score += 4;
                if (/\\d+\\+?/.test(label)) score += 2;
                if (/#\\/(feed|library|archive)/.test(href)) score += 4;
                if (/\\/(reports?|resources?|resource-library|knowledge-hub|library|archive)\\b/.test(href)) score += 3;
                if (!href || href === '#') score += 1;
                return { element, score };
            })
            .filter((entry) => entry.score >= 7)
            .sort((left, right) => right.score - left.score);
        if (!controls.length) return false;
        if (typeof controls[0].element.scrollIntoView === 'function') {
            controls[0].element.scrollIntoView({ block: 'center', inline: 'center' });
        }
        controls[0].element.click();
        return true;
    }"""
    return (
        script.replace("__NAMED_CONTROL_SELECTOR__", named_control_selector)
        .replace("__HELPER_BUNDLE__", helper_bundle)
    )


def _browser_click_tab_script() -> str:
    helper_bundle = _browser_dom_helper_bundle(lower_case=True)
    script = """(tabLabel) => {
        __HELPER_BUNDLE__
        const target = normalize(tabLabel);
        const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
        for (const tab of tabs) {
            const label = normalize(tab.textContent || tab.getAttribute('aria-label') || '');
            if (!label || !isVisible(tab) || label !== target) continue;
            tab.click();
            return true;
        }
        return false;
    }"""
    return script.replace("__HELPER_BUNDLE__", helper_bundle)


def _browser_apply_report_filter_script() -> str:
    helper_bundle = _browser_dom_helper_bundle(lower_case=True)
    script = """() => {
        __HELPER_BUNDLE__
        const candidates = Array.from(document.querySelectorAll('input[type="checkbox"], input[type="radio"], [role="checkbox"]'));
        const preferredOptionLabels = [
            'report',
            'reports',
            'whitepaper',
            'whitepapers',
            'white paper',
            'ebook',
            'ebooks',
            'insight guide',
            'insight guides',
            'study',
            'studies',
            'research report',
            'research reports',
            'benchmark',
            'benchmarks',
            'playbook',
            'playbooks',
        ];
        const isPreferredOptionLabel = (label) => preferredOptionLabels.some((candidate) => (
            label === candidate ||
            label.startsWith(candidate + ' ') ||
            label.startsWith(candidate + '(') ||
            label.includes(' ' + candidate + ' ')
        ));
        const applyButtons = Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"]'));
        const clickApplyIfPresent = () => {
            for (const button of applyButtons) {
                const label = normalize(button.textContent || button.value || button.getAttribute('aria-label') || '');
                if (label === 'apply' && isVisible(button)) {
                    button.click();
                    return true;
                }
            }
            return false;
        };
        let toggled = false;
        for (const element of candidates) {
            const labelledBy = element.id ? document.querySelector(`label[for="${element.id}"]`) : null;
            const container = element.closest('label, div, li');
            const label = normalize(
                (labelledBy ? labelledBy.textContent : '') ||
                (container ? container.textContent : '') ||
                element.getAttribute('aria-label') ||
                ''
            );
            if ((label === 'report' || label === 'reports') && isVisible(element)) {
                const checked = element.checked === true || element.getAttribute('aria-checked') === 'true';
                if (!checked) {
                    element.click();
                }
                toggled = true;
                break;
            }
        }
        if (toggled) {
            if (clickApplyIfPresent()) {
                return true;
            }
            return true;
        }
        const selects = Array.from(document.querySelectorAll('select'))
            .filter((element) => isVisible(element) && !element.disabled);
        for (const select of selects) {
            const options = Array.from(select.options || [])
                .map((option) => ({
                    value: option.value,
                    label: normalize(option.textContent || option.label || ''),
                    selected: option.selected === true,
                }))
                .filter((entry) => entry.label);
            if (!options.length) continue;
            const preferred = options.find((entry) => isPreferredOptionLabel(entry.label));
            if (!preferred || preferred.selected) continue;
            select.value = preferred.value;
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            if (clickApplyIfPresent()) {
                return true;
            }
            return true;
        }
        return false;
    }"""
    return script.replace("__HELPER_BUNDLE__", helper_bundle)
