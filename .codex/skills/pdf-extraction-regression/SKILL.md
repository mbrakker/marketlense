---
name: pdf-extraction-regression
description: Verify MarketLense PDF, OCR, chart, table, crop, or visual-evidence changes; not for browser acquisition routing.
---

# PDF extraction regression

Use after changing PDF text/OCR, candidate extraction, figure/table decisions,
crop geometry or refinement, or PDF-derived evidence.

## Entry points and invariants

- `src/services/pdf_service.py` is the public PDF/OCR boundary; implementation
  remains under `src/services/_pdf/`.
- Preserve deterministic candidate identity, source/page provenance, crop
  bounds, meaningful chart/table content, and explicit degraded outcomes.
- Do not move PDF/OCR I/O into generators or orchestrators, or make a visual
  quality decision depend on uncontrolled provider behavior.

## Inspect and verify

Inspect the changed public facade, relevant `_pdf` component, contracts, and
the matching committed golden fixture. Select only the affected focused tests:

```powershell
python -m pytest -q tests/test_pdf_text_service.py tests/test_pdf_contents_service.py
python -m pytest -q tests/test_pdf_crop_service.py tests/test_pdf_crop_decomposition.py
python -m pytest -q tests/test_pdf_visual_candidates_decomposition.py tests/test_pdf_table_heuristics_decomposition.py
```

For candidate or crop-quality changes, also run the matching existing gate:

```powershell
python scripts/ci/check_pdf_candidate_benchmark.py
python scripts/ci/check_pdf_crop_refine_benchmark.py
```

Record fixture/golden identity, candidate or crop comparison, degraded-page
behavior, and every selected command. Completion requires preserved provenance
and deterministic focused evidence; use the completion gate afterward.
