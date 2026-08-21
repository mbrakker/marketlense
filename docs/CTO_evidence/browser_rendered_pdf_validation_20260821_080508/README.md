# Browser-rendered PDF validation — 2026-08-21

## Verdict

**VERIFIED IMPROVEMENT**

The exact nine-report cohort below was replayed on `main` after adding a
provenance-preserving rendered-PDF path for verified on-site reports. No
discovery, ingest, analysis, extraction, generation, publishing, or WordPress
stage was run.

## Reproducibility

- Current `main` commit: `e60b15166f6617f95a4cf61281a92afbaa380e82`
- Configuration: `src/config/app.browser_acquisition_final_validation_rerun_20260820_e60b1516.yaml`
  - SHA-256: `73296BD81008C4BAC4CB8A827D84CAC8BC92FCAF547A63DCCDEE61795697D219`
  - same inherited Browser Use model: `gpt-5-mini`; temperature `0.0`; zero retries.
  - no generic Browser Use context-reduction experiment.
- Frozen cohort manifest: [baseline_manifest.json](baseline_manifest.json)
  - SHA-256: `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`
- Baseline replay retained verbatim: [baseline_30_report_replay.json](baseline_30_report_replay.json)
  - SHA-256: `D3B4116B29EA04BF2CED61D9F1F56BB45F30FED505FC108ABE2FBBA9FBD811C3`
- Final acquisition-only replay: [final_replay/diagnostic_replay.json](final_replay/diagnostic_replay.json)
  - SHA-256: `98DC3569BFD8C74361AE150B72BE7E068E24CE74B5CE4D23AF931EC2DFD81096`

The retained `current_replay` and `fixed_replay` directories are intermediate
diagnostics. `final_replay` is the terminal validation run. The latter uses a
30-second isolated local-renderer deadline; its output is accepted only with a
local PDF signature, verified route status, and Drive persistence.

## Exact cohort and final results

| ID | Publisher | URL | Final route | Final artifact | Verified |
|---|---|---|---|---|---|
| `fac_eda48226bd40dd9fece75890` | BlueCore | `http://bluecore.com/lp/consumer-electronics-retailers-guide` | browser_onsite_report | rendered_onsite_pdf | yes |
| `fac_0294383b7bf86f9bcc6fbf06` | Brand Finance | `https://brandfinance.com/consulting/brand-research` | browser_listing_hub | html | no |
| `fac_10a7fd2d5e39d5c484777954` | Brand Finance | `https://brandfinance.com/insights/insurance-2026-ai-risk-and-reporting-redefining-brand-value` | browser_onsite_report | rendered_onsite_pdf | yes |
| `fac_b4408981245f7cedaad405c2` | Kenshoo Skai | `https://skai.io/de/skai-research-center?wg-choose-original=false` | browser_onsite_report | rendered_onsite_pdf | yes |
| `fac_b42ceee7557c1317ef2c2ad6` | Algolia | `https://www.algolia.com/lp/algolia-forrester-tei-report-2026` | browser_onsite_report | rendered_onsite_pdf | yes |
| `fac_f2a23a6db782909156ca996f` | Bain & Company | `https://www.bain.com/insights/topics/technology-report` | browser_onsite_report | rendered_onsite_pdf | yes |
| `fac_8dc34ec7ffcca9fc7f349331` | BlueCore | `https://www.bluecore.com/bfcm-resources/black-friday-trends-and-benchmarks` | browser_onsite_report | rendered_onsite_pdf | yes |
| `fac_489b10b8fee8b3591af2ce51` | Bright Local | `https://www.brightlocal.com/learn/google-business-profile/reporting` | browser_onsite_report | rendered_onsite_pdf | yes |
| `fac_82f650b19147f442363508b2` | Barclays | `https://www.ib.barclays/research/the-eagle-eye.html` | browser_onsite_report | html | no |

Brand Finance Consulting remains a verified on-site HTML capture from a listing-hub terminal state with no renderable terminal HTML. Barclays remains a bounded-incomplete on-site capture after six Agent calls; it is intentionally not counted as a success.

## Comparable baseline vs. current metrics

Resource metrics use each report's final task-scoped acquisition telemetry row.
The denominator remains all nine attempted reports.

| Metric | Previously retained nine-report run | Current final run | Change |
|---|---:|---:|---:|
| Attempted reports | 9 | 9 | 0 |
| Verified acquisitions | 0 | 7 | +7 |
| Acquisition success rate | 0.00% | 77.78% | +77.78 pp |
| Browser Use Agent usage | 1 report | 1 report | 0 |
| Browser Use Agent calls | 6 | 6 | 0 |
| Input tokens | 98,229 | 111,698 | +13,469 |
| Cached input tokens | 37,504 | 44,672 | +7,168 |
| Output tokens | 8,763 | 5,437 | −3,326 (−37.96%) |
| Browser launches | 2 | 2 | 0 |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.033645 | $0.028747 | −$0.004898 (−14.56%) |
| Cost per verified acquisition | not defined (0 verified) | $0.004107 | not comparable |
| Total acquisition duration | 287.500 s | 195.884 s | −91.616 s (−31.87%) |

Verified route-resolution counts: HTTP/direct 7, private API 0, browser
preflight 0, deterministic standard form 0, deterministic learned playbook 0,
remembered blocker 0, Browser Use Agent 0. Of the two unresolved reports, Brand
Finance Consulting ended in a no-Agent browser/preflight capture and Barclays
used the Agent (six calls). The seven HTTP/direct on-site captures were rendered
and verified without an Agent.

## Implementation validated

- Direct on-site HTML capture retains the HTML snapshot and produces a bounded
  `rendered_onsite_pdf` primary artifact when possible.
- Browser terminal capture no longer requires a publisher print control before
  attempting browser print-to-PDF.
- Generated PDFs remain distinct from publisher-supplied PDFs and are accepted
  only after signature, route, and Drive verification.
- Renderer isolation terminates no-progress rendering after 30 seconds and
  falls back to the retained HTML rather than fabricating a PDF.

Focused regression validation:

```text
python -m pytest tests/test_acquisition_failure_remediation.py tests/test_browser_report_download_service/test_onsite_and_terminal.py -q
59 passed in 58.78s
```
