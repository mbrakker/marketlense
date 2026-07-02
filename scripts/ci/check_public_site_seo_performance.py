from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_JSON = "out/public_site_seo_performance_staging.json"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def main() -> None:
    if _env("RUN_PUBLIC_SITE_SEO_PERFORMANCE_GATE") != "1":
        print("Public-site SEO/performance gate skipped.")
        return

    base_url = _env("PUBLIC_SITE_BASE_URL")
    if not base_url:
        raise SystemExit("Missing required staging environment variable: PUBLIC_SITE_BASE_URL")

    paths = [
        item.strip()
        for item in _env("PUBLIC_SITE_SEO_PATHS").split(",")
        if item.strip()
    ]
    command = [
        sys.executable,
        "scripts/quality/public_site_seo_performance.py",
        "--base-url",
        base_url,
        "--baseline",
        _env("PUBLIC_SITE_BASELINE_PATH", "config/public_site_baselines.yaml"),
        "--output-json",
        _env("PUBLIC_SITE_SEO_PERFORMANCE_JSON", DEFAULT_OUTPUT_JSON),
    ]
    for path in paths:
        command.extend(["--path", path])
    result = subprocess.run(command, cwd=REPO_ROOT, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
