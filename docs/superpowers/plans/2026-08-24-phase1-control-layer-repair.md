# Phase-1 Control Layer Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair and objectively validate the provisional MarketLense Phase-1 Codex engineering-control layer without adding Phase-2 capability.

**Architecture:** Keep the benchmark, completion gate, Skills, and evidence corpus-specific. Use existing quality checks and historical worktrees; CodeGraph remains an external, temporary development dependency and is retained only when a matched end-to-end agent A/B meets the recorded decision rule.

**Tech Stack:** Python standard library, pytest, Git worktrees, Codex native agents/MCP, JSON, existing MarketLense quality scripts.

## Global Constraints

- Preserve the frozen pre-Phase-1 comparison protocol and its 10/6 split.
- No production runtime dependency, Phase-2 state, scheduler, queue, agent-memory, Repowise, or sqz work.
- Correctness and verified behavioral evidence outrank retrieval or implementation similarity metrics.
- CodeGraph index/configuration is development-local and is removed unless the corrected end-to-end A/B passes its adoption rule.
- Reviewers are read-only; the parent alone integrates repairs and determines completion through the deterministic gate.

### Task 1: Repair the deterministic completion gate

**Files:** `scripts/quality/agent_completion_gate.py`, `tests/test_agent_completion_gate.py`, `docs/quality/testing.md`.

- [ ] Write focused failing tests for architecture-triggered escalation, public contracts/persisted schemas, subsystem test selection, non-duplicated aggregate execution, content-sensitive snapshots, and bounded diagnostics.
- [ ] Replace coarse role-path escalation with architecture-policy/release-trigger-aligned rules and existing credible subsystem test mappings.
- [ ] Capture bounded check diagnostics and detect byte/content changes in already-dirty files.
- [ ] Run the completion-gate tests and selected existing check tests.

### Task 2: Repair lifecycle and native Skills

**Files:** `AGENTS.md`, `.codex/skills/marketlense-quality-gate/SKILL.md`, `.codex/skills/final-engineering-review/SKILL.md`, `.codex/skills/marketlense-delegation/SKILL.md`, `.codex/skills/marketlense-delegation/references/task-forms.md`, `.codex/skills/speedup-proof/SKILL.md`.

- [ ] Narrowly route significant behavior through subsystem Skill, read-only final review, parent repair, and completion gate.
- [ ] Replace full-diff reviewer preloading with base SHA, changed names, acceptance criteria, and bounded summary while retaining one immutable snapshot.
- [ ] Remove stale native-limit claims and unconditional optimization approval; require native limits only when exposed and use autonomous reversible baseline/hypothesis/change/measurement/keep-or-revert experiments.
- [ ] Validate modified Skills with the available Skill validator.

### Task 3: Repair CodeGraph methodology and run the matched A/B

**Files:** `scripts/quality/codegraph_phase0_benchmark.py`, `tests/test_codegraph_phase0_benchmark.py`, `benchmarks/agent-engineering/codegraph-phase0.json`, `benchmarks/agent-engineering/baselines/codegraph-phase0.json`, new A/B evidence artifacts and benchmark documentation.

- [ ] Correct native timing and discovery reporting so only actual native output determines discovered files/recall.
- [ ] Install/configure the current CodeGraph release as a temporary development-only minimal MCP, create an ignored local index, and use only `codegraph_explore`.
- [ ] Run matched prompt-isolated Codex A/B exploration on at least eight representative cases, recording correctness, discovered files, modifications, checks, observable tool/file reads/tokens, elapsed time, intervention, and rework.
- [ ] Retain CodeGraph only when the recorded end-to-end decision rule improves efficiency without correctness/relevant-file regression; otherwise remove config, CLI, and local index.

### Task 4: Run real final-review and Phase-1 checkpoint evidence

**Files:** `benchmarks/agent-engineering/baselines/`, `benchmarks/agent-engineering/README.md`, `docs/quality/benchmarks.md`.

- [ ] Run the six historical final-review cases with real read-only reviewer output and score useful-find and false-positive rates.
- [ ] Run a genuine baseline-Codex versus repaired-Phase-1 comparison using the existing benchmark and record all primary/observable secondary metrics without synthetic telemetry.
- [ ] Reject/remove any mechanism that does not demonstrate measured benefit; freeze only evidence-backed retained mechanisms.

### Task 5: Validate and integrate

- [ ] Validate all benchmark/injection/protocol and final-review corpora, run affected unit tests, and inspect the final diff for secret/scope exposure.
- [ ] Run the deterministic completion gate, commit, push, and report Phase-1 checkpoint outcomes and any deliberately removed mechanism.
