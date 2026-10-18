# Ingest run artifacts

This archive preserves the five source PDFs admitted by ingest run `d36c4253-46d0-498c-9069-553d61010936` on 2026-10-17 and the complete report artifact directories produced for those sources.

- `sources/` contains byte-for-byte copies of the original PDFs, named by their Google Drive file IDs.
- `reports/` contains full copies of the matching `out/<sha1>-pdf/` directories, including JSON and PNG artifacts.
- `manifest.json` maps each source PDF to its report artifact directory and records hashes, sizes, artifact inventories, and the observed per-source pipeline outcome.

The SHA-1 of each original PDF matches the key in its corresponding report artifact directory. SHA-256 values are also recorded in the manifest for integrity checks. The run admitted and validated all five PDFs, but ended with zero successful pipelines: four report generation failures and one file processing failure. The file processing failure has error code `insight_safe_removal_no_replacement`.
