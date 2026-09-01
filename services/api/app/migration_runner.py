from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine


MIGRATION_LOCK_ID = 5_506_170_014_293_216_817


def _config() -> Config:
    repository_root = Path(__file__).resolve().parents[3]
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "services" / "api" / "migrations"))
    return config


def upgrade_database(engine: Engine) -> None:
    config = _config()
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": MIGRATION_LOCK_ID})
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def downgrade_database(engine: Engine, revision: str = "base") -> None:
    config = _config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, revision)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Paperlight database migrations through a live connection.")
    parser.add_argument("direction", choices=("upgrade", "downgrade"))
    parser.add_argument("revision", nargs="?", default=None)
    args = parser.parse_args()

    from .database import engine

    if args.direction == "upgrade":
        upgrade_database(engine)
    else:
        downgrade_database(engine, args.revision or "base")


if __name__ == "__main__":
    main()
