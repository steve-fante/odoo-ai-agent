"""Recherche BM25 dans la base de connaissance fonctionnelle Odoo.

Pourquoi BM25 plutôt qu'une base vectorielle : le corpus tient en quelques
dizaines de documents, les questions utilisent le vocabulaire exact d'Odoo
(« bon de commande », « écriture comptable », `sale_order`), et BM25 se lit,
se teste et s'explique sans dépendance lourde ni appel réseau. Passer à des
embeddings n'aurait de sens qu'avec un corpus volumineux et un vocabulaire
utilisateur éloigné de celui de la documentation.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_TOKEN_RE = re.compile(r"[a-z0-9_]+")

_STOPWORDS = frozenset(
    """
    a au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me
    meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te
    tes toi ton tu un une vos votre vous c d j l m n s t y est sont etre avoir plus tres
    the of and to in for is are on
    """.split()  # noqa: SIM905 - plus lisible qu'une liste de 80 littéraux
)


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )


def tokenize(text: str) -> list[str]:
    normalised = _strip_accents(text.lower())
    return [t for t in _TOKEN_RE.findall(normalised) if t not in _STOPWORDS and len(t) > 1]


@dataclass
class Document:
    doc_id: str
    title: str
    text: str


@dataclass
class SearchHit:
    document: Document
    score: float


class BM25Retriever:
    """Implémentation BM25 Okapi, volontairement courte et testable."""

    def __init__(self, documents: list[Document], k1: float = 1.5, b: float = 0.75) -> None:
        if not documents:
            raise ValueError("La base de connaissance est vide.")
        self.documents = documents
        self.k1 = k1
        self.b = b
        self._tokens = [tokenize(f"{d.title}\n{d.text}") for d in documents]
        self._lengths = [len(t) for t in self._tokens]
        self._avg_len = sum(self._lengths) / len(self._lengths)
        self._freqs: list[dict[str, int]] = []
        doc_freq: dict[str, int] = {}
        for tokens in self._tokens:
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            self._freqs.append(counts)
            for token in counts:
                doc_freq[token] = doc_freq.get(token, 0) + 1
        n = len(documents)
        self._idf = {
            token: math.log(1 + (n - df + 0.5) / (df + 0.5)) for token, df in doc_freq.items()
        }

    def search(self, query: str, top_k: int = 3) -> list[SearchHit]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scored: list[SearchHit] = []
        for idx, doc in enumerate(self.documents):
            score = 0.0
            length = self._lengths[idx] or 1
            for token in query_tokens:
                freq = self._freqs[idx].get(token, 0)
                if freq == 0:
                    continue
                idf = self._idf.get(token, 0.0)
                denom = freq + self.k1 * (1 - self.b + self.b * length / self._avg_len)
                score += idf * freq * (self.k1 + 1) / denom
            if score > 0:
                scored.append(SearchHit(doc, round(score, 4)))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]


def load_documents(kb_path: Path) -> list[Document]:
    """Charge les fichiers Markdown du dossier de connaissance."""
    kb_path = Path(kb_path)
    if not kb_path.exists():
        raise FileNotFoundError(f"Base de connaissance introuvable : {kb_path}")
    documents: list[Document] = []
    for path in sorted(kb_path.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        first_line = raw.splitlines()[0] if raw.strip() else path.stem
        title = first_line.lstrip("# ").strip() or path.stem
        documents.append(Document(doc_id=path.name, title=title, text=raw))
    if not documents:
        raise FileNotFoundError(f"Aucun fichier .md dans {kb_path}")
    return documents


def build_retriever(kb_path: Path) -> BM25Retriever:
    return BM25Retriever(load_documents(kb_path))
