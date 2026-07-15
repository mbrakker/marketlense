# Configuration

> **Documentation type:** Operational procedure
> **Canonical topic:** Runtime configuration
> **Update trigger:** Configuration resolution, operator-facing setting, or configuration asset changes.

`src/config/app.yaml` holds committed, environment-neutral defaults. `src/config/app.example.yaml` is the starter overlay for environment-specific settings. Do not place secrets in either file.

Configuration resolves in this order:

1. `src/config/app.yaml`, unless `MARKET_LENSE_CONFIG_PATH` selects another base file.
2. `app.<profile>.yaml` next to the selected `app.yaml` when `MARKET_LENSE_CONFIG_PROFILE` is set.
3. `app.local.yaml` next to the selected `app.yaml`, when present.
4. Environment variables where the configuration loader supports an override.

The important operator sections are `paths`, `ingest`, `publish`, `browser_download`, `mailbox_acquisition`, `publisher_discovery`, and `workflow_control`. `workflow_control.remediation_reaper.execution_enabled` remains `false` until record creation and read-only projections have been verified; `max_records_per_run` and `lease_seconds` bound each explicit reaper invocation. `openai_models`, `llm_routing`, and `cost` govern model routing and accounting; edit them only with the associated quality and operational implications understood.

Use the generated [configuration reference](../generated/configuration-reference.md) for the current section inventory. It is generated from `src/config/app.example.yaml`; use the YAML and typed contracts as the final authority for values and validation.
