"""Clients LLM interchangeables.

L'agent ne dépend d'aucun fournisseur : il manipule des messages au format
« blocs de contenu » (texte / tool_use / tool_result). `FakeLLM` rejoue un
scénario écrit à la main, ce qui permet de tester tout le graphe hors ligne,
sans clé d'API ni coût — condition pour que la CI reste verte et gratuite.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMClient(Protocol):
    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Renvoie un message assistant : {"role": "assistant", "content": [blocs]}."""
        ...


# --------------------------------------------------------------------------- Anthropic


class AnthropicClient:
    def __init__(self, model: str, api_key: str | None = None, temperature: float = 0.0) -> None:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Le paquet anthropic est requis : pip install 'odoo-ai-agent[anthropic]'"
            ) from exc
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY absent. Copiez .env.example vers .env et renseignez la clé."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model

        # `temperature` n'est plus accepté par messages.create() dans les versions
        # récentes du SDK. Conservé pour la compatibilité de l'interface, non transmis.
        self.temperature = temperature

    def chat(self, system, messages, tools):  # noqa: ANN001, ANN201
        response = self._client.messages.create(
            model=self.model,
            max_tokens=2048,
           #temperature=self.temperature,
            system=system,
            tools=tools,
            messages=messages,
        )
        content = []
        for block in response.content:
            if block.type == "text":
                content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
        return {"role": "assistant", "content": content}


# ------------------------------------------------------------------------------ OpenAI


class OpenAIClient:
    """Adaptateur OpenAI : conversion des schémas d'outils et des messages."""

    def __init__(self, model: str, api_key: str | None = None, temperature: float = 0.0) -> None:
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Le paquet openai est requis : pip install 'odoo-ai-agent[openai]'"
            ) from exc
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY absent.")
        self._client = OpenAI(api_key=key)
        self.model = model
        self.temperature = temperature

    @staticmethod
    def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    @staticmethod
    def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for message in messages:
            content = message["content"]
            if isinstance(content, str):
                out.append({"role": message["role"], "content": content})
                continue
            if message["role"] == "assistant":
                text = "".join(b["text"] for b in content if b["type"] == "text")
                calls = [
                    {
                        "id": b["id"],
                        "type": "function",
                        "function": {"name": b["name"], "arguments": _dumps(b["input"])},
                    }
                    for b in content
                    if b["type"] == "tool_use"
                ]
                entry: dict[str, Any] = {"role": "assistant", "content": text or None}
                if calls:
                    entry["tool_calls"] = calls
                out.append(entry)
            else:
                for block in content:
                    if block["type"] == "tool_result":
                        out.append(
                            {
                                "role": "tool",
                                "tool_call_id": block["tool_use_id"],
                                "content": block["content"],
                            }
                        )
                    elif block["type"] == "text":
                        out.append({"role": "user", "content": block["text"]})
        return out

    def chat(self, system, messages, tools):  # noqa: ANN001, ANN201
        payload = [{"role": "system", "content": system}, *self._to_openai_messages(messages)]
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=payload,
            tools=self._to_openai_tools(tools),
        )
        choice = response.choices[0].message
        content: list[dict[str, Any]] = []
        if choice.content:
            content.append({"type": "text", "text": choice.content})
        for call in choice.tool_calls or []:
            content.append(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.function.name,
                    "input": _loads(call.function.arguments),
                }
            )
        return {"role": "assistant", "content": content}


def _dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _loads(value: str) -> Any:
    import json

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


# -------------------------------------------------------------------------------- Fake


@dataclass
class FakeLLM:
    """Rejoue une liste de réponses préparées. Utilisé par les tests.

    Chaque élément de `script` est soit une chaîne (réponse texte finale),
    soit un tuple (nom_outil, arguments) qui produit un bloc tool_use.
    """

    script: list[Any]
    calls: list[dict[str, Any]] = field(default_factory=list)
    _cursor: int = 0

    def chat(self, system, messages, tools):  # noqa: ANN001, ANN201
        self.calls.append({"system": system, "messages": list(messages), "tools": tools})
        if self._cursor >= len(self.script):
            return {
                "role": "assistant",
                "content": [{"type": "text", "text": "Fin du scénario de test."}],
            }
        step = self.script[self._cursor]
        self._cursor += 1
        if isinstance(step, str):
            return {"role": "assistant", "content": [{"type": "text", "text": step}]}
        name, arguments = step
        return {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": f"call_{self._cursor}",
                    "name": name,
                    "input": arguments,
                }
            ],
        }


def make_llm(provider: str, model: str, temperature: float = 0.0) -> LLMClient:
    provider = provider.lower()
    if provider == "anthropic":
        return AnthropicClient(model=model, temperature=temperature)
    if provider == "openai":
        return OpenAIClient(model=model, temperature=temperature)
    raise ValueError(f"Fournisseur LLM inconnu : {provider}")
