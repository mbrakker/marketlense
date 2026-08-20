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
click alone. On a reused async Browser Use session, the same executor supports
`open`/`navigate`, `click`/`submit`, `fill`/`type`, `select`, and `verify` with
CSS, role/name, label, field-name, data-attribute, or visible-text locators as
applicable. Role/name matching is exact and must resolve exactly one current
element; it never uses a fuzzy match or the first control. For `fill`/`type`, a
role locator is limited to a native text input or textarea with the observed
`textbox` or `searchbox` role. For `select`, it is limited to an observed
`combobox` or `listbox` that still resolves to a native `<select>`. Unsupported
or drifted custom controls fall through to Browser Use on the same session.
Form values are accepted only from `${identity.<key>}` references.
Every locator/control error and every URL/text postcondition mismatch is route
drift, so execution falls through to Browser Use without replacing the current
browser, page, cookies, or storage. A completed, verified playbook accepts the
acquisition with zero Browser Use model calls. Missing executable evidence, a
postcondition mismatch,
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

During a Browser Use acquisition, MarketLense also compares a deterministic
fingerprint at each Agent turn. It includes the effective URL, actionable
DOM/form state, typed blocker state, document candidates, document/network
evidence, and confirmation signals. The Agent stops only after three
consecutive equivalent fingerprints; one stalled turn never terminates a
route. A navigation, form-state change, new document candidate, network
document evidence, confirmation signal, or blocker-state change resets the
counter. If an actionable DOM representation is absent, empty, or cannot be
read, no-progress detection fails open for the rest of that acquisition: its
empty fingerprint does not advance the stall counter and cannot yield
`blocked_no_progress`. The stop is finalized as the typed `blocked_no_progress`
terminal result with bounded scalar/hash evidence, so it remains auditable and
follows the ordinary retained route-learning and three-compatible-attempt
suppression rules. Raw DOM, form values, screenshots, prompts, and model prose
are never put in the standard no-progress event or route record.

An explicitly scoped reliability profile may set browser acquisition retries to
zero when a timed-out deterministic route is being measured rather than
recovered. The timeout remains a typed terminal result with its route,
timestamps, and resource envelope; this run-only policy does not alter the
normal acquisition default or suppress a future explicit revalidation.

Successful browser-route promotion preserves route prose and version history for audit,
but treats all model-supplied route-step locator and postcondition fields as untrusted.
The browser runtime separately records each successfully resolved/acted-on locator and
the immediately following URL/title state. Promotion is all-or-nothing and uses only
that execution trace: every action must have its own action-bound locator and URL/text
postcondition evidence. A later terminal state is associated only with the final action;
it cannot validate an earlier selector. The promotion service ranks runtime-observed
locators by role/name, label, HTML name, data attribute, CSS, then visible text. Form
values are represented only by an `${identity.<key>}` placeholder in the playbook; no
email address or other personal identity value is persisted. Before an active playbook
is written, promotion checks that its action/locator pair is supported by the
deterministic executor, including the native role constraints for form controls.
Failed, multi-action,
missing, and unverified records (including a final submit) cause a typed
`not_promotable` result and leave no active playbook write.

For Browser Use history, a model `click` is recorded as semantic `submit` only when
the runtime-resolved native DOM element is a form submit control: a `button` with an
implicit or explicit submit type, or an `input` with `type=submit` or `type=image`.
The model response, action prose, accessible name, and ARIA role do not promote a
normal button or link; an email route therefore satisfies terminal-submit validation
only with that resolved-control evidence.

When a publisher page embeds a public Adobe InDesign Publish Online report, acquisition
does not treat incidental newsletter forms as a report gate. It verifies the publisher
page's Adobe viewer URL, reads the viewer-provided version prefix, then captures the
public `content.json` text asset into an HTML handoff plus a retained raw JSON audit
artifact. The capture is accepted only when the returned asset has multiple text-bearing
pages and substantial text; unavailable, malformed, or truncated Adobe content falls
back to the normal browser path rather than being saved as a partial report.

Use `python -m src.cli download-report <url>` for an explicit acquisition request and `python -m src.cli browser-doctor` to diagnose the local browser runtime. Browser, Drive, and mailbox prerequisites are covered in [credentials](../ops/credentials.md); recovery guidance is in [troubleshooting](../ops/troubleshooting.md).
