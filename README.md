# odoo-ai-agent

**Un agent IA qui répond en français à des questions métier sur une base Odoo, sans jamais inventer un chiffre.**

[![CI](https://github.com/steve-fante/odoo-ai-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/steve-fante/odoo-ai-agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Licence](https://img.shields.io/badge/licence-MIT-green)

---

## Le problème

Dans une PME équipée d'Odoo, la question « quel est mon encours client ? » suppose
de connaître trois choses : que les factures vivent dans `account_move`, que
`move_type` doit valoir `out_invoice`, et que `payment_state` distingue `not_paid`
de `partial`. Le directeur financier ne les connaît pas. Il demande au consultant,
qui écrit la requête. Le délai se compte en jours.

Brancher un LLM sur la base ne suffit pas : il produira des requêtes plausibles et
fausses, ou pire, des chiffres inventés sans avoir consulté quoi que ce soit.

Ce dépôt traite les trois problèmes réels de ce cas d'usage :

| Problème | Réponse apportée |
|---|---|
| Le modèle ignore les règles de gestion Odoo | Base de connaissance fonctionnelle interrogée par BM25 |
| Le modèle peut écrire une requête destructrice | Trois couches de garde-fous, dont un autorisateur SQLite |
| Le modèle peut inventer un chiffre | Évaluation qui vérifie l'exactitude **et** l'ancrage sur une requête réelle |

## Démonstration en 30 secondes, sans clé d'API

```bash
git clone https://github.com/steve-fante/odoo-ai-agent.git
cd odoo-ai-agent
pip install -e ".[dev]"
python scripts/demo_offline.py
```

```
╭─ Question ───────────────────────────────────────────────────────────╮
│ Quel est le chiffre d'affaires hors taxes commandé en 2024 ?         │
╰──────────────────────────────────────────────────────────────────────╯

Trace des outils
  1. OK    search_docs     {'query': "statuts sale_order chiffre d'affaires"}
  2. OK    describe_table  {'table': 'sale_order'}
  3. REFUS run_sql         → Une seule instruction SQL est autorisée
  4. OK    run_sql         {'sql': 'SELECT ROUND(SUM(amount_untaxed), 2) ...'}

╭─ Réponse ────────────────────────────────────────────────────────────╮
│ Le chiffre d'affaires hors taxes commandé en 2024 s'élève à          │
│ 512 905,03 €, sur les commandes confirmées ou clôturées uniquement.  │
╰──────────────────────────────────────────────────────────────────────╯
```

L'étape 3 est volontaire : elle montre le garde-fou rejeter une requête à deux
instructions, et l'agent se corriger à l'étape suivante.

## Utilisation réelle

```bash
cp .env.example .env          # renseigner ANTHROPIC_API_KEY
python -m odoo_ai_agent ask "Quel client a généré le plus de chiffre d'affaires ?"
python -m odoo_ai_agent shell # session interactive
```

Contre une vraie base Odoo :

```bash
export DATABASE_URL="postgresql://lecteur:motdepasse@localhost:5432/odoo_prod"
pip install -e ".[postgres]"
```

> Créez un rôle PostgreSQL **en lecture seule** dédié. Les garde-fous applicatifs
> sont une commodité ; les droits SQL sont la seule vraie protection.

## Architecture

```
                      ┌──────────────────────────────┐
   question ────────▶ │  think  (LLM + outils)       │
                      └──────────┬───────────────────┘
                                 │ tool_use
                                 ▼
                      ┌──────────────────────────────┐
                      │  act                         │
                      │   ├─ list_tables             │
                      │   ├─ describe_table          │
                      │   ├─ run_sql ──▶ sql_guard ──┼──▶ SQLite / PostgreSQL
                      │   └─ search_docs ─▶ BM25     │      (lecture seule)
                      └──────────┬───────────────────┘
                                 │ tool_result
                                 └──────▶ retour à think
```

Graphe [LangGraph](https://langchain-ai.github.io/langgraph/) à deux nœuds, avec
arête conditionnelle. Détail des choix dans [`docs/architecture.md`](docs/architecture.md).

## Sécurité : trois couches, une seule inviolable

1. **`sql_guard.py`** — une seule instruction, `SELECT`/`WITH` uniquement, liste noire
   de mots-clés et de fonctions système, analyse des identifiants **hors littéraux**
   (une requête sur un client nommé « Delete Express » ne doit pas être bloquée).
2. **Bornage systématique** — `LIMIT` injecté ou ramené au plafond, `statement_timeout`.
3. **Moteur** — autorisateur SQLite refusant tout ce qui n'est pas une lecture ;
   sur PostgreSQL, transaction `READ ONLY` et rôle sans droit d'écriture.

Les deux premières couches servent à échouer tôt avec un message que l'agent peut
comprendre et corriger. La troisième est celle sur laquelle on s'engage.

## Évaluation

Un agent sans évaluation est une démonstration, pas un produit. Le harnais
(`evals/run_eval.py`) mesure trois choses distinctes :

- **exactitude** — la valeur citée est comparée à une vérité terrain calculée à
  l'exécution par une requête de référence ;
- **ancrage** — un chiffre juste obtenu sans appel à `run_sql` est compté comme un
  échec : c'est une coïncidence, pas un comportement fiable ;
- **refus** — sur une question hors périmètre (« le chiffre d'affaires du trimestre
  prochain »), l'agent doit refuser au lieu d'extrapoler.

```bash
python evals/run_eval.py --json metrics.json
```

Format de sortie :

```
[PASS] ca_2024                  ok
[PASS] nb_commandes_confirmees  ok
...
--- Métriques ---
Exactitude        : 8/8 (100%)
Réponses ancrées  : 7/8
Étapes moyennes   : 3.4
Latence moyenne   : 4.1 s
```

<!-- TODO : remplacer par les chiffres réellement obtenus, en précisant le modèle. -->

Les huit cas couvrent les pièges classiques d'Odoo : filtrage des états de commande,
distinction `move_type`, et `stock_location.usage` pour le stock réel.

## Tests

```bash
pytest -q          # 61 tests, aucun appel réseau
ruff check .
```

Les tests du graphe utilisent un `FakeLLM` qui rejoue un scénario écrit à la main.
Conséquence : la CI est verte, gratuite et déterministe, et l'on teste
l'orchestration plutôt que l'humeur du modèle.

## Choix techniques et leurs limites

**BM25 plutôt qu'une base vectorielle.** Le corpus tient en quatre documents et les
questions emploient le vocabulaire exact d'Odoo. Des embeddings n'apporteraient rien
ici, au prix d'une dépendance et d'un appel réseau supplémentaires. Ce choix
s'inverserait avec un corpus de plusieurs centaines de pages.

**Validation lexicale plutôt qu'un parseur SQL complet.** `sqlglot` donnerait une
analyse syntaxique exacte. La validation par mots présentée ici est plus simple à
lire et à auditer, et la couche 3 rattrape ce qu'elle laisserait passer. Sur un
périmètre plus large, le parseur deviendrait justifié.

**Client LLM maison plutôt que les wrappers LangChain.** L'agent manipule des blocs
de contenu bruts, ce qui rend `FakeLLM` trivial à écrire et les traces lisibles.
LangGraph n'est utilisé que pour ce qu'il fait bien : l'orchestration.

**Ce que ce dépôt ne fait pas :** pas de gestion multi-sociétés, pas de contrôle
d'accès par utilisateur Odoo, pas de cache. Un déploiement réel exigerait au
minimum le second point.

## Structure

```
src/odoo_ai_agent/
├── sql_guard.py   # validation défensive des requêtes
├── db.py          # accès lecture seule SQLite / PostgreSQL
├── retriever.py   # BM25 sur la base de connaissance
├── tools.py       # outils exposés au modèle
├── llm.py         # clients Anthropic / OpenAI / Fake
├── agent.py       # graphe LangGraph
└── cli.py
data/kb/           # règles de gestion Odoo (Markdown)
evals/             # jeu de questions + harnais de mesure
scripts/           # génération de la base de démo, démo hors ligne
tests/             # 61 tests
```

## Auteur

**Steve Christian FANTE** — Consultant ERP Odoo, Master MIAGE Management des SI.
Cinq déploiements Odoo Enterprise menés de bout en bout, 45 utilisateurs formés.

[LinkedIn](https://linkedin.com/in/steve-c-fante)

## Licence

MIT — voir [LICENSE](LICENSE).

