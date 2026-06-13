# Report Card And Semantic Cover System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver three canonical WordPress report cards backed by complete density-specific TLDRs and deterministic semantic cover assets, migrate every report placement, verify the portal, and regenerate the installable theme and plugin ZIPs.

**Architecture:** The existing Python report pipeline remains the owner of grounded card intelligence and cover generation. It publishes validated card metadata and three cover media IDs through the existing WordPress service boundary. The WordPress plugin validates and renders one of three canonical variants, while the block theme owns layout and responsive styling.

**Tech Stack:** Python 3.12+, dataclasses, JSON Schema, Pillow, pytest, WordPress 6.9+, PHP 8.2, WordPress REST API, block-theme templates/patterns, CSS Grid/subgrid, Playwright, PowerShell/Bash packaging.

---

## File Structure

### Python pipeline

- Create `src/contracts/report_cards.py`: versioned card TLDR, insight, geography, cover fingerprint, asset-set, and manifest contracts.
- Modify `src/contracts/cover_images.py`: replace the single-output cover contract with aspect-specific render requests and asset-set outcomes.
- Modify `src/contracts/wordpress.py`: allow validated REST post meta in the canonical post-create request.
- Modify `src/schemas/artifacts.schema.json`: require compact TLDR and cover semantics.
- Create `src/prompts/report_vs/artifacts/cover_semantics/system.yaml`: grounded cover-semantics system prompt.
- Create `src/prompts/report_vs/artifacts/cover_semantics/user.yaml`: constrained fingerprint output prompt.
- Modify `src/prompts/report_vs/artifacts/summary/user.yaml`: request both TLDR projections.
- Modify `src/prompts/_dry_run_fixtures.yaml`: add valid fixture outputs for the changed/new prompts.
- Modify `src/config/app.yaml`: route the new prompt namespace to the existing approved analysis model.
- Modify `src/config/cover-styles.yaml`: define the restrained palette, exact aspect dimensions, title zones, and geometry settings.
- Modify `src/generators/_artifact_generator/generation.py`: generate cover semantics with summary and insight artifacts.
- Modify `src/generators/_artifact_generator/storage.py`: assemble, adapt, validate, hash, and cache the new artifact fields.
- Create `src/generators/report_card_projection.py`: pure domain projection from report artifacts to a complete card manifest.
- Modify `src/generators/cover_image_generator.py`: map the approved fingerprint to one of 16 geometry families and request three renders.
- Modify `src/services/cover_style_service.py`: parse the versioned multi-layout cover configuration.
- Modify `src/services/cover_image_service.py`: render deterministic abstract geometry and fail closed on title overflow.
- Modify `src/generators/report_render_generator.py`: build and persist the card manifest after successful cover generation.
- Modify `src/generators/publish_generator.py`: read the manifest, upload all cover assets, and attach card meta.
- Modify `src/services/_wordpress_service/posts.py`: send the validated `meta` object in the existing REST request.
- Modify `src/orchestrators/ingest_orchestrator.py`: support explicit report-card backfill without changing normal skip behavior.
- Modify `src/_cli/pipeline.py`: expose report-card backfill through the existing `ingest` command.

### WordPress plugin

- Modify `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-meta.php`: register and validate card meta fields.
- Modify `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php`: expose the normalized canonical card view model.
- Create `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-card-renderer.php`: own small, medium, and large markup only.
- Modify `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`: delegate all report-card output to the renderer.
- Modify `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-plugin.php`: construct and inject the renderer.
- Modify `Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php`: load the renderer and bump the plugin version.
- Create `Wordpress/scripts/audit-report-card-contracts.php`: fail when any published report lacks a valid card contract.

### WordPress theme

- Modify `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`: define the canonical card system and remove obsolete report-card rules.
- Modify `Wordpress/wp-content/themes/marketlense/patterns/report-grid.php`: request small cards explicitly.
- Modify report-related theme templates/patterns discovered by the static migration test so each report placement requests only `small`, `medium`, or `large`.
- Modify `Wordpress/wp-content/themes/marketlense/style.css`: bump the theme version.

### Tests and docs

- Create `tests/test_report_card_contracts.py`.
- Create `tests/test_report_card_projection.py`.
- Create `tests/test_cover_geometry_selection.py`.
- Extend `tests/test_cover_image_generator.py`.
- Extend `tests/test_cover_style_service.py`.
- Create `tests/integration/test_cover_image_service.py`.
- Extend `tests/test_publish_generator.py` for the new manifest and WordPress meta contract.
- Modify `tests/wordpress_runtime/report_view_model_harness.php`.
- Create `tests/wordpress_runtime/report_card_renderer_harness.php`.
- Create `tests/test_wordpress_report_card_contract.py`.
- Create `tests/test_wordpress_report_card_migration.py`.
- Extend `tests/test_wordpress_market_bearing_portal.py`.
- Modify `scripts/ci/run_mutation_gate.py`: add the critical report-card projection target.
- Update `docs/quality/contract_schemas.json`.
- Update affected golden `artifacts.json` fixtures through the existing fixture-generation path, never by inserting sentinel values.
- Modify `README.md` and `README_WORDPRESS.md`.

---

### Task 1: Define The Versioned Card Contracts

**Files:**
- Create: `src/contracts/report_cards.py`
- Modify: `src/contracts/cover_images.py`
- Test: `tests/test_report_card_contracts.py`
- Modify: `docs/quality/contract_schemas.json`

- [ ] **Step 1: Write failing contract round-trip and completeness tests**

