# R8 / PATH-02 Browser Artifact Path Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every browser-download artifact, temporary sibling, capture, copied file, and browser profile path deterministic, collision-safe, reopenable, and valid within the conservative Windows path budget before external acquisition work starts.

**Architecture:** Add one private browser artifact-path helper under `src/services/_browser_report_download/` that reuses `safe_path_segment()` and `bounded_artifact_filename()`, measures resolved paths in Windows UTF-16 units, and raises typed non-retryable `AppError` values for impossible destinations. Keep URL identity, session identity, cleanup, route selection, HTTP streaming, PDF validation, and result contracts in their current owners; each producer calls the helper at its existing boundary.

**Tech Stack:** Python, `pathlib`, `hashlib`, `pytest`, existing `AppError`, browser-report private service modules, and repository CI policy scripts.

## Global Constraints

- Preserve the full normalized URL as acquisition identity and retain the existing 12-character normalized-URL hash for ordinary download directories.
- Use the conservative 240-unit full-path budget and Windows UTF-16 code units, plus the 255-unit component budget.
- Reuse `src/utils/path_utils.py`; do not add a storage abstraction, registry, database, lock service, route, prompt, model call, or retry layer.
- Validate before HTTP download, browser construction, browser-agent/model work, profile `mkdir()`, or cleanup of an existing download directory.
- Preserve source URLs, provenance, PDF validation, cache/session reuse, TTL, cross-publisher rejection, cleanup, fallback, and public result schemas.
- Optional missing external attachments may remain unavailable, but an impossible configured path must raise a typed non-retryable error rather than be silently skipped.
- Use approved external-boundary fakes; do not patch private helpers, dataclass constructors, generator internals, or orchestrator internals.
- Do not change PATH-01 mailbox code or implement PATH-03 through PATH-06.

---

### Task 1: Add the browser artifact-path helper and failing unit tests

**Files:**
- Create: `src/services/_browser_report_download/artifact_paths.py`
- Create: `tests/test_browser_artifact_paths.py`
- Modify: `src/utils/path_utils.py` only for a narrowly reusable reserved-name correction

**Interfaces:**
- `windows_path_units(value: str | Path) -> int`
- `resolve_browser_artifact_path(*, parent_dir: Path, source_name: str, extension: str | None = None, identity: str = "", fixed_name: str | None = None, force_identity_hash: bool = False, temporary_suffixes: tuple[str, ...] = ()) -> Path`
- `validate_browser_artifact_path(path: Path, *, temporary_suffixes: tuple[str, ...] = ()) -> Path`
- `validate_browser_profile_path(profile_dir: Path, *, profile_directory: str = "Default", include_session_ledger: bool = False) -> Path`

- [ ] **Step 1: Write failing tests.** Cover short-name preservation, stable replay, Unicode/reserved/trailing-character sanitization, distinct identity hashes, fixed names, component limits, `.pdf.part` budgeting, UTF-16 surrogate counting, and an impossible deep parent that raises non-retryable `AppError` before creating anything. A representative assertion is:

```python
path = resolve_browser_artifact_path(
    parent_dir=tmp_path,
    source_name="report.pdf",
    extension=".pdf",
    identity="https://example.com/report.pdf",
    temporary_suffixes=(".part",),
)
assert path.name == "report.pdf"
assert windows_path_units(path.with_suffix(path.suffix + ".part")) <= 240
```

- [ ] **Step 2: Run the tests red.** Run `python -m pytest -q tests/test_browser_artifact_paths.py`; the failure must be due to the missing helper/behavior, not test syntax.

- [ ] **Step 3: Implement the minimal helper.** Sanitize before calling `bounded_artifact_filename()`. Preserve unchanged short safe ASCII names; append a stable SHA-256 identity digest when sanitization, compaction, or an explicit collision loses identity. Preserve extensions. Calculate the filename budget from the resolved parent and the largest real temporary sibling (for example `report.pdf.part`) in UTF-16 units, enforce 240/255, re-resolve, and verify containment. Derive profile allowance from representative vendored Chromium paths (`Local State`, `Default\Network\Cookies`, `Default\Local Storage\leveldb\LOG`) plus the actual profile name rather than a broad arbitrary constant. Raise actionable non-retryable `AppError` on impossible candidates.

