import json
import logging
from typing import List, Dict, Any
import chromadb
from chromadb.utils import embedding_functions
from app.config import settings

logger = logging.getLogger("hireflow.rag")

class RAGService:
    def __init__(self):
        self.db_path = settings.CHROMA_PERSIST_DIRECTORY
        self._client = None
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            try:
                self._client = chromadb.PersistentClient(path=self.db_path)
                emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=settings.EMBEDDING_MODEL_NAME
                )
                self._collection = self._client.get_or_create_collection(
                    name="hireflow_questions",
                    embedding_function=emb_fn
                )
            except Exception as e:
                logger.error(f"Failed to connect to ChromaDB: {str(e)}")
                raise e
        return self._collection

    def get_questions_for_role(self, role_name: str, skills: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Queries ChromaDB for interview questions relevant to the role and skills.
        Uses metadata filtering as primary, falling back to pure semantic search if not enough questions are found.
        """
        try:
            collection = self._get_collection()
            query_text = f"Interview questions for {role_name} covering skills like {', '.join(skills)}"
            
            logger.info(f"Querying questions for role: '{role_name}' with query: '{query_text}'")

            # 1. Attempt with metadata filter
            results = collection.query(
                query_texts=[query_text],
                n_results=limit,
                where={"role_name": role_name}
            )

            # Check if we got enough results. If not, do a generic query (fallback)
            ids = results.get("ids", [[]])[0]
            if len(ids) < limit:
                logger.info("Fewer results than requested; querying without metadata filter for semantic fallback.")
                fallback_results = collection.query(
                    query_texts=[query_text],
                    n_results=limit
                )
                # Combine results, prioritizing filtered ones
                seen_ids = set(ids)
                combined_metadatas = list(results.get("metadatas", [[]])[0])
                
                fallback_ids = fallback_results.get("ids", [[]])[0]
                fallback_metadatas = fallback_results.get("metadatas", [[]])[0]

                for fid, fmeta in zip(fallback_ids, fallback_metadatas):
                    if fid not in seen_ids and len(combined_metadatas) < limit:
                        combined_metadatas.append(fmeta)
                        seen_ids.add(fid)
                
                final_metadatas = combined_metadatas
            else:
                final_metadatas = results.get("metadatas", [[]])[0]

            # 2. Format output
            questions = []
            for meta in final_metadatas:
                try:
                    rubric_data = json.loads(meta.get("eval_rubric", "[]"))
                except Exception:
                    rubric_data = []

                questions.append({
                    "role_name": meta.get("role_name"),
                    "question_text": meta.get("question_text"),
                    "expected_answer": meta.get("expected_answer"),
                    "eval_rubric": rubric_data
                })
            
            return questions

        except Exception as e:
            logger.error(f"Error querying ChromaDB: {str(e)}")
            # Return empty list in case of errors
            return []

rag_service = RAGService()
