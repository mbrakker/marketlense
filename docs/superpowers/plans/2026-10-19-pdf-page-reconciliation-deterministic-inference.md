# Deterministic PDF Page Reconciliation Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** Diagnose all 23 unresolved pages in the four committed golden PDFs and implement only deterministic, evidence-supported inference that reduces unresolved coverage without changing correct mappings or activating Phase 2.

**Architecture:** Keep the standalone reconciler in src/services/_pdf/page_reconciliation.py. Reuse its existing candidate, direct-confirmation, sequence, inference, and provenance contracts; do not add OCR, vision, LLM, services, dependencies, downstream consumers, or generic scoring. Real-PDF diagnosis and rendered review are evidence gates before any production behavior change.

**Tech Stack:** Python 3.12, PyMuPDF, pytest, typed dataclass contracts, JSON Schema 1.1, Ruff, mypy, repository architecture/documentation gates, GitHub Actions.

## Global Constraints

- Accuracy is the priority; do not increase coverage by guessing printed page numbers.
- Diagnose all 23 unresolved pages before implementing new inference rules.
- Preserve verified as directly observed visible evidence, inferred as mathematical sequence support, and unresolved as insufficient evidence.
- Preserve fail-closed behavior for strong/weak conflicts, numbering restarts, ambiguous sequences, and PDFs without printed pagination.
- Do not alter DocMap, findings, claim validation, publication, production orchestrators, or any Phase 2 consumer.
- Add no new dependency, service, LLM call, OCR/vision path, or generic scoring system.
- Increment the algorithm version for behavior changes; change the schema version only when the persisted contract shape changes.
- Work on a new clean feature branch based on codex/pdf-page-reconciliation-phase1-corrected; commit and push without merging.
- Update docs/quality/page-reconciliation-pilot.md and the S3 entry in CONSOLIDATED_TODO.md with measured evidence only.

## Files and Responsibilities

- src/services/_pdf/page_reconciliation.py: deterministic candidate confirmation and sequence inference; change only after a failing regression exists.
- src/contracts/pdf_page_reconciliation.py: algorithm version only if inference behavior changes; preserve schema 1.1 unless the contract shape changes.
- src/schemas/pdf_page_reconciliation.schema.json: update the algorithm constant only when the contract validator embeds it; do not alter field shape without a contract requirement.
- tests/test_pdf_page_reconciliation.py: focused synthetic regressions for each inference rule actually accepted by the evidence gate and all preserved fail-closed cases.
- scripts/quality/reconcile_pdf_pages.py: reuse unchanged for fresh, warm-cache, schema, and algorithm-version-bound real-PDF runs.
- docs/quality/page-reconciliation-pilot.md: complete unresolved-page diagnosis, page-level evidence, before/after cohort measurements, hashes, determinism, performance, and verification commands.
- CONSOLIDATED_TODO.md: update only the authoritative S3 status/evidence line; keep Phase 2 blocked.
- docs/superpowers/plans/2026-10-19-pdf-page-reconciliation-deterministic-inference.md: this execution plan and checkpoint record.

### Task 1: Create the clean feature branch and capture the baseline

**Files:**
- Modify: none
- Inspect: AGENTS.md, src/services/_pdf/page_reconciliation.py, src/contracts/pdf_page_reconciliation.py, tests/test_pdf_page_reconciliation.py, docs/quality/page-reconciliation-pilot.md

**Interfaces:**
- Consumes: pushed codex/pdf-page-reconciliation-phase1-corrected at 1687cc1.
- Produces: clean branch codex/pdf-page-reconciliation-deterministic-inference, recorded baseline algorithm pdf-page-reconciliation-v3, schema 1.1, and four fresh baseline JSON outputs.

- [ ] **Step 1: Verify the starting branch is clean and current**

Run:

~~~powershell
git switch codex/pdf-page-reconciliation-phase1-corrected
git status --short --branch
git log -1 --oneline
~~~

Expected: no worktree changes, branch at 1687cc1 or its exact pushed descendant, and no unrelated edits.

- [ ] **Step 2: Create and push the clean feature branch**

Run:

~~~powershell
git switch -c codex/pdf-page-reconciliation-deterministic-inference
git push -u origin codex/pdf-page-reconciliation-deterministic-inference
~~~

Expected: the new branch is based only on the corrected Phase 1 implementation and has no merge commit.

- [ ] **Step 3: Run the focused baseline tests**

Run:

