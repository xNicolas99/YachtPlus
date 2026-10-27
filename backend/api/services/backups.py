"""Bounded Docker volume archives; no host mounts or local tar extraction.

The helper is never started. Docker's archive API reads a read-only volume mount
and writes only a newly created, empty volume. Archive paths, types, ownership
and sizes are checked before Docker receives a restore stream.
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import time
from uuid import UUID, uuid4

import docker
from fastapi import HTTPException
from sqlalchemy import select, update

from api.db.database import SessionLocal
from api.db.models.backups import BackupSchedule, VolumeBackup
from api.db.models.operations import Operation
from api.db.models.users import User
from api.settings import get_settings
from api.utils.docker_client import sync_docker_client

logger = logging.getLogger(__name__)
MAX_MEMBERS = 100000
MAX_SECONDS = 600
VOLUME_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")


def validate_volume_name(value):
    if not isinstance(value, str) or not VOLUME_NAME.fullmatch(value):
        raise HTTPException(422, "Invalid volume name")
    return value


def canonical_id(value):
    try:
        result = str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, "Backup not found") from None
    if value != result:
        raise HTTPException(404, "Backup not found")
    return result


@contextmanager
def archive_directory():
    """Open a private, symlink-free archive directory using a directory fd."""
    path = Path(get_settings().BACKUP_DIR).absolute()
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise ValueError("Backup directory must not contain symlinks")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ValueError("Invalid backup directory")
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def open_archive(backup_id):
    name = canonical_id(backup_id) + ".tar"
    with archive_directory() as directory:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > get_settings().BACKUP_MAX_BYTES:
                raise ValueError("Invalid backup archive")
            yield stream


@contextmanager
def staging_file():
    """Stage on backup storage, never the image's small /tmp tmpfs."""
    with archive_directory() as directory:
        name = ".stage-" + uuid4().hex + ".tmp"
        descriptor = os.open(name, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=directory)
        # Keep an open anonymous file: process exit also reclaims a partial stream.
        os.unlink(name, dir_fd=directory)
        with os.fdopen(descriptor, "w+b") as stream:
            yield stream


def delete_archive(backup_id):
    with archive_directory() as directory:
        try:
            os.unlink(canonical_id(backup_id) + ".tar", dir_fd=directory)
        except FileNotFoundError:
            pass


def _check_deadline(deadline):
    if time.monotonic() > deadline:
        raise ValueError("Backup operation timed out")


