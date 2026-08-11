# GWI Readiness First-Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent mechanical editorial labels, unsupported expert commentary, and duplicated table-of-contents prose from reaching first-run report readiness for any publisher.

**Architecture:** Trace the retained GWI report through public artifact assembly and semantic grounding. Reject or normalize label-style public prose before HTML rendering, and make the expert-comment generator request only claims directly supported by retained source evidence. Preserve the existing readiness rule as the final defence, then validate against the original failed report.

**Tech Stack:** Python, typed report-generation contracts, prompt resources, pytest, retained report checkpoints.

## Global Constraints

- Preserve grounded source claims and do not add publisher-specific branching.
- Prefer first-run deterministic validation or prompt constraints over regeneration.
- Add regression tests before each production change and observe the expected failure.
- Run a safe validation through the report’s retained pipeline; do not publish or write to WordPress.

---

### Task 1: Trace and prevent mechanical public labels

**Files:**
- Modify: `src/generators/public_editorial_quality_generator.py` or the first artifact-assembly boundary identified by trace
- Test: existing focused public-editorial-quality test module

- [x] Write a failing test using `Implication:`-prefixed generated public prose and assert first-run normalization omits the label without changing the supported sentence.
- [x] Run the focused test and confirm it fails because that label reaches the public artifact/rendering boundary.
- [x] Implement the smallest publisher-agnostic normalization or assembly check at that boundary.
- [x] Run the focused test and confirm it passes.

### Task 2: Prevent unsupported expert-comment inferences

**Files:**
- Modify: the expert-comment prompt/resource or its first-run contract boundary identified by trace
- Test: existing expert-comment/grounding test module

- [x] Write a failing test where a source describes an end-to-end workflow but does not support a claimed reduction in vendor integration, and assert the first-run output does not retain the causal inference.
- [x] Run the focused test and confirm it fails against the current contract.
- [x] Implement the smallest source-grounding constraint at the generator boundary.
- [x] Run the focused test and confirm it passes.

### Task 3: Verify the failed report and commit

**Files:**
- Modify: `docs/workflows/report-processing.md` if operational behavior changes

- [x] Run focused regression tests and static checks for changed modules.
- [x] Reprocess GWI from retained source through artifact validation, render, report-card generation, and GTML without publication.
- [x] Confirm no editorial-scaffold, semantic-grounding, duplicate-insight, or metadata-governance readiness failure remains.
- [x] Inspect the final diff and commit the scoped change.
