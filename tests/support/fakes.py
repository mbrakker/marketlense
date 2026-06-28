from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class FakeHttpResponse:
    status_code: int
    text: str
    headers: dict[str, Any]
    reason: str

    @classmethod
    def from_payload(
        cls,
        *,
        status_code: int,
        payload: object | None = None,
        text: str | None = None,
        headers: dict[str, Any] | None = None,
        reason: str = "",
    ) -> "FakeHttpResponse":
        rendered = text if text is not None else json.dumps(payload)
        return cls(
            status_code=status_code,
            text=rendered,
            headers=dict(headers or {}),
            reason=reason,
        )


@dataclass(frozen=True)
class RecordedHttpRequest:
    method: str
    url: str
    headers: dict[str, Any]
    params: dict[str, Any]
    data: Any
    files: dict[str, Any]
    allow_redirects: Any
    timeout: Any
    verify: Any

    @property
    def json_data(self) -> Any:
        raw = self.data
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return raw
        return json.loads(raw)


HttpRouteHandler = Callable[[RecordedHttpRequest], FakeHttpResponse]


class RequestsRouter:
    def __init__(self) -> None:
        self._routes: dict[
            tuple[str, str], list[FakeHttpResponse | Exception | HttpRouteHandler]
        ] = {}
        self.calls: list[RecordedHttpRequest] = []

    def add(
        self,
        method: str,
        url: str,
        *responses: FakeHttpResponse | Exception | HttpRouteHandler,
    ) -> None:
        if not responses:
            raise AssertionError("at least one fake response is required")
        key = (method.upper(), url)
        self._routes.setdefault(key, []).extend(responses)

    def add_json(
        self,
        method: str,
        url: str,
        *,
        status_code: int,
        payload: object | None = None,
        text: str | None = None,
        headers: dict[str, Any] | None = None,
        reason: str = "",
    ) -> None:
        self.add(
            method,
            url,
            FakeHttpResponse.from_payload(
                status_code=status_code,
                payload=payload,
                text=text,
                headers=headers,
                reason=reason,
            ),
        )

    def calls_for(self, method: str, url: str) -> list[RecordedHttpRequest]:
        lookup = (method.upper(), url)
        return [
            call for call in self.calls if (call.method.upper(), call.url) == lookup
        ]

    def get(
        self,
        url: str,
        *,
        headers: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        allow_redirects: Any = True,
        timeout: Any = None,
        verify: Any = None,
    ) -> FakeHttpResponse:
        return self._dispatch(
            "GET",
            url,
            headers=headers,
            params=params,
            data=None,
            files=None,
            allow_redirects=allow_redirects,
            timeout=timeout,
            verify=verify,
        )

    def post(
        self,
        url: str,
        *,
        headers: dict[str, Any] | None = None,
        data: Any = None,
        files: dict[str, Any] | None = None,
        allow_redirects: Any = True,
        timeout: Any = None,
        verify: Any = None,
    ) -> FakeHttpResponse:
        return self._dispatch(
            "POST",
            url,
            headers=headers,
            params=None,
            data=data,
            files=files,
            allow_redirects=allow_redirects,
            timeout=timeout,
            verify=verify,
        )

    def _dispatch(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, Any] | None,
        params: dict[str, Any] | None,
        data: Any,
        files: dict[str, Any] | None,
        allow_redirects: Any,
        timeout: Any,
        verify: Any,
    ) -> FakeHttpResponse:
        call = RecordedHttpRequest(
            method=method.upper(),
            url=url,
            headers=dict(headers or {}),
            params=dict(params or {}),
            data=data,
            files=dict(files or {}),
            allow_redirects=allow_redirects,
            timeout=timeout,
            verify=verify,
        )
        self.calls.append(call)
        key = (call.method, call.url)
        queue = self._routes.get(key)
        if not queue:
            raise AssertionError(
                f"no fake route registered for {call.method} {call.url}"
            )
        current = queue[0]
        if len(queue) > 1:
            queue.pop(0)
        if isinstance(current, Exception):
            raise current
        if callable(current):
            return current(call)
        return current


