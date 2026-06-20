# Briefing Card System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable small, medium, and large briefing cards with deterministic executive-blue covers, grounded source/evidence counters, and a seven-day `New` badge.

**Architecture:** Briefing cards use their own contract. Python projects their assets and data from validated cross-report packages; WordPress validates and renders the card; the block theme owns responsive presentation.

**Tech Stack:** Python dataclasses, YAML, Pillow, WordPress/PHP 8.2, CSS container queries, pytest, PHP runtime harnesses.

---

## File Map

- `src/contracts/cover_images.py`, `src/services/cover_style_service.py`, `src/config/cover-styles.yaml`, `src/generators/cover_image_generator.py`: report and briefing cover profiles.
- `src/contracts/_cross_report_analysis/requests.py`, `src/generators/cross_report_analysis_generator.py`, `src/orchestrators/publish_orchestrator.py`, `src/contracts/wordpress.py`, `src/generators/publish_generator.py`: briefing-card projection and publication.
- `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-briefing-card-view-model-builder.php`: validated briefing presentation model.
- `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-briefing-card-renderer.php`: three canonical card variants.
- `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-meta.php`, `class-marketlense-core-plugin.php`, `class-marketlense-core-shortcodes.php`, and `marketlense-core.php`: metadata, injection, and placement migration.
- `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`: briefing-only presentation layer.
- `tests/wordpress_runtime/briefing_card_view_model_harness.php`, `tests/wordpress_runtime/briefing_card_renderer_harness.php`, `tests/test_wordpress_briefing_card_migration.py`, `tests/test_cover_style_service.py`, `tests/integration/test_cover_image_service.py`, `tests/test_cross_report_publish_orchestrator.py`, and `tests/test_publish_generator.py`: regression coverage.

### Task 1: Define Executive-Blue Cover Profiles

**Files:** modify `src/contracts/cover_images.py`, `src/services/cover_style_service.py`, and `src/config/cover-styles.yaml`; test `tests/test_cover_style_service.py`.

- [ ] **Step 1: Write the failing profile test**

```python
def test_default_cover_style_exposes_report_and_briefing_profiles() -> None:
    config = load_cover_styles(CoverStyleLoadRequest(schema_version="2.0", path=""), _ctx()).config
    assert config.schema_version == "3.0"
    assert config.profiles["report"].style.background_color == "#061A31"
    assert config.profiles["briefing"].style.background_color == "#0A255A"
    assert config.profiles["briefing"].layouts["small"].title_y == 270
```

- [ ] **Step 2: Confirm the test is red**

Run: `pytest tests/test_cover_style_service.py::test_default_cover_style_exposes_report_and_briefing_profiles -v`

Expected: FAIL because `profiles` does not exist.

- [ ] **Step 3: Implement typed profile configuration**

```python
@dataclass(frozen=True)
class CoverImageProfile:
    schema_version: str = field(metadata={"doc": "Cover-profile schema version."})
    style: CoverImageStyle = field(metadata={"doc": "Resolved palette and fonts."})
    layouts: Dict[str, CoverImageLayout] = field(metadata={"doc": "Three canonical layouts."})
```

