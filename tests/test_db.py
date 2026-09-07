from __future__ import annotations

import sqlite3

import pytest

from odoo_ai_agent.sql_guard import SQLGuardError


def test_tables_attendues(db) -> None:  # noqa: ANN001
    tables = db.list_tables()
    for expected in ["res_partner", "sale_order", "sale_order_line", "account_move", "stock_quant"]:
        assert expected in tables


def test_describe_table_renvoie_les_colonnes(db) -> None:  # noqa: ANN001
    columns = {c["column"] for c in db.describe_table("sale_order")}
    assert {"id", "name", "partner_id", "date_order", "state", "amount_untaxed"} <= columns


def test_describe_table_detecte_les_cles_etrangeres(db) -> None:  # noqa: ANN001
    refs = {c["column"]: c["references"] for c in db.describe_table("sale_order_line")}
    assert refs["order_id"].startswith("sale_order")
    assert refs["product_id"].startswith("product_template")


def test_table_inconnue(db) -> None:  # noqa: ANN001
    with pytest.raises(ValueError):
        db.describe_table("table_inexistante")


def test_select_simple(db) -> None:  # noqa: ANN001
    result = db.run_select("SELECT COUNT(*) AS n FROM sale_order")
    assert result.columns == ["n"]
    assert result.rows[0][0] == 160


def test_limite_appliquee(db) -> None:  # noqa: ANN001
    result = db.run_select("SELECT id FROM sale_order")
    assert len(result.rows) == 50  # max_rows de la fixture
    assert result.truncated is True


def test_ecriture_refusee_par_le_garde_fou(db) -> None:  # noqa: ANN001
    with pytest.raises(SQLGuardError):
        db.run_select("DELETE FROM sale_order")


def test_ecriture_refusee_par_l_autorisateur_sqlite(db) -> None:  # noqa: ANN001
    """Deuxième ligne de défense : même en contournant sql_guard, le moteur refuse."""
    with pytest.raises(sqlite3.DatabaseError):
        db._conn.execute("DELETE FROM sale_order")


def test_rendu_markdown(db) -> None:  # noqa: ANN001
    result = db.run_select("SELECT name, state FROM sale_order LIMIT 3")
    rendered = result.to_markdown()
    assert rendered.startswith("| name | state |")
    assert rendered.count("\n") >= 4
