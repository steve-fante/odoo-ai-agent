"""Tests du graphe complet, avec un LLM simulé.

Aucun appel réseau, aucune clé d'API : la CI reste verte et gratuite, et les
tests vérifient le comportement de l'orchestration, pas celui du modèle.
"""

from __future__ import annotations

from odoo_ai_agent.agent import OdooAgent
from odoo_ai_agent.config import Settings
from odoo_ai_agent.llm import FakeLLM


def _agent(script, db, retriever, max_steps: int = 8) -> OdooAgent:  # noqa: ANN001
    return OdooAgent(
        llm=FakeLLM(script=script),
        database=db,
        retriever=retriever,
        settings=Settings(max_agent_steps=max_steps),
    )


def test_reponse_directe_sans_outil(db, retriever) -> None:  # noqa: ANN001
    agent = _agent(["Bonjour, posez-moi une question sur la base."], db, retriever)
    answer = agent.ask("Bonjour")
    assert "Bonjour" in answer.text
    assert answer.used_database is False
    assert answer.steps == 1


def test_boucle_outil_puis_reponse(db, retriever) -> None:  # noqa: ANN001
    script = [
        ("run_sql", {"sql": "SELECT COUNT(*) AS n FROM sale_order"}),
        "Il y a 160 bons de commande dans la base.",
    ]
    agent = _agent(script, db, retriever)
    answer = agent.ask("Combien de commandes ?")
    assert "160" in answer.text
    assert answer.used_database is True
    assert answer.sql_executed == ["SELECT COUNT(*) AS n FROM sale_order LIMIT 50"]


def test_enchainement_de_plusieurs_outils(db, retriever) -> None:  # noqa: ANN001
    script = [
        ("list_tables", {}),
        ("describe_table", {"table": "sale_order"}),
        ("search_docs", {"query": "statuts sale_order"}),
        ("run_sql", {"sql": "SELECT COUNT(*) FROM sale_order WHERE state = 'sale'"}),
        "Réponse finale.",
    ]
    agent = _agent(script, db, retriever)
    answer = agent.ask("Combien de commandes confirmées ?")
    noms = [c["tool"] for c in answer.tool_calls]
    assert noms == ["list_tables", "describe_table", "search_docs", "run_sql"]
    assert answer.steps == 5


def test_erreur_sql_renvoyee_au_modele(db, retriever) -> None:  # noqa: ANN001
    """Une requête refusée ne fait pas planter l'agent : il reçoit l'erreur."""
    script = [
        ("run_sql", {"sql": "DELETE FROM sale_order"}),
        ("run_sql", {"sql": "SELECT COUNT(*) FROM sale_order"}),
        "160 commandes.",
    ]
    agent = _agent(script, db, retriever)
    answer = agent.ask("Combien de commandes ?")
    premiere = answer.tool_calls[0]
    assert premiere["ok"] is False
    assert "SELECT" in premiere["error"]
    assert "160" in answer.text


def test_outil_inconnu_ne_fait_pas_planter(db, retriever) -> None:  # noqa: ANN001
    agent = _agent([("outil_fantome", {}), "Je n'ai pas pu utiliser cet outil."], db, retriever)
    answer = agent.ask("Test")
    assert "pas pu" in answer.text


def test_borne_de_pas_respectee(db, retriever) -> None:  # noqa: ANN001
    """Un modèle qui bouclerait à l'infini est arrêté par max_agent_steps."""
    boucle = [("list_tables", {})] * 20
    agent = _agent(boucle, db, retriever, max_steps=4)
    answer = agent.ask("Question qui boucle")
    assert answer.steps == 4
    assert len(answer.tool_calls) <= 4


def test_trace_des_appels_disponible(db, retriever) -> None:  # noqa: ANN001
    script = [("describe_table", {"table": "res_partner"}), "Voici les colonnes."]
    agent = _agent(script, db, retriever)
    answer = agent.ask("Structure de res_partner ?")
    assert answer.tool_calls[0]["arguments"] == {"table": "res_partner"}
    assert answer.tool_calls[0]["ok"] is True


def test_prompt_systeme_transmis(db, retriever) -> None:  # noqa: ANN001
    llm = FakeLLM(script=["ok"])
    agent = OdooAgent(llm=llm, database=db, retriever=retriever, settings=Settings())
    agent.ask("Question")
    assert "N'invente jamais un chiffre" in llm.calls[0]["system"]
    assert {t["name"] for t in llm.calls[0]["tools"]} == {
        "list_tables",
        "describe_table",
        "run_sql",
        "search_docs",
    }
