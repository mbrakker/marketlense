# Local Development

> **Documentation type:** Operational procedure
> **Canonical topic:** Local development setup
> **Update trigger:** Supported Python version, dependency installation, local entrypoint, or configuration bootstrap changes.

## Prerequisites

- CPython 3.12. Native dependency installation has been verified on Windows x64
  with CPython 3.12.10 and Ubuntu 24.04 x86_64 with CPython 3.12.3. Although
  project metadata allows newer Python releases, Python 3.13 and later have not
  been verified against the canonical lock.
- A local virtual environment.
- Credentials only for workflows that contact their external systems.

## Setup

Codex Cloud uses the repository bootstrap and its hash-locked dependencies; see
[Codex Cloud environment](codex-cloud-environment.md). Install the canonical
lock with hash verification, then install the checked-out vendored browser-use
package in editable mode using the already-installed, hash-locked build tools.

Linux:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-index --no-build-isolation --editable tools/browser-use
.venv/bin/python -m pip check
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python.exe -m pip install --no-index --no-build-isolation --editable .\tools\browser-use
.venv\Scripts\python.exe -m pip check
```

The first install verifies every third-party artifact against `requirements.lock`.
The editable source is the checked-out repository tree rather than a standalone
wheel, so pip cannot verify it as a hashed distribution. Its Git revision
provides source provenance; its build requirements (`hatchling` and `editables`)
are exact-pinned in the vendored `pyproject.toml` and hash-locked. The editable
command disables build isolation to use those installed tools and disables the
package index so it fails if a required dependency is missing. It still resolves
and checks the package dependencies; do not add `--no-deps` or disable hash
verification for the lock install.

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
