from __future__ import annotations

from pathlib import Path

from Wordpress.scripts import marketlense_admin


def test_wordpress_admin_cli_routes_each_command_to_one_handler() -> None:
    calls: list[str] = []
    handlers = {
        command: (lambda selected=command: calls.append(selected))
        for command in marketlense_admin.COMMAND_HANDLERS
    }

    for command in handlers:
        assert marketlense_admin.main([command], handlers=handlers) == 0

    assert calls == list(marketlense_admin.COMMAND_HANDLERS)


def test_wordpress_admin_cli_dry_run_has_no_external_side_effect(capsys) -> None:
    called = False

    def _handler() -> None:
        nonlocal called
        called = True

    result = marketlense_admin.main(
        ["provision", "--dry-run"],
        handlers={"provision": _handler},
    )

    assert result == 0
    assert called is False
    assert "Dry run" in capsys.readouterr().out


def test_legacy_wordpress_rest_scripts_delegate_to_canonical_cli() -> None:
    scripts_root = Path("Wordpress/scripts")
    for name, command in (
        ("provision-site-structure-rest.py", "provision"),
        ("seed-publisher-homepages-rest.py", "seed-homepages"),
        ("sync-publisher-profiles-rest.py", "sync-profiles"),
    ):
        source = (scripts_root / name).read_text(encoding="utf-8")
        assert "marketlense_admin import main" in source
        assert f'main(["{command}", *sys.argv[1:]])' in source
