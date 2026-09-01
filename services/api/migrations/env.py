from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from services.api.app.database import Base
from services.api.app import models  # noqa: F401


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    raise RuntimeError("Paperlight migrations require a live database connection")


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is None:
        raise RuntimeError("Paperlight migrations must run through migration_runner.upgrade_database")
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
