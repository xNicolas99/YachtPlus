from os.path import abspath, dirname
import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, MetaData
from sqlalchemy import pool
from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

sys.path.insert(0, dirname(dirname(abspath(__file__))))

# Import Base first, then every model module so their tables are registered
# in Base.metadata. Importing the package (`api.db.models`) does not register
# the concrete tables, which broke autogenerate.
from api.db.database import Base
from api.db.models import containers, users  # noqa: F401
from api.db.models.settings import TokenBlacklist  # noqa: F401

print("--- MODELS ---")
target_metadata = Base.metadata
config.set_main_option(
    "sqlalchemy.url", os.environ.get("DATABASE_URL", "sqlite:///config/data.sqlite")
)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _ensure_schema(connection) -> None:
    """Create the initial schema on a fresh database before alembic runs.

    YachtPlus historically relied on `Base.metadata.create_all()` at startup
    rather than a baseline migration. Existing migrations only add/alter
    columns. Without this guard, `alembic upgrade head` fails on a new
    database because the first migration references tables that do not yet
    exist.
    """
    from sqlalchemy import inspect

    inspector = inspect(connection)
    tables = inspector.get_table_names()
    if not tables or "alembic_version" not in tables:
        Base.metadata.create_all(connection)


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _ensure_schema(connection)
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
