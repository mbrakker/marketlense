# Delegation task forms

Copy one form into a child task and replace every bracketed value. Omit no
required field. The parent retains this contract and compares the final report
against it.

## Explorer — read-only

```markdown
Mode: Explorer (strictly read-only)
Objective: [one question that advances the parent objective]
Scope: [bounded investigation; explicitly out-of-scope work]
Allowed subsystems/paths: [repository-relative paths or named subsystems]
Prohibited: edit/create/delete/format files; test runs with writes; stage,
commit, push; external writes; spawning another child; scope expansion.
Tools: [read-only repository tools; `codegraph_explore` only if configured]
Native limits: [only actual current-surface fields; otherwise `not exposed`]
Expected output:
- relevant files and why;
- call/data flows and public contracts;
- concrete risks or contradictions;
- unresolved evidence and the cheapest next inspection.
Required evidence: [path:line, symbol, test, command output, or retained artifact]
Verification responsibility: Parent verifies every material claim against source/tests.
Stop conditions: [evidence unavailable; requested path outside scope; credentials,
external write, or product decision required; native limit reached]. Stop and
return the bounded evidence; do not continue elsewhere.
```

Explorer reports facts and uncertainty, not edits or a PASS/FAIL verdict.

## Implementer — bounded write

```markdown
Mode: Implementer (bounded write)
Objective: [one implementation outcome within the parent objective]
Acceptance criteria:
- [observable criterion]
- [observable criterion]
Scope: [specific behavior and explicit exclusions]
Allowed subsystems/paths: [exclusive repository-relative paths]
Write authority: [edit only listed paths; no generated/runtime artifacts]
Worktree: [assigned isolated path, or `not needed: one sequential writer`]
Prohibited: paths outside scope; new dependency/runtime/service; external write;
child delegation; commit/push unless explicitly authorized.
Required inspection: [contracts, tests, policy, related current behavior]
Required verification: [exact focused commands and expected observable evidence]
Native limits: [only actual current-surface fields; otherwise `not exposed`]
Expected output:
- changed files and a one-line reason for each;
- acceptance-criterion result;
- exact commands, exit status, and relevant output;
- unverified requirements, residual risks, and stop conditions reached.
Verification responsibility: Child runs only assigned checks; parent reviews the
diff, integrates, runs the completion gate, and decides completion.
Stop conditions: [scope conflict; missing authority; failed required check;
contract ambiguity; necessary change outside allowed paths; native limit reached].
Stop with the current diff and evidence. Do not repair outside scope or retry
through a new child.
```

An Implementer may make changes only after all acceptance criteria and allowed
paths are populated. The parent creates a worktree before dispatch when
parallel writers would otherwise touch the same checkout; a worktree is not
needed for an Explorer or a single sequential Implementer.