Change `CoverImageStyleConfig` to `profiles: Dict[str, CoverImageProfile]`. Parse only report and briefing, reject missing/unknown profiles and absent sizes with non-retryable `cover_style_invalid`, preserve all report values, and configure briefing with `#0A255A`, `#123A78`, `#6F9ED4`, `#D8E8F8`, `#F8FAFC` and vertically centered title rectangles.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/test_cover_style_service.py -v`

Commit: `git add src/contracts/cover_images.py src/services/cover_style_service.py src/config/cover-styles.yaml tests/test_cover_style_service.py; git commit -m "feat: add briefing cover profile"`

### Task 2: Render Profile-Specific Briefing Assets

**Files:** modify `src/contracts/cover_images.py` and `src/generators/cover_image_generator.py`; test `tests/integration/test_cover_image_service.py`.

- [ ] **Step 1: Write a red three-asset briefing test**

```python
report = CoverImageReport(
    schema_version="3.0", file_id="briefing-1", title="Retail Media Decision Window",
    publisher="Market Bearing", report_slug="retail-media-decision-window",
    time_period="20 June 2026", region="Global", cover_profile="briefing",
    fingerprint=_fingerprint(),
)
assert Image.open(assets.small.output_path).size == (1600, 900)
assert Image.open(assets.medium.output_path).size == (1200, 1500)
assert Image.open(assets.large.output_path).size == (1200, 1600)
```

- [ ] **Step 2: Confirm failure**

Run: `pytest tests/integration/test_cover_image_service.py -k briefing_cover -v`

Expected: FAIL because the request has no `cover_profile`.

- [ ] **Step 3: Select a profile in the existing generator**

```python
cover_profile: str = field(default="report", metadata={"doc": "Approved report or briefing cover profile."})
profile = config.profiles[report.cover_profile]
response = cover_image_service.render_cover_image(
    CoverImageRenderRequest(..., style=profile.style, layout=profile.layouts[size], ...), ctx
)
```

Validate only report/briefing, preserve report default behavior, and include `cover_profile` in `cover_asset_rendered` log fields. Do not add a second rendering service.

- [ ] **Step 4: Verify and commit**

Run: `pytest tests/test_cover_style_service.py tests/integration/test_cover_image_service.py -v`

Commit: `git add src/contracts/cover_images.py src/generators/cover_image_generator.py tests/integration/test_cover_image_service.py; git commit -m "feat: render briefing cover assets"`

### Task 3: Project and Publish a Briefing Card Manifest

**Files:** modify `src/contracts/_cross_report_analysis/requests.py`, `src/generators/cross_report_analysis_generator.py`, `src/orchestrators/publish_orchestrator.py`, `src/contracts/wordpress.py`, `src/generators/publish_generator.py`; test `tests/test_cross_report_publish_orchestrator.py` and `tests/test_publish_generator.py`.

- [ ] **Step 1: Write failing publication assertions**

```python
assert package.briefing_card_manifest.source_report_ids == ["report-1", "report-2"]
assert package.briefing_card_manifest.evidence_count == 8
assert post_request.meta["ml_briefing_card_schema_version"] == "1.0"
assert post_request.meta["ml_briefing_source_report_ids"] == [101, 102]
assert post_request.meta["ml_briefing_evidence_count"] == 8
assert post_request.meta["ml_briefing_card_cover_small_id"] > 0
```

- [ ] **Step 2: Confirm failure**

Run: `pytest tests/test_cross_report_publish_orchestrator.py tests/test_publish_generator.py -k briefing_card -v`

Expected: FAIL because publish packages expose no briefing-card manifest.

- [ ] **Step 3: Add one validated manifest to the cross-report package**

```python
BriefingCardManifest(
    schema_version="1.0", title_scale=title_scale, summary_compact=compact_summary,
    summary_standard=generated.executive_summary, decision_focus=generated.decision_focus,
    executive_takeaways=tuple(generated.executive_takeaways[:2]),
    source_report_ids=tuple(selected_report_ids), evidence_count=len(evidence_reference_ids),
    fingerprint=briefing_fingerprint, covers=cover_assets,
)
```

Define this dataclass in the existing cross-report contract namespace. Require unique non-empty sources, exactly two takeaways, complete sentence summaries, full cover assets, and a briefing fingerprint. Derive compact summary through sentence-safe logic, upload all three assets before publishing, and persist only attachment IDs, source WordPress IDs, and evidence count in `ml_briefing` meta.

- [ ] **Step 4: Verify idempotency and commit**

Run: `pytest tests/test_cross_report_publish_orchestrator.py tests/test_publish_generator.py -k "briefing or cross_report" -v`

Expected: PASS; identical packages produce neither duplicate media nor duplicate posts, and invalid source IDs/covers/takeaways fail before WordPress I/O.

Commit: `git add src/contracts/_cross_report_analysis/requests.py src/generators/cross_report_analysis_generator.py src/orchestrators/publish_orchestrator.py src/contracts/wordpress.py src/generators/publish_generator.py tests/test_cross_report_publish_orchestrator.py tests/test_publish_generator.py; git commit -m "feat: publish briefing card manifests"`

### Task 4: Add WordPress Contract, View Model, and Renderer

**Files:** create `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-briefing-card-view-model-builder.php` and `class-marketlense-core-briefing-card-renderer.php`; modify `class-marketlense-core-meta.php`, `marketlense-core.php`, and `class-marketlense-core-plugin.php`; create PHP harnesses and `tests/test_wordpress_briefing_card_migration.py`.

- [ ] **Step 1: Write the PHP harness test first**

```python
payload = run_harness("briefing_card_renderer_harness.php", {"briefing": complete_briefing_contract(), "variant": "large"})
assert payload["error"] == ""
assert "ml-briefing-card--large" in payload["html"]
assert "2 source reports" in payload["html"]
assert "8 evidence items" in payload["html"]
assert "New" in payload["html"]
```

Cover all three variants, unsupported variant, absent cover, invalid takeaways, pluralization, and publication ages of zero, six days 23:59:59, exactly seven days, and future.

- [ ] **Step 2: Confirm failure**

Run: `pytest tests/test_wordpress_briefing_card_migration.py -v`

Expected: FAIL because the new classes and harnesses do not exist.

- [ ] **Step 3: Register and build the contract**

Register REST-visible `ml_briefing` metadata for schema version, title scale, compact/standard summaries, decision focus, two takeaways, source report IDs, evidence count, fingerprint, and three cover media IDs. Implement `Briefing_Card_View_Model_Builder::build(\WP_Post $post): array`; validate all fields and source posts, resolve cover URLs, and calculate:

```php
$age = current_time('timestamp', true) - $timestamp;
$is_new = $age >= 0 && $age < 7 * DAY_IN_SECONDS;
```

- [ ] **Step 4: Render only canonical variants**

```php
private const VARIANTS = ['small', 'medium', 'large'];

