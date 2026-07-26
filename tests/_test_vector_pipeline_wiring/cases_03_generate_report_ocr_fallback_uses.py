# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_generate_report_ocr_fallback_uses_ocr_pdf_for_vector_and_original_for_visuals(
    tmp_path,
) -> None:
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(
        **{
            **settings.__dict__,
            "openai_timeout_seconds": 3600.0,
            "pdf_text_ocr_enabled": True,
            "pdf_text_ocr_cache_enabled": False,
        }
    )
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    file = DriveFile(
        schema_version="1.0",
        file_id="file_vs",
        name="vector.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-vs",
        task_id="task-vs",
        span_id="span-vs",
    )
    ocr_pdf_path = str(tmp_path / "ocr.pdf")
    preview_paths: list[str] = []
    figure_paths: list[str] = []
    candidate_paths: list[str] = []
    vector_upload_paths: list[str] = []

    def _sample(req, ctx):
        if req.path == str(pdf_path):
            return PdfTextSampleResponse(
                schema_version="1.0",
                samples=[
                    PdfTextSample(
                        page_index=0, page_number=1, char_count=0, has_text=False
                    )
                ],
                any_text=False,
            )
        return PdfTextSampleResponse(
            schema_version="1.0",
            samples=[
                PdfTextSample(page_index=0, page_number=1, char_count=18, has_text=True)
            ],
            any_text=True,
        )

    def _render_preview(req, ctx):
        preview_paths.append(req.pdf_path)
        return SimpleNamespace(
            schema_version="1.1",
            image_path=str(tmp_path / "preview.png"),
            page_number=0,
        )

    def _extract_best_figure(req, ctx):
        figure_paths.append(req.pdf_path)
        return SimpleNamespace(image_path=None, caption=None)

    def _collect_candidates(req, ctx):
        candidate_paths.append(req.pdf_path)
        return SimpleNamespace(candidates=[])

    def _vector_store_upload_file(req, ctx):
        vector_upload_paths.append(req.file_path)
        return SimpleNamespace(openai_file_id="file_upload")

    def _render_report(req, ctx):
        output_path = tmp_path / "out.html"
        output_path.write_text("<html><body>Published</body></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(output_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        sample_pdf_text=_sample,
        openai_ocr_pdf=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            pages=[
                SimpleNamespace(schema_version="1.0", page_number=1, text="ocr text")
            ],
            raw_text='{"pages":[{"page_number":1,"text":"ocr text"}]}',
            model=req.model,
            request_id="req_ocr",
        ),
        render_text_pdf=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            output_path=ocr_pdf_path,
            rendered_page_count=len(req.pages),
        ),
        extract_pdf_text=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            text="ocr text",
            pages_extracted=1,
            char_count=8,
            text_density=8.0,
        ),
        detect_contents_page=lambda req, ctx: SimpleNamespace(
            schema_version="1.0",
            path=req.path,
            has_contents=False,
            page_index=-1,
            page_number=0,
            heading="",
            confidence=0.0,
        ),
        render_preview=_render_preview,
        extract_best_figure=_extract_best_figure,
        collect_candidates=_collect_candidates,
        vector_store_upload_file=_vector_store_upload_file,
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {"docMap": {"title": "Doc Title", "publisher": "Doc Publisher"}}
        },
        generate_artifacts=lambda **kwargs: _analysis_artifacts(),
        run_validation=lambda *args, **kwargs: ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(tmp_path / "validation.json"),
        ),
        render_report=_render_report,
    )

    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
    )

    assert outcome.status == "processed"
    assert outcome.ocr_fallback_used is True
    assert outcome.ocr_pdf_path == ocr_pdf_path
    assert vector_upload_paths == [ocr_pdf_path]
    assert preview_paths == [str(pdf_path)]
    assert figure_paths == [str(pdf_path)]
    assert candidate_paths == [str(pdf_path)]


