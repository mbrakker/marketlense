"""Shared generator-layer bridge for analysis-pack storage compatibility.

Generators own the decision to accept either the canonical dataclass service
boundary or legacy positional test doubles. Centralizing that compatibility
keeps the behavior consistent without duplicating dispatch logic.
"""

from __future__ import annotations

from typing import Any, Optional

from src.contracts.report_analysis import (
    AnalysisPackPathRequest,
    AnalysisStorePackRequest,
)
from src.contracts.run_context import RunContext
from src.services import report_analysis_store_service


def _output_path_from_response(response: object) -> Optional[str]:
    if isinstance(response, str):
        return response
    output_path = getattr(response, "output_path", None)
    if isinstance(output_path, str):
        return output_path
    return None


def resolve_pack_path(
    *,
    analysis_store: Any,
    request: AnalysisPackPathRequest,
    ctx: RunContext,
) -> str:
    pack_path_method = getattr(analysis_store, "pack_path", None)
    if pack_path_method is not None:
        try:
            response = pack_path_method(request, ctx)
            output_path = _output_path_from_response(response)
            if output_path is not None:
                return output_path
        except TypeError:
            return str(
                pack_path_method(
                    request.output_dir,
                    request.report_id,
                    request.pack_name,
                    report_slug=request.report_slug,
                )
            )
    return report_analysis_store_service.pack_path(request, ctx).output_path


def store_pack(
    *,
    analysis_store: Any,
    request: AnalysisStorePackRequest,
    ctx: RunContext,
) -> str:
    store_pack_method = getattr(analysis_store, "store_pack", None)
    if store_pack_method is not None:
        try:
            response = store_pack_method(request, ctx)
            output_path = _output_path_from_response(response)
            if output_path is not None:
                return output_path
        except TypeError:
            return str(
                store_pack_method(
                    request.output_dir,
                    request.report_id,
                    request.pack_name,
                    request.payload,
                    ctx,
                    report_slug=request.report_slug,
                )
            )
    return report_analysis_store_service.store_pack(request, ctx).output_path
