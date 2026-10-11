# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

from src.contracts.report_assets import CropRequest
from src.contracts.report_models import CropItem
from src.services.pdf_service import crop_regions

from ._shared import *  # noqa: F401,F403


def test_render_adds_responsive_srcset_for_verified_publication_crop(tmp_path):
    pdf_path = tmp_path / "responsive.pdf"
    document = fitz.open()
    page = document.new_page(width=420, height=560)
    page.insert_text((65, 105), "Annual growth by region", fontsize=16)
    page.draw_line((75, 390), (350, 390), color=(0, 0, 0), width=2)
    page.draw_line((75, 150), (75, 390), color=(0, 0, 0), width=2)
    for index, (x, height) in enumerate(((110, 120), (180, 170), (250, 95))):
        page.draw_rect(
            fitz.Rect(x, 390 - height, x + 35, 390),
            color=(0.1, 0.35, 0.7),
            fill=(0.2, 0.5, 0.85),
        )
        page.insert_text((x, 390 - height - 8), f"{50 + index * 10}%", fontsize=9)
    document.save(pdf_path.as_posix())
    document.close()

    crop = crop_regions(
        CropRequest(
            schema_version="1.0",
            pdf_path=pdf_path.as_posix(),
            out_dir=tmp_path.as_posix(),
            report_name="report",
            items=[
                CropItem(
                    id="primary",
                    type="chart",
                    score=90.0,
                    page=0,
                    bbox=(45.0, 75.0, 385.0, 435.0),
                )
            ],
            subdir="slices",
            pad=0,
            mode="publication_strict",
            dpi=216,
        ),
        _ctx(),
    ).outcomes[0]
    assert crop.accepted is True
    image_path = tmp_path / crop.path
    with Image.open(image_path) as image:
        width, height = image.size
        variant = image.resize((width * 2, height * 2))
    variant_path = image_path.with_name(f"{image_path.stem}@2x{image_path.suffix}")
    variant.save(variant_path)

    data = {
        "title": "Responsive Figure Report",
        "tldr": "TLDR",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "_figure_assets": [
            {
                "image_path": crop.path,
                "page": 0,
                "candidate_id": "primary",
                "kind": "chart",
                "is_primary": True,
                "display_caption": "Primary generated caption",
                "crop_qa_accepted": crop.accepted,
                "crop_qa_sidecar_path": crop.qa_sidecar_path,
                "crop_quality_profile": crop.quality_profile,
                "crop_dpi": crop.dpi,
                "crop_image_sha256": crop.image_sha256,
            }
        ],
        "artifacts": {
            "chart_insight_cards": [
                {
                    "status": "generated",
                    "candidate_id": "primary",
                    "crop_qa_accepted": True,
                    "evidence_id": "f1",
                    "insight_id": "i1",
                    "source_page": 0,
                    "caption": "Primary generated caption",
                    "public_takeaway": "The chart supports the published finding.",
                }
            ]
        },
    }
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data=data,
            doc_name="responsive.pdf",
            file_id="file_responsive",
            out_dir=str(tmp_path),
            preview_png=None,
            final_crop_dpi=216,
        ),
        _ctx(),
    )
    html = Path(response.html_path).read_text(encoding="utf-8")

    image_rel_path = Path(crop.path)
    variant_rel_path = image_rel_path.with_name(
        f"{image_rel_path.stem}@2x{image_rel_path.suffix}"
    )
    expected_srcset = (
        f'srcset="{image_rel_path.as_posix()} 1x, {variant_rel_path.as_posix()} 2x"'
    )
    assert expected_srcset in html
    assert 'sizes="(max-width: 800px) 100vw, 980px"' in html
    assert f'width="{width}"' in html
    assert f'height="{height}"' in html
    assert 'loading="lazy"' in html


__all__ = ["test_render_adds_responsive_srcset_for_verified_publication_crop"]
