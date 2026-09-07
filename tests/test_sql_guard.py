"""Le garde-fou SQL est la pièce la plus sensible : il est testé en premier."""

from __future__ import annotations

import pytest

from odoo_ai_agent.sql_guard import SQLGuardError, enforce_limit, ensure_read_only, sanitize


@pytest.mark.parametrize(
    "query",
    [
        "SELECT 1",
        "select name from res_partner where customer_rank > 0",
        "WITH t AS (SELECT id FROM sale_order) SELECT COUNT(*) FROM t",
        "SELECT name FROM res_partner WHERE name = 'Mise a jour du contrat'",
        "SELECT name FROM res_partner WHERE name = 'L''entreprise'",
        "SELECT id FROM sale_order -- commentaire\n WHERE state = 'sale'",
        "/* en-tête */ SELECT id FROM sale_order",
    ],
)
def test_requetes_acceptees(query: str) -> None:
    assert ensure_read_only(query)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM res_partner",
        "UPDATE sale_order SET state = 'done'",
        "INSERT INTO res_partner (name) VALUES ('x')",
        "DROP TABLE sale_order",
        "SELECT 1; DROP TABLE sale_order",
        "SELECT 1; SELECT 2",
        "PRAGMA table_info(sale_order)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_sleep(30)",
        "ATTACH DATABASE '/tmp/x.db' AS x",
        "  ",
        "",
    ],
)
def test_requetes_refusees(query: str) -> None:
    with pytest.raises(SQLGuardError):
        ensure_read_only(query)


def test_apostrophe_non_fermee_est_refusee() -> None:
    with pytest.raises(SQLGuardError):
        ensure_read_only("SELECT * FROM res_partner WHERE name = 'abc")


def test_limit_ajoutee_si_absente() -> None:
    assert enforce_limit("SELECT id FROM sale_order", 100).endswith("LIMIT 100")


def test_limit_conservee_si_plus_petite() -> None:
    assert enforce_limit("SELECT id FROM sale_order LIMIT 5", 100).endswith("LIMIT 5")


def test_limit_ramenee_au_plafond() -> None:
    out = enforce_limit("SELECT id FROM sale_order LIMIT 9999", 100)
    assert out.endswith("LIMIT 100")


def test_sanitize_enchaine_les_deux_etapes() -> None:
    out = sanitize("SELECT id FROM sale_order;", 20)
    assert out == "SELECT id FROM sale_order LIMIT 20"


def test_mot_interdit_dans_un_litteral_est_tolere() -> None:
    """Un faux positif ici rendrait l'agent inutilisable sur des données réelles."""
    out = sanitize("SELECT id FROM res_partner WHERE name = 'Delete Express'", 10)
    assert "Delete Express" in out
