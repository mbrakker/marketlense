# Black-Box Pre-Phase-1 Benchmark Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two implementation-coupled evaluator payloads with black-box behavioral checks and freeze an elapsed-time comparison population without adding Phase-1 capability.

**Architecture:** Keep the existing corpus-specific injector and manifest, adding a SHA-verified evaluator-owned payload source that is independent of historical solution commits. The payloads exercise only publicly observable process behavior in isolated historical worktrees. The protocol records the new injection version and immutable elapsed-time eligible case IDs; only the two affected historical tasks are rerun.

**Tech Stack:** Python standard library, pytest, Git worktrees, JSON.

## Global Constraints

- Preserve the ten comparison IDs, six holdouts, prompts, parent revisions, worker restrictions, and prompt isolation.
- Do not install, enable, or implement a Phase-1 tool, Skill, MCP, or production behavior.
- Inject payloads only after a worker stops; retain SHA-256 provenance.
- Do not award or deny verification based on a historical helper, contract, module, or cache implementation.
- Keep unavailable telemetry unavailable and compare elapsed time only across the frozen matching case set.

---

### Task 1: Support evaluator-owned behavioral payloads

**Files:**
- Modify: `scripts/quality/agent_engineering_benchmark.py`
- Modify: `tests/test_agent_engineering_benchmark.py`
- Modify: `benchmarks/agent-engineering/evaluator-injections.json`

- [x] Add a failing test proving the injector accepts a SHA-pinned evaluator-owned payload without requiring a historical source API.
- [x] Implement the smallest manifest source selector that accepts either a historical source or a repository-local evaluator payload, rejects ambiguous entries, verifies SHA-256, and preserves parent-revision validation.
- [x] Run the injector/scorer tests.

### Task 2: Define black-box LLM and reuse checks

**Files:**
- Create: `benchmarks/agent-engineering/evaluator-payloads/llm_prompt_behavior.py`
- Create: `benchmarks/agent-engineering/evaluator-payloads/perf_reuse_behavior.py`
- Modify: `benchmarks/agent-engineering/evaluator-injections.json`

- [x] Write evaluator-only checks that exercise task-observable behavior without importing historical solution-only symbols or requiring a particular internal module.
- [x] Pin each payload path and SHA-256 in the injection manifest version.
- [x] Verify each payload does not expose its contents in a worker prompt and runs only after injection.

### Task 3: Freeze elapsed comparison and rerun affected cases

**Files:**
- Modify: `benchmarks/agent-engineering/pre-phase1-protocol.json`
- Modify: `benchmarks/agent-engineering/baselines/codex-pre-phase1-run.json`
- Modify: `benchmarks/agent-engineering/baselines/codex-pre-phase1-score.json`
- Modify: `benchmarks/agent-engineering/baselines/codex-pre-phase1-report.json`

- [x] Add exactly the independently timed baseline IDs to `elapsed_comparison_case_ids` and validate that they are comparison cases with measured elapsed values.
- [x] Recreate and rerun only ML-LLM-001 and ML-PERF-001 with frozen prompts, parent revisions, restrictions, and the declared repair topology.
- [x] Inject the behavioral payloads after workers stop, record evaluator results, regenerate the canonical score/report, and preserve the prior genuine capture.

### Task 4: Validate and freeze

**Files:**
- Modify: `benchmarks/agent-engineering/README.md`
- Modify: `docs/quality/benchmarks.md`
- Modify: `docs/superpowers/plans/2026-08-24-black-box-pre-phase1-repair.md`

- [x] Run corpus/protocol/injection validation, benchmark scorer tests, exact re-score, JSON/documentation checks, and the deterministic completion gate.
- [x] Inspect the benchmark/docs-only diff, commit, and push; report canonical metrics and the two corrected case outcomes.
