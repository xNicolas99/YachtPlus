"""Archive safety, ownership, scheduling and authorization for volume backups."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
from types import SimpleNamespace
import tarfile
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import docker
from fastapi import HTTPException
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.db.models.backups import BackupSchedule, VolumeBackup
from api.db.models.operations import Operation
from api.db.models.users import User
from api.routers import backups as router
from api.services import backups


@pytest.fixture
def backup_settings(tmp_path, monkeypatch):
    values = SimpleNamespace(BACKUP_DIR=str(tmp_path / "archives"), BACKUP_MAX_BYTES=1024 * 1024,
                             BACKUP_HELPER_IMAGE="local-helper", DISABLE_AUTH=False)
    monkeypatch.setattr(backups, "get_settings", lambda: values)
    return values


def archive_bytes(entries=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        if entries is None:
            entries = [("data", tarfile.DIRTYPE, b""), ("data/settings.txt", tarfile.REGTYPE, b"example data")]
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.uid = 0
            info.gid = 0
            info.mode = 0o6755
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                info.linkname = "../../outside"
            info.size = len(payload) if kind == tarfile.REGTYPE else 0
            archive.addfile(info, io.BytesIO(payload) if kind == tarfile.REGTYPE else None)
    return output.getvalue()


def test_archive_rewrite_preserves_data_and_normalizes_ownership(backup_settings):
    output = io.BytesIO()
    assert backups.normalize_archive(io.BytesIO(archive_bytes()), output) == 2
    with tarfile.open(fileobj=output) as archive:
        assert archive.extractfile("data/settings.txt").read() == b"example data"
        for entry in archive:
            assert entry.uid == entry.gid == 1000
            assert not entry.mode & 0o6000


def test_restore_archive_is_relative_to_new_volume_root(backup_settings):
    output = io.BytesIO()
    backups.normalize_archive(io.BytesIO(archive_bytes()), output, strip_root=True)
    with tarfile.open(fileobj=output) as archive:
        assert archive.getnames() == [".", "settings.txt"]
        assert archive.extractfile("settings.txt").read() == b"example data"


@pytest.mark.parametrize("name", ["/etc/passwd", "data/../escape", "other/file", "data\\file", "../data/file"])
def test_archive_rejects_escaping_paths(backup_settings, name):
    with pytest.raises(ValueError, match="unsafe"):
        backups.normalize_archive(io.BytesIO(archive_bytes([(name, tarfile.REGTYPE, b"bad")])), io.BytesIO())


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE])
def test_archive_rejects_links_and_special_files(backup_settings, kind):
    with pytest.raises(ValueError, match="unsafe"):
        backups.normalize_archive(io.BytesIO(archive_bytes([("data/entry", kind, b"")])), io.BytesIO())


def test_archive_rejects_duplicate_paths(backup_settings):
    entries = [("data/file", tarfile.REGTYPE, b"one"), ("data/file", tarfile.REGTYPE, b"two")]
    with pytest.raises(ValueError, match="duplicate"):
        backups.normalize_archive(io.BytesIO(archive_bytes(entries)), io.BytesIO())


def test_archive_size_limit_is_enforced(backup_settings):
    backup_settings.BACKUP_MAX_BYTES = 10240
    payload = archive_bytes([("data/file", tarfile.REGTYPE, b"x" * 20000)])
    with pytest.raises(ValueError, match="size limit"):
        backups.normalize_archive(io.BytesIO(payload), io.BytesIO())


def test_archive_extended_metadata_is_bounded_before_parsing(backup_settings):
    info = tarfile.TarInfo("extended")
    info.type = tarfile.XHDTYPE
    info.size = 70000
    payload = info.tobuf() + b"x" * 70144
    with pytest.raises(ValueError, match="metadata"):
        backups.normalize_archive(io.BytesIO(payload), io.BytesIO())


def test_archive_directory_refuses_symlinks(backup_settings, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "archives").symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        with backups.archive_directory():
            pytest.fail("Symlink directory must not be opened")


def test_archive_read_refuses_symlink_file(backup_settings, tmp_path):
    archive_id = str(uuid4())
    private = tmp_path / "private"
    private.write_text("not an archive")
    root = tmp_path / "archives"
    root.mkdir()
    (root / (archive_id + ".tar")).symlink_to(private)
    with pytest.raises(OSError):
        with backups.open_archive(archive_id):
            pytest.fail("Symlink file must not be followed")


def client_context(monkeypatch, client):
    @contextmanager
    def factory():
        yield client
    monkeypatch.setattr(backups, "sync_docker_client", factory)


def test_backup_helper_is_never_started_and_source_is_read_only(backup_settings, monkeypatch):
    client = MagicMock()
    client.api.timeout = 60
    client.volumes.get.return_value.attrs = {"Driver": "local", "Options": None}
    client.images.get.return_value.attrs = {"Config": {}}
    client.containers.list.return_value = []
    helper = client.containers.create.return_value
    helper.get_archive.return_value = (iter([archive_bytes()]), {})
    client_context(monkeypatch, client)
    identifier = str(uuid4())

    result = backups.create_backup_sync(identifier, "app-data")

    helper.start.assert_not_called()
    helper.remove.assert_called_once_with(force=True, v=False)
    options = client.containers.create.call_args.kwargs
    assert options["user"] == "1000:1000"
    assert options["read_only"] is True
    assert options["network_mode"] == "none"
    assert options["cap_drop"] == ["ALL"]
    assert options["security_opt"] == ["no-new-privileges:true"]
    assert options["mounts"][0]["ReadOnly"] is True
    with backups.open_archive(identifier) as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == result["sha256"]
        assert result["size_bytes"] == stream.seek(0, 2)


@pytest.mark.parametrize("attrs", [
    {"Driver": "nfs"}, {"Driver": "local", "Options": {"device": "/"}},
])
def test_backup_refuses_custom_volume_drivers(backup_settings, attrs):
    client = MagicMock()
    client.volumes.get.return_value.attrs = attrs
    with pytest.raises(ValueError, match="ordinary local"):
        backups._validate_source(client, "app-data", True)


def test_backup_refuses_infrastructure_volume_even_when_confirmed(backup_settings):
    client = MagicMock()
    client.volumes.get.return_value.attrs = {"Driver": "local"}
    container = SimpleNamespace(name="yacht", attrs={"Config": {"Labels": {"local.yachtplus.infrastructure": "app"}}, "Mounts": [{"Type": "volume", "Name": "app-data", "Destination": "/data"}]})
    client.containers.list.return_value = [container]
    with pytest.raises(ValueError, match="Infrastructure"):
        backups._validate_source(client, "app-data", True)


@pytest.mark.parametrize("container_id,labels,destination,allowed", [
    ("a" * 64, {}, "/config", True),
    ("f" * 64, {}, "/config", False),
    ("a" * 64, {"local.yachtplus.infrastructure": "app"}, "/config", False),
    ("a" * 64, {}, "/run/yachtplus-security", False),
    ("a" * 64, {}, "/var/lib/docker", False),
    ("a" * 64, {}, "/var/run", False),
])
def test_inventory_and_backup_policy_distinguish_application_config_from_infrastructure(
    backup_settings, monkeypatch, container_id, labels, destination, allowed,
):
    monkeypatch.setenv("HOSTNAME", "f" * 12)
    client = MagicMock()
    volume = SimpleNamespace(name="app-data", attrs={"Driver": "local", "Options": None})
    client.volumes.list.return_value = [volume]
    client.volumes.get.return_value = volume
    container = SimpleNamespace(name="application", attrs={
        "Id": container_id, "Config": {"Labels": labels}, "State": {"Running": False},
        "Mounts": [{"Type": "volume", "Name": "app-data", "Destination": destination}],
    })
    client.containers.list.return_value = [container]
    client_context(monkeypatch, client)

    assert backups.volume_inventory_sync()[0]["allowed"] is allowed
    if allowed:
        backups._validate_source(client, "app-data", False)
    else:
        with pytest.raises(ValueError, match="Infrastructure"):
            backups._validate_source(client, "app-data", True)


def test_backup_requires_explicit_live_confirmation(backup_settings):
    client = MagicMock()
    client.volumes.get.return_value.attrs = {"Driver": "local"}
    container = SimpleNamespace(name="app", attrs={"Config": {"Labels": {}}, "State": {"Running": True}, "Mounts": [{"Type": "volume", "Name": "app-data", "Destination": "/data"}]})
    client.containers.list.return_value = [container]
    with pytest.raises(ValueError, match="in use"):
        backups._validate_source(client, "app-data", False)
    backups._validate_source(client, "app-data", True)


def write_test_archive(backup_settings):
    identifier = str(uuid4())
    from pathlib import Path
    root = Path(backup_settings.BACKUP_DIR)
    root.mkdir(exist_ok=True)
    payload = archive_bytes()
    (root / (identifier + ".tar")).write_bytes(payload)
    return identifier, hashlib.sha256(payload).hexdigest()


def test_restore_rejects_changed_archive_before_creating_any_volume(backup_settings, monkeypatch):
    identifier, _ = write_test_archive(backup_settings)
    factory = MagicMock()
    monkeypatch.setattr(backups, "sync_docker_client", factory)
    with pytest.raises(ValueError, match="checksum"):
        backups.restore_backup_sync(identifier, "0" * 64, "new-data")
    factory.assert_not_called()


def test_restore_never_overwrites_existing_volume(backup_settings, monkeypatch):
    identifier, digest = write_test_archive(backup_settings)
    client = MagicMock()
    client.api.timeout = 60
    client_context(monkeypatch, client)
    with pytest.raises(ValueError, match="already exists"):
        backups.restore_backup_sync(identifier, digest, "existing")
    client.volumes.create.assert_not_called()
    client.containers.create.assert_not_called()


def test_restore_does_not_delete_a_volume_created_by_another_request(backup_settings, monkeypatch):
    identifier, digest = write_test_archive(backup_settings)
    client = MagicMock()
    client.api.timeout = 60
    client.volumes.get.side_effect = docker.errors.NotFound("missing")
    volume = client.volumes.create.return_value
    volume.attrs = {"Labels": {"local.yachtplus.restore.transaction": "some-other-request"}}
    client_context(monkeypatch, client)
    with pytest.raises(ValueError, match="another operation"):
        backups.restore_backup_sync(identifier, digest, "racing-volume")
    volume.remove.assert_not_called()
    client.containers.create.assert_not_called()


class MockAuth:
    def __init__(self, username="admin", api_key=False):
        self.username = username
        self.api_key = api_key

    async def jwt_required(self, **kwargs):
        return True

    async def get_jwt_subject(self):
        return self.username

    def is_api_key(self):
        return self.api_key


@pytest.mark.asyncio
async def test_backup_admin_gate_rejects_regular_users_and_api_keys(db, monkeypatch):
    monkeypatch.setattr("api.auth.auth.get_settings", lambda: SimpleNamespace(DISABLE_AUTH=False))
    db.add_all([User(username="operator", hashed_password="unused", is_active=True, is_superuser=False), User(username="admin", hashed_password="unused", is_active=True, is_superuser=True)])
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await router._administrator(MockAuth("operator"), db)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await router._administrator(MockAuth(api_key=True), db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_daily_schedule_runs_once_per_due_utc_day(db, backup_settings, monkeypatch):
    actor = User(username="admin", hashed_password="unused", is_active=True, is_superuser=True)
    db.add(actor)
    await db.commit()
    policy = BackupSchedule(volume="data", enabled=True, hour_utc=2, minute_utc=30, retain_count=7,
                            created_by=actor.username, created_by_id=actor.id, created_by_version=actor.auth_version)
    db.add(policy)
    await db.commit()
    monkeypatch.setattr(backups, "SessionLocal", async_sessionmaker(bind=db.bind, expire_on_commit=False))
    queued = []

    async def queue(session, **kwargs):
        row = VolumeBackup(volume="data", status="completed", created_by="admin", operation_id="operation")
        session.add(row)
        await session.commit()
        queued.append(row)
        return row

    monkeypatch.setattr(backups, "queue_backup", queue)
    monkeypatch.setattr("api.services.operations.wait_for_operation", AsyncMock())
    await backups.run_due_backups(datetime(2026, 10, 27, 2, 29, tzinfo=timezone.utc))
    assert not queued
    await backups.run_due_backups(datetime(2026, 10, 27, 2, 30, tzinfo=timezone.utc))
    await backups.run_due_backups(datetime(2026, 10, 27, 4, 30, tzinfo=timezone.utc))
    assert len(queued) == 1
    await backups.run_due_backups(datetime(2026, 10, 28, 2, 30, tzinfo=timezone.utc))
    assert len(queued) == 2


@pytest.mark.asyncio
async def test_schedule_does_not_transfer_to_recreated_administrator(db, backup_settings, monkeypatch):
    actor = User(username="admin", hashed_password="unused", is_active=True, is_superuser=True)
    db.add(actor)
    await db.commit()
    policy = BackupSchedule(volume="data", enabled=True, hour_utc=0, created_by="admin",
                            created_by_id=actor.id + 1, created_by_version=actor.auth_version)
    db.add(policy)
    await db.commit()
    monkeypatch.setattr(backups, "SessionLocal", async_sessionmaker(bind=db.bind, expire_on_commit=False))
    queue = AsyncMock()
    monkeypatch.setattr(backups, "queue_backup", queue)
    await backups.run_due_backups(datetime(2026, 10, 27, 3, tzinfo=timezone.utc))
    queue.assert_not_awaited()
    await db.refresh(policy)
    assert policy.enabled is False
    assert "authorization changed" in policy.last_error


@pytest.mark.asyncio
async def test_schedule_does_not_survive_changed_credentials(db, backup_settings, monkeypatch):
    actor = User(username="admin", hashed_password="unused", is_active=True, is_superuser=True)
    db.add(actor)
    await db.commit()
    policy = BackupSchedule(volume="data", enabled=True, hour_utc=0, created_by="admin",
                            created_by_id=actor.id, created_by_version="old-credentials")
    db.add(policy)
    await db.commit()
    monkeypatch.setattr(backups, "SessionLocal", async_sessionmaker(bind=db.bind, expire_on_commit=False))
    queue = AsyncMock()
    monkeypatch.setattr(backups, "queue_backup", queue)
    await backups.run_due_backups(datetime(2026, 10, 27, 3, tzinfo=timezone.utc))
    queue.assert_not_awaited()
    await db.refresh(policy)
    assert policy.enabled is False


@pytest.mark.asyncio
async def test_retention_preserves_archives_with_pending_restoration(db, backup_settings, monkeypatch):
    actor = User(username="admin", hashed_password="unused", is_active=True, is_superuser=True)
    db.add(actor)
    await db.commit()
    policy = BackupSchedule(volume="data", enabled=True, retain_count=1, created_by="admin",
                            created_by_id=actor.id, created_by_version=actor.auth_version)
    old = VolumeBackup(id=str(uuid4()), volume="data", status="completed", created_by="admin",
                       created_at=datetime(2026, 10, 26, tzinfo=timezone.utc))
    new = VolumeBackup(volume="data", status="completed", created_by="admin",
                       created_at=datetime(2026, 10, 27, tzinfo=timezone.utc))
    db.add_all([policy, old, new])
    db.add(Operation(kind="volume.restore", resource="restored-data", action=old.id.replace("-", ""),
                     actor="admin", actor_id=actor.id, actor_instance=actor.account_instance, worker_id="worker", heartbeat_at=datetime.now(timezone.utc),
                     status="queued", phase="Queued"))
    await db.commit()
    monkeypatch.setattr(backups, "SessionLocal", async_sessionmaker(bind=db.bind, expire_on_commit=False))
    removed = MagicMock()
    monkeypatch.setattr(backups, "delete_archive", removed)
    await backups._apply_retention("data", policy.id, actor)
    removed.assert_not_called()
    assert len((await db.execute(select(VolumeBackup))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_restart_repairs_only_proven_interrupted_backups(db, backup_settings, monkeypatch):
    now = datetime.now(timezone.utc)
    dead = Operation(id=str(uuid4()), kind="volume.backup", resource="data", actor="admin", actor_id=1,
                     actor_instance=str(uuid4()), worker_id="dead", heartbeat_at=now, status="interrupted", phase="Interrupted")
    live = Operation(id=str(uuid4()), kind="volume.backup", resource="live", actor="admin", actor_id=1,
                     actor_instance=str(uuid4()), worker_id="live", heartbeat_at=now, status="running", phase="Reading archive")
    db.add_all([dead, live])
    db.add_all([VolumeBackup(volume="data", status="running", created_by="admin", operation_id=dead.id),
                VolumeBackup(volume="live", status="running", created_by="admin", operation_id=live.id)])
    await db.commit()
    monkeypatch.setattr(backups, "SessionLocal", async_sessionmaker(bind=db.bind, expire_on_commit=False))
    await backups.recover_backups()
    rows = {row.volume: row for row in (await db.execute(select(VolumeBackup))).scalars()}
    assert rows["data"].status == "failed"
    assert "interrupted" in rows["data"].error
    assert rows["live"].status == "running"


@pytest.mark.asyncio
async def test_backup_metadata_and_operation_link_share_one_commit(db, backup_settings, monkeypatch):
    actor = User(username="admin", hashed_password="unused", is_active=True, is_superuser=True)
    db.add(actor)
    await db.commit()
    operation_id = str(uuid4())

    async def submit(session, **kwargs):
        pending = [row for row in session.new if isinstance(row, VolumeBackup)]
        assert len(pending) == 1
        assert pending[0].operation_id is None
        operation = SimpleNamespace(id=operation_id)
        kwargs["before_commit"](operation)
        await session.commit()
        return operation

    monkeypatch.setattr("api.services.operations.submit_operation", submit)
    result = await backups.queue_backup(db, volume="data", actor=actor)
    assert result.operation_id == operation_id
    assert (await db.execute(select(VolumeBackup.operation_id))).scalar_one() == operation_id


@pytest.mark.asyncio
async def test_queue_failure_does_not_leave_unlinked_backup(db, backup_settings, monkeypatch):
    actor = User(username="admin", hashed_password="unused", is_active=True, is_superuser=True)
    db.add(actor)
    await db.commit()

    async def submit(session, **kwargs):
        await session.flush()
        raise HTTPException(429, "Queue full")

    monkeypatch.setattr("api.services.operations.submit_operation", submit)
    with pytest.raises(HTTPException) as exc:
        await backups.queue_backup(db, volume="data", actor=actor)
    assert exc.value.status_code == 429
    assert not (await db.execute(select(VolumeBackup))).scalars().all()


@pytest.mark.asyncio
async def test_one_enqueue_rollback_does_not_stop_other_schedules(db, backup_settings, monkeypatch):
    actor = User(username="admin", hashed_password="unused", is_active=True, is_superuser=True)
    db.add(actor)
    await db.commit()
    for volume in ("first", "second"):
        db.add(BackupSchedule(volume=volume, enabled=True, hour_utc=0, created_by="admin",
                              created_by_id=actor.id, created_by_version=actor.auth_version))
    await db.commit()
    monkeypatch.setattr(backups, "SessionLocal", async_sessionmaker(bind=db.bind, expire_on_commit=False))
    accepted = []

    async def enqueue(session, **kwargs):
        if kwargs["volume"] == "first":
            await session.rollback()
            raise HTTPException(429, "Queue full")
        accepted.append(kwargs["volume"])
        return SimpleNamespace(id="accepted")

    monkeypatch.setattr(backups, "queue_backup", enqueue)
    await backups.run_due_backups(datetime(2026, 10, 27, 3, tzinfo=timezone.utc))
    assert accepted == ["second"]
    rows = {row.volume: row for row in (await db.execute(select(BackupSchedule))).scalars()}
    assert "Scheduled backup failed" in rows["first"].last_error
