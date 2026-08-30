# Docpack Specs

Docpack payloads are stored under:

- `out/<report-slug>/report_analysis/*.json`

Typed contracts live in:

- `src/contracts/docpacks.py`

## Core Packs

- `doc_map` -> schema: `src/schemas/doc_map.schema.json`
- `scope` -> schema: `src/schemas/scope_pack.schema.json`
- `methods` -> schema: `src/schemas/methods_pack.schema.json`
- `findings` -> schema: `src/schemas/findings_pack.schema.json`
- `limitations` -> schema: `src/schemas/limitations_pack.schema.json`
- `quote_candidates` -> schema: `src/schemas/quote_candidates_pack.schema.json`
- `artifacts` -> schema: `src/schemas/artifacts.schema.json`
- `validation` -> schema: `src/schemas/validation_report.schema.json`

## Registry

- Registry key: `ingest.evidence_packs.registry`
- Strict schema flag: `analysis.strict_schema_validation`

`doc_map` is always enforced as the first pack step.

After a usable `doc_map` is generated, the existing single `findings` pack call
receives a compact JSON projection of its major sections (`id`, `title`,
`summary`, `key_points`, and `pages`). This guides evidence retrieval across
report themes without adding per-section model calls. The projection is planning
context only: each finding remains grounded in file-search evidence.

`doc_map.sections[]` requires:

- `id`
- `title`
- `summary` (brief section synopsis)
- `key_points` (array of concise supporting bullets; may be empty when source is sparse)

`findings.findings[]` retains its existing `id`, `text`, `evidence`,
`confidence`, and `pages` fields. It may additionally link a grounded finding
to the supplied DocMap with optional `section_id` and `section_title`. These
links are additive, so legacy retained findings packs remain schema-valid.

The production registry has one representative-evidence path. Its final
insights retain source-backed metrics, priority moves, and counter-signals;
artifact assembly deterministically projects those supported fields into the
metric spine, recommendation, and risk outputs. It does not schedule separate
key-metric, recommendation, risk-register, or contradiction model families.
Retained artifacts that cite IDs from those retired families remain readable for
validation and replay only; this compatibility path never schedules or
normalizes a retired family for new reports.

Schema validity alone does not make a `doc_map` usable. Before a map can advance
generation or be reused from cache, the generator verifies that it has at least
one subject-specific section and source-derived narrative terms. Runtime control
metadata—such as report, vector-store, or pack identifiers; file names; field
labels; and metadata-only prose—does not count as document content. A failed
check is rejected for bounded structured-output recovery (or cache regeneration)
without any publisher-specific allowlist.

## Referential Integrity

Cross-pack checks require `artifacts` evidence references to resolve to known IDs extracted from:

- `doc_map.sections[].id`
- `findings.findings[].id`
- `quote_candidates.quote_candidates[].id`
- IDs in retained specialist-family payloads, when replaying an artifact created
  before those families were retired

`artifacts.toc_entries[]` is the authoritative Covered topics structure, deterministically derived from eligible `doc_map.sections[]`, with:

- `section_id`
- `section_title`
- `display_title`
- `summary`
- `key_points`
- `pages`
- `order`

`artifacts.toc_topics[]` is a legacy compatibility projection derived from `toc_entries[].display_title`.

`artifacts.toc_topics_expanded[]` is a legacy enriched projection derived from `toc_entries[]`, with:

- `topic`
- `summary`
- `key_points`
- `section_id`
- `section_title`
- `pages`
