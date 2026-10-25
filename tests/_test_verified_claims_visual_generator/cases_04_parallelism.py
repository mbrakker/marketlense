from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from contextlib import suppress
from types import SimpleNamespace

import pytest

from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.prompts import PromptRenderRequest
from src.generators.verified_claims_visual_generator import (
    VerifiedClaimsVisualDependencies,
    evaluate_shortlisted_claims,
)
from src.services.prompt_service import load_prompt_set, render_prompt

from .cases_01_visual import _claim, _ctx, _request, _settings


class _VisualParallelProbe:
    def __init__(self, *, expected_pages: int, synchronize_first_pair: bool) -> None:
        self.expected_pages = expected_pages
        self.synchronize_first_pair = synchronize_first_pair
        self.lock = threading.Lock()
        self.first_pair = threading.Barrier(2, timeout=0.5)
        self.rendered_pages: list[int] = []
        self.phase_by_candidate: dict[str, list[str]] = defaultdict(list)
        self.task_ids_by_candidate: dict[str, set[str]] = defaultdict(set)
        self.completed_candidates: list[str] = []
        self.provider_started_before_render_complete = False
        self.active_provider_calls = 0
        self.max_active_provider_calls = 0


def _parallel_dependencies(
    probe: _VisualParallelProbe,
    *,
    fail_render_prompt_for: str = "",
) -> VerifiedClaimsVisualDependencies:
    def render_page(request, _ctx):
        physical_page = request.page + 1
        with probe.lock:
            probe.rendered_pages.append(physical_page)
        time.sleep(0.005)
        return SimpleNamespace(
            image_path=f"report/crop_refine_pages/page-{request.page}.png"
        )

    def render(request: PromptRenderRequest, render_ctx):
        if fail_render_prompt_for and fail_render_prompt_for in str(
            request.variables.get("claim_json", "")
        ):
            raise RuntimeError("unexpected worker preparation failure")
        return render_prompt(request, render_ctx)

    def call_model(request: OpenAIJSONImagePromptRequest, ctx):
        match = re.search(r"page-(\d+)\.png", request.image_paths[0])
        assert match is not None
        physical_page = int(match.group(1)) + 1
        candidate_id = f"candidate-{physical_page - 4}"
        phase = "correction" if request.max_output_tokens == 4096 else "verification"

        with probe.lock:
            if len(probe.rendered_pages) < probe.expected_pages:
                probe.provider_started_before_render_complete = True
            probe.phase_by_candidate[candidate_id].append(phase)
            probe.task_ids_by_candidate[candidate_id].add(str(ctx.task_id))
            probe.active_provider_calls += 1
            probe.max_active_provider_calls = max(
                probe.max_active_provider_calls, probe.active_provider_calls
            )
        try:
            if (
                probe.synchronize_first_pair
                and phase == "correction"
                and candidate_id in {"candidate-1", "candidate-2"}
            ):
                with suppress(threading.BrokenBarrierError):
                    probe.first_pair.wait()
            time.sleep(0.04 if candidate_id == "candidate-1" else 0.005)
            corrected_claim = f"Corrected claim for {candidate_id}"
            if phase == "correction":
                payload = {
                    "claim": corrected_claim,
                    "status": "corrected",
                    "issues": [],
                }
            else:
                payload = {
                    "outcome": "verified",
                    "diagnostics": [],
                    "source_truth_notes": (
                        f"The chart on physical page {physical_page} reports the "
                        f"61% value for the video-user cohort in {candidate_id}."
                    ),
                    "supporting_physical_pages": [physical_page],
                    "source_truth_notes_by_page": {
                        str(physical_page): (
                            f"The chart on physical page {physical_page} reports the "
                            f"61% value for the video-user cohort in {candidate_id}."
                        )
                    },
                    "verified_fact": {
                        "statement": corrected_claim,
                        "metric": {
                            "label": "Share",
                            "value": "61%",
                            "unit": "%",
                            "cohort": "video users",
                        },
                        "qualifiers": [],
                    },
                }
                with probe.lock:
                    probe.completed_candidates.append(candidate_id)
            return SimpleNamespace(
                parsed_json=payload,
                request_id=f"{candidate_id}-{phase}",
                model=request.model,
            )
        finally:
            with probe.lock:
                probe.active_provider_calls -= 1

    return VerifiedClaimsVisualDependencies(
        load_prompt_set=load_prompt_set,
        render_prompt=render,
        render_page_for_crop_refine=render_page,
        openai_chat_json_with_images=call_model,
    )


def test_parallel_visual_evaluations_are_bounded_and_ordered(tmp_path):
    claims = [
        _claim("candidate-1", "Original 1", page=5),
        _claim("candidate-2", "Original 2", page=6),
        _claim("candidate-3", "Original 3", page=7),
    ]
    probe = _VisualParallelProbe(expected_pages=3, synchronize_first_pair=True)
    settings = _settings(tmp_path)
    settings.verified_visual_claim_parallel_workers = 2

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=settings,
        ctx=_ctx(),
        dependencies=_parallel_dependencies(probe),
    )

    assert [item.candidate_id for item in result.claims] == [
        "candidate-1",
        "candidate-2",
        "candidate-3",
    ]
    assert [item.outcome for item in result.claims] == ["verified"] * 3
    assert all(
        phases == ["correction", "verification"]
        for phases in probe.phase_by_candidate.values()
    )
    assert all(len(task_ids) == 2 for task_ids in probe.task_ids_by_candidate.values())
    assert probe.max_active_provider_calls == 2
    assert probe.completed_candidates.index("candidate-2") < (
        probe.completed_candidates.index("candidate-1")
    )
    assert result.candidate_roster_digest


