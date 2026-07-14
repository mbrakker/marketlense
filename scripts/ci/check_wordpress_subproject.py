from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORDPRESS_ROOT = REPO_ROOT / "Wordpress"
THEME_ROOT = WORDPRESS_ROOT / "wp-content" / "themes" / "marketlense"
PLUGIN_ROOT = WORDPRESS_ROOT / "wp-content" / "plugins" / "marketlense-core"

THEME_SOURCE_DIRS = (
    THEME_ROOT / "parts",
    THEME_ROOT / "patterns",
    THEME_ROOT / "templates",
)


def _iter_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _run(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode == 0:
        return
    sys.stderr.write(result.stdout)
    sys.stderr.write(result.stderr)
    raise SystemExit(result.returncode)


def assert_no_hardcoded_root_relative_links() -> None:
    offenders: list[str] = []
    patterns = ('href="/', '"url":"/')
    for directory in THEME_SOURCE_DIRS:
        for path in _iter_files(directory, (".html", ".php")):
            content = path.read_text(encoding="utf-8")
            for token in patterns:
                if token in content:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)} contains {token!r}"
                    )

    if offenders:
        raise SystemExit(
            "Found deploy-fragile root-relative links in WordPress theme source:\n"
            + "\n".join(offenders)
        )


def assert_legacy_topic_archive_removed() -> None:
    legacy_template = THEME_ROOT / "templates" / "taxonomy-ml_topic.html"
    if legacy_template.exists():
        raise SystemExit(
            f"Legacy topic archive template still exists: {legacy_template.relative_to(REPO_ROOT)}"
        )


def lint_php_files() -> None:
    php_bin = shutil.which("php")
    if php_bin is None:
        raise SystemExit("PHP CLI is required for WordPress subproject checks.")

    for root in (THEME_ROOT, PLUGIN_ROOT):
        for path in _iter_files(root, (".php",)):
            _run([php_bin, "-l", str(path)], cwd=REPO_ROOT)


def lint_shell_scripts() -> None:
    bash_bin = shutil.which("bash")
    if bash_bin is None:
        raise SystemExit("bash is required for WordPress subproject checks.")

    for path in _iter_files(WORDPRESS_ROOT / "scripts", (".sh",)):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        _run([bash_bin, "-n", relative_path], cwd=REPO_ROOT)


def run_archive_browser_facet_cache_audit() -> None:
    php_bin = shutil.which("php")
    if php_bin is None:
        raise SystemExit("PHP CLI is required for WordPress subproject checks.")
    _run(
        [php_bin, "Wordpress/scripts/audit-archive-browser-facet-cache.php"],
        cwd=REPO_ROOT,
    )


def maybe_run_smoke_test() -> None:
    if os.environ.get("RUN_WORDPRESS_SMOKE") != "1":
        return
    if shutil.which("wp") is None:
        return
    if not (WORDPRESS_ROOT / "scripts" / "smoke-test.sh").exists():
        return
    _run(["bash", "Wordpress/scripts/smoke-test.sh"], cwd=REPO_ROOT)


def main() -> None:
    assert_no_hardcoded_root_relative_links()
    assert_legacy_topic_archive_removed()
    lint_php_files()
    lint_shell_scripts()
    run_archive_browser_facet_cache_audit()
    maybe_run_smoke_test()
    print("WordPress subproject checks passed.")


if __name__ == "__main__":
    main()
