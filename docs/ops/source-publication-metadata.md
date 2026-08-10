# Canonical report-source identity and publication provenance

> **Documentation type:** Current operational reference
> **Canonical topic:** Source publication provenance
> **Update trigger:** Acquisition evidence, persistence contract, rendering policy, or recovery behavior changes.

## Ownership and flow

Reports migration 19 adds an additive evidence model to the existing reports
SQLite database. `SourceIdentityObservation` is an immutable, hash-addressed
observation against an existing `report_sources` row. `SourceIdentityResolution`
is its current deterministic resolution. The old `SourcePublicationMetadata`
record remains the date-extraction input and legacy compatibility boundary; it
is not a substitute for the canonical source identity.

Browser acquisition reads only its terminal HTML snapshot, invokes the
deterministic browser-download service parser, and records a source observation
after a completed download. It stores canonical title and evidence locator,
publisher identifier/name when available, canonical landing/source/artifact
URLs, publication date/status/evidence locator, discovery/retrieval instants,
route, content hash, resolution method/confidence, issues, and supersession
reference. It never stores page text in provenance tables or standard logs.
New observations accept only absolute HTTP(S) URLs; unsafe URLs from historic
rows are suppressed before any public projection.

Drive-sourced reports use the same observation model before cohort admission.
The preflight first looks up the retained `report_sources` record by the PDF's
exact MD5. When no source row exists, it may resolve the canonical title and
publisher from retained `reports` metadata with the same exact MD5 (including
`source_md5`). That compatibility lookup accepts only one non-placeholder,
non-leaked title/publisher pair; conflicting rows fail closed and neither a
title, filename, URL, nor partial publisher match is a lookup key. A non-empty
publisher on a checksum-bound `report_sources` record is promoted to an
immutable `exact_md5_database_record` observation. If no database fallback
resolves identity, the bounded first-pages text sample may contribute one
unambiguous explicit imprint (`Published by`, `A report by`, or copyright
notice) as a `document_imprint_extraction` observation. Filenames, generic
prose, multiple different imprints, and placeholder-like values are never
accepted. Neither fallback invents a landing-page URL.

The current implemented extraction order is JSON-LD `datePublished`, Open
Graph `article:published_time`, named publication-date metadata, then a
semantically marked HTML `time` element. Values are normalized only to the
precision supplied by the source: `YYYY-MM-DD`, `YYYY-MM`, or `YYYY`. The
parser never considers filenames, local timestamps, download time, Drive
timestamps, title text, generic page text, or an LLM.

Observation IDs are stable hashes of the bounded contract. Repeating an exact
observation is idempotent; a contradictory later observation is retained rather
than overwritten. The resolver prefers publisher-verifiable dates, then the
highest confidence evidence, with stable deterministic tie-breakers. A verified
date disagreement makes the resolution `conflicting`, clears its public date,
and retains `publication_date_conflict`. Unknown dates remain `unknown`—they
are never inferred from filenames, timestamps, Drive metadata, generic page
text, or an LLM. Legacy v18 records resolve as `legacy_unverified` until a new
observation is recorded.

The resolution's `source_metadata_hash` covers only public identity/provenance
fields, not observation insertion time. It is persisted on report metadata,
analytics projections, and the report-card manifest. The public package and
WordPress receive only source title, safe URL, publication date, and a short
publisher/title note; evidence locators, confidence, routes, issues, and
retrieval details remain private.

## Rendering and recovery policy

Report generation resolves canonical source identity through
`report_store_service` before rendering. A verified date is the only date
supplied to a report-card manifest. `unknown` and `legacy_unverified` are
rendered without a date, so private report processing remains possible.
Conflicting date provenance is fail-closed at the existing publication-metadata
boundary: it writes durable remediation evidence and prevents public use of an
invented date.

Publisher identity is required for public output; a public publisher URL is
not. When no resolved safe HTTP(S) URL exists, the rendered source section
shows `Source URL: Not available` and contains no original-source anchor. That
disclosure satisfies source-link readiness while retaining the identity and
grounding gates.

The render-only lineage compatibility hash now uses the resolved v19 source
metadata hash, falling back to v18 only for historic rows. A metadata-only
change invalidates rendered HTML and downstream publication only; it does not
require source parsing, OCR, selection, report analysis, artifact generation,
validation, or a provider call.

## Operator validation and rollback

Run the focused checks after a source-provenance change:

```powershell
python -m pytest -q tests/test_source_identity_provenance.py tests/test_source_publication_metadata.py tests/test_report_render_generator_publication_metadata.py tests/test_minimal_execution_planner.py tests/test_wordpress_report_card_contract.py
python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json
```

For a retained browser acquisition, verify the row by source record ID and
status only; do not print captured HTML. The existing `remediation-soak`
command reports any terminal render hold without executing a repair:

```powershell
python -m src.cli remediation-soak
```

The migration is additive: it creates `source_identity_observations` and
`source_identity_resolutions` plus nullable report/projection columns, and
does not rewrite legacy source rows. To disable consumption of resolved
identity while preserving observations, deploy the prior v18-compatible
application revision; it ignores the v19 tables and retains the old bounded
publication behavior. Do not drop v19 tables as part of rollback. To stop a
bad source becoming public, retain the remediation record and correct or
supersede its supporting publisher evidence before a render-only repair.