~~~powershell
python -m pytest -q tests/test_pdf_page_reconciliation.py tests/test_pdf_text_service.py tests/test_pdf_contents_service.py tests/test_claim_validation_source_pages.py tests/_test_evidence_pack_generator/cases_05_findings_targeted_retrieval.py
~~~

Expected: the current Phase 1 baseline remains green before any new test or production edit.

- [ ] **Step 4: Run the standalone baseline cohort**

Run the existing CLI with --force for each PDF into a temporary diagnostic directory, then run each once warm without --force:

~~~powershell
python scripts/quality/reconcile_pdf_pages.py --pdf "tests/fixtures/pdf_benchmark/golden/2026_Global_Food_and_Drink_Predictions.pdf" --output-dir "$env:TEMP\marketlense-reconciliation-baseline" --force
python scripts/quality/reconcile_pdf_pages.py --pdf "tests/fixtures/pdf_benchmark/golden/CAPGEMINI - 2026-Retail-Trends_ACIG.pdf" --output-dir "$env:TEMP\marketlense-reconciliation-baseline" --force
python scripts/quality/reconcile_pdf_pages.py --pdf "tests/fixtures/pdf_benchmark/golden/IAS - Industry_Pulse_Report_2026_ACIG.pdf" --output-dir "$env:TEMP\marketlense-reconciliation-baseline" --force
python scripts/quality/reconcile_pdf_pages.py --pdf "tests/fixtures/pdf_benchmark/golden/JULIUS BAER - Secular-outlook-2026_ACIG.pdf" --output-dir "$env:TEMP\marketlense-reconciliation-baseline" --force
~~~

Expected: baseline counts remain 65 verified, 4 inferred, and 23 unresolved across 92 pages; retain JSON hashes and timing/RSS measurements for comparison.

### Task 2: Diagnose every unresolved page before changing inference

**Files:**
- Create: temporary diagnostic/render artifacts outside the repository, removed or ignored after evidence capture
- Modify: none
- Document later: docs/quality/page-reconciliation-pilot.md

**Interfaces:**
- Consumes: baseline JSON mappings and the four committed golden PDFs.
- Produces: a 23-row diagnosis table with physical page, rendered observation, adjacent anchors, expected logical label when calculable, classification, and an explicit recoverability decision.

- [ ] **Step 1: Extract the baseline unresolved-page inventory**

Use the baseline JSON payloads to enumerate every mapping with status == unresolved, preserving report name, physical page, evidence kind/detail, and neighboring mapping statuses/labels.

Expected inventory:

~~~text
Global Food and Drink: physical pages 1-8
Capgemini: physical pages 1 and 15
IAS: physical pages 1 and 8-11
Julius Baer: physical pages 1-2 and 31-36
~~~

- [ ] **Step 2: Render every unresolved page and adjacent anchors**

Use PyMuPDF rendering at a readable resolution, including the full page and a margin-focused crop for each unresolved page plus its nearest verified/inferred neighbors. Use view_image for visual inspection. Record only bounded observations in the evidence table; do not retain raw page text in standard logs.

- [ ] **Step 3: Classify all 23 pages**

Assign exactly one diagnosis to each page:

~~~text
no visible printed pagination
missing number within a consistent sequence
missing number before or after a verified sequence
printed label present but not extracted/recognized
conflicting or ambiguous labels
numbering restart or numbering-system transition
unreadable/image-only page
other with an explicit explanation
~~~

For each row, record neighboring anchors and whether a proposed label would be independently justified. A candidate is recoverable only if the rendered page and surrounding evidence satisfy a deterministic rule without asserting that an inferred label is visibly printed.

- [ ] **Step 4: Decide the implementation gate**

The rendered IAS pages 8-11 are a recoverable extraction case: each visibly shows its printed footer label, but native text blocks either merge the label into a long survey-question line or split the footer marker and numeric token into separate same-baseline blocks. No longer interpolation or boundary extrapolation is justified by the cohort: the other unresolved pages are covers, unnumbered layout pages, document-boundary pages, or weak standalone labels without two-sided direct anchors. Continue only with the bounded footer extraction rule below; do not change the inference gap bound or add extrapolation.

### Task 3: Add tests for the evidence-supported rule before implementation

**Files:**
- Modify: tests/test_pdf_page_reconciliation.py
- Inspect: existing tests for interpolation, Roman/prefixed labels, restarts, conflicts, unnumbered pages, and Capgemini footer/chart disambiguation

**Interfaces:**
- Consumes: the concrete recoverable rule selected by Task 2.
- Produces: failing tests that assert observable status, printed label, anchors, provenance, and preserved fail-closed behavior.

