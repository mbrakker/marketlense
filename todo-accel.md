# Acceleration TODOs (Drive List / Ingest / Report Generate)

Source list (summary)
- Drive list
  - 1) Add `page_size` and cap to limit/batch.
  - 2) Add `order_by=modifiedTime desc` when limit is set.
  - 3) Add `modified_after` cutoff from last successful ingest.
  - 4) Add metadata-only listing and fetch names only for processed files.
  - 5) Drop unused Drive `version` field.
  - 6) Make `supportsAllDrives` / `includeItemsFromAllDrives` configurable.
  - 7) Support `driveId` + `corpora=drive` for shared drives.
  - 8) Reuse a single Drive client per run.
  - 9) Materialize list (up to limit) before processing.
  - 10) Stop paging when `modifiedTime <= last_run`.
- Ingest
  - [x] 1) Skip download/EOF/hash when state already has md5.
  - [x] 2) Cache by `file_id` (not name).
  - [x] 3) Add md5 sidecar/state to avoid rehash.
  - [x] 4) Skip EOF checks on cache hits.
  - [x] 5) EOF check should read only tail bytes.
  - [x] 6) Stream download to disk + md5 while streaming.
  - [x] 7) If Drive md5 matches cached, skip `file_md5`.
  - [x] 8) Skip report generation if HTML exists for same md5.
  - [x] 10) Add `file_stat` service for exists+size+mtime(+md5).
- Report generate
  - 1) Cache packs/artifacts/validation/html by md5 + prompt/model hash.
  - 2) Cache `pdf_info`, contents detection, text extraction by md5.
  - 3) Reuse `pdf_context` for pdf_info.
  - 4) Skip candidate gallery crops unless debug.
  - 5) Cap ranker candidates with heuristics.
  - 6) Skip cover image if already up-to-date.
  - 7) Reuse cached packs when `vector_store_keep` is true.
  - 8) Sample text before full extract; skip if none.
  - 9) Disable legacy pack mirroring after migration.
  - 10) Make contents preview optional / lower DPI if unused.

Expanded tasks (use as Codex prompts)

Drive list
1) Add configurable page size for Drive list
   - Goal: Reduce Drive API pagination overhead when a batch limit is used.
   - Context: `list_pdfs` does not set `pageSize`, so Drive defaults are used.
   - Deliverables:
     - Extend `DriveListRequest` to include `page_size: Optional[int]`.
     - In `drive_service.list_pdfs`, pass `pageSize` to `files().list(...)`.
     - In `ingest_orchestrator.run_ingest`, set `page_size=min(limit or settings.batch_limit, 1000)` when limit is set.
     - Update config docs if needed (optional, but keep settings centralized).
   - Acceptance:
     - Listing a limited batch uses fewer pages (logged or validated via tests).

2) Add order_by=modifiedTime desc for limited runs
   - Goal: Ensure the first page contains the most recent PDFs when limiting.
   - Context: Limit truncates after N items, but Drive order is undefined.
   - Deliverables:
     - Add `order_by` to `DriveListRequest` (optional string).
     - Pass `orderBy` to Drive list when `limit` is provided.
     - Default behavior unchanged when no limit.
   - Acceptance:
     - Logs show `orderBy=modifiedTime desc` for limited runs.

3) Add modified_after cutoff using state DB
   - Goal: Avoid scanning older files already processed.
   - Context: Ingest has state DB but list doesn’t filter by last run.
   - Deliverables:
     - Add a state lookup for last successful ingest timestamp.
     - Extend `DriveListRequest` with `modified_after` and add to Drive query.
     - Store updated "last_successful_ingest_utc" on successful completion.
   - Acceptance:
     - List query includes a `modifiedTime > ...` clause when available.

4) Add metadata-only list mode
   - Goal: Reduce payload size by omitting unused fields.
   - Context: `version` and sometimes `name` are not always required.
   - Deliverables:
     - Add a `list_mode` enum or boolean flag to `DriveListRequest`.
     - Implement `fields` selection based on mode.
     - Fetch `name` only for items that will be processed.
   - Acceptance:
     - Drive response fields shrink in metadata-only mode (logs).

5) Drop unused Drive `version` field
   - Goal: Reduce response size and eliminate unused data.
   - Context: `DriveFile.version` is not used downstream.
   - Deliverables:
     - Remove `version` from `DriveFile` dataclass.
     - Remove `version` from Drive list `fields`.
     - Update any downstream mapping/tests.
   - Acceptance:
     - No references to `DriveFile.version` remain.

