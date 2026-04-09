# Market Lense Streamlit Control Panel Architecture and Delivery Plan

## Objective

Build the Streamlit UI into the primary operator control panel for Market Lense.

The target product must satisfy five non-negotiable goals:

1. Full coverage of all project features
2. Full control of all configuration
3. Real control-panel behavior: run workflows, monitor progress, inspect stats, and debug failures from one place
4. Modern design
5. User-friendly, comfortable UX

The UI must stay aligned with the existing `contracts -> services -> generators -> orchestrators` architecture. Streamlit is the presentation shell, not a place to duplicate business logic.

---

## Current-State Analysis

### What already exists

The current Streamlit cockpit already provides meaningful operational value:

- Thin entrypoint: `src/streamlit_app.py`
- One existing Streamlit page surface: `src/ui/streamlit_pages.py`
- Read models and dashboard data assembly: `src/generators/streamlit_dashboard_generator.py`
- Direct UI actions for:
  - `ingest`
  - `extract-candidates`
  - `generate-covers`
  - `publish-wp`
  - `recategorize`
  - `update-wp-categories`
  - `cost-report`
- Existing pages for reports, evidence, validation, logs, storage, and settings
- Editable `app.yaml` with validation and backup support
- Prompt registry visibility

### What is missing relative to the target product

The cockpit is useful, but it is not yet the full project control panel.

#### 1. Feature coverage is incomplete

The UI does not currently expose several real project workflows that already exist in the CLI:

- `download-report`
- `discover-publisher-inventory`
- `audit-acquisition-paths`
- `sync-publishers`
- `drive-oauth-login`

That means the Streamlit app does not yet provide full coverage of the operational surface.

#### 2. Full config control is incomplete

`app.yaml` is editable, but full operational control requires first-class UI editing or management for all major config assets, not only one file:

- `src/config/category-mappings.yaml`
- `src/config/cover-styles.yaml`
- `src/config/browser_download_identity.yaml`
- publisher snapshot JSON
- prompt files under `src/prompts/`
- secret and auth setup status

Today those surfaces are split between read-only views, hidden filesystem knowledge, and external manual editing.

#### 3. The app is not yet a real run-control plane

Long actions are still launched inline inside the Streamlit session. That limits the system in several ways:

- no persistent run supervisor
- no background queue
- no cancel or retry control
- no cross-session run history
- no durable active-job monitor
- live monitoring is tied too closely to one browser session

For a true control panel, long-running workflows must become tracked background jobs with persisted status and log linkage.

#### 4. UI maintainability is becoming a problem

The entrypoint is thin, but `src/ui/streamlit_pages.py` has grown into a large multi-page module. The next stage should split the UI by bounded context without adding pointless layers.

#### 5. UX and design are functional, but not final

The current UI works, but it still has architectural and usability debt:

- flat radio navigation does not scale well
- page grouping is weak
- there is heavy custom CSS injection instead of native Streamlit theming as the baseline
- first-time operator flows are not guided enough
- the current structure is stronger as an inspector than as an operator console

---

## Product Definition

The target Streamlit system is not just a dashboard. It is the operations console for the entire project.

It must let an operator:

- launch every supported workflow
- inspect every workflow result
- inspect and edit runtime configuration safely
- monitor active and historical runs
- inspect logs, validation, evidence, outputs, storage, and costs
- manage publisher discovery and report acquisition workflows
- troubleshoot WordPress publishing and taxonomy flows

If a workflow exists in the project and is operationally relevant, the UI must surface it.

---

## Coverage Gap Matrix

| Capability | Current UI Status | Target Status |
| --- | --- | --- |
| Ingest | Implemented | Keep and harden |
| Candidate extraction | Implemented | Keep and harden |
| Cover generation | Implemented | Keep and harden |
| WordPress publish | Implemented | Keep and harden |
| Recategorize | Implemented | Keep and harden |
| WordPress category sync | Implemented | Keep and harden |
| Cost report | Implemented | Keep and harden |
| Logs, storage, report inspection | Implemented | Deepen with run-linked context |
| `download-report` | Missing | Add dedicated page |
| `discover-publisher-inventory` | Missing | Add dedicated page |
| `audit-acquisition-paths` | Missing | Add dedicated page |
| `sync-publishers` | Missing | Add dedicated admin page |
| `drive-oauth-login` | Missing | Add auth/setup page |
| `app.yaml` editing | Implemented | Keep and harden |
| Category mappings editing | Partial | Add structured + raw editing |
| Cover style editing | Partial | Add structured + raw editing |
| Browser download identity editing | Missing | Add dedicated editor |
| Prompt inspection | Partial | Add inspect, diff, edit, validate flow |
| Secret/auth control | Partial | Add masked management surface |

The definition of "full feature coverage" for this project is simple:

- every operator-facing CLI command must have a Streamlit surface
- every important artifact/result must be inspectable from the UI
- every important configuration surface must be visible and controllable

---

## Streamlit Implementation Rules

This plan follows the Streamlit guidance already available in the project skill set.

### Navigation and layout

