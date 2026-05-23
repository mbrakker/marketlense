from __future__ import annotations

from scripts.ci.check_architecture_imports import (
    ImportCycle,
    ImportViolation,
    scan_file,
    scan_first_party_import_cycles,
)


def test_architecture_import_gate_detects_reverse_dependency(tmp_path) -> None:
    path = tmp_path / "src" / "services" / "bad_service.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from src.generators import report_analysis_generator\n",
        encoding="utf-8",
    )

    violations = scan_file(path)

    assert violations == [
        ImportViolation(
            role="services",
            path=path,
            line=1,
            column=1,
            imported="src.generators",
            rule="services must not import src.generators",
        )
    ]


def test_architecture_import_gate_allows_forward_dependency(tmp_path) -> None:
    path = tmp_path / "src" / "generators" / "good_generator.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from src.services import prompt_service\n"
        "from src.contracts.prompts import PromptRenderRequest\n",
        encoding="utf-8",
    )

    assert scan_file(path) == []


def test_architecture_import_gate_detects_first_party_cycles(tmp_path) -> None:
    root = tmp_path / "src"
    first = root / "services" / "first.py"
    second = root / "services" / "second.py"
    third = root / "services" / "third.py"
    first.parent.mkdir(parents=True)
    first.write_text("from src.services.second import run_second\n", encoding="utf-8")
    second.write_text("from src.services.third import run_third\n", encoding="utf-8")
    third.write_text("from src.services.first import run_first\n", encoding="utf-8")

    assert scan_first_party_import_cycles(root) == [
        ImportCycle(
            modules=(
                "src.services.first",
                "src.services.second",
                "src.services.third",
                "src.services.first",
            )
        )
    ]


def test_architecture_import_gate_detects_type_checking_import_cycles(tmp_path) -> None:
    root = tmp_path / "src"
    first = root / "services" / "first.py"
    second = root / "services" / "second.py"
    first.parent.mkdir(parents=True)
    first.write_text(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from src.services.second import Second\n",
        encoding="utf-8",
    )
    second.write_text("from src.services.first import build_first\n", encoding="utf-8")

    assert scan_first_party_import_cycles(root) == [
        ImportCycle(
            modules=(
                "src.services.first",
                "src.services.second",
                "src.services.first",
            )
        )
    ]
