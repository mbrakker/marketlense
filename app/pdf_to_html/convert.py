"""Convert a single PDF to HTML using Marker (marker-pdf) with LLM (OpenAI) enabled.

Provides convert_pdf_to_html() and a CLI entrypoint.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

try:
    from . import marker_config as config
except Exception:
    # allow direct run when package not installed
    import marker_config as config  # type: ignore

# Optionally load .env for local development (keeps secrets out of source)
try:
    from dotenv import load_dotenv, find_dotenv
    dotenv_file = find_dotenv(usecwd=True)
    if dotenv_file:
        load_dotenv(dotenv_file, override=False)
except Exception:
    # python-dotenv not installed or no .env found — continue silently
    pass


def _build_marker_args(pdf_path: Path, outdir: Path) -> list[str]:
    args: list[str] = []

    # Required flags
    args.extend(["--output_format", "html", "--use_llm", "--llm_service", config.llm_service])

    # Model and optional base URL
    args.extend(["--openai_model", config.openai_model])
    if config.openai_base_url:
        args.extend(["--openai_base_url", config.openai_base_url])

    # Optional block correction prompt
    if getattr(config, "block_correction_prompt", None):
        args.extend(["--block_correction_prompt", config.block_correction_prompt])

    # Marker options: snake_case keys -> --snake-case
    for key, val in (config.marker_options or {}).items():
        flag = "--" + key.replace("_", "-")
        if isinstance(val, bool):
            if val:
                args.append(flag)
        elif val is not None:
            args.extend([flag, str(val)])

    # Output destination: run in a temp dir and collect outputs there
    # Provide input path as final arg
    args.append(str(pdf_path))
    return args


def _find_html_in_dir(d: Path, expected_basename: Optional[str] = None) -> Optional[Path]:
    html_files = list(d.rglob("*.html"))
    if not html_files:
        return None
    if expected_basename:
        for p in html_files:
            if p.stem == expected_basename:
                return p
    # fallback: return first
    return html_files[0]


def convert_pdf_to_html(pdf_path: str, output_dir: Optional[str] = None) -> str:
    """Convert a single PDF to HTML using Marker.

    Returns the path to the produced HTML file.
    Raises EnvironmentError, FileNotFoundError, RuntimeError on failures.
    """
    pdf = Path(pdf_path).expanduser().resolve()
    if not pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {pdf}")
    if pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Input must be a .pdf file: {pdf}")

    out_dir = Path(output_dir) if output_dir else Path(config.output_dir)
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Check marker_single available
    marker_cmd = shutil.which("marker_single")
    if not marker_cmd:
        raise EnvironmentError(
            "marker_single CLI not found. Is marker-pdf installed? Run: pip install marker-pdf"
        )

    # Work in a temp directory to capture marker outputs reliably
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        cmd = [marker_cmd] + _build_marker_args(pdf, workdir)

        print(f"Starting Marker conversion: {pdf.name}")
        print(f"Running command: {' '.join(cmd[:4])} ...")

        # Ensure API key available in environment and pass to child process
        api_key = os.environ.get(config.openai_api_env)
        if not api_key:
            raise EnvironmentError(
                f"OpenAI API key not found in environment variable {config.openai_api_env}."
            )
        env = os.environ.copy()
        env[config.openai_api_env] = api_key

        proc = subprocess.run(
            cmd,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        if proc.returncode != 0:
            # Print stderr excerpt
            excerpt = proc.stderr.strip()[:400]
            raise RuntimeError(
                f"Marker failed (rc={proc.returncode}). stderr:\n{excerpt}"
            )

        # Find produced HTML
        expected_name = pdf.stem
        found = _find_html_in_dir(workdir, expected_basename=expected_name)
        if not found:
            # fallback to any html
            found = _find_html_in_dir(workdir)
        if not found:
            raise RuntimeError("Marker completed but no HTML output found in temporary directory.")

        target = out_dir / f"{expected_name}.html"
        if target.exists():
            print(f"Output exists and will be overwritten: {target}")
            try:
                target.unlink()
            except Exception:
                pass

        shutil.move(str(found), str(target))

        print(f"Conversion complete. Output: {target}")
        return str(target)


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a PDF to HTML using Marker (LLM mode)")
    parser.add_argument("pdf", help="Path to input PDF file")
    parser.add_argument("--output-dir", help="Directory to place HTML output")
    args = parser.parse_args(argv)

    try:
        result = convert_pdf_to_html(args.pdf, args.output_dir)
        print(result)
        return 0
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except EnvironmentError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(_main())
