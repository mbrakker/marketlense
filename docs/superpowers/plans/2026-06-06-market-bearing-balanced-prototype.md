# Market Bearing Balanced Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved balanced editorial prototype from local snapshots of published WordPress artifacts.

**Architecture:** Keep the prototype dependency-free. Store published REST responses as local JSON, normalize and relate them in a pure client content model, render pages through focused view functions, and keep routing/events in the application entrypoint. Preserve the future WordPress split between block-theme presentation and core-plugin content queries.

**Tech Stack:** Semantic HTML, tokenized CSS, browser ES modules, Node built-in test runner, local HTTP server, browser automation.

---

### Task 1: Snapshot And Content Contract

**Files:**
- Create: `out/market-bearing-prototype/data/wp-reports.json`
- Create: `out/market-bearing-prototype/data/wp-briefings.json`
- Create: `out/market-bearing-prototype/data/wp-signals.json`
- Create: `out/market-bearing-prototype/content-model.mjs`
- Create: `out/market-bearing-prototype/tests/content-model.test.mjs`

- [ ] Write tests asserting report normalization, represented-only taxonomies, computed citation counters, filtering, and pagination.
- [ ] Run `node --test out/market-bearing-prototype/tests/content-model.test.mjs` and confirm failure because the content model does not exist.
- [ ] Implement pure content-model functions and generate the local snapshots from published REST artifacts.
- [ ] Run the content-model tests and confirm they pass.

### Task 2: Data-Driven Page Shell

**Files:**
- Modify: `out/market-bearing-prototype/index.html`
- Create: `out/market-bearing-prototype/render.mjs`
- Replace: `out/market-bearing-prototype/app.js` with `out/market-bearing-prototype/app.mjs`
- Create: `out/market-bearing-prototype/tests/prototype-contract.test.mjs`

- [ ] Write contract tests asserting empty mount points, required routes, shared navigation, and absence of hard-coded report cards.
- [ ] Run the contract test and confirm failure against the existing static page.
- [ ] Replace record markup with semantic mount points and implement view renderers for Home, Reports, Topics, Publishers, Signals, Briefings, Report, and Methodology.
- [ ] Implement routing, search, filters, sort, pagination, mobile navigation, and focus updates.
- [ ] Run both test files and confirm they pass.

### Task 3: Complete Visual System

**Files:**
- Modify: `out/market-bearing-prototype/styles.css`
- Modify: `out/market-bearing-prototype/brand-spec.md`
- Modify: `out/market-bearing-prototype/README.md`

- [ ] Apply the approved Market Bearing tokens to all new modules.
- [ ] Add responsive layouts, visible focus, disclosure, result, empty, and loading states.
- [ ] Document snapshot provenance, regeneration inputs, WordPress ownership mapping, and review commands.
- [ ] Run tests after styling and documentation changes.

### Task 4: Browser Verification

**Files:**
- Update generated screenshots under `out/market-bearing-prototype/`

- [ ] Start a local server at `http://127.0.0.1:4173/`.
- [ ] Verify Home, Reports, Topics, Publishers, Signals, Briefings, and Report at desktop width.
- [ ] Verify navigation, global search, filtering, sorting, pagination, and report deep links.
- [ ] Verify Home and Report at mobile width.
- [ ] Confirm the browser console contains no errors or warnings.
- [ ] Capture updated desktop and mobile screenshots.
- [ ] Run the complete prototype test command one final time.
