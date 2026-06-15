from __future__ import annotations

from typing import Any, cast

from src.services._llm_service.openai_shared import *
from src.services._llm_service.openai_client import *


@dataclass(frozen=True)
class _ChatCompletionRun:
    payload: str
    request_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


def _legacy_chat_completion_call(
    *,
    api_key: str,
    timeout_seconds: float | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    seed: int | None,
) -> _ChatCompletionRun:
    # Compatibility path for environments where OpenAI client instantiation
    # fails (e.g., unexpected kwargs like proxies in older dependencies).
    previous_timeout = getattr(openai_legacy, "timeout", None)
    had_timeout_attr = hasattr(openai_legacy, "timeout")
    previous_max_retries = getattr(openai_legacy, "max_retries", None)
    had_max_retries_attr = hasattr(openai_legacy, "max_retries")
    legacy_openai = cast(Any, openai_legacy)
    legacy_openai.api_key = api_key
    legacy_openai.max_retries = 0
    try:
        if timeout_seconds is not None:
            legacy_openai.timeout = timeout_seconds
        elif had_timeout_attr:
            delattr(legacy_openai, "timeout")
        payload_args = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "seed": seed,
        }
        try:
            payload_args["response_format"] = {"type": "json_object"}
            resp = legacy_openai.ChatCompletion.create(**payload_args)
        except TypeError:
            payload_args.pop("response_format", None)
            resp = legacy_openai.ChatCompletion.create(**payload_args)
        payload = resp["choices"][0]["message"]["content"]
        usage = resp.get("usage") or {}
        return _ChatCompletionRun(
            payload=payload,
            request_id=resp.get("id"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
    finally:
        if had_timeout_attr:
            legacy_openai.timeout = previous_timeout
        else:
            try:
                delattr(legacy_openai, "timeout")
            except AttributeError:
                had_timeout_attr = False
        if had_max_retries_attr:
            legacy_openai.max_retries = previous_max_retries
        else:
            try:
                delattr(legacy_openai, "max_retries")
            except AttributeError:
                had_max_retries_attr = False


def _modern_chat_completion_call(
    *,
    api_key: str,
    timeout_seconds: float | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    seed: int | None,
) -> _ChatCompletionRun:
    client_factory = _openai_client_factory()
    if client_factory is None:
        raise TypeError("OpenAI client not available")
    client_kwargs: dict = {"api_key": api_key, "max_retries": 0}
    if timeout_seconds is not None:
        client_kwargs["timeout"] = timeout_seconds
    client = client_factory(**client_kwargs)
    payload_args = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
    }
    if seed is not None:
        payload_args["seed"] = seed
    resp = client.chat.completions.create(**payload_args)
    usage = getattr(resp, "usage", None)
    return _ChatCompletionRun(
        payload=resp.choices[0].message.content or "",
        request_id=getattr(resp, "id", None),
        prompt_tokens=getattr(usage, "prompt_tokens", None)
        if usage is not None
        else None,
        completion_tokens=getattr(usage, "completion_tokens", None)
        if usage is not None
        else None,
        total_tokens=getattr(usage, "total_tokens", None)
        if usage is not None
        else None,
    )


def _run_chat_completion(
    *,
    api_key: str,
    timeout_seconds: float | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    seed: int | None,
) -> _ChatCompletionRun:
    try:
        return _modern_chat_completion_call(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            seed=seed,
        )
    except TypeError:
        return _legacy_chat_completion_call(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            seed=seed,
        )


def analyze_report(
    request: OpenAIAnalyzeRequest, ctx: RunContext
) -> OpenAIAnalyzeResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_analyze_start",
            module=logger.name,
            fields={
                "model": request.model,
                "temperature": request.temperature,
                "seed": request.seed,
                "timeout_seconds": request.timeout_seconds,
                "prompt_system_sha256": request.prompt_system_sha256,
                "prompt_user_sha256": request.prompt_user_sha256,
            },
        )
    )

    payload = None
    request_id = None
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    tool_calls = request.tool_calls or 0
    cached_tokens = request.cached_input_tokens

    try:
        run = _run_chat_completion(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            model=request.model,
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            temperature=request.temperature,
            seed=request.seed,
        )
        payload = run.payload
        request_id = run.request_id
        prompt_tokens = run.prompt_tokens
        completion_tokens = run.completion_tokens
        total_tokens = run.total_tokens
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_request_failed",
            default_message="OpenAI request failed",
        )
        raise AppError(
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            context={
                "model": request.model,
                "provider_error_type": type(exc).__name__,
            },
        ) from exc

    payload_text = payload if isinstance(payload, str) else ""
    if not payload_text:
        raise AppError(
            code="openai_response_empty",
            message="OpenAI response payload is empty",
            retryable=False,
            context={"model": request.model},
        )

    try:
        data = json.loads(payload_text)
        _validate_payload(data)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="openai_response_invalid_json",
            message="OpenAI response JSON parsing failed",
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc
    except ValueError as exc:
        raise AppError(
            code="openai_response_validation_failed",
            message=str(exc),
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc

    _record_usage_accounting(
        ctx=ctx,
        step_name="openai_analyze",
        model=request.model,
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        cached_input_tokens=int(cached_tokens) if cached_tokens is not None else None,
        tool_calls=tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=request_id,
    )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_analyze_complete",
            module=logger.name,
            fields={
                "request_id": request_id or "",
                "prompt_system_sha256": request.prompt_system_sha256,
                "prompt_user_sha256": request.prompt_user_sha256,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        )
    )

    quote = Quote(
        text=data.get("quote", {}).get("text", ""),
        author=data.get("quote", {}).get("author", "Unknown"),
    )
    figure = Figure(
        title=data.get("figure", {}).get("title", ""),
        evidence=data.get("figure", {}).get("evidence", ""),
    )
    title = (data.get("title") or "").strip()
    publisher = data.get("publisher", "") or ""
    region = data.get("region", "") or ""
    time_period = data.get("time_period", "") or ""
    raw_taxonomy = data.get("taxonomy") or []
    taxonomy = []
    if isinstance(raw_taxonomy, list):
        taxonomy = [str(item).strip() for item in raw_taxonomy if str(item).strip()]
    insights = data.get("insights", [])
    if len(insights) < 5:
        insights = insights + [""] * (5 - len(insights))
    insights = insights[:5]

    result = ReportPayload(
        tldr=data.get("tldr", ""),
        title=title,
        insights=insights,
        quote=quote,
        figure=figure,
        publisher=publisher,
        taxonomy=taxonomy,
        region=region,
        time_period=time_period,
        commentary=data.get("commentary", ""),
        source=data.get("source", ""),
    )

    return OpenAIAnalyzeResponse(
        schema_version="1.0",
        payload=result,
        prompt_system_sha256=request.prompt_system_sha256,
        prompt_user_sha256=request.prompt_user_sha256,
        model=request.model,
        temperature=request.temperature,
        raw_content=payload_text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        request_id=str(request_id) if request_id else None,
    )


