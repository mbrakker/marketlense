# Credentials and Access

> **Documentation type:** Operational procedure
> **Canonical topic:** Credentials and external access
> **Update trigger:** Provider, authentication mode, secret name, or credential-recovery procedure changes.

Store local secrets in `.env`; production and CI inject the same environment variables from their managed secret stores. `.env`, Google OAuth client files, Google OAuth token files, and runtime directories are ignored by Git. `.env.example` is the committed inventory of supported secret names and contains no real values. Never copy secret values into source, YAML, documentation, logs, tests, fixtures, screenshots, errors, or generated references. Application code resolves credentials through `src/services/config_service.py`.

| Boundary | Required when | Configuration or environment |
| --- | --- | --- |
| LLM provider | Analysis, OCR, browser model use, or other provider calls | `OPENAI_API_KEY`; optional `OPENROUTER_API_KEY` fallback |
| Browser form identity | A gated publisher requires an authorized operator identity | Untracked identity YAML selected by `BROWSER_DOWNLOAD_IDENTITY_CONFIG_PATH`; the committed `src/config/browser_download_identity.yaml` is value-free |
| Google Drive | Listing, download, or archival | `ingest.drive` OAuth/service-account settings and matching local secret material |
| IMAP / Gmail | Email-delivered report acquisition | `mailbox_acquisition` plus IMAP secrets or Gmail OAuth files |
| WordPress | Publishing, provisioning, or hosted checks | `WP_SITE_URL` and either `WP_BEARER_TOKEN` or `WP_USERNAME` plus `WP_APP_PASSWORD` |

For user Drive OAuth, run:

```powershell
python -m src.cli drive-oauth-login --client-json .\google_oauth_client.json --token-json .\google_oauth_token.json
```

The Drive service refreshes a valid authorized-user token for configured calls. If a credential becomes invalid, replace or re-authorize the local secret material and rerun a bounded plan or workflow; do not edit provider tokens into YAML. See [troubleshooting](troubleshooting.md) for failure routing.

## Browser form identity

Browser form values are sensitive identity data, including business email,
phone, organization, location, and publisher-specific qualification values.
The committed [`browser_download_identity.yaml`](../../src/config/browser_download_identity.yaml)
contains only schema, field labels, aliases, select-option aliases, consent
policy, and publisher host mappings. Its `null` entries are deliberate
synthetic placeholders: they are safe to copy, cannot supply a value, and must
not be replaced in the tracked file.

To enable authorized form completion, copy that template to the ignored local
path below (or another secret-managed path), populate only the required
authorized values, and select it through `.env` or the deployment environment:

```powershell
Copy-Item src/config/browser_download_identity.yaml src/config/browser_download_identity.local.yaml
# Edit only the copied file with authorized values; do not commit it.
$env:BROWSER_DOWNLOAD_IDENTITY_CONFIG_PATH = "src/config/browser_download_identity.local.yaml"
```

The loader preserves the same field mappings and publisher overrides from the
selected profile. An absent or `null` value is never invented: if a rendered
form requires it, acquisition returns the typed
`blocked_missing_identity_field` outcome. Standard logs and retained
acquisition evidence store only redacted values, identity references, or typed
blocker categories, never the configured value itself.
