from __future__ import annotations

from pathlib import Path

from scripts.ci.check_split_symbol_links import scan_symbol_links


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_split_symbol_gate_rejects_missing_required_export(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "services" / "_config_service" / "common.py",
        "HELPER = object()\n__all__ = []\n",
    )

    violations = scan_symbol_links(
        root=tmp_path,
        boundary_export_requirements={
            "src/services/_config_service/common.py": ("HELPER",)
        },
        star_link_targets=(),
        ordered_submodule_exports={},
    )

    assert [(item.category, item.symbol) for item in violations] == [
        ("missing_required_export", "HELPER")
    ]


def test_split_symbol_gate_rejects_unlinked_star_import_symbol(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src" / "services" / "_config_service" / "common.py",
        "HELPER = object()\n__all__ = []\n",
    )
    consumer = _write(
        tmp_path / "src" / "services" / "_config_service" / "consumer.py",
        "from src.services._config_service.common import *\n\n"
        "def load_value():\n"
        "    return HELPER\n",
    )

    violations = scan_symbol_links(
        root=tmp_path,
        boundary_export_requirements={},
        star_link_targets=("src/services/_config_service/*.py",),
        ordered_submodule_exports={},
    )

    assert any(
        item.path == consumer
        and item.category == "unlinked_star_import_symbol"
        and item.symbol == "HELPER"
        for item in violations
    )


def test_split_symbol_gate_rejects_unsafe_submodule_export_order(
    tmp_path: Path,
) -> None:
    facade = _write(
        tmp_path / "src" / "services" / "_pdf" / "visual_heuristics.py",
        "_SUBMODULE_EXPORTS = ['helper']\n"
        "__all__ = []\n"
        "__all__ += _SUBMODULE_EXPORTS\n"
        "from ._visual_heuristics.child import *\n",
    )
    _write(
        tmp_path / "src" / "services" / "_pdf" / "_visual_heuristics" / "child.py",
        "def helper():\n    return 'ok'\n__all__ = ['helper']\n",
    )

    violations = scan_symbol_links(
        root=tmp_path,
        boundary_export_requirements={},
        star_link_targets=(),
        ordered_submodule_exports={
            "src/services/_pdf/visual_heuristics.py": {
                "_SUBMODULE_EXPORTS": "src/services/_pdf/_visual_heuristics/child.py"
            }
        },
    )

    assert [(item.path, item.category, item.symbol) for item in violations] == [
        (facade, "unsafe_export_order", "_SUBMODULE_EXPORTS")
    ]


def test_split_symbol_gate_accepts_linked_split_family(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "services" / "_config_service" / "common.py",
        "HELPER = object()\n__all__ = ['HELPER']\n",
    )
    _write(
        tmp_path / "src" / "services" / "_config_service" / "consumer.py",
        "from src.services._config_service.common import *\n\n"
        "def load_value():\n"
        "    return HELPER\n",
    )

    assert (
        scan_symbol_links(
            root=tmp_path,
            boundary_export_requirements={
                "src/services/_config_service/common.py": ("HELPER",)
            },
            star_link_targets=("src/services/_config_service/*.py",),
            ordered_submodule_exports={},
        )
        == ()
    )