def test_rendering_completes_before_workers_and_shared_pages_are_reused(tmp_path):
    claims = [
        _claim("candidate-1", "Original 1", page=5),
        _claim("candidate-2", "Original 2", page=6),
    ]
    claims[0]["pages"] = [5, 6]
    claims[0]["evidence_spans"] = [
        {"evidence_id": "f1", "page": 5, "start": 10, "end": 20},
        {"evidence_id": "f1", "page": 6, "start": 10, "end": 20},
    ]
    claims[1]["pages"] = [6, 7]
    claims[1]["evidence_spans"] = [
        {"evidence_id": "f1", "page": 6, "start": 10, "end": 20},
        {"evidence_id": "f1", "page": 7, "start": 10, "end": 20},
    ]
    probe = _VisualParallelProbe(expected_pages=3, synchronize_first_pair=False)
    settings = _settings(tmp_path)
    settings.verified_visual_claim_parallel_workers = 2
    requests: list[OpenAIJSONImagePromptRequest] = []

    dependencies = _parallel_dependencies(probe)
    base_call = dependencies.openai_chat_json_with_images

    def record_call(request, ctx):
        requests.append(request)
        return base_call(request, ctx)

    dependencies = VerifiedClaimsVisualDependencies(
        load_prompt_set=dependencies.load_prompt_set,
        render_prompt=dependencies.render_prompt,
        render_page_for_crop_refine=dependencies.render_page_for_crop_refine,
        openai_chat_json_with_images=record_call,
    )

    result = evaluate_shortlisted_claims(
        request=_request(tmp_path, claims),
        settings=settings,
        ctx=_ctx(),
        dependencies=dependencies,
    )

    assert probe.rendered_pages == [5, 6, 7]
    assert not probe.provider_started_before_render_complete
    assert [request.image_paths for request in requests[:2]] == [
        [
            str(tmp_path / "report/crop_refine_pages/page-4.png"),
            str(tmp_path / "report/crop_refine_pages/page-5.png"),
        ],
        [
            str(tmp_path / "report/crop_refine_pages/page-5.png"),
            str(tmp_path / "report/crop_refine_pages/page-6.png"),
        ],
    ]
    assert result.rendered_pages == {
        5: str(tmp_path / "report/crop_refine_pages/page-4.png"),
        6: str(tmp_path / "report/crop_refine_pages/page-5.png"),
        7: str(tmp_path / "report/crop_refine_pages/page-6.png"),
    }


def test_unexpected_worker_preparation_exception_fails_closed(tmp_path):
    claims = [
        _claim("candidate-1", "Original 1", page=5),
        _claim("candidate-2", "Original 2", page=6),
        _claim("candidate-3", "Original 3", page=7),
    ]
    probe = _VisualParallelProbe(expected_pages=3, synchronize_first_pair=False)
    settings = _settings(tmp_path)
    settings.verified_visual_claim_parallel_workers = 2

    with pytest.raises(RuntimeError, match="unexpected worker preparation failure"):
        evaluate_shortlisted_claims(
            request=_request(tmp_path, claims),
            settings=settings,
            ctx=_ctx(),
            dependencies=_parallel_dependencies(
                probe, fail_render_prompt_for="candidate-2"
            ),
        )

    assert "candidate-3" not in probe.phase_by_candidate


def test_worker_count_one_preserves_structural_results(tmp_path):
    claims = [
        _claim("candidate-1", "Original 1", page=5),
        _claim("candidate-2", "Original 2", page=6),
    ]
    sequential_root = tmp_path / "sequential"
    parallel_root = tmp_path / "parallel"
    sequential_root.mkdir()
    parallel_root.mkdir()
    sequential_settings = _settings(sequential_root)
    sequential_settings.verified_visual_claim_parallel_workers = 1
    sequential_probe = _VisualParallelProbe(
        expected_pages=2, synchronize_first_pair=False
    )
    sequential = evaluate_shortlisted_claims(
        request=_request(sequential_root, claims),
        settings=sequential_settings,
        ctx=_ctx(),
        dependencies=_parallel_dependencies(sequential_probe),
    )

    parallel_settings = _settings(parallel_root)
    parallel_settings.verified_visual_claim_parallel_workers = 2
    parallel_probe = _VisualParallelProbe(
        expected_pages=2, synchronize_first_pair=False
    )
    parallel = evaluate_shortlisted_claims(
        request=_request(parallel_root, claims),
        settings=parallel_settings,
        ctx=_ctx(),
        dependencies=_parallel_dependencies(parallel_probe),
    )

    def structural(response):
        return [
            (
                item.candidate_id,
                item.outcome,
                item.final_claim,
                item.physical_pages,
                item.evidence_ids,
                item.verified_fact,
            )
            for item in response.claims
        ]

    assert structural(sequential) == structural(parallel)
    assert sequential.candidate_roster_digest == parallel.candidate_roster_digest
