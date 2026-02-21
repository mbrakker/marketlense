# Docpack Prompt Authoring

Prompts for evidence packs live in:

- `src/prompts/report_vs/evidence_packs/*/system.yaml`
- `src/prompts/report_vs/evidence_packs/*/user.yaml`

## Required Prompt Contract

Each pack prompt must explicitly define:

- required output fields
- allowed null/empty behavior
- evidence ID requirements
- minimum item counts where applicable
- strict JSON object response requirement

## Authoring Rules

- Keep format instructions schema-aligned with the target `src/schemas/*.schema.json`.
- Use stable field names that match typed contracts in `src/contracts/docpacks.py`.
- Avoid ambiguous free-form instructions for required structured fields.
- Keep retrieval context references explicit (do not invent source IDs).

## Logging and Reproducibility

Generators log:

- prompt namespace and file path
- prompt hashes
- rendered system prompt
- rendered user prompt
- model parameters
- raw model response

Any prompt change should be accompanied by:

- schema compatibility check
- positive-path test
- negative-path test
