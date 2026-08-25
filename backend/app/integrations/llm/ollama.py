"""Direct, non-streaming adapter for Ollama's native HTTP API."""

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.domain.recommendations import (
    RecommendationReasoning,
    RecommendationReasoningEvidence,
)
from app.integrations.contracts import LlmProviderStatus
from app.integrations.llm.errors import (
    LlmConfigurationError,
    LlmMalformedResponseError,
    LlmModelUnavailableError,
    LlmTimeoutError,
    LlmUnavailableError,
)


class _Tag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1)


class _TagsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    models: list[_Tag]


class _Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str = Field(min_length=1)


class _ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: _Message


class OllamaLlmProvider:
    """Explain grounded inputs without participating in facts or ranking."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_model
        self._timeout = settings.ollama_request_timeout_seconds
        self._client = client

    async def status(self) -> LlmProviderStatus:
        if not self._base_url or not self._model:
            return self._status(configured=False)
        response = await self._request("GET", "/api/tags")
        try:
            tags = _TagsResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise LlmMalformedResponseError(
                "Ollama returned an invalid model-list response"
            ) from exc
        configured_model = _canonical_model_name(self._model)
        names = {_canonical_model_name(item.name) for item in tags.models}
        return self._status(
            configured=True,
            reachable=True,
            model_available=configured_model in names,
        )

    async def explain(
        self, evidence: RecommendationReasoningEvidence
    ) -> RecommendationReasoning:
        if not self._base_url or not self._model:
            raise LlmConfigurationError("Ollama is not configured")
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Return only JSON satisfying the requested schema. Explain "
                        "why this route appears at its already-determined rank; do "
                        "not rerank it or introduce a hidden score. Do not change "
                        "supplied numbers or generate coordinates or geometry. Use "
                        "only the supplied, pre-approved statements verbatim; do "
                        "not invent conditions, safety claims, or other unsupported "
                        "facts. Treat unknowns as unknown.\n"
                        "evidence="
                        f"{evidence.model_dump_json(exclude={
                            'recommendation': {
                                'candidate': {
                                    'geometry',
                                    'geojson_reference',
                                    'provenance',
                                }
                            }
                        })}"
                    ),
                }
            ],
            "stream": False,
            "format": RecommendationReasoning.model_json_schema(),
            "options": {"temperature": 0},
        }
        response = await self._request("POST", "/api/chat", json=body)
        try:
            chat = _ChatResponse.model_validate(response.json())
            reasoning = RecommendationReasoning.model_validate_json(
                chat.message.content
            )
            _validate_grounded_reasoning(reasoning, evidence)
            return reasoning
        except (ValueError, ValidationError) as exc:
            raise LlmMalformedResponseError(
                "Ollama returned an invalid chat response"
            ) from exc

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        assert self._base_url is not None
        try:
            if self._client is not None:
                response = await self._client.request(
                    method, f"{self._base_url}{path}", timeout=self._timeout, **kwargs
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method,
                        f"{self._base_url}{path}",
                        timeout=self._timeout,
                        **kwargs,
                    )
        except httpx.TimeoutException as exc:
            raise LlmTimeoutError("Ollama request timed out") from exc
        except httpx.RequestError as exc:
            raise LlmUnavailableError("Ollama is unreachable") from exc
        if path == "/api/chat" and response.status_code == 404:
            raise LlmModelUnavailableError("The configured Ollama model is unavailable")
        if response.is_error:
            category = "client" if response.status_code < 500 else "server"
            raise LlmUnavailableError(f"Ollama returned a {category} error")
        return response

    def _status(
        self,
        *,
        configured: bool,
        reachable: bool = False,
        model_available: bool = False,
    ) -> LlmProviderStatus:
        return LlmProviderStatus(
            configured=configured,
            reachable=reachable,
            model_available=model_available,
            provider="ollama",
            model=self._model,
        )


def _canonical_model_name(model: str) -> str:
    """Match Ollama's implicit `latest` tag without altering registry ports."""
    basename = model.rsplit("/", maxsplit=1)[-1]
    if ":" not in basename and "@" not in basename:
        return f"{model}:latest"
    return model


def _validate_grounded_reasoning(
    reasoning: RecommendationReasoning, evidence: RecommendationReasoningEvidence
) -> None:
    """Reject valid-looking prose that was not supplied by trusted application code."""
    fields = ("reasons", "cautions", "highlights", "qualitative_tags")
    if reasoning.summary not in evidence.summaries or any(
        not set(getattr(reasoning, field)).issubset(getattr(evidence, field))
        for field in fields
    ):
        raise LlmMalformedResponseError(
            "Ollama returned reasoning unsupported by supplied evidence"
        )
