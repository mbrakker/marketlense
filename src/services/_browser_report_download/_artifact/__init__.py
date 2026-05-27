"""Internal browser-report artifact finalization capability family.

The package separates artifact adaptation capabilities while preserving
``browser_report_download_service`` as the single external-system boundary.
"""

ARTIFACT_LOGGER_NAME = "market_lense.browser_report_download_artifact"
_VERIFIED_EMAIL_SIGNAL_MARKERS = {
    "delivery_text",
    "success_text",
    "success_url",
    "form_disappeared",
    "network_confirmation_request",
}

__all__ = ["ARTIFACT_LOGGER_NAME", "_VERIFIED_EMAIL_SIGNAL_MARKERS"]