def openai_chat_json(
    request: OpenAIJSONPromptRequest, ctx: RunContext
) -> OpenAIResponseResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_start",
            module=logger.name,
            fields={
                "model": request.model,
                "temperature": request.temperature,
                "seed": request.seed,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    cache_spec = _semantic_response_cache_spec(
        request,
        operation="openai_chat_json",
        params={
            "model": request.model,
            "temperature": request.temperature,
            "seed": request.seed,
            "response_format": "json_object",
        },
    )
    if cache_spec is not None:
        cached_payload = _read_semantic_response_cache(cache_spec, ctx)
        if cached_payload is not None:
            return _openai_response_result_from_cache(cached_payload)
    metadata = _OpenAIResponseMetadata(
        text="",
        request_id=None,
        input_tokens=None,
        output_tokens=None,
        tool_calls=0,
        total_tokens=None,
        parsed_json=None,
        parse_strategy="empty",
    )

    try:
        run = _run_chat_completion(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            model=request.model,
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            temperature=request.temperature,
            seed=request.seed,
        )
        metadata = _adapt_chat_completion_metadata(run)
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_chat_failed",
            default_message="OpenAI chat request failed",
        )
        raise AppError(
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            context={
                "model": request.model,
                "provider_error_type": type(exc).__name__,
            },
        ) from exc

    _record_usage_accounting(
        ctx=ctx,
        step_name="openai_chat_json",
        model=request.model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=metadata.request_id,
    )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_complete",
            module=logger.name,
            fields={
                "model": request.model,
                "request_id": metadata.request_id or "",
                "prompt_tokens": metadata.input_tokens,
                "completion_tokens": metadata.output_tokens,
                "total_tokens": metadata.total_tokens,
                "parsed_json": metadata.parsed_json is not None,
            },
        )
    )

    result = OpenAIResponseResult(
        schema_version="1.0",
        text=metadata.text,
        parsed_json=metadata.parsed_json,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        model=request.model,
        total_tokens=metadata.total_tokens,
        request_id=metadata.request_id,
    )
    _write_semantic_response_cache(
        cache_spec,
        ctx,
        response_payload=asdict(result),
    )
    return result


