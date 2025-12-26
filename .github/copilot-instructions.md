<!-- Guidance for AI coding agents working on Market Lense -->
# Copilot instructions — Market Lense

Purpose: help an AI agent become productive quickly by describing the architecture, key workflows, and project-specific patterns.

- **Big picture**: the `app/` package ingests PDFs from Google Drive, extracts the first ~5 pages of text, asks OpenAI for a STRICT JSON analysis, finds candidate charts/tables, ranks them, crops images, and renders a final HTML report using Jinja templates.
  - Entrypoint: the CLI command `ingest` in [app/cli.py](app/cli.py).
  - OpenAI integration: [app/openai_client.py](app/openai_client.py) extracts text (pypdf) and calls the OpenAI Chat Completions API using `response_format={"type":"json_object"}` — expect and enforce strict JSON.
  - Ranking: [app/rank.py](app/rank.py) sends candidate summaries to the model and writes raw responses to `debug/` for inspection.
  - State: processed files are recorded in SQLite at `STATE_DB` (default `./state/index.sqlite`) via [app/state.py](app/state.py).
  - Templates: final HTML produced via Jinja template at `templates/report.html.j2` (see `app/render.py`).

- **Environment & run**
  - Required env vars (loaded via `.env` in [app/config.py](app/config.py)): `GOOGLE_SERVICE_ACCOUNT_JSON`, `GDRIVE_FOLDER_ID`, `OPENAI_API_KEY`. Defaults: `OPENAI_MODEL` defaults to `gpt-5` and `BATCH_LIMIT` defaults to `20`.
  - Typical run (from repo root):

```bash
python -m app.cli ingest --limit 3
```

- **Project conventions and guarantees**
  - Models must return strict JSON. The code uses `response_format={"type":"json_object"}` wherever possible and performs defensive validation (`_validate_payload` in `app/openai_client.py`). Follow the same approach when adding new prompts.
  - When calling models to produce structured outputs, include a small schema or explicit cardinality (e.g., 5 insights). See `PROMPT` and `SCHEMA` in [app/openai_client.py](app/openai_client.py).
  - Ranking responses are saved under `debug/` with timestamps — use these files when debugging model output parsing.

- **Key integration points (code to inspect when changing behavior)**
  - Drive: `app/drive.py` (functions: `drive_client`, `list_pdfs`, `ensure_download`, `effective_md5`) — responsible for download + MD5 checks.
  - Text extraction: `app/openai_client.py::_extract_text_first_pages` uses `pypdf` and truncates to ~80k chars.
  - Candidate detection + data model: `app/candidates.py` (`Candidate` dataclass) and `app/extract.py` (`collect_candidates`).
  - Cropping & figure extraction: `app/crop.py`, `app/figure.py` (produces PNGs used in templates).
  - Rendering: `app/render.py` (Jinja environment) and template at `templates/report.html.j2`.

- **Debugging tips**
  - If a run fails to parse model output, check `debug/rank_raw_*.txt` and OpenAI logs; code includes wide defensive parsing in `app/rank.py`.
  - To re-run a file, remove its entry from the SQLite DB (`state/index.sqlite`) or run with a modified `CACHE_DIR` / `STATE_DB` in env.

- **When editing or adding prompts**
  - Mirror existing style: small, strict instruction with explicit schema (see `PROMPT`/`SCHEMA` in `app/openai_client.py`).
  - Preserve `response_format` usage and add defensive parsing+debug dump of raw model output.

If anything here is unclear or you'd like more detail in a particular area (Drive auth, template variables, or prompt decisions), tell me which part to expand.
