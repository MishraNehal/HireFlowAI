"""
Alembic environment for HireFlow AI.
Reads DATABASE_URL from .env via app.config and runs migrations
against the live Supabase PostgreSQL instance.
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

# ── Make app importable ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Load settings (reads .env automatically) ──────────────────────────────────
from app.config import settings

# ── Import every model so Alembic sees the full schema ────────────────────────
import app.models  # noqa: F401  (registers all tables with Base.metadata)
from app.database import Base

# ── Alembic config object ──────────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL script only)."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations directly against the DB.
    Uses settings.DATABASE_URL directly — bypasses alembic.ini placeholder.
    """
    connectable = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
