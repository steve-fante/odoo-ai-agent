"""Agent IA pour interroger une base Odoo en langage naturel.

Le paquet expose :
  - `sql_guard`  : validation défensive des requêtes générées par le modèle
  - `db`         : accès en lecture seule à SQLite ou PostgreSQL
  - `schema`     : introspection du schéma Odoo
  - `retriever`  : recherche BM25 dans la base de connaissance fonctionnelle
  - `tools`      : les outils mis à disposition du modèle
  - `agent`      : le graphe LangGraph qui orchestre le tout
"""

__version__ = "0.1.0"
