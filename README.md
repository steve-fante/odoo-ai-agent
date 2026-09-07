# odoo-ai-agent

**Un agent IA qui rÃ©pond en franÃ§ais Ã  des questions mÃ©tier sur une base Odoo, sans jamais inventer un chiffre.**

[![CI](https://github.com/steve-fante/odoo-ai-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/steve-fante/odoo-ai-agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Licence](https://img.shields.io/badge/licence-MIT-green)

---

## Le problÃ¨me

Dans une PME Ã©quipÃ©e d'Odoo, la question Â« quel est mon encours client ? Â» suppose
de connaÃ®tre trois choses : que les factures vivent dans `account_move`, que
`move_type` doit valoir `out_invoice`, et que `payment_state` distingue `not_paid`
de `partial`. Le directeur financier ne les connaÃ®t pas. Il demande au consultant,
qui Ã©crit la requÃªte. Le dÃ©lai se compte en jours.

Brancher un LLM sur la base ne suffit pas : il produira des requÃªtes plausibles et
fausses, ou pire, des chiffres inventÃ©s sans avoir consultÃ© quoi que ce soit.

Ce dÃ©pÃ´t traite les trois problÃ¨mes rÃ©els de ce cas d'usage :

| ProblÃ¨me | RÃ©ponse apportÃ©e |
|---|---|
| Le modÃ¨le ignore les rÃ¨gles de gestion Odoo | Base de connaissance fonctionnelle interrogÃ©e par BM25 |
| Le modÃ¨le peut Ã©crire une requÃªte destructrice | Trois couches de garde-fous, dont un autorisateur SQLite |
| Le modÃ¨le peut inventer un chiffre | Ã‰valuation qui vÃ©rifie l'exactitude **et** l'ancrage sur une requÃªte rÃ©elle |

## DÃ©monstration en 30 secondes, sans clÃ© d'API

```bash
git clone https://github.com/steve-fante/odoo-ai-agent.git
cd odoo-ai-agent
pip install -e ".[dev]"
python scripts/demo_offline.py
```

```
â•­â”€ Question â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â•®
â”‚ Quel est le chiffre d'affaires hors taxes commandÃ© en 2024 ?         â”‚
â•°â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â•¯

Trace des outils
  1. OK    search_docs     {'query': "statuts sale_order chiffre d'affaires"}
  2. OK    describe_table  {'table': 'sale_order'}
  3. REFUS run_sql         â†’ Une seule instruction SQL est autorisÃ©e
  4. OK    run_sql         {'sql': 'SELECT ROUND(SUM(amount_untaxed), 2) ...'}

â•­â”€ RÃ©ponse â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â•®
â”‚ Le chiffre d'affaires hors taxes commandÃ© en 2024 s'Ã©lÃ¨ve Ã           â”‚
â”‚ 512 905,03 â‚¬, sur les commandes confirmÃ©es ou clÃ´turÃ©es uniquement.  â”‚
â•°â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â•¯
```

L'Ã©tape 3 est volontaire : elle montre le garde-fou rejeter une requÃªte Ã  deux
instructions, et l'agent se corriger Ã  l'Ã©tape suivante.

## Utilisation rÃ©elle

```bash
cp .env.example .env          # renseigner ANTHROPIC_API_KEY
python -m odoo_ai_agent ask "Quel client a gÃ©nÃ©rÃ© le plus de chiffre d'affaires ?"
python -m odoo_ai_agent shell # session interactive
```

Contre une vraie base Odoo :

```bash
export DATABASE_URL="postgresql://lecteur:motdepasse@localhost:5432/odoo_prod"
pip install -e ".[postgres]"
```

> CrÃ©ez un rÃ´le PostgreSQL **en lecture seule** dÃ©diÃ©. Les garde-fous applicatifs
> sont une commoditÃ© ; les droits SQL sont la seule vraie protection.

## Architecture

```
                      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
   question â”€â”€â”€â”€â”€â”€â”€â”€â–¶ â”‚  think  (LLM + outils)       â”‚
                      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                 â”‚ tool_use
                                 â–¼
                      â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
                      â”‚  act                         â”‚
                      â”‚   â”œâ”€ list_tables             â”‚
                      â”‚   â”œâ”€ describe_table          â”‚
                      â”‚   â”œâ”€ run_sql â”€â”€â–¶ sql_guard â”€â”€â”¼â”€â”€â–¶ SQLite / PostgreSQL
                      â”‚   â””â”€ search_docs â”€â–¶ BM25     â”‚      (lecture seule)
                      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                                 â”‚ tool_result
                                 â””â”€â”€â”€â”€â”€â”€â–¶ retour Ã  think
```

Graphe [LangGraph](https://langchain-ai.github.io/langgraph/) Ã  deux nÅ“uds, avec
arÃªte conditionnelle. DÃ©tail des choix dans [`docs/architecture.md`](docs/architecture.md).

## SÃ©curitÃ© : trois couches, une seule inviolable

1. **`sql_guard.py`** â€” une seule instruction, `SELECT`/`WITH` uniquement, liste noire
   de mots-clÃ©s et de fonctions systÃ¨me, analyse des identifiants **hors littÃ©raux**
   (une requÃªte sur un client nommÃ© Â« Delete Express Â» ne doit pas Ãªtre bloquÃ©e).
2. **Bornage systÃ©matique** â€” `LIMIT` injectÃ© ou ramenÃ© au plafond, `statement_timeout`.
3. **Moteur** â€” autorisateur SQLite refusant tout ce qui n'est pas une lecture ;
   sur PostgreSQL, transaction `READ ONLY` et rÃ´le sans droit d'Ã©criture.

Les deux premiÃ¨res couches servent Ã  Ã©chouer tÃ´t avec un message que l'agent peut
comprendre et corriger. La troisiÃ¨me est celle sur laquelle on s'engage.

## Ã‰valuation

Un agent sans Ã©valuation est une dÃ©monstration, pas un produit. Le harnais
(`evals/run_eval.py`) mesure trois choses distinctes :

- **exactitude** â€” la valeur citÃ©e est comparÃ©e Ã  une vÃ©ritÃ© terrain calculÃ©e Ã 
  l'exÃ©cution par une requÃªte de rÃ©fÃ©rence ;
- **ancrage** â€” un chiffre juste obtenu sans appel Ã  `run_sql` est comptÃ© comme un
  Ã©chec : c'est une coÃ¯ncidence, pas un comportement fiable ;
- **refus** â€” sur une question hors pÃ©rimÃ¨tre (Â« le chiffre d'affaires du trimestre
  prochain Â»), l'agent doit refuser au lieu d'extrapoler.

```bash
python evals/run_eval.py --json metrics.json
```

Format de sortie :

```
[PASS] ca_2024                  ok
[PASS] nb_commandes_confirmees  ok
...
--- MÃ©triques ---
Exactitude        : 8/8 (100%)
RÃ©ponses ancrÃ©es  : 7/8
Ã‰tapes moyennes   : 3.4
Latence moyenne   : 4.1 s
```

<!-- TODO : remplacer par les chiffres rÃ©ellement obtenus, en prÃ©cisant le modÃ¨le. -->

Les huit cas couvrent les piÃ¨ges classiques d'Odoo : filtrage des Ã©tats de commande,
distinction `move_type`, et `stock_location.usage` pour le stock rÃ©el.

## Tests

```bash
pytest -q          # 61 tests, aucun appel rÃ©seau
ruff check .
```

Les tests du graphe utilisent un `FakeLLM` qui rejoue un scÃ©nario Ã©crit Ã  la main.
ConsÃ©quence : la CI est verte, gratuite et dÃ©terministe, et l'on teste
l'orchestration plutÃ´t que l'humeur du modÃ¨le.

## Choix techniques et leurs limites

**BM25 plutÃ´t qu'une base vectorielle.** Le corpus tient en quatre documents et les
questions emploient le vocabulaire exact d'Odoo. Des embeddings n'apporteraient rien
ici, au prix d'une dÃ©pendance et d'un appel rÃ©seau supplÃ©mentaires. Ce choix
s'inverserait avec un corpus de plusieurs centaines de pages.

**Validation lexicale plutÃ´t qu'un parseur SQL complet.** `sqlglot` donnerait une
analyse syntaxique exacte. La validation par mots prÃ©sentÃ©e ici est plus simple Ã 
lire et Ã  auditer, et la couche 3 rattrape ce qu'elle laisserait passer. Sur un
pÃ©rimÃ¨tre plus large, le parseur deviendrait justifiÃ©.

**Client LLM maison plutÃ´t que les wrappers LangChain.** L'agent manipule des blocs
de contenu bruts, ce qui rend `FakeLLM` trivial Ã  Ã©crire et les traces lisibles.
LangGraph n'est utilisÃ© que pour ce qu'il fait bien : l'orchestration.

**Ce que ce dÃ©pÃ´t ne fait pas :** pas de gestion multi-sociÃ©tÃ©s, pas de contrÃ´le
d'accÃ¨s par utilisateur Odoo, pas de cache. Un dÃ©ploiement rÃ©el exigerait au
minimum le second point.

## Structure

```
src/odoo_ai_agent/
â”œâ”€â”€ sql_guard.py   # validation dÃ©fensive des requÃªtes
â”œâ”€â”€ db.py          # accÃ¨s lecture seule SQLite / PostgreSQL
â”œâ”€â”€ retriever.py   # BM25 sur la base de connaissance
â”œâ”€â”€ tools.py       # outils exposÃ©s au modÃ¨le
â”œâ”€â”€ llm.py         # clients Anthropic / OpenAI / Fake
â”œâ”€â”€ agent.py       # graphe LangGraph
â””â”€â”€ cli.py
data/kb/           # rÃ¨gles de gestion Odoo (Markdown)
evals/             # jeu de questions + harnais de mesure
scripts/           # gÃ©nÃ©ration de la base de dÃ©mo, dÃ©mo hors ligne
tests/             # 61 tests
```

## Auteur

**Steve Christian FANTE** â€” Consultant ERP Odoo, Master MIAGE Management des SI.
Cinq dÃ©ploiements Odoo Enterprise menÃ©s de bout en bout, 45 utilisateurs formÃ©s.

[LinkedIn](https://linkedin.com/in/steve-c-fante)

## Licence

MIT â€” voir [LICENSE](LICENSE).



