# Acceleration TODOs (Drive List / Ingest / Report Generate)

Status: Completed on 2026-02-04.

Source list (summary)
- Drive list
  - [x] 1) Add `page_size` and cap to limit/batch.
  - [x] 2) Add `order_by=modifiedTime desc` when limit is set.
  - [x] 4) Add metadata-only listing and fetch names only for processed files.
  - [x] 5) Drop unused Drive `version` field.
  - [x] 6) Make `supportsAllDrives` / `includeItemsFromAllDrives` configurable.
  - [x] 7) Support `driveId` + `corpora=drive` for shared drives.
  - [x] 8) Reuse a single Drive client per run.
  - [x] 9) Materialize list (up to limit) before processing.


- Report generate
  - [x] 1) Cache packs/artifacts/validation/html by md5 + prompt/model hash.
  - [x] 2) Cache `pdf_info`, contents detection, text extraction by md5.
  - [x] 3) Reuse `pdf_context` for pdf_info.
  - [x] 7) Reuse cached packs when `vector_store_keep` is true.
  - [x] 9) Disable legacy pack mirroring after migration.


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

7) Reuse cached packs when `vector_store_keep` is true
   - Goal: Avoid re-running vector-store powered LLM steps.
   - Context: Vector store is reused but packs are regenerated.
   - Deliverables:
     - If packs exist on disk for the same md5 and prompt hashes, reuse them.
     - Add clear logging for reuse.
   - Acceptance:
     - Evidence pack generation is skipped on re-run.


9) Disable legacy pack mirroring after migration
   - Goal: Reduce duplicate writes.
   - Context: `report_analysis_store_service` mirrors legacy paths by default.
   - Deliverables:
     - Add config flag to disable legacy mirror.
     - Update callers to pass `mirror_legacy=False` when flag is set.
   - Acceptance:
     - Only one pack write per pack when mirror disabled.