@dataclass(frozen=True)
class FakeOpenAIResult:
    output_text: str
    usage: dict[str, Any]
    id: str = "resp_1"


class FakeOpenAIBoundary:
    def __init__(self) -> None:
        self.client_kwargs: list[dict[str, Any]] = []
        self.calls: dict[str, list[dict[str, Any]]] = {
            "embeddings.create": [],
            "responses.create": [],
            "vector_stores.create": [],
            "vector_stores.delete": [],
            "vector_stores.retrieve": [],
            "vector_stores.update": [],
            "vector_stores.files.create": [],
            "files.create": [],
        }
        self._queues: dict[str, list[Any]] = {name: [] for name in self.calls}

    def add(self, operation: str, *items: Any) -> None:
        if operation not in self._queues:
            raise AssertionError(f"unknown fake OpenAI operation: {operation}")
        if not items:
            raise AssertionError("at least one fake OpenAI item is required")
        self._queues[operation].extend(items)

    def queue_response_text(
        self,
        text: str,
        *,
        usage: dict[str, Any] | None = None,
        request_id: str = "resp_1",
    ) -> None:
        self.add(
            "responses.create",
            FakeOpenAIResult(
                output_text=text,
                usage=usage
                or {"input_tokens": 10, "output_tokens": 20, "total_tool_calls": 2},
                id=request_id,
            ),
        )

    def client_factory(self, **kwargs: Any) -> "_FakeOpenAIClient":
        self.client_kwargs.append(dict(kwargs))
        return _FakeOpenAIClient(self)

    def _resolve(self, operation: str, call: dict[str, Any]) -> Any:
        self.calls[operation].append(dict(call))
        queue = self._queues[operation]
        if not queue:
            raise AssertionError(f"no fake OpenAI item registered for {operation}")
        current = queue[0]
        if len(queue) > 1:
            queue.pop(0)
        if isinstance(current, Exception):
            raise current
        if callable(current):
            return current(call)
        return current


class _FakeResponsesResource:
    def __init__(self, boundary: FakeOpenAIBoundary) -> None:
        self._boundary = boundary

    def create(self, **kwargs: Any) -> Any:
        return self._boundary._resolve("responses.create", kwargs)


class _FakeEmbeddingsResource:
    def __init__(self, boundary: FakeOpenAIBoundary) -> None:
        self._boundary = boundary

    def create(self, **kwargs: Any) -> Any:
        return self._boundary._resolve("embeddings.create", kwargs)


class _FakeVectorStoreFilesResource:
    def __init__(self, boundary: FakeOpenAIBoundary) -> None:
        self._boundary = boundary

    def create(self, **kwargs: Any) -> Any:
        return self._boundary._resolve("vector_stores.files.create", kwargs)


class _FakeVectorStoresResource:
    def __init__(self, boundary: FakeOpenAIBoundary) -> None:
        self._boundary = boundary
        self.files = _FakeVectorStoreFilesResource(boundary)

    def create(self, **kwargs: Any) -> Any:
        return self._boundary._resolve("vector_stores.create", kwargs)

    def retrieve(self, vector_store_id: str) -> Any:
        return self._boundary._resolve(
            "vector_stores.retrieve", {"vector_store_id": vector_store_id}
        )

    def update(self, **kwargs: Any) -> Any:
        return self._boundary._resolve("vector_stores.update", kwargs)

    def delete(self, vector_store_id: str) -> Any:
        return self._boundary._resolve(
            "vector_stores.delete", {"vector_store_id": vector_store_id}
        )


class _FakeFilesResource:
    def __init__(self, boundary: FakeOpenAIBoundary) -> None:
        self._boundary = boundary

    def create(self, **kwargs: Any) -> Any:
        return self._boundary._resolve("files.create", kwargs)


class _FakeOpenAIClient:
    def __init__(self, boundary: FakeOpenAIBoundary) -> None:
        self.embeddings = _FakeEmbeddingsResource(boundary)
        self.responses = _FakeResponsesResource(boundary)
        self.vector_stores = _FakeVectorStoresResource(boundary)
        self.files = _FakeFilesResource(boundary)
