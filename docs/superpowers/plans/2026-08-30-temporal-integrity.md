# Temporal Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve source-proven comparative periods from findings through all report-local public editorial prose and repair any deterministic temporal-integrity failure through the existing bounded regeneration loop.

**Architecture:** Extend the existing deterministic public-editorial-quality evaluator rather than introduce a separate validation subsystem. The evaluator will compare only explicit temporal qualifiers found in retained source evidence with their linked public claim, emitting an existing targeted-regeneration-compatible error for lost periods and malformed comparison grammar. Artifact prompts will require period and forecast-marker preservation for initial generation and their existing repair counterparts will require direct correction from the retained evidence.

**Tech Stack:** Python, pytest, YAML/Jinja prompt templates, existing report artifact contracts and bounded regeneration orchestrator.

## Global Constraints

- Do not change chart, table, figure, crop, model-family, model-routing, or call-count behavior.
- Preserve only source-proven temporal qualifiers; never infer or reconstruct absent periods.
- Treat `Q1 2025` and `Q2 2025` as distinct even though both contain `2025`.
- Keep the existing public-editorial-quality validation and targeted-regeneration path.
- Update the canonical workflow and editorial-output documentation in the same change.

---

### Task 1: Define deterministic temporal-integrity behavior with failing tests

**Files:**
- Modify: `tests/test_public_editorial_quality_generator.py`
- Modify: `tests/test_render_service_public_prose.py`

**Interfaces:**
- Consumes: `evaluate_public_editorial_quality(report_id, artifacts)` and `_build_core_signal(summary, insights)`.
- Produces: blocking `public_editorial_quality.temporal_integrity` issues for lost source comparative qualifiers and malformed `in to` / `between and` wording; valid same-year, H1/H2, month/year, FY, and forecast comparisons remain accepted.

- [x] **Step 1: Write failing public-editorial tests**

```python
def test_temporal_integrity_rejects_collapsed_quarterly_comparison() -> None:
    report = evaluate_public_editorial_quality(
        report_id="activate-2026",
        artifacts=artifacts_with_insight(
            text="Share fell from 43% in 2025 to 41% in 2025.",
            evidence="Share fell from 43% in Q1 2025 to 41% in Q2 2025.",
        ),
    )
    assert "public_editorial_quality.temporal_integrity" in {
        issue.rule_id for issue in report.issues
    }
```

- [x] **Step 2: Run the new test and verify it fails because no temporal rule exists**

Run: `python -m pytest -q tests/test_public_editorial_quality_generator.py -k temporal_integrity`

Expected: FAIL because the current evaluator has no temporal-integrity issue.

- [x] **Step 3: Add focused Core-signal regression coverage**

```python
def test_core_signal_retains_distinct_quarterly_periods() -> None:
    signal = _build_core_signal(
        {"executive_summary": "Share fell from 43% in Q1 2025 to 41% in Q2 2025."},
        [],
    )
    assert "Q1 2025" in signal["text"]
    assert "Q2 2025" in signal["text"]
```

- [x] **Step 4: Run the Core-signal test and verify current behavior**

Run: `python -m pytest -q tests/test_render_service_public_prose.py -k quarterly_periods`

Expected: PASS if the renderer already preserves complete supported sentences; otherwise FAIL with the truncation/collapse to correct.

### Task 2: Implement the narrow validation rule and retain recovery compatibility

**Files:**
- Modify: `src/generators/public_editorial_quality_generator.py`
- Modify: `tests/test_public_editorial_quality_generator.py`
- Modify: `tests/test_report_regeneration_generator.py`

**Interfaces:**
- Consumes: each public text item and its linked retained evidence text.
- Produces: error issues with repair target `insights_bundle` or `summary` only when source comparison qualifiers are missing or malformed comparison prose is emitted; source text is never rewritten.

- [x] **Step 1: Implement a pure qualifier extractor and comparison check after the red test**

```python
def _temporal_integrity_issue(text: str, evidence_text: str) -> str:
    """Return a deterministic explanation only for source-proven temporal loss."""
```

The extractor recognizes quarter (`Q1`–`Q4`), half (`H1`/`H2`), named month plus year, fiscal year (`FY 2025`/`FY2025`), and explicit forecast markers. It checks only a source comparison containing at least two distinct qualifiers and fails only if the public claim loses one; same-year comparisons with both qualifiers remain valid. It also returns an error for `in to` and `between and`.

- [x] **Step 2: Run focused validation tests**

Run: `python -m pytest -q tests/test_public_editorial_quality_generator.py -k temporal_integrity`

