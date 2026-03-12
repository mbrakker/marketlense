from __future__ import annotations

import logging

PDF_LOGGER_NAME = "market_lense.pdf_service"
CANDIDATE_LOGGER_NAME = f"{PDF_LOGGER_NAME}.candidate_extraction"
CROP_LOGGER_NAME = f"{PDF_LOGGER_NAME}.crop"
PREVIEW_LOGGER_NAME = f"{PDF_LOGGER_NAME}.preview"
FIGURE_LOGGER_NAME = f"{PDF_LOGGER_NAME}.figure"
EOF_TAIL_BYTES = 2048

logger = logging.getLogger(PDF_LOGGER_NAME)
candidate_logger = logging.getLogger(CANDIDATE_LOGGER_NAME)
crop_logger = logging.getLogger(CROP_LOGGER_NAME)
preview_logger = logging.getLogger(PREVIEW_LOGGER_NAME)
figure_logger = logging.getLogger(FIGURE_LOGGER_NAME)
