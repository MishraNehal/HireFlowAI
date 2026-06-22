"""
RAG API endpoints.

POST /api/v1/rag/bootstrap        -> seed synthetic data for the caller's company
POST /api/v1/rag/query            -> semantic search over the company's knowledge base
POST /api/v1/rag/ingest           -> add a single document to the knowledge base
GET  /api/v1/rag/knowledge-base   -> list documents (placeholder, unchanged from Milestone 1)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware import require_auth
from app.models.company import CompanyUser
from app.models.knowledge import KnowledgeDocType, KnowledgeSource
from app.services.rag import ingest_document, query_knowledge_base

logger = logging.getLogger("hireflow.rag")
router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


def _envelope(success: bool, message: str, data=None, error: str = None):
    return {
        "success": success,
        "message": message,
        "data": data,
        "error": error,
        "meta": {"timestamp": datetime.now(timezone.utc).isoformat()},
    }


class RagQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    role_tag: Optional[str] = None
    n_results: int = Field(5, ge=1, le=20)


class RagIngestRequest(BaseModel):
    doc_type: KnowledgeDocType
    content: str = Field(..., min_length=1)
    role_tag: Optional[str] = None


@router.post("/bootstrap")
def bootstrap_knowledge_base(
    auth: CompanyUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Seeds the caller's company with the synthetic JD/question/rubric/
    model-answer/policy data and colleges, if not already seeded.
    Safe to call repeatedly — seed_all() skips work that's already done."""
    # Imported lazily so a slow/optional import (sentence-transformers model
    # load, data file reads) only happens when this endpoint is actually hit,
    # not on every app startup.
    from data.seed import seed_all

    try:
        seed_all(db, company_id=auth.company_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Synthetic data files missing: {e}")
    except Exception as e:
        logger.exception("Bootstrap failed for company %s", auth.company_id)
        raise HTTPException(status_code=500, detail=f"Bootstrap failed: {e}")

    return _envelope(
        True,
        "Knowledge base bootstrap complete (no-op if already seeded)",
        data={"company_id": str(auth.company_id)},
    )


@router.post("/query")
def rag_query(
    body: RagQueryRequest,
    auth: CompanyUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Semantic search over the caller's company knowledge base."""
    try:
        results = query_knowledge_base(
            db,
            company_id=auth.company_id,
            query=body.query,
            role_tag=body.role_tag,
            n_results=body.n_results,
        )
    except Exception as e:
        logger.exception("RAG query failed for company %s", auth.company_id)
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return _envelope(
        True,
        f"Found {len(results)} result(s)",
        data={"results": results},
    )


@router.post("/ingest")
def ingest_single_document(
    body: RagIngestRequest,
    auth: CompanyUser = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Adds a single document to the caller's company knowledge base.
    Documents added through this endpoint are tagged source=real, since
    they're operator-provided rather than the bootstrapped synthetic set."""
    try:
        doc = ingest_document(
            db,
            company_id=auth.company_id,
            doc_type=body.doc_type,
            content=body.content,
            role_tag=body.role_tag,
            source=KnowledgeSource.real,
        )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("Ingest failed for company %s", auth.company_id)
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")

    return _envelope(
        True,
        "Document ingested",
        data={"id": str(doc.id), "doc_type": doc.doc_type.value, "role_tag": doc.role_tag},
    )


@router.get("/knowledge-base")
def list_knowledge_base(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Knowledge base — Milestone 2"}