Expected: PASS for Q1/Q2, H1/H2, month/year, FY, forecast, valid same-year, and malformed-comparison cases.

- [x] **Step 3: Add a regeneration test using the existing repair adapter**

```python
def test_regeneration_routes_temporal_integrity_to_the_existing_supported_family(tmp_path) -> None:
    repaired = regenerate_artifacts(..., issues=[temporal_integrity_issue])
    assert repaired["insights_final"][0]["text"] == "43% in Q1 2025 to 41% in Q2 2025"
```

- [x] **Step 4: Run regeneration coverage**

Run: `python -m pytest -q tests/test_report_regeneration_generator.py -k temporal_integrity`

Expected: PASS with the existing bounded repair mechanism and no new generation family.

### Task 3: Strengthen initial and repair prompt contracts

**Files:**
- Modify: `src/prompts/report_vs/evidence_packs/findings/system.yaml`
- Modify: `src/prompts/report_vs/artifacts/{insights_candidates,insights_final,summary,expert_comment,linkedin_post}/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/{insights_candidates,insights_final,summary,expert_comment,linkedin_post}/user.yaml`
- Modify: `src/prompts/_dry_run_fixtures.yaml`
- Modify: `tests/test_prompt_dry_run_validation.py`

**Interfaces:**
- Consumes: existing `doc_map_json`, evidence-pack JSON, editorial-plan JSON, and grounding-package variables.
- Produces: the unchanged schemas with explicit instructions to copy comparative periods and forecast markers exactly when used in prose, and to omit a period rather than inventing one.

- [x] **Step 1: Write a prompt dry-run test with an Activate/IAB quarterly fixture**

```python
def test_editorial_prompts_render_temporal_preservation_contract() -> None:
    rendered = render_all_editorial_prompt_families(quarterly_fixture)
    assert all("temporal qualifier" in item.user_text for item in rendered)
```

- [x] **Step 2: Verify it fails before prompt updates**

Run: `python -m pytest -q tests/test_prompt_dry_run_validation.py -k temporal_preservation`

Expected: FAIL because the temporal-preservation instruction is absent.

- [x] **Step 3: Update initial and regeneration prompt wording without adding variables or schemas**

Each changed prompt says: when conveying a source comparison, retain every exact supplied temporal qualifier (quarter, half, month/year, fiscal-year, and forecast marker); do not reduce distinct periods to a shared year; omit the temporal claim if the retained evidence cannot support it; never invent a period.

- [x] **Step 4: Run prompt validation**

Run: `python -m pytest -q tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py`

Expected: PASS; all prompt namespaces render with the existing fixture contract.

### Task 4: Add regression fixtures, document the behavior, and validate retained outputs

**Files:**
- Modify: the existing report-artifact/public-editorial regression fixtures selected during implementation for Activate 2026 and IAB/PwC
- Modify: `docs/product/editorial-output.md`
- Modify: `docs/workflows/validation-and-regeneration.md`

**Interfaces:**
- Consumes: retained source evidence for `43% in Q1 2025 to 41% in Q2 2025` and the IAB quarterly case.
- Produces: initial-generation and regeneration regression evidence across findings, final insights, summary, Expert View, Core Signal, and LinkedIn; documentation of the deterministic source-proven check.

- [x] **Step 1: Add retained fixtures and assertions for all public surfaces**

```python
assert "Q1 2025" in all_affected_outputs
assert "Q2 2025" in all_affected_outputs
assert "15.7% in to 14.3% in" not in all_affected_outputs
```

- [x] **Step 2: Run the requested suites**

Run: `python -m pytest -q tests/test_artifact_generator.py tests/test_public_editorial_quality_generator.py tests/test_report_regeneration_generator.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py`

Expected: PASS.

- [x] **Step 3: Regenerate and inspect the Activate 2026 and IAB/PwC retained reports**

Run the repository’s existing safe regeneration command/profile for each report, then search each produced finding, summary, expert comment, Core Signal, and LinkedIn artifact for the affected claims.

Expected: every occurrence keeps the source-supported distinct periods; no `in to` / `between and`; no new period appears.

- [x] **Step 4: Final integrity and delivery**

Run: `git diff --check; git diff --name-only; git status --short; git diff --cached --check`

Commit only after both retained-output inspections and all requested suites pass:

```powershell
git add <validated temporal-integrity files>
git commit -m "fix: preserve comparative temporal qualifiers"
git push
```

Expected: clean scoped diff, committed SHA, and successful push.
