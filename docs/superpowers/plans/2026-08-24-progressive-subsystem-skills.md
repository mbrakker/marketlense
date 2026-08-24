# Progressive Subsystem Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add narrow repository-local Codex Skills for the MarketLense subsystem routes already named by `AGENTS.md`.

**Architecture:** Each Skill lives in `.codex/skills/<name>/SKILL.md`, keeps only its trigger, canonical entrypoints, invariants, inspection targets, focused checks, evidence, and completion conditions, and links to existing policy rather than copying it. A project-local `speedup-proof` refines the existing Skill under the same name with MarketLense benchmarks instead of adding another optimization workflow.

**Tech Stack:** Codex Skill Markdown and existing Python quality/test commands.

## Global Constraints

- No Claude Code or DeerFlow dependency, installation, configuration, or copied implementation.
- Keep `AGENTS.md` unchanged unless a concise routing correction is necessary.
- Existing policy and CI scripts remain authoritative; create no routing framework or new quality runner.
- Add supporting references only if a Skill genuinely needs conditional detail.

---

### Task 1: Capture canonical subsystem entrypoints and focused checks

**Files:**
- Create: `docs/superpowers/plans/2026-08-24-progressive-subsystem-skills.md`

- [x] Inspect existing commands, tests, contracts, and policy references for acquisition, PDF, LLM, editorial, WordPress, dependencies, quality, and performance.
- [x] Record only proven canonical entrypoints and bounded test choices in the Skill instructions.

### Task 2: Add seven requested subsystem Skills

**Files:**
- Create: `.codex/skills/acquisition-regression/SKILL.md`
- Create: `.codex/skills/pdf-extraction-regression/SKILL.md`
- Create: `.codex/skills/llm-change-eval/SKILL.md`
- Create: `.codex/skills/editorial-output-eval/SKILL.md`
- Create: `.codex/skills/wordpress-regression/SKILL.md`
- Create: `.codex/skills/dependency-upgrade/SKILL.md`
- Create: `.codex/skills/marketlense-quality-gate/SKILL.md`

- [x] Implement narrow discriminating triggers and direct links to canonical sources.
- [x] Include only subsystem-specific inspection, invariants, focused checks, evidence, and completion conditions.

### Task 3: Improve the existing optimization workflow without duplication

**Files:**
- Create: `.codex/skills/speedup-proof/SKILL.md`

- [x] Preserve the existing explicit-approval and evidence-first optimization behavior under the same Skill name.
- [x] Replace generic benchmark guidance with relevant MarketLense measurement entrypoints and completion evidence.

### Task 4: Validate and document the project-local catalog

**Files:**
- Modify: `docs/superpowers/plans/2026-08-24-progressive-subsystem-skills.md`

- [x] Run the Codex Skill validator on each Skill.
- [x] Run the deterministic completion gate and record structured result: `PASS`
  for 9 changed Skill/plan files; the existing documentation check passed and no
  aggregate escalation was required.
- [ ] Inspect the final diff, commit, and push `main` as requested.
