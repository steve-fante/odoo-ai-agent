"""Démonstration hors ligne, sans clé d'API.

Rejoue un scénario réaliste avec un LLM simulé pour montrer la mécanique de
l'agent : appel d'outils, garde-fou SQL, réponse ancrée sur une requête.

    python scripts/demo_offline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.syntax import Syntax  # noqa: E402

from odoo_ai_agent.agent import OdooAgent  # noqa: E402
from odoo_ai_agent.config import Settings  # noqa: E402
from odoo_ai_agent.db import SQLiteDatabase  # noqa: E402
from odoo_ai_agent.llm import FakeLLM  # noqa: E402
from odoo_ai_agent.retriever import build_retriever  # noqa: E402
from scripts.seed_demo import seed  # noqa: E402

console = Console()

SCENARIO = [
    ("search_docs", {"query": "statuts sale_order chiffre d'affaires", "top_k": 1}),
    ("describe_table", {"table": "sale_order"}),
    # Volontairement dangereuse : montre le garde-fou en action.
    ("run_sql", {"sql": "SELECT amount_untaxed FROM sale_order; DROP TABLE sale_order"}),
    (
        "run_sql",
        {
            "sql": "SELECT ROUND(SUM(amount_untaxed), 2) AS ca FROM sale_order "
            "WHERE state IN ('sale', 'done') AND date_order LIKE '2024%'"
        },
    ),
    "Le chiffre d'affaires hors taxes commandé en 2024 s'élève à 512 905,03 €, "
    "sur les commandes confirmées ou clôturées uniquement.\n\n"
    "```sql\nSELECT ROUND(SUM(amount_untaxed), 2) AS ca FROM sale_order\n"
    "WHERE state IN ('sale', 'done') AND date_order LIKE '2024%'\n```",
]

QUESTION = "Quel est le chiffre d'affaires hors taxes commandé en 2024 ?"


def main() -> int:
    db_path = ROOT / "data" / "demo_odoo.sqlite"
    if not db_path.exists():
        console.print("[dim]Génération de la base de démonstration…[/dim]")
        seed(db_path)

    database = SQLiteDatabase(db_path, max_rows=200)
    agent = OdooAgent(
        llm=FakeLLM(script=SCENARIO),
        database=database,
        retriever=build_retriever(ROOT / "data" / "kb"),
        settings=Settings(),
    )

    console.print(Panel(QUESTION, title="Question", border_style="blue"))
    answer = agent.ask(QUESTION)

    console.print("\n[bold]Trace des outils[/bold]")
    for i, call in enumerate(answer.tool_calls, start=1):
        if call.get("ok"):
            console.print(f"  {i}. [green]OK[/green]    {call['tool']}  {call['arguments']}")
        else:
            console.print(f"  {i}. [red]REFUS[/red] {call['tool']}  → {call['error']}")

    console.print()
    console.print(Panel(answer.text, title="Réponse", border_style="cyan"))
    for sql in answer.sql_executed:
        console.print(Syntax(sql, "sql", theme="ansi_dark", word_wrap=True))

    console.print(
        f"\n[dim]{answer.steps} appels au modèle · "
        f"{len(answer.tool_calls)} appels d'outils · "
        f"réponse ancrée : {answer.used_database}[/dim]"
    )
    database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
