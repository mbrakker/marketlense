# Test Long-File Decomposition Review

Generated: 2026-06-11

## Scope

This review covers the movement-only split of first-party test modules that exceeded the 1,000-line ownership threshold. The original pytest entrypoint files remain as facades, while focused case groups and shared builders live in adjacent private packages under `tests/`.

## Architecture Review

- Modular monolith preservation: yes. The change is test-only and does not introduce a new runtime package, process, deployable unit, external service boundary, or production import path.
- Boundary semantics: the new boundaries are local test ownership boundaries. Each original test file keeps its canonical pytest path, while adjacent private modules own contiguous behavior-case groups and shared fixture/helper setup.
- Fewer-module alternative: keeping the previous files would preserve one path but leaves long-test concentration unchecked. The private-package split keeps existing entrypoints while making case groups small enough to review and collect independently.
- Cognitive load: the next engineer can still run the original test path, while focused failures now point to smaller private case modules. Local shared modules hold imports, builders, and fixtures that were already file-global test dependencies.

## Movement Audit

Command run after decomposition:

```powershell
python scripts/count_long_files.py --min-lines 1000
pytest --collect-only -q <affected original test facades>
pytest -q
```

AST movement audit against `HEAD`:

- moved symbol count: 1,584
- unchanged moved symbol count: 1,583
- changed moved symbol count: 1
- missing moved symbol count: 0
- facade-owned definition count after split: 0

The single changed moved symbol is a stale artifact-generator expectation corrected from `summary_claim_span_missing` to the currently enforced `summary_missing_claim_evidence` taxonomy for claims with no evidence id.
