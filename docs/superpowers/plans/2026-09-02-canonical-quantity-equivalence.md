# Canonical Quantity Equivalence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let deterministic numeric grounding accept equivalent universal quantity displays while preserving rejection of changed value, currency, unit, sign, ratio, range, and timeframe semantics.

**Architecture:** `src.utils.quantity` remains the sole deterministic parser and gains a small immutable canonical representation plus an exact-equivalence predicate. Numeric grounding (`numeric_only=True`) consumes that predicate instead of erasing unit and magnitude information. It does not identify business metrics or subjects: semantic grounding continues to own that question.

**Tech Stack:** Python 3.12, dataclasses, regular expressions, pytest, Ruff, mypy.

## Global Constraints

- Build on `src.utils.quantity`; do not introduce report, category, or business-metric rules.
- Canonicalize only parsed numeric value/sign, normalized magnitude, explicit unit/currency, ratio, range, and attached timeframe.
- Do not treat percent, percentage points, currencies, count units, ratios, ranges, or signs as interchangeable.
- Do not alter validator thresholds, severity, publication readiness, or semantic subject/metric matching.
- Preserve the untracked `tmp/` workspace content.

---

### Task 1: Define the canonical primitive contract and parser coverage

**Files:**
- Modify: `src/utils/quantity.py`
- Modify: `tests/test_quantity_utils.py`
- Test: `tests/test_quantity_utils.py::test_canonical_quantity_equivalence_normalizes_display_forms`

**Interfaces:**
- Consumes: existing immutable `Quantity` values produced by `extract_quantities(text)`.
- Produces: `canonicalize_quantity(quantity: Quantity) -> CanonicalQuantity` and `quantities_canonically_equivalent(left: Quantity, right: Quantity) -> bool`.

- [x] **Step 1: Write the failing parser/equivalence tests**

```python
assert _canonical_match("$3.0T", "$3 trillion")
assert _canonical_match("20%", "20 percent")
assert _canonical_match("2x", "2 times")
assert not _canonical_match("20%", "20 percentage points")
assert not _canonical_match("$3B", "$3T")
assert not _canonical_match("$3T", "€3T")
assert not _canonical_match("-3%", "3%")
assert not _canonical_match("10-12%", "10-13%")
assert not _canonical_match("$3T in Q1 2025", "$3 trillion in Q2 2025")
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests/test_quantity_utils.py::test_canonical_quantity_equivalence_normalizes_display_forms`

Expected: FAIL because canonical-equivalence functions and the `times`/signed-number parse support do not exist.

- [x] **Step 3: Add the minimal universal canonicalization**

```python
@dataclass(frozen=True)
class CanonicalQuantity:
    comparator: Comparator
    value: float
    low: Optional[float]
    high: Optional[float]
    unit_family: str
    unit: str
    timeframe: str

def quantities_canonically_equivalent(left: Quantity, right: Quantity) -> bool:
    return canonicalize_quantity(left) == canonicalize_quantity(right)
```

Normalize `x` and `times` to ratio `x`, use the already-scaled numeric values and normalized currencies, and include the range endpoints and structurally attached `timeframe` in the equality contract.

- [x] **Step 4: Run the test to verify it passes**

Run: `python -m pytest -q tests/test_quantity_utils.py::test_canonical_quantity_equivalence_normalizes_display_forms`

Expected: PASS.

### Task 2: Use canonical primitives in deterministic numeric grounding

**Files:**
- Modify: `src/generators/validation/quantities.py`
- Modify: `tests/_test_validation_generator/cases_01_validation_flags_metric_and_quote.py`
- Test: `tests/test_validation_generator.py::test_validation_accepts_equivalent_numeric_displays`

**Interfaces:**
- Consumes: a candidate `Quantity` and retained evidence `Quantity` in `quantity_supported(..., numeric_only=True)`.
- Produces: `True` only for canonical primitive equality; it intentionally does not establish subject or metric equivalence.

- [x] **Step 1: Write failing numeric-grounding tests**

```python
assert not validate_new_numbers(... "Market value reached €3T." ... "$3T" ...)
assert not validate_new_numbers(... "Adoption rose 20 percentage points." ... "20%" ...)
assert validate_new_numbers(... "Market value reached $3.0 trillion." ... "$3T" ...) == []
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests/test_validation_generator.py::test_validation_accepts_equivalent_numeric_displays`

Expected: FAIL because numeric-only matching currently strips family, unit, and magnitude before comparison.

- [x] **Step 3: Replace only the numeric-only comparison path**

```python
def quantities_match_numeric_only(candidate: Quantity, evidence: Quantity) -> bool:
    return quantities_canonically_equivalent(candidate, evidence)
```

Retain existing public APIs and unsupported-number severity so no gate or threshold changes.

- [x] **Step 4: Run the focused validation test to verify it passes**

Run: `python -m pytest -q tests/test_validation_generator.py::test_validation_accepts_equivalent_numeric_displays`

Expected: PASS.

### Task 3: Document the scope and validate release-relevant behavior

**Files:**
- Modify: `docs/quality/public-editorial-quality.md`

**Interfaces:**
- Consumes: parsed explicit quantity primitives from public copy and retained evidence.
- Produces: documentation stating that equivalent displays are normalized while metric/subject semantics and publication decisions remain unchanged.

- [x] **Step 1: Document the fail-closed boundary**

```markdown
Numeric grounding compares explicit universal quantity primitives in canonical form. It may normalize notation such as `$3T` and `$3 trillion`, but it does not equate currencies, unit families, signs, ratios, ranges, attached timeframes, or distinct business subjects and metrics.
```

- [x] **Step 2: Run focused utility and validation tests**

Run: `python -m pytest -q tests/test_quantity_utils.py tests/test_validation_generator.py`

Expected: PASS.

- [x] **Step 3: Run relevant public-quality checks**

Run: `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py; python scripts/ci/check_public_report_quality.py --minimum-reports 15 --output-dir out/public_report_quality_canonical_quantity --output-json out/public_report_quality_canonical_quantity.json`

Expected: PASS with no active quality blockers.

- [ ] **Step 4: Run formatting, lint, typing, and the smallest meaningful broader suite**

Run: `python scripts/ci/check_formatting.py; python scripts/ci/check_ruff_lint.py; python scripts/ci/run_type_check.py; python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Inspect scope and commit/push/PR**

```powershell
git diff --check
git status --short
git add src/utils/quantity.py src/generators/validation/quantities.py tests/test_quantity_utils.py tests/_test_validation_generator/cases_01_validation_flags_metric_and_quote.py docs/quality/public-editorial-quality.md docs/superpowers/plans/2026-09-02-canonical-quantity-equivalence.md
git commit -m "feat: canonicalize quantity equivalence"
git push -u origin feat/canonical-quantity-equivalence
gh pr create --base main --head feat/canonical-quantity-equivalence --title "feat: canonicalize quantity equivalence" --body "..."
```

Expected: clean scoped diff, pushed branch, and a pull request with test evidence.
