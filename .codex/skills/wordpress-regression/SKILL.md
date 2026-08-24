---
name: wordpress-regression
description: Verify MarketLense WordPress service, theme, plugin, or published-UI changes; not for generation-only editorial changes.
---

# WordPress regression

Use after changing `Wordpress/`, WordPress contracts, publication orchestration,
the WordPress service, REST behavior, or public rendering/navigation.

## Entry points and invariants

- `src/services/wordpress_service.py` is the canonical WordPress boundary;
  implementation remains under `src/services/_wordpress_service/`.
- Keep publication sequencing in `src/orchestrators/publish_orchestrator.py`.
- Preserve idempotent publication, typed failures, destination identity,
  read-back verification, public contract compatibility, and explicit human
  publication approval. Do not make live public writes for routine testing.

## Inspect and verify

Read the affected contract, service/orchestrator, matching WordPress source,
and public-render behavior. Select focused checks by changed capability:

```powershell
python -m pytest -q tests/test_wordpress_service.py tests/test_wordpress_public_render_boundary.py
python -m pytest -q tests/test_wordpress_publish_entity_rest_verification.py tests/test_wordpress_report_rendering_contract.py
python -m pytest -q tests/test_wordpress_public_navigation.py tests/test_wordpress_theme_packaging.py
python scripts/ci/check_wordpress_subproject.py
```

Run `check_wordpress_staging_rest_gate.py` only with an explicitly authorized,
safe staging target. Record test/staging target, publication approval state,
read-back result, and skipped live validation. Completion requires focused
coverage plus completion-gate evidence.
