# Browser acquisition final validation rerun — 2026-08-20

## Verdict: REGRESSION

This is a complete, acquisition-only replay of the immutable 30-report cohort in
`../../acquisition_failure_remediation_20260814_5d4c027f/failed_acquisition_manifest.json`.
No discovery, ingest, extraction, generation, publishing, or WordPress stage was
run. Normal artifact verification was unchanged: only
`artifact_verification.verified_usable_artifact == true` counts as an acquisition.

The current run has much lower Browser Use resource consumption, but verified
acquisition fell from 5/30 to 3/30 (16.67% to 10.00%). This is therefore a
regression, not a verified improvement.

## Reproducibility and retained inputs

- Current `main` commit: `e60b15166f6617f95a4cf61281a92afbaa380e82`.
- Current acquisition run: `fc4a52e2-1565-488b-9c48-f9e008da97c5`.
- Current model: `gpt-5-mini`.
- Current configuration: `../../../src/config/app.browser_acquisition_final_validation_rerun_20260820_e60b1516.yaml`
  (SHA-256 `73296BD81008C4BAC4CB8A827D84CAC8BC92FCAF547A63DCCDEE61795697D219`).
- The replay retained zero acquisition retries and the comparable browser email
  route envelope (240 seconds / 24 steps), with the outer worker cap observed as
  312–315 seconds. It did not enable the rejected generic Browser Use
  context-reduction experiment.
- `baseline_evidence.json` pins the exact retained baseline manifest and attempt
  record by source path and SHA-256. `current_replay/acquisition_attempts.jsonl`
  is the immutable per-report output for this run.

The rerun contains one surgical, uncommitted fix after the first attempt exposed
a cancellation-resistant Browser Use websocket preflight: the preflight coroutine
is now enclosed by a daemon-thread deadline in synchronous callers, producing a
typed `browser preflight session timed out` failure instead of blocking the
cohort. The matching regression test and workflow documentation update are in
the worktree. During this live acquisition run the promoted identity configuration
also learned five non-sensitive form labels in `src/config/browser_download_identity.yaml`;
that run-generated change was preserved, not reverted.

## Metrics

| Metric | Baseline | Current | Change |
| --- | ---: | ---: | ---: |
| Attempted reports | 30 | 30 | 0 |
| Verified acquisitions | 5 | 3 | -2 |
| Acquisition success rate | 16.67% | 10.00% | -6.67 pp |
| Browser Use Agent reports | 29 | 5 | -24 (-82.76%) |
| Browser Use Agent calls | 1,239 | 23 | -1,216 (-98.14%) |
| Input tokens | 24,698,470 | 455,391 | -24,243,079 (-98.16%) |
| Cached input tokens | 9,338,240 | 173,440 | -9,164,800 (-98.14%) |
| Output tokens | 1,192,806 | 26,039 | -1,166,767 (-97.82%) |
| Browser launches | 212 | 21 | -191 (-90.09%) |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $6.459150 | $0.126904 | -$6.332246 (-98.04%) |
| Cost per verified acquisition | $1.291830 | $0.042301 | -$1.249529 (-96.73%) |
| Acquisition duration | 3,081.923 s | 5,970.490 s | +2,888.567 s (+93.73%) |

## Verified-acquisition route resolution

The table below counts only normal verified acquisitions, so its row totals equal
the verified-acquisition count. A route that merely captured HTML or inferred an
email delivery is not counted.

| Route class | Baseline | Current | Evidence interpretation |
| --- | ---: | ---: | --- |
| HTTP/direct | 2 | 2 | `report_page_pdf_link_probe` verified native PDFs |
| Private API | 0 | 0 | No normal verified acquisition recorded through a private API |
| Browser preflight | 2 | 0 | Baseline `browser_preflight_js_pdf_probe`; no current verified preflight PDF |
| Deterministic standard form | 0 | 0 | No normally verified native PDF through this route |
| Deterministic learned playbook | 0 | 0 | One current playbook HTML capture occurred, but it is not a verified usable artifact |
| Remembered blocker | 0 | 0 | No row records `used_memory_route: true` as a normal verified acquisition |
| Browser Use Agent | 1 | 1 | BCG native PDF, with 13 baseline versus 3 current Agent calls |

Current architecture observations from the retained telemetry:

- Each report has one task-scoped `resource_attempts` record, supplying calls,
  tokens, launches, retries, cost, duration, route, and terminal outcome.
- Current direct-PDF resolution avoided Agent calls and launches for the two
  report-page probes.
- Browser preflight was invoked before Agent fallback, and the repaired
  cancellation boundary terminated websocket-affected preflights in about
  26–28 seconds instead of stalling the batch.
- Learned deterministic playbook activity is retained for the Brand Finance
  listing capture, but it did not pass native-PDF acquisition verification.
- `used_memory_route` was false (or absent on failures) for the cohort; no
  remembered-blocker success is claimed.
- Five reports used the Agent (23 calls total). The remaining fallback attempts
  either terminated without a model call or resolved deterministically.
- The no-progress/worker terminal cap produced explicit failures for the stuck
  Browser Use workers; failed reports stayed in the denominator.

## Comparison conclusion

Against the previously retained run of the same report-acquisition scope, current
main reduced Browser Use incidence by 24 reports (82.76%), Agent calls by 1,216
(98.14%), input/cached/output tokens by 98.16%/98.14%/97.82%, browser launches
by 191 (90.09%), and cost by $6.332246 (98.04%). It did **not** reduce
acquisition time: duration increased by 2,888.567 seconds (93.73%). Verified
acquisition success regressed by 2 reports, from 5/30 to 3/30 (-6.67 percentage
points). Therefore the result is **REGRESSION**.
