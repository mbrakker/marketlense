from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from src.contracts.crop_qa_escalation import (
    CropQaEscalationPolicy,
    CropQaEscalationRequest,
)
from src.generators.crop_qa_escalation_generator import escalate_crop_qa
from src.utils.errors import AppError
from src.contracts.run_context import RunContext


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


class _ImageModelClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests = []

    def openai_chat_json_with_images(self, request, ctx):
        self.requests.append(request)
        return SimpleNamespace(
            text=json.dumps(self.payload),
            parsed_json=self.payload,
            request_id="req-crop-1",
            input_tokens=91,
            output_tokens=19,
            total_tokens=110,
            model=request.model,
        )


def _write_crop(tmp_path: Path, name: str, score: float, defects: list[str]) -> tuple[str, str]:
    crop_path = tmp_path / name
    Image.new("RGB", (220, 120), "white").save(crop_path)
    sidecar_path = crop_path.with_suffix(crop_path.suffix + ".qa.json")
    sidecar_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "mode": "publication_strict",
                "accepted": True,
                "score": score,
                "defects": defects,
                "detectors": {"chart_completeness": {"confidence": 0.71}},
                "render_dpi": 216,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return str(crop_path), str(sidecar_path)


def test_crop_qa_escalation_default_is_deterministic_no_model(tmp_path: Path) -> None:
    crop_path, sidecar_path = _write_crop(tmp_path, "good.png", 91.0, [])
    model_client = _ImageModelClient({"decision": "reject"})

    response = escalate_crop_qa(
        CropQaEscalationRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            crops=[
                {
                    "candidate_id": "c1",
                    "image_path": crop_path,
                    "qa_sidecar_path": sidecar_path,
                    "quality_profile": "publication_strict",
                }
            ],
            policy=CropQaEscalationPolicy(schema_version="1.0", enabled=False),
        ),
        _ctx(),
        llm_client=model_client,
    )

    assert response.model_call_count == 0
    assert response.escalation_rate == 0.0
    assert response.decisions[0].decision == "not_escalated"
    assert response.decisions[0].deterministic_score == 91.0
    assert json.loads(Path(sidecar_path).read_text(encoding="utf-8"))["score"] == 91.0
    assert model_client.requests == []


def test_crop_qa_escalation_calls_model_for_bounded_low_confidence_crop(
    tmp_path: Path,
) -> None:
    crop_path, sidecar_path = _write_crop(
        tmp_path, "borderline.png", 76.0, ["chart_axis_clipped"]
    )
    model_client = _ImageModelClient(
        {
            "decision": "repair",
            "defects": ["axis_clipped"],
            "repair_instruction": "retry publication_strict with a wider right edge",
            "confidence": 0.82,
        }
    )

    response = escalate_crop_qa(
        CropQaEscalationRequest(
            schema_version="1.0",
            output_dir=str(tmp_path),
            crops=[
                {
                    "candidate_id": "chart-1",
                    "image_path": crop_path,
                    "qa_sidecar_path": sidecar_path,
                    "quality_profile": "publication_strict",
                }
            ],
            policy=CropQaEscalationPolicy(
                schema_version="1.0",
                enabled=True,
                low_confidence_min_score=72.0,
                low_confidence_max_score=82.0,
                max_escalations=1,
                max_repairs=1,
                model="gpt-5-mini",
                api_key="test-key",
            ),
        ),
        _ctx(),
        llm_client=model_client,
    )

    assert response.model_call_count == 1
    assert response.repair_count == 1
    assert response.escalation_rate == 1.0
    assert response.decisions[0].candidate_id == "chart-1"
    assert response.decisions[0].decision == "repair"
    assert response.decisions[0].provider_request_id == "req-crop-1"
    assert response.decisions[0].defects == ["axis_clipped"]
    assert model_client.requests[0].image_paths == [crop_path]


def test_crop_qa_escalation_requires_model_client_when_enabled(tmp_path: Path) -> None:
    crop_path, sidecar_path = _write_crop(tmp_path, "borderline.png", 76.0, [])

    try:
        escalate_crop_qa(
            CropQaEscalationRequest(
                schema_version="1.0",
                output_dir=str(tmp_path),
                crops=[
                    {
                        "candidate_id": "chart-1",
                        "image_path": crop_path,
                        "qa_sidecar_path": sidecar_path,
                        "quality_profile": "publication_strict",
                    }
                ],
                policy=CropQaEscalationPolicy(schema_version="1.0", enabled=True),
            ),
            _ctx(),
        )
    except AppError as exc:
        assert exc.code == "model_client_required"
        assert exc.context["scope"] == "crop_qa_escalation"
    else:  # pragma: no cover
        raise AssertionError("Expected AppError")
