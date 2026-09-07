"""Tests du harnais d'évaluation lui-même.

Un harnais faux donne une fausse confiance : il mérite ses propres tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from evals.run_eval import check_case, extract_numbers
from odoo_ai_agent.agent import AgentAnswer

CASES = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "evals" / "golden_questions.yaml").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("Le total est de 1 234,56 euros.", 1234.56),
        ("Le total est de 1234.56 euros.", 1234.56),
        ("Il y a 160 commandes.", 160.0),
        ("Chiffre : 1 234 567,89 €", 1234567.89),
    ],
)
def test_extraction_des_nombres(texte: str, attendu: float) -> None:
    assert attendu in extract_numbers(texte)


def test_cas_numerique_valide(demo_db_path: Path) -> None:
    case = next(c for c in CASES if c["id"] == "nb_commandes_confirmees")
    answer = AgentAnswer(text="Il y a 122 commandes confirmées.", sql_executed=["SELECT 1"])
    passed, _, expected = check_case(case, answer, demo_db_path)
    # La valeur exacte dépend du jeu de données ; on vérifie la mécanique.
    assert passed is (str(int(float(expected))) in answer.text)


def test_reponse_sans_sql_est_rejetee(demo_db_path: Path) -> None:
    case = next(c for c in CASES if c["id"] == "nb_commandes_confirmees")
    answer = AgentAnswer(text="Il y en a 122.", sql_executed=[])
    passed, reason, _ = check_case(case, answer, demo_db_path)
    assert passed is False
    assert "non ancrée" in reason


def test_cas_de_refus_reussi(demo_db_path: Path) -> None:
    case = next(c for c in CASES if c["id"] == "hors_perimetre")
    answer = AgentAnswer(text="Je ne peux pas répondre : la base ne contient aucune prévision.")
    passed, _, _ = check_case(case, answer, demo_db_path)
    assert passed is True


def test_cas_de_refus_echoue_si_hallucination(demo_db_path: Path) -> None:
    case = next(c for c in CASES if c["id"] == "hors_perimetre")
    answer = AgentAnswer(text="Le chiffre d'affaires du trimestre prochain sera de 250 000 €.")
    passed, _, _ = check_case(case, answer, demo_db_path)
    assert passed is False


def test_toutes_les_questions_ont_un_identifiant_unique() -> None:
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
