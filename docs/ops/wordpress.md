# WordPress Operations

> **Documentation type:** Operational procedure
> **Canonical topic:** WordPress operations
> **Update trigger:** Local sync, packaging, provisioning, verification, publishing, or rollback procedure changes.

The WordPress subproject contains the `marketlense-core` plugin and `marketlense` block theme. Its front-end shortcode and rendering contract is documented separately in [README_WORDPRESS.md](../../README_WORDPRESS.md); the implementation map is [architecture/wordpress-front-end.md](../architecture/wordpress-front-end.md).

## Local Studio workflow

The known local install is `C:\Users\Михаил\Studio\marker-lense`, served at `http://localhost:8881/` when Studio is running. Keep theme and plugin targets as real directories: do not symlink the block theme.

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\sync-local-wordpress.ps1 `
  -LocalWpPath 'C:\Users\Михаил\Studio\marker-lense'
```

Add `-Watch` for continuous synchronization. Use `-SyncTarget theme` or `-SyncTarget plugin` to limit the copy.

## Provision and verify

```powershell
python Wordpress/scripts/marketlense_admin.py provision
python Wordpress/scripts/marketlense_admin.py seed-homepages
python Wordpress/scripts/marketlense_admin.py sync-profiles
python scripts/ci/check_wordpress_subproject.py
```

Add `--dry-run` to the administration commands to validate selection without external mutation. The subproject check performs static PHP/shell/template checks; optional live smoke behavior is controlled by its documented environment prerequisites.

## Publish and rollback

Set WordPress credentials as described in [credentials](credentials.md). Publish through the Python boundary with `python -m src.cli publish-wp`; do not use WordPress to synthesize report intelligence. The publisher writes `ml_content_sha256` with the canonical `ml_file_id` and card/source metadata, so the authenticated canary readback can verify exact post content without retaining the body in logs or idempotency records.

Before it resolves terms, uploads media, or creates a post, the publisher authenticates to the target post-type schema and verifies the registered proof fields. `ml_file_id` and `ml_content_sha256` are mandatory for every route; `ml_report` additionally requires its source-attribution fields. A missing field produces the typed `preflight_blocked` result with no WordPress write request, which protects a stale plugin deployment from creating an unverifiable post.

For a release canary, pass the fixed cohort manifest and `--require-full-validation-manifest`, publish only to the approved target, and rerun the same command unchanged. Confirm that the first outcome contains the typed readback proof and that the repeat reports `requested_write_count=0` and `actual_write_count=0`. If publication must be reversed, use the site’s normal authenticated administrative process for the specific post, retain the source run and artifact evidence, and correct the pipeline cause before republishing. The publisher never deletes a post automatically after a readback failure; the typed rollback states are reserved for an explicitly approved rollback workflow, rather than risking deletion when transaction identity is incomplete.
