"""Interface en ligne de commande."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .agent import OdooAgent
from .config import Settings
from .db import make_database
from .llm import make_llm
from .retriever import build_retriever

console = Console()


def _build_agent(settings: Settings) -> OdooAgent:
    database = make_database(
        settings.database_url,
        max_rows=settings.max_rows,
        timeout_s=settings.query_timeout_s,
    )
    retriever = build_retriever(settings.kb_path)
    llm = make_llm(settings.llm_provider, settings.llm_model, settings.temperature)
    return OdooAgent(llm=llm, database=database, retriever=retriever, settings=settings)


def cmd_ask(args: argparse.Namespace) -> int:
    settings = Settings()
    agent = _build_agent(settings)
    with console.status("[dim]Interrogation de la base…"):
        answer = agent.ask(args.question)

    console.print(Panel(answer.text or "_(réponse vide)_", title="Réponse", border_style="cyan"))

    if args.verbose:
        for call in answer.tool_calls:
            status = "ok" if call.get("ok") else "erreur"
            console.print(f"[dim]· {call['tool']} ({status}) {call.get('arguments', {})}[/dim]")
    for sql in answer.sql_executed:
        console.print(Syntax(sql, "sql", theme="ansi_dark", word_wrap=True))
    if not answer.used_database:
        console.print("[yellow]Attention : aucune requête SQL n'a été exécutée.[/yellow]")
    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    settings = Settings()
    agent = _build_agent(settings)
    console.print("[bold cyan]Agent Odoo[/bold cyan] — Ctrl+C ou « quit » pour sortir.\n")
    while True:
        try:
            question = console.input("[bold]› [/bold]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nAu revoir.")
            return 0
        if question.lower() in {"quit", "exit", ":q"}:
            return 0
        if not question:
            continue
        answer = agent.ask(question)
        console.print(Panel(answer.text, border_style="cyan"))
        for sql in answer.sql_executed:
            console.print(Syntax(sql, "sql", theme="ansi_dark", word_wrap=True))
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    from scripts.seed_demo import seed  # type: ignore[import-not-found]

    path = Path(args.output)
    seed(path)
    console.print(f"[green]Base de démonstration créée :[/green] {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="odoo-ai-agent",
        description="Pose des questions métier en français à une base Odoo.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ask = sub.add_parser("ask", help="Poser une question unique")
    p_ask.add_argument("question", help="La question, entre guillemets")
    p_ask.add_argument("-v", "--verbose", action="store_true", help="Afficher la trace des outils")
    p_ask.set_defaults(func=cmd_ask)

    p_shell = sub.add_parser("shell", help="Session interactive")
    p_shell.set_defaults(func=cmd_shell)

    p_seed = sub.add_parser("seed", help="Générer la base de démonstration")
    p_seed.add_argument("-o", "--output", default="data/demo_odoo.sqlite")
    p_seed.set_defaults(func=cmd_seed)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
