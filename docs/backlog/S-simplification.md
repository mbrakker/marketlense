# Boundary simplification

Canonical owner IDs: S3, S4. This document contains **Active outcome specifications and their retained technical proposal slices**. Status belongs to [CONSOLIDATED_TODO.md](../../CONSOLIDATED_TODO.md), not to individual proposal sections. The complete source texts are preserved unchanged in the [historical backlog](archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) and [historical proposal catalogue](archive/10improvements-20261011-preconsolidation.md).

Before implementing a slice, verify its historic diagnosis at current HEAD; use its **Luna implementation prompt** together with the full evidence and criteria immediately above it. Proposed thresholds are acceptance targets, not current results. Closed parent milestones are not reopened by a proposal's historical wording.

---
 
## S3. Simplify the PDF visual-heuristics boundary

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** PDF visual families are decomposed behind compatibility facades. Inspect `_visual_heuristics/shared.py` parent-namespace injection and reciprocal facade/child imports as a concrete coupling candidate; historical file counts are not a current measurement or refactor mandate. Preserve the audit-first/no-significant-change exit and canonical PDF boundary.
- **Target behaviour:** The PDF visual capability has clear semantic ownership and a smaller dependency surface only where evidence shows real coupling, while candidate/crop behavior, artifact paths, cache semantics, benchmarks and public facades remain unchanged.
- **What to implement, in order:**
  1. Run the dependency/ownership/module-size audit and identify one concrete remaining coupling that materially obscures the PDF boundary; if none is significant, close/hold with evidence rather than refactor for aesthetics.
  2. Define the intended owner/facade before movement and document which callers/contracts must remain stable.
  3. Move/extract only the identified responsibility behind the canonical PDF service boundary; do not add navigation-only layers or duplicate external-library access.
  4. Preserve compatibility facade/imports where approved callers still require them and update architecture mapping/movement evidence.
  5. Run focused equivalence tests and retained PDF candidate/crop benchmarks before closing.
- **Acceptance criteria:**
  - A specific pre-change coupling/ownership finding and measurable simplification are documented; otherwise the item may conclude “no significant change justified.”
  - External PDF/library I/O remains owned by the canonical boundary and is not duplicated in generators/orchestrators/UI.
  - Candidate selection, crop/table outputs, artifact paths, cache identities and retained benchmark signatures remain equivalent.
  - Architecture/import/service-boundary gates and focused/full relevant tests pass with no new generic facade layer.

### Luna implementation prompt — S3

```text
Work on S3 — Simplify the PDF visual-heuristics boundary at the current MarketLense HEAD.
Owner specification: docs/backlog/S-simplification.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## S4. Give WordPress shortcodes semantic ownership

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** `Archive_Browser` and `Publisher_Directory` already own archive/directory behavior through stable Shortcodes delegation/render registration. The catch-all retains navigation/homepage/topic/publisher-profile/entity concerns and unreachable old report-browser/briefing bodies. Complete live-family ownership and cleanup with runtime equivalence; do not re-extract completed owners or preserve dead code solely for string tests.
- **Target behaviour:** Coherent shortcode families have explicit feature ownership behind a stable registration/compatibility facade. Public shortcode names, hooks, output contracts, query behavior and CSS/JS handles do not change as a result of the refactor.
- **What to implement, in order:**
  1. Inventory remaining live shortcode families, their actual helper callers and unreachable former archive bodies; credit existing Archive_Browser/Publisher_Directory ownership.
  2. Keep stable tags/registration/public-render facade; start with an independent remaining live family instead of re-extracting completed archive/directory owners.
  3. Extract family-owned rendering/query helpers into feature-specific classes/modules while keeping shared primitives genuinely shared and WordPress-native.
  4. Preserve all existing shortcode tags, action/filter registration, asset handles, GET/query semantics and rendered markup unless a separate approved behavior item owns a change.
  5. Prove runtime markup/query/hook/asset equivalence, move source-inspection tests to canonical owners, then remove obsolete bodies/helpers only after live caller checks.
- **Acceptance criteria:**
  - Every extracted unit owns a coherent documented shortcode family; the original catch-all class no longer implements unrelated feature semantics directly.
  - Existing shortcode tags/hooks, report/archive/filter query behavior, public markup contracts and asset handles remain unchanged in equivalence tests.
  - No additional navigation-only abstraction or duplicate WordPress query/I/O boundary is introduced.
  - PHP/runtime tests cover each family and compatibility registration; architecture/service-boundary tests pass.

### Luna implementation prompt — S4

```text
Work on S4 — Give WordPress shortcodes semantic ownership at the current MarketLense HEAD.
Owner specification: docs/backlog/S-simplification.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
