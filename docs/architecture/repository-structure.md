# Repository Structure

> **Documentation type:** Current reference
> **Canonical topic:** Repository structure
> **Update trigger:** Top-level layout or canonical entrypoint changes.

| Path | Responsibility |
| --- | --- |
| `src/contracts/` | Versioned dataclass contracts and schema-facing models |
| `src/services/` | Canonical external-system and I/O boundaries |
| `src/generators/` | Domain assembly and validation logic |
| `src/orchestrators/` | Workflow sequencing, retry, state, and idempotency |
| `src/prompts/` | Use-case-scoped prompt namespaces |
| `src/playbooks/` | Reviewable, file-based browser-route guidance and related runtime playbook assets |
| `src/_cli/` and `src/cli.py` | CLI command families and public CLI facade |
| `src/ui/` and `src/streamlit_app.py` | Operator UI and its presentation layer |
| `src/config/` | Versioned non-secret configuration and configuration assets |
| `src/schemas/` | JSON schemas for persisted and generated artifacts |
| `src/utils/` | Deterministic, side-effect-free helpers shared across architectural roles |
| `scripts/ci/` | Repository and quality gates |
| `scripts/quality/` | Evidence, benchmark, and quality tooling |
| `Wordpress/` | Theme, plugin, and WordPress operational scripts |
| `docs/` | Canonical human and generated documentation |

Large public modules may remain compatibility facades over private, capability-scoped implementation packages in the same bounded context. The facade is the discoverable import surface; private implementation modules are not alternative public entrypoints.
