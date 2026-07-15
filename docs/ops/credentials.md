# Credentials and Access

> **Documentation type:** Operational procedure
> **Canonical topic:** Credentials and external access
> **Update trigger:** Provider, authentication mode, secret name, or credential-recovery procedure changes.

Store secrets in `.env`, a CI secret store, or process environment. `.env`, Google OAuth client files, Google OAuth token files, and runtime directories are ignored by Git. Never copy secret values into documentation, logs, fixtures, or generated references.

| Boundary | Required when | Configuration or environment |
| --- | --- | --- |
| LLM provider | Analysis, OCR, browser model use, or other provider calls | `OPENAI_API_KEY`; optional `OPENROUTER_API_KEY` fallback |
| Google Drive | Listing, download, or archival | `ingest.drive` OAuth/service-account settings and matching local secret material |
| IMAP / Gmail | Email-delivered report acquisition | `mailbox_acquisition` plus IMAP secrets or Gmail OAuth files |
| WordPress | Publishing, provisioning, or hosted checks | `WP_SITE_URL` and either `WP_BEARER_TOKEN` or `WP_USERNAME` plus `WP_APP_PASSWORD` |

For user Drive OAuth, run:

```powershell
python -m src.cli drive-oauth-login --client-json .\google_oauth_client.json --token-json .\google_oauth_token.json
```

The Drive service refreshes a valid authorized-user token for configured calls. If a credential becomes invalid, replace or re-authorize the local secret material and rerun a bounded plan or workflow; do not edit provider tokens into YAML. See [troubleshooting](troubleshooting.md) for failure routing.
