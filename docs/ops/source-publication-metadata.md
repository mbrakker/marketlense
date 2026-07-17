# Source-supported publication metadata

> **Documentation type:** Current operational reference
> **Canonical topic:** Source publication provenance
> **Update trigger:** Acquisition evidence, persistence contract, rendering policy, or recovery behavior changes.

## Ownership and flow

The canonical record is `SourcePublicationMetadata` in the report-store
contract family. Browser acquisition reads only the existing terminal HTML
snapshot, invokes the deterministic browser-download service parser, and
persists the bounded provenance against the existing `report_sources` row in
the reports SQLite database. It never stores page text in the provenance row
or standard logs.

The current implemented extraction order is JSON-LD `datePublished`, Open
Graph `article:published_time`, named publication-date metadata, then a
semantically marked HTML `time` element. Values are normalized only to the
precision supplied by the source: `YYYY-MM-DD`, `YYYY-MM`, or `YYYY`. The
parser never considers filenames, local timestamps, download time, Drive
timestamps, title text, generic page text, or an LLM.

The record retains the source URL, retrieval instant, extraction kind and
locator, SHA-256 of the observed value, status, contradiction state, and all
bounded observations. Repeating the same observation is idempotent. A valid
observation remains selected over a weaker unknown or invalid observation;
incompatible valid values are retained and set `conflicting` rather than being
silently replaced.

## Rendering and recovery policy

Report generation resolves this record through `report_store_service` before
rendering. A verified date is the only date supplied to a report-card manifest.
`unknown` and `legacy_unverified` are rendered without a date, so private
report processing remains possible. `invalid` and `conflicting` provenance
raises `source_publication_metadata_not_renderable`; the existing
report-generation terminal failure boundary writes the durable remediation
record and prevents public use of an invented date.

The render-only lineage compatibility hash includes the full persisted
publication provenance. Changing it invalidates rendered HTML and downstream
publication only; it does not require source parsing, OCR, selection, report
analysis, artifact generation, validation, or a provider call.

## Operator validation and rollback

Run the focused checks after a source-provenance change:

```powershell
python -m pytest tests/test_source_publication_metadata.py tests/test_report_render_generator.py tests/test_minimal_execution_planner.py
python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
```

For a retained browser acquisition, verify the row by source record ID and
status only; do not print captured HTML. The existing `remediation-soak`
command reports any terminal render hold without executing a repair:

```powershell
python -m src.cli remediation-soak
```

The migration is additive. A rollback to an earlier application revision
leaves the provenance table unused without rewriting legacy records. To stop a
bad source from becoming public, retain the resulting remediation record and
correct or remove the supporting publisher evidence before a render-only
repair.
