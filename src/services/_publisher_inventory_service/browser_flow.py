from __future__ import annotations

"""Compatibility facade for publisher-inventory browser traversal helpers."""

import asyncio
import requests

from src.services._publisher_inventory_service._browser_flow.interactions import (
    _apply_report_filter,
    _browser_wait_for_settle,
    _click_archive_expander,
    _click_load_more,
    _click_pagination_next,
    _click_tab,
    _dismiss_cookie_banner,
    _extract_rendered_inventory_state,
    _prime_browser_inventory_surface,
    _record_browser_scroll_probe_metrics,
    _reset_empty_results_filters,
    _wait_for_inventory_growth,
    _wait_for_inventory_growth_probe,
    _wait_for_inventory_transition,
    _wait_for_tab_activation,
)
from src.services._publisher_inventory_service._browser_flow.collection import (
    _close_unexpected_blank_pages,
    _collect_browser_inventory_pages,
    _extract_rendered_html_supplement_candidates,
    _is_browser_placeholder_page_url,
    _page_target_id,
)
from src.services._publisher_inventory_service._browser_flow.supplement import (
    _HTTP_SUPPLEMENT_HTML_MAX_BYTES,
    _extract_browser_http_supplement_candidates,
)
from src.services._publisher_inventory_service._browser_flow.traversal import (
    _run_browser_traversal,
    _run_browser_traversal_with_timeout,
    _seed_initial_browser_page,
)

__all__ = [name for name in globals() if not name.startswith("__")]
