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
session-reuse finalization, and browser-launch accounting. Async deterministic
form handling never closes or replaces that lease: a helper failure resumes
Browser Use on the same browser, and the outer acquisition runner remains its
sole lifecycle owner. For browser email forms, a deterministic submit returns
early only after the canonical terminal-confirmation evidence verifies email
delivery. A submitted-but-unverified or ambiguous page is handed to Browser
Use through that same live browser session; only an unknown required identity
value returns the typed blocker without invoking Browser Use or guessing a
value. A terminally verified deterministic submit constructs no Browser Use
agent and therefore cannot be submitted again by that fallback path.

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

Before route planning or browser preflight, acquisition also evaluates one
fresh exact remembered terminal blocker. It suppresses only a verified browser
route whose canonical terminal evidence is explicitly `blocked`, repeats the
same typed blocker label, is within route-memory TTL, and is enabled by the
current suppression policy. Stale, publisher-scope, inferred, weak, or
policy-incompatible evidence never suppresses the route. An explicit
`revalidate_route_policy` always continues to acquisition. A configured
CAPTCHA manual handoff also continues to acquisition, and removes CAPTCHA from
the empirical route-suppression cohort so an operator can complete the visible
challenge.

For all other cases, `browser_download.route_suppression` can skip a browser
route before browser or model work only after at least three compatible attempts
meet its configured typed terminal-failure threshold. Its decision is
policy-hash-bound and TTL-limited; a successful explicit revalidation
supersedes the old decision without deleting either the suppression history or
resource records. Direct routes and the existing identity and hard-blocker
policies remain independent controls.

An explicitly scoped reliability profile may set browser acquisition retries to
zero when a timed-out deterministic route is being measured rather than
recovered. The timeout remains a typed terminal result with its route,
timestamps, and resource envelope; this run-only policy does not alter the
normal acquisition default or suppress a future explicit revalidation.

Successful browser-route promotion preserves its route prose, observed evidence labels,
and version history for audit while also retaining executable action data where the run
observed it. Promotion is all-or-nothing: every action must be explicitly verified with
its own action-bound locator evidence and URL/text postcondition evidence. Terminal or
global evidence cannot validate an earlier selector. The promotion service ranks locators
by role/name, label, HTML name, data attribute, CSS, then visible text. Form values are
represented only by an `${identity.<key>}` placeholder in the playbook; no email address
or other personal identity value is persisted. Failed, blocked, missing, and unverified
actions (including a final submit) cause a typed `not_promotable` result and leave no
active playbook write.

When a publisher page embeds a public Adobe InDesign Publish Online report, acquisition
does not treat incidental newsletter forms as a report gate. It verifies the publisher
page's Adobe viewer URL, reads the viewer-provided version prefix, then captures the
public `content.json` text asset into an HTML handoff plus a retained raw JSON audit
artifact. The capture is accepted only when the returned asset has multiple text-bearing
pages and substantial text; unavailable, malformed, or truncated Adobe content falls
back to the normal browser path rather than being saved as a partial report.

Use `python -m src.cli download-report <url>` for an explicit acquisition request and `python -m src.cli browser-doctor` to diagnose the local browser runtime. Browser, Drive, and mailbox prerequisites are covered in [credentials](../ops/credentials.md); recovery guidance is in [troubleshooting](../ops/troubleshooting.md).
