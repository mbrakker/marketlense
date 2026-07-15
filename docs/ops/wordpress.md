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

Set WordPress credentials as described in [credentials](credentials.md). Publish through the Python boundary with `python -m src.cli publish-wp`; do not use WordPress to synthesize report intelligence. If publication must be reversed, use the site’s normal authenticated administrative process for the specific post, retain the source run and artifact evidence, and correct the pipeline cause before republishing.
