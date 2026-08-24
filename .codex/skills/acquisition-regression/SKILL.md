---
name: acquisition-regression
description: Verify MarketLense discovery, acquisition, download, or browser-route changes; not for PDF extraction after an artifact is acquired.
---

# Acquisition regression

Use after changing publisher discovery, mailbox acquisition, browser download,
route planning, acquisition handoff, or acquisition evidence.

## Entry points and invariants

- `src/services/browser_report_download_service.py` is the browser boundary;
  `src/services/mailbox_acquisition_service.py` owns mailbox I/O.
- `src/orchestrators/report_download_orchestrator.py` and
  `src/orchestrators/acquisition_ingest_handoff_orchestrator.py` own workflow
  sequencing and retry decisions.
- Preserve source identity, bounded route/browser budgets, terminal evidence,
  typed failure behavior, and idempotent handoff. Do not promote a shell,
  redirect, blocked page, or unrelated document as an acquired report.

## Inspect and verify

Read the changed service/orchestrator, its contract under `src/contracts/`,
route-specific tests, and retained evidence only when the request involves an
evidence projection. Keep browser, HTTP, and mailbox calls behind their
canonical services.

Run the smallest applicable checks, for example:

```powershell
python -m pytest -q tests/test_browser_report_download_service.py tests/test_report_download_orchestrator.py
python -m pytest -q tests/test_browser_runtime_contract.py tests/test_browser_route_budgets.py
python -m pytest -q tests/test_acquisition_ingest_handoff_orchestrator.py tests/test_acquisition_audit_orchestrator.py
```

Use a controlled browser or live-provider run only when the changed behavior
cannot be proven with the deterministic suite and the request authorizes it.
Record the route, terminal outcome, bounded resource use, and artifact or
typed failure. Completion requires focused checks for the changed path, no
unexplained side effects, and the normal completion-gate evidence.
