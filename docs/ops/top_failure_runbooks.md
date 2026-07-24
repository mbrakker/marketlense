# Top Failure Runbooks

> **Documentation type:** Operational procedure
> **Canonical topic:** Typed failure runbooks
> **Update trigger:** Failure code, drill, alert label, or remediation command changes.

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
## Failure-specific checkpoint recovery

Use `python -m src.cli remediations` to inspect the durable row, then run
`python -m src.cli remediation-reap` only when
`workflow_control.remediation_reaper.execution_enabled` is explicitly enabled.
The reaper accepts no untyped or proof-free restart and consumes one durable
attempt only.

| Failure code | Safe recovery | Never do |
| --- | --- | --- |
| `taxonomy_invalid_json`, `taxonomy_schema_invalid` | Resume after the retained `selection_complete` checkpoint; reuse source PDFs and the existing vector store. | Reparse the source or create another vector store. |
| `category_fit_contradiction` | Resume category-fit work from retained selection/vector evidence. | Regenerate unrelated editorial families. |
| `unsupported_material_claim` | Regenerate the independently materialized affected insights/claim family, run its required validation, then render. | Broadly regenerate taxonomy, evidence packs, or unrelated artifacts. |
| `final_html_internal_identifier` | Rerender and revalidate from `analysis_complete`. | Call an LLM, parse a PDF, or publish. |
| `missing_report_card_manifest` | Rebuild card assets/manifest from `analysis_complete`, then render validation. | Re-run source/analysis/model work. |
| `wordpress_readback_failed` | Perform the authenticated GET-only post lookup/reconciliation. | Repeat a WordPress write. |

If checkpoint lineage, artifact references, admission identity, budget, or the
one-attempt bound cannot be proven, the row is held or terminates with its
typed fallback. Preserve the row; do not edit its checkpoint or reset attempts.
