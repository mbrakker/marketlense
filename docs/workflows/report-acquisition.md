# Report Acquisition

> **Documentation type:** Current reference
> **Canonical topic:** Report acquisition workflow
> **Update trigger:** Acquisition routes, browser policy, persistence, or archival changes.

Report acquisition evaluates a source URL and classifies a bounded outcome such as a PDF download, an on-site report capture, or delayed email delivery. It uses persisted route information only as an input to planning; failures and route changes remain observable and retry ownership stays with the orchestrator.

For every retained PDF outcome, the canonical acquisition-to-ingest handoff
rechecks the local file and its MD5, records a bounded source-identity
observation, and upserts the report record before enqueuing `source_ingest`.
The report ID is the retained Drive ID when available and otherwise a
content-derived `acquired-<md5>` value; it is never substituted with the source
identity. Direct, browser, and mailbox routes therefore share one deterministic
idempotency key (`<md5>:source_ingest:<processing-version>`). A repeated URL or
mirror URL with the same bytes reuses the source identity and enqueue record,
while different content remains distinct even when its title is the same. A
reused retained Drive ID with changed bytes fails closed instead of rebinding
the report record.

For an email-gated browser route, terminal stabilization polls only after recorded submission evidence, a transient terminal condition, or an explicit assist trigger. A route with no recorded submission finishes without the email polling schedule, and timeout-recovery attempts are bounded by the request timeout as well as the recovery safety cap. A terminal page with an explicit email-delivery confirmation is accepted as verified evidence even when a timed-out browser response omitted the earlier form-field record.

Eligible browser preflight opens the same managed browser profile used by Browser
Use. When preflight confirms a direct PDF it closes that browser without
constructing an agent. After an escalation, acquisition first attempts every
matching fresh, publisher-specific route playbook that is fully executable:
each step must have a supported deterministic action and locator plus a
machine-checkable URL or visible-text postcondition. Its terminal result is
passed through the same artifact/submission finalizer used by Browser Use, so a
PDF, email submission, or on-site capture is never accepted on the basis of a
click alone. A completed, verified playbook accepts the acquisition with zero
Browser Use model calls. Missing executable evidence, a postcondition mismatch,
an executor error, or failed terminal verification is logged as drift and
continues to the unchanged Browser Use path. Generic and historical
prompt-only playbooks are therefore guidance only and always fall back. The
live browser lease is process-local, so both deterministic execution and the
Agent handoff retain cookies, local storage, session ownership, shutdown,
session-reuse finalization, and browser-launch accounting.

Each governed acquisition attempt now retains a scalar resource envelope in the
reports store: elapsed time, route family and policy hash, browser launch/step
and screenshot counts, browser-model token/cost totals read from the canonical
usage ledger, Drive/mailbox counters, retry count, typed terminal outcome, and
the verified artifact hash when one exists. Telemetry reads the canonical
ledger by the exact `(run_id, task_id)` acquisition scope, including Browser Use
and grounded form-value derivation model calls. The same task identity is
retained for browser reservations/final actuals and direct side-effect events,
so sequential and parallel acquisitions in one run cannot inherit each
other's calls, tokens, launches, retries, or cost. Browser launches are
recorded only from durable actual usage; an attempt with no real launch records
zero. Missing historic or unavailable measurements are marked as incomplete
rather than read as zero. The report-store
aggregate groups this evidence by publisher and route, exposing sample size,
success rate, cost per verified acquisition, median/p95 time, browser steps per
success, terminal failures, and avoided browser/model operations.

`browser_download.route_suppression` can skip a browser route before browser or
model work only after at least three compatible attempts meet its configured
typed terminal-failure threshold. Its decision is policy-hash-bound and
TTL-limited; `revalidate_route_policy` bypasses the decision for an explicit
operator retry. A successful explicit revalidation supersedes the old decision
without deleting either the suppression history or resource records. Direct
routes and the existing CAPTCHA, identity, and hard-blocker policies remain
independent controls.

An explicitly scoped reliability profile may set browser acquisition retries to
zero when a timed-out deterministic route is being measured rather than
recovered. The timeout remains a typed terminal result with its route,
timestamps, and resource envelope; this run-only policy does not alter the
normal acquisition default or suppress a future explicit revalidation.

Successful browser-route promotion preserves its route prose, observed evidence labels,
and version history for audit while also retaining executable action data where the run
observed it. A promoted action must itself be explicitly verified with observed
post-action evidence. The promotion service ranks locators by role/name, label, HTML
name, data attribute, CSS, then visible text, and retains observed URL/text
postconditions. Form values are represented only by an `identity.<key>` placeholder in
the playbook; no email address or other personal identity value is persisted. Failed,
blocked, missing, and unverified actions remain only in the original route evidence and
are never written as active playbook steps.

Use `python -m src.cli download-report <url>` for an explicit acquisition request and `python -m src.cli browser-doctor` to diagnose the local browser runtime. Browser, Drive, and mailbox prerequisites are covered in [credentials](../ops/credentials.md); recovery guidance is in [troubleshooting](../ops/troubleshooting.md).
