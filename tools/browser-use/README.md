# Vendored Browser Use

This directory contains a vendored copy of Browser Use inside the Market Lense repository.

Market Lense is the primary project. The root repository `AGENTS.md`, root README, and root repo conventions take precedence over any upstream Browser Use guidance when working in this monorepo.

This vendored subtree keeps Browser Use package and CLI behavior intact, including the existing editable install path and `browser-use` console scripts. It is preserved here as a tool dependency, not as the authoritative top-level project in this workspace.

Preserved upstream reference files:

- `UPSTREAM_README.md`
- `UPSTREAM_AGENTS.md`
- `UPSTREAM_CLAUDE.md`
- `UPSTREAM_CLOUD.md`

Local usage from the Market Lense virtualenv:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .\tools\browser-use
.\.venv\Scripts\browser-use.exe --help
```

Contributors should not follow upstream standalone-repository workflow instructions from the preserved reference files unless they are intentionally syncing or auditing the upstream project.
