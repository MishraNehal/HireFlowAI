from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.middleware import require_auth

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


@router.post("/query")
def rag_query(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": {"answer": "", "sources": []}, "message": "RAG query — Milestone 2"}


@router.post("/ingest")
def ingest_document(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "message": "Document ingested — Milestone 2"}


@router.get("/knowledge-base")
def list_knowledge_base(auth=Depends(require_auth), db: Session = Depends(get_db)):
    return {"success": True, "data": [], "message": "Knowledge base — Milestone 2"}
