# PDF page reconciliation v5 geometry fix

## Goal

Correct the remaining false-positive risk in structured footer extraction by using
PyMuPDF line bboxes for footer-region, baseline, and left-to-right checks while
retaining the containing text-block bbox for persisted provenance. Preserve the
Phase 1 fail-closed behavior and the v4 golden-PDF counts.

## Scope

- Inspect native PyMuPDF line/block grouping for the IAS and synthetic genuine PDFs.
- Add RED tests for separated baselines, multiline blocks crossing the footer band,
  ordering, uniqueness, missing labels, explicit `REPORT | N`, and strong/weak
  conflicts.
- Add one narrow page-artifact helper that reuses one `get_text("dict")` result for
  block pairs and line records.
- Use line geometry in both structured-footer matching and ordinary margin-line
  candidate extraction so body numbers in crossing blocks cannot become evidence.
- Increment the algorithm from v4 to v5; keep schema version 1.1 and persisted
  geometry scope `text_block`.
- Re-run focused, downstream, contract, architecture, local quality, and hosted
  CI checks; refresh the pilot evidence and existing S3 status entry.

## Verification checkpoints

1. Current v4 branch is clean and native IAS line geometry is recorded.
2. Synthetic genuine-PDF regressions fail before production changes.
3. Geometry fix passes focused/full reconciliation tests without changing the
   existing fail-closed cases.
4. Four golden PDFs remain 71 verified, 2 inferred, 19 unresolved with no
   incorrect mapping changes; IAS 8-11/16-17 and Capgemini 12 are checked.
5. Final diff is scoped, schema-valid, documented, committed, pushed, and checked
   by exact-SHA CI. Phase 2 remains blocked.
