# Report Acquisition

> **Documentation type:** Current reference
> **Canonical topic:** Report acquisition workflow
> **Update trigger:** Acquisition routes, browser policy, persistence, or archival changes.

Report acquisition evaluates a source URL and classifies a bounded outcome such as a PDF download, an on-site report capture, or delayed email delivery. It uses persisted route information only as an input to planning; failures and route changes remain observable and retry ownership stays with the orchestrator.

For an email-gated browser route, terminal stabilization polls only after recorded submission evidence, a transient terminal condition, or an explicit assist trigger. A route with no recorded submission finishes without the email polling schedule, and timeout-recovery attempts are bounded by the request timeout as well as the recovery safety cap.

Use `python -m src.cli download-report <url>` for an explicit acquisition request and `python -m src.cli browser-doctor` to diagnose the local browser runtime. Browser, Drive, and mailbox prerequisites are covered in [credentials](../ops/credentials.md); recovery guidance is in [troubleshooting](../ops/troubleshooting.md).