```python
from dataclasses import asdict

from src.contracts.report_cards import (
    CardCoverAsset,
    CardCoverAssetSet,
    CoverFingerprintProjectionRequest,
    CoverFingerprint,
    ReportCardManifestWriteRequest,
    ReportCardManifestWriteResponse,
    ReportCardManifestRequest,
    ReportCardManifest,
)


def _manifest() -> ReportCardManifest:
    fingerprint = CoverFingerprint(
        schema_version="1.0",
        geometry_family="ascending_trajectory",
        evidence_shape="trend",
        direction="rising",
        geography_scope="global",
        evidence_density="metric_rich",
        domain_layer="grid",
        seed=184221,
        selection_reason="Trend evidence with a rising direction dominates the report.",
    )
    covers = CardCoverAssetSet(
        schema_version="1.0",
        small=CardCoverAsset("1.0", "small", "assets/report-card-small.png", 1600, 900),
        medium=CardCoverAsset("1.0", "medium", "assets/report-card-medium.png", 1200, 1500),
        large=CardCoverAsset("1.0", "large", "assets/report-card-large.png", 1200, 1600),
    )
    return ReportCardManifest(
        schema_version="1.0",
        title="Global Economic Conditions Quarterly Update",
        title_scale="long",
        publisher="McKinsey & Company",
        published_date="2026-06-13",
        geography_label="Global",
        geography_scope="global",
        covered_period="Q2 2026",
        tldr_compact="Growth remains uneven as rates and trade pressure reshape investment decisions.",
        tldr_standard="Growth remains uneven across markets as persistent rates, trade pressure, and weaker demand reshape investment decisions through the second quarter of 2026.",
        key_insights=(
            "Investment remains concentrated in resilient service sectors.",
            "Trade pressure is widening the gap between regional outlooks.",
        ),
        fingerprint=fingerprint,
        covers=covers,
    )


def test_report_card_manifest_round_trip(assert_no_defaulted_required_fields) -> None:
    manifest = _manifest()
    rebuilt = ReportCardManifest.from_dict(asdict(manifest))
    assert rebuilt == manifest
    assert_no_defaulted_required_fields(rebuilt)


def test_report_card_manifest_rejects_incomplete_cover_set(assert_app_error) -> None:
    payload = asdict(_manifest())
    payload["covers"]["large"] = None
    try:
        ReportCardManifest.from_dict(payload)
    except Exception as error:
        assert_app_error(error, code="cover_asset_set_incomplete", retryable=False)
    else:
        raise AssertionError("Incomplete cover sets must fail")
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run: `python -m pytest tests/test_report_card_contracts.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'src.contracts.report_cards'`.

- [ ] **Step 3: Implement the contracts and validation constructors**

Create frozen dataclasses with documented fields and `from_dict()` constructors. `CoverFingerprintProjectionRequest` carries file ID, artifact hash, region, and cover semantics before image generation. `ReportCardManifestRequest` carries normalized report text, the completed fingerprint, insights, and completed cover assets after image generation. `ReportCardManifestWriteRequest` carries the report output directory and a validated manifest; `ReportCardManifestWriteResponse` carries schema version, canonical manifest path, and bytes written. Use these exact allowed values:

```python
CARD_SIZES = ("small", "medium", "large")
GEOGRAPHY_SCOPES = ("global", "regional", "country", "unknown")
EVIDENCE_SHAPES = (
    "trend", "comparison", "distribution", "flow", "network",
    "concentration", "hierarchy", "cycle", "uncertainty", "system",
)
DIRECTIONS = (
    "rising", "falling", "stable", "volatile", "converging",
    "diverging", "cyclical", "neutral",
)
EVIDENCE_DENSITIES = ("metric_rich", "balanced", "qualitative")
GEOMETRY_FAMILIES = (
    "ascending_trajectory", "descending_trajectory", "volatility_corridor",
    "convergence_funnel", "divergence_fan", "parallel_bands",
    "ranked_strata", "distribution_field", "concentration_core",
    "flow_channels", "network_constellation", "hierarchy_terraces",
    "cycle_orbit", "forecast_horizon", "uncertainty_envelope", "system_matrix",
)
```

`ReportCardManifest.from_dict()` must validate:

- compact TLDR: `1..18` words, complete final punctuation, no terminal ellipsis;
- standard TLDR: `1..45` words, complete final punctuation, no terminal ellipsis;
- exactly two nonempty key insights;
- title scale in `short|medium|long|xlong`;
- all three cover assets present with the exact dimensions from the design;
- fingerprint values belong to the allowed sets.

Raise the approved non-retryable `AppError` codes from the design spec.

- [ ] **Step 4: Update `src/contracts/cover_images.py` to carry `CoverFingerprint` and return `CardCoverAssetSet`**

`CoverImageReport` gains a required `fingerprint: CoverFingerprint`. `CoverImageGenerationOutcome` replaces `output_path` with `assets: CardCoverAssetSet | None` while retaining status and typed error text.

Set changed cover request/response contracts to schema version `2.0`. Legacy version `1.0` requests fail with a typed `cover_contract_migration_required` error; the Task 10 backfill is the explicit migration path because a legacy single image cannot be losslessly adapted into three semantic assets.

- [ ] **Step 5: Run contract tests and update the schema snapshot**

Run:

```powershell
python -m pytest tests/test_report_card_contracts.py -v
python scripts/ci/check_contract_schemas.py --update
python scripts/ci/check_contract_schemas.py
```

Expected: all commands PASS; the snapshot command prints `Contract schema snapshot gate passed.`

- [ ] **Step 6: Commit**

```powershell
git add src/contracts/report_cards.py src/contracts/cover_images.py tests/test_report_card_contracts.py docs/quality/contract_schemas.json
git commit -m "feat: define report card presentation contracts"
```

### Task 2: Generate And Validate Density-Specific TLDRs

**Files:**
- Modify: `src/prompts/report_vs/artifacts/summary/user.yaml`
- Modify: `src/prompts/_dry_run_fixtures.yaml`
- Modify: `src/schemas/artifacts.schema.json`
- Modify: `src/generators/_artifact_generator/storage.py`
- Test: `tests/_test_artifact_generator/cases_01_validates_schema_and_evidence_ids.py`
- Test: `tests/test_prompt_dry_run_validation.py`

- [ ] **Step 1: Add failing artifact tests for both TLDR projections**

Add a positive fixture with:

```python
summary = {
    "tldr": "Retail growth depends on trust, invisible AI, and experience-led discovery through 2026.",
    "card_tldr_compact": "Trust, invisible AI, and experience-led discovery will define retail growth through 2026.",
    "executive_summary": "Grounded executive summary.",
    "claim_evidence_map": [],
}
```

Add separate negative tests asserting:

```python
assert_app_error(error, code="card_tldr_compact_invalid", retryable=False)
assert_app_error(error, code="card_tldr_standard_invalid", retryable=False)
```

Use a 19-word compact TLDR and a 46-word standard TLDR as the failing inputs. Also reject a terminal three-period suffix and the Unicode ellipsis character.

- [ ] **Step 2: Run the focused tests and verify schema/semantic failures**

Run: `python -m pytest tests/_test_artifact_generator/cases_01_validates_schema_and_evidence_ids.py tests/test_prompt_dry_run_validation.py -v`

Expected: FAIL because `card_tldr_compact` is not required or validated.

- [ ] **Step 3: Change the summary prompt output contract**

The prompt JSON example must be:

```yaml
"summary": {
  "tldr": "<one complete sentence, maximum 45 words>",
  "card_tldr_compact": "<one complete sentence, maximum 18 words>",
  "executive_summary": "<5-7 sentence executive summary grounded in evidence, include key conclusions and insights>",
  "claim_evidence_map": [
    {"claim": "<concise claim>", "evidence_id": "<single existing evidence id from findings/quotes/doc map>", "evidence": "<supporting excerpt or paraphrase>", "pages": [1]}
  ]
}
```

Add explicit instructions that the compact sentence is independently authored and must not be a clipped prefix.

- [ ] **Step 4: Update schema and semantic validation**

Require `card_tldr_compact` in `summary.required`. Add a pure word-count helper in `storage.py` and raise:

```python
raise AppError(
    code="card_tldr_compact_invalid",
    message="summary.card_tldr_compact must be a complete sentence of 1 to 18 words",
    retryable=False,
)
```

Use the corresponding standard error for `summary.tldr` outside `1..45` words.

Bump the artifacts payload to schema version `2.0`. Cached version `1.0` payloads are adapted only when a valid compact TLDR can be recovered from an already complete 18-word-or-shorter TLDR; otherwise cache adaptation fails with `card_tldr_compact_invalid` and forces regeneration.

- [ ] **Step 5: Update dry-run fixtures and affected golden artifacts through the normal fixture path**

Every non-abstained summary fixture receives a real compact summary. Do not use `"TLDR"`, empty strings, or copied 19+-word prefixes.

- [ ] **Step 6: Run prompt, schema, and artifact tests**

Run:

```powershell
python -m pytest tests/test_prompt_dry_run_validation.py tests/_test_artifact_generator -v
python scripts/ci/check_prompt_fixture_regression.py
```

Expected: PASS. If the prompt corpus gate reports a bounded token increase, update its existing allowlist with an explicit expiry and measured delta rather than weakening the gate.

- [ ] **Step 7: Commit**

```powershell
git add src/prompts/report_vs/artifacts/summary/user.yaml src/prompts/_dry_run_fixtures.yaml src/schemas/artifacts.schema.json src/generators/_artifact_generator/storage.py tests/_test_artifact_generator tests/test_prompt_dry_run_validation.py tests/fixtures
git commit -m "feat: add bounded card tldr projections"
```

### Task 3: Add Grounded Cover Semantics

**Files:**
- Create: `src/prompts/report_vs/artifacts/cover_semantics/system.yaml`
- Create: `src/prompts/report_vs/artifacts/cover_semantics/user.yaml`
- Modify: `src/config/app.yaml`
- Modify: `src/prompts/_dry_run_fixtures.yaml`
- Modify: `src/schemas/artifacts.schema.json`
- Modify: `src/generators/_artifact_generator/generation.py`
- Modify: `src/generators/_artifact_generator/storage.py`
- Test: `tests/_test_artifact_generator/cases_02_assemble_artifacts_logs_topic_brief.py`

- [ ] **Step 1: Write a failing generation test**

Capture the prompt namespaces requested by the existing rendering dependency and assert:

```python
assert "report_vs/artifacts/cover_semantics" in requested_namespaces
assert artifacts["cover_semantics"] == {
    "evidence_shape": "trend",
    "direction": "rising",
    "geography_scope": "global",
    "evidence_density": "metric_rich",
    "domain_layer": "grid",
    "selection_reason": "Rising time-series evidence dominates the report.",
}
```

Also assert the structured records with `event == "artifact_model_response"` contain the required run/task/span/module/role fields.

- [ ] **Step 2: Run the focused test and confirm the missing namespace failure**

Run: `python -m pytest tests/_test_artifact_generator/cases_02_assemble_artifacts_logs_topic_brief.py -v`

Expected: FAIL because no cover-semantics artifact is generated.

- [ ] **Step 3: Add the prompt namespace**

The system prompt must require evidence-grounded classification and prohibit literal category illustration. The user prompt must return only:

```json
{
  "cover_semantics": {
    "evidence_shape": "trend",
    "direction": "rising",
    "geography_scope": "global",
    "evidence_density": "metric_rich",
    "domain_layer": "grid",
    "selection_reason": "Rising time-series evidence dominates the report."
  }
}
```

The prompt enumerates only the approved values from `report_cards.py` and receives DocMap, summary, insights, categories, region, and covered period as variables.

- [ ] **Step 4: Generate, validate, and store `cover_semantics`**

Use `render_artifact_json_model()` with a child context named `cover_semantics`. Validate the returned mapping before adding it to `assemble_artifacts_payload()`. Add `cover_semantics` to prompt hash calculation and cached-payload adaptation so cache keys change when the prompt changes.

Bump the artifacts payload to schema version `3.0`. Version `2.0` payloads without cover semantics fail with `cover_fingerprint_invalid` and are regenerated by the Task 10 backfill; do not invent semantic values during cache adaptation.

- [ ] **Step 5: Update schema, config routing, and dry-run fixture**

Add `cover_semantics` to the artifact schema's required properties. Route `report_vs/artifacts/cover_semantics` to `gpt-5-mini`, matching the existing summary/insight analysis tier.

- [ ] **Step 6: Run tests and prompt gates**

Run:

```powershell
python -m pytest tests/_test_artifact_generator tests/test_prompt_dry_run_validation.py -v
python scripts/ci/check_prompt_fixture_regression.py
```

Expected: PASS with the exact prompt text and response represented in structured logs.

- [ ] **Step 7: Commit**

```powershell
git add src/prompts/report_vs/artifacts/cover_semantics src/config/app.yaml src/prompts/_dry_run_fixtures.yaml src/schemas/artifacts.schema.json src/generators/_artifact_generator tests
git commit -m "feat: generate grounded cover semantics"
```

### Task 4: Implement Deterministic Geometry Selection

**Files:**
- Create: `src/generators/report_card_projection.py`
- Create: `tests/test_cover_geometry_selection.py`
- Create: `tests/test_report_card_projection.py`

- [ ] **Step 1: Write table-driven failing tests for all 16 families**

Use this complete mapping table:

```python
CASES = [
    ("trend", "rising", "ascending_trajectory"),
    ("trend", "falling", "descending_trajectory"),
    ("trend", "volatile", "volatility_corridor"),
    ("comparison", "converging", "convergence_funnel"),
    ("comparison", "diverging", "divergence_fan"),
    ("comparison", "neutral", "parallel_bands"),
    ("hierarchy", "neutral", "ranked_strata"),
    ("distribution", "neutral", "distribution_field"),
    ("concentration", "neutral", "concentration_core"),
    ("flow", "neutral", "flow_channels"),
    ("network", "neutral", "network_constellation"),
    ("hierarchy", "stable", "hierarchy_terraces"),
    ("cycle", "cyclical", "cycle_orbit"),
    ("trend", "neutral", "forecast_horizon"),
    ("uncertainty", "neutral", "uncertainty_envelope"),
    ("system", "neutral", "system_matrix"),
]
```

For `forecast_horizon`, pass `domain_layer="forecast"`; otherwise pass `domain_layer="grid"`. Assert that replacing the selector with one constant family would fail at least 15 cases.

- [ ] **Step 2: Add failing projection tests**

Assert that `build_cover_fingerprint()`:

- derives a stable integer seed from file ID and artifact hash;
- classifies global/multi-market, regional, country, and unknown geography;
- chooses the deterministic family from the validated cover semantics.

Assert that `build_report_card_manifest()`:

- takes title, publisher, publication date, covered period, completed fingerprint, insights, and cover assets as explicit arguments;
- chooses the first two `insights_final[*].text` entries without clipping;
- assigns one of `short|medium|long|xlong` title scales;
- raises `card_title_overflow` for titles over 120 normalized characters or with an unbreakable token over 32 characters;
- rejects missing compact/standard TLDRs and fewer than two insights.

- [ ] **Step 3: Run tests and confirm the missing module failure**

Run: `python -m pytest tests/test_cover_geometry_selection.py tests/test_report_card_projection.py -v`

Expected: FAIL with a missing `report_card_projection` module.

- [ ] **Step 4: Implement pure projection functions**

Create these public functions with this deterministic logic:

```python
def select_geometry_family(semantics: dict[str, object]) -> str:
    shape = str(semantics.get("evidence_shape") or "").strip()
    direction = str(semantics.get("direction") or "neutral").strip()
    domain = str(semantics.get("domain_layer") or "").strip()
    if shape == "trend" and domain == "forecast":
        return "forecast_horizon"
    if shape == "trend" and direction == "rising":
        return "ascending_trajectory"
    if shape == "trend" and direction == "falling":
        return "descending_trajectory"
    if shape == "trend" and direction == "volatile":
        return "volatility_corridor"
    if shape == "comparison" and direction == "converging":
        return "convergence_funnel"
    if shape == "comparison" and direction == "diverging":
        return "divergence_fan"
    mapping = {
        "comparison": "parallel_bands",
        "distribution": "distribution_field",
        "flow": "flow_channels",
        "network": "network_constellation",
        "concentration": "concentration_core",
        "cycle": "cycle_orbit",
        "uncertainty": "uncertainty_envelope",
        "system": "system_matrix",
    }
    if shape == "hierarchy":
        return "hierarchy_terraces" if direction == "stable" else "ranked_strata"
    return mapping[shape]