def test_generate_report_vector_store_figure_caption_fail_open_runs_before_validation(
    tmp_path,
) -> None:
    settings = _ingest_settings(tmp_path)
    settings = settings.__class__(
        **{
            **settings.__dict__,
            "figure_caption_enabled": True,
            "figure_caption_prompt_namespace": "report_vs/figure_caption",
            "figure_caption_max_chars": 120,
            "openai_models": {"report_vs/figure_caption": "gpt-5-caption"},
        }
    )
    pdf_path = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as handle:
        writer.write(handle)

    file = DriveFile(
        schema_version="1.0",
        file_id="file_vs",
        name="vector.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    ctx = RunContext(
        schema_version="1.0",
        run_id="run-vs",
        task_id="task-vs",
        span_id="span-vs",
    )
    execution_trace: list[str] = []
    analysis_store: list[tuple[str, object]] = []

    def _extract_best_figure(req, _ctx):
        execution_trace.append("figure_select")
        return SimpleNamespace(
            image_path="vector/assets/figure.png",
            caption="Detected figure caption",
            page=0,
        )

    def _store_pack(request, _ctx):
        analysis_store.append((request.pack_name, request.payload))
        return SimpleNamespace(
            output_path=str(
                Path(request.output_dir)
                / slugify(request.report_slug or request.report_id)
                / "report_analysis"
                / f"{request.pack_name}.json"
            )
        )

    def _fake_artifacts(
        report_id,
        doc_map,
        evidence_packs,
        settings,
        vector_store_id=None,
        source_status=None,
        ctx=None,
        report_name=None,
        **kwargs,
    ):
        execution_trace.append("artifacts")
        payload = _analysis_artifacts()
        _store_pack(
            AnalysisStorePackRequest(
                schema_version="1.0",
                output_dir=settings.output_dir,
                report_id=report_id,
                pack_name="artifacts",
                payload=payload,
                report_slug=report_name,
            ),
            ctx,
        )
        return payload

    def _fake_load_prompt_set(request, _ctx):
        execution_trace.append("caption_prompt")
        return SimpleNamespace(
            system=SimpleNamespace(
                path="src/prompts/report_vs/figure_caption/system.yaml",
                text='{"instruction":"limit {{ max_chars }}"}',
                sha256="system-sha",
            ),
            user=SimpleNamespace(
                path="src/prompts/report_vs/figure_caption/user.yaml",
                text='{"context": {{ context_json }}, "limit": {{ max_chars }}}',
                sha256="user-sha",
            ),
        )

    def _fake_render_prompt(request, _ctx):
        text = request.template.text
        for key, value in request.variables.items():
            text = text.replace("{{ " + key + " }}", str(value))
        return SimpleNamespace(schema_version="1.0", text=text)

    def _fake_openai_chat_json_with_images(request, _ctx):
        execution_trace.append("figure_caption")
        raise RuntimeError("caption_provider_down")

    def _fake_validation(req, settings, ctx, pack_name="validation", **kwargs):
        execution_trace.append("validation")
        assert req.report.figure.title == "Detected figure caption"
        assert req.report._figure_assets[0].display_caption == "Detected figure caption"
        slug = slugify(kwargs.get("report_name") or req.report_id)
        return ValidationReport(
            schema_version="1.1",
            status="pass",
            severity="pass",
            issues=[],
            source_path=str(
                Path(settings.output_dir)
                / slug
                / "report_analysis"
                / f"{pack_name}.json"
            ),
        )

    def _fake_render_report(req, _ctx):
        execution_trace.append("render")
        assert (
            req.data["_figure_assets"][0]["display_caption"]
            == "Detected figure caption"
        )
        html_path = tmp_path / "out.html"
        html_path.write_text("<html></html>", encoding="utf-8")
        return RenderResponse(schema_version="1.0", html_path=str(html_path))

    deps = _base_vector_report_dependencies(
        tmp_path,
        extract_best_figure=_extract_best_figure,
        collect_candidates=lambda req, _ctx: SimpleNamespace(candidates=[]),
        load_prompt_set=_fake_load_prompt_set,
        render_prompt=_fake_render_prompt,
        openai_chat_json_with_images=_fake_openai_chat_json_with_images,
        generate_evidence_packs=lambda **kwargs: {
            "doc_map": {
                "docMap": {
                    "title": "Doc Title",
                    "publisher": "Doc Publisher",
                    "sections": [
                        {"title": "Overview", "summary": "Summary", "pages": [1]}
                    ],
                }
            },
            "findings": {"findings": []},
        },
        generate_artifacts=_fake_artifacts,
        run_validation=_fake_validation,
        analysis_store_pack=_store_pack,
        render_report=_fake_render_report,
        upsert_report_metadata=lambda req, _ctx: None,
        get_report_metadata=lambda req, _ctx: ReportMetadataGetResponse(
            schema_version="1.1",
            file_id="file_vs",
            title="Doc Title",
            created_at=1,
            updated_at=2,
            file_name="vector.pdf",
            publisher="Doc Publisher",
            taxonomy=["tag"],
            categories=[],
            region="US",
            time_period="2024",
            source_url=None,
            html_path=None,
            md5="md5",
            page_count=1,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id="vs_new",
            evidence_pack_paths={},
        ),
    )

    outcome = rgo.run_report_generation(
        file,
        str(pdf_path),
        settings,
        md5="md5",
        ctx=ctx,
        dependencies=deps,
    )

    assert outcome.status == "processed"
    assert outcome.evidence_packs is not None
    assert "figure_captions" in outcome.evidence_packs
    assert execution_trace.index("artifacts") < execution_trace.index("figure_caption")
    assert execution_trace.index("figure_caption") < execution_trace.index("validation")
    assert execution_trace.index("validation") < execution_trace.index("render")
    pack_names = [name for name, _payload in analysis_store]
    assert "figure_captions" in pack_names


__all__ = [
    "test_generate_report_ocr_fallback_uses_ocr_pdf_for_vector_and_original_for_visuals",
    "test_generate_report_vector_store_figure_caption_fail_open_runs_before_validation",
]
