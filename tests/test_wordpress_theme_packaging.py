from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME_PACKAGER = ROOT / "Wordpress" / "scripts" / "build-theme-zip.ps1"
THEME_ARCHIVE = ROOT / "Wordpress" / "dist" / "marketlense.zip"


def test_native_theme_packager_builds_uploadable_archive() -> None:
    assert THEME_PACKAGER.is_file()

    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(THEME_PACKAGER),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    with zipfile.ZipFile(THEME_ARCHIVE) as archive:
        names = set(archive.namelist())

    assert "marketlense/style.css" in names
    assert "marketlense/assets/css/theme.css" in names
