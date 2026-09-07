"""Validation défensive des requêtes SQL produites par le modèle.

Principe retenu : ne jamais faire confiance au texte généré par un LLM.
Trois lignes de défense se cumulent, et ce module n'en est que la première :

1. validation syntaxique et lexicale ici (une seule instruction, SELECT seul,
   pas de mot-clé de modification, pas de fonction système dangereuse) ;
2. borne systématique du nombre de lignes (`enforce_limit`) ;
3. côté base : utilisateur en lecture seule, transaction READ ONLY et
   `statement_timeout` (voir `db.py`), plus un autorisateur SQLite.

La couche 3 est la seule réellement inviolable. Les couches 1 et 2 servent à
échouer tôt, avec un message que l'agent peut comprendre et corriger.
"""

from __future__ import annotations

import re

__all__ = ["SQLGuardError", "normalise", "ensure_read_only", "enforce_limit", "sanitize"]


class SQLGuardError(ValueError):
    """Levée quand une requête est refusée avant exécution."""


_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_WS_RE = re.compile(r"\s+")

# Mots-clés qui modifient les données, le schéma ou la session.
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "insert", "update", "delete", "drop", "alter", "create", "truncate",
        "replace", "merge", "upsert", "grant", "revoke", "attach", "detach",
        "pragma", "vacuum", "reindex", "copy", "call", "do", "execute", "exec",
        "commit", "rollback", "savepoint", "begin", "set", "reset", "listen",
        "notify", "lock", "cluster", "refresh", "prepare", "deallocate",
    }
)

# Fonctions permettant de lire des fichiers, dormir ou sortir de la base.
_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_sleep",
        "lo_import", "lo_export", "dblink", "dblink_exec", "load_extension",
        "readfile", "writefile", "system",
    }
)

_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*")
_LIMIT_RE = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)


def normalise(sql: str) -> str:
    """Retire les commentaires, normalise les espaces, enlève le `;` final."""
    if sql is None:
        raise SQLGuardError("Requête vide.")
    cleaned = _COMMENT_RE.sub(" ", sql)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned:
        raise SQLGuardError("Requête vide après nettoyage des commentaires.")
    return cleaned


def _words_outside_strings(sql: str) -> list[str]:
    """Extrait les identifiants en ignorant le contenu des littéraux texte.

    Sans cela, une requête légitime comme `WHERE name = 'Mise a jour'`
    déclencherait une fausse alerte sur le mot « update ».
    """
    buffer: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == quote:
                # '' et "" échappent le guillemet en SQL standard
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        buffer.append(ch)
        i += 1
    if quote is not None:
        raise SQLGuardError("Littéral texte non refermé dans la requête.")
    return _WORD_RE.findall("".join(buffer).lower())


def ensure_read_only(sql: str) -> str:
    """Refuse tout ce qui n'est pas une unique requête de lecture."""
    cleaned = normalise(sql)

    if ";" in cleaned:
        raise SQLGuardError(
            "Une seule instruction SQL est autorisée (le caractère ';' est interdit)."
        )

    words = _words_outside_strings(cleaned)
    if not words:
        raise SQLGuardError("Aucune instruction SQL détectée.")

    if words[0] not in {"select", "with"}:
        raise SQLGuardError(
            f"Seules les requêtes SELECT sont autorisées (reçu : « {words[0].upper()} »)."
        )

    forbidden = sorted(set(words) & _FORBIDDEN_KEYWORDS)
    if forbidden:
        raise SQLGuardError(
            "Mot-clé interdit dans une requête de lecture : " + ", ".join(forbidden)
        )

    dangerous = sorted(set(words) & _FORBIDDEN_FUNCTIONS)
    if dangerous:
        raise SQLGuardError("Fonction système interdite : " + ", ".join(dangerous))

    return cleaned


def enforce_limit(sql: str, max_rows: int) -> str:
    """Garantit qu'aucune requête ne peut renvoyer plus de `max_rows` lignes."""
    if max_rows <= 0:
        raise ValueError("max_rows doit être strictement positif.")

    match = _LIMIT_RE.search(sql)
    if match is None:
        return f"{sql} LIMIT {max_rows}"

    requested = int(match.group(1))
    if requested <= max_rows:
        return sql
    start, end = match.span(1)
    return sql[:start] + str(max_rows) + sql[end:]


def sanitize(sql: str, max_rows: int) -> str:
    """Enchaîne validation et bornage. C'est le seul point d'entrée à utiliser."""
    return enforce_limit(ensure_read_only(sql), max_rows)