def classify_geography(region: str) -> tuple[str, str]:
    normalized = " ".join(str(region or "").split())
    folded = normalized.casefold()
    if not normalized:
        return "", "unknown"
    if folded in {"global", "worldwide", "international", "multi-market"} or "," in normalized:
        return normalized, "global"
    if folded in {"europe", "asia pacific", "latin america", "middle east", "africa", "north america"}:
        return normalized, "regional"
    return normalized, "country"


def select_title_scale(title: str) -> str:
    normalized = " ".join(title.split())
    count = len(normalized)
    longest_token = max((len(token) for token in normalized.split()), default=0)
    if count > 120 or longest_token > 32:
        raise AppError(
            code="card_title_overflow",
            message="Complete report title does not fit the approved card title scale",
            retryable=False,
        )
    if count <= 42:
        return "short"
    if count <= 64:
        return "medium"
    if count <= 88:
        return "long"
    return "xlong"


def stable_cover_seed(file_id: str, artifact_hash: str) -> int:
    material = f"{file_id.strip()}:{artifact_hash.strip()}".encode("utf-8")
    return int(hashlib.sha256(material).hexdigest()[:8], 16)


def build_cover_fingerprint(request: CoverFingerprintProjectionRequest) -> CoverFingerprint:
    geography_label, geography_scope = classify_geography(request.region)
    del geography_label
    return CoverFingerprint(
        schema_version="1.0",
        geometry_family=select_geometry_family(request.cover_semantics),
        evidence_shape=str(request.cover_semantics["evidence_shape"]),
        direction=str(request.cover_semantics["direction"]),
        geography_scope=geography_scope,
        evidence_density=str(request.cover_semantics["evidence_density"]),
        domain_layer=str(request.cover_semantics["domain_layer"]),
        seed=stable_cover_seed(request.file_id, request.artifact_hash),
        selection_reason=str(request.cover_semantics["selection_reason"]),
    )


