from dataclasses import replace
from types import SimpleNamespace

from src.contracts.drive import DriveFile
from src.contracts.report_generation import ReportRuntimeState
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.generators.report_generation_shared import derive_title, report_slug
from src.generators.report_title_identity_generator import (
    resolve_ambiguous_report_title,
)
from src.generators.report_title_resolution_generator import resolve_report_title


def test_ambiguous_title_uses_one_bounded_identity_image_call(
    ingest_settings, run_context, tmp_path
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="retail-media-outlook-2026.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    settings = replace(
        ingest_settings,
        output_dir=str(tmp_path),
        llm_execution_policies={},
        llm_routing={},
    )
    runtime = ReportRuntimeState(
        schema_version="1.0",
        file=file,
        local_pdf_path=str(tmp_path / file.name),
        settings=settings,
        md5="md5",
        ctx=run_context,
        file_name=file.name,
        report_name=report_slug(file.name, file.file_id),
        report_title=derive_title(file.name),
        analysis_mode="vector_store",
        analysis_modes=["vector_store"],
        report_worker_limit=1,
        parallel_within_file=False,
    )
    cover_path = tmp_path / "cover.png"
    cover_path.write_bytes(b"test image")
    dependencies = replace(
        ReportSourceDependencies.default(),
        render_preview=lambda request, ctx: SimpleNamespace(image_path="cover.png"),
    )
    pages = [
        (2, "Retail Media Outlook 2026\nExample Research"),
        (3, "Commerce Media Outlook 2026\nExample Research"),
    ]
    deterministic = resolve_report_title(
        file_name=file.name,
        pdf_metadata={"Title": "PowerPoint Presentation"},
        pages=pages,
    )
    requests = []

    class IdentityClient:
        def openai_chat_json_with_images(self, request, ctx):
            requests.append(request)
            return SimpleNamespace(
                parsed_json={
                    "title": "Retail Media Outlook 2026",
                    "edition": "2026",
                    "publisher_candidate": "Example Research",
                    "confidence": "high",
                    "evidence": ["cover page", "page 3"],
                }
            )

    result = resolve_ambiguous_report_title(
        runtime=runtime,
        dependencies=dependencies,
        pdf_metadata={"Title": "PowerPoint Presentation"},
        pages=pages,
        deterministic_resolution=deterministic,
        llm_client=IdentityClient(),
    )

    assert result.title == "Retail Media Outlook 2026"
    assert result.candidate_source == "llm_identity_resolution"
    assert len(requests) == 1
    assert requests[0].image_paths == [str(cover_path)]
    assert "PowerPoint Presentation" in requests[0].user_prompt
    assert "Retail Media Outlook 2026" in requests[0].user_prompt
    assert "candidates" not in requests[0].user_prompt