- [ ] **Step 1: Write the failing real-fixture regression for embedded footer labels**

Add a regression against the committed IAS fixture. It must assert that physical pages 8-11 become directly verified labels 8-11, retain visible-footer methods and source geometry, and leave the cover page unresolved:

~~~python
def test_ias_footer_labels_embedded_in_long_text_blocks_are_verified(
    run_context,
) -> None:
    response = reconcile_pdf_pages(
        PdfPageReconciliationRequest(
            schema_version=PDF_PAGE_RECONCILIATION_SCHEMA_VERSION,
            path=(
                "tests/fixtures/pdf_benchmark/golden/"
                "IAS - Industry_Pulse_Report_2026_ACIG.pdf"
            ),
        ),
        run_context,
    )

    assert [response.mappings[page - 1].printed_label for page in range(8, 12)] == [
        "8", "9", "10", "11"
    ]
    assert [response.mappings[page - 1].status for page in range(8, 12)] == [
        "verified", "verified", "verified", "verified"
    ]
    assert all(
        response.mappings[page - 1].method == "visible_footer"
        and response.mappings[page - 1].source_geometry is not None
        for page in range(8, 12)
    )
    assert response.mappings[0].status == "unresolved"
~~~

Add a focused synthetic negative case with a long lower-page chart block containing numeric tokens but no structured footer marker; it must remain unresolved. Keep conflict exclusion, no-pagination, numbering-restart, Roman/prefixed, and Capgemini disambiguation regressions unchanged and green.

- [ ] **Step 2: Run only the new tests and verify RED**

Run:

~~~powershell
python -m pytest -q tests/test_pdf_page_reconciliation.py -k "ias_footer_labels or structured_footer"
~~~

Expected: the IAS fixture test fails because pages 8-11 are still unresolved, and the negative case fails only if the extraction rule is too broad; no production code has changed yet.

### Task 4: Implement the smallest deterministic inference change

**Files:**
- Modify: src/services/_pdf/page_reconciliation.py
- Modify: src/contracts/pdf_page_reconciliation.py only if behavior changes, by incrementing the algorithm version
- Modify: src/schemas/pdf_page_reconciliation.schema.json only if its algorithm constant must match
- Do not modify: public PDF facade, downstream consumers, orchestration, or schema field shape

**Interfaces:**
- Consumes: the failing IAS fixture test and the Task 2 footer-block evidence.
- Produces: directly verified visible-footer mappings for labels that are present in a structured lower-page footer, with existing text-block geometry and no sequence inference change.

- [ ] **Step 1: Implement only the structured footer extraction rule**

Add a private deterministic helper used by _observe_page. It may inspect PyMuPDF text-dictionary lines in the existing page boundary, but it must accept a label only when all conditions hold:

~~~text
the text line is in the existing visible-footer band;
the line contains a report-footer marker followed by | and one positive Arabic label,
or a same-baseline numeric-only line is immediately to the right of a footer-marker line;
the candidate is unique on the page and the footer marker is not a chart/body token;
the candidate detail is bounded and its geometry is the containing source text block.
~~~

Use the existing _parse_label_token and _Candidate contract, mark this structured footer evidence strong, and leave _follows_sequence, _infer_missing_labels, the maximum physical inference gap, boundary extrapolation, restart handling, and conflict handling unchanged. A footer marker without a unique numeric label must remain unresolved.

- [ ] **Step 2: Increment only the algorithm version for behavior changes**

Set PDF_PAGE_RECONCILIATION_ALGORITHM_VERSION to pdf-page-reconciliation-v4 because candidate extraction behavior changes. Update the schema validator algorithm constant while retaining schema 1.1 and its field shape.

- [ ] **Step 3: Run the new tests and full reconciliation tests**

Run:

~~~powershell
python -m pytest -q tests/test_pdf_page_reconciliation.py -k "ias_footer_labels or structured_footer"
python -m pytest -q tests/test_pdf_page_reconciliation.py
~~~

Expected: new cases pass, all prior cases pass, and no test accepts a false verified or inferred label.

### Task 5: Re-run the real PDF cohort and inspect every changed mapping

**Files:**
- Modify: none during measurement
- Evidence: temporary fresh/warm JSON outputs and rendered page images outside the repository

**Interfaces:**
- Consumes: the implementation branch and all four committed golden PDFs.
- Produces: exact before/after mapping diff, page-level visual evidence for every newly inferred page, deterministic hashes, timing/RSS measurements, and a no-regression decision.

- [ ] **Step 1: Run three forced fresh passes and one warm pass per PDF**