def build_report_card_manifest(request: ReportCardManifestRequest) -> ReportCardManifest:
    insights = tuple(
        str(item.get("text") or "").strip()
        for item in request.insights_final[:2]
    )
    if len(insights) != 2 or any(not item for item in insights):
        raise AppError(
            code="card_key_insights_invalid",
            message="Exactly two complete card insights are required",
            retryable=False,
        )
    geography_label, geography_scope = classify_geography(request.region)
    return ReportCardManifest(
        schema_version="1.0",
        title=request.title.strip(),
        title_scale=select_title_scale(request.title),
        publisher=request.publisher.strip(),
        published_date=request.published_date,
        geography_label=geography_label,
        geography_scope=geography_scope,
        covered_period=request.covered_period.strip(),
        tldr_compact=request.tldr_compact.strip(),
        tldr_standard=request.tldr_standard.strip(),
        key_insights=insights,
        fingerprint=request.fingerprint,
        covers=request.covers,
    )
```

These functions perform no I/O and no logging. `select_geometry_family()` follows the approved priority order. `stable_cover_seed()` uses the first eight hexadecimal characters of SHA-256 as an unsigned integer.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_cover_geometry_selection.py tests/test_report_card_projection.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/generators/report_card_projection.py tests/test_cover_geometry_selection.py tests/test_report_card_projection.py
git commit -m "feat: project semantic report card manifests"
```

### Task 5: Render Three Premium Cover Assets

**Files:**
- Modify: `src/config/cover-styles.yaml`
- Modify: `src/services/cover_style_service.py`
- Modify: `src/services/cover_image_service.py`
- Modify: `src/generators/cover_image_generator.py`
- Modify: `src/orchestrators/cover_image_orchestrator.py`
- Modify: `src/_cli/pipeline.py`
- Modify: `tests/test_cover_style_service.py`
- Modify: `tests/test_cover_image_generator.py`
- Modify: `tests/test_cover_image_orchestrator.py`
- Create: `tests/integration/test_cover_image_service.py`

- [ ] **Step 1: Write failing style and generator tests**

Assert the loaded config exposes these dimensions:

```python
assert (config.layouts["small"].width, config.layouts["small"].height) == (1600, 900)
assert (config.layouts["medium"].width, config.layouts["medium"].height) == (1200, 1500)
assert (config.layouts["large"].width, config.layouts["large"].height) == (1200, 1600)
```

Assert the generator calls `render_cover_image()` exactly three times with `small`, `medium`, and `large`, and returns a complete `CardCoverAssetSet`.

- [ ] **Step 2: Write failing service integration tests**

Use the real local font and Pillow renderer. Assert:

```python
assert Image.open(result.small.output_path).size == (1600, 900)
assert Image.open(result.medium.output_path).size == (1200, 1500)
assert Image.open(result.large.output_path).size == (1200, 1600)
```

Use the 100-character live title fixture. Add a separate impossible unbroken-title fixture and assert `cover_title_overflow`.

- [ ] **Step 3: Run focused tests and confirm failures**

Run: `python -m pytest tests/test_cover_style_service.py tests/test_cover_image_generator.py -v`

Expected: FAIL because the current config and renderer support one 1600x900 layout and silently return minimum-size overflow.

- [ ] **Step 4: Replace the cover configuration with version `2.0`**

Define:

```yaml
schema_version: "2.0"
palette:
  background: "#061A31"
  background_elevated: "#082B54"
  geometry: "#6F94B5"
  geometry_highlight: "#D8E8F3"
  text: "#F8FAFC"
layouts:
  small:
    width: 1600
    height: 900
  medium:
    width: 1200
    height: 1500
  large:
    width: 1200
    height: 1600
```

Each layout also defines fixed publisher, title, and period rectangles plus approved max/min font sizes. Do not retain category color overrides.

- [ ] **Step 5: Implement geometry primitives in the existing image service**

Keep all filesystem/font/Pillow I/O in `cover_image_service.py`. Add private drawing functions for line, band, field, node, orbit, envelope, and matrix primitives; dispatch the 16 family names to compositions assembled from those primitives. Seed a local `random.Random(request.fingerprint.seed)` instance and never use global randomness.

Replace `_fit_multiline_text()` fallback behavior with:

```python
raise AppError(
    code="cover_title_overflow",
    message=f"Complete cover title does not fit the {request.size} title zone",
    retryable=False,
    context={"title": title, "size": request.size},
)
```

- [ ] **Step 6: Implement three-output generation**

Use deterministic paths:

```text
out/<report-slug>/assets/report-card-small.png
out/<report-slug>/assets/report-card-medium.png
out/<report-slug>/assets/report-card-large.png
```

Log family, size, seed, measured title font, and output path for each render.

Update `cover_image_orchestrator.py` so standalone regeneration loads each report's stored `artifacts.json`, validates `cover_semantics`, projects the fingerprint, and passes it to `CoverImageReport`. Update the `generate-covers` CLI table to print all three output paths rather than the removed singular `output_path`.

- [ ] **Step 7: Run cover tests and verify required logs**

Run:

```powershell
python -m pytest tests/test_cover_style_service.py tests/test_cover_image_generator.py tests/test_cover_image_orchestrator.py -v
python -m pytest tests/integration/test_cover_image_service.py -v -m integration
```

Expected: PASS; generated images have exact dimensions and the long title is complete.

- [ ] **Step 8: Commit**

