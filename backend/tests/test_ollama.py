import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.llm.errors import (
    LlmConfigurationError,
    LlmMalformedResponseError,
    LlmTimeoutError,
    LlmUnavailableError,
)
from app.integrations.llm.ollama import OllamaLlmProvider


class _Grounded:
    def model_dump_json(self) -> str:
        return '{"grounded":true}'


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def configured() -> Settings:
    return Settings(
        ollama_base_url="http://localhost:11434/",
        ollama_model="deployed-model:latest",
        _env_file=None,
    )


@pytest.mark.anyio
async def test_unconfigured_status_does_not_make_an_http_request() -> None:
    status = await OllamaLlmProvider(Settings(_env_file=None)).status()
    assert (status.configured, status.reachable, status.model_available) == (
        False,
        False,
        False,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("models", "available"),
    [
        ([{"name": "deployed-model:latest"}], True),
        ([], False),
        ([{"name": "other"}], False),
    ],
)
async def test_status_checks_tags_and_model_availability(models, available) -> None:
    async with client(
        lambda request: httpx.Response(200, json={"models": models})
    ) as http:
        status = await OllamaLlmProvider(configured(), http).status()
    assert status.reachable is True
    assert status.model_available is available


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [{}, {"models": "bad"}, {"models": [{}]}])
async def test_status_rejects_malformed_tags(payload) -> None:
    async with client(lambda request: httpx.Response(200, json=payload)) as http:
        with pytest.raises(LlmMalformedResponseError):
            await OllamaLlmProvider(configured(), http).status()


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [500, 503])
async def test_status_maps_server_errors(status_code: int) -> None:
    async with client(
        lambda request: httpx.Response(status_code, text="internal details")
    ) as http:
        with pytest.raises(LlmUnavailableError, match="server error"):
            await OllamaLlmProvider(configured(), http).status()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (httpx.ReadTimeout("late"), LlmTimeoutError),
        (httpx.ConnectError("refused"), LlmUnavailableError),
    ],
)
async def test_status_maps_transport_failures(failure, error) -> None:
    def fail(request):
        raise failure

    async with client(fail) as http:
        with pytest.raises(error):
            await OllamaLlmProvider(configured(), http).status()


@pytest.mark.anyio
async def test_chat_request_and_response() -> None:
    captured = {}

    def chat(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert str(request.url) == "http://localhost:11434/api/chat"
        content = json.dumps({"summary": "Grounded", "reasons": [], "warnings": []})
        return httpx.Response(200, json={"message": {"content": content}})

    async with client(chat) as http:
        result = await OllamaLlmProvider(configured(), http).explain(
            _Grounded(), _Grounded()
        )  # type: ignore[arg-type]
    assert result.summary == "Grounded"
    assert captured["model"] == "deployed-model:latest"
    assert captured["stream"] is False
    assert captured["options"] == {"temperature": 0}


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [400, 404, 500, 503])
async def test_chat_maps_http_errors_without_response_body(status_code: int) -> None:
    async with client(
        lambda request: httpx.Response(status_code, text="sensitive provider body")
    ) as http:
        with pytest.raises(LlmUnavailableError) as caught:
            await OllamaLlmProvider(configured(), http).explain(
                _Grounded(), _Grounded()
            )  # type: ignore[arg-type]
    assert "sensitive" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload", [{}, {"message": {}}, {"message": {"content": "not JSON"}}]
)
async def test_chat_rejects_malformed_responses(payload) -> None:
    async with client(lambda request: httpx.Response(200, json=payload)) as http:
        with pytest.raises(LlmMalformedResponseError):
            await OllamaLlmProvider(configured(), http).explain(
                _Grounded(), _Grounded()
            )  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_chat_requires_configuration() -> None:
    with pytest.raises(LlmConfigurationError):
        await OllamaLlmProvider(Settings(_env_file=None)).explain(
            _Grounded(), _Grounded()
        )  # type: ignore[arg-type]
