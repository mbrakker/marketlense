# Local Development

> **Documentation type:** Operational procedure
> **Canonical topic:** Local development setup
> **Update trigger:** Supported Python version, dependency installation, local entrypoint, or configuration bootstrap changes.

## Prerequisites

- CPython 3.12 or later, as declared in `pyproject.toml`.
- A local virtual environment.
- Credentials only for workflows that contact their external systems.

## Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
Copy-Item src\config\app.example.yaml src\config\app.local.yaml
```

Keep machine-specific values in `src/config/app.local.yaml` and secrets in `.env` or the process environment. Do not commit either secret material or generated runtime output.

## Start locally

```powershell
python -m src.cli --help
python -m src.cli plan "ingest new reports"
streamlit run src/streamlit_app.py
```

`plan` is safe to use before credentials are available because it produces an execution plan without launching a workflow. To process reports, complete [configuration](configuration.md) and [credentials](credentials.md), then run a bounded command such as `python -m src.cli ingest --limit 1`.

For WordPress local development, use [WordPress operations](wordpress.md). For test and gate commands, use [quality testing](../quality/testing.md).
