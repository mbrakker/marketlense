# Browser-use Random Report Download Probe

Date: 2026-04-20
Updated: 2026-04-21

## Scope

- Objective: test 10 random report-download candidates and document browser-use failures, especially stalling.
- Sample selection: 10 domain-distinct non-PDF rows from `state/reports.sqlite` `report_sources`, fixed seed `20260420`.
- Execution path: real `run_report_download(...)` orchestration with `PublisherInventoryCandidateTrace` built from the stored candidate row.
- Runtime settings: loaded from repo config; only batch override was `timeout_seconds=120.0` instead of default `360.0`.

## Original Batch Result

- 10/10 runs ended non-success in the bounded April 20 diagnostic run.
- 2/10 were rejected before browser-use started: Comscore and Coveo.
- 8/10 reached browser-use and all 8 originally ended with `browser_download_agent_timeout`.
- 3/8 browser-use timeouts already had a real PDF artifact on disk: Contentsquare, Harris Williams, and Capgemini.
- 4/8 browser-use timeouts happened after browser logs had already shown `Task completed successfully`: Contentsquare, Harris Williams, Attest, and Validity.

## Current Active Issues

- Full 10-candidate rerun is still pending. Confirmed fixes below remove the reproduced stall classes from the active issue list, but the full random batch has not yet been rerun end-to-end after the patches.
- Listing-hub wandering remains unproven at batch scale. Prompt guidance is tighter, but Innovid/iAB and Publicis-style listing-hub loops have not been revalidated across the original random sample.
- Mintel full acquisition is still unresolved. The browser path no longer stalls, but the live route ends as `email_delivery / email_required` because Mintel's Location/Country autocomplete does not persist the configured Austria selection.

## Confirmed Fixed

- Post-completion browser-use stalls are fixed for the reproduced completed-history paths. Completed agent history is now salvaged without waiting on cleanup paths that can hang, and lookup-assist is bounded.
- Worker response loss after browser-use completion is fixed for the reproduced paths. Live worker runs now write `browser_agent_worker_response.json` and exit with `return_code=0` instead of leaving the parent with only `browser_download_agent_timeout`.
- Empty-page browser failures no longer collapse into non-retryable weak route summaries. They now map to retryable `browser_download_page_not_loaded`.
- Windows `browser-use doctor` no longer crashes under this console encoding. `browser-use doctor` exited `0` on April 21 with diagnostics output and no `UnicodeEncodeError`.
- Mintel Location autocomplete failures are now typed correctly. The final live run `verification_mintel_live_20260421_retry21_confirm_unknown_enum` returned:
  - `RESULT_OUTCOME= email_required`
  - `RESULT_BLOCKED= blocked_unknown_required_enum`
  - `RESULT_BLOCKED_DETAIL= The 'Location' field requires a selection from a dropdown, and 'Austria' could not be successfully selected or autocompleted.`

## Per-run Notes From Original Probe

1. Innovid / iAB
   Result: `browser_download_agent_timeout` at 155s.
   Current status: active until rerun; original failure was listing-hub churn with no artifact.

2. Publicis Commerce
   Result: `browser_download_agent_timeout` at 158s.
   Current status: active until rerun; original failure was heavy exploration churn with no artifact.

3. Contentsquare
   Result: `browser_download_agent_timeout` at 157s.
   Current status: stall class fixed in targeted regressions; original run downloaded `Sense_ A User´s Guide to Contentsquare´s AI.pdf` before hanging.

4. Comscore
   Result: `report_download_candidate_rejected_non_report`.
   Current status: unchanged; rejected by readiness gate before browser-use.

5. Harris Williams
   Result: `browser_download_agent_timeout` at 157s.
   Current status: stall class fixed in targeted regressions; original run downloaded `BS_Sector_Brief_C_I_Q1_2026_FINAL.pdf` before hanging.

6. Coveo
   Result: `report_download_candidate_rejected_non_report`.
   Current status: unchanged; rejected by readiness gate before browser-use.

7. Capgemini
   Result: `browser_download_agent_timeout` at 159s.
   Current status: direct Capgemini PDF path was previously live-confirmed as `pdf_download / downloaded`; original artifact-loss symptom is not active.

8. Attest
   Result: `browser_download_agent_timeout` at 155s.
   Current status: stall class fixed in targeted regressions; original no-report conclusion still needs rerun if this candidate remains important.

9. Validity / Litmus-linked candidate
   Result: `browser_download_agent_timeout` at 156s.
   Current status: stall class fixed in targeted regressions; blocked/403 route still needs rerun if this candidate remains important.

10. Mintel
    Result: `browser_download_agent_timeout` at 157s.
    Current status: timeout fixed. Final live behavior is now `email_required` with `blocked_unknown_required_enum` for Location autocomplete; full email submission is still unresolved.

## Verification Artifacts

- Original batch artifacts:
  - `out/browser_downloads/browser_use_random_report_probe_20260420_batch1.json`
  - `out/browser_downloads/browser_use_random_report_probe_20260420_batch2.json`
  - `out/browser_downloads/browser_use_random_report_probe_20260420_batch3.json`
- Latest live Mintel verification:
  - task id `verification_mintel_live_20260421_retry21_confirm_unknown_enum`
  - logs in `logs/market_lense_2026-04-21.log`
  - worker response under `out/browser_downloads/www.mintel.com/fb6bb01f2666/browser_agent_worker_response.json`

## Verification Commands Run

- `pytest tests/test_browser_report_download_service.py -k "preserves_configured_location_lookup_blocker or trusts_explicit_lookup_enum_blocker or partial_lookup_timeout or maps_empty_page_to_retryable_load_error or prompt_marks_unverified_memory_as_weak or recovers_lookup_before_completed_history_shutdown or bounds_lookup_assist_after_completed_history_timeout"`
- `pytest tests/test_browser_use_vendor_compat.py`
- `pytest tests/test_report_download_route_planner.py -k "email_form or direct_detail_url_instead_of_source_listing or keeps_onsite_for_insights_longread or prefers_pdf_click_for_resource_report_pages"`
- `browser-use doctor`
