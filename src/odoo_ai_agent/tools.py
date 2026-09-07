"""Outils exposés au modèle.

Le schéma JSON suit le format « tool use » d'Anthropic, repris tel quel par
l'API OpenAI moyennant une conversion triviale. Chaque outil renvoie du texte :
c'est ce que le modèle sait le mieux consommer, et cela rend les traces
lisibles lors du débogage.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .db import Database
from .retriever import BM25Retriever
from .sql_guard import SQLGuardError

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "list_tables",
        "description": (
            "Liste les tables disponibles dans la base Odoo. "
            "À appeler en premier quand on ignore le nom exact d'une table."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "describe_table",
        "description": (
            "Décrit les colonnes d'une table Odoo : nom, type, nullabilité et clé étrangère. "
            "À appeler avant d'écrire une requête sur une table qu'on n'a pas encore inspectée."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Nom exact de la table, ex. sale_order"}
            },
            "required": ["table"],
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Exécute une requête SELECT en lecture seule sur la base Odoo et renvoie le résultat "
            "sous forme de tableau. Une seule instruction, sans point-virgule. "
            "Les requêtes de modification sont rejetées."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "Requête SELECT (ou WITH ... SELECT)"}
            },
            "required": ["sql"],
        },
    },
    {
        "name": "search_docs",
        "description": (
            "Recherche dans la base de connaissance fonctionnelle Odoo : signification des "
            "champs, valeurs possibles des statuts, règles de gestion. À utiliser quand la "
            "question porte sur le sens métier d'une donnée plutôt que sur un chiffre."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termes de recherche"},
                "top_k": {"type": "integer", "description": "Nombre de documents (défaut 3)"},
            },
            "required": ["query"],
        },
    },
]


@dataclass
class ToolCallResult:
    content: str
    is_error: bool = False


class Toolbox:
    """Fait le lien entre les noms d'outils et les implémentations réelles."""

    def __init__(self, database: Database, retriever: BM25Retriever) -> None:
        self.db = database
        self.retriever = retriever
        self.calls: list[dict[str, Any]] = []  # trace, utilisée par les évaluations
        self._last_sql: str | None = None
        self._handlers: dict[str, Callable[..., str]] = {
            "list_tables": self._list_tables,
            "describe_table": self._describe_table,
            "run_sql": self._run_sql,
            "search_docs": self._search_docs,
        }

    @property
    def executed_sql(self) -> list[str]:
        return [c["result_sql"] for c in self.calls if c.get("result_sql")]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        handler = self._handlers.get(name)
        if handler is None:
            return ToolCallResult(f"Outil inconnu : {name}", is_error=True)
        record: dict[str, Any] = {"tool": name, "arguments": arguments}
        try:
            content = handler(**arguments)
            record["ok"] = True
        except SQLGuardError as exc:
            record.update(ok=False, error=str(exc))
            self.calls.append(record)
            return ToolCallResult(
                f"Requête refusée par le garde-fou SQL : {exc}\n"
                "Reformule une requête SELECT unique, sans point-virgule.",
                is_error=True,
            )
        except Exception as exc:  # noqa: BLE001 - on renvoie l'erreur au modèle
            record.update(ok=False, error=str(exc))
            self.calls.append(record)
            return ToolCallResult(f"Erreur lors de l'exécution : {exc}", is_error=True)
        if name == "run_sql":
            record["result_sql"] = self._last_sql
        self.calls.append(record)
        return ToolCallResult(content)

    # ------------------------------------------------------------------ handlers

    def _list_tables(self) -> str:
        tables = self.db.list_tables()
        return "Tables disponibles :\n" + "\n".join(f"- {t}" for t in tables)

    def _describe_table(self, table: str) -> str:
        columns = self.db.describe_table(table)
        if not columns:
            return f"Aucune colonne trouvée pour {table}."
        lines = [f"Colonnes de {table} :"]
        for col in columns:
            null = "" if col["nullable"] else " NOT NULL"
            ref = f" -> {col['references']}" if col.get("references") else ""
            lines.append(f"- {col['column']} ({col['type']}){null}{ref}")
        return "\n".join(lines)

    def _run_sql(self, sql: str) -> str:
        result = self.db.run_select(sql)
        self._last_sql = result.sql
        header = f"Requête exécutée :\n```sql\n{result.sql}\n```\n\nRésultat :\n"
        return header + result.to_markdown()

    def _search_docs(self, query: str, top_k: int = 3) -> str:
        hits = self.retriever.search(query, top_k=top_k)
        if not hits:
            return "Aucun document pertinent trouvé."
        blocks = [
            f"### {hit.document.title} (source : {hit.document.doc_id}, score {hit.score})\n"
            f"{hit.document.text.strip()}"
            for hit in hits
        ]
        return "\n\n---\n\n".join(blocks)