- [ ] **Step 4: Run `python -m pytest -q tests/test_browser_artifact_paths.py tests/test_path_utils.py` and verify green.**

- [ ] **Step 5: Commit after fresh verification:** `git add src/services/_browser_report_download/artifact_paths.py tests/test_browser_artifact_paths.py src/utils/path_utils.py tests/test_path_utils.py; git commit -m "fix(browser): add bounded artifact path policy"`.

### Task 2: Harden the shared browser download directory and host component

**Files:**
- Modify: `src/services/_browser_report_download/request.py:207-235`
- Modify: `tests/test_browser_artifact_paths.py`

**Interfaces:** Keep `resolve_download_dir_path()` and `prepare_download_dir()` signatures unchanged; consume Task 1 validation helpers.

- [ ] **Step 1:** Add failing tests for short-host compatibility (`root/host/sha1[:12]`), long-host compaction, reserved/lossy host hashing, case-insensitive Windows equality, distinct-host isolation, and a deep root that raises before `prepare_download_dir()` deletes a sentinel.
- [ ] **Step 2:** Run `python -m pytest -q tests/test_browser_artifact_paths.py -k "download_dir or host or sentinel"` and confirm the current unbounded construction fails the new cases.
- [ ] **Step 3:** Implement at the owning producer. Keep normalized URL identity and the ordinary URL hash. Build a safe hostname/netloc component; add a deterministic hash of the original hostname whenever sanitization/compaction loses identity. Calculate the complete resolved directory budget including the URL hash, fixed browser outputs, temporary suffixes, and the validated managed-profile allowance. Raise `browser_download_output_dir_invalid` with `next_action` recommending a shorter `output_dir` when the minimum layout cannot fit. Preserve containment and cleanup semantics.
- [ ] **Step 4:** Run `python -m pytest -q tests/test_browser_artifact_paths.py tests/test_browser_report_download_service/test_worker_and_recovery.py` and verify green.
- [ ] **Step 5:** Commit: `git add src/services/_browser_report_download/request.py tests/test_browser_artifact_paths.py; git commit -m "fix(browser): bound download directory paths"`.

### Task 3: Route PDF destinations and external artifact materialization through the helper

**Files:**
- Modify: `src/services/_browser_report_download/_http/pdf_transfer.py`
- Modify: `src/services/_browser_report_download/_artifact/pdf.py`
- Modify: `src/services/_browser_report_download/_browser_runtime/_terminal_assets/artifacts.py`
- Create: `tests/test_browser_artifact_materialization_paths.py`

- [ ] **Step 1:** Write failing tests for long URL basenames, Unicode/query/reserved names, same basename from distinct URLs, `.pdf.part` overflow, HTTP header fallback, wrapper/embedded recovery, exact byte readback, transfer-failure cleanup, identical external basenames, same-file replay, bounded collision variants, non-PDF extension preservation, and impossible-root propagation as `AppError`.
- [ ] **Step 2:** Run `python -m pytest -q tests/test_browser_artifact_materialization_paths.py` and confirm red.
- [ ] **Step 3:** Implement. Route `try_direct_pdf_download()`, `_try_fetch_pdf_target()`, and `_pdf_prefetch_destination_path()` through the helper. Preserve short normalized-URL filenames; use URL identity hashes for lossy/long names and candidate URLs sharing a directory. Validate destination and `.part` inside `download_pdf_from_url()` before the first HTTP call; leave streaming, caps, fallback headers, wrapper detection, and PDF validation unchanged. Use the helper for `_copy_external_artifact()` and `_adopt_external_downloaded_file()`. Check `samefile()` first, then use one bounded deterministic identity-hash collision variant; raise rather than overwrite if that variant is occupied by another source. Do not catch path-budget errors as optional-attachment absence. Verify containment, existence, readability, and exact bytes before returning materialized paths.
- [ ] **Step 4:** Run `python -m pytest -q tests/test_browser_artifact_materialization_paths.py tests/test_browser_pdf_transfer.py tests/test_browser_report_download_http_decomposition.py tests/test_browser_report_download_artifact_decomposition.py` and inspect that no extra HTTP request was introduced.
- [ ] **Step 5:** Commit: `git add src/services/_browser_report_download/_http/pdf_transfer.py src/services/_browser_report_download/_artifact/pdf.py src/services/_browser_report_download/_browser_runtime/_terminal_assets/artifacts.py tests/test_browser_artifact_materialization_paths.py; git commit -m "fix(browser): bound PDF and copied artifact destinations"`.

