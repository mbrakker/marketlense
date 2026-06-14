# Simplification Audit: 2026-06-14

This audit closes the investigation-only effort-under-four items from
`simplification.md`. It records the evidence checked, the removal decision,
the operational risk, the owner, and the next review date.

## WordPress Legacy Migrations

- Evidence: the configured WordPress REST site was provisioned successfully on
  2026-06-14; repository code still registers the June 6 header override
  migration and June 7 site identity/public discovery migrations.
- Decision: retain.
- Reason: WordPress REST does not expose the migration option values used to
  prove every deployed install completed these migrations. Removing the hooks
  would make older installs permanently miss the one-time correction.
- Owner: WordPress deployment maintainers.
- Next review: 2026-09-14, after deployment inventory confirms all sites have
  the migration option values.

## Theme CSS

- Evidence: `theme.css` contains 1,611 selector blocks. Its root token layer
  already aliases WordPress color, type, radius, shadow, spacing, card, chip,
  focus, and transition tokens. Literal `#fff` remains common, but its uses
  include foreground text, gradients, and compositing where mechanical
  replacement would change semantics.
- Decision: retain selectors and literals.
- Reason: no selector has both zero template/PHP references and a visual
  screenshot baseline proving safe removal. Token extraction without that
  evidence would create churn rather than reduce coupling.
- Owner: WordPress theme maintainers.
- Next review: 2026-09-14 with an approved page screenshot corpus.

## Compatibility Exports

- Evidence: compatibility facades remain for Streamlit pages, report source
  generation, publisher inventory, browser download, PDF crop/visual/table
  capabilities, config capabilities, and service facades. Decomposition tests
  explicitly assert several of these surfaces.
- Decision: retain.
- Reason: repository import search cannot prove external consumers do not use
  public facade names. Removing them would be a public API migration.
- Owner: repository maintainers.
- Next review: 2026-09-14 after public import ownership is documented.

## Feature And Rollout Controls

- Evidence: publisher discovery controls for deferred recovery, structured
  route reuse, preflight/direct-detail routing, candidate screening, candidate
  quality checks, and resource-quality ranking default on and are logged by the
  orchestrator. Browser session reuse defaults off and supports bounded canary
  and same-publisher modes.
- Decision: retain.
- Reason: these flags select materially different operational and failure
  behavior; they are not expired default-on aliases. No production usage
  telemetry proves a removable branch.
- Owner: acquisition workflow maintainers.
- Next review: 2026-09-14 with usage counts per flag.

## Legacy Data Adapters

- Evidence: analysis-store positional compatibility is covered by dedicated
  tests; render normalization still accepts legacy `figure` and `quote`
  payloads; report-store serializers and route lookup normalize persisted
  historical records; WordPress supports legacy report markup and metadata.
- Decision: retain.
- Reason: existing persisted fixtures exercise these shapes. Removal requires a
  migration and fixture inventory, not a code-only deletion.
- Owner: report persistence maintainers.
- Next review: 2026-09-14 after persisted-state migration metrics exist.

## Prompt And Model Configuration

- Evidence: ten generator modules use `prepare_prompt_bundle`, which owns prompt
  loading, rendering, and longest-prefix model resolution. Evidence-pack
  strategies preserve use-case-local namespaces. Specialized OCR, cache-key,
  figure-caption, and crop-refine paths call `resolve_model` where they do not
  own a complete prompt-render operation.
- Decision: no further centralization.
- Reason: moving namespace declarations into one registry would violate
  use-case-local prompt ownership; wrapping pure model lookup would add
  pass-through indirection.
- Owner: model pipeline maintainers.
- Next review: 2026-09-14 during the next prompt logging audit.
