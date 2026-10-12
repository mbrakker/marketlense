# Local Development

> **Documentation type:** Operational procedure
> **Canonical topic:** Local development setup
> **Update trigger:** Supported Python version, dependency installation, local entrypoint, or configuration bootstrap changes.

## Prerequisites

- CPython 3.12 or later, as declared in `pyproject.toml`.
- A local virtual environment.
- Credentials only for workflows that contact their external systems.

## Setup

Codex Cloud uses the repository bootstrap and its hash-locked dependencies; see
[Codex Cloud environment](codex-cloud-environment.md). The canonical lock is
hash-verified for the CPython 3.12 Linux environment used by CI. Its
platform-specific hashes do not currently cover Windows wheels: a clean
CPython 3.12 Windows install with `--require-hashes` fails at the Windows
`aiohttp==3.14.3` wheel. Do not disable hash checking to work around this. A
reproducible Windows bootstrap is unavailable until the lock carries verified
Windows artifact hashes.

Keep machine-specific values in `src/config/app.local.yaml` and secrets in `.env` or the process environment. Do not commit either secret material or generated runtime output.

## Dependency security updates

When a direct dependency has a security advisory, update its exact source pin and
the matching hash-locked entry together. Validate the change with
`python scripts/ci/check_dependency_consistency.py` before installing or
publishing it; CI rejects declarations that drift from `requirements.lock`.

## Start locally

```powershell
python -m src.cli --help
python -m src.cli plan "ingest new reports"
streamlit run src/streamlit_app.py
```

`plan` is safe to use before credentials are available because it produces an execution plan without launching a workflow. To process reports, complete [configuration](configuration.md) and [credentials](credentials.md), then run a bounded command such as `python -m src.cli ingest --limit 1`.

Browser doctor and browser acquisition use the same interpreter and canonical
`browser_use` loader. The editable install above provides the supported
vendored runtime; Playwright is not a required runtime dependency. Run the doctor
through the environment that will execute acquisition (normally `.venv`): it
checks the worker subprocess import before opening a bounded browser session and
reports the interpreter, virtualenv, module path, and supported vendored-package
checksum. The capability preflight checks runtime imports and browser assets
without opening a browser.

For WordPress local development, use [WordPress operations](wordpress.md). For test and gate commands, use [quality testing](../quality/testing.md).
