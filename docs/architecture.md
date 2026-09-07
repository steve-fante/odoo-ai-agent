# Architecture et décisions

Ce document explique **pourquoi** chaque pièce est là. Le code dit comment ;
il ne dit pas ce qui a été écarté, ni à quelles conditions il faudrait changer d'avis.

## Vue d'ensemble

```
              ┌───────────────────────────────────────────────┐
  question ──▶│ OdooAgent.ask()                               │
              │                                               │
              │   ┌─────────┐   tool_use    ┌─────────────┐   │
              │   │  think  │──────────────▶│     act     │   │
              │   │  (LLM)  │◀──────────────│  (Toolbox)  │   │
              │   └────┬────┘  tool_result  └──────┬──────┘   │
              │        │ texte seul                │          │
              └────────┼───────────────────────────┼──────────┘
                       ▼                           │
                  AgentAnswer                      ▼
                  · text                    ┌──────────────┐
                  · sql_executed            │  sql_guard   │
                  · tool_calls              └──────┬───────┘
                  · steps                          ▼
                                          ┌──────────────────┐
                                          │ SQLite/PostgreSQL│
                                          │  (lecture seule) │
                                          └──────────────────┘
```

## Le flux, étape par étape

1. `ask()` initialise l'état avec la question de l'utilisateur.
2. Le nœud `think` appelle le modèle avec le prompt système, l'historique et les
   quatre schémas d'outils.
3. L'arête conditionnelle `_route` regarde la dernière réponse :
   - elle contient au moins un bloc `tool_use` → aller vers `act` ;
   - elle ne contient que du texte, ou le plafond d'étapes est atteint → terminer.
4. Le nœud `act` exécute chaque appel via la `Toolbox`, capture les erreurs et
   renvoie les résultats sous forme de blocs `tool_result`.
5. Retour en `think` avec l'historique enrichi.

## Décisions

### Pourquoi LangGraph, et seulement pour l'orchestration

LangGraph apporte ce dont on a besoin : un graphe explicite, des arêtes
conditionnelles, une limite de récursion. En revanche l'agent n'utilise pas les
wrappers de modèles LangChain. Manipuler directement des blocs de contenu au
format Anthropic présente trois avantages :

- `FakeLLM` tient en vingt lignes, donc les tests couvrent le graphe entier ;
- changer de fournisseur revient à écrire un adaptateur, pas à réécrire l'agent ;
- les traces sont lisibles telles quelles lors du débogage.

### Pourquoi des outils atomiques plutôt qu'un seul outil « text-to-SQL »

Un unique outil qui recevrait la question et renverrait la réponse ferait porter
toute la difficulté sur un seul appel. En découpant en `list_tables`,
`describe_table`, `search_docs` et `run_sql`, le modèle construit son contexte
progressivement, et chaque étape est observable, testable et attribuable en cas
d'erreur.

### Pourquoi BM25 et non des embeddings

Le corpus fait quatre documents. Les questions emploient le vocabulaire exact
d'Odoo (`move_type`, `payment_state`, « bon de commande »). BM25 excelle sur la
correspondance lexicale exacte, ne demande aucun appel réseau, aucun index à
maintenir, et son score se lit et s'explique.

**Quand changer d'avis :** corpus de plusieurs centaines de pages, ou questions
utilisateur formulées dans un vocabulaire éloigné de la documentation. Le point
d'insertion serait `retriever.py`, dont l'interface (`search(query, top_k)`) ne
changerait pas.

### Pourquoi une validation lexicale plutôt qu'un parseur SQL

`sqlglot` fournirait un arbre syntaxique exact et éviterait les faux positifs.
Le choix retenu — analyse par mots, en ignorant le contenu des littéraux — se lit
en une page, s'audite en cinq minutes et n'ajoute aucune dépendance.

Ce choix n'est défendable **que parce que** la troisième couche existe :
l'autorisateur SQLite et le rôle PostgreSQL en lecture seule. Sans elle, il
faudrait un parseur.

**Le détail qui compte :** `_words_outside_strings` ignore le contenu des chaînes.
Sans cela, une requête légitime sur un client nommé « Delete Express » serait
rejetée. Ce genre de faux positif rend un agent inutilisable en production, et
c'est le test `test_mot_interdit_dans_un_litteral_est_tolere` qui le verrouille.

### Pourquoi le prompt impose de citer la requête

Trois bénéfices, pour une contrainte d'une ligne :

- l'utilisateur peut vérifier le raisonnement sans lire le code ;
- le consultant peut réutiliser la requête telle quelle ;
- l'évaluation peut distinguer une réponse ancrée d'une réponse inventée.

### Pourquoi l'évaluation mesure l'ancrage séparément de l'exactitude

Un modèle peut deviner « 160 commandes » parce que c'est un ordre de grandeur
plausible. La réponse serait comptée juste par une évaluation naïve, alors que le
comportement est précisément celui qu'on veut éliminer. `requires_sql` échoue le
cas dès qu'aucun `run_sql` n'a été exécuté, quel que soit le chiffre annoncé.

## Ce qui manquerait pour un déploiement réel

| Manque | Conséquence | Piste |
|---|---|---|
| Contrôle d'accès par utilisateur Odoo | Un utilisateur voit toutes les données | Filtre injecté sur `company_id` et règles `ir.rule` |
| Multi-sociétés | Chiffres agrégés à tort entre entités | Colonne `company_id` obligatoire dans le prompt et le garde-fou |
| Cache des schémas | Latence et coût de jetons inutiles | Mise en cache de `describe_table` par instance |
| Journalisation | Aucune traçabilité des questions posées | Écriture de `tool_calls` dans une table dédiée |
| Coût par requête | Non mesuré | Comptage des jetons dans `AgentAnswer` |

## Volumétrie de la base de démonstration

40 partenaires, 20 produits, 160 bons de commande sur 2024–2025, 413 lignes de
commande, une facture par commande confirmée, 24 quants de stock. Graine
aléatoire fixée à 42 : les chiffres sont reproductibles, condition nécessaire
pour que les évaluations comparent à une vérité terrain stable.
