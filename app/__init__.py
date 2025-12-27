from .logging_config import setup_logging

# Initialize logging early when the package is imported so modules log consistently.
setup_logging()

# Re-export selected helpers from subpackages at the package root.
# Priority given to top-level `app` exposures so callers can do `from app import ...`.
try:
	# Expose `convert_pdf_to_html` on the `app` package for convenience.
	from .pdf_to_html.convert import convert_pdf_to_html  # type: ignore
	__all__ = ["convert_pdf_to_html"]
except Exception:
	# If the subpackage isn't available at import time, fall back to an empty export list.
	__all__ = []