```powershell
git add src/config/cover-styles.yaml src/services/cover_style_service.py src/services/cover_image_service.py src/generators/cover_image_generator.py src/orchestrators/cover_image_orchestrator.py src/_cli/pipeline.py tests/test_cover_style_service.py tests/test_cover_image_generator.py tests/test_cover_image_orchestrator.py tests/integration/test_cover_image_service.py
git commit -m "feat: render semantic report cover asset sets"
```

### Task 6: Persist The Card Manifest During Report Rendering

**Files:**
- Modify: `src/generators/report_render_generator.py`
- Modify: `src/contracts/ingest.py`
- Modify: `src/services/file_service.py`
- Test: `tests/test_report_render_generator.py`
- Test: `tests/test_file_service.py`

- [ ] **Step 1: Write a failing report-render test**

Capture `ReportCardManifestWriteRequest` and assert the persisted payload is written to:

```text
out/<report-slug>/report-card-manifest.json
```

Assert the payload contains complete TLDRs, two insights, fingerprint, and all three relative cover paths. Assert no manifest is written when cover generation returns an error.

- [ ] **Step 2: Run the test and confirm no manifest is produced**

Run: `python -m pytest tests/test_report_render_generator.py -k report_card_manifest -v`

Expected: FAIL because report rendering currently logs one cover outcome and does not persist card presentation data.

- [ ] **Step 3: Build the fingerprint before covers, then write the manifest after a complete cover outcome**

Use `build_cover_fingerprint()` with `analysis.artifacts_payload["cover_semantics"]`, region, file ID, and the artifact hash. Pass that fingerprint to `CoverImageReport`. After the generator returns `CardCoverAssetSet`, use `build_report_card_manifest()` with the fingerprint, TLDRs, insights, report metadata, and assets. Call a new top-level `file_service.write_report_card_manifest(request, ctx)` function that validates the request, serializes `asdict(request.manifest)` with sorted ASCII-safe JSON, and atomically writes `report-card-manifest.json` under the supplied report output directory. Return `ReportCardManifestWriteResponse` and emit start/complete structured events with required context fields. Add the manifest path to `IngestOutcome` with a schema-version bump and round-trip test.

- [ ] **Step 4: Add file-service behavior and log-field tests**

In `tests/test_file_service.py`, use `tmp_path` without patching internals. Assert the real file contains the complete manifest, the response reports the resolved path and positive byte count, and both structured log events include `run_id`, `task_id`, `span_id`, `role`, `module`, and `event`. For the negative case, create a regular file where the output directory must be and assert the real write raises non-retryable `report_card_manifest_write_failed`.

- [ ] **Step 5: Fail closed for invalid card data**

Do not swallow non-retryable card-contract errors. Log `report_card_manifest_validation_failed` and return an error ingest outcome; retryable service errors still propagate to the orchestrator.

- [ ] **Step 6: Run focused and regression tests**

Run: `python -m pytest tests/test_report_render_generator.py tests/test_report_generation_contracts.py tests/test_file_service.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/generators/report_render_generator.py src/contracts/ingest.py src/services/file_service.py tests/test_report_render_generator.py tests/test_report_generation_contracts.py tests/test_file_service.py docs/quality/contract_schemas.json
git commit -m "feat: persist report card manifests"
```

### Task 7: Publish Card Metadata And Cover IDs Through WordPress REST

**Files:**
- Modify: `src/contracts/wordpress.py`
- Modify: `src/services/_wordpress_service/posts.py`
- Modify: `src/generators/publish_generator.py`
- Test: `tests/test_publish_generator.py`
- Test: `tests/integration/test_service_integrations.py`

- [ ] **Step 1: Write failing service and generator tests**

Assert `create_post()` sends:

```python
"meta": {
    "ml_card_schema_version": "1.0",
    "ml_card_title_scale": "long",
    "ml_card_tldr_compact": "Complete compact TLDR.",
    "ml_card_tldr_standard": "Complete standard TLDR with the required grounded context.",
    "ml_card_key_insights": ["First insight.", "Second insight."],
    "ml_card_geography_scope": "global",
    "ml_card_cover_fingerprint": {"geometry_family": "ascending_trajectory", "seed": 184221},
    "ml_card_cover_small_id": 301,
    "ml_card_cover_medium_id": 302,
    "ml_card_cover_large_id": 303,
}
```

Assert all three cover files are uploaded, and the large cover is used as `featured_media` only for compatibility; card rendering uses the explicit size IDs.

- [ ] **Step 2: Run tests and confirm missing meta support**

Run: `python -m pytest tests/test_publish_generator.py tests/integration/test_service_integrations.py -k "publish or wordpress" -v`

Expected: FAIL because `WordPressPostCreateRequest` and the transport omit `meta`.

- [ ] **Step 3: Add typed post meta to the canonical WordPress request**

Add:

```python
meta: Optional[Dict[str, object]] = field(
    default=None,
    metadata={"doc": "Validated WordPress post meta keyed by registered REST field name."},
)
```

The service copies `request.meta` into the JSON payload without deciding card semantics.

- [ ] **Step 4: Load and validate the sibling manifest in `publish_generator.py`**

Resolve `report-card-manifest.json` from the HTML path's report directory, deserialize with `ReportCardManifest.from_dict()`, upload all three assets, and build the exact meta object above. Missing or invalid manifests raise `cover_asset_set_incomplete` or the relevant TLDR/title error before the post call.

- [ ] **Step 5: Run service, generator, contract, and log tests**

Run:

```powershell
python -m pytest tests/test_publish_generator.py tests/integration/test_service_integrations.py -k "publish or wordpress" -v
python scripts/ci/check_contract_schemas.py --update
python scripts/ci/check_contract_schemas.py
```

Expected: PASS and no live WordPress call in default unit tests.

- [ ] **Step 6: Commit**

```powershell
git add src/contracts/wordpress.py src/services/_wordpress_service/posts.py src/generators/publish_generator.py tests/test_publish_generator.py tests/integration/test_service_integrations.py docs/quality/contract_schemas.json
git commit -m "feat: publish report card metadata"
```

### Task 8: Register And Validate WordPress Card Meta

**Files:**
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-meta.php`
- Modify: `tests/wordpress_runtime/report_view_model_harness.php`
- Create: `tests/test_wordpress_report_card_contract.py`

- [ ] **Step 1: Write failing PHP-runtime tests for registered values and `New` boundaries**

Extend the harness input with a `meta` object and publication timestamp. Assert:

```python
assert model["tldr_compact"] == "Complete compact TLDR."
assert model["tldr_standard"] == "Complete standard TLDR."
assert model["key_insights"] == ["First insight.", "Second insight."]
assert model["geography_scope"] == "global"
assert model["is_new"] is True
```

Parameterize age values `0`, `604799`, `604800`, and `-1`, expecting `True`, `True`, `False`, and `False`.

- [ ] **Step 2: Run tests and confirm missing fields**

Run: `python -m pytest tests/test_wordpress_report_card_contract.py -v`

Expected: FAIL because the plugin registers only file ID, digest flag, publisher, period, and region.

- [ ] **Step 3: Register the card meta fields with field-specific sanitizers**

Add constants for every `ml_card_*` key. String fields use `sanitize_text_field`; insight arrays validate exactly two strings; fingerprint validates JSON/object keys and approved family; media IDs validate positive integers. All fields remain `single`, `show_in_rest`, and restricted to users who can edit posts.

Register the structured fields with explicit REST schemas:

```php
register_post_meta(
    $post_type,
    self::META_CARD_KEY_INSIGHTS,
    [
        'single' => true,
        'type' => 'array',
        'show_in_rest' => [
            'schema' => [
                'type' => 'array',
                'minItems' => 2,
                'maxItems' => 2,
                'items' => ['type' => 'string'],
            ],
        ],
        'sanitize_callback' => [self::class, 'sanitize_card_insights'],
        'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
    ]
);

