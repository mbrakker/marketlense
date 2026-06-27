from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME_PACKAGER_PS1 = ROOT / "Wordpress" / "scripts" / "build-theme-zip.ps1"
THEME_PACKAGER_SH = ROOT / "Wordpress" / "scripts" / "build-theme-zip.sh"
THEME_ARCHIVE = ROOT / "Wordpress" / "dist" / "marketlense.zip"


def test_native_theme_packager_builds_uploadable_archive() -> None:
    if sys.platform == "win32":
        assert THEME_PACKAGER_PS1.is_file()
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(THEME_PACKAGER_PS1),
        ]
    else:
        assert THEME_PACKAGER_SH.is_file()
        command = ["bash", str(THEME_PACKAGER_SH)]

    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    with zipfile.ZipFile(THEME_ARCHIVE) as archive:
        names = set(archive.namelist())

    assert "marketlense/style.css" in names
    assert "marketlense/assets/css/theme.css" in names
