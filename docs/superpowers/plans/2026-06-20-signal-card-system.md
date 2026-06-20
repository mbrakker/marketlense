# Signal Card System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable small, medium, and large WordPress signal cards backed by validated signal content and deterministic three-size cover assets.

**Architecture:** Signal generation emits versioned, complete card content. The signal-post orchestrator renders signal-profile cover assets and hands the completed card payload to the existing publish boundary. WordPress validates the payload in a dedicated view-model builder, renders it through a dedicated renderer, and exposes the three canonical variants through one shortcode.

**Tech Stack:** Python dataclasses and Pillow cover pipeline; WordPress PHP 8.2; CSS Grid and container queries; pytest; Playwright CLI.

---

### Task 1: Signal Card Contract

**Files:**
- Create: `src/contracts/signal_cards.py`
- Modify: `src/contracts/wordpress_entities.py`
- Modify: `src/generators/signal_post_generator.py`
- Test: `tests/test_signal_post_generator.py`

- [x] **Step 1: Write failing card-content assertions**

```python
assert projection.card_content.summary
assert projection.card_content.source_count == 2
assert projection.card_content.evidence_count == 2
assert projection.card_content.fingerprint.geometry_family
```

- [x] **Step 2: Run the focused generator test**

Run: `pytest tests/test_signal_post_generator.py -q`
Expected: failure because `SignalPublishProjection` has no `card_content`.

- [x] **Step 3: Add typed signal card content and deterministic fingerprint selection**

```python
SignalCardContent(
    schema_version="1.0",
    summary=summary,
    confidence=confidence,
    source_count=len(source_report_ids),
    evidence_count=len(evidence_ids),
    uncertainty=uncertainty,
    fingerprint=fingerprint,
)
```

- [x] **Step 4: Re-run the focused generator test**

Run: `pytest tests/test_signal_post_generator.py -q`
Expected: pass.

### Task 2: Signal Cover And Publish Payload

**Files:**
- Modify: `src/config/cover-styles.yaml`
- Modify: `src/contracts/publish.py`
- Modify: `src/contracts/_cross_report_analysis/publication.py`
- Modify: `src/utils/html_utils.py`
- Modify: `src/generators/publish_generator.py`
- Modify: `src/orchestrators/signal_post_orchestrator.py`
- Modify: `src/orchestrators/publish_orchestrator.py`
- Test: `tests/test_publish_signal_cards.py`
- Test: `tests/integration/test_cover_image_service.py`

- [x] **Step 1: Write failing publish tests for the three signal covers and metadata**

```python
assert update_call.json_data["meta"]["ml_signal_card_schema_version"] == "1.0"
assert update_call.json_data["meta"]["ml_signal_card_cover_large_id"] == 303
assert update_call.json_data["meta"]["ml_signal_source_count"] == 2
```

- [x] **Step 2: Run the focused publish test**

Run: `pytest tests/test_publish_signal_cards.py -q`
Expected: failure because signal-card metadata is not parsed or published.

- [x] **Step 3: Add the `signal` profile and complete publication flow**

```python
signal_card = {
    "schema_version": "1.0",
    "summary": content.summary,
    "confidence": content.confidence,
    "source_count": content.source_count,
    "evidence_count": content.evidence_count,
    "uncertainty": content.uncertainty,
    "covers": cover_paths,
}
```

- [x] **Step 4: Re-run focused card publication and cover tests**

Run: `pytest tests/test_publish_signal_cards.py tests/integration/test_cover_image_service.py -q`
Expected: pass.

### Task 3: WordPress Renderer And Reuse Boundary

**Files:**
- Create: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-signal-card-view-model-builder.php`
- Create: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-signal-card-renderer.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-meta.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-plugin.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`
- Modify: `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`
- Create: `tests/wordpress_runtime/signal_card_renderer_harness.php`
- Create: `tests/test_wordpress_signal_card_renderer.py`
- Modify: `tests/test_wordpress_signal_contracts.py`

- [x] **Step 1: Write failing renderer tests for canonical variants and content tracks**

```python
assert "ml-signal-card--small" in html
assert "Signal condition" not in small_html
assert "Signal condition" in large_html
```

- [x] **Step 2: Run the focused renderer test**

Run: `pytest tests/test_wordpress_signal_card_renderer.py -q`
Expected: failure because the signal renderer does not exist.

- [x] **Step 3: Implement the view model, renderer, metadata, and `ml_signal_cards` shortcode**

```php
[ml_signal_cards variant="small" per_page="12"]
```

- [x] **Step 4: Add component-scoped responsive CSS and run focused tests**

Run: `pytest tests/test_wordpress_signal_card_renderer.py tests/test_wordpress_signal_contracts.py -q`
Expected: pass.

### Task 4: Documentation And Browser Regression Check

**Files:**
- Modify: `Wordpress/wp-content/plugins/marketlense-core/readme.txt`
- Test: existing focused Python and WordPress tests

- [x] **Step 1: Document the card contract and canonical shortcode**

```text
[ml_signal_cards variant="small|medium|large" per_page="1..48"]
```

- [x] **Step 2: Run formatting, focused tests, and WordPress checks**

Run: `pytest tests/test_signal_post_generator.py tests/test_publish_signal_cards.py tests/test_wordpress_signal_card_renderer.py tests/test_wordpress_signal_contracts.py -q`
Expected: pass.

- [x] **Step 3: Seed local development records only, verify 1440px and 390px, then remove temporary browser artifacts**

Run: `playwright-cli open http://localhost/digitalinsights/signals/ --headed`
Expected: no horizontal overflow, visible small cards, and no console errors.