def _check_tar_headers(source, deadline):
    """Bound extended metadata before tarfile allocates/parses its payload."""
    original = source.tell()
    length = source.seek(0, os.SEEK_END)
    source.seek(original)
    headers = 0
    try:
        while True:
            _check_deadline(deadline)
            block = source.read(tarfile.BLOCKSIZE)
            if not block or block == b"\0" * tarfile.BLOCKSIZE:
                break
            if len(block) != tarfile.BLOCKSIZE:
                raise ValueError("Archive has an incomplete header")
            info = tarfile.TarInfo.frombuf(block, encoding="utf-8", errors="surrogateescape")
            headers += 1
            if headers > MAX_MEMBERS * 2 or info.size < 0:
                raise ValueError("Archive contains too many entries")
            if info.type in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK) and info.size > 65536:
                raise ValueError("Archive metadata exceeds the size limit")
            skip = ((info.size + tarfile.BLOCKSIZE - 1) // tarfile.BLOCKSIZE) * tarfile.BLOCKSIZE
            if source.tell() + skip > length:
                raise ValueError("Archive data is truncated")
            source.seek(skip, os.SEEK_CUR)
    finally:
        source.seek(original)


def normalize_archive(source, destination, *, deadline=None, strip_root=False):
    """Validate and rewrite a tar stream without extracting it on this host."""
    deadline = deadline or time.monotonic() + MAX_SECONDS
    _check_tar_headers(source, deadline)
    limit = get_settings().BACKUP_MAX_BYTES
    total = count = 0
    seen = set()
    with tarfile.open(fileobj=source, mode="r|", errorlevel=2) as incoming:
        with tarfile.open(fileobj=destination, mode="w|", format=tarfile.PAX_FORMAT) as outgoing:
            for member in incoming:
                _check_deadline(deadline)
                count += 1
                raw = member.name
                parts = PurePosixPath(raw).parts
                if (
                    count > MAX_MEMBERS or len(raw) > 4096 or "\\" in raw or "\x00" in raw
                    or raw.startswith("/") or ".." in parts or not parts or parts[0] != "data"
                    or not (member.isfile() or member.isdir()) or member.size < 0
                    or (len(parts) == 1 and not member.isdir())
                ):
                    raise ValueError("Archive contains an unsafe path or unsupported entry")
                name = "/".join(parts)
                if name in seen:
                    raise ValueError("Archive contains duplicate paths")
                seen.add(name)
                total += member.size
                if total > limit:
                    raise ValueError("Backup exceeds the configured size limit")
                clean_name = ("/".join(parts[1:]) or ".") if strip_root else name
                clean = tarfile.TarInfo(clean_name)
                clean.type = tarfile.DIRTYPE if member.isdir() else tarfile.REGTYPE
                clean.size = 0 if member.isdir() else member.size
                clean.mode = member.mode & 0o777
                clean.uid = clean.gid = 1000
                clean.mtime = max(0, member.mtime)
                fileobj = incoming.extractfile(member) if member.isfile() else None
                try:
                    outgoing.addfile(clean, fileobj)
                finally:
                    if fileobj:
                        fileobj.close()
                if destination.tell() > limit:
                    raise ValueError("Backup exceeds the configured size limit")
    if not count:
        raise ValueError("Archive is empty or malformed")
    if destination.tell() > limit:
        raise ValueError("Backup exceeds the configured size limit")
    destination.seek(0)
    return count


def _helper_image(client):
    def checked(reference):
        image = client.images.get(reference)
        if (image.attrs.get("Config") or {}).get("Volumes"):
            raise ValueError("Backup helper image must not declare additional volumes")
        return image.id

    configured = get_settings().BACKUP_HELPER_IMAGE
    if configured:
        return checked(configured)
    current = os.environ.get("HOSTNAME")
    if current:
        try:
            return checked(client.containers.get(current).attrs["Image"])
        except docker.errors.NotFound:
            pass
    apps = client.containers.list(all=True, filters={"label": "local.yachtplus.infrastructure=app"})
    if len(apps) == 1:
        return checked(apps[0].attrs["Image"])
    raise ValueError("Configure BACKUP_HELPER_IMAGE with an existing local image for backups")


def _protected_container(attrs):
    role = (attrs.get("Config", {}).get("Labels") or {}).get("local.yachtplus.infrastructure")
    current = os.environ.get("HOSTNAME", "")
    container_id = attrs.get("Id", "")
    return bool(role or (current and container_id and current in {container_id, container_id[:12]}))


def volume_inventory_sync():
    with sync_docker_client() as client:
        containers = client.containers.list(all=True)
        result = []
        for volume in client.volumes.list():
            name = volume.name
            attrs = volume.attrs
            attached = []
            blocked = bool(attrs.get("Driver") not in (None, "local") or attrs.get("Options"))
            for container in containers:
                details = container.attrs
                mounts = [mount for mount in details.get("Mounts", []) if mount.get("Type") == "volume" and mount.get("Name") == name]
                if not mounts:
                    continue
                if _protected_container(details) or any(mount.get("Destination") in {"/run/yachtplus-security", "/var/lib/docker", "/var/run"} for mount in mounts):
                    blocked = True
                if details.get("State", {}).get("Running"):
                    attached.append(container.name)
            result.append({"name": name, "allowed": not blocked, "running_containers": attached,
                           "reason": "Infrastructure volumes and custom volume drivers/options are excluded" if blocked else None})
        return result


def _validate_source(client, volume, confirm_live):
    validate_volume_name(volume)
    details = client.volumes.get(volume).attrs
    if details.get("Driver") not in (None, "local") or details.get("Options"):
        raise ValueError("Only ordinary local Docker volumes can be backed up")
    running = []
    for container in client.containers.list(all=True):
        attrs = container.attrs
        mounts = [mount for mount in attrs.get("Mounts", []) if mount.get("Type") == "volume" and mount.get("Name") == volume]
        if not mounts:
            continue
        if _protected_container(attrs) or any(mount.get("Destination") in {"/run/yachtplus-security", "/var/lib/docker", "/var/run"} for mount in mounts):
            raise ValueError("Infrastructure volumes cannot be backed up here")
        if attrs.get("State", {}).get("Running"):
            running.append(container.name)
    if running and not confirm_live:
        raise ValueError("Volume is in use; stop its application or explicitly confirm a live, crash-consistent backup")


def _helper(client, volume, read_only):
    return client.containers.create(
        image=_helper_image(client), command=["/bin/true"], entrypoint=["/bin/true"],
        name="yachtplus-backup-" + uuid4().hex,
        user="1000:1000", read_only=True, cap_drop=["ALL"],
        security_opt=["no-new-privileges:true"], network_mode="none", pids_limit=16,
        mem_limit="64m", labels={"local.yachtplus.backup.helper": "true"},
        mounts=[docker.types.Mount(target="/data", source=volume, type="volume", read_only=read_only, no_copy=True)],
    )


def create_backup_sync(backup_id, volume, confirm_live=False):
    backup_id = canonical_id(backup_id)
    deadline = time.monotonic() + MAX_SECONDS
    maximum = get_settings().BACKUP_MAX_BYTES
    with sync_docker_client() as client:
        client.api.timeout = min(getattr(client.api, "timeout", 60), 60)
        _validate_source(client, volume, confirm_live)
        helper = _helper(client, volume, True)
        try:
            chunks, _ = helper.get_archive("/data", chunk_size=1024 * 1024)
            with staging_file() as received:
                try:
                    for chunk in chunks:
                        _check_deadline(deadline)
                        if received.tell() + len(chunk) > maximum:
                            raise ValueError("Backup exceeds the configured size limit")
                        received.write(chunk)
                finally:
                    if hasattr(chunks, "close"):
                        chunks.close()
                received.seek(0)
                with archive_directory() as directory:
                    temporary = "." + backup_id + "." + uuid4().hex + ".tmp"
                    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=directory)
                    try:
                        with os.fdopen(fd, "w+b") as archive:
                            normalize_archive(received, archive, deadline=deadline)
                            digest = hashlib.file_digest(archive, "sha256").hexdigest()
                            size = archive.seek(0, os.SEEK_END)
                            archive.flush()
                            os.fsync(archive.fileno())
                        # UUID file names are never reused; fail closed on an existing destination.
                        os.link(temporary, backup_id + ".tar", src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                        os.fsync(directory)
                        return {"size_bytes": size, "sha256": digest}
                    finally:
                        os.unlink(temporary, dir_fd=directory)
        finally:
            helper.remove(force=True, v=False)


def restore_backup_sync(backup_id, sha256, target):
    validate_volume_name(target)
    deadline = time.monotonic() + MAX_SECONDS
    with open_archive(backup_id) as archive, staging_file() as normalized:
        if hashlib.file_digest(archive, "sha256").hexdigest() != sha256:
            raise ValueError("Backup checksum verification failed")
        archive.seek(0)
        normalize_archive(archive, normalized, deadline=deadline, strip_root=True)
        with sync_docker_client() as client:
            client.api.timeout = min(getattr(client.api, "timeout", 60), 60)
            # Docker create-volume is idempotent, so a simple preflight is insufficient:
            # the unguessable ownership label must prove this call owns the new volume.
            ownership = uuid4().hex
            try:
                client.volumes.get(target)
            except docker.errors.NotFound:
                pass
            else:
                raise ValueError("Restore destination already exists; choose a new volume name")
            volume = client.volumes.create(name=target, driver="local", labels={"local.yachtplus.restore.transaction": ownership})
            helper = None
            try:
                volume.reload()
                if (volume.attrs.get("Labels") or {}).get("local.yachtplus.restore.transaction") != ownership:
                    raise ValueError("Restore destination was created by another operation")
                helper = _helper(client, target, False)
                # Strip the validated data/ prefix and write into this mount only.
                if not helper.put_archive("/data", normalized):
                    raise ValueError("Docker did not accept the restore archive")
                return {"volume": target}
            except Exception:
                # Never remove an existing/unproven volume after a create-volume race.
                volume.reload()
                if (volume.attrs.get("Labels") or {}).get("local.yachtplus.restore.transaction") == ownership:
                    if helper is not None:
                        helper.remove(force=True, v=False)
                        helper = None
                    volume.remove()
                raise
            finally:
                if helper is not None:
                    helper.remove(force=True, v=False)


def backup_data(row):
    data = {name: getattr(row, name) for name in ("id", "volume", "created_by", "created_at", "status", "size_bytes", "sha256", "error", "operation_id")}
    if data["created_at"] and data["created_at"].tzinfo is None:
        data["created_at"] = data["created_at"].replace(tzinfo=timezone.utc)
    return data


def inspect_archive_sync(backup_id, sha256, target=None):
    with open_archive(backup_id) as archive, staging_file() as normalized:
        if hashlib.file_digest(archive, "sha256").hexdigest() != sha256:
            raise ValueError("Backup checksum verification failed")
        archive.seek(0)
        count = normalize_archive(archive, normalized)
    if target is not None:
        validate_volume_name(target)
        with sync_docker_client() as client:
            try:
                client.volumes.get(target)
            except docker.errors.NotFound:
                pass
            else:
                raise ValueError("Restore destination already exists; choose a new volume name")
    return {"entry_count": count, "checksum_verified": True, "target_volume": target}


def schedule_data(row):
    data = {name: getattr(row, name) for name in ("id", "volume", "enabled", "hour_utc", "minute_utc", "retain_count", "confirm_live", "created_by", "last_run_at", "last_error")}
    if data["last_run_at"] and data["last_run_at"].tzinfo is None:
        data["last_run_at"] = data["last_run_at"].replace(tzinfo=timezone.utc)
    return data


async def restore_is_pending(db, backup_id):
    return (await db.execute(select(Operation.id).where(
        Operation.kind == "volume.restore", Operation.action == canonical_id(backup_id).replace("-", ""),
        Operation.status.in_(["queued", "running"]),
    ).limit(1))).scalar_one_or_none() is not None


async def _assert_admin(username, version):
    if get_settings().DISABLE_AUTH and username == "dev":
        return
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == username))).scalars().first()
        if not user or not user.is_active or not user.is_superuser or user.auth_version != version:
            raise ValueError("Backup administrator session is no longer valid")


