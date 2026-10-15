"""Provider-agnostic JSON output: prompt with the schema, extract, validate, one repair retry."""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .base import LLMBadResponseError, LLMError, LLMProvider, LLMResult, Message

PROMPTS = Path(__file__).parent / "prompts"
FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class CallBudget:
    """Hard cap on LLM calls per plan (L8), repairs included."""

    def __init__(self, max_calls: int):
        self.max_calls = max_calls
        self.used = 0

    def take(self) -> None:
        if self.used >= self.max_calls:
            raise LLMError(f"LLM call cap of {self.max_calls} reached", code="llm_call_cap")
        self.used += 1


def render(name: str, **values: str) -> str:
    text = (PROMPTS / f"{name}.md").read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def extract_json(text: str) -> Any:
    """Strip code fences and noise, then parse the outermost JSON object."""
    m = FENCE.search(text)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


async def complete_json[T: BaseModel](
    provider: LLMProvider,
    messages: list[Message],
    model: type[T],
    budget: CallBudget,
    *,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    timeout: float = 60.0,
) -> tuple[T, LLMResult]:
    schema = model.model_json_schema()
    msgs: list[Message] = [
        *messages,
        {
            "role": "user",
            "content": "Return ONLY a JSON object matching this JSON schema, no prose, no code fences:\n"
            + json.dumps(schema),
        },
    ]
    native = schema if provider.supports_native_schema else None
    for attempt in range(2):
        budget.take()
        result = await provider.complete(
            msgs,
            temperature=min(temperature, 0.2),
            max_tokens=max_tokens,
            json_schema=native,
            timeout=timeout,
        )
        try:
            return model.model_validate(extract_json(result.text)), result
        except (ValueError, ValidationError) as e:
            if attempt == 1:
                raise LLMBadResponseError(f"invalid JSON after one repair: {str(e)[:200]}") from e
            msgs = [
                *msgs,
                {"role": "assistant", "content": result.text[:4000]},
                {
                    "role": "user",
                    "content": f"That reply was invalid: {str(e)[:500]}. "
                    "Return only the corrected JSON object.",
                },
            ]
    raise AssertionError("unreachable")
