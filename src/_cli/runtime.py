from __future__ import annotations

import sys
from collections.abc import Iterable
from typing import Any


def sync_cli_patch_points(module_globals: dict[str, Any], names: Iterable[str]) -> None:
    facade = sys.modules.get("src.cli")
    if facade is None:
        return
    for name in names:
        if hasattr(facade, name):
            module_globals[name] = getattr(facade, name)
