from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_ARTIFACT = "out/activate-2025-ecommerce-pdf.html"
DEFAULT_BRIEFING_ARTIFACT = (
    "out/live_model_client_injection_cross_report/cross_report_analysis/"
    "ai-brand-trust-consumer-decision-2026/analysis.json"
)
DEFAULT_SIGNAL_ARTIFACT = (
    "out/allegro-2026-trends-macrotrends-es-acig-pdf/report_analysis/signals.json"
)
DEFAULT_OUTPUT_JSON = "out/wordpress_entity_rest_verification_staging.json"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _required_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise SystemExit(f"Missing required staging environment variable: {name}")
    return value


def _artifact_path(env_name: str, default: str) -> Path:
    path = REPO_ROOT / _env(env_name, default)
    if not path.is_file():
        raise SystemExit(
            f"Required existing artifact for {env_name} was not found: {path}"
        )
    return path


def main() -> None:
    if _env("RUN_WORDPRESS_STAGING_REST_GATE") != "1":
        print("WordPress staging REST gate skipped.")
        return

    report_artifact = _artifact_path(
        "WP_STAGING_REPORT_ARTIFACT", DEFAULT_REPORT_ARTIFACT
    )
    briefing_artifact = _artifact_path(
        "WP_STAGING_BRIEFING_ARTIFACT", DEFAULT_BRIEFING_ARTIFACT
    )
    signal_artifact = _artifact_path(
        "WP_STAGING_SIGNAL_ARTIFACT", DEFAULT_SIGNAL_ARTIFACT
    )
    output_json = REPO_ROOT / _env("WP_STAGING_REST_EVIDENCE_JSON", DEFAULT_OUTPUT_JSON)
    slug_suffix = "staging-rest-gate-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")

    env = os.environ.copy()
    env["WP_SITE_URL"] = _required_env("WP_STAGING_SITE_URL")
    bearer_token = _env("WP_STAGING_BEARER_TOKEN")
    if bearer_token:
        env["WP_BEARER_TOKEN"] = bearer_token
        env.pop("WP_USERNAME", None)
        env.pop("WP_APP_PASSWORD", None)
    else:
        env["WP_USERNAME"] = _required_env("WP_STAGING_USERNAME")
        env["WP_APP_PASSWORD"] = _required_env("WP_STAGING_APP_PASSWORD")
        env.pop("WP_BEARER_TOKEN", None)
    if _env("WP_STAGING_SSL_VERIFY"):
        env["WP_SSL_VERIFY"] = _env("WP_STAGING_SSL_VERIFY")
    if _env("WP_STAGING_CA_BUNDLE_PATH"):
        env["WP_CA_BUNDLE_PATH"] = _env("WP_STAGING_CA_BUNDLE_PATH")

    command = [
        sys.executable,
        "Wordpress/scripts/verify-publish-entity-rest.py",
        "--report-artifact",
        str(report_artifact),
        "--briefing-artifact",
        str(briefing_artifact),
        "--signal-artifact",
        str(signal_artifact),
        "--status",
        "draft",
        "--slug-suffix",
        slug_suffix,
        "--output-json",
        str(output_json),
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, env=env, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    print(f"WordPress staging REST evidence written to {output_json}")


if __name__ == "__main__":
    main()
