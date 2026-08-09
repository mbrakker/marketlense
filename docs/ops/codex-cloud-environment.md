# Codex Cloud Environment

> **Documentation type:** Operational procedure
> **Canonical topic:** Credential-free Codex Cloud setup
> **Update trigger:** Supported Python version, dependency lock, bootstrap command, environment-variable inventory, or credential boundary changes.

This procedure assumes a clean checkout is the complete source of code and
dependency truth. It does not require or create `.env`, copy a local overlay, or
restore ignored runtime state.

## Setup

From the repository root, run:

```bash
./scripts/bootstrap_codex_cloud.sh
```

The script requires CPython 3.12, creates the ignored `.venv` when necessary,
installs `requirements.lock` with pip hash checking, and runs `pip check`. It is
safe to rerun. Use `.venv/bin/python` explicitly for every subsequent Python
command; do not rely on shell activation.

Dependency installation requires HTTPS access to `pypi.org` and
`files.pythonhosted.org`. No application-provider domain is needed for setup.

## Environment variables

No environment variable is required for setup, the default test suite, static
quality gates, CLI help, or workflow planning. These optional non-secret
variables select committed configuration or runtime locations when an operator
needs an override:

- `MARKET_LENSE_CONFIG_PATH`, `MARKET_LENSE_CONFIG_PROFILE`, and
  `MARKET_LENSE_PRODUCER_COMMIT` select configuration and provenance.
- `OUTPUT_DIR`, `CACHE_DIR`, `STATE_DB`, `REPORTS_DB`, `COST_LEDGER_PATH`,
  `LLM_USAGE_DB_PATH`, `MARKET_LENSE_LOG_DIR`, `MAILBOX_OUTPUT_DIR`,
  `BROWSER_DOWNLOAD_OUTPUT_DIR`, and `PUBLISHER_DISCOVERY_OUTPUT_DIR` select
  runtime locations.
- `GOOGLE_DRIVE_AUTH_MODE`, `GMAIL_USER_ID`, `IMAP_HOST`, `IMAP_PORT`,
  `IMAP_USER`, `IMAP_MAILBOX`, `WP_SITE_URL`, `WP_ADMIN_URL`, `WP_USERNAME`,
  `WP_SSL_VERIFY`, and `WP_CA_BUNDLE_PATH` are non-secret external-boundary
  settings. They are required only by the corresponding selected workflow when
  an equivalent committed/local configuration value is absent.

The following are secret values or paths to secret credential material. Define
only those required by an explicitly authorized external workflow; never invent
values or commit them:

- LLM providers: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`.
- Google Drive: `GOOGLE_SERVICE_ACCOUNT_JSON`, or
  `GOOGLE_OAUTH_CLIENT_JSON` and `GOOGLE_OAUTH_TOKEN_JSON`.
- Gmail/mailbox acquisition: `GMAIL_OAUTH_CLIENT_PATH` and
  `GMAIL_OAUTH_TOKEN_PATH`, or `IMAP_PASS` (with the non-secret IMAP settings).
- WordPress: `WP_BEARER_TOKEN`, or `WP_APP_PASSWORD` with `WP_USERNAME`.

`OPENROUTER_HTTP_REFERER` is optional request metadata, not a credential. The
committed `.env.example` remains the concise secret inventory; this cloud setup
does not create `.env`.

## Credential boundary

The following commands are safe in a clean checkout and do not contact
application providers:

```bash
.venv/bin/python -m src.cli --help
.venv/bin/python -m src.cli plan "ingest new reports"
.venv/bin/python -m pytest -m "not integration"
.venv/bin/python scripts/ci/check_dependency_consistency.py
.venv/bin/python scripts/ci/check_formatting.py
.venv/bin/python scripts/ci/check_ruff_lint.py
.venv/bin/python scripts/ci/run_type_check.py
```

Commands that perform report discovery or acquisition, Drive listing/download
or archival, Gmail/IMAP polling, LLM analysis/OCR/browser work, WordPress
publication, or live/integration/canary validation require the matching external
credentials and explicit authorization. Do not run them as part of cloud
bootstrap. In particular, do not run the real 20-report canary or any publisher,
Gmail, Google Drive, OpenAI API, or WordPress operation from this procedure.
