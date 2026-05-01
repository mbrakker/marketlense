from __future__ import annotations

import asyncio
from importlib import import_module

import requests  # type: ignore[import-untyped]

from src.contracts.publisher_inventory import (
    PublisherInventoryLandingPageInspectionRequest,
    PublisherInventoryLandingPageInspectionResponse,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
)
from src.contracts.run_context import RunContext
from src.services._publisher_inventory_service import workflow as _workflow
from src.services._publisher_inventory_service.workflow import *


def _sync_runtime_patch_points() -> None:
    _workflow.asyncio = asyncio
    _workflow.import_module = import_module
    _workflow.requests = requests


def discover_publisher_inventory(
    request: PublisherInventoryServiceRequest, ctx: RunContext
) -> PublisherInventoryServiceResponse:
    _sync_runtime_patch_points()
    return _workflow.discover_publisher_inventory(request, ctx)


def inspect_publisher_inventory_landing_pages(
    request: PublisherInventoryLandingPageInspectionRequest, ctx: RunContext
) -> PublisherInventoryLandingPageInspectionResponse:
    _sync_runtime_patch_points()
    return _workflow.inspect_publisher_inventory_landing_pages(request, ctx)
