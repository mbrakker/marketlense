from __future__ import annotations

from pathlib import Path

from scripts.ci.check_bounded_logging import find_direct_asdict_log_fields


def test_bounded_logging_gate_rejects_direct_contract_serialization(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "src" / "unsafe_logging.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "from dataclasses import asdict\n"
        "\n"
        "def emit(ctx, result):\n"
        "    return log_event(ctx, fields=asdict(result))\n",
        encoding="utf-8",
    )

    violations = find_direct_asdict_log_fields((source_path,), root=tmp_path)

    assert len(violations) == 1
    assert violations[0].path == "src/unsafe_logging.py"
    assert violations[0].line == 4


def test_bounded_logging_gate_accepts_explicit_scalar_summary(tmp_path: Path) -> None:
    source_path = tmp_path / "src" / "safe_logging.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "def emit(ctx, result):\n"
        "    return log_event(ctx, fields={'status': result.status})\n",
        encoding="utf-8",
    )

    assert find_direct_asdict_log_fields((source_path,), root=tmp_path) == ()