6) Make supportsAllDrives / includeItemsFromAllDrives configurable
   - Goal: Avoid extra search scope when not needed.
   - Context: Listing non-shared drives still sets shared drive flags.
   - Deliverables:
     - Add config flags under `ingest` for `supports_all_drives` and `include_items_from_all_drives`.
     - Pass flags to `drive_service.list_pdfs`.
     - Default behavior preserved (current values).
   - Acceptance:
     - Config values are logged and honored in list calls.

7) Support shared drive scoping (driveId + corpora)
   - Goal: Reduce search scope and latency for shared drives.
   - Context: Drive API supports `driveId` + `corpora="drive"`.
   - Deliverables:
     - Add optional `drive_id` to config and `DriveListRequest`.
     - If `drive_id` present, set `corpora="drive"` and `driveId`.
   - Acceptance:
     - Logs show `driveId` used when configured.

8) Reuse a single Drive client per run
   - Goal: Avoid re-auth overhead for list + download.
   - Context: `drive_service` builds a new client per call.
   - Deliverables:
     - Add a simple client cache keyed by `sa_path`.
     - Ensure reuse for both list and download in the same run.
   - Acceptance:
     - Client creation logged once per run for a given SA path.

9) Materialize list up to limit before processing
   - Goal: Ensure `drive_list` timing reflects actual list work.
   - Context: Generator completion currently spans the entire ingest loop.
   - Deliverables:
     - Collect up to `max_n` files into a list before the per-file loop.
     - Keep generator semantics inside service; materialize in orchestrator.
   - Acceptance:
     - `drive_list` timing only covers list API calls.

10) Stop paging once `modifiedTime <= last_run`
   - Goal: Short-circuit listing once older files appear.
   - Context: When ordered desc, older pages are not needed.
   - Deliverables:
     - With `orderBy` and `modified_after`, stop page iteration once
       `modifiedTime <= modified_after`.
     - Add log event for early stop.
   - Acceptance:
     - Page loop terminates early when cutoff is reached.

Ingest
1) Skip download/EOF/hash when state already has md5 (DONE)
   - Goal: Avoid unnecessary I/O when file already processed.
   - Context: `_should_skip` is called after cache/EOF checks.
   - Deliverables:
     - If `file.md5_checksum` exists, check state immediately.
     - Skip download/EOF/hash if state shows processed with same md5.
     - Keep behavior unchanged when md5 is missing.
   - Acceptance:
     - Previously processed files do not trigger download logs.

2) Cache by `file_id` instead of file name (DONE)
   - Goal: Prevent cache misses on renamed files.
   - Context: Cache path uses `safe_pdf_name(file.name)`.
   - Deliverables:
     - Update cache filename to include `file_id` (e.g., `{file_id}.pdf`).
     - Optionally keep name in a sidecar for readability.
   - Acceptance:
     - Renaming a Drive file does not trigger re-download.

3) Add md5 sidecar/state to avoid rehash (DONE)
   - Goal: Avoid expensive `file_md5` on every run.
   - Context: Cache hit still computes md5 if file exists.
   - Deliverables:
     - Store md5 in a sidecar file (e.g., `.md5`) or in state DB keyed by
       `file_id + cache_path + size + mtime`.
     - When sidecar matches file size+mtime, skip hashing.
   - Acceptance:
     - Cache hits avoid `file_md5` unless file changed.

4) Skip EOF checks on cache hits (DONE)
   - Goal: Reduce extra file reads when cache is valid.
   - Context: EOF check reads the full file even on cache hits.
   - Deliverables:
     - Only run EOF check when a fresh download occurs.
     - If cached file fails EOF check, re-download once.
   - Acceptance:
     - Cache hit path has no EOF read logs.

5) EOF check should read only tail bytes (DONE)
   - Goal: Reduce I/O for large PDFs.
   - Context: `check_pdf_eof` reads entire file bytes.
   - Deliverables:
     - Change `pdf_service.check_pdf_eof` to read only last N bytes (2048).
     - Keep semantics intact (`%%EOF` detection).
   - Acceptance:
     - File read in EOF check is O(tail bytes), not full size.

6) Stream download to disk + md5 while streaming (DONE)
   - Goal: Avoid buffering large files in memory and rehashing.
   - Context: Download reads into memory then writes and hashes.
   - Deliverables:
     - Add a new `drive_service.download_pdf_to_path` that streams to disk.
     - Compute md5 incrementally during streaming.
     - Update ingest to use streaming path, returning size+md5.
   - Acceptance:
     - Download does not allocate full file in memory.

7) If Drive md5 matches cached, skip `file_md5` (DONE)
   - Goal: Use Drive checksum to avoid local hash.
   - Context: `file_md5` is invoked even when Drive md5 exists.
   - Deliverables:
     - If cached file exists and Drive md5 exists, compare using sidecar or
       (if sidecar missing) compute once and store.
   - Acceptance:
     - `file_md5` logs appear only when Drive md5 is missing or sidecar absent.

