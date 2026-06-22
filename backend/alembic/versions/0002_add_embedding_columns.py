"""Add embedding columns for pgvector RAG support

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-17

These columns exist on the KnowledgeBase and CandidateProfile SQLAlchemy
models (app/models/knowledge.py, app/models/candidate.py) but were never
added to the actual schema in 0001_initial_schema.py — that migration
created both tables before the embedding columns were added to the models.

Written with IF NOT EXISTS / IF EXISTS so it's safe to run even if the
columns were already added manually via the Supabase SQL editor.
"""
from typing import Sequence, Union
from alembic import op

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Belt-and-suspenders: 0001 already enables this, but a migration that
    # depends on pgvector should not assume something outside its own chain.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS embedding vector(384)")
    op.execute("ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS embedding vector(384)")


def downgrade() -> None:
    op.execute("ALTER TABLE candidate_profiles DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE knowledge_base DROP COLUMN IF EXISTS embedding")
