# PATH-02 Corrective Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Correct the remaining PATH-02 browser artifact identity, retry-safety, idempotence, and destination-containment defects without changing acquisition routing or persisted contracts.

**Architecture:** Keep \`artifact_paths.py\` as the browser-owned path policy boundary. Extend its existing filename and containment logic, add one deterministic URL-specific PDF destination selector, and add one bounded-memory external-materialization routine reused by both adoption entry points. Keep HTTP streaming and PDF validation in the HTTP/PDF service; callers may reuse only identity-specific verified PDFs and may not delete destinations they do not own.

**Tech Stack:** Python 3.12+, pathlib, hashlib, shutil, requests, pytest, native Windows UTF-16 path measurements.

## Global Constraints

- Keep the existing Windows path budgets: 240 UTF-16 code units for full paths and 255 for components.
- Preserve URL normalization, source/provenance fields, cache keys, session identities, route selection, wrapper recovery, PDF validation, and existing result schemas.
- Use existing \`safe_path_segment()\`, \`bounded_artifact_filename()\`, \`AppError\`, and browser path-budget checks.
- Do not add browser visits, LLM calls, network probes, a database/registry, a lock service, a generic transaction framework, or a new storage subsystem.
- Destination paths must remain below their resolved browser output parent; externally supplied source paths may remain outside that root.
- Every behavior change gets a failing regression test before production code; tests assert real filesystem bytes and cleanup effects.
- Keep R8 Active; update only PATH-02 evidence in the canonical backlog documents.

---

### Task 1: Preserve URL identity during filename compaction and enforce destination containment

**Files:**
- Modify: \`src/services/_browser_report_download/artifact_paths.py:_bounded_filename, resolve_browser_artifact_path, validate_browser_artifact_path\`
- Test: \`tests/test_browser_artifact_paths.py\`

**Interfaces:**
- \`_bounded_filename(source_name, extension, identity, force_identity_hash, max_name_units)\` returns a deterministic readable-stem plus 12-hex identity suffix whenever the clean filename is lossy, reserved, explicitly forced, hash-looking with a different identity, or exceeds the available name budget.
- \`validate_browser_artifact_path(path, temporary_suffixes=(), parent_dir=None)\` validates the lexical destination against the resolved intended parent, rejects external final symlinks, and validates final and temporary paths.

- [ ] **Step 1: Write failing identity and containment tests.**

Add tests for two long identical basenames with different URLs, same URL replay, long Unicode names, a literal \`report-<12 hex>.pdf\` versus a generated identity name, and existing/missing external destination symlinks. Assert distinct names, stable replay, full-path and \`.part\` budgets, typed non-retryable errors, and unchanged external bytes.

- [ ] **Step 2: Run the focused tests to verify the defects.**

Run:

\`\`\`powershell
python -m pytest -q tests/test_browser_artifact_paths.py
\`\`\`

Expected: the new long-name identity and symlink-containment tests fail against the current helper.

- [ ] **Step 3: Implement the smallest helper correction.**

Compute the identity digest before compaction, reserve \`-\` plus 12 hexadecimal characters and the extension, truncate only the readable stem, and raise \`browser_download_artifact_path_invalid\` when the suffix cannot fit. Recognize an existing generated suffix only when it matches the supplied identity digest, so a literal hash-looking source name is re-identified instead of impersonating another URL. Pass the resolved intended parent into validation; reject resolved candidates outside it and existing final symlinks that redirect outside it.

- [ ] **Step 4: Run the focused helper tests and existing path tests.**

Run the command from Step 2 and:

\`\`\`powershell
python -m pytest -q tests/test_browser_artifact_paths.py tests/test_browser_capture_paths.py tests/test_browser_profile_paths.py
\`\`\`

Expected: all pass with no directory creation before impossible-root failures.

- [ ] **Step 5: Commit the isolated helper correction.**

\`\`\`powershell
git add tests/test_browser_artifact_paths.py src/services/_browser_report_download/artifact_paths.py
git commit -m "Fix browser artifact identity and containment"
\`\`\`

### Task 2: Make URL-specific PDF destination selection deterministic and reusable

**Files:**
- Modify: \`src/services/_browser_report_download/artifact_paths.py\`
- Modify: \`src/services/_browser_report_download/_browser_runtime/_terminal_assets/artifacts.py:_prefetch_structured_pdf_artifact, _pdf_prefetch_destination_path\`
- Modify: \`src/services/_browser_report_download/_artifact/pdf.py:_try_fetch_pdf_target\`
- Modify: \`src/services/_browser_report_download/_http/pdf_transfer.py:try_direct_pdf_download\`
- Test: \`tests/test_browser_artifact_materialization_paths.py\`
- Test: \`tests/test_browser_pdf_transfer.py\`

**Interfaces:**
- Add \`select_browser_pdf_destination_path(parent_dir, source_name, target_url)\` beside the existing browser path helpers. It returns the normal bounded destination when free; otherwise it returns the deterministic URL-identity destination. It never treats an ordinary occupied basename as source proof.
- All three callers use the same selector and reuse an existing identity-specific regular PDF without another HTTP request. An invalid or ambiguous identity destination remains a failed acquisition, not a successful reuse.

- [ ] **Step 1: Write failing shared-directory prefetch tests.**

Add deterministic tests that stream bytes A from \`https://publisher.example/2025/report.pdf\` and bytes B from \`https://publisher.example/2026/report.pdf\` through structured prefetch in one directory. Assert distinct paths and exact bytes, B replay reuse without a duplicate, and the same behavior for long identical basenames. Add direct/target selection tests proving a normal occupied \`report.pdf\` is not reused for a different URL.

- [ ] **Step 2: Run the new tests to verify wrong-source reuse.**

\`\`\`powershell
python -m pytest -q tests/test_browser_artifact_materialization_paths.py tests/test_browser_pdf_transfer.py
\`\`\`

Expected: the current prefetch returns the first shared \`report.pdf\` or constructs a non-canonical second hash, so the new tests fail.

- [ ] **Step 3: Implement and route the shared selector.**

Use the original URL basename and canonical target URL for both normal and forced-identity candidates. Avoid re-hashing a filename already compacted for that URL. In prefetch, direct download, and target fetch, skip network work only for an existing regular identity-specific PDF; otherwise invoke the existing downloader and preserve provenance as the candidate URL.

- [ ] **Step 4: Run focused materialization and affected acquisition tests.**

\`\`\`powershell
python -m pytest -q tests/test_browser_artifact_materialization_paths.py tests/test_browser_pdf_transfer.py tests/test_browser_report_download_service/_test_prompt_and_probe/cases_04_recovers_embedded_pdf_from_encoded.py tests/test_browser_report_download_service/_test_prompt_and_probe/cases_05_email_gate_and_terminal_results.py tests/test_browser_report_download_service/_test_onsite_and_terminal/cases_02_fetches_relative_observed_pdf_candidate.py
\`\`\`

Expected: all existing wrapper, embedded-PDF, relative-target, fallback-header, and new source-isolation tests pass.

- [ ] **Step 5: Commit the selector correction.**

\`\`\`powershell
git add tests/test_browser_artifact_materialization_paths.py tests/test_browser_pdf_transfer.py src/services/_browser_report_download/artifact_paths.py src/services/_browser_report_download/_browser_runtime/_terminal_assets/artifacts.py src/services/_browser_report_download/_artifact/pdf.py src/services/_browser_report_download/_http/pdf_transfer.py
git commit -m "Prevent browser PDF source aliasing"
\`\`\`

### Task 3: Make PDF transfers and caller failures no-clobber

**Files:**
- Modify: \`src/services/_browser_report_download/_http/pdf_transfer.py:download_pdf_from_url, ensure_downloaded_pdf\`
- Modify: \`src/services/_browser_report_download/_artifact/pdf.py:_try_fetch_pdf_target\`
- Modify: \`src/services/_browser_report_download/_browser_runtime/_terminal_assets/artifacts.py:_prefetch_structured_pdf_artifact\`
- Test: \`tests/test_browser_pdf_transfer.py\`
- Test: \`tests/test_browser_artifact_materialization_paths.py\`

**Interfaces:**
- \`download_pdf_from_url()\` keeps streaming to \`.part\`, deletes only the failed attempt's temporary file, and commits without replacing an unexpected destination. It accepts an explicit same-attempt wrapper-replacement mode used only by \`ensure_downloaded_pdf()\`.
- Caller error handlers no longer unlink final destinations. New invalid output is rejected or removed only when the current attempt demonstrably owns it; competing or pre-existing bytes remain unchanged.

- [ ] **Step 1: Write failing byte-preservation and commit-conflict tests.**

Add tests for a valid existing identity PDF followed by a failing transfer, a valid ordinary PDF occupied by another source, partial \`.part\` cleanup, invalid response content, and a destination appearing immediately before commit. Assert exact old bytes, no final success, cleaned \`.part\`, unchanged competing bytes, and preserved wrapper recovery.

- [ ] **Step 2: Run the tests to verify destructive cleanup.**

\`\`\`powershell
python -m pytest -q tests/test_browser_pdf_transfer.py tests/test_browser_artifact_materialization_paths.py
\`\`\`

Expected: current caller cleanup removes the existing final file or \`Path.replace()\` overwrites the injected competing file, so the new tests fail.

- [ ] **Step 3: Implement staged no-clobber publication.**

Retain the two-header fetch and size limits. Clean \`.part\` in the transfer-level exception path. Publish with the repository’s create-if-absent pattern or an equivalent platform-safe no-clobber operation; raise a typed retryable conflict when a competing destination appears. Allow replacement only for the non-PDF wrapper path owned by the same \`ensure_downloaded_pdf()\` attempt. Remove unconditional final \`unlink()\` calls from the three PDF callers and leave PDF signature/metadata validation authoritative.

- [ ] **Step 4: Run wrapper and PDF validation regressions.**

\`\`\`powershell
python -m pytest -q tests/test_browser_pdf_transfer.py tests/test_browser_report_download_service/_test_prompt_and_probe/cases_04_recovers_embedded_pdf_from_encoded.py tests/test_browser_report_download_service/_test_prompt_and_probe/cases_05_email_gate_and_terminal_results.py
\`\`\`

Expected: all pass with exact recovered PDF bytes and no valid artifact loss.

- [ ] **Step 5: Commit the transfer-safety correction.**

\`\`\`powershell
git add tests/test_browser_pdf_transfer.py tests/test_browser_artifact_materialization_paths.py src/services/_browser_report_download/_http/pdf_transfer.py src/services/_browser_report_download/_artifact/pdf.py src/services/_browser_report_download/_browser_runtime/_terminal_assets/artifacts.py
git commit -m "Preserve browser PDFs across failed transfers"
\`\`\`

### Task 4: Consolidate external artifact adoption and close local-file bypasses

**Files:**
- Modify: \`src/services/_browser_report_download/_artifact/pdf.py:_adopt_external_downloaded_file, _resolve_downloaded_file\`
- Modify: \`src/services/_browser_report_download/_browser_runtime/_terminal_assets/artifacts.py:_copy_external_artifact, _materialize_external_artifacts\`
- Create or modify: shared browser artifact materialization helper under \`src/services/_browser_report_download\`
- Test: \`tests/test_browser_artifact_materialization_paths.py\`
- Test: \`tests/test_browser_artifact_paths.py\`

**Interfaces:**
- One shared \`materialize_external_browser_artifact(source_path, download_dir)\` routine uses bounded-memory byte comparison, deterministic identity/content variants, bounded collision attempts, regular-file checks, temporary staging, and no-clobber publication.
- Both existing callers retain their current names and return types and delegate to that routine. Local browser files are validated for root containment, regular/readable status, and full path budget; an over-budget local file is compacted/copied before it is returned.

- [ ] **Step 1: Write failing idempotence, conflict, and bypass tests.**

Add tests for copying the same PDF twice, two same-basename PDFs with different bytes, replaying both without new destinations, a changed source path preserving the earlier copy, a midway copy failure leaving no partial destination, and a long local browser file being compacted before return. Assert exact bytes, destination counts, root containment, and no false successful result.

- [ ] **Step 2: Run the new materialization tests.**

\`\`\`powershell
python -m pytest -q tests/test_browser_artifact_materialization_paths.py
\`\`\`

Expected: the current implementations create numbered duplicates and return over-budget local paths, so the new tests fail.

- [ ] **Step 3: Implement one shared bounded-memory materializer.**

Compare regular existing files by size and streaming chunks. Use the ordinary filename first, then a source-identity candidate, then a content-aware identity candidate when the same source path changed bytes. Copy to a validated \`.part\` sibling, publish without clobbering a competing destination, clean only attempt-owned temporary files, and return only an existing regular readable file within the validated root.

- [ ] **Step 4: Run materialization, capture, and decomposition tests.**

\`\`\`powershell
python -m pytest -q tests/test_browser_artifact_materialization_paths.py tests/test_browser_capture_paths.py tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_report_download_artifact_decomposition.py
\`\`\`

Expected: existing bounded-path behavior remains green and both adoption entry points now agree on replay semantics.

- [ ] **Step 5: Commit the idempotence and bypass correction.**

\`\`\`powershell
git add tests/test_browser_artifact_materialization_paths.py tests/test_browser_artifact_paths.py src/services/_browser_report_download/_artifact/pdf.py src/services/_browser_report_download/_browser_runtime/_terminal_assets/artifacts.py
git commit -m "Make browser artifact materialization idempotent"
\`\`\`

### Task 5: Reconcile PATH-02 evidence and complete verification

**Files:**
- Modify: \`docs/backlog/R-engineering.md\` PATH-02 evidence only
- Modify: \`docs/backlog/proposal-index.md\` PATH-02 row only
- Modify: \`CONSOLIDATED_TODO.md\` PATH-02 evidence only
- Test: all focused PATH-02 suites and affected browser acquisition suites

- [ ] **Step 1: Run the complete focused verification.**

\`\`\`powershell
python -m pytest -q tests/test_browser_artifact_paths.py tests/test_browser_artifact_materialization_paths.py tests/test_browser_capture_paths.py tests/test_browser_profile_paths.py tests/test_browser_pdf_transfer.py tests/test_browser_report_download_http_decomposition.py tests/test_browser_report_download_artifact_decomposition.py tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_report_download_cdp.py tests/test_browser_report_download_cdp_decomposition.py tests/test_browser_download_helpers.py
python -m pytest -q tests/test_browser_report_download_service/test_onsite_and_terminal.py tests/test_browser_report_download_service/test_browser_preflight.py tests/test_browser_report_download_service/test_rendered_terminal_preflight.py tests/test_browser_report_download_service/_test_worker_and_recovery/cases_03_browser_session_reuse_rejects_cross.py tests/test_browser_report_download_service/_test_worker_and_recovery/cases_04_reuses_bounded_same_publisher_profile.py tests/test_browser_report_download_service/_test_worker_and_recovery/cases_06_worker_execution_and_cleanup.py
\`\`\`

The second command uses the repository’s established \`tests/test_browser_report_download_service\` layout.

- [ ] **Step 2: Run static and contract gates.**

\`\`\`powershell
python scripts/ci/check_formatting.py
python scripts/ci/check_ruff_lint.py
python scripts/ci/check_forbidden_patching.py
python scripts/ci/run_type_check.py
python scripts/ci/check_architecture_imports.py
python scripts/ci/check_role_io_boundaries.py
python scripts/ci/check_service_boundary_map.py
python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
git diff --check
\`\`\`

- [ ] **Step 3: Run the complete pytest suite and retain environment evidence.**

Run \`python -m pytest -q\`. If the CPython-3.12 wheelhouse gate still fails under CPython 3.14.2, do not change dependency or CI logic; report it and use the supported CI environment for that gate if available.

- [ ] **Step 4: Run native Windows byte/path measurements.**

Verify both colliding URL paths, long Unicode names, \`.part\` cleanup, external-copy replay, exact readback bytes, and complete UTF-16 path lengths. Check whether the vendored/live \`browser_use\` runtime is available; if not, report live browser launch as unverified.

- [ ] **Step 5: Inspect scope and update only PATH-02 evidence.**

Review \`git diff --stat\`, \`git diff --check\`, changed-file ownership, and secret exposure. Record root cause, exact changed functions, tests/counts, before/after paths and bytes, native Windows status, remaining risk, corrective commit SHAs, and that R8 remains Active for PATH-03–06.

- [ ] **Step 6: Commit and push the corrective branch without merging.**

\`\`\`powershell
git add src tests docs/backlog/R-engineering.md docs/backlog/proposal-index.md CONSOLIDATED_TODO.md
git commit -m "Correct PATH-02 artifact identity and retry safety"
git push origin codex/path-02-browser-path-hardening
\`\`\`
