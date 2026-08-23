# Initial-30 targeted failure remediation validation

Verdict: **VERIFIED IMPROVEMENT**.

This acquisition-only validation replays the exact three failed records from the
retained initial-30 cohort. No discovery, ingest, analysis, extraction,
generation, publication, or WordPress stage was run.

## Baseline retained

- [Baseline replay](../browser_rendered_pdf_validation_20260821_080508/baseline_30_report_replay.json), SHA-256 `d3b4116b29ea04bf2ced61d9f1f56bb45f30fed505fc108abe2fbba9fbd811c3`.
- [Baseline manifest](../browser_rendered_pdf_validation_20260821_080508/baseline_manifest.json), SHA-256 `13602c0bc0038db4588193760158288314a4bfa943290a8c7c287caccc914ae9`.
- Baseline model/settings: inherited Browser Use `gpt-5-mini`, temperature `0.0`, zero retries, as recorded in the [baseline README](../browser_rendered_pdf_validation_20260821_080508/README.md).

The exact replay cohort was:

| ID | Publisher | Canonical report URL | Baseline failure |
|---|---|---|---|
| `fac_26fd23fd3cf0198081e38c28` | Criteo | `https://go.criteo.com/en/cpg-consumer-insights` | `browser_download_missing_file` |
| `fac_9d4d17626b51fdefb56842cb` | Barclays | `https://www.ib.barclays/research.html` | `browser_download_missing_file` |
| `fac_92baa3a4f4faa888ade7d54f` | Jungle Scout | `https://www.junglescout.com/resources/reports/amazon-beauty-category-insights` | `blocked_unknown_required_enum` |

## Current replay

- Current commit: `b90756835801f7ff441501aab7343301a65ee68a`.
- [Replay configuration](../initial_30_targeted_failure_replay_20260823_173000/configuration.yaml), SHA-256 `ded984d08f3ae1a4457b9f22fbae986182bb1f3b54fdd538f54314d9bca411cc`.
- [Identity configuration](../../../src/config/browser_download_identity.yaml), SHA-256 `7c6bbb1c271ade0488d3a17e727b494bea576ee200792e771f29d6cd874217d5`.
- Model remained the inherited `gpt-5-mini` / temperature `0.0`; the current config has zero retries and disables route/playbook promotion.

| Publisher | Current terminal result | Verification | Route | Agent calls | Duration |
|---|---|---|---|---:|---:|
| Criteo | Downloaded 6,645,905-byte PDF | passed | `browser_preflight_js_pdf_probe` | 0 | 22.718 s |
| Barclays | `blocked_no_progress` at protected research hub | failed; kept in denominator | `browser_listing_hub` | 5 | 73.883 s |
| Jungle Scout | Captured complete 25-page Issuu rendered PDF | passed | `browser_onsite_report` | 0 | 14.427 s |

Exact current records are retained at:

- [Criteo attempt](../initial_30_targeted_failure_replay_20260823_173000/criteo_extensionless_pdf_validation_bounded/acquisition_attempts.jsonl), SHA-256 `6323f19734943657394c4e4e7c27c5ec6e7967a365ba21ba022b3450e34ecfff`.
- [Barclays attempt](../initial_30_targeted_failure_replay_20260823_173000/barclays_extensionless_pdf_validation/acquisition_attempts.jsonl), SHA-256 `192135821cce9233709c473742397b3ae44f53b5b7079be72cd2ff4b3d8c1707`.
- [Jungle Scout attempt](../initial_30_targeted_failure_replay_20260823_173000/junglescout_final_commit_validation/acquisition_attempts.jsonl), SHA-256 `602efd79388c073ca328fe26f5753a0aa6637bf3478e493b1b767baf9f807b95`.

## Baseline vs current

| Metric | Baseline | Current | Change |
|---|---:|---:|---:|
| Attempted reports | 3 | 3 | 0 |
| Verified acquisitions | 0 | 2 | +2 |
| Acquisition success rate | 0.0% | 66.7% | +66.7 pp |
| Browser Use Agent usage | 3 reports | 1 report | -66.7% |
| Browser Use Agent calls | 14 | 5 | -64.3% |
| Input tokens | 295,435 | 111,251 | -62.3% |
| Cached input tokens | 108,288 | 44,160 | -59.2% |
| Output tokens | 13,900 | 2,728 | -80.4% |
| Browser launches | 3 | 2 | -33.3% |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.077296 | $0.023333 | -$0.053963 (-69.8%) |
| Cost per verified acquisition | n/a | $0.011667 | n/a (baseline had zero verified acquisitions) |
| Total acquisition duration | 412.261 s | 111.028 s | -301.233 s (-73.1%) |

Resolution routes (verified reports only): HTTP/direct `0`; private API `0`;
browser preflight `1`; deterministic standard form `0`; deterministic learned
playbook `0`; remembered blocker `0`; Browser Use Agent `0`; deterministic
on-site rendered-PDF capture `1`. Browser Use Agent was used once for Barclays,
but did not resolve a report and stopped through no-progress termination.

Barclays remains an acquisition failure because the protected current hub did
not produce a normal verified artifact. The failure was not replaced, and the
success denominator remains all three reports.
