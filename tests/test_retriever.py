from __future__ import annotations

from odoo_ai_agent.retriever import BM25Retriever, Document, tokenize


def test_tokenize_retire_accents_et_mots_vides() -> None:
    assert tokenize("Le chiffre d'affaires généré") == ["chiffre", "affaires", "genere"]


def test_recherche_trouve_le_bon_document(retriever) -> None:  # noqa: ANN001
    hits = retriever.search("statuts possibles d'un bon de commande", top_k=1)
    assert hits
    assert "vente" in hits[0].document.doc_id


def test_recherche_stock(retriever) -> None:  # noqa: ANN001
    hits = retriever.search("emplacement interne quantité disponible", top_k=1)
    assert hits
    assert "stock" in hits[0].document.doc_id


def test_recherche_facturation(retriever) -> None:  # noqa: ANN001
    hits = retriever.search("move_type facture client payment_state", top_k=1)
    assert hits
    assert "comptabilite" in hits[0].document.doc_id


def test_requete_sans_correspondance() -> None:
    retriever = BM25Retriever([Document("a.md", "Titre", "contenu sur les stocks")])
    assert retriever.search("astrophysique quantique") == []


def test_scores_decroissants(retriever) -> None:  # noqa: ANN001
    hits = retriever.search("facture client état paiement", top_k=3)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