public function render(array $briefing, string $variant): string
{
    if (! in_array($variant, self::VARIANTS, true)) {
        throw new \InvalidArgumentException('Unsupported briefing card variant: ' . $variant);
    }
    if (($briefing['card_contract_valid'] ?? false) !== true) {
        throw new \UnexpectedValueException('A valid briefing card contract is required');
    }
}
```

Small renders compact summary/counters; medium adds decision focus; large adds decision focus and exactly two takeaways. Use escaped labels, decorative inline SVGs, and empty cover alt text because the title is adjacent semantic HTML.

- [ ] **Step 5: Verify and commit**

Run: `pytest tests/test_wordpress_briefing_card_migration.py tests/test_wordpress_report_card_migration.py -v`

Commit: `git add Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-briefing-card-view-model-builder.php Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-briefing-card-renderer.php Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-meta.php Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-plugin.php tests/wordpress_runtime/briefing_card_view_model_harness.php tests/wordpress_runtime/briefing_card_renderer_harness.php tests/test_wordpress_briefing_card_migration.py; git commit -m "feat: add canonical briefing card renderer"`

### Task 5: Migrate Briefing Placements and Theme CSS

**Files:** modify `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`, `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`, and `Wordpress/wp-content/themes/marketlense/patterns/featured-briefing.php`; test `tests/test_wordpress_briefing_card_migration.py`.

- [ ] **Step 1: Add red static migration checks**

```python
assert "$this->briefing_card_renderer->render($briefing, 'large')" in featured_briefing
assert "$this->briefing_card_renderer->render($briefing, 'small')" in briefings_index
assert "ml-featured-briefing-card" not in featured_briefing
assert ".ml-briefing-card--small" in briefing_css
assert "@container" in briefing_css
assert "line-clamp" not in briefing_css
```

- [ ] **Step 2: Confirm failure**

Run: `pytest tests/test_wordpress_briefing_card_migration.py -v`

Expected: FAIL because generic briefing-card calls remain.

- [ ] **Step 3: Migrate all briefing placements**

Inject briefing classes into `Shortcodes`. Render newest valid briefing as `large`; query only `ml_briefing_card_schema_version = 1.0` in the archive and render `small`. Register `[ml_latest_briefings]` as the only curated placement entrypoint and accept only the three canonical variants. Remove only briefing-specific generic card calls.

- [ ] **Step 4: Add a scoped CSS block**

Create `/* BEGIN canonical briefing cards */` after report-card CSS. Use `.ml-briefing-card--small`, `.ml-briefing-card--medium`, and `.ml-briefing-card--large` with report-equivalent grid tracks, `container-type: inline-size`, responsive document-order stack, focus state, and reduced-motion override. Use `#0A255A` as cover fallback and `#174991` for actions/counter icons. Do not modify report selectors, use gradients, or clamp semantic text.

- [ ] **Step 5: Verify and commit**

Run: `pytest tests/test_wordpress_briefing_card_migration.py tests/test_wordpress_market_bearing_portal.py tests/test_wordpress_entity_destinations.py -v`

Commit: `git add Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php Wordpress/wp-content/themes/marketlense/assets/css/theme.css Wordpress/wp-content/themes/marketlense/patterns/featured-briefing.php tests/test_wordpress_briefing_card_migration.py; git commit -m "feat: render briefing cards across portal"`

### Task 6: Document and Verify

**Files:** modify `README.md`, `README_WORDPRESS.md`, `Wordpress/wp-content/plugins/marketlense-core/readme.txt`, and `scripts/ci/run_mutation_gate.py`.

- [ ] **Step 1: Document card contract and mutation scope**

Document card variants, source/evidence derivation, executive-blue covers, less-than-seven-day `New`, `[ml_latest_briefings]`, and the generate/publish/audit sequence. Add briefing projection and renderer decision modules to the mutation gate.

- [ ] **Step 2: Run automated verification**

Run: `pytest tests/test_cover_style_service.py tests/integration/test_cover_image_service.py tests/test_cross_report_publish_orchestrator.py tests/test_publish_generator.py tests/test_wordpress_briefing_card_migration.py tests/test_wordpress_report_card_migration.py -v`

Run: `python scripts/ci/check_wordpress_subproject.py`

Run: `python scripts/ci/run_mutation_gate.py`

Expected: all commands exit `0` and changed briefing decision logic has no untriaged mutation.

- [ ] **Step 3: Verify visually and build releases**

Inspect homepage featured briefing, `/briefings/`, and a medium-card placement at 1440px, 1024px, 768px, and 390px. Confirm centered cover titles, counters, `New` boundaries, keyboard focus, reduced motion, complete text, and no horizontal overflow. Capture desktop/mobile images in `out/`, then run `powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\build-plugin-zip.ps1` and `bash Wordpress/scripts/build-theme-zip.sh`.

## Plan Self-Review

- Tasks 1-2 establish and render the distinct cover profile; Task 3 publishes grounded data; Task 4 validates/renders WordPress contracts; Task 5 migrates every briefing placement; Task 6 covers docs, CI, and browser checks.
- All referenced types and modules are defined in an earlier task. All renderer variants are `small`, `medium`, or `large`.
