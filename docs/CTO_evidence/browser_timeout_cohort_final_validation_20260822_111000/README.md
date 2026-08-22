# Browser Use acquisition final validation — 2026-08-22

## Verdict: NOT VERIFIED

This acquisition-only replay selected the exact retained 15-report Browser Use
timeout cohort. It did not run discovery, ingest, analysis, extraction,
generation, publishing, or WordPress. The runner emitted normal terminal
records for five reports, then made no progress beyond the established route
terminal envelope. It was stopped after a sustained no-progress interval;
therefore it is not a complete, comparable 15-report run.

Normal acquisition verification was not changed. A success requires
`artifact_verification.verified_usable_artifact == true`; all five retained
records are false. No easier reports were substituted.

## Retained baseline and current configuration

- Baseline source is retained exactly as `baseline_manifest.json` (SHA-256
  `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`) and
  `baseline_all_attempts.jsonl` (SHA-256
  `C695010527AA4B67DE69D36632772E3104A67107F5C09EDC302714BCC7EC0D7B`).
- The exact selected cohort is the 15 baseline rows with
  `acquisition_error.error_code == browser_download_agent_timeout`; its
  materialized selection is `selected_baseline_records.json`.
- Current commit: `85c2fad9974fa5f13457955353af750c7a33cf41`.
- Current profile: `configuration.yaml` (SHA-256
  `8CCC21831118A6820E38A33CD4231EACA119596CE875D3F833501237A9902701`);
  model `gpt-5-mini`, zero retries, `browser_email_form` 240 seconds / 24
  steps, isolated output/state, and route/private-API playbook promotion
  disabled.
- Current identity configuration SHA-256:
  `7C6BBB1C271ADE0488D3A17E727B494BEA576EE200792E771F29D6CD874217D5`.
- The rejected generic Browser Use context-reduction experiment remains absent;
  see the retained rejection decision at
  `../browser_acquisition_final_validation_20260820_e60b1516/browser_use_context_reduction_rejection.md`.
- Retained current result SHA-256:
  `EC7A108D45D81A6F55A9BD77BD7C85440006B455014A393522CDFE3D249726D6`.

## Baseline versus current evidence

| Metric | Retained 15-report baseline | Current run | Comparison status |
| --- | ---: | ---: | --- |
| Cohort reports | 15 | 15 fixed; 5 terminal records retained | incomplete current run |
| Verified acquisitions | 0 | 0 of 5 terminal records | full-cohort rate unavailable |
| Acquisition success rate | 0.00% | 0.00% of retained terminal records | not comparable |
| Browser Use Agent reports | 0 | 2 of 5 retained records | not comparable |
| Browser Use Agent calls | 0 | 9 | not comparable |
| Input / cached / output tokens | 0 / 0 / 0 | 205,312 / 71,680 / 8,900 | not comparable |
| Browser launches | 15 | 5 | not comparable |
| Retries | 0 | 0 | not comparable |
| Total acquisition cost | $0.000000 | $0.053000 for 5 records | not comparable |
| Cost per verified acquisition | not defined | not defined | not comparable |
| Acquisition duration | 5,168.898 s | 2,039.367 s for terminal records only | not comparable |

The runner subsequently made no progress and emitted no sixth terminal record.
The unrecorded stalled interval is deliberately not assigned to a report,
cost, token, route, or success rate. Full-cohort reductions cannot be inferred
from a five-record prefix.

## Per-report terminal results

| Candidate | Publisher | Route | Agent calls | Verified | Duration | Terminal result |
| --- | --- | --- | ---: | --- | ---: | --- |
| `fac_fa1889b4c19f0f238659145e` | Criteo | `browser_email_form` | 3 | no | 349.494 s | `browser_download_agent_timeout` |
| `fac_0ef70242a602b9ed7641c056` | Adjust | `browser_email_form` | 6 | no | 344.225 s | `browser_download_agent_timeout` |
| `fac_3e630244e5c22fe8fa787255` | GWI | `browser_email_form` | 0 | no | 405.551 s | `browser_download_agent_timeout` |
| `fac_4da62bac17be2e7185090695` | GWI | `browser_email_form` | 0 | no | 390.913 s | `browser_download_agent_timeout` |
| `fac_c0e4c925c1ed4ce6149711b8` | GWI | `browser_email_form` | 0 | no | 549.184 s | `browser_download_agent_timeout` |
| Remaining exact cohort members | GWI and Jungle Scout | — | — | — | — | no terminal record after runner no-progress stall |

Verified route-resolution counts for the five retained terminal records are:
HTTP/direct 0; private API 0; browser preflight 0; deterministic standard form
0; deterministic learned playbook 0; remembered blocker 0; Browser Use Agent
0. These are not full-cohort counts.

## Architecture observations

- Each retained report has a task-scoped `resource_attempts` record, covering
  route, calls, tokens, launches, retries, cost, and terminal status.
- The current code orders private API before browser preflight, then remembered
  blocker and deterministic playbook handling before Browser Use Agent fallback.
  This partial run directly exercised Agent fallback for Criteo and Adjust, but
  did not directly exercise a successful private-API, preflight, standard-form,
  learned-playbook, or remembered-blocker resolution.
- The run is negative evidence for no-progress termination at runner scope: it
  required a manual stop after the fifth terminal record and before a sixth
  record could be retained.

Against the previously retained run of the same report-acquisition scope, the
current replay cannot establish any reduction in Browser Use incidence, Agent
calls, tokens, browser launches, cost, or acquisition time, and it cannot show
whether verified acquisition success regressed. The required full 15-report
comparison is therefore **NOT VERIFIED**.