def openai_chat_json_with_images(
    request: OpenAIJSONImagePromptRequest, ctx: RunContext
) -> OpenAIResponseResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_with_images_start",
            module=logger.name,
            fields={
                "model": request.model,
                "temperature": request.temperature,
                "seed": request.seed,
                "timeout_seconds": request.timeout_seconds,
                "image_count": len(request.image_paths or []),
            },
        )
    )
    if not request.image_paths:
        raise AppError(
            code="openai_images_missing",
            message="openai_chat_json_with_images requires at least one image path",
            retryable=False,
        )
    cache_spec = _semantic_response_cache_spec(
        request,
        operation="openai_chat_json_with_images",
        params={
            "model": request.model,
            "temperature": request.temperature,
            "seed": request.seed,
            "response_format": "json_object",
        },
        context={
            "image_fingerprints": [
                _file_fingerprint(path, content_hash=True)
                for path in (request.image_paths or [])
            ],
        },
    )
    if cache_spec is not None:
        cached_payload = _read_semantic_response_cache(cache_spec, ctx)
        if cached_payload is not None:
            return _openai_response_result_from_cache(cached_payload)
    image_urls = [_image_path_to_data_url(path) for path in request.image_paths]
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="chat_json_with_images",
        )
        user_content = [{"type": "input_text", "text": request.user_prompt}]
        user_content.extend(
            {"type": "input_image", "image_url": image_url} for image_url in image_urls
        )
        payload_args: dict[str, Any] = {
            "model": request.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": request.system_prompt}],
                },
                {"role": "user", "content": user_content},
            ],
        }
        known_unsupported = _known_unsupported_responses_params(request.model)
        if request.temperature is not None and "temperature" not in known_unsupported:
            payload_args["temperature"] = request.temperature
        if request.seed is not None and "seed" not in known_unsupported:
            payload_args["seed"] = request.seed
        if known_unsupported:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="openai_chat_json_with_images_skip_known_unsupported_params",
                    module=logger.name,
                    fields={
                        "model": request.model,
                        "skipped_params": sorted(known_unsupported),
                    },
                )
            )
        resp = client.responses.create(**payload_args)
    except AppError:
        raise
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_chat_images_failed",
            default_message="OpenAI JSON+images request failed",
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="openai_chat_json_with_images_error",
                module=logger.name,
                fields={
                    "model": request.model,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        )
        raise AppError(
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            context={
                "model": request.model,
                "provider_error_type": type(exc).__name__,
            },
        ) from exc

    metadata = _adapt_responses_metadata(resp, recover_json_object=False)
    _record_usage_accounting(
        ctx=ctx,
        step_name="openai_chat_json_with_images",
        model=request.model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=metadata.request_id,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_with_images_complete",
            module=logger.name,
            fields={
                "model": request.model,
                "request_id": metadata.request_id or "",
                "image_count": len(request.image_paths or []),
                "input_tokens": metadata.input_tokens,
                "output_tokens": metadata.output_tokens,
                "tool_calls": metadata.tool_calls,
                "parsed_json": metadata.parsed_json is not None,
            },
        )
    )
    result = OpenAIResponseResult(
        schema_version="1.0",
        text=metadata.text,
        parsed_json=metadata.parsed_json,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        model=request.model,
        total_tokens=metadata.total_tokens,
        request_id=metadata.request_id,
    )
    _write_semantic_response_cache(
        cache_spec,
        ctx,
        response_payload=asdict(result),
    )
    return result


__all__ = [name for name in globals() if not name.startswith("__")]
