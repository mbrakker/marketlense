# Top Failure Runbooks

Last drill date: 2026-04-25
Owner: operations

## `pdf_text_unextractable`

Check whether the PDF is image-only or whether deterministic sample pages missed extractable report content. Confirm `ingest.pdf_text.ocr_fallback.enabled` before rerunning OCR-backed ingestion.

Remediation hook:

```powershell
python -m src.cli ingest --limit 1
```

## `pdf_text_ocr_failed`

Inspect the OCR prompt namespace, OpenAI request logs, timeout settings, and page chunk count. Rerun only after confirming the original PDF is still available and the OCR timeout is not shorter than the service timeout.

Remediation hook:

```powershell
python -m src.cli ingest --limit 1
```

## `browser_download_timeout`

Review the newest `failed_attempt__*.json` forensic pack under the affected browser-download output directory first. Use that bundle's route family, error class, terminal evidence, and retained artifact paths before falling back to publisher route history. Prefer deterministic direct PDF or on-site capture routes when the timeout repeats for the same URL.

Remediation hook:

```powershell
python -m src.cli audit-acquisition-paths --publisher-limit 1 --candidate-limit-per-publisher 1
```

## `publisher_inventory_http_empty`

Confirm the publisher insights URL still exposes an archive or report detail page. If HTTP parsing is structurally empty, run browser discovery and inspect route-quality output before expanding candidate screening.

Remediation hook:

```powershell
python -m src.cli discover-publisher-inventory "https://example.com/insights"
```
