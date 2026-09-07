"""Le graphe LangGraph : boucle raisonnement / action.

    ┌────────┐  tool_use   ┌────────┐
    │ think  │ ──────────▶ │  act   │
    │ (LLM)  │ ◀────────── │(outils)│
    └────┬───┘             └────────┘
         │ texte seul
         ▼
        END

Deux garde-fous d'orchestration :
  - `max_steps` borne le nombre d'aller-retours (une boucle infinie coûte cher) ;
  - le prompt système impose de citer la requête SQL exécutée, ce qui rend
    chaque réponse vérifiable et permet aux évaluations de détecter une
    réponse inventée sans consultation de la base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .config import Settings
from .db import Database
from .llm import LLMClient
from .retriever import BM25Retriever
from .tools import TOOL_SPECS, Toolbox

SYSTEM_PROMPT = """Tu es un assistant spécialisé dans l'analyse d'une base de données Odoo.

Ta mission : répondre à des questions métier en interrogeant la base, jamais de mémoire.

Méthode imposée :
1. Si tu ignores la structure, appelle `list_tables` puis `describe_table`.
2. Si la question porte sur le sens d'un champ ou d'un statut, appelle `search_docs`.
3. Écris une requête SELECT, exécute-la avec `run_sql`.
4. Réponds en français, en une à trois phrases, avec le chiffre exact obtenu.

Règles absolues :
- N'invente jamais un chiffre. Tout nombre cité doit provenir d'un `run_sql`.
- Termine toujours par la requête utilisée, dans un bloc ```sql.
- Si la question ne peut pas être répondue avec les données disponibles, dis-le
  explicitement plutôt que d'approximer.
- Les montants sont en euros, les dates au format AAAA-MM-JJ.
"""


class AgentState(TypedDict):
    messages: list[dict[str, Any]]
    steps: int


@dataclass
class AgentAnswer:
    text: str
    sql_executed: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    steps: int = 0

    @property
    def used_database(self) -> bool:
        return bool(self.sql_executed)


def _last_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message["role"] != "assistant":
            continue
        texts = [b["text"] for b in message["content"] if b.get("type") == "text"]
        if texts:
            return "\n".join(texts).strip()
    return ""


def _tool_uses(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message.get("content", [])
    if isinstance(content, str):
        return []
    return [b for b in content if b.get("type") == "tool_use"]


class OdooAgent:
    def __init__(
        self,
        llm: LLMClient,
        database: Database,
        retriever: BM25Retriever,
        settings: Settings | None = None,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.llm = llm
        self.settings = settings or Settings()
        self.toolbox = Toolbox(database, retriever)
        self.system_prompt = system_prompt
        self._graph = self._build_graph()

    # ------------------------------------------------------------------ graphe

    def _build_graph(self):  # noqa: ANN202
        graph = StateGraph(AgentState)
        graph.add_node("think", self._think)
        graph.add_node("act", self._act)
        graph.set_entry_point("think")
        graph.add_conditional_edges("think", self._route, {"act": "act", "end": END})
        graph.add_edge("act", "think")
        return graph.compile()

    def _think(self, state: AgentState) -> AgentState:
        message = self.llm.chat(self.system_prompt, state["messages"], TOOL_SPECS)
        return {"messages": [*state["messages"], message], "steps": state["steps"] + 1}

    def _act(self, state: AgentState) -> AgentState:
        last = state["messages"][-1]
        results = []
        for block in _tool_uses(last):
            outcome = self.toolbox.dispatch(block["name"], block.get("input") or {})
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": outcome.content,
                    "is_error": outcome.is_error,
                }
            )
        return {
            "messages": [*state["messages"], {"role": "user", "content": results}],
            "steps": state["steps"],
        }

    def _route(self, state: AgentState) -> str:
        if state["steps"] >= self.settings.max_agent_steps:
            return "end"
        return "act" if _tool_uses(state["messages"][-1]) else "end"

    # -------------------------------------------------------------------- API

    def ask(self, question: str) -> AgentAnswer:
        self.toolbox.calls.clear()
        initial: AgentState = {
            "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
            "steps": 0,
        }
        final = self._graph.invoke(initial, config={"recursion_limit": 64})
        return AgentAnswer(
            text=_last_text(final["messages"]),
            sql_executed=list(self.toolbox.executed_sql),
            tool_calls=list(self.toolbox.calls),
            steps=final["steps"],
        )
