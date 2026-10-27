"""API requests and background jobs must not share a file DB transaction."""
import os
from pathlib import Path
import subprocess
import sys


def test_file_database_isolates_concurrent_session_transactions(tmp_path):
    script = '''
import asyncio
from sqlalchemy import text
from api.db.database import engine, SessionLocal

async def verify():
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE pool_probe (value INTEGER)"))
    async with SessionLocal() as writer, SessionLocal() as reader:
        await writer.execute(text("INSERT INTO pool_probe VALUES (1)"))
        assert (await reader.execute(text("SELECT count(*) FROM pool_probe"))).scalar_one() == 0
        await reader.rollback()
        await writer.commit()
    async with SessionLocal() as reader:
        assert (await reader.execute(text("SELECT count(*) FROM pool_probe"))).scalar_one() == 1
    await engine.dispose()

asyncio.run(verify())
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'sessions.db'}"},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
