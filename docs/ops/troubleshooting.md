# Troubleshooting

> **Documentation type:** Operational procedure
> **Canonical topic:** Troubleshooting
> **Update trigger:** Operator-facing failure mode or diagnostic procedure changes.

| Symptom | First action | Next reference |
| --- | --- | --- |
| Missing or invalid source PDF | Inspect the source outcome and retained acquisition evidence | [Report acquisition](../workflows/report-acquisition.md) |
| OCR or text extraction failure | Confirm the source PDF and OCR policy before retrying | [Top failure runbooks](top_failure_runbooks.md) |
| Browser acquisition issue | Run `python -m src.cli browser-doctor` and inspect the bounded diagnostic output | [Report acquisition](../workflows/report-acquisition.md) |
| Mail delivery not found | Confirm mailbox configuration and request scope | [Mailbox acquisition](../workflows/mailbox-acquisition.md) |
| Drive or WordPress authentication failure | Repair local credentials or secrets without logging them | [Credentials](credentials.md) |
| Publish or public-site issue | Inspect publish validation and WordPress response context | [WordPress operations](wordpress.md) |
| Stalled or failed UI job | Inspect the persisted run and dead-letter context | [Operator cockpit](../architecture/operator-cockpit.md) |
| PDF preview missing only in a deep Windows workspace | Use the returned preview artifact reference; preview output compacts its directory segment to stay within the Windows path budget | [Report processing](../workflows/report-processing.md) |
| Intermittent Windows local-cache write error | Re-run the bounded operation; only native rename sharing/access errors are retried locally, while other write errors remain explicit | [Local development](local-development.md) |

Use `python -m src.cli --help` to confirm available commands. Avoid broad retries and destructive cleanup until the retained evidence identifies the affected workflow and side effect.

For a `browser_email_form` fallback, inspect
`browser_report_download_pre_llm_autofill_escalated`. A reason of
`async_browser_session` means deterministic pre-fill was intentionally skipped: it
must not share a Browser Use session with a helper that cannot be safely cancelled.
Browser Use receives the untouched session as the fallback.