register_post_meta(
    $post_type,
    self::META_CARD_COVER_FINGERPRINT,
    [
        'single' => true,
        'type' => 'object',
        'show_in_rest' => [
            'schema' => [
                'type' => 'object',
                'required' => ['geometry_family', 'seed'],
                'properties' => [
                    'geometry_family' => ['type' => 'string'],
                    'seed' => ['type' => 'integer'],
                ],
                'additionalProperties' => true,
            ],
        ],
        'sanitize_callback' => [self::class, 'sanitize_cover_fingerprint'],
        'auth_callback' => static fn (): bool => current_user_can('edit_posts'),
    ]
);
```

- [ ] **Step 4: Update the harness stubs**

Make `get_post_meta()` return values from `$GLOBALS['ml_test_meta']`, add `wp_get_attachment_image_url()` and current-time stubs, and emit the full view model as JSON.

- [ ] **Step 5: Run PHP-runtime and WordPress lint checks**

Run:

```powershell
python -m pytest tests/test_wordpress_report_card_contract.py -v
python scripts/ci/check_wordpress_subproject.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-meta.php tests/wordpress_runtime/report_view_model_harness.php tests/test_wordpress_report_card_contract.py
git commit -m "feat: register wordpress report card contracts"
```

### Task 9: Build The Canonical WordPress View Model

**Files:**
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php`
- Modify: `tests/wordpress_runtime/report_view_model_harness.php`
- Modify: `tests/test_wordpress_report_card_contract.py`

- [ ] **Step 1: Add failing view-model assertions**

Assert the model contains:

```php
[
    'title_scale' => 'long',
    'tldr_compact' => 'Complete compact TLDR.',
    'tldr_standard' => 'Complete standard TLDR.',
    'key_insights' => ['First insight.', 'Second insight.'],
    'geography_scope' => 'global',
    'geography_icon' => 'globe',
    'is_new' => true,
    'covers' => [
        'small' => 'https://example.test/media/small.png',
        'medium' => 'https://example.test/media/medium.png',
        'large' => 'https://example.test/media/large.png',
    ],
]
```

Add regional/country cases expecting `locator`, and unknown geography expecting an empty label/icon.

- [ ] **Step 2: Run tests and confirm missing model fields**

Run: `python -m pytest tests/test_wordpress_report_card_contract.py -v`

Expected: FAIL.

- [ ] **Step 3: Replace excerpt-derived card intelligence with registered meta**

The builder must stop using `wp_trim_words()` for canonical report cards. Keep legacy excerpt fields only for non-card consumers until static search proves they are unused. Validate all required card fields and expose a `card_contract_valid` boolean plus `card_contract_errors` list for the migration audit; normal renderer calls reject invalid models.

- [ ] **Step 4: Implement exact `New` and icon rules**

Use:

```php
$age = current_time('timestamp', true) - (int) $timestamp;
$is_new = $age >= 0 && $age < 7 * DAY_IN_SECONDS;
```

Map `global` to `globe`, `regional|country` to `locator`, and `unknown` to an empty icon.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_wordpress_report_card_contract.py tests/test_wordpress_report_view_model_runtime.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-view-model-builder.php tests/wordpress_runtime/report_view_model_harness.php tests/test_wordpress_report_card_contract.py
git commit -m "feat: expose canonical report card view models"
```

### Task 10: Backfill Card Data And Pass The Activation Audit

**Files:**
- Modify: `src/orchestrators/ingest_orchestrator.py`
- Modify: `src/_cli/pipeline.py`
- Modify: `tests/test_ingest_parallel.py`
- Modify: `tests/test_cli.py`
- Create: `Wordpress/scripts/audit-report-card-contracts.php`
- Modify: `tests/test_wordpress_report_card_migration.py`
- Modify: `README_WORDPRESS.md`

- [ ] **Step 1: Write a failing static audit-script test**

Assert the script checks every published report for:

```php
$required_keys = [
    'ml_card_schema_version',
    'ml_card_title_scale',
    'ml_card_tldr_compact',
    'ml_card_tldr_standard',
    'ml_card_key_insights',
    'ml_card_geography_scope',
    'ml_card_cover_fingerprint',
    'ml_card_cover_small_id',
    'ml_card_cover_medium_id',
    'ml_card_cover_large_id',
];
```

It must exit nonzero and print post ID/title plus missing keys when any report is invalid; it exits zero only with `0 invalid published reports`.

- [ ] **Step 2: Run the test and confirm the script is absent**

Run: `python -m pytest tests/test_wordpress_report_card_migration.py -k audit -v`

Expected: FAIL.

- [ ] **Step 3: Add an explicit pipeline backfill mode**

Add `force_report_cards: bool = False` to `run_ingest()` and this CLI option to the existing `ingest` command:

```python
force_report_cards: bool = typer.Option(
    False,
    "--force-report-cards",
    help="Reprocess reports whose report-card manifest is missing or invalid",
)
```

Normal ingest skip behavior remains unchanged. In force mode, a previously processed file is reprocessed only when its expected `report-card-manifest.json` is missing or fails `ReportCardManifest.from_dict()`. A valid manifest still skips. Log `ingest_report_card_backfill_decision` with file ID, decision, and reason.

- [ ] **Step 4: Add failing orchestrator and CLI tests, then implement the mode**

Tests assert:

- normal mode skips a previously processed report;
- force mode reprocesses a missing manifest;
- force mode reprocesses an invalid manifest;
- force mode skips a valid manifest;
- the CLI passes `force_report_cards=True` only when the flag is present.

Run: `python -m pytest tests/test_ingest_parallel.py tests/test_cli.py -k report_cards -v`

Expected after implementation: PASS.

- [ ] **Step 5: Implement the WP-CLI eval-file audit**

The script loads published report IDs, validates arrays/media attachment existence, and writes deterministic machine-readable lines. It performs no mutation.

- [ ] **Step 6: Document and run the backfill sequence before renderer migration**

Run against the target WordPress environment:

```powershell
python -m src.cli ingest --force-report-cards
python -m src.cli publish-wp
wp eval-file Wordpress/scripts/audit-report-card-contracts.php
```

The first command reprocesses only reports with missing or invalid manifests. The second republishes regenerated HTML and card metadata through the existing idempotent publish workflow. Do not start Task 11 until the audit prints `0 invalid published reports`.

- [ ] **Step 7: Run backfill, static, and PHP lint tests**

Run:

```powershell
python -m pytest tests/test_ingest_parallel.py tests/test_cli.py -k report_cards -v
python -m pytest tests/test_wordpress_report_card_migration.py -v
php -l Wordpress/scripts/audit-report-card-contracts.php
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/orchestrators/ingest_orchestrator.py src/_cli/pipeline.py tests/test_ingest_parallel.py tests/test_cli.py Wordpress/scripts/audit-report-card-contracts.php tests/test_wordpress_report_card_migration.py README_WORDPRESS.md
git commit -m "feat: gate report card rollout on complete backfill"
```

### Task 11: Implement The Three Report Card Renderers

**Files:**
- Create: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-card-renderer.php`
- Create: `tests/wordpress_runtime/report_card_renderer_harness.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php`
- Create: `tests/test_wordpress_report_card_renderer.py`