async def _apply_retention(volume, schedule_id, actor):
    async with SessionLocal() as db:
        schedule = await db.get(BackupSchedule, schedule_id)
        if not schedule or not schedule.enabled or schedule.created_by_id != actor.id or schedule.created_by_version != actor.auth_version:
            return
        older = (await db.execute(select(VolumeBackup).where(
            VolumeBackup.volume == volume, VolumeBackup.status == "completed",
        ).order_by(VolumeBackup.created_at.desc(), VolumeBackup.id).offset(schedule.retain_count))).scalars().all()
        for row in older:
            if await restore_is_pending(db, row.id):
                continue
            await asyncio.to_thread(delete_archive, row.id)
            await db.delete(row)
        schedule.last_error = None
        await db.commit()


async def _schedule_error(schedule_id, message):
    if not schedule_id:
        return
    async with SessionLocal() as db:
        schedule = await db.get(BackupSchedule, schedule_id)
        if schedule:
            schedule.last_error = message
            await db.commit()


async def backup_runner(backup_id, actor, confirm_live, report, schedule_id=None):
    try:
        await _assert_admin(actor.username, actor.auth_version)
        async with SessionLocal() as db:
            backup = await db.get(VolumeBackup, backup_id)
            backup.status = "running"
            volume = backup.volume
            await db.commit()
        await report("Reading and validating volume archive")
        result = await asyncio.to_thread(create_backup_sync, backup_id, volume, confirm_live)
        async with SessionLocal() as db:
            backup = await db.get(VolumeBackup, backup_id)
            backup.status = "completed"
            backup.size_bytes = result["size_bytes"]
            backup.sha256 = result["sha256"]
            await db.commit()
        await report("Backup archive verified and saved")
        if schedule_id:
            try:
                await _apply_retention(volume, schedule_id, actor)
            except Exception:
                logger.exception("Backup retention failed for schedule %s", schedule_id)
                await _schedule_error(schedule_id, "Backup saved, but retention cleanup failed. Check server logs.")
        return {"backup_id": backup_id}
    except Exception:
        logger.exception("Volume backup failed: %s", backup_id)
        async with SessionLocal() as db:
            backup = await db.get(VolumeBackup, backup_id)
            if backup:
                backup.status = "failed"
                backup.error = "Backup failed. Check server logs and volume consistency requirements."
                await db.commit()
        await _schedule_error(schedule_id, "Scheduled backup failed. Check Tasks and server logs.")
        raise ValueError("Volume backup failed; check server logs") from None