### Task 4: Bound browser-rendered PDF, on-site capture, and fixed terminal asset names

**Files:**
- Modify: `src/services/_browser_report_download/_browser_runtime/_terminal_assets/capture.py`
- Modify: `src/services/_browser_report_download/_browser_runtime/_terminal_assets/page_state.py`
- Modify: `src/services/_browser_report_download/_artifact/onsite.py`
- Modify: `src/services/_browser_report_download/_http/onsite_capture.py`
- Modify: `src/services/_browser_report_download/browser.py`
- Create: `tests/test_browser_capture_paths.py`

- [ ] **Step 1:** Write failing tests for long final-page stems, similar URL identities, rendered-PDF/HTML/Markdown exact readback, deep roots, fixed compatibility for `browser-route-playbook-rendered.pdf`, `onsite_capture.html`, `onsite_capture.rendered.pdf`, `terminal_snapshot.html`, and `terminal_screenshot.png`, CDP failure, and unchanged provenance/format.
- [ ] **Step 2:** Run `python -m pytest -q tests/test_browser_capture_paths.py` and confirm red.
- [ ] **Step 3:** Implement. Use the helper for URL-derived capture names with final URL identity. Use `fixed_name=` for deterministic playbook, onsite, and terminal names so they are validated rather than renamed. Propagate impossible-root `AppError`; keep unsupported/failed optional capture behavior, CDP calls, PDF validation, source attribution, and returned paths unchanged.
- [ ] **Step 4:** Run `python -m pytest -q tests/test_browser_capture_paths.py tests/test_browser_report_download_service/test_onsite_and_terminal.py tests/test_browser_report_download_runtime_decomposition.py` and verify green.
- [ ] **Step 5:** Commit: `git add src/services/_browser_report_download/_browser_runtime/_terminal_assets/capture.py src/services/_browser_report_download/_browser_runtime/_terminal_assets/page_state.py src/services/_browser_report_download/_artifact/onsite.py src/services/_browser_report_download/_http/onsite_capture.py src/services/_browser_report_download/browser.py tests/test_browser_capture_paths.py; git commit -m "fix(browser): bound capture artifact paths"`.

### Task 5: Validate managed browser and persistent session-reuse profiles before use

**Files:**
- Modify: `src/services/_browser_report_download/_browser_runtime/_session_lifecycle/cleanup.py`
- Modify: `src/services/_browser_report_download/session_reuse.py`
- Modify: `src/services/_browser_report_download/browser.py`
- Create: `tests/test_browser_profile_paths.py`

