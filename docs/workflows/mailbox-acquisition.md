# Mailbox Acquisition

> **Documentation type:** Current reference
> **Canonical topic:** Mailbox acquisition workflow
> **Update trigger:** Mail provider, delivery matching, attachment handling, or deferred-workflow changes.

When a publisher delivers a requested report by email, MarketLense persists a delivery request and checks the configured mailbox through the mailbox acquisition service. Matching is scoped to the request and retained source context; successful PDF attachments or contained PDF files can re-enter the normal report acquisition workflow.

Before the browser can submit an email form, the orchestrator stores a non-pollable `submission_started` intent with the recipient, report, publisher, source identity, and generation. Only a browser-confirmed submission promotes that row to `pending` and stores the exact confirmation timestamp as its mailbox watermark. If confirmation persistence is interrupted, replay holds the existing intent instead of submitting again. The durable acquisition queue creates mailbox work only after the verified row has a request ID, timestamp, source identity, and publisher identity. The mailbox child copies its source URL, title, publisher, recipient, and timestamp from that row. Replays do not update the stored watermark or reopen a completed request; a distinct workflow submission starts a new generation. `email_required` creates no mailbox child or pollable request. Mailbox payload schema 3.0 carries the persisted identity, and legacy 1.0 or 2.0 jobs fail closed because they lack the complete verified identity.

IMAP polling opens mailboxes read-only and fetches messages by UID with `BODY.PEEK[]`, so inspection does not mark mail as read. IMAP message identities are opaque and scoped to the account, mailbox, UIDVALIDITY, and UID; a UIDVALIDITY change resets the seen-message cursor. Legacy sequence-number IDs are ignored once this identity format is used. Receipt time comes from IMAP INTERNALDATE; the sender's Date header is not used to decide whether delivery occurred after a request.

Mailbox link candidates retain the exact URL bytes from each HTML `href` together with bounded anchor and nearby text. Candidate relevance uses that link-local context so unrelated message text cannot make an unrelated link appear report-related. Signed URL paths and query strings are preserved during normalization; structured log redaction removes signed query values before logging.

Configure `mailbox_acquisition` and the required IMAP or Gmail OAuth credentials before use. The CLI command `python -m src.cli poll-mail-report` performs an explicit poll. See [credentials](../ops/credentials.md) and [recovery](../ops/recovery.md).
