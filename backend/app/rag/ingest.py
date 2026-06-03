import os
import json
import logging
import chromadb
from chromadb.utils import embedding_functions
from app.config import settings

logger = logging.getLogger("hireflow.ingest")
logging.basicConfig(level=logging.INFO)

def run_ingestion():
    # 1. Paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    questions_file = os.path.join(current_dir, "..", "..", "data", "interview_questions.json")
    
    if not os.path.exists(questions_file):
        logger.error(f"Questions file not found at: {questions_file}")
        return

    logger.info(f"Loading questions from {questions_file}")
    with open(questions_file, "r", encoding="utf-8") as f:
        questions = json.load(f)

    # 2. ChromaDB setup
    db_path = settings.CHROMA_PERSIST_DIRECTORY
    logger.info(f"Connecting to ChromaDB at: {db_path}")
    client = chromadb.PersistentClient(path=db_path)

    # Embedding function
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.EMBEDDING_MODEL_NAME
    )

    # Get or create collection
    collection_name = "hireflow_questions"
    logger.info(f"Creating or getting collection '{collection_name}'")
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=emb_fn
    )

    # 3. Add documents
    documents = []
    metadatas = []
    ids = []

    for i, q in enumerate(questions):
        role_name = q.get("role_name", "")
        question_text = q.get("question_text", "")
        expected_answer = q.get("expected_answer", "")
        eval_rubric = q.get("eval_rubric", [])

        # The document text itself is the question text and role context
        doc_text = f"Role: {role_name}\nQuestion: {question_text}"
        
        documents.append(doc_text)
        metadatas.append({
            "role_name": role_name,
            "question_text": question_text,
            "expected_answer": expected_answer,
            "eval_rubric": json.dumps(eval_rubric)  # Chroma DB only supports primitive types for metadata
        })
        ids.append(f"q_{i}")

    logger.info(f"Upserting {len(documents)} questions into ChromaDB...")
    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    logger.info("Ingestion completed successfully!")

if __name__ == "__main__":
    run_ingestion()
