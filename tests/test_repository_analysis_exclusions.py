from __future__ import annotations

from pathlib import Path

from scripts.count_long_files import collect_long_files, render_long_file_report


def _write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"line {index}" for index in range(count)), encoding="utf-8"
    )


def test_long_file_scan_excludes_temp_vendor_replay_and_clone_trees(tmp_path):
    _write_lines(tmp_path / "src" / "runtime.py", 7)
    _write_lines(tmp_path / "tests" / "test_runtime.py", 7)
    _write_lines(tmp_path / "scripts" / "audit.py", 7)
    _write_lines(
        tmp_path
        / "Wordpress"
        / "wp-content"
        / "plugins"
        / "marketlense-core"
        / "plugin.php",
        7,
    )
    _write_lines(tmp_path / ".codex_tmp" / "linux-ci-repro" / "src" / "clone.py", 100)
    _write_lines(tmp_path / "tools" / "browser-use" / "browser_use" / "agent.py", 100)
    _write_lines(tmp_path / "tools" / "local_tool" / "audit.py", 100)
    _write_lines(tmp_path / ".pytest_tmp_cross_unit" / "repro.py", 100)
    _write_lines(tmp_path / "tmp_pytest_ingest" / "repro.py", 100)
    _write_lines(tmp_path / "state" / "ui_runs" / "run-1" / "replay_manifest.py", 100)
    _write_lines(tmp_path / "out" / "report" / "generated.py", 100)

    result = collect_long_files(root=tmp_path, min_lines=5)
    reported_paths = {
        item.path for section in result.sections for item in section.files
    }

    assert reported_paths == {
        "src/runtime.py",
        "tests/test_runtime.py",
        "scripts/audit.py",
        "Wordpress/wp-content/plugins/marketlense-core/plugin.php",
    }
    assert result.scanned_count == 4
    assert result.skipped_count == 7
    assert result.skipped_by_reason["top-level runtime/temp directory"] == 5
    assert result.skipped_by_reason["vendored dependency tree"] == 1
    assert result.skipped_by_reason["outside first-party analysis roots"] == 1


def test_first_party_roots_are_not_excluded_by_runtime_like_nested_names(tmp_path):
    _write_lines(tmp_path / "src" / "cache" / "domain_cache.py", 8)
    _write_lines(tmp_path / "tests" / "tmp_helpers" / "test_helpers.py", 8)
    _write_lines(tmp_path / "scripts" / "tmp_tools" / "audit_helper.py", 8)
    _write_lines(tmp_path / "Wordpress" / "scripts" / "tmp_sync.py", 8)
    _write_lines(tmp_path / "cache" / "generated.py", 100)
    _write_lines(tmp_path / "tmp_tools" / "generated.py", 100)

    result = collect_long_files(root=tmp_path, min_lines=5)
    reported_paths = {
        item.path for section in result.sections for item in section.files
    }

    assert reported_paths == {
        "src/cache/domain_cache.py",
        "tests/tmp_helpers/test_helpers.py",
        "scripts/tmp_tools/audit_helper.py",
        "Wordpress/scripts/tmp_sync.py",
    }
    assert result.scanned_count == 4
    assert result.skipped_count == 2


def test_long_file_report_groups_first_party_sections(tmp_path):
    _write_lines(tmp_path / "src" / "large.py", 6)
    _write_lines(tmp_path / "tests" / "test_large.py", 6)
    _write_lines(tmp_path / "scripts" / "large_tool.py", 6)
    _write_lines(tmp_path / "Wordpress" / "wp-content" / "themes" / "theme.php", 6)
    _write_lines(tmp_path / "tools" / "browser-use" / "vendor.py", 50)

    report = render_long_file_report(collect_long_files(root=tmp_path, min_lines=5))

    assert "First-party src files with more than 5 lines:" in report
    assert "First-party tests files with more than 5 lines:" in report
    assert "First-party scripts files with more than 5 lines:" in report
    assert "WordPress integration files with more than 5 lines:" in report
    assert "vendor.py" not in report
    assert "Skipped files: 1" in report
