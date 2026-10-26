"""Alembic environment: raw-SQL migrations, connecting through psycopg 3."""

from alembic import context
from sqlalchemy import create_engine, pool

from unicode.config import get_settings

config = context.config


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url") or get_settings().migrations_database_url
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, transaction_per_migration=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
