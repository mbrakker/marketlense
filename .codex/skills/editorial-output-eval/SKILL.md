---
name: editorial-output-eval
description: Verify generated MarketLense editorial or user-facing intelligence; not for provider routing, WordPress transport, or presentation-only changes.
---

# Editorial output evaluation

Use after changing report intelligence, public editorial quality rules,
rendered prose, evidence-pack content, or reader-facing advisory output.

## Entry points and invariants

- `src/generators/public_editorial_quality_generator.py` owns deterministic
  editorial quality evaluation; publishing remains in its existing orchestrator
  and WordPress service boundaries.
- Preserve source grounding, provenance/linkage, schema completeness, quality
  rule results, and explicit abstention or failure rather than invented claims.
- Do not place long prompt prose in code or bypass retained evidence validation.

## Inspect and verify

Inspect the relevant generator, public contract under `src/contracts/`, source
evidence expectations, and public-render tests. Use the narrow applicable
checks:

```powershell
python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py
python -m pytest -q tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py
python scripts/ci/check_public_report_quality.py
```

Record the evaluated fixture/artifact identity, passed and failed rule IDs,
grounding outcome, and any approved waiver. Completion requires reader-facing
output evidence and no unverified public-quality regression; follow with the
completion gate.
