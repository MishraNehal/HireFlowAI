"""Widen file_url columns to match model definitions

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-17

Same drift story as 0002: resumes.file_url and onboarding_documents.file_url
are declared as String(2048) on the SQLAlchemy models (app/models/candidate.py,
app/models/offer.py), but 0001_initial_schema.py created both as
varchar(500) — that migration predates the models being widened.

This surfaced as a live bug: Supabase Storage signed URLs carry a JWT
token + expiry + signature as query params and routinely exceed 500
characters, so every resume upload failed with
psycopg2.errors.StringDataRightTruncation on INSERT.

Using ALTER COLUMN TYPE directly (not IF NOT EXISTS, since these are
existing columns being widened, not new ones) — widening a varchar is a
safe, non-destructive operation in Postgres.
"""
from typing import Sequence, Union
from alembic import op

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE resumes ALTER COLUMN file_url TYPE varchar(2048)")
    op.execute("ALTER TABLE onboarding_documents ALTER COLUMN file_url TYPE varchar(2048)")


def downgrade() -> None:
    # Not a true reverse — truncates any URL over 500 chars if downgraded
    # after real signed URLs have been stored. Documented here rather than
    # silently corrupting data on a downgrade nobody should actually run.
    op.execute("ALTER TABLE resumes ALTER COLUMN file_url TYPE varchar(500)")
    op.execute("ALTER TABLE onboarding_documents ALTER COLUMN file_url TYPE varchar(500)")
