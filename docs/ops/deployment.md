# Deployment and Packaging

> **Documentation type:** Operational procedure
> **Canonical topic:** Deployment and packaging
> **Update trigger:** Packaging, deployment, or rollback mechanism changes.

MarketLense does not use a documentation-site deployment. Python runtime configuration is supplied by the deployment environment; WordPress theme and plugin artifacts are packaged from the repository.

Build WordPress upload archives from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\build-plugin-zip.ps1
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\build-theme-zip.ps1
```

The outputs are `Wordpress/dist/marketlense-core.zip` and `Wordpress/dist/marketlense.zip`. Validate the WordPress subproject before deploying and follow the provisioning and rollback sequence in [WordPress operations](wordpress.md). Quality release gates and evidence process are in [release gates](../quality/release-gates.md) and [evidence](../quality/evidence.md).
