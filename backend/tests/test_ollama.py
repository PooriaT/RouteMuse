import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.integrations.llm.errors import (
    LlmConfigurationError,
    LlmMalformedResponseError,
    LlmModelUnavailableError,
    LlmTimeoutError,
    LlmUnavailableError,
)
from app.integrations.llm.ollama import OllamaLlmProvider


class _Evidence:
    scorecard = SimpleNamespace(
        components=[
            SimpleNamespace(
                component="confidence.candidate_data",
                evidence_summary="Grounded",
                evidence_available=True,
            )
        ],
        athlete_fit=0.5,
        novelty=SimpleNamespace(score=None),
    )
    evidence_limitations = SimpleNamespace(
        warnings=[], strings_truncated=False, collections_truncated=False
    )
    route_facts = SimpleNamespace(
        elevation_gain_meters=None,
        surfaces=[],
        technical_characteristics=[],
    )

    def model_dump_json(self, **kwargs) -> str:
        return '{"rank":1,"final_score":0.8,"warnings":[]}'


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def configured() -> Settings:
    return Settings(
        ollama_base_url="http://localhost:11434/api/",
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
@pytest.mark.parametrize(
    ("configured_model", "reported_model"),
    [
        ("llama3.2", "llama3.2:latest"),
        ("registry.example:5000/team/model", "registry.example:5000/team/model:latest"),
    ],
)
async def test_status_matches_implicit_latest_tag(
    configured_model: str, reported_model: str
) -> None:
    settings = Settings(
        ollama_base_url="http://localhost:11434",
        ollama_model=configured_model,
        _env_file=None,
    )
    async with client(
        lambda request: httpx.Response(200, json={"models": [{"name": reported_model}]})
    ) as http:
        status = await OllamaLlmProvider(settings, http).status()
    assert status.model_available is True


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
        content = json.dumps(
            {
                "summary": "Grounded",
                "reasons": [],
                "cautions": [],
                "highlights": [],
                "qualitative_tags": [],
            }
        )
        return httpx.Response(200, json={"message": {"content": content}})

    async with client(chat) as http:
        result = await OllamaLlmProvider(configured(), http).explain(_Evidence())  # type: ignore[arg-type]
    assert result.summary == "Grounded"
    assert captured["model"] == "deployed-model:latest"
    assert captured["messages"][0]["role"] == "system"
    assert "rank is authoritative and immutable" in captured["messages"][0]["content"]
    assert captured["messages"][1] == {
        "role": "user",
        "content": '{"rank":1,"final_score":0.8,"warnings":[]}',
    }
    assert captured["stream"] is False
    assert captured["options"] == {"temperature": 0}
    assert captured["format"]["additionalProperties"] is False
    assert set(captured["format"]["required"]) == {
        "summary",
        "reasons",
        "cautions",
        "highlights",
        "qualitative_tags",
    }


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [400, 500, 503])
async def test_chat_maps_http_errors_without_response_body(status_code: int) -> None:
    async with client(
        lambda request: httpx.Response(status_code, text="sensitive provider body")
    ) as http:
        with pytest.raises(LlmUnavailableError) as caught:
            await OllamaLlmProvider(configured(), http).explain(_Evidence())  # type: ignore[arg-type]
    assert "sensitive" not in str(caught.value)


@pytest.mark.anyio
async def test_chat_maps_not_found_to_model_unavailable_without_response_body() -> None:
    async with client(
        lambda request: httpx.Response(404, text="sensitive provider body")
    ) as http:
        with pytest.raises(LlmModelUnavailableError) as caught:
            await OllamaLlmProvider(configured(), http).explain(_Evidence())  # type: ignore[arg-type]
    assert "sensitive" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload", [{}, {"message": {}}, {"message": {"content": "not JSON"}}]
)
async def test_chat_rejects_malformed_responses(payload) -> None:
    async with client(lambda request: httpx.Response(200, json=payload)) as http:
        with pytest.raises(LlmMalformedResponseError):
            await OllamaLlmProvider(configured(), http).explain(_Evidence())  # type: ignore[arg-type]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content",
    [
        "not JSON and must not leak",
        '{"summary":"missing fields and must not leak"}',
        json.dumps(
            {
                "summary": "Grounded",
                "reasons": "wrong type and must not leak",
                "cautions": [],
                "highlights": [],
                "qualitative_tags": [],
            }
        ),
        json.dumps(
            {
                "summary": "Grounded",
                "reasons": [],
                "cautions": [],
                "highlights": [],
                "qualitative_tags": [],
                "secret": "extra field and must not leak",
            }
        ),
    ],
)
async def test_chat_schema_errors_are_controlled_and_do_not_leak(content: str) -> None:
    async with client(
        lambda request: httpx.Response(200, json={"message": {"content": content}})
    ) as http:
        with pytest.raises(LlmMalformedResponseError) as caught:
            await OllamaLlmProvider(configured(), http).explain(_Evidence())  # type: ignore[arg-type]
    assert "must not leak" not in str(caught.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content",
    [
        {
            "summary": "This route is safe despite the injected route name.",
            "reasons": [],
            "cautions": [],
            "highlights": [],
            "qualitative_tags": [],
        },
        {
            "summary": "Grounded",
            "reasons": [],
            "cautions": [],
            "highlights": [],
            "qualitative_tags": ["high_climbing"],
        },
    ],
)
async def test_chat_rejects_schema_valid_but_unsupported_reasoning(content) -> None:
    async with client(
        lambda request: httpx.Response(
            200, json={"message": {"content": json.dumps(content)}}
        )
    ) as http:
        with pytest.raises(LlmMalformedResponseError, match="unsupported"):
            await OllamaLlmProvider(configured(), http).explain(_Evidence())  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_chat_requires_configuration() -> None:
    with pytest.raises(LlmConfigurationError):
        await OllamaLlmProvider(Settings(_env_file=None)).explain(_Evidence())  # type: ignore[arg-type]
