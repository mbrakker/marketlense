"""Legacy compatibility facade for the canonical :mod:`llm_service` boundary."""

from src.services.llm_service import (
    OPENAI_OCR_RESPONSE_FORMAT,
    _image_path_to_data_url,
    _strip_json_fence,
    analyze_report,
    openai_chat_json,
    openai_chat_json_with_images,
    openai_legacy,
    openai_ocr_pdf,
    openai_respond_with_vector_store,
    openai_vector_store_attach_file,
    openai_vector_store_create,
    openai_vector_store_delete,
    openai_vector_store_status,
    openai_vector_store_update_metadata,
    openai_vector_store_upload_file,
)

__all__ = [
    "OPENAI_OCR_RESPONSE_FORMAT",
    "_image_path_to_data_url",
    "_strip_json_fence",
    "analyze_report",
    "openai_chat_json",
    "openai_chat_json_with_images",
    "openai_legacy",
    "openai_ocr_pdf",
    "openai_respond_with_vector_store",
    "openai_vector_store_attach_file",
    "openai_vector_store_create",
    "openai_vector_store_delete",
    "openai_vector_store_status",
    "openai_vector_store_update_metadata",
    "openai_vector_store_upload_file",
]