- [ ] **Step 1: Write failing renderer boundary tests**

For each accepted variant, assert one root class:

```python
assert 'class="ml-card ml-card--small"' in small_html
assert 'class="ml-card ml-card--medium"' in medium_html
assert 'class="ml-card ml-card--large"' in large_html
```

Assert:

- small uses `tldr_compact` and contains no insight list;
- medium uses `tldr_standard` and contains no insight list;
- large uses `tldr_standard` and renders exactly two `<li>` insights;
- the correct cover URL is used for each variant;
- the `New` badge appears only when `is_new` is true;
- global uses the globe SVG and regional/country uses the locator SVG;
- title and TLDR output contain no clamp wrapper, ellipsis, or shortened text;
- invalid variant `compact` throws `InvalidArgumentException`.

- [ ] **Step 2: Run tests and confirm the missing renderer failure**

Run: `python -m pytest tests/test_wordpress_report_card_renderer.py -v`

Expected: FAIL because the renderer class and harness do not exist.

- [ ] **Step 3: Implement one focused renderer class**

Public API:

```php
public function render(array $report, string $variant): string
```

Accepted variants are exactly `small`, `medium`, and `large`. Use output buffering internally, WordPress escaping at output, empty image alt text, visible HTML title/publisher/period, inline decorative SVGs with `aria-hidden="true"`, and one link destination from `permalink`.

- [ ] **Step 4: Load the renderer from the plugin bootstrap**

Add one `require_once` before the shortcodes class. Do not instantiate it globally in this task; dependency injection is handled in Task 12.

- [ ] **Step 5: Run renderer and PHP lint tests**

Run:

```powershell
python -m pytest tests/test_wordpress_report_card_renderer.py -v
python scripts/ci/check_wordpress_subproject.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-report-card-renderer.php Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php tests/wordpress_runtime/report_card_renderer_harness.php tests/test_wordpress_report_card_renderer.py
git commit -m "feat: add canonical wordpress report card renderer"
```

### Task 12: Migrate All Plugin Report Placements

**Files:**
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-plugin.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php`
- Create: `tests/test_wordpress_report_card_migration.py`

- [ ] **Step 1: Write a failing static migration test**

Assert:

```python
assert "private function render_report_card" not in shortcodes
assert "new Report_Card_Renderer" in plugin
assert "$this->report_card_renderer->render($report, 'small')" in shortcodes
assert "$this->report_card_renderer->render($report, 'medium')" in shortcodes
assert "$this->report_card_renderer->render($report, 'large')" in shortcodes
```

Also enumerate every shortcode method that outputs report content and fail if it emits a legacy `.ml-report-card` or bespoke featured-report article directly.

- [ ] **Step 2: Run the migration test and confirm legacy ownership**

Run: `python -m pytest tests/test_wordpress_report_card_migration.py -v`

Expected: FAIL because `Shortcodes` owns private report-card markup.

- [ ] **Step 3: Inject the renderer**

Construct `Report_Card_Renderer` in `Plugin::__construct()` and pass it to `Shortcodes`. Update the shortcode constructor signature explicitly.

- [ ] **Step 4: Replace report outputs with canonical variants**

Use this placement map:

| Placement | Variant |
| --- | --- |
| report browser/archive/search/topic/publisher/related/latest grids | `small` |
| curated rows and non-featured homepage report modules | `medium` |
| featured digest/homepage featured report | `large` |

Delete the private legacy `render_report_card()` after all callers delegate. Do not alter non-report entity cards.

For `ml_latest_reports`, add `variant` to `shortcode_atts()` with default `small`, normalize it with `sanitize_key()`, and reject any value outside `small|medium|large` with `InvalidArgumentException`. Pass the validated value to the canonical renderer. Add positive assertions for all three values and a negative assertion for `compact`; do not silently fall back for an invalid explicit value.

- [ ] **Step 5: Run migration, renderer, and existing portal tests**

Run:

```powershell
python -m pytest tests/test_wordpress_report_card_migration.py tests/test_wordpress_report_card_renderer.py tests/test_wordpress_market_bearing_portal.py -v
python scripts/ci/check_wordpress_subproject.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-plugin.php Wordpress/wp-content/plugins/marketlense-core/includes/class-marketlense-core-shortcodes.php tests/test_wordpress_report_card_migration.py
git commit -m "refactor: route report placements through canonical cards"
```

### Task 13: Implement The Theme Card System

**Files:**
- Modify: `Wordpress/wp-content/themes/marketlense/assets/css/theme.css`
- Modify: `Wordpress/wp-content/themes/marketlense/patterns/report-grid.php`
- Modify: report-related files under `Wordpress/wp-content/themes/marketlense/templates/` and `patterns/` identified by the migration test
- Modify: `tests/test_wordpress_market_bearing_portal.py`
- Modify: `tests/test_wordpress_report_card_migration.py`

- [ ] **Step 1: Add failing static CSS and template assertions**

Require:

```python
for selector in (
    ".ml-card--small",
    ".ml-card--medium",
    ".ml-card--large",
    ".ml-card__title",
    ".ml-card__tldr",
    ".ml-card__facts",
    ".ml-card__insights",
):
    assert selector in css

assert "-webkit-line-clamp" not in canonical_card_css
assert "text-overflow: ellipsis" not in canonical_card_css
assert "overflow: hidden" not in semantic_text_rules
```

Assert report patterns use shortcodes/canonical renderer output and no block-query report card markup remains.

- [ ] **Step 2: Run tests and confirm missing canonical CSS**

Run: `python -m pytest tests/test_wordpress_market_bearing_portal.py tests/test_wordpress_report_card_migration.py -v`

Expected: FAIL.

- [ ] **Step 3: Add one delimited canonical CSS section**

Use markers:

```css
/* BEGIN canonical report cards */
/* END canonical report cards */
```

Implement:

- explicit internal grid tracks for title, facts, TLDR, insights, and action;
- equal sibling alignment at normal breakpoints;
- `text-wrap: balance` on titles and `text-wrap: pretty` on TLDR/insights;
- medium side-by-side layout and large portrait media layout;
- one-column reflow under the existing mobile breakpoint;
- container-query refinements only after a widely available fallback declaration;
- `:focus-visible`, hover, and reduced-motion rules;
- no dense auto-placement that changes visual order;
- no semantic text clipping.

- [ ] **Step 4: Remove obsolete report-card rules**

Delete only CSS selectors proven by the migration test to belong to legacy report cards. Preserve similarly named non-report editorial post cards until their usage is confirmed.

- [ ] **Step 5: Update report patterns/templates**

`report-grid.php` explicitly requests `[ml_latest_reports limit="6" variant="small"]`. Other report-specific template placements use the approved placement map. Editorial WordPress posts remain non-report cards.

- [ ] **Step 6: Run static and WordPress checks**

Run:

```powershell
python -m pytest tests/test_wordpress_market_bearing_portal.py tests/test_wordpress_report_card_migration.py -v
python scripts/ci/check_wordpress_subproject.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add Wordpress/wp-content/themes/marketlense/assets/css/theme.css Wordpress/wp-content/themes/marketlense/patterns Wordpress/wp-content/themes/marketlense/templates tests/test_wordpress_market_bearing_portal.py tests/test_wordpress_report_card_migration.py
git commit -m "feat: style canonical report card variants"
```

### Task 14: Run Browser Verification And Accessibility Stress Tests

**Files:**
- Create or update browser artifacts only under: `output/playwright/report-card-system/`
- Modify production files only when a verified defect is found

- [ ] **Step 1: Start or identify the local WordPress target**

Use the repository's existing local WordPress environment and sync script when required:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\sync-local-wordpress.ps1
```

