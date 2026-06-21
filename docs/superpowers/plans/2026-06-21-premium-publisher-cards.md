# Premium Publisher Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render premium, filter-aware publisher cards using only real public report coverage, synchronized report-value aggregates, publisher logos, and matching report categories.

**Architecture:** Keep report filtering in `Archive_Browser`, publisher-card rendering in a dedicated `Publisher_Directory` plugin owner, and WordPress term metadata registration in `Taxonomies`. Python remains responsible for reading report-score data through the report-store service and synchronizing only aggregates whose `file_id`s are present on published WordPress reports. The block theme only supplies layout and presentation.

**Tech Stack:** Python 3.12, SQLite, WordPress PHP, REST API, block theme CSS, pytest, PHP linting.

---

### Task 1: Approve a visual v0 before production code

**Files:**
- Create: `.superpowers/brainstorm/<session>/content/publisher-card-v0.html`
- Test: visual review in the approved visual-companion browser session

- [ ] **Step 1: Create a v0 with real card information hierarchy**

Show one small card and one medium card using the approved navy/blue/cool-canvas system. The small card must show the real-logo frame, value band, numeric aggregate, assessed sample count, existing report/briefing/signal counts, and three category citations. The filter rail must show search, category, period, and region only.

- [ ] **Step 2: Verify the v0 against the approved design**

Confirm visual hierarchy, no invented metrics, no publisher select, and a clear small-card default with the user in the browser.

- [ ] **Step 3: Record the v0 approval before changing production code**

Proceed only after the user confirms the visual treatment. Do not add a parallel stylesheet or component framework.

### Task 2: Add a typed public-report score aggregate service

**Files:**
- Modify: `src/contracts/_report_store/sources.py`
- Modify: `src/contracts/report_store.py`
- Modify: `src/services/_report_store_service/sources.py`
- Modify: `src/services/report_store_service.py`
- Test: `tests/test_report_store_service.py`

- [ ] **Step 1: Write failing contract and service tests**

Add a test that creates three `reports` rows and matching `report_sources` rows: two rows have a report-value score and their `file_id`s are supplied as published; one is scored but omitted from the published list. Assert the response has a sample size of `2`, the arithmetic average of only the two public scores, and no result for an empty public-file list.

```python
response = list_public_publisher_report_value_aggregates(
    PublicPublisherReportValueAggregateRequest(
        schema_version="1.0",
        db_path=str(db_path),
        published_file_ids=["public-a", "public-b"],
    ),
    ctx,
)
aggregate = next(item for item in response.aggregates if item.publisher_name == "Publisher A")
assert aggregate.sample_size == 2
assert aggregate.average_score == pytest.approx(70.0)
assert len(response.aggregates) == 1
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/test_report_store_service.py -k public_publisher_report_value -q`

Expected: FAIL because the aggregate contract/service does not exist.

- [ ] **Step 3: Add the aggregate contracts and query**

Define fully documented dataclasses for the request, aggregate item, and response. The service query must join `reports.source_md5` to `report_sources.md5`, restrict to the supplied published `reports.file_id` values, discard null scores, and return each file's publisher-normalized aggregate data. Derive the band using the existing report-value thresholds (`high >= 78`, `medium >= 60`, `low >= 40`, otherwise `weak`) in one public report-value helper; do not duplicate thresholds in the sync script.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python -m pytest tests/test_report_store_service.py -k public_publisher_report_value -q`

Expected: PASS.

- [ ] **Step 5: Add negative-path coverage**

Assert an invalid/absent database path raises the existing typed `AppError` service failure and a source row without a matching public `file_id` cannot contribute to an aggregate.

### Task 3: Synchronize public aggregates into registered publisher term metadata

