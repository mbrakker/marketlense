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

## Variety Packs

- `key_metrics` -> schema: `src/schemas/key_metrics_pack.schema.json`
- `risk_register` -> schema: `src/schemas/risk_register_pack.schema.json`
- `recommendations` -> schema: `src/schemas/recommendations_pack.schema.json`
- `contradictions` -> schema: `src/schemas/contradictions_pack.schema.json`

## Registry and Feature Flags

- Registry key: `ingest.evidence_packs.registry`
- Variety flag: `ingest.evidence_packs.enable_new_variety_packs`
- Strict schema flag: `analysis.strict_schema_validation`

`doc_map` is always enforced as the first pack step.

`doc_map.sections[]` requires:

- `id`
- `title`
- `summary` (brief section synopsis)
- `key_points` (array of concise supporting bullets; may be empty when source is sparse)

## Referential Integrity

Cross-pack checks require `artifacts` evidence references to resolve to known IDs extracted from:

- `doc_map.sections[].id`
- `findings.findings[].id`
- `quote_candidates.quote_candidates[].id`