8) Skip report generation if HTML exists for same md5 (DONE)
   - Goal: Avoid re-generating reports already rendered.
   - Context: Some state rows may be missing; HTML already exists.
   - Deliverables:
     - Add report metadata lookup by `file_id` + `md5`.
     - If HTML path exists and md5 matches, return `IngestOutcome` as skipped.
   - Acceptance:
     - Re-ingest does not regenerate unchanged reports.


10) Add `file_stat` service (exists + size + mtime + optional md5) (DONE)
   - Goal: Reduce multiple file open/stat operations.
   - Context: `file_exists` + `file_md5` are separate calls.
   - Deliverables:
     - Add `FileStatRequest/Response` in contracts.
     - Implement in `file_service` and update ingest to use it.
   - Acceptance:
     - Ingest uses a single stat call per cached file.

Report generate
1) Cache packs/artifacts/validation/html by md5 + prompt/model hash
   - Goal: Skip expensive LLM calls when inputs are unchanged.
   - Context: Evidence packs and artifacts are re-generated every run.
   - Deliverables:
     - Store cache keys in state or analysis store metadata
       (`md5 + prompt hashes + model + settings`).
     - If cache hit, load JSON packs and skip model calls.
   - Acceptance:
     - Logs show cache hits and skipped model calls on re-run.

2) Cache `pdf_info`, contents detection, text extraction by md5
   - Goal: Avoid repeated PDF parsing.
   - Context: `extract_pdf_info` and text operations run every time.
   - Deliverables:
     - Add cache files under `cache_dir` keyed by md5.
     - Short-circuit PDF service calls when cache exists.
   - Acceptance:
     - Re-ingest uses cached PDF info/text logs.

3) Reuse `pdf_context` for pdf_info
   - Goal: Avoid opening PDF multiple times.
   - Context: `extract_pdf_info` opens a new reader even when context exists.
   - Deliverables:
     - Allow `PdfInfoRequest` to accept an optional `pdf_context`.
     - Use existing `pypdf_reader` when available.
   - Acceptance:
     - Single PDF open per report generation path.

4) Skip candidate gallery crops unless debug enabled
   - Goal: Reduce image cropping time and disk I/O.
   - Context: All candidate crops are generated even if unused.
   - Deliverables:
     - Add a config flag (e.g., `ingest.debug_candidate_gallery`).
     - Only crop full candidate set when flag is true.
   - Acceptance:
     - Default path crops only top items used in output.

5) Cap ranker candidates with heuristics
   - Goal: Reduce prompt size and model latency.
   - Context: Ranker processes all candidates.
   - Deliverables:
     - Add a pre-filter (e.g., limit by page range or candidate count).
     - Document heuristic in code and logs.
   - Acceptance:
     - Ranker receives no more than configured max candidates.

6) Skip cover image generation if already up-to-date
   - Goal: Avoid re-rendering identical cover images.
   - Context: Cover images are generated every time.
   - Deliverables:
     - Add a cache key from cover inputs (title, publisher, categories, style).
     - Skip generation if output exists and cache key matches.
   - Acceptance:
     - Cover generation logs show cache hits.

7) Reuse cached packs when `vector_store_keep` is true
   - Goal: Avoid re-running vector-store powered LLM steps.
   - Context: Vector store is reused but packs are regenerated.
   - Deliverables:
     - If packs exist on disk for the same md5 and prompt hashes, reuse them.
     - Add clear logging for reuse.
   - Acceptance:
     - Evidence pack generation is skipped on re-run.

8) Sample text before full extract
   - Goal: Avoid full text extraction when PDF is not extractable.
   - Context: Full extract happens before sample validation.
   - Deliverables:
     - Move `sample_pdf_text` before `extract_pdf_text`.
     - If sample indicates no text, skip full extract.
   - Acceptance:
     - Non-text PDFs do not run full extraction.

9) Disable legacy pack mirroring after migration
   - Goal: Reduce duplicate writes.
   - Context: `report_analysis_store_service` mirrors legacy paths by default.
   - Deliverables:
     - Add config flag to disable legacy mirror.
     - Update callers to pass `mirror_legacy=False` when flag is set.
   - Acceptance:
     - Only one pack write per pack when mirror disabled.

10) Make contents preview optional / lower DPI if unused
   - Goal: Reduce image rendering time.
   - Context: Contents preview rendered even if not required by templates.
   - Deliverables:
     - Add config flags `contents_preview_enabled` and `contents_preview_dpi`.
     - Skip preview rendering when disabled.
   - Acceptance:
     - No preview render logs when disabled; report still generates.
