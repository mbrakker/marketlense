# Delegation Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight project-local Codex delegation convention for bounded Explorer and Implementer child tasks.

**Architecture:** Put essential routing and parent-responsibility rules in `.codex/skills/marketlense-delegation/SKILL.md`; put the copyable task forms in a supporting reference loaded only when delegation is actually needed. Link the existing specialized final-review workflow to the generic Explorer controls without changing production code or creating a scheduler, queue, database, or runtime.

**Tech Stack:** Codex Skill Markdown and native Codex collaboration/worktree capabilities when the execution surface exposes them.

## Global Constraints

- Do not install or configure Claude Code, DeerFlow, Waku Agent, CodeGraph, or another agent runtime.
- Child agents cannot expand the parent objective, delegate again, commit, push, or perform external writes unless the parent explicitly authorizes that action in the contract.
- Use native Codex limits only when the current surface exposes them; do not emulate time, turn, or queue management.
- The parent owns integration, deterministic state transitions, and completion decisions.

---

### Task 1: Define the reusable native delegation contract

**Files:**
- Create: `.codex/skills/marketlense-delegation/SKILL.md`
- Create: `.codex/skills/marketlense-delegation/references/task-forms.md`

- [x] Define use conditions, parent controls, Explorer/Implementer selection, native-limit handling, and stop conditions.
- [x] Add copyable Explorer and Implementer forms with objective, scope, paths, mode, output, evidence, verification, and limits.

### Task 2: Reuse the convention from specialized review

**Files:**
- Modify: `.codex/skills/final-engineering-review/SKILL.md`

- [x] Refer to the generic Explorer contract for read-only reviewer dispatch while retaining the specialized reviewer roles.

### Task 3: Validate and deliver

**Files:**
- Modify: `docs/superpowers/plans/2026-08-24-delegation-contract.md`

- [x] Validate the new Skill and existing affected Skill.
- [x] Run the deterministic completion gate: `PASS` for four Skill/plan files;
  the existing documentation check passed and no aggregate escalation was
  required.
- [ ] Inspect scope, commit, and push `main`.
