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
`browser_report_download_pre_llm_autofill_escalated`. Deterministic standard-form
handling runs on the already-open async Browser Use session before the Agent. An
unsupported form or unverified submit preserves that same page, cookies, and local
storage for Browser Use fallback; only the outer browser lifecycle closes it.

If a Browser Use run stops after repeated equivalent states, retain the terminal
`blocked_no_progress` route result rather than treating it as a browser-worker
timeout. The async handoff marks BrowserSession teardown as intentional before
the loop cancels background CDP tasks, so the session must not begin a fresh
WebSocket reconnect while the acquisition worker is completing. That terminal
path must not re-enter browser capture, dialog inspection, artifact prefetch,
or form assistance after the Agent event loop has ended. Browser workers also
discard child stdout/stderr instead of capturing a pipe, because a Chrome child
can inherit a pipe and defer worker completion after the response artifact is
written. The session-owning async wrapper cancels the still-running Agent task
as soon as that detector stops it, retaining the partial history rather than
waiting for optional Agent cleanup. Inspect the bounded no-progress event and
the retained per-report evidence before retrying.

When bounded browser preflight confirms a terminal not-found page from its
title and page body, it records `blocked_static_archive` and skips Agent work.
That outcome is not an acquisition success; it prevents repeated navigation of
the same obsolete exact URL.
