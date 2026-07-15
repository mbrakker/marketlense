from __future__ import annotations

import argparse

import pytest

from scripts.quality.public_site_responsive_smoke import (
    _cli_command,
    _measurement_from_cli_output,
    _parse_viewport,
)


def test_responsive_smoke_reads_playwright_json_measurement() -> None:
    measurement = _measurement_from_cli_output(
        '### Result\n"{\\"viewport_width\\":390,\\"document_width\\":390,'
        '\\"horizontal_overflow\\":false,\\"non_lazy_broken_image_count\\":0}"\n'
    )

    assert measurement == {
        "viewport_width": 390,
        "document_width": 390,
        "horizontal_overflow": False,
        "non_lazy_broken_image_count": 0,
    }


def test_responsive_smoke_rejects_invalid_viewport() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="WIDTHxHEIGHT"):
        _parse_viewport("390-by-844")


def test_responsive_smoke_uses_cmd_shim_on_windows(
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr("sys.platform", "win32")

    assert _cli_command("session", "open", "https://example.test")[0] == "npx.cmd"
