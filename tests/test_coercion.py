from __future__ import annotations

from src.utils.coercion import (
    coerce_bool,
    coerce_extended_bool,
    coerce_float,
    coerce_int,
)


def test_coerce_int_uses_default_and_minimum() -> None:
    assert coerce_int("7", 0) == 7
    assert coerce_int("bad", 3) == 3
    assert coerce_int(None, 2, min_value=5) == 5
    assert coerce_int("-1", 0, min_value=0) == 0


def test_coerce_float_uses_default_on_invalid_values() -> None:
    assert coerce_float("1.25", 0.0) == 1.25
    assert coerce_float("bad", 2.5) == 2.5
    assert coerce_float(None, 3.0) == 3.0


def test_coerce_bool_uses_default_token_sets() -> None:
    assert coerce_bool("true", False) is True
    assert coerce_bool("off", True) is False
    assert coerce_bool("y", False) is False
    assert coerce_bool("", True) is True


def test_coerce_bool_supports_custom_token_sets() -> None:
    assert (
        coerce_bool(
            "y",
            False,
            true_tokens={"1", "true", "yes", "y", "on"},
            false_tokens={"0", "false", "no", "n", "off"},
        )
        is True
    )
    assert (
        coerce_bool(
            "n",
            True,
            true_tokens={"1", "true", "yes", "y", "on"},
            false_tokens={"0", "false", "no", "n", "off"},
        )
        is False
    )


def test_coerce_extended_bool_accepts_extended_tokens() -> None:
    assert coerce_extended_bool("t", False) is True
    assert coerce_extended_bool("f", True) is False
    assert coerce_extended_bool("Y", False) is True
