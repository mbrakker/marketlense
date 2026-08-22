# Adjust thank-you route validation

## Scope and baseline

This is a single-candidate acquisition-only validation. It reuses the retained
failed Adjust listing candidate in [cohort.json](cohort.json); it does not run
discovery, ingest, analysis, extraction, generation, publishing, WordPress, or
mailbox acquisition.

The exact retained baseline is the Adjust entry in
`docs/CTO_evidence/browser_isolated_timeout_15_20260822_144500/baseline_evidence/baseline_manifest.json`.
That entry exhausted the `browser_email_form` route with 6 Browser Use calls,
140,918 input tokens, 54,016 cached-input tokens, 7,139 output tokens, and a
357.498-second timeout. It did not verify an acquired artifact.

## Current implementation

- Commit: `e1ca10e67a6d8a735052168d2e5ad8aeec44e1c9`
- Configuration: `src/config/app.adjust_thank_you_validation_20260822_210757.yaml`
- Model: `gpt-5-mini`; temperature `0.0`; no retry.
- Deterministic route: the retained Adjust listing is navigated directly to
  `https://www.adjust.com/resources/ebooks/japan-app-trends/` in an isolated
  worker. A completed but unverified route hands off only that same-origin URL
  to the fresh Browser Use worker.

The non-submitting deterministic replay (`run_id`
`adjust_thank_you_validation_20260822_223000`) completed with that report-page
URL. In the bounded submission run (`run_id`
`adjust_thank_you_validation_20260822_224000`), the worker log confirms that
the playbook completed and that Browser Use started from the report-page URL,
not the listing. Its browser history then recorded the sanitized terminal path
`www.adjust.com/thank-you/ebooks/`.

The process was deliberately stopped immediately after this requested thank-you
page condition was observed. Mailbox polling was never invoked. Therefore this
record verifies browser form-terminal navigation only; it does **not** claim a
verified artifact acquisition or email delivery.

## Observed scalar usage before terminal stop

For `adjust_thank_you_validation_20260822_224000`, the task-scoped usage ledger
recorded 5 Browser Use calls, 119,316 input tokens, 45,184 cached-input tokens,
6,610 output tokens, and estimated cost `$0.032884` before the terminal stop.
These figures are not a like-for-like completed-acquisition benchmark because
the run intentionally stopped once the page condition was observed.

## Reproduction

Run `run_adjust_form_terminal.py` from the repository root. It writes only a
sanitized terminal result to `terminal_result.json`; it does not call mailbox
acquisition. The runner intentionally excludes identity values, raw prompts,
browser history query strings, and model responses from retained evidence.
