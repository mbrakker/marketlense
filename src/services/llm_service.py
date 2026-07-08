from __future__ import annotations

from src.services._llm_service.client import (
    LLMServiceClient,
    build_client,
    build_client_for_settings,
    build_client_from_callables,
    build_model_call_audit_record,
    build_model_call_replay_bundle,
    build_openai_client,
    build_openai_client_for_settings,
    build_openai_client_from_callables,
    client_policy_from_settings,
    default_client_policy,
    default_openai_client_policy,
    openai_client_policy_from_settings,
)
from src.services._llm_service.openai_chat import (
    analyze_report,
    openai_chat_json,
    openai_chat_json_with_images,
)
from src.services._llm_service.embeddings import openai_create_embeddings
from src.services._llm_service.openai_responses import (
    openai_ocr_pdf,
    openai_respond_with_vector_store,
)
from src.services._llm_service.openai_shared import (
    OPENAI_OCR_RESPONSE_FORMAT,
    _image_path_to_data_url,
    _strip_json_fence,
    openai_legacy,
)
from src.services._llm_service.openrouter import (
    build_openrouter_client,
    openrouter_chat_json,
)
from src.services._llm_service.vector_store import (
    openai_vector_store_attach_file,
    openai_vector_store_create,
    openai_vector_store_delete,
    openai_vector_store_status,
    openai_vector_store_update_metadata,
    openai_vector_store_upload_file,
)

__all__ = [
    "LLMServiceClient",
    "OPENAI_OCR_RESPONSE_FORMAT",
    "_image_path_to_data_url",
    "_strip_json_fence",
    "analyze_report",
    "build_client",
    "build_client_for_settings",
    "build_client_from_callables",
    "build_model_call_audit_record",
    "build_model_call_replay_bundle",
    "build_openai_client",
    "build_openai_client_for_settings",
    "build_openai_client_from_callables",
    "build_openrouter_client",
    "client_policy_from_settings",
    "default_client_policy",
    "default_openai_client_policy",
    "openai_chat_json",
    "openai_chat_json_with_images",
    "openai_client_policy_from_settings",
    "openai_create_embeddings",
    "openai_legacy",
    "openai_ocr_pdf",
    "openai_respond_with_vector_store",
    "openrouter_chat_json",
    "openai_vector_store_attach_file",
    "openai_vector_store_create",
    "openai_vector_store_delete",
    "openai_vector_store_status",
    "openai_vector_store_update_metadata",
    "openai_vector_store_upload_file",
]
