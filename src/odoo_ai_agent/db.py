"""Accès en lecture seule à la base Odoo (SQLite pour la démo, PostgreSQL en réel).

Deux implémentations derrière la même interface :

- `SQLiteDatabase` installe un *autorisateur* SQLite qui refuse au niveau du
  moteur toute opération autre qu'une lecture. Même si la validation textuelle
  de `sql_guard` était contournée, l'écriture serait rejetée.
- `PostgresDatabase` ouvre une transaction `READ ONLY` et pose un
  `statement_timeout`. En production on y ajoute un rôle SQL sans droit
  d'écriture : c'est la vraie garantie.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from .sql_guard import sanitize


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    sql: str
    truncated: bool = False

    def to_markdown(self, max_display: int = 30) -> str:
        """Rendu compact, lisible par un LLM comme par un humain."""
        if not self.columns:
            return "_(aucune colonne)_"
        if not self.rows:
            return "_(aucune ligne)_"
        shown = self.rows[:max_display]
        head = "| " + " | ".join(self.columns) + " |"
        sep = "| " + " | ".join("---" for _ in self.columns) + " |"
        body = [
            "| " + " | ".join("" if v is None else str(v) for v in row) + " |" for row in shown
        ]
        out = "\n".join([head, sep, *body])
        if len(self.rows) > max_display:
            out += f"\n\n_({len(self.rows)} lignes, {max_display} affichées)_"
        return out


class Database(Protocol):
    dialect: str

    def run_select(self, sql: str) -> QueryResult: ...
    def list_tables(self) -> list[str]: ...
    def describe_table(self, table: str) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


# --------------------------------------------------------------------------- SQLite


class SQLiteDatabase:
    dialect = "sqlite"

    def __init__(self, path: str | Path, max_rows: int = 200, timeout_s: int = 10) -> None:
        self.path = str(path)
        self.max_rows = max_rows
        self._conn = sqlite3.connect(self.path, timeout=timeout_s)
        self._conn.set_authorizer(self._authorizer)

    @staticmethod
    def _authorizer(action: int, arg1, arg2, db_name, trigger) -> int:  # noqa: ANN001
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
        }
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    def run_select(self, sql: str) -> QueryResult:
        safe_sql = sanitize(sql, self.max_rows)
        cur = self._conn.cursor()
        cur.execute(safe_sql)
        rows = cur.fetchall()
        columns = [d[0] for d in cur.description] if cur.description else []
        cur.close()
        return QueryResult(
            columns=columns,
            rows=rows,
            sql=safe_sql,
            truncated=len(rows) >= self.max_rows,
        )

    def list_tables(self) -> list[str]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [r[0] for r in cur.fetchall()]
        cur.close()
        return tables

    def describe_table(self, table: str) -> list[dict[str, Any]]:
        if table not in self.list_tables():
            raise ValueError(f"Table inconnue : {table}")
        # PRAGMA est bloqué par l'autorisateur : on lit sqlite_master à la place.
        cur = self._conn.cursor()
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,))
        row = cur.fetchone()
        cur.close()
        return _parse_create_table(row[0]) if row and row[0] else []

    def close(self) -> None:
        self._conn.close()


def _parse_create_table(ddl: str) -> list[dict[str, Any]]:
    """Extrait un descriptif de colonnes depuis un CREATE TABLE.

    Volontairement simple : le schéma de démo est écrit par ce dépôt, une seule
    colonne par ligne. Pour un schéma Odoo réel on passe par PostgreSQL, dont
    l'introspection est faite via information_schema.
    """
    body = ddl[ddl.index("(") + 1 : ddl.rindex(")")]
    columns: list[dict[str, Any]] = []
    for raw in body.split(",\n"):
        line = raw.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        columns.append(
            {
                "column": parts[0].strip('"'),
                "type": parts[1],
                "nullable": "NOT NULL" not in line.upper(),
                "references": _extract_reference(line),
            }
        )
    return columns


def _extract_reference(line: str) -> str | None:
    upper = line.upper()
    if "REFERENCES" not in upper:
        return None
    idx = upper.index("REFERENCES") + len("REFERENCES")
    return line[idx:].strip().rstrip(",").split()[0]


# ------------------------------------------------------------------------ PostgreSQL


class PostgresDatabase:
    dialect = "postgresql"

    def __init__(self, url: str, max_rows: int = 200, timeout_s: int = 10) -> None:
        try:
            import psycopg2  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - dépend de l'installation
            raise RuntimeError(
                "psycopg2 est requis pour PostgreSQL : pip install 'odoo-ai-agent[postgres]'"
            ) from exc
        self.max_rows = max_rows
        self._conn = psycopg2.connect(url)
        self._conn.set_session(readonly=True, autocommit=False)
        with self._conn.cursor() as cur:
            cur.execute("SET statement_timeout = %s", (timeout_s * 1000,))

    def run_select(self, sql: str) -> QueryResult:
        safe_sql = sanitize(sql, self.max_rows)
        with self._conn.cursor() as cur:
            cur.execute(safe_sql)
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description] if cur.description else []
        self._conn.rollback()  # aucune transaction ouverte ne traîne
        return QueryResult(columns, rows, safe_sql, truncated=len(rows) >= self.max_rows)

    def list_tables(self) -> list[str]:
        res = self.run_select(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        return [r[0] for r in res.rows]

    def describe_table(self, table: str) -> list[dict[str, Any]]:
        res = self.run_select(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            f"WHERE table_schema = 'public' AND table_name = '{_escape(table)}' "
            "ORDER BY ordinal_position"
        )
        return [
            {"column": r[0], "type": r[1], "nullable": r[2] == "YES", "references": None}
            for r in res.rows
        ]

    def close(self) -> None:
        self._conn.close()


def _escape(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum():
        raise ValueError(f"Nom de table invalide : {identifier}")
    return identifier


# ---------------------------------------------------------------------------- Fabrique


def make_database(url: str, max_rows: int = 200, timeout_s: int = 10) -> Database:
    parsed = urlparse(url)
    if parsed.scheme in ("sqlite", "sqlite3", ""):
        path = url.split("///", 1)[-1] if "///" in url else url
        return SQLiteDatabase(path, max_rows=max_rows, timeout_s=timeout_s)
    if parsed.scheme in ("postgres", "postgresql"):
        return PostgresDatabase(url, max_rows=max_rows, timeout_s=timeout_s)
    raise ValueError(f"Schéma de connexion non supporté : {parsed.scheme}")
