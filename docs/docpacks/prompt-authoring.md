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

The prompt-loading and artifact-generation paths log:

- prompt namespace and file path
- canonical prompt-content identity and dependency counts
- resolved execution identity, provider/model, and bounded model parameters
- rendered-prompt hashes and character counts in dry-run diagnostics

Those operational logs never contain rendered prompt text, source extracts, or
raw model responses. The prompt service records a machine-independent
dependency manifest for every namespace: both YAML roots, ordered included
partials, and schema source files. Its canonical prompt-content identity hashes
that manifest without timestamps or absolute paths. A prompt cache read hashes
each declared dependency, so partial and schema changes invalidate only the
dependent namespace in the running process.

Model-backed artifact cache metadata, prompt-family materialisations, and
provider-accounting metadata also retain the prompt-content identity, manifest,
and an execution identity. The execution identity combines the resolved
provider/model, sampling and token/timeout controls, retrieval mode, routing
and compaction policy, output-contract version, and validator version. A
legacy record remains readable but is not reused when current execution
identity compatibility is required.

`llm_execution_policies` in `src/config/app.yaml` is the canonical typed
provider-call policy inventory. Resolution is exact namespace then longest
approved prefix; provider retries are forbidden there because workflow retry
policy remains orchestrator-owned. Prompt dry-run fixtures render retained
variables but resolve model and temperature through this same runtime policy.
Their old model/temperature fields are descriptive only unless a fixture sets
the explicit `test_only_execution_override` flag.

Legacy `openai_models` entries may still select a more specific model during
the migration, but they inherit every other field from the nearest canonical
execution policy. A model override must therefore never clear its parent
output cap, timeout, structured-output requirement, retrieval mode, or
provenance identity.

Any prompt or schema dependency change should be accompanied by:

- schema compatibility check
- positive-path test
- negative-path test
- cache-invalidation evidence for the affected namespace