Expected: active local theme/plugin files match the workspace.

- [ ] **Step 2: Verify desktop and responsive layouts with the Browser plugin**

Open the homepage, reports archive, one topic archive, one publisher archive, and search results. Capture screenshots at `1440x1000`, `1024x900`, `768x1024`, and `390x844`.

For each page, evaluate:

```javascript
() => ({
  horizontalOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  variants: Array.from(document.querySelectorAll('.ml-card')).map((card) => card.className),
  clippedText: Array.from(document.querySelectorAll('.ml-card__title,.ml-card__tldr'))
    .filter((node) => node.scrollHeight > node.clientHeight || node.scrollWidth > node.clientWidth)
    .map((node) => node.textContent.trim()),
})
```

Expected: no horizontal overflow, only the three approved variant classes, and an empty `clippedText` array.

- [ ] **Step 3: Verify alignment and content completeness**

On a multi-card row, compare title, facts, TLDR, and action bounding boxes. Cards may have different overall rows only under narrow/reflow states; at desktop listing widths, sibling action baselines must match within one CSS pixel.

- [ ] **Step 4: Verify 200% zoom, text-spacing overrides, keyboard focus, and reduced motion**

Inject the WCAG text-spacing override and confirm no title/TLDR content disappears. Tab through every card action and verify visible focus. Emulate `prefers-reduced-motion: reduce` and verify cards do not translate.

- [ ] **Step 5: Verify cover identity**

For the same report in small, medium, and large contexts, confirm the same geometry family/seed is visually recognizable while each asset uses its own composition and complete title.

- [ ] **Step 6: Save evidence and run browser-console checks**

Store screenshots and snapshots under `output/playwright/report-card-system/`. Ignore only a confirmed favicon 404; all production JavaScript/PHP/network errors must be fixed and rechecked.

- [ ] **Step 7: Commit any verified fixes and no generated browser artifacts unless repository policy tracks them**

```powershell
git add Wordpress tests
git commit -m "fix: resolve report card browser verification defects"
```

Skip this commit when no production defect was found.

### Task 15: Documentation, Versions, Full Verification, And ZIP Regeneration

**Files:**
- Modify: `README.md`
- Modify: `README_WORDPRESS.md`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/marketlense-core.php`
- Modify: `Wordpress/wp-content/plugins/marketlense-core/readme.txt`
- Modify: `Wordpress/wp-content/themes/marketlense/style.css`
- Modify: `scripts/ci/run_mutation_gate.py`
- Regenerate: `Wordpress/dist/marketlense-core.zip`
- Regenerate: `Wordpress/dist/marketlense.zip`

- [ ] **Step 1: Update documentation**

Document the three variants, placement map, TLDR limits, 16 geometry families, fingerprint fields, cover dimensions, metadata icons, `New` boundary, backfill audit, browser checks, and ZIP commands.

- [ ] **Step 2: Bump release versions consistently**

Increment plugin `1.5.1` to `1.6.0` in the plugin header, constant, and `readme.txt`. Increment theme `1.4.2` to `1.5.0` in `style.css`.

- [ ] **Step 3: Run focused feature tests**

```powershell
python -m pytest tests/test_report_card_contracts.py tests/test_report_card_projection.py tests/test_cover_geometry_selection.py tests/test_cover_image_generator.py tests/test_cover_style_service.py tests/test_publish_generator.py tests/test_wordpress_report_card_contract.py tests/test_wordpress_report_card_renderer.py tests/test_wordpress_report_card_migration.py tests/test_wordpress_market_bearing_portal.py -v
```

Expected: PASS.

- [ ] **Step 4: Run the full default test and integrity gates**

```powershell
python -m pytest
python scripts/ci/check_formatting.py
python scripts/ci/run_type_check.py
python scripts/ci/check_architecture_imports.py
python scripts/ci/check_forbidden_patching.py
python scripts/ci/check_contract_schemas.py
python scripts/ci/check_prompt_fixture_regression.py
python scripts/ci/check_wordpress_subproject.py
```

Expected: every command PASS. Do not regenerate baselines or lower thresholds to hide a regression.

- [ ] **Step 5: Run mutation coverage for changed critical generators**

Extend `_targets()` in `scripts/ci/run_mutation_gate.py` with:

```python
MutationTarget(
    module_path=ROOT / "src" / "generators" / "report_card_projection.py",
    test_paths=("tests/test_report_card_projection.py", "tests/test_cover_geometry_selection.py"),
    max_mutants=6,
    min_score=80.0,
),
MutationTarget(
    module_path=ROOT / "src" / "generators" / "cover_image_generator.py",
    test_paths=("tests/test_cover_image_generator.py",),
    max_mutants=4,
    min_score=75.0,
),
MutationTarget(
    module_path=ROOT / "src" / "generators" / "report_render_generator.py",
    test_paths=("tests/test_report_render_generator.py",),
    max_mutants=4,
    min_score=75.0,
),
MutationTarget(
    module_path=ROOT / "src" / "generators" / "publish_generator.py",
    test_paths=("tests/test_publish_generator.py",),
    max_mutants=4,
    min_score=75.0,
),
```

The existing `_artifact_generator/generation.py` target remains active. Then run:

```powershell
python scripts/ci/run_mutation_gate.py --json-out mutation_results.json
```

Expected: no surviving mutation in changed decision logic. Add assertions for any surviving mutation before continuing.

- [ ] **Step 6: Build the plugin ZIP**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\build-plugin-zip.ps1
```

Expected: the command prints a path ending in `Wordpress\dist\marketlense-core.zip`.

- [ ] **Step 7: Build the theme ZIP**

Run from PowerShell through the repository's Bash environment:

```powershell
bash Wordpress/scripts/build-theme-zip.sh
```

Expected: the command prints a path ending in `Wordpress/dist/marketlense.zip`.

- [ ] **Step 8: Inspect ZIP contents and checksums**

```powershell
@'
import hashlib
import zipfile
from pathlib import Path

for path in (
    Path("Wordpress/dist/marketlense-core.zip"),
    Path("Wordpress/dist/marketlense.zip"),
):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert names
        assert not any("/.git/" in name or "/tests/" in name for name in names)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"{path}: {digest}")
'@ | python -
```

Expected: both archives are nonempty, contain one top-level plugin/theme directory, exclude development files, and print SHA-256 values.

- [ ] **Step 9: Review final diff and commit release artifacts**

```powershell
git diff --check
git status --short
git add README.md README_WORDPRESS.md Wordpress/wp-content/plugins/marketlense-core Wordpress/wp-content/themes/marketlense Wordpress/dist/marketlense-core.zip Wordpress/dist/marketlense.zip
git commit -m "feat: release semantic report card system"
```

- [ ] **Step 10: Final verification report**

Report:

- test and integrity-gate results;
- browser pages/viewports checked;
- migration audit result;
- plugin/theme versions;
- ZIP paths and SHA-256 checksums;
- any explicitly unrun live integration step.

Do not claim completion if the published-report audit is nonzero or either ZIP was built before the final verified source state.