- [ ] **Step 1:** Write failing tests for normal managed naming/cleanup, deep-root validation before `mkdir()`/browser construction, locked profile cleanup, matching session reuse, cross-publisher rejection, persistent ledger/index readback, failed initialization cleanup, and protection of active/reusable profiles.
- [ ] **Step 2:** Run `python -m pytest -q tests/test_browser_profile_paths.py` and confirm red.
- [ ] **Step 3:** Implement. Validate the complete managed profile path, `Default` profile directory, representative browser descendants, session ledger/index paths, and configured persistent base before profile `mkdir()` or browser construction. Keep the existing cleanup prefix and `_profile_dir_for()` mode/publisher/session hashes. Raise a typed actionable error for an impossible configured base instead of silently relocating it. Preserve TTL, cleanup, scope checks, reuse, and locked-directory behavior.
- [ ] **Step 4:** Run `python -m pytest -q tests/test_browser_profile_paths.py tests/test_browser_report_download_service/test_browser_preflight.py tests/test_browser_report_download_service/test_worker_and_recovery.py` and verify green.
- [ ] **Step 5:** Commit: `git add src/services/_browser_report_download/_browser_runtime/_session_lifecycle/cleanup.py src/services/_browser_report_download/session_reuse.py src/services/_browser_report_download/browser.py tests/test_browser_profile_paths.py; git commit -m "fix(browser): validate profile path budgets before launch"`.

### Task 6: Verify downstream contracts and update canonical evidence

**Files:**
- Modify: `tests/integration/test_browser_report_download_service.py` only for deterministic canonical readback coverage
- Modify: `CONSOLIDATED_TODO.md`
- Modify: `docs/backlog/R-engineering.md`
- Modify: `docs/backlog/proposal-index.md`

- [ ] **Step 1:** Add/update one canonical `download_report_with_browser_use()` regression with controlled HTTP/browser boundaries; assert returned paths exist and reopen exact bytes, source/provenance/route are unchanged, non-PDF content is rejected, and impossible roots fail before boundary calls.
- [ ] **Step 2:** Run `python -m pytest -q tests/test_browser_pdf_transfer.py tests/test_browser_artifact_materialization_paths.py tests/test_browser_capture_paths.py tests/test_browser_profile_paths.py tests/test_browser_report_download_http_decomposition.py tests/test_browser_report_download_artifact_decomposition.py tests/test_browser_report_download_runtime_decomposition.py tests/test_browser_report_download_service tests/integration/test_browser_report_download_service.py`.
- [ ] **Step 3:** Record actual root causes, changed files, compatibility behavior, focused totals, UTF-16 before/after examples, native Windows/browser-runtime availability, and residual risks in all three canonical backlog files. Keep R8 Active while PATH-03..06 remain open; mark PATH-02 verified only for directly evidenced criteria.
- [ ] **Step 4:** Commit: `git add tests/integration/test_browser_report_download_service.py CONSOLIDATED_TODO.md docs/backlog/R-engineering.md docs/backlog/proposal-index.md; git commit -m "docs: record PATH-02 browser path evidence"`.

### Task 7: Run quality gates, inspect scope, and publish the branch

- [ ] **Step 1:** Run `python scripts/ci/check_formatting.py`, `python scripts/ci/check_ruff_lint.py`, `python scripts/ci/check_forbidden_patching.py`, `python -m pytest -q tests/test_long_test_file_ownership.py`, `python scripts/ci/run_type_check.py`, `python scripts/ci/check_architecture_imports.py`, `python scripts/ci/check_role_io_boundaries.py`, `python scripts/ci/check_service_boundary_map.py`, `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json`, and `git diff --check`; run `python -m pytest` when focused checks are green and dependencies are available. Record exact unavailable browser-runtime/native scenarios.
- [ ] **Step 2:** Inspect the complete diff for scope, secrets, duplicate path logic, unchanged public schemas, no extra external calls, and exact measured budgets; distinguish new failures from pre-existing/unavailable checks.
- [ ] **Step 3:** Push with `git status --short --branch`, `git log --oneline --decorate -12`, and `git push -u origin codex/path-02-browser-path-hardening`.
- [ ] **Step 4:** Deliver root cause → fix → evidence for each producer, changed-file list, before/after paths and UTF-16 lengths, test/gate outcomes, compatibility, residual risks, native limitations, and final commit SHA.