async def queue_backup(db, *, volume, actor, confirm_live=False, schedule_id=None):
    from api.services.operations import submit_operation
    row = VolumeBackup(id=str(uuid4()), volume=validate_volume_name(volume), created_by=actor.username, status="queued")
    db.add(row)
    try:
        async def runner(report):
            return await backup_runner(row.id, actor, confirm_live, report, schedule_id)
        await submit_operation(db, kind="volume.backup", resource=volume, actor=actor, runner=runner,
                               before_commit=lambda operation: setattr(row, "operation_id", operation.id))
    except Exception:
        await db.rollback()
        raise
    return row


async def run_due_backups(now=None):
    """Claim due slots and enqueue jobs; their runners own retention cleanup.

    The scanner never waits for archive streaming, so a slow backup does not
    block later policies or lose its cleanup when the scheduler times out.
    """
    now = now or datetime.now(timezone.utc)
    async with SessionLocal() as db:
        identifiers = (await db.execute(select(BackupSchedule.id).where(BackupSchedule.enabled.is_(True)))).scalars().all()
    for schedule_id in identifiers:
        # A failed enqueue rolls its transaction back and expires ORM objects.
        # Isolate policies so that one failure cannot invalidate later rows.
        async with SessionLocal() as db:
            schedule = await db.get(BackupSchedule, schedule_id)
            if schedule is None or not schedule.enabled:
                continue
            slot = now.replace(hour=schedule.hour_utc, minute=schedule.minute_utc, second=0, microsecond=0)
            previous = schedule.last_run_at
            if previous and previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            if now < slot or (previous and previous >= slot):
                continue
            condition = BackupSchedule.last_run_at.is_(None) if schedule.last_run_at is None else BackupSchedule.last_run_at == schedule.last_run_at
            claimed = await db.execute(update(BackupSchedule).where(BackupSchedule.id == schedule.id, condition).values(last_run_at=now))
            await db.commit()
            if not claimed.rowcount:
                continue
            actor = (await db.execute(select(User).where(User.username == schedule.created_by))).scalars().first()
            if not actor or not actor.is_active or not actor.is_superuser or actor.id != schedule.created_by_id or actor.auth_version != schedule.created_by_version:
                logger.warning("Skipping backup schedule with unavailable administrator: %s", schedule.id)
                schedule.enabled = False
                schedule.last_error = "Administrator authorization changed; review and save this schedule again."
                await db.commit()
                continue
            try:
                await queue_backup(db, volume=schedule.volume, actor=actor, confirm_live=schedule.confirm_live, schedule_id=schedule.id)
            except Exception:
                await db.rollback()
                logger.exception("Scheduled volume backup failed: %s", schedule_id)
                await db.execute(update(BackupSchedule).where(BackupSchedule.id == schedule_id).values(
                    last_error="Scheduled backup failed. Check Tasks and server logs.",
                ))
                await db.commit()


async def recover_backups(db=None):
    """Only repair metadata whose operation has actually failed/interrupted.

    Another healthy API worker may own a live job, so startup alone is never
    evidence that its archives should be marked failed.
    """
    if db is None:
        async with SessionLocal() as session:
            await recover_backups(session)
        return
    failed = select(Operation.id).where(Operation.status.in_(["failed", "interrupted"]))
    await db.execute(update(VolumeBackup).where(
        VolumeBackup.status.in_(["queued", "running"]), VolumeBackup.operation_id.in_(failed),
    ).values(status="failed", error="Backup task failed or was interrupted; create a new backup."))
    await db.commit()
