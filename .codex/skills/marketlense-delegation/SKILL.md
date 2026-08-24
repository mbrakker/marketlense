---
name: marketlense-delegation
description: Delegate a bounded read-only investigation or isolated implementation task while keeping MarketLense integration and completion with the parent.
---

# MarketLense delegation

Use only when a child can complete a bounded, independently reviewable part of
the parent's current objective. Do not delegate routine local work, a vague
research request, or work that needs a scheduler, durable state, or autonomous
follow-up.

## Parent controls

The parent writes the contract before dispatch, retains the user objective, and
is solely responsible for integration, deterministic state transitions, checks,
and completion. A child may not broaden scope, create subagents, change the
mode, add paths, commit/push, or perform an external write unless that exact
authority appears in its contract.

Use **Explorer** for read-only evidence gathering. Use **Implementer** only
when acceptance criteria and allowed write paths are explicit. Read
`references/task-forms.md` when constructing either task.

For structural Explorer work, prefer the high-level `codegraph_explore` tool
only when CodeGraph is already configured on the current surface. It is
retrieval assistance, not authority; do not install, initialize, or preserve a
CodeGraph index merely to delegate. Verify material ambiguous results against
current source and tests.

## Limits and isolation

Use a native execution, time, turn, token, or reasoning limit only when the
current Codex delegation surface exposes that setting. On this surface,
`reasoning_effort` is available for a spawned child, while time/turn/token
caps are not; omit unsupported fields and use the declared stop conditions or
native interruption rather than inventing counters or a queue.

Explorers are strictly read-only: no file edits, formatters, test runs that
write state, staging, commits, or external writes. For concurrent Implementers,
the parent creates and assigns an isolated worktree only when parallel writes
provide real value; otherwise use one bounded writer in the current worktree.

## Semantic reasoning, deterministic control

Children use LLM reasoning to interpret code and evidence. The parent uses the
repository's deterministic commands and policies for workflow state,
verification, integration, and PASS/FAIL. A child report is evidence, never a
completion decision.

## Completion

Accept a child result only after checking its scope, evidence paths, commands,
and working-tree result. Integrate or repair only in the parent task, run the
applicable subsystem Skill and `marketlense-quality-gate`, and report any stop
condition or unverified requirement instead of silently retrying or expanding
the delegation.
