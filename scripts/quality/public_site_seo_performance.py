from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.contracts.public_site_quality import (  # noqa: E402
    PublicSitePageQuality,
    PublicSiteQualityReport,
)

DEFAULT_PATHS = (
    "/",
    "/reports/",
    "/briefings/",
    "/signals/",
    "/methodology/",
    "/contact/",
    "/submit/",
)
DEFAULT_BASELINE_PATH = "config/public_site_baselines.yaml"


def _load_baseline(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise SystemExit(f"Baseline file must contain a YAML object: {path}")
    return payload


def _metadata_from_html(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    def meta_name(name: str) -> str:
        tag = soup.find("meta", attrs={"name": name})
        return str(tag.get("content") or "").strip() if tag else ""

    def meta_prop(name: str) -> str:
        tag = soup.find("meta", attrs={"property": name})
        return str(tag.get("content") or "").strip() if tag else ""

    canonical = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    return {
        "meta.description": meta_name("description"),
        "link.canonical": str(canonical.get("href") or "").strip() if canonical else "",
        "og.title": meta_prop("og:title"),
        "og.description": meta_prop("og:description"),
        "og.url": meta_prop("og:url"),
        "twitter.card": meta_name("twitter:card"),
        "twitter.title": meta_name("twitter:title"),
        "twitter.description": meta_name("twitter:description"),
    }


def _resource_urls(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for tag_name, attr_name in (
        ("img", "src"),
        ("script", "src"),
        ("link", "href"),
        ("source", "src"),
    ):
        for tag in soup.find_all(tag_name):
            if tag_name == "link":
                rel_values = {
                    str(item).casefold()
                    for item in tag.get("rel", [])
                    if str(item).strip()
                }
                if not rel_values.intersection(
                    {"stylesheet", "preload", "modulepreload", "icon", "apple-touch-icon"}
                ):
                    continue
            value = str(tag.get(attr_name) or "").strip()
            if not value or value.startswith(("data:", "mailto:", "tel:", "#")):
                continue
            absolute = urljoin(page_url, value)
            if absolute not in urls:
                urls.append(absolute)
    return urls


def _same_site(url: str, base_url: str) -> bool:
    return urlparse(url).netloc == urlparse(base_url).netloc


def _resource_weight(
    session: requests.Session,
    *,
    urls: list[str],
    base_url: str,
    timeout_seconds: float,
    limit: int,
) -> int:
    total = 0
    for url in urls[:limit]:
        if not _same_site(url, base_url):
            continue
        try:
            response = session.head(url, timeout=timeout_seconds, allow_redirects=True)
        except requests.RequestException:
            continue
        length = response.headers.get("content-length")
        if length and length.isdigit():
            total += int(length)
    return total


def inspect_page(
    *,
    session: requests.Session,
    url: str,
    base_url: str,
    baseline: dict[str, Any],
    timeout_seconds: float,
    resource_limit: int,
) -> PublicSitePageQuality:
    started = time.perf_counter()
    response = session.get(url, timeout=timeout_seconds, stream=True)
    response_start_ms = (time.perf_counter() - started) * 1000.0
    body = response.content
    html = body.decode(response.encoding or "utf-8", errors="replace")
    metadata = _metadata_from_html(html)
    resource_urls = _resource_urls(html, url)
    page_weight = len(body) + _resource_weight(
        session,
        urls=resource_urls,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        limit=resource_limit,
    )
    dom_complete_ms = (time.perf_counter() - started) * 1000.0
    required_metadata = [
        str(item)
        for item in baseline.get("required_metadata", [])
        if str(item).strip()
    ]
    missing_metadata = [
        key for key in required_metadata if not str(metadata.get(key) or "").strip()
    ]
    thresholds = baseline.get("baseline") if isinstance(baseline.get("baseline"), dict) else {}
    threshold_violations: list[str] = []
    measured = {
        "response_start_ms": response_start_ms,
        "dom_complete_ms": dom_complete_ms,
        "request_count": 1 + len(resource_urls),
        "page_weight_bytes": page_weight,
    }
    for key, raw_limit in thresholds.items():
        try:
            limit_value = float(raw_limit)
        except (TypeError, ValueError):
            continue
        if float(measured.get(str(key), 0.0)) > limit_value:
            threshold_violations.append(str(key))

    return PublicSitePageQuality(
        schema_version="1.0",
        url=url,
        status_code=int(response.status_code),
        response_start_ms=round(response_start_ms, 3),
        dom_complete_ms=round(dom_complete_ms, 3),
        request_count=int(measured["request_count"]),
        page_weight_bytes=int(page_weight),
        metadata=metadata,
        missing_metadata=missing_metadata,
        threshold_violations=threshold_violations,
    )


def inspect_site(
    *,
    base_url: str,
    paths: list[str],
    baseline: dict[str, Any],
    timeout_seconds: float = 15.0,
    resource_limit: int = 80,
) -> PublicSiteQualityReport:
    normalized_base = base_url.rstrip("/") + "/"
    pages: list[PublicSitePageQuality] = []
    with requests.Session() as session:
        session.headers.update(
            {"User-Agent": "MarketBearingPublicSiteGate/1.0"}
        )
        for path in paths:
            url = urljoin(normalized_base, path.lstrip("/"))
            pages.append(
                inspect_page(
                    session=session,
                    url=url,
                    base_url=normalized_base,
                    baseline=baseline,
                    timeout_seconds=timeout_seconds,
                    resource_limit=resource_limit,
                )
            )
    passed = all(
        page.status_code < 400
        and not page.missing_metadata
        and not page.threshold_violations
        for page in pages
    )
    return PublicSiteQualityReport(
        schema_version="1.0",
        base_url=normalized_base,
        pages=pages,
        passed=passed,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check hosted public-site SEO/social metadata and performance baselines."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--resource-limit", type=int, default=80)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    baseline = _load_baseline(Path(args.baseline))
    report = inspect_site(
        base_url=str(args.base_url),
        paths=[str(item) for item in (args.path or DEFAULT_PATHS)],
        baseline=baseline,
        timeout_seconds=float(args.timeout_seconds),
        resource_limit=int(args.resource_limit),
    )
    payload = asdict(report)
    output = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
