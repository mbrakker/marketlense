# Final Engineering Review Skill Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task by task.

**Goal:** Add a repository-local, read-only three-reviewer Codex Skill for significant MarketLense changes, together with a deterministic historical review benchmark.

**Architecture:** Keep the reusable workflow in `.codex/skills/final-engineering-review/` so it is project-local and has no production import path. Reuse the existing agent-engineering benchmark location for a small, review-specific corpus and scorer; the Skill itself remains an instruction artifact and makes no external dependency or write action.

**Tech Stack:** Codex Skill Markdown, Python standard library, JSON, pytest.

---

### Task 1: Define the historical review benchmark contract

**Files:**
- Create: `tests/test_final_engineering_review_benchmark.py`
- Create: `benchmarks/agent-engineering/final-engineering-review.json`

**Step 1: Write the failing test**

Assert that the corpus is traceable to the retained agent-engineering cases and that its scoring rules count only evidence-backed, high-confidence introduced findings as useful while measuring false positives separately.

**Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_final_engineering_review_benchmark.py`
Expected: FAIL because the corpus and scorer do not yet exist.

**Step 3: Write minimal implementation**

Add the six-case historical corpus and a small corpus-specific scoring script under `scripts/quality/`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_final_engineering_review_benchmark.py`
Expected: PASS.

**Result:** Completed. The scorer validates six cases mapped to retained task
evidence and separately counts useful evidence-backed findings, false positives,
and suppressed reports.

### Task 2: Add the reusable read-only Skill

**Files:**
- Create: `.codex/skills/final-engineering-review/SKILL.md`
- Create: `.codex/skills/final-engineering-review/references/finding-contract.md`

**Step 1: Implement the smallest workflow**

Specify significance gating, three independent review scopes, parallel dispatch when available, strict reviewer read-only constraints, parent evidence validation/deduplication, and high-confidence-only reporting.

**Step 2: Validate the Skill package**

Run: `python C:/Users/Михаил/.codex/skills/.system/skill-creator/scripts/quick_validate.py .codex/skills/final-engineering-review`
Expected: PASS.

**Result:** Completed. The project-local Skill dispatches exactly three
read-only reviewers, requires an immutable diff snapshot, and retains only
parent-validated, high-confidence introduced findings.

### Task 3: Document and validate the reusable benchmark

**Files:**
- Modify: `benchmarks/agent-engineering/README.md`
- Modify: `docs/quality/benchmarks.md`

**Step 1: Document exact commands and evaluator-owned data**

Describe historical-worktree preparation, the review-run record, deterministic useful-finding and false-positive metrics, and the Skill's significant-change scope.

**Step 2: Run focused validation**

Run: `python scripts/quality/final_engineering_review_benchmark.py validate --corpus benchmarks/agent-engineering/final-engineering-review.json`
Expected: PASS.

**Result:** Completed. Benchmark commands and evaluator-owned-data handling
are documented in the existing agent-engineering and quality benchmark docs.

### Task 4: Record evidence and deliver

**Files:**
- Modify: `docs/superpowers/plans/2026-08-24-final-engineering-review.md`

**Step 1: Run focused tests and documentation checks**

Run the benchmark tests and targeted documentation/agent-policy validation selected by the deterministic completion gate.

**Step 2: Inspect diff and completion evidence**

Run the canonical completion command and record its structured result. If existing baseline failures prevent PASS, report them without weakening a policy.

**Result:** Completed. `python scripts/quality/agent_completion_gate.py` returned
`PASS` with 8 changed files, no failures or unverified requirements, an
unchanged working tree during checks, and no aggregate full-gate escalation.

**Step 3: Commit and push**

Commit the scoped changes and push `main` to `origin` as requested.
