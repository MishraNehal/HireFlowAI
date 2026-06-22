"""
Seed script — loads backend/data/synthetic/*.json into the database.

Run directly: python data/seed.py
Or call seed_all(db, company_id=...) from elsewhere (e.g. the RAG bootstrap
API route in Task 2.6) to seed a specific company on demand.

What gets seeded where:
- colleges.json          -> colleges table (global, not company-scoped)
- jds.json               -> knowledge_base (doc_type=past_jd)
- interview_questions.json -> knowledge_base (doc_type=interview_question)
- rubric.json            -> knowledge_base (doc_type=rubric)
- model_answers.json     -> knowledge_base (doc_type=model_answer)
- hiring_policies.json   -> knowledge_base (doc_type=hiring_policy)
- candidates.json        -> NOT seeded here. It's sample candidate data for
  later testing of scoring/interview agents, and inserting it would require
  a real campaign_id that doesn't exist yet at this stage of the build.

Idempotent: re-running this script is safe. Colleges are matched by name
(only missing ones are inserted) and knowledge_base seeding is skipped
entirely if the target company already has any knowledge_base rows.
"""
import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.company import Company
from app.models.campaign import College, CollegeTier
from app.models.knowledge import KnowledgeBase, KnowledgeDocType, KnowledgeSource
from app.services.rag import embed_texts

DATA_DIR = Path(__file__).resolve().parent / "synthetic"

# Stable lookup key for the default demo company, so repeated runs without
# an explicit company_id always resolve to the same company instead of
# creating a new one every time.
DEMO_CLERK_ORG_ID = "demo-org-hireflow-seed"


def _load_json(filename: str):
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Expected synthetic data file at {path}, but it does not exist. "
            f"Did Task 2.2's JSON files get copied into backend/data/synthetic/?"
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_or_create_demo_company(db) -> Company:
    """Returns the existing demo company if one exists, otherwise creates it.
    Used when seed.py is run with no company_id argument."""
    company = db.query(Company).filter_by(clerk_org_id=DEMO_CLERK_ORG_ID).first()
    if company:
        return company

    company = Company(
        name="HireFlow Demo Company",
        industry="Technology",
        clerk_org_id=DEMO_CLERK_ORG_ID,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    print(f"Created demo company: {company.id}")
    return company


def seed_colleges(db) -> int:
    """Inserts any colleges from colleges.json not already present (matched
    by name). Returns the number of newly inserted colleges."""
    colleges_data = _load_json("colleges.json")

    existing_names = {name for (name,) in db.query(College.name).all()}
    new_colleges = [c for c in colleges_data if c["name"] not in existing_names]

    if not new_colleges:
        print(f"Colleges: 0 new (all {len(colleges_data)} already present)")
        return 0

    for c in new_colleges:
        db.add(College(
            name=c["name"],
            city=c.get("city"),
            state=c.get("state"),
            tier=CollegeTier(c["tier"]),
            placement_email=c.get("placement_email"),
            tpo_name=c.get("tpo_name"),
            tpo_contact=c.get("tpo_contact"),
            historical_rating=c.get("historical_rating"),
        ))
    db.commit()
    print(f"Colleges: inserted {len(new_colleges)} new (of {len(colleges_data)} total in file)")
    return len(new_colleges)


def _build_knowledge_documents() -> list:
    """Loads jds/questions/rubric/model_answers/hiring_policies and flattens
    them into a uniform list of {doc_type, role_tag, content} dicts ready
    for embedding and insertion."""
    docs = []

    for jd in _load_json("jds.json"):
        docs.append({
            "doc_type": KnowledgeDocType.past_jd,
            "role_tag": jd["role"],
            "content": jd["content"],
        })

    for q in _load_json("interview_questions.json"):
        content = (
            f"[{q['role']} - {q['topic']}, {q['difficulty']}] {q['question']}\n"
            f"Answer: {q['answer']}\n"
            f"Explanation: {q['explanation']}"
        )
        docs.append({
            "doc_type": KnowledgeDocType.interview_question,
            "role_tag": q["role"],
            "content": content,
        })

    rubric = _load_json("rubric.json")
    docs.append({
        "doc_type": KnowledgeDocType.rubric,
        "role_tag": None,  # rubric applies across all roles
        "content": rubric["content"],
    })

    for ma in _load_json("model_answers.json"):
        content = (
            f"[{ma['role']}] Model answer: {ma['model_answer']}\n"
            f"Key points: {', '.join(ma['key_points'])}"
        )
        docs.append({
            "doc_type": KnowledgeDocType.model_answer,
            "role_tag": ma["role"],
            "content": content,
        })

    for policy in _load_json("hiring_policies.json"):
        docs.append({
            "doc_type": KnowledgeDocType.hiring_policy,
            "role_tag": policy["role"],
            "content": policy["content"],
        })

    return docs


def seed_knowledge_base(db, company_id) -> int:
    """Embeds and inserts JD/question/rubric/model-answer/policy documents
    for company_id. Skips entirely if this company already has synthetic
    knowledge_base rows, so re-running seed.py doesn't create duplicates.

    Only counts source=synthetic rows (not source=real) so that a company
    which has manually ingested a real document via the /ingest API
    endpoint can still receive its synthetic baseline through bootstrap —
    otherwise a single real ingest would permanently block seeding.
    Returns the number of documents inserted."""
    existing_count = (
        db.query(KnowledgeBase)
        .filter_by(company_id=company_id, source=KnowledgeSource.synthetic)
        .count()
    )
    if existing_count > 0:
        print(f"Knowledge base: skipped (company already has {existing_count} synthetic documents)")
        return 0

    docs = _build_knowledge_documents()
    contents = [d["content"] for d in docs]

    print(f"Embedding {len(contents)} documents...")
    embeddings = embed_texts(contents)

    for doc, embedding in zip(docs, embeddings):
        db.add(KnowledgeBase(
            company_id=company_id,
            doc_type=doc["doc_type"],
            role_tag=doc["role_tag"],
            content=doc["content"],
            embedding=embedding,
            source=KnowledgeSource.synthetic,
        ))
    db.commit()
    print(f"Knowledge base: inserted {len(docs)} documents")
    return len(docs)


def seed_all(db, company_id=None) -> None:
    """Runs the full seed sequence. If company_id is not provided, seeds
    against (and creates if needed) a stable demo company."""
    if company_id is None:
        company = get_or_create_demo_company(db)
        company_id = company.id
    else:
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"No company found with id={company_id}")

    print(f"Seeding for company: {company.name} ({company_id})")
    print("-" * 60)

    n_colleges = seed_colleges(db)
    n_docs = seed_knowledge_base(db, company_id)

    print("-" * 60)
    print(f"Seeded {n_colleges} colleges and {n_docs} knowledge_base documents")
    print(f"Company ID used: {company_id}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()