- Use `st.navigation(..., position="sidebar")` with grouped sections because the product has many pages.
- Keep the sidebar limited to navigation and global filters only.
- Main pages should use bordered containers, compact KPI rows, and at most four columns.
- Use one dominant task per page.

### Widgets and interaction patterns

- Use `st.segmented_control` for small single-select mode switches.
- Use `st.pills` for compact visible multi-filters.
- Use `st.toggle` for runtime feature switches and settings.
- Use `st.dataframe` and `st.data_editor` with `column_config` for readable tables.
- Use `@st.dialog` for destructive or high-risk confirmations.
- Use `st.tabs` for secondary views, not as the primary navigation system.

### State and architecture

- Use `st.session_state` for selected report, selected run, shared filters, and cache invalidation state.
- Keep Streamlit pages presentation-focused.
- Keep business logic in generators.
- Keep workflow sequencing and retries in orchestrators.
- Keep filesystem, process, database, network, and config I/O in services.

### Theming

- Move baseline theming into `.streamlit/config.toml`.
- Use custom CSS only for small component-level cases that native theming cannot solve cleanly.
- Do not rely on CSS injection as the primary design system.

---

## Target Navigation

The next navigation should represent real operator jobs, not just a flat list of pages.

### Overview

- Cockpit overview
- Run center

### Core operations

- Ingest control
- Candidate extraction
- Cover images
- Publishing and taxonomy

### Publisher operations

- Publisher discovery
- Report download lab
- Acquisition audit
- Publisher sync
- Auth and external access

### Content QA

- Report command center
- Analysis and evidence
- Validation center

### Observability

- Cost and usage
- Logs and live events
- System and storage

### Configuration

- Settings and prompts

This grouping reduces cognitive load and gives the user a clear mental model:

- run work
- inspect content
- inspect system state
- manage configuration

---

## Target UI Architecture

### Required structure

The app should move from one large UI module to bounded-context page modules.

Preferred structure:

```text
src/
  streamlit_app.py
  ui/
    app_pages/
      cockpit_overview.py
      run_center.py
      ingest_control.py
      candidate_extraction.py
      cover_images.py
      publishing_taxonomy.py
      publisher_discovery.py
      report_download_lab.py
      acquisition_audit.py
      publisher_sync.py
      auth_access.py
      report_command_center.py
      analysis_evidence.py
      validation_center.py
      cost_usage.py
      logs_events.py
      system_storage.py
      settings_prompts.py
    common.py
    state.py
```

Rules for this split:

- `streamlit_app.py` remains the entrypoint only
- page modules render one bounded context each
- `common.py` should contain only genuinely shared UI helpers
- `state.py` should initialize shared session state
- avoid creating thin pass-through layers that only rename calls

### Workflow execution model

Short read operations can stay in-process. Long-running write operations should move to a tracked background execution model.

Recommended new boundary:

```text
src/
  contracts/
    ui_run_control.py
  services/
    process_service.py
    run_registry_service.py
  orchestrators/
    ui_run_control_orchestrator.py
```

Responsibilities:

- `process_service.py`
  - canonical boundary for local process execution
  - launches and polls background commands safely
  - captures stdout, stderr, pid, exit status

- `run_registry_service.py`
  - persists run metadata
  - stores command, run type, state, timestamps, linked artifact paths, log path, and result summary

- `ui_run_control_orchestrator.py`
  - decides how jobs are launched, monitored, retried, canceled, and surfaced in the UI
  - maps UI actions to tracked background jobs

This is the key architectural change needed to make the Streamlit app a real control panel instead of a synchronous command launcher.

### Why background job control matters

Without background job control:

- ingest can block one browser session
- discovery and download workflows cannot be monitored reliably from another session
- historical run visibility is weak
- run state becomes tied to reruns instead of persisted control-plane state

With background job control:

- operators can launch work and return later
- run history becomes durable
- logs and outputs become attachable to a run record
- the UI becomes a real operational console

---

## Config Control Architecture

To satisfy "full control of all config", the UI needs a clear config-management model.

### Required editable surfaces

- `src/config/app.yaml`
- `src/config/category-mappings.yaml`
- `src/config/cover-styles.yaml`
- `src/config/browser_download_identity.yaml`
- publisher snapshot JSON used by `sync-publishers`
- prompt files under `src/prompts/`

### Required management capabilities

- structured form editor where a structure is stable and human-manageable
- raw YAML or JSON editor for full-fidelity editing
- validation before save
- backup before overwrite
- diff or change preview where useful
- modified timestamp and file path visibility
- typed error reporting on invalid saves

### Secret and auth handling

Secrets must still come from environment variables or a secret store.

The UI should support one of these models:

1. Local development mode
   - masked write-only inputs for `.env` or a local secret file managed by a service boundary

2. Deployed mode
   - read-only secret presence/status
   - explicit guidance on where the deployment secret must be updated

The UI must never reveal stored secret values after save.

---

## UX and Visual Design Direction

The final control panel should look like a deliberate operations product, not a default Streamlit demo.

### Visual direction

