"""
RAG (Retrieval-Augmented Generation) service.

Provides the two primitives every agent and API route needs to read/write the
company-scoped knowledge base:

- ingest_document(...): embed a piece of text and store it in knowledge_base.
- query_knowledge_base(...): embed a query and return the most semantically
  similar documents for a company, via pgvector cosine similarity.

Embeddings are generated locally with sentence-transformers — no API key or
network call is required at query time, only once to download model weights
the first time the process starts.
"""
from functools import lru_cache
from typing import Optional
from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.knowledge import KnowledgeBase, KnowledgeDocType, KnowledgeSource

# Must match KnowledgeBase.embedding = Vector(384) in app/models/knowledge.py.
# all-MiniLM-L6-v2 produces 384-dim vectors, so this is a sanity check, not a
# configurable value — changing the model requires a migration to resize the column.
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Loads the sentence-transformers model once per process and reuses it.
    The first call downloads model weights (~90MB for all-MiniLM-L6-v2);
    every call after that is served from this in-memory cache."""
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_text(text: str) -> list[float]:
    """Embed a single piece of text into a normalized 384-dim vector."""
    if not text or not text.strip():
        raise ValueError("text must be a non-empty string")

    embedder = get_embedder()
    vector = embedder.encode(text, normalize_embeddings=True)
    embedding = vector.tolist()

    if len(embedding) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding model '{settings.EMBEDDING_MODEL}' produced a "
            f"{len(embedding)}-dim vector, but knowledge_base.embedding expects "
            f"{EMBEDDING_DIM} dims. Did EMBEDDING_MODEL change without a migration?"
        )
    return embedding


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed multiple texts in one model call — much faster than calling
    embed_text() in a loop when seeding many documents at once (see data/seed.py)."""
    if not texts:
        return []

    embedder = get_embedder()
    vectors = embedder.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vectors]


def ingest_document(
    db: Session,
    company_id: UUID,
    doc_type: KnowledgeDocType,
    content: str,
    role_tag: Optional[str] = None,
    source: KnowledgeSource = KnowledgeSource.synthetic,
) -> KnowledgeBase:
    """Embed `content` and store it as a new row in knowledge_base.

    This function does NOT call db.commit() — it only flushes, so the caller
    (a route handler or seed.py) controls the transaction boundary and can
    batch many ingests into a single commit.
    """
    embedding = embed_text(content)

    doc = KnowledgeBase(
        company_id=company_id,
        doc_type=doc_type,
        role_tag=role_tag,
        content=content,
        embedding=embedding,
        source=source,
    )
    db.add(doc)
    db.flush()  # assigns doc.id and catches DB-level errors early, without committing
    return doc


def query_knowledge_base(
    db: Session,
    company_id: UUID,
    query: str,
    role_tag: Optional[str] = None,
    n_results: int = 5,
) -> list[dict]:
    """Embed `query` and return up to `n_results` of the most semantically
    similar documents for this company, optionally filtered to a role_tag.

    Returns a list of dicts (not ORM objects) so this can be serialized
    straight into an API response: id, doc_type, role_tag, content, source,
    similarity (0-1, higher = more similar).
    """
    n_results = max(1, n_results)
    query_embedding = embed_text(query)

    distance = KnowledgeBase.embedding.cosine_distance(query_embedding).label("distance")

    stmt = (
        select(KnowledgeBase, distance)
        .where(KnowledgeBase.company_id == company_id)
        .where(KnowledgeBase.embedding.isnot(None))
    )
    if role_tag:
        stmt = stmt.where(KnowledgeBase.role_tag == role_tag)

    stmt = stmt.order_by(distance).limit(n_results)

    rows = db.execute(stmt).all()

    results = []
    for doc, dist in rows:
        # pgvector cosine_distance ranges 0 (identical) to 2 (opposite) for
        # normalized vectors; convert to a 0-1 similarity score for consumers.
        similarity = round(1 - (dist / 2), 4)
        results.append({
            "id": str(doc.id),
            "doc_type": doc.doc_type.value,
            "role_tag": doc.role_tag,
            "content": doc.content,
            "source": doc.source.value,
            "similarity": similarity,
        })
    return results
