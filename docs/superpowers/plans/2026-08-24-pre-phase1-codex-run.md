# Pre-Phase-1 Codex Benchmark Run Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute and retain a genuine representative Codex baseline against the Phase-0 historical benchmark cutoff at `fd59abac1bd35fda5ee652adad80e21c7de52823`.

**Architecture:** Create ten disposable detached worktrees at historical fixing-commit parents and give child workers only their agent-facing task prompts. The parent retains evaluator-owned ground truth, collects child reports, independently assesses diffs and focused checks, normalizes observable metrics, and stores an actual run record and score report separately from corpus-integrity metadata.

**Tech Stack:** Git worktrees, native Codex child agents, existing benchmark scorer, pytest, JSON.

## Global Constraints

- Treat all commits after `fd59abac` as Phase-1 and exclude their tooling from every child worktree.
- No production credentials, browser profiles, publication targets, live provider calls, commits, pushes, or external writes in benchmark cases.
- Prompts reveal no evaluator-owned file list, fixing diff, required checks, or failure condition.
- Missing telemetry remains `"unavailable"`; correctness is an evaluator decision backed by diff and deterministic checks.

---

### Task 1: Prepare ten isolated historical cases

**Files:**
- Create: `docs/superpowers/plans/2026-08-24-pre-phase1-codex-run.md`

- [x] Select a representative ten-case subset covering architecture, bug, feature, browser, PDF, LLM, performance, and service-boundary work.
- [x] Create one detached worktree at each selected fixing-commit parent without copying evaluator truth into a worker prompt.

### Task 2: Execute the genuine child-agent baseline

**Files:**
- Create: `benchmarks/agent-engineering/baselines/codex-pre-phase1-run.json`

- [x] Dispatch bounded workers against assigned historical worktrees and retain their discovered files, modifications, commands, elapsed time, and unresolved evidence.
- [x] Stop workers on scope, authority, or deterministic-check blockers; do not retry using Phase-1 tools.

### Task 3: Evaluate and score results

**Files:**
- Create: `benchmarks/agent-engineering/baselines/codex-pre-phase1-report.json`

- [x] Compare each worker diff with evaluator-owned historical truth and run safe focused checks where possible.
- [x] Score the actual run with the existing corpus scorer and record category results, unavailable telemetry, failures, and reproducibility metadata.

### Task 4: Retain procedure and clean isolation

**Files:**
- Modify: `benchmarks/agent-engineering/README.md`
- Modify: `docs/quality/benchmarks.md`
- Modify: `docs/superpowers/plans/2026-08-24-pre-phase1-codex-run.md`

- [x] Document the frozen cutoff, selected cases, exact execution process, and limitations without leaking evaluator truth into prompts.
- [x] Remove only the named disposable worktrees after evidence has been retained.
- [x] Run the deterministic completion gate, inspect the final diff, commit, and push.
