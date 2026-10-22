# R8 / PATH-03 — Candidate PDF Cache and OCR Chunk Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Make candidate PDF caches and OCR chunk/render artifacts deterministic, source-aware, atomic, and within supported Windows path budgets while preserving compatible cache hits and OCR contracts.

**Architecture:** Keep cache naming in the candidate orchestrator, PDF chunk path/write ownership in the PDF service, and OCR cache/render path selection in the OCR generator. Reuse `safe_path_segment`, `bounded_artifact_filename`, the canonical file service, MD5 lineage, and existing cache keys; add only small path-budget helpers needed by these producers. No PATH-02 changes, new infrastructure, or provider/model behavior changes.

**Tech Stack:** Python, pytest, `pypdf`, PyMuPDF, typed `AppError`, `src.services.file_service`, native Windows-compatible path accounting.

## Global Constraints

- Preserve existing Drive IDs, MD5 lineage, OCR contracts, prompt/model settings, provider calls, and downstream provenance.
- Preserve normal filename compatibility where safely possible and existing compatible OCR cache hits.
- Keep writes atomic and reject conflicting artifacts without destructive replacement.
- Fail with actionable non-retryable errors before download/OCR when the resolved root cannot fit the supported Windows path policy.
- Do not modify PATH-04–06 or reopen PATH-02.
- Add focused tests before production code and verify each regression through a red-green cycle.

### Task 1: Source-aware bounded candidate cache paths

**Files:**
- Modify: `src/utils/path_utils.py`
- Modify: `src/orchestrators/candidate_extraction_orchestrator.py`
- Test: `tests/test_candidate_extraction_orchestrator.py`
- Test: `tests/test_path_utils.py`

**Interfaces:**
- Candidate cache naming keeps the readable sanitized PDF stem, adds deterministic Drive-file identity and available MD5 identity, and bounds the final path plus atomic temp path.
- Compatible old `cache_dir/<safe filename>.pdf` files may be promoted to the new source-specific path only after MD5 and byte verification.
- Candidate writes use the file service’s no-conflicting-replacement behavior; a different artifact at the same case-insensitive destination raises a non-retryable typed error.

- [x] Write failing tests for identical filenames with distinct Drive IDs, changed MD5 content, case-insensitive names, long Unicode/deep roots, compatible legacy replay, and an impossible cache root that performs zero download calls.
- [x] Run the focused candidate/path tests and confirm the new assertions fail for the current filename-only implementation.
- [x] Add only the path-unit/reserved-component helpers needed to calculate a bounded filename budget and retain deterministic compaction.
- [x] Implement source/content-aware candidate naming, legacy MD5-verified promotion, no-clobber writes, and pre-download root validation.
- [x] Rerun the focused tests and confirm cache hits return the correct source-specific artifact without extra Drive work.

### Task 2: Atomic, source-aware OCR chunk artifacts

**Files:**
- Modify: `src/services/_pdf/text.py`
- Test: `tests/test_pdf_text_service.py`

**Interfaces:**
- `split_pdf_for_ocr` continues returning `PdfOcrSplitResponse` with one-based page ranges, ordered chunks, original `source_pdf_path`, and absolute `chunk_pdf_path` values.
- Chunk names retain readable source stems and exact page ranges, add a deterministic source/content identity, and fit the final and temporary path budgets.
- Chunk bytes are generated in memory and committed through `file_service.write_bytes(..., reject_conflicting_existing=True)` so valid same-content replays reuse safely and conflicting artifacts never replace one another.

- [x] Write failing tests for long source stems and deep output roots, case-insensitive collisions, exact page-order/readback, repeated replay, and a conflicting pre-existing chunk.
- [x] Run the focused PDF text tests and confirm the new tests fail because the service currently writes the full stem directly with `open("wb")`.
- [x] Implement root/component validation before PDF processing where possible, deterministic content/path identity, in-memory PDF serialization, and atomic no-conflict publication.
- [x] Rerun the focused PDF tests and inspect every returned chunk with a real PDF reader for page count and sequence.

### Task 3: Bound OCR generator roots and noncached rendered output

**Files:**
- Modify: `src/generators/pdf_text_ocr_generator.py`
- Test: `tests/_test_report_source_generator/cases_01_writes_caches_and_marks_low.py`
- Test: `tests/_test_report_source_generator/cases_02_uses_cached_ocr_pdf_without.py`

**Interfaces:**
- Existing MD5/prompt/model OCR cache keys and cache-hit behavior remain unchanged.
- Cached JSON/PDF paths keep their current normal names when they fit; compact deterministic paths are selected only when the resolved root/atomic temp path requires it.
- Noncached rendered OCR PDFs use a bounded, sanitized, deterministic output filename rather than the unbounded report name.
- Chunk directory components are bounded while preserving source identity through the chunk service’s returned references.

- [x] Add failing generator regressions for long report names, deep cache roots, noncached render paths, existing cache replay, and zero additional OCR/provider calls on a compatible hit.
- [x] Run the focused report-source tests and confirm failure on the current unbounded chunk/render paths.
- [x] Implement bounded path selection and typed impossible-root validation without changing prompt rendering, model routing, cache key fields, or chunk order.
- [x] Rerun generator tests and verify all persisted references point to existing readable artifacts.

### Task 4: Representative evidence, backlog update, and release verification

**Files:**
- Modify: `CONSOLIDATED_TODO.md`
- Modify: `docs/backlog/R-engineering.md`
- Test/verification: focused suites, PDF candidate benchmark, repository quality gates, and a native Windows run when available.

**Interfaces:**
- PATH-03 remains open/Active under R8; only its implementation evidence and residual gaps are updated. PATH-02 wording remains unchanged.

- [x] Run the focused candidate, PDF text, report-source/OCR, file-service, and path utility suites.
- [x] Run the actual representative candidate extraction and OCR split/readback path with isolated artifacts; record exact paths, pages, cache-hit/provider-call evidence, and path measurements.
- [x] Run applicable formatting, Ruff, forbidden-patching, architecture/I/O, contract, test ownership, and type checks; run native Windows tests if the environment supports them.
- [x] Inspect the final diff for scope and secret exposure, record passed/failed/unavailable checks and genuine residual gaps in both canonical backlog locations.
- [ ] Commit the verified branch, push it to `origin`, and report the commit SHA without merging.
