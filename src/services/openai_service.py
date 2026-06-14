from __future__ import annotations

from src.contracts.openai import (
    OpenAIAnalyzeRequest,
    OpenAIAnalyzeResponse,
    OpenAIJSONImagePromptRequest,
    OpenAIJSONPromptRequest,
    OpenAIPdfOcrRequest,
    OpenAIPdfOcrResponse,
    OpenAIResponseRequest,
    OpenAIResponseResult,
    OpenAIVectorStoreAttachFileRequest,
    OpenAIVectorStoreAttachFileResponse,
    OpenAIVectorStoreCreateRequest,
    OpenAIVectorStoreCreateResponse,
    OpenAIVectorStoreDeleteRequest,
    OpenAIVectorStoreDeleteResponse,
    OpenAIVectorStoreFileUploadRequest,
    OpenAIVectorStoreFileUploadResponse,
    OpenAIVectorStoreStatusRequest,
    OpenAIVectorStoreStatusResponse,
    OpenAIVectorStoreUpdateMetadataRequest,
    OpenAIVectorStoreUpdateMetadataResponse,
)
from src.contracts.run_context import RunContext
from src.services._openai_service import base as _base
from src.services._openai_service import chat as _chat
from src.services._openai_service import responses as _responses
from src.services._openai_service import vector_store as _vector_store
from src.services._openai_service.base import (
    OPENAI_OCR_RESPONSE_FORMAT,
    openai_legacy,
    _image_path_to_data_url,
    _strip_json_fence,
)


def analyze_report(
    request: OpenAIAnalyzeRequest, ctx: RunContext
) -> OpenAIAnalyzeResponse:
    return _chat.analyze_report(request, ctx)


def openai_chat_json(
    request: OpenAIJSONPromptRequest, ctx: RunContext
) -> OpenAIResponseResult:
    return _chat.openai_chat_json(request, ctx)


def openai_chat_json_with_images(
    request: OpenAIJSONImagePromptRequest, ctx: RunContext
) -> OpenAIResponseResult:
    return _chat.openai_chat_json_with_images(request, ctx)


def openai_ocr_pdf(
    request: OpenAIPdfOcrRequest, ctx: RunContext
) -> OpenAIPdfOcrResponse:
    return _responses.openai_ocr_pdf(request, ctx)


def openai_respond_with_vector_store(
    request: OpenAIResponseRequest, ctx: RunContext
) -> OpenAIResponseResult:
    return _responses.openai_respond_with_vector_store(request, ctx)


def openai_vector_store_create(
    request: OpenAIVectorStoreCreateRequest, ctx: RunContext
) -> OpenAIVectorStoreCreateResponse:
    return _vector_store.openai_vector_store_create(request, ctx)


def openai_vector_store_upload_file(
    request: OpenAIVectorStoreFileUploadRequest, ctx: RunContext
) -> OpenAIVectorStoreFileUploadResponse:
    return _vector_store.openai_vector_store_upload_file(request, ctx)


def openai_vector_store_attach_file(
    request: OpenAIVectorStoreAttachFileRequest, ctx: RunContext
) -> OpenAIVectorStoreAttachFileResponse:
    return _vector_store.openai_vector_store_attach_file(request, ctx)


def openai_vector_store_status(
    request: OpenAIVectorStoreStatusRequest, ctx: RunContext
) -> OpenAIVectorStoreStatusResponse:
    return _vector_store.openai_vector_store_status(request, ctx)


def openai_vector_store_delete(
    request: OpenAIVectorStoreDeleteRequest, ctx: RunContext
) -> OpenAIVectorStoreDeleteResponse:
    """Delete an OpenAI vector store through the canonical OpenAI boundary."""
    return _vector_store.openai_vector_store_delete(request, ctx)


def openai_vector_store_update_metadata(
    request: OpenAIVectorStoreUpdateMetadataRequest, ctx: RunContext
) -> OpenAIVectorStoreUpdateMetadataResponse:
    return _vector_store.openai_vector_store_update_metadata(request, ctx)


__all__ = [
    "OPENAI_OCR_RESPONSE_FORMAT",
    "openai_legacy",
    "_image_path_to_data_url",
    "_strip_json_fence",
    "analyze_report",
    "openai_chat_json",
    "openai_chat_json_with_images",
    "openai_ocr_pdf",
    "openai_respond_with_vector_store",
    "openai_vector_store_attach_file",
    "openai_vector_store_create",
    "openai_vector_store_delete",
    "openai_vector_store_status",
    "openai_vector_store_update_metadata",
    "openai_vector_store_upload_file",
]