Use the standalone CLI and record counts, output hashes, fresh timings, warm timings, and process RSS. Validate every output through the existing schema and algorithm-bound cache path.

- [ ] **Step 2: Compare mapping identity and provenance**

Compare every physical page before/after for printed label, status, method, evidence kind, anchors, geometry, and native metadata. Any previously correct mapping change is a blocker requiring diagnosis and test correction.

- [ ] **Step 3: Render and inspect every newly inferred page**

For each newly inferred page, inspect the full page and neighboring anchors. Record whether the label is visibly confirmed (which would require direct extraction rather than inference), mathematically supported but not visible, or insufficiently supported. Reject any inference that depends on a conflicting label, restart, unrelated sequence, or unreadable evidence.

- [ ] **Step 4: Run the PDF regression suite**

Run:

~~~powershell
python -m pytest -q tests/test_pdf_page_reconciliation.py tests/test_pdf_text_service.py tests/test_pdf_contents_service.py tests/test_claim_validation_source_pages.py tests/_test_evidence_pack_generator/cases_05_findings_targeted_retrieval.py
~~~

Expected: all focused and affected downstream tests pass without changing downstream behavior.

### Task 6: Update evidence, run gates, commit, push, and obtain CI

**Files:**
- Modify: docs/quality/page-reconciliation-pilot.md
- Modify: CONSOLIDATED_TODO.md
- Inspect final diff for scope and secret exposure

**Interfaces:**
- Consumes: diagnosis table, implementation diff, cohort comparison, rendered evidence, deterministic hashes, and validation results.
- Produces: auditable Phase 1 verdict, pushed feature branch, and hosted CI evidence; Phase 2 remains blocked.

- [ ] **Step 1: Update pilot evidence with all 23 diagnoses**

Document the classification and recoverability of every unresolved physical page, exact page-level changes, all newly inferred evidence, unchanged mappings, source hashes, JSON hashes, performance, provenance, and residual limitations. If no new mappings are justified, explicitly record the zero-change outcome and recommendation to retain v3.

- [ ] **Step 2: Update the S3 status entry**

Record the final algorithm version, verified/inferred/unresolved counts, visual-review result, tests/gates, branch commit, and the fact that no Phase 2 downstream consumer changed. Do not mark Phase 2 complete.

- [ ] **Step 3: Run local quality gates**

Run:

~~~powershell
python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
python scripts/ci/check_architecture_imports.py
python scripts/ci/check_role_io_boundaries.py
python scripts/ci/check_service_boundary_map.py
python -m ruff check src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py tests/test_pdf_page_reconciliation.py
python -m ruff format --check src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py tests/test_pdf_page_reconciliation.py
python -m mypy src/contracts/pdf_page_reconciliation.py src/services/_pdf/page_reconciliation.py scripts/quality/reconcile_pdf_pages.py
python -m pytest -q tests/contracts/test_contract_roundtrip.py
python scripts/ci/check_documentation.py --check-generated
git diff --check
~~~

Expected: all applicable gates pass; any skipped gate is reported with the reason.

- [ ] **Step 4: Inspect and commit the final diff**

Run:

~~~powershell
git diff --stat origin/codex/pdf-page-reconciliation-phase1-corrected..HEAD
git diff --check origin/codex/pdf-page-reconciliation-phase1-corrected..HEAD
git status --short --branch
git add src tests docs/quality/page-reconciliation-pilot.md CONSOLIDATED_TODO.md docs/superpowers/plans/2026-10-19-pdf-page-reconciliation-deterministic-inference.md
git commit -m "feat: improve deterministic PDF page inference"
git push
~~~

Expected: only scoped files are committed; no secrets or unrelated changes are present.

- [ ] **Step 5: Wait for exact-SHA hosted CI**

Run:

~~~powershell
gh run list --branch codex/pdf-page-reconciliation-deterministic-inference --limit 3
gh run watch <exact-run-id> --interval 10
~~~

Expected: tests, architecture/documentation/schema gates, both mutation partitions, PDF benchmark evidence, and release evidence pass on the final implementation SHA. Report any pre-existing or unavailable checks separately.

- [ ] **Step 6: Final branch verification**

Run:

~~~powershell
git switch codex/pdf-page-reconciliation-deterministic-inference
git status --short --branch
git log -1 --oneline
git diff --check origin/codex/pdf-page-reconciliation-phase1-corrected..HEAD
~~~

Expected: clean pushed branch, no merge, and a final PASS/FAIL recommendation based on evidence. Stop without implementing Phase 2.

