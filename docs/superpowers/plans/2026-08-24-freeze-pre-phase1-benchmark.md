# Freeze Pre-Phase-1 Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze a fair, reproducible pre-Phase-1 Codex benchmark without changing MarketLense production behavior.

**Architecture:** Extend the existing corpus-specific scorer rather than adding a framework. Historical solution paths become evaluator-only reference diagnostics; explicit evaluator scope findings become the only scope penalty. A small versioned protocol declares the ten comparison cases, six holdouts, starting-revision rule, injection manifest, execution restrictions, and measurement schema. The injector copies only manifest-declared evaluator tests from a pinned historical source revision into an already-created detached worktree.

**Tech Stack:** Python standard library, Git worktrees/show, JSON, pytest.

## Global Constraints

- Preserve the genuine ten-case run; do not synthesize a replacement.
- Do not implement, enable, or depend on Phase-1 Skills, MCPs, or production runtime code.
- Agent prompts remain evaluator-hidden from historical files, injection paths, required checks, and fixing diffs.
- Never treat unavailable telemetry as zero.
- Phase-1 comparison must use the committed protocol unchanged.

---

### Task 1: Establish fair scorer semantics

**Files:**
- Modify: `scripts/quality/agent_engineering_benchmark.py`
- Modify: `tests/test_agent_engineering_benchmark.py`
- Modify: `benchmarks/agent-engineering/cases.json`

- [x] Add failing scorer tests proving a modified alternative file has no scope penalty unless the evaluator records it as a verified violation, and proving historical-reference recall remains diagnostic.
- [x] Replace `relevant_files`/`allowed_modified_files` corpus metadata with historical-reference terminology and explicit evaluator scope-review metadata.
- [x] Implement the smallest scorer change that emits candidate files modified, verified scope violations, and historical-reference-file recall, with correctness and required verification dominating the weighted score.
- [x] Run `python -m pytest -q tests/test_agent_engineering_benchmark.py`.

### Task 2: Add deterministic evaluator-only injection

**Files:**
- Modify: `scripts/quality/agent_engineering_benchmark.py`
- Modify: `tests/test_agent_engineering_benchmark.py`
- Create: `benchmarks/agent-engineering/evaluator-injections.json`

- [x] Add tests for copying only manifest-declared files from the pinned source revision, refusing a non-parent worktree, and recording injection metadata.
- [x] Implement a corpus-specific `prepare-evaluator-worktree` command that verifies the historical parent revision and writes only the declared test/fixture files.
- [x] Declare the two affected case injections, including source revision, destination, SHA-256, and injection version.
- [x] Run focused injector/scorer tests and validate the corpus.

### Task 3: Freeze protocol and corrected artifacts

**Files:**
- Create: `benchmarks/agent-engineering/pre-phase1-protocol.json`
- Modify: `benchmarks/agent-engineering/baselines/codex-pre-phase1-run.json`
- Modify: `benchmarks/agent-engineering/baselines/codex-pre-phase1-score.json`
- Modify: `benchmarks/agent-engineering/baselines/codex-pre-phase1-report.json`
- Modify: `benchmarks/agent-engineering/README.md`
- Modify: `docs/quality/benchmarks.md`

- [x] Declare exactly ten comparison IDs and six holdout IDs, corpus hash/version, immutable prompts, starting-revision rule, worker topology, restrictions, injection version, and measurement schema.
- [x] Recreate only ML-LLM-001 and ML-PERF-001 from their retained starting revisions, inject the declared evaluator tests after worker completion, and rerun only the affected evaluator commands.
- [x] Update the preserved raw run records with injection provenance and corrected evaluator results, then regenerate the canonical score/report using the updated scorer.
- [x] Document protocol immutability, holdout exclusion from Phase-1 tuning, and the corrected primary/secondary metrics.

### Task 4: Validate and freeze

**Files:**
- Modify: `docs/superpowers/plans/2026-08-24-freeze-pre-phase1-benchmark.md`

- [x] Run corpus validation, scorer/injector tests, JSON validation, the canonical completion gate, and the exact re-score command.
- [x] Inspect scope for benchmark/docs-only changes, commit, and push the frozen protocol and corrected baseline.
