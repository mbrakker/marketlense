from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.contracts.openai import OpenAIJSONImagePromptRequest
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_analysis import AnalysisStorePackRequest
from src.contracts.run_context import RunContext
from src.services import llm_service, report_analysis_store_service
from src.services.prompt_service import load_prompt_set, render_prompt


@dataclass(frozen=True)
class FigureCaptionDependencies:
    load_prompt_set: Callable[[PromptLoadRequest, RunContext], Any]
    render_prompt: Callable[[PromptRenderRequest, RunContext], Any]
    openai_chat_json_with_images: Callable[
        [OpenAIJSONImagePromptRequest, RunContext], Any
    ]
    analysis_store_pack: Callable[[AnalysisStorePackRequest, RunContext], Any]

    @classmethod
    def default(cls) -> "FigureCaptionDependencies":
        return cls(
            load_prompt_set=load_prompt_set,
            render_prompt=render_prompt,
            openai_chat_json_with_images=llm_service.openai_chat_json_with_images,
            analysis_store_pack=report_analysis_store_service.store_pack,
        )

