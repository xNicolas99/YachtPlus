"""The release entrypoint runs Alembic before serving requests."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from api.db.database import Base, sync_migration_url
import api.db.models  # noqa: F401 - register all mapped tables


BACKEND_DIR = Path(__file__).resolve().parents[1]
HEAD = "20261001_0001"


@pytest.mark.parametrize(
    "source,expected_driver",
    [
        ("sqlite:///local.db", "sqlite"),
        ("sqlite+aiosqlite:///local.db", "sqlite"),
        ("postgresql://user:p%25ss@localhost/yacht", "postgresql+psycopg2"),
        ("postgresql+asyncpg://user:p%25ss@localhost/yacht", "postgresql+psycopg2"),
        ("mysql://user:p%25ss@localhost/yacht", "mysql+pymysql"),
        ("mysql+aiomysql://user:p%25ss@localhost/yacht", "mysql+pymysql"),
    ],
)
def test_migration_url_uses_available_sync_driver(source, expected_driver):
    url = make_url(sync_migration_url(source))
    assert url.drivername == expected_driver
    assert url.password == make_url(source).password
    engine = create_engine(url)
    try:
        assert engine.dialect.name == expected_driver.split("+")[0]
    finally:
        engine.dispose()


def _upgrade(database_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    env["FERNET_SALT_FILE"] = str(database_path.parent / ".fernet_salt")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _assert_upgraded(database_path: Path) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == HEAD
            assert "expires" in {column["name"] for column in inspect(conn).get_columns("apikeys")}
            assert "setup_status" in inspect(conn).get_table_names()
            assert "setup_registration_claim" in inspect(conn).get_table_names()
    finally:
        engine.dispose()


def test_upgrade_initializes_fresh_database_and_is_repeatable(tmp_path):
    database_path = tmp_path / "fresh.db"
    _upgrade(database_path)
    _assert_upgraded(database_path)
    _upgrade(database_path)
    _assert_upgraded(database_path)


def test_upgrade_existing_unversioned_database_without_apikey_expiry(tmp_path):
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(conn)
            conn.execute(text("ALTER TABLE apikeys DROP COLUMN expires"))
    finally:
        engine.dispose()

    _upgrade(database_path)
    _assert_upgraded(database_path)


def test_upgrade_versioned_database_adds_registration_claim(tmp_path):
    database_path = tmp_path / "versioned.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(conn)
            conn.execute(text("DROP TABLE setup_registration_claim"))
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(text("INSERT INTO alembic_version VALUES ('20260821_1348')"))
    finally:
        engine.dispose()

    _upgrade(database_path)
    _assert_upgraded(database_path)


def test_upgrade_resumes_partial_credentials_migration_and_encrypts_smtp(tmp_path):
    database_path = tmp_path / "partial.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(conn)
            from api.db.models.users import User
            conn.execute(User.__table__.insert().values(email="captain", hashed_password="hash", is_active=True, auth_version="old"))
            conn.execute(text("ALTER TABLE user DROP COLUMN auth_version"))
            conn.execute(text("ALTER TABLE user ADD COLUMN auth_version VARCHAR(64)"))
            conn.execute(text("INSERT INTO smtp_settings (server,port,sender_email,password) VALUES ('mail.example',587,'captain@example.com','old-plaintext-password')"))
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(text("INSERT INTO alembic_version VALUES ('20260929_0001')"))
        _upgrade(database_path)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT auth_version FROM user")).scalar()
            assert len(version) == 64
            assert not next(c for c in inspect(conn).get_columns("user") if c['name'] == 'auth_version')['nullable']
            password = conn.execute(text("SELECT password FROM smtp_settings")).scalar()
            assert password.startswith("v2:") and "old-plaintext-password" not in password
        _upgrade(database_path)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT auth_version FROM user")).scalar() == version
            assert conn.execute(text("SELECT password FROM smtp_settings")).scalar() == password
    finally:
        engine.dispose()


def test_upgrade_allows_missing_optional_smtp_table(tmp_path):
    database_path = tmp_path / "missing-smtp.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(conn)
            conn.execute(text("DROP TABLE smtp_settings"))
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(text("INSERT INTO alembic_version VALUES ('20260929_0001')"))
        _upgrade(database_path)
        _assert_upgraded(database_path)
    finally:
        engine.dispose()