**Files:**
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-taxonomies.php`
- Modify: `Wordpress/scripts/admin/sync_profiles.py`
- Modify: `Wordpress/scripts/publisher_profiles_common.py`
- Modify: `tests/test_publisher_profiles_common.py`
- Create: `tests/test_publisher_report_value_sync.py`

- [ ] **Step 1: Write failing metadata and sync tests**

Assert the profile payload includes the three new term meta keys only when a public aggregate is present:

```python
assert payload["meta"]["ml_publisher_report_value_score"] == 70.0
assert payload["meta"]["ml_publisher_report_value_band"] == "medium"
assert payload["meta"]["ml_publisher_report_value_sample_size"] == 2
```

Also assert the REST readiness check requires the three keys and that an unmatched publisher omits all three values rather than writing sentinel data.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_publisher_profiles_common.py tests/test_publisher_report_value_sync.py -q`

Expected: FAIL because term metadata and public-score synchronization do not exist.

- [ ] **Step 3: Register and populate the term metadata**

Register `ml_publisher_report_value_score` as a REST-visible numeric term meta field, `ml_publisher_report_value_band` as a sanitized string constrained to the four canonical bands, and `ml_publisher_report_value_sample_size` as a non-negative integer in `Taxonomies`.

In `sync_profiles`, first fetch each publisher term and its published report `ml_file_id` values through the existing REST client. Load `paths.reports_db` with the existing config service, request the typed aggregate service once for the collected public file IDs, and merge the matching aggregate into that term's existing profile payload. Preserve all existing profile fields and omit quality keys when the aggregate is unavailable. This keeps the script as the orchestrator of the existing SQLite and WordPress service boundaries; it must not execute ad-hoc SQL.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `python -m pytest tests/test_publisher_profiles_common.py tests/test_publisher_report_value_sync.py -q`

Expected: PASS.

- [ ] **Step 5: Add idempotency coverage**

Run the identical sync payload twice against the REST-client test double and assert both writes carry the same aggregate fields and do not create a duplicate term.

### Task 4: Extract the filter-aware publisher directory owner

**Files:**
- Create: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-publisher-directory.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-archive-browser.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php`
- Test: `tests/test_wordpress_publisher_directory.py`
- Test: `tests/test_wordpress_archive_browser_parity.py`

- [ ] **Step 1: Write failing ownership and behavior tests**

Create structural tests proving that `Shortcodes::render_publishers_directory()` delegates to `Publisher_Directory`, while `Archive_Browser` supplies the shared selected filters, matching report IDs, facet options, active chips, and filter asset enqueueing. Assert the publisher-directory rail renders `s`, `category`, `ml_period`, and `ml_region`, but never renders `name="ml_publisher"`.

```python
assert 'name="ml_publisher"' not in publisher_directory_source
assert 'data-ml-live-filter-form' in publisher_directory_source
assert 'matching_report_ids' in archive_browser_source
assert 'new Publisher_Directory(' in shortcodes_source
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/test_wordpress_publisher_directory.py tests/test_wordpress_archive_browser_parity.py -q`

Expected: FAIL because the owner and publisher-filter mode do not exist.

- [ ] **Step 3: Implement shared report filtering without a publisher facet**

Add a focused public `Archive_Browser` API that returns canonical report IDs and report facets for the current `search/topic/period/region` state while preserving the existing report-archive behavior. It must use `Meta::apply_report_card_query_constraints()`, preserve GET/live-submission semantics, and keep the publisher selector exclusive to the report archive.

`Publisher_Directory` uses those matched IDs to group reports by `ml_publisher` term. It renders only terms with one or more matched reports, obtains category counts from those same post IDs, and uses the registered quality metadata. It must render no quality badge when the score, band, or sample size is incomplete.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python -m pytest tests/test_wordpress_publisher_directory.py tests/test_wordpress_archive_browser_parity.py -q`

Expected: PASS.

- [ ] **Step 5: Add a PHP runtime harness for observable output**

Create a minimal WordPress-function harness that renders one publisher with a logo, matched reports, a medium aggregate, and four categories. Assert rendered HTML contains the real image markup, score/band/sample text, three category citations plus the overflow count, and no publisher select. Add an unmatched-score case that asserts the quality panel is absent.

### Task 5: Apply the three-size premium card presentation

