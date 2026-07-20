"""Canonical browser-use runtime resolution shared by doctor and workers."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import ModuleType

from src.utils.errors import AppError


@dataclass(frozen=True)
class BrowserRuntimeIdentity:
    """Non-secret runtime facts used to prove browser doctor/worker parity."""

    interpreter_path: str
    python_version: str
    virtualenv_path: str
    browser_use_module_path: str
    runtime_source: str
    vendored_checksum: str

    def concise(self) -> str:
        return (
            f"python={self.interpreter_path}; version={self.python_version}; "
            f"venv={self.virtualenv_path or '-'}; source={self.runtime_source}; "
            f"module={self.browser_use_module_path}; vendor_checksum="
            f"{self.vendored_checksum or '-'}"
        )


def browser_runtime_identity(module: ModuleType) -> BrowserRuntimeIdentity:
    module_path = Path(str(getattr(module, "__file__", "") or "")).resolve()
    vendor_root = _vendored_browser_use_root()
    is_vendored = _is_within(module_path, vendor_root)
    return BrowserRuntimeIdentity(
        interpreter_path=str(Path(sys.executable).resolve()),
        python_version=sys.version.split()[0],
        virtualenv_path=(
            str(Path(sys.prefix).resolve()) if sys.prefix != sys.base_prefix else ""
        ),
        browser_use_module_path=str(module_path),
        runtime_source="vendored" if is_vendored else "installed",
        vendored_checksum=_vendored_checksum(vendor_root) if is_vendored else "",
    )


def load_browser_use_runtime(*, normalized_url: str = "") -> ModuleType:
    """Load browser-use from the installed package or the supported vendor tree.

    Both the process-local worker and its subprocess use this function.  The
    vendor tree is deliberately an explicit supported runtime, not a doctor-only
    ``sys.path`` workaround.
    """

    try:
        return importlib.import_module("browser_use")
    except ModuleNotFoundError as installed_error:
        vendor_root = _vendored_browser_use_root()
        if not vendor_root.is_dir():
            raise _unavailable_error(
                normalized_url, installed_error
            ) from installed_error
        vendor_root_token = str(vendor_root)
        if vendor_root_token not in sys.path:
            sys.path.insert(0, vendor_root_token)
        try:
            return importlib.import_module("browser_use")
        except Exception as vendor_error:
            raise _unavailable_error(normalized_url, vendor_error) from vendor_error
    except Exception as exc:
        raise _unavailable_error(normalized_url, exc) from exc


def load_browser_session_class(*, normalized_url: str = "") -> type:
    load_browser_use_runtime(normalized_url=normalized_url)
    try:
        module = importlib.import_module("browser_use.browser.session")
        return module.BrowserSession
    except Exception as exc:
        raise _unavailable_error(normalized_url, exc) from exc


def _vendored_browser_use_root() -> Path:
    return Path(__file__).resolve().parents[4] / "tools" / "browser-use"


def _vendored_checksum(vendor_root: Path) -> str:
    init_path = vendor_root / "browser_use" / "__init__.py"
    try:
        return sha256(init_path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _unavailable_error(normalized_url: str, cause: Exception) -> AppError:
    return AppError(
        code="browser_use_unavailable",
        message="The canonical browser_use runtime is unavailable to this worker",
        cause=cause,
        retryable=False,
        context={"normalized_url": normalized_url},
    )
