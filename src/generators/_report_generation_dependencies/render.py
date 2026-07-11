from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.contracts.cover_images import CoverImageGenerationRequest
from src.contracts.files import (
    FileBundleHashRequest,
    FileStatRequest,
    JsonObjectCacheReadRequest,
    JsonObjectCacheWriteRequest,
    ReadTextRequest,
    WriteBytesRequest,
)
from src.contracts.report_assets import PreviewRequest, RenderRequest, RenderResponse
from src.contracts.report_cards import (
    ReportCardManifestWriteRequest,
    ReportCardManifestWriteResponse,
)
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataUpsertRequest,
    ReportSourceIdentityResolveRequest,
)
from src.contracts.run_context import RunContext
from src.generators.cover_image_generator import generate_cover_images
from src.services.file_service import (
    file_stat,
    hash_file_bundle,
    read_json_object_cache,
    read_text,
    write_json_object_cache,
    write_bytes,
    write_report_card_manifest,
)
from src.services.pdf_service import render_preview as render_preview_service
from src.services.render_service import render_report as render_report_service
from src.services.report_store_service import (
    get_metadata as get_report_metadata,
    resolve_report_source_identity,
    upsert_metadata as upsert_report_metadata,
)


@dataclass(frozen=True)
class ReportRenderDependencies:
    render_preview: Callable[[PreviewRequest, RunContext], Any]
    upsert_report_metadata: Callable[[ReportMetadataUpsertRequest, RunContext], Any]
    get_report_metadata: Callable[[ReportMetadataGetRequest, RunContext], Any]
    resolve_report_source_identity: Callable[
        [ReportSourceIdentityResolveRequest, RunContext], Any
    ]
    render_report: Callable[[RenderRequest, RunContext], RenderResponse]
    generate_cover_images: Callable[[CoverImageGenerationRequest, RunContext], Any]
    file_stat: Callable[[FileStatRequest, RunContext], Any]
    read_text: Callable[[ReadTextRequest, RunContext], Any]
    write_bytes: Callable[[WriteBytesRequest, RunContext], Any]
    write_report_card_manifest: Callable[
        [ReportCardManifestWriteRequest, RunContext], ReportCardManifestWriteResponse
    ]
    read_json_object_cache: Callable[[JsonObjectCacheReadRequest, RunContext], Any] = (
        read_json_object_cache
    )
    write_json_object_cache: Callable[
        [JsonObjectCacheWriteRequest, RunContext], Any
    ] = write_json_object_cache
    hash_file_bundle: Callable[[FileBundleHashRequest, RunContext], Any] = (
        hash_file_bundle
    )

    @classmethod
    def default(cls) -> "ReportRenderDependencies":
        return cls(
            render_preview=render_preview_service,
            upsert_report_metadata=upsert_report_metadata,
            get_report_metadata=get_report_metadata,
            resolve_report_source_identity=resolve_report_source_identity,
            render_report=render_report_service,
            generate_cover_images=generate_cover_images,
            file_stat=file_stat,
            read_text=read_text,
            write_bytes=write_bytes,
            write_report_card_manifest=write_report_card_manifest,
            read_json_object_cache=read_json_object_cache,
            write_json_object_cache=write_json_object_cache,
            hash_file_bundle=hash_file_bundle,
        )