**Files:**
- Modify: `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`
- Modify: `Wordpress/wp-content/themes/marketlense/templates/page-publishers-directory.html`
- Modify: `tests/test_wordpress_entity_card_size_parity.py`
- Modify: `tests/test_wordpress_market_bearing_portal.py`

- [ ] **Step 1: Write failing CSS/template tests**

Assert the publisher page retains one `ml_publishers_directory` shortcode, declares small as the default card class, and the CSS defines `.ml-publisher-directory-card--small`, `--medium`, and `--large` with the same desktop media proportions used by report cards (`36%` medium and `40%` large), a narrow-screen stacked fallback, container-query-safe card layout, visible focus styles, and reduced-motion behavior.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/test_wordpress_entity_card_size_parity.py tests/test_wordpress_market_bearing_portal.py -q`

Expected: FAIL because publisher cards have only the legacy one-size presentation.

- [ ] **Step 3: Implement the approved visual treatment**

Use existing CSS custom properties only. Small cards remain the directory grid default. Medium/large cards place the contained logo/identity panel next to the evidence content on desktop and collapse to a 16:10 stacked media treatment below `782px`. Keep the current documented hover/focus and `prefers-reduced-motion` behavior. Add layout rules for the assessment, sample count, category citations, overflow chip, empty filtered state, and filter rail without changing report-card CSS behavior.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `python -m pytest tests/test_wordpress_entity_card_size_parity.py tests/test_wordpress_market_bearing_portal.py -q`

Expected: PASS.

### Task 6: Document, package, and verify against a real WordPress surface

**Files:**
- Modify: `README_WORDPRESS.md`
- Modify: `wordpress_implementation_map.md`
- Test: `tests/test_wordpress_theme_packaging.py`

- [ ] **Step 1: Document the contract**

Describe the new synchronized publisher term meta, public-report-only score eligibility, category citations, and directory filter behavior. State explicitly that the publisher facet remains on `/reports/` but is intentionally absent from `/publishers-directory/`.

- [ ] **Step 2: Run all targeted tests**

Run: `python -m pytest tests/test_report_store_service.py tests/test_publisher_profiles_common.py tests/test_publisher_report_value_sync.py tests/test_wordpress_publisher_directory.py tests/test_wordpress_archive_browser_parity.py tests/test_wordpress_entity_card_size_parity.py tests/test_wordpress_market_bearing_portal.py tests/test_wordpress_theme_packaging.py -q`

Expected: PASS.

- [ ] **Step 3: Run WordPress structural verification and build packages**

Run: `python scripts/ci/check_wordpress_subproject.py`

Expected: `WordPress subproject checks passed.`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File Wordpress/scripts/build-plugin-zip.ps1`

Expected: `Built plugin archive: ...marketlense-core.zip`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File Wordpress/scripts/build-theme-zip.ps1`

Expected: `Built theme archive: ...marketlense.zip`

- [ ] **Step 4: Perform a live verification**

Deploy the generated plugin and theme to the configured WordPress target, run `python Wordpress/scripts/sync-publisher-profiles-rest.py`, then verify `/publishers-directory/` at desktop, tablet, and mobile widths. Confirm logos load, quality aggregates only appear for matched public scores, filter changes update matching publisher cards, the publisher selector is absent, categories are tied to matching reports, and browser console output is clean.

- [ ] **Step 5: Migrate already published publisher cards**

Deploy the plugin before migration so the new REST term-meta fields are registered. Run `python Wordpress/scripts/sync-publisher-profiles-rest.py` against the existing WordPress site. The command must inspect every current publisher term and update it in place from the configured report database; it must not create replacement terms, change term slugs, remove existing profile/logo metadata, or manufacture a score for publishers without matched public scored reports.

Record the number of current terms inspected, the number updated with a quality aggregate, and the number intentionally left without one. Verify one existing scored publisher card shows the new assessment/category treatment and one existing unscored publisher card has no score panel.

- [ ] **Step 6: Commit the verified implementation**

```bash
git add src Wordpress tests README_WORDPRESS.md wordpress_implementation_map.md
git commit -m "feat: enrich publisher cards with report evidence"
```
