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
[Codex Cloud environment](codex-cloud-environment.md). The local Windows setup is:

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
Copy-Item src\config\app.example.yaml src\config\app.local.yaml
```

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
`browser_use` loader. Run the doctor through the environment that will execute
acquisition (normally `.venv`): it checks the worker subprocess import before
opening a bounded browser session and reports the interpreter, virtualenv,
module path, and supported vendored-package checksum.

For WordPress local development, use [WordPress operations](wordpress.md). For test and gate commands, use [quality testing](../quality/testing.md).
