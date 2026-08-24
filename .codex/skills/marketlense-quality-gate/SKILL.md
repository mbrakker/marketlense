---
name: marketlense-quality-gate
description: Produce deterministic MarketLense completion evidence after significant implementation work; not a substitute for subsystem regression Skills.
---

# MarketLense quality gate

Use as the final repository-specific verification workflow after significant
implementation work, following the applicable subsystem Skill.

## Canonical entrypoints

```powershell
python scripts/quality/agent_completion_gate.py
python scripts/ci/run_quality_gate.py --list
```

The first command classifies the actual diff, runs the least-cost credible
existing checks, and deterministically decides PASS/FAIL. The second is the
aggregate CI sequence; do not recreate either command in this Skill.

## Inspect and validate

Before running, inspect the final diff for scope, secrets, and unrelated
changes. Read `docs/quality/release-gates.md` only when selecting or explaining
aggregate escalation, and `docs/quality/evidence.md` only when the task changes
release evidence.

Run the completion command and retain its JSON. A required failed or unrun
check, a changed working tree during validation, or `result: "FAIL"` prevents a
completion claim. When the report requires the aggregate gate, run it; do not
weaken existing thresholds or treat a pre-existing failure as a PASS.

For significant workflow code, also use the approved safe discovery →
acquisition → ingest → publish validation when credentials and authority allow.
Record the exact profile, safe target, stage outcomes, and any unavailable
external verification. Completion is only a command-produced PASS plus the
applicable subsystem evidence; an LLM never assigns PASS.
