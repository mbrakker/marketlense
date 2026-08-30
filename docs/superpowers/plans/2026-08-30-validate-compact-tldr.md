# Validate Compact TLDR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate `summary.card_tldr_compact` with the existing evidence-linked public editorial quality path before publication.

**Architecture:** Extend the existing Summary text-item enumeration so compact TLDRs inherit the retained `claim_evidence_map`, deterministic public-copy checks, and the established `summary` repair target. Keep rendering’s current compact-TLDR preference unchanged and prove it consumes the validated artifact value.

**Tech Stack:** Python, pytest, existing deterministic public-editorial validator and report renderer.

## Global Constraints

- No new LLM call, artifact family, publish gate, schema layer, SEO generation branch, or chart/table change.
- Preserve existing `summary.tldr` and `summary.executive_summary` behavior.
- Use retained Summary evidence and the existing bounded `summary` regeneration target.

---

### Task 1: Prove the missing public-validator coverage

**Files:**
- Modify: `tests/test_public_editorial_quality_generator.py`
- Modify: `tests/test_report_regeneration_generator.py`

**Interfaces:**
- Consumes: `evaluate_public_editorial_quality(report_id, artifacts)` and `_public_text_items(artifacts)`.
- Produces: regression proof that compact TLDR is evidence-linked, receives numeric and temporal checks, passes when complete, and routes repair to `summary`.

- [ ] **Step 1: Write failing tests**

```python
assert {(item["artifact"], item["field"]) for item in _public_text_items(artifacts)} >= {
    ("summary", "card_tldr_compact"),
}
assert "public_editorial_quality.incomplete_numeric_expression" in rule_ids
assert "public_editorial_quality.temporal_integrity" in rule_ids
assert report.status == "pass"
assert issue.repair_target == "summary"
```

- [ ] **Step 2: Run targeted tests to verify RED**

Run: `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_report_regeneration_generator.py -k "compact or iab"`

Expected: failures because `_public_text_items()` does not emit `card_tldr_compact`.

- [ ] **Step 3: Implement minimal coverage expansion**

```python
for field_name in ("tldr", "card_tldr_compact", "executive_summary"):
    ...
```

- [ ] **Step 4: Run targeted tests to verify GREEN**

Run: `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_report_regeneration_generator.py -k "compact or iab"`

Expected: all selected tests pass.

### Task 2: Document and verify the reader-facing boundary

**Files:**
- Modify: `docs/quality/public-editorial-quality.md`
- Test: `tests/test_report_render_generator.py`

**Interfaces:**
- Consumes: validated retained Summary artifact and existing render-service metadata projection.
- Produces: documentation and regression evidence that SEO/Open Graph/Twitter/JSON-LD retain their compact-TLDR preference only after validation.

- [ ] **Step 1: Update the gate reference**

```markdown
The retained Summary `tldr`, `card_tldr_compact`, and `executive_summary`
share the same evidence-linked public-prose validation and summary repair target.
```

- [ ] **Step 2: Run render regression tests**

Run: `python -m pytest -q tests/test_report_render_generator.py`

Expected: rendering tests pass with compact TLDR used in public metadata surfaces.

### Task 3: Run focused validation and replay

**Files:**
- Verify only: changed implementation, tests, and diagnostics.

- [ ] **Step 1: Run requested focused suites**

Run: public-editorial, summary/artifact, regeneration, render-service, and relevant prompt/contract regression tests discovered from repository scripts.

- [ ] **Step 2: Run the documented five-report replay after focused suites pass**

Run: the repository’s safe five-report replay command, retain results, and investigate any regression attributable to this change.

- [ ] **Step 3: Inspect and publish**

Run: `git diff --check`, inspect scoped diff and model-call/artifact-family changes, commit `fix: validate compact tldr before publication`, and push the current branch.
