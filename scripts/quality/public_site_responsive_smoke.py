from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urljoin

DEFAULT_PATHS = ("/", "/reports/")
DEFAULT_VIEWPORTS = ((390, 844), (768, 1024), (1440, 1000))
_MEASUREMENT_SCRIPT = (
    "async()=>{await document.fonts.ready;await new Promise(r=>setTimeout(r,250));"
    "const v=document.documentElement.clientWidth;const b=[...document.images].filter("
    "i=>i.loading!=='lazy'&&(!i.complete||i.naturalWidth===0));return JSON.stringify("
    "{viewport_width:v,document_width:document.documentElement.scrollWidth,"
    "horizontal_overflow:document.documentElement.scrollWidth>v,"
    "non_lazy_broken_image_count:b.length});}"
)


@dataclass(frozen=True)
class ResponsivePageQuality:
    """Rendered responsive smoke outcome for one public page and viewport."""

    url: str
    viewport_width: int
    viewport_height: int
    document_width: int
    horizontal_overflow: bool
    non_lazy_broken_image_count: int


@dataclass(frozen=True)
class ResponsiveSmokeReport:
    """Aggregate public responsive smoke outcome."""

    schema_version: str
    base_url: str
    pages: list[ResponsivePageQuality]
    passed: bool


def _cli_command(session: str, *args: str) -> list[str]:
    return [
        "npx.cmd" if sys.platform == "win32" else "npx",
        "--yes",
        "--package",
        "@playwright/cli",
        "playwright-cli",
        f"-s={session}",
        *args,
    ]


def _run_cli(session: str, *args: str) -> str:
    completed = subprocess.run(
        _cli_command(session, *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _measurement_from_cli_output(output: str) -> dict[str, object]:
    for line in reversed(output.splitlines()):
        value = line.strip()
        if not value:
            continue
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, str):
            try:
                decoded = json.loads(decoded)
            except json.JSONDecodeError:
                continue
        if isinstance(decoded, dict) and "viewport_width" in decoded:
            return decoded
    raise RuntimeError("Playwright responsive smoke did not return a measurement")


def inspect_site(
    *,
    base_url: str,
    paths: Sequence[str],
    viewports: Sequence[tuple[int, int]],
    session: str,
) -> ResponsiveSmokeReport:
    normalized_base = base_url.rstrip("/") + "/"
    pages: list[ResponsivePageQuality] = []
    _run_cli(session, "open", normalized_base)
    try:
        for viewport_width, viewport_height in viewports:
            _run_cli(session, "resize", str(viewport_width), str(viewport_height))
            for path in paths:
                url = urljoin(normalized_base, path.lstrip("/"))
                _run_cli(session, "goto", url)
                measured = _measurement_from_cli_output(
                    _run_cli(session, "eval", _MEASUREMENT_SCRIPT)
                )
                pages.append(
                    ResponsivePageQuality(
                        url=url,
                        viewport_width=int(measured["viewport_width"]),
                        viewport_height=viewport_height,
                        document_width=int(measured["document_width"]),
                        horizontal_overflow=bool(measured["horizontal_overflow"]),
                        non_lazy_broken_image_count=int(
                            measured["non_lazy_broken_image_count"]
                        ),
                    )
                )
    finally:
        _run_cli(session, "close")
    return ResponsiveSmokeReport(
        schema_version="1.0",
        base_url=normalized_base,
        pages=pages,
        passed=all(
            not page.horizontal_overflow and page.non_lazy_broken_image_count == 0
            for page in pages
        ),
    )


def _parse_viewport(value: str) -> tuple[int, int]:
    width, separator, height = value.lower().partition("x")
    if separator != "x" or not width.isdigit() or not height.isdigit():
        raise argparse.ArgumentTypeError(
            "Viewport must use WIDTHxHEIGHT, for example 390x844"
        )
    return int(width), int(height)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test rendered public pages for overflow and visible broken images."
        )
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--viewport", action="append", type=_parse_viewport, default=[])
    parser.add_argument("--session", default="market-lense-responsive-smoke")
    parser.add_argument("--output-json", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    report = inspect_site(
        base_url=str(args.base_url),
        paths=[str(path) for path in (args.path or DEFAULT_PATHS)],
        viewports=list(args.viewport or DEFAULT_VIEWPORTS),
        session=str(args.session),
    )
    output = json.dumps(asdict(report), ensure_ascii=True, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
