import json
import re
from html import unescape
from pathlib import Path

import pytest
from PIL import Image

from src.contracts.report_assets import RenderRequest
from src.contracts.run_context import RunContext
from src.services._render_service.normalization import _public_citation_label
from src.services._render_service.view import (
    _build_seo_title,
    _marketlense_article_url,
    _normalize_public_title,
    _seo_description,
)
from src.services.render_service import render_report

__all__ = [
    "json",
    "re",
    "unescape",
    "Path",
    "pytest",
    "Image",
    "RenderRequest",
    "RunContext",
    "_public_citation_label",
    "_build_seo_title",
    "_marketlense_article_url",
    "_normalize_public_title",
    "_seo_description",
    "render_report",
    "_ctx",
]


def _ctx():
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
