# Core Signal Heading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent generic Core Signal headings by deriving a reader-facing heading from the same selected evidence-backed insight as the body.

**Architecture:** Keep Core Signal selection in `src/services/_render_service/normalization.py`. Reuse its complete-sentence and clause-boundary shortening protections, with the complete selected sentence as the safe fallback; omit the module only when no selected insight or summary sentence exists. Fixture-backed render tests use the retained Batch 3 report artifacts and assert the public HTML cannot contain the retired generic copy.

**Tech Stack:** Python 3.12, pytest, Jinja report renderer, retained JSON fixtures.

## Global Constraints

- No LLM or external model call is added.
- Heading and body must derive from the same selected insight/evidence item.
- Preserve existing decimal, time, ratio, and coordinated-phrase safeguards.
- `Source-backed market signal` must never enter published HTML.
- Render the five retained Batch 3 reports and inspect every Core Signal before committing.

---

### Task 1: Specify public Core Signal behavior with retained fixtures

**Files:**
- Create: `tests/fixtures/editorial_core_signal/batch_03_core_signals.json`
- Modify: `tests/test_render_service_public_prose.py`

**Interfaces:**
- Consumes: `_build_core_signal(tldr_text: str, executive_summary: str, insights: list[dict[str, str]]) -> dict[str, str]`.
- Produces: public-core-signal regression coverage using literal expected headings and bodies.

- [x] **Step 1: Write failing behavior tests**

```python
assert signal["heading"] == "The complete selected insight sentence."
assert signal["heading"] != "Source-backed market signal"
assert "Source-backed market signal" not in rendered_html
```

Cover a normal sentence, a long clause-shortened sentence, decimal/ratio and timestamp examples, a coordinated phrase, and the no-short-safe-heading fallback. Load the four fallback Batch 3 insights and expected headings from the new fixture.

- [x] **Step 2: Run the focused tests to verify the existing generic-heading failures**

Run: `python -m pytest -q tests/test_render_service_public_prose.py`

Expected: failures show `Source-backed market signal` where the fixtures require a subject-specific or complete-sentence heading.

### Task 2: Derive or safely retain the selected sentence as the heading

**Files:**
- Modify: `src/services/_render_service/normalization.py:195-272`

**Interfaces:**
- Consumes: selected Core Signal candidate body and existing `_core_signal_heading(text: str) -> str` shortening logic.
- Produces: non-generic reader-facing `heading` and unchanged selected `body`, `insight_id`, and `evidence_id`.

- [x] **Step 1: Implement the smallest deterministic fallback**

```python
heading = _core_signal_heading(body) if body else ""
if body and not heading:
    heading = body
```

Do not change candidate ranking or source IDs. Return an empty heading/body only when no candidate sentence exists, allowing the template to omit the signal panel instead of emitting invented generic copy.

- [x] **Step 2: Run the focused public-prose tests**

Run: `python -m pytest -q tests/test_render_service_public_prose.py`

Expected: PASS; all assertions confirm a same-item heading/body pair and no generic fallback.

### Task 3: Render-regress retained reports and document the public contract

**Files:**
- Modify: `docs/product/editorial-output.md:120-133`
- Modify: `docs/workflows/report-processing.md:94-98`
- Test: `tests/test_render_service_public_advisory.py`

**Interfaces:**
- Consumes: retained Batch 3 final insights/artifacts and report rendering entry points.
- Produces: rendered public HTML without generic Core Signal fallback copy and documented complete-sentence fallback behavior.

- [x] **Step 1: Update documentation**

State that Core Signal headings reuse deterministic safe shortening and otherwise use the complete selected sentence; generic system copy is never public-facing.

- [x] **Step 2: Render and inspect all five Batch 3 reports**

Run the repository’s safe retained-artifact render path, then assert each `final.html` Core Signal is non-generic and records its expected heading/body pairing.

- [x] **Step 3: Run quality checks**

Run:

```powershell
python -m pytest -q tests/test_render_service_public_prose.py tests/test_render_service_public_advisory.py
python scripts/ci/check_public_report_quality.py
git diff --check
```

Expected: all commands exit 0 and no rendered Batch 3 HTML contains `Source-backed market signal`.

- [ ] **Step 4: Review and publish the completed change**

Run `git diff --check`, inspect the staged diff and rendered artifacts for the prohibited copy, then commit and push only if every validation has passed:

```powershell
git add src/services/_render_service/normalization.py tests/test_render_service_public_prose.py tests/fixtures/editorial_core_signal/batch_03_core_signals.json docs/product/editorial-output.md docs/workflows/report-processing.md docs/superpowers/plans/2026-09-02-core-signal-heading.md
git commit -m "fix: derive editorial core signal headings"
git push
```
