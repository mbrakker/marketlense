# Mailbox Acquisition

> **Documentation type:** Current reference
> **Canonical topic:** Mailbox acquisition workflow
> **Update trigger:** Mail provider, delivery matching, attachment handling, or deferred-workflow changes.

When a publisher delivers a requested report by email, MarketLense persists a delivery request and checks the configured mailbox through the mailbox acquisition service. Matching is scoped to the request and retained source context; successful PDF attachments or contained PDF files can re-enter the normal report acquisition workflow.

Configure `mailbox_acquisition` and the required IMAP or Gmail OAuth credentials before use. The CLI command `python -m src.cli poll-mail-report` performs an explicit poll. See [credentials](../ops/credentials.md) and [recovery](../ops/recovery.md).
