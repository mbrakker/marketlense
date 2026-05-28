# PDF Crop Decomposition Review

Date: 2026-05-28

## Decision

`src/services/_pdf/crop.py` remains the stable internal compatibility surface behind the canonical `src/services/pdf_service.py` boundary. Implementation is split into private `_crop/` capability owners for image operations, deterministic crop geometry, table continuation stitching, crop-region artifact writes, crop-refine rendering, and preview rendering.

This preserves the modular monolith. It does not introduce a new service boundary, entrypoint, deployable component, provider interaction, prompt/config/schema change, or alternate crop workflow.

## Boundary Rationale

The prior module combined several stable responsibilities: PIL image trimming, PyMuPDF rectangle adjustment, adjacent-page table augmentation, cache-backed crop artifact writes, crop-refine page/bbox helpers, and preview rendering. The new modules separate those responsibilities without changing thresholds, branch order, render settings, fingerprint payloads, filenames, logging events, or contracts.

The split creates more than three private peer modules, so this review is required. The boundary is semantic rather than line-count-only: each owner can be tested through existing crop service behavior and compatibility imports remain centralized through `crop.py`.

## Verification Evidence

- Pre-refactor local baseline: `C:/Users/8FEE~1/AppData/Local/Temp/pdf_crop_baseline_pre_o606j5ys/baseline.json`
- Red ownership test before movement: `python -m pytest tests/test_pdf_crop_decomposition.py -q` failed because `_crop/` modules and facade `__all__` did not exist.
- Post-movement direct crop suite: `python -m pytest tests/test_pdf_crop_service.py -q` passed after restoring moved dataclass decorators.
- Focused affected suite: `python -m pytest tests/test_pdf_crop_decomposition.py tests/test_pdf_crop_service.py tests/test_pdf_figures_service tests/test_candidate_extraction_generator.py tests/test_candidate_extraction_orchestrator.py tests/test_pdf_panel_detection_decomposition.py tests/test_pdf_visual_candidates_decomposition.py tests/test_pdf_table_heuristics_decomposition.py tests/test_pdf_internal_boundaries.py -q` passed with `168 passed`.
- Full coverage run: `python -m pytest --cov=src --cov-report=xml --cov-report=term-missing` passed with `2648 passed, 17 deselected`.
- Quality gates passed: formatting, risk policy, split-symbol links, mypy, architecture imports, forbidden patching, repository hygiene, quality ledger, remediation runbooks, backlog source, contract schemas, WordPress subproject, coverage, mutation, quality regression, and prompt fixture regression.
- Post-refactor local baseline: `C:/Users/8FEE~1/AppData/Local/Temp/pdf_crop_baseline_pre_9jirgawu/baseline.json`
- Real-PDF gate: normalized candidate outputs, candidate-pack JSON, crop/preview/refine outputs, and artifact hashes matched exactly after temp-root normalization. Median candidate-pack runtime changed from `4.945724s` to `4.416999s` for Capgemini and from `8.049204s` to `7.562803s` for Kantar. No external/model/browser/OCR activity was introduced.

## Movement Audit

AST comparison against `HEAD:src/services/_pdf/crop.py` found `79` moved definitions/constants unchanged. One private helper, `_build_table_continuation_augments`, has an annotation-only difference so `table_continuation.py` does not import the region owner and violate the dependency direction; runtime behavior is unchanged. The corrective edit during verification restored the original `@dataclass(frozen=True)` decorators on `_ResolvedCropRegion` and `_TableContinuationAugment`, which were omitted by the mechanical extraction script.
