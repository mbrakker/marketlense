---
name: dependency-upgrade
description: Safely evaluate a MarketLense dependency addition or upgrade; not for ordinary application behavior changes without dependency metadata changes.
---

# Dependency upgrade

Use when dependency manifests, lockfiles, vendored development tooling, or a
third-party provider/library version changes.

## Entry points and invariants

- `pyproject.toml`, `requirements*.txt`, and their lock/constraint artifacts are
  the dependency source of truth; do not add a runtime dependency for an
  agent-only workflow.
- Preserve the architecture policy's canonical external-system boundaries,
  Python compatibility, deterministic installation metadata, and production
  import isolation.

## Inspect and verify

Read the changed manifest/lockfile, direct import sites, license/security and
provider compatibility evidence, and existing tests for the integration. Run:

```powershell
python scripts/ci/check_dependency_consistency.py
python -m pytest -q tests/test_dependency_consistency.py
python scripts/ci/run_type_check.py
```

Then run the narrowest boundary test for each changed direct dependency; use a
controlled integration check only when local fakes cannot establish
compatibility. Record old/new versions, direct consumers, runtime versus
development scope, resolved metadata, exact checks, and rollback path.
Completion requires no unexpected production import or lock drift and a passing
completion gate; high-risk upgrades escalate through the aggregate quality gate.
