"""Deterministic provider for tests and CI. Never selectable in production."""

import json
from typing import Any

from .base import LLMResult, Message

FACTS_START, FACTS_END = "<facts>", "</facts>"


class FakeProvider:
    name = "fake"
    model = "fake-1"
    supports_native_schema = False

    def __init__(self, replies: list[str] | None = None, prefix: str = ""):
        self.replies = list(replies or [])
        self.prefix = prefix  # lets tests make two "providers" word things differently
        self.calls: list[list[Message]] = []

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        json_schema: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> LLMResult:
        self.calls.append(messages)
        if self.replies:
            text = self.replies.pop(0)
        else:
            joined = "\n".join(m["content"] for m in messages)
            if '{"summary"' in joined:  # scout judge explanation: echo the verdict facts
                facts = json.loads(joined.split(FACTS_START, 1)[1].split(FACTS_END, 1)[0])
                text = json.dumps(
                    {
                        "summary": f"{facts['verdict']} with spawn score {facts['spawn score']} at {facts['confidence']} confidence."
                    }
                )
            elif '{"answer"' in joined:  # ask the plan: quote the top city
                facts = json.loads(joined.split(FACTS_START, 1)[1].split(FACTS_END, 1)[0])
                c = facts["cities"][0]
                text = json.dumps(
                    {
                        "answer": f"**{c['name']}** leads with spawn score {c['spawn_score']} [{c['result_ids'][0]}]."
                    }
                )
            elif FACTS_START in joined:
                text = self._brief(joined)
            elif '"anchors"' in joined:
                anchors = [
                    {"name": "Gully Boy", "type": "movie"},
                    {"name": "Not A Real Film 404", "type": "movie"},
                ]
                text = json.dumps({"anchors": anchors})
            else:
                names = ["Hades", "Dead Cells", "Slay the Spire", "Not A Real Game 9000"]
                text = json.dumps({"names": names})
        return LLMResult(text=text, model=self.model, provider=self.name)

    def _brief(self, prompt: str) -> str:
        facts = json.loads(prompt.split(FACTS_START, 1)[1].split(FACTS_END, 1)[0])
        top = facts["cities"][:3]
        body = " ".join(
            f"**{c['name']}** has spawn score {c['spawn_score']} [{c['result_ids'][0]}]."
            for c in top
        )
        return json.dumps(
            {
                "sections": [
                    {"heading": "Where to launch", "body": f"{self.prefix}{body}"},
                    {
                        "heading": "Caveats",
                        "body": "This is an affinity index, not a sales forecast.",
                    },
                ]
            }
        )

    async def aclose(self) -> None:
        return None
