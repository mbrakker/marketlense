# Retained crop-refinement golden corpus v1

This corpus contains approved, already-produced crop-refinement evidence copied
from the local retained benchmark on 2026-07-13. It is intentionally separate
from the PDF candidate corpus because it preserves the decision sidecars and
rendered crop artifacts required by the crop-refinement gate.

- Reports: IAS Industry Pulse 2026, Julius Baer Secular Outlook 2026, and
  Worldpanel Brand Footprint 2025.
- Evidence per report: candidate pack, `crop_refine.json`, and the candidate,
  slice, and crop-refinement page assets used by the committed baseline.
- Integrity: CI verifies the candidate-pack, decision, and crop-artifact
  SHA-256 signatures from `docs/quality/pdf_crop_refine_benchmark_baseline.json`.

Do not replace this corpus with generated fixtures. Refresh it only from
reviewed retained artifacts, update the baseline through the benchmark command,
and record the resulting signature review in the change.
