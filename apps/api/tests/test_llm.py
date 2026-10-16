"""LLM layer: adapters build correct requests, JSON repair, registry, portability."""

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import BaseModel

from crowdspawn_api.llm.base import LLMAuthError, LLMBadResponseError, LLMError, LLMRateLimitError
from crowdspawn_api.llm.fake import FakeProvider
from crowdspawn_api.llm.gemini import GeminiProvider
from crowdspawn_api.llm.ollama_cloud import OllamaCloudProvider
from crowdspawn_api.llm.openai_compat import OpenAICompatProvider
from crowdspawn_api.llm.registry import build_provider
from crowdspawn_api.llm.structured import CallBudget, complete_json, extract_json

from .conftest import make_settings

MSGS: list[Any] = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]


class Names(BaseModel):
    names: list[str]


@pytest.mark.parametrize(
    "text",
    [
        '{"names": ["A"]}',
        '```json\n{"names": ["A"]}\n```',
        'Sure! Here you go:\n```\n{"names": ["A"]}\n``` hope it helps',
        'noise {"names": ["A"]} trailing',
    ],
)
def test_extract_json(text: str) -> None:
    assert extract_json(text) == {"names": ["A"]}


def test_extract_json_fails_without_object() -> None:
    with pytest.raises(ValueError):
        extract_json("no json here")


async def test_one_repair_then_success() -> None:
    fake = FakeProvider(replies=["not json", '{"names": ["Hades"]}'])
    budget = CallBudget(4)
    out, _ = await complete_json(fake, MSGS, Names, budget)
    assert out.names == ["Hades"] and budget.used == 2
    assert "invalid" in fake.calls[1][-1]["content"]


async def test_exactly_one_repair_then_error() -> None:
    fake = FakeProvider(replies=["nope", "still nope", '{"names": []}'])
    with pytest.raises(LLMBadResponseError):
        await complete_json(fake, MSGS, Names, CallBudget(4))
    assert len(fake.calls) == 2


async def test_call_budget_cap() -> None:
    budget = CallBudget(1)
    fake = FakeProvider(replies=["bad", "bad"])
    with pytest.raises(LLMError) as e:
        await complete_json(fake, MSGS, Names, budget)
    assert e.value.code == "llm_call_cap"


@respx.mock
async def test_ollama_cloud_request() -> None:
    route = respx.post("https://ollama.com/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hello"},
                "prompt_eval_count": 3,
                "eval_count": 2,
            },
        )
    )
    p = OllamaCloudProvider("https://ollama.com", "k", "gemma4:31b")
    r = await p.complete(MSGS, temperature=0.1, max_tokens=50)
    req = route.calls[0].request
    body = json.loads(req.content)
    assert req.headers["Authorization"] == "Bearer k"
    assert body == {
        "model": "gemma4:31b",
        "messages": MSGS,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 50},
    }
    assert (r.text, r.provider, r.usage) == ("hello", "ollama_cloud", {"prompt": 3, "output": 2})


@respx.mock
async def test_gemini_request_uses_native_schema() -> None:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-x:generateContent"
    route = respx.post(url).mock(
        return_value=httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": '{"names": []}'}]}}]}
        )
    )
    p = GeminiProvider("gk", "gemini-x")
    out, _ = await complete_json(p, MSGS, Names, CallBudget(2))
    body = json.loads(route.calls[0].request.content)
    assert route.calls[0].request.headers["x-goog-api-key"] == "gk"
    assert body["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert body["contents"][0] == {"role": "user", "parts": [{"text": "hi"}]}
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"]["properties"]["names"]
    assert out.names == []


@respx.mock
async def test_openai_compat_request() -> None:
    route = respx.post("https://api.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "yo"}}]})
    )
    p = OpenAICompatProvider("https://api.example.com/v1/", "ok", "m1")
    r = await p.complete(MSGS)
    assert route.calls[0].request.headers["Authorization"] == "Bearer ok"
    assert json.loads(route.calls[0].request.content)["model"] == "m1" and r.text == "yo"


@respx.mock
async def test_error_mapping() -> None:
    respx.post("https://ollama.com/api/chat").mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(429),
            httpx.Response(200, json={"oops": 1}),
            httpx.ReadTimeout("slow"),
        ]
    )
    p = OllamaCloudProvider("https://ollama.com", "k", "m")
    for exc in (LLMAuthError, LLMRateLimitError, LLMBadResponseError, LLMError):
        with pytest.raises(exc):
            await p.complete(MSGS)


@pytest.mark.parametrize(
    ("provider", "over", "expected"),
    [
        ("ollama_cloud", {"ollama_api_key": "k", "ollama_model": "m"}, "ollama_cloud"),
        ("gemini", {"gemini_api_key": "k", "gemini_model": "m"}, "gemini"),
        (
            "openai_compat",
            {"openai_compat_api_key": "k", "openai_compat_base_url": "https://x"},
            "openai_compat",
        ),
        ("fake", {}, "fake"),
        ("ollama_cloud", {}, None),  # no key: brief falls back to the template
        ("fake", {"app_env": "production"}, None),  # fake is never allowed in production
        ("nonsense", {}, None),
    ],
)
def test_registry_selects_by_env(
    tmp_path: Path, provider: str, over: dict[str, Any], expected: str | None
) -> None:
    p = build_provider(make_settings(tmp_path, llm_provider=provider, **over))
    assert (p.name if p else None) == expected


def test_no_provider_names_outside_llm() -> None:
    src = Path(__file__).parents[1] / "src" / "crowdspawn_api"
    pattern = re.compile(r"ollama|gemini|openai", re.IGNORECASE)
    allowed = {"settings.py", "registry.py"}  # settings holds env names; registry wires them
    offenders = [
        str(f.relative_to(src))
        for f in src.rglob("*.py")
        if "llm" not in f.relative_to(src).parts
        and f.name not in allowed
        and pattern.search(f.read_text())
    ]
    assert offenders == []
