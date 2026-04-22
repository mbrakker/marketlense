from __future__ import annotations

from scripts.ci.check_architecture_imports import ImportViolation, scan_file


def test_architecture_import_gate_detects_reverse_dependency(tmp_path) -> None:
    path = tmp_path / "src" / "services" / "bad_service.py"
    path.parent.mkdir(parents=True)
    path.write_text("from src.generators import report_generator\n", encoding="utf-8")

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