- Light-first control room aesthetic
- Clean neutral workspace with stronger sidebar identity
- Purposeful typography
- High contrast, easy scan hierarchy
- Calm but not bland

Suggested theme direction:

- main background: warm off-white
- card background: white
- sidebar: deep green or deep slate
- accent: blue-green or mineral blue
- body font: `Manrope`
- heading font: `Sora`
- code font: `JetBrains Mono`

### Interaction design rules

- one primary action per page
- secondary actions in dialogs or compact action rows
- table rows must open contextual details without navigation confusion
- filters should be visible, compact, and persistent
- every long-running action must show run status, start time, and linked logs
- every artifact view should show source path and provenance

### UX comfort rules

- prefer sentence case
- prefer caption and badges over heavy alert boxes for normal status
- keep important flows within three clicks
- provide defaults for common actions
- remember the last selected report, run, and filters per session
- add guided empty states instead of blank panels

---

## Delivery Plan

### Phase 1: Foundation and page split

Goal: make the UI maintainable enough to grow.

Deliverables:

- replace flat page routing with grouped `st.navigation`
- split `src/ui/streamlit_pages.py` into bounded-context page modules
- create `src/ui/state.py` for shared `st.session_state` initialization
- move baseline design into `.streamlit/config.toml`
- keep only small targeted CSS where native theming is insufficient
- add a dedicated Run Center page skeleton

Exit criteria:

- no single monolithic page module owns the entire cockpit
- navigation is grouped by operator job
- design no longer depends primarily on injected CSS

### Phase 2: Full workflow coverage

Goal: ensure the Streamlit UI covers the real project surface.

Deliverables:

- add Publisher discovery page
- add Report download lab page
- add Acquisition audit page
- add Publisher sync page
- add Auth and external access page for Drive OAuth and related status
- surface all existing CLI workflows through the UI

Exit criteria:

- every operator-facing CLI workflow has a Streamlit surface
- every workflow page shows inputs, execution status, results, and artifact locations

### Phase 3: Full config control

Goal: make configuration complete and safe from within the control panel.

Deliverables:

- add editors for category mappings, cover styles, browser download identity, publisher snapshot, and prompts
- add prompt hash, prompt diff, and save validation
- add secret and auth status panel
- add masked secret management path for local development if the project chooses to support it

Exit criteria:

- every important non-secret config asset is editable from the UI
- every secret surface is at least manageable or explicitly routed to its real control point

### Phase 4: Real run control

Goal: turn the cockpit into a true run and monitoring console.

Deliverables:

- add background job launch for long workflows
- persist run registry records
- add run history, active jobs, and per-run detail view
- link each run to logs, outputs, duration, cost, and outcome
- add retry and cancel controls where safe

Exit criteria:

- long workflows do not depend on one active browser rerun loop
- an operator can leave and return to inspect a job later
- the Run Center becomes the single place to understand active and recent work

### Phase 5: UX hardening and operator polish

Goal: make the system comfortable for daily use.

Deliverables:

- page-specific quick actions and presets
- better empty states and error explanations
- pinned key columns and cleaner tables
- keyboard-friendly flows
- responsive layout checks for laptop widths
- guided first-run setup hints on auth, config, and publishing readiness

Exit criteria:

- common tasks are easy without prior repo knowledge
- the UI feels like an operations product, not a developer-only admin panel

---

## Acceptance Criteria

The Streamlit control panel is complete only when all five goals are true at the same time.

### 1. Full coverage of all features

Done when:

- every operator-facing CLI command has a UI entrypoint
- every important result artifact is viewable from the UI
- every major workflow exposes status, outputs, and failure context

### 2. Full control of all config

Done when:

- all important config files are visible and editable from the UI
- prompt assets are inspectable and manageable from the UI
- secret and auth state is controllable without exposing secret values

### 3. Real control panel behavior

Done when:

- long workflows run as tracked jobs
- progress, logs, duration, and outputs are tied to persisted run records
- operators can inspect current and historical runs from one place

### 4. Modern design

Done when:

- the UI uses a coherent native Streamlit theme
- navigation is grouped and scalable
- layouts are intentional and readable

### 5. User-friendly and comfortable UX

Done when:

- first-time operators can launch and inspect workflows without reading source code
- common tasks are easy and predictable
- the UI exposes system power without exposing implementation chaos

---

## Non-Negotiable Guardrails

- The UI must not duplicate business logic already owned by generators or orchestrators.
- The UI must not introduce shadow service boundaries for systems that already have a canonical service.
- The UI must not become a new monolith after the page split.
- Long-running execution, retries, and lifecycle state belong in orchestrators and services, not inside ad hoc Streamlit callbacks.
- Configuration edits must be validated and logged.
- Secret values must never be re-displayed after save.

---

## Final Direction

The current Streamlit cockpit is a strong base, but it is still one step short of the real target.

The next version should be built as:

- a grouped multi-page Streamlit application
- a full operator-facing surface for every workflow
- a safe configuration console
- a persistent run monitor
- a modern, high-comfort operations UI

That is the path from "useful dashboard" to "project control panel."
