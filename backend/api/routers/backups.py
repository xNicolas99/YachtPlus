"""Administrator-only volume archives and opt-in daily schedules."""
import asyncio
import logging

import docker
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.auth import require_superuser
from api.auth.jwt import get_auth_wrapper
from api.db.models.backups import BackupSchedule, VolumeBackup
from api.services import backups
from api.utils.audit import log_activity
from api.utils.auth import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


class BackupRequest(BaseModel):
    volume: str = Field(min_length=1, max_length=255)
    confirm_live: StrictBool = False


class RestoreRequest(BaseModel):
    target_volume: str = Field(min_length=1, max_length=255)
    confirm_new_volume: StrictBool = False


class ScheduleRequest(BaseModel):
    enabled: StrictBool = False
    hour_utc: int = Field(default=2, ge=0, le=23)
    minute_utc: int = Field(default=0, ge=0, le=59)
    retain_count: int = Field(default=7, ge=1, le=30)
    confirm_live: StrictBool = False


async def _administrator(authorize, db):
    user = await require_superuser(authorize, db)
    if getattr(authorize, "is_api_key", lambda: False)():
        raise HTTPException(403, "Volume backups are not available via API key")
    return user


async def _completed_backup(db, backup_id):
    row = await db.get(VolumeBackup, backups.canonical_id(backup_id))
    if row is None:
        raise HTTPException(404, "Backup not found")
    if row.status != "completed" or not row.sha256:
        raise HTTPException(409, "Only completed backups can be restored")
    return row


async def _validate_source(volume, confirm_live):
    def validate():
        from api.utils.docker_client import sync_docker_client
        with sync_docker_client() as client:
            backups._validate_source(client, volume, confirm_live)
    try:
        await asyncio.to_thread(validate)
    except HTTPException:
        raise
    except docker.errors.NotFound:
        raise HTTPException(404, "Volume not found") from None
    except ValueError as exc:
        # Messages here are fixed policy strings, not daemon exceptions.
        raise HTTPException(409, str(exc)) from None
    except Exception:
        logger.exception("Could not validate backup volume")
        raise HTTPException(503, "Docker volume inventory is unavailable") from None


@router.get("/volumes")
async def available_volumes(db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    await _administrator(Authorize, db)
    try:
        return {"items": await asyncio.to_thread(backups.volume_inventory_sync)}
    except Exception:
        logger.exception("Could not read backup volume inventory")
        raise HTTPException(503, "Docker volume inventory is unavailable") from None


@router.get("/schedules")
async def list_schedules(db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    await _administrator(Authorize, db)
    rows = (await db.execute(select(BackupSchedule).order_by(BackupSchedule.volume))).scalars().all()
    return {"items": [backups.schedule_data(row) for row in rows]}


@router.put("/schedules/{volume}")
async def save_schedule(volume: str, payload: ScheduleRequest, db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    user = await _administrator(Authorize, db)
    backups.validate_volume_name(volume)
    if payload.enabled:
        await _validate_source(volume, payload.confirm_live)
    row = (await db.execute(select(BackupSchedule).where(BackupSchedule.volume == volume))).scalars().first()
    if row is None:
        row = BackupSchedule(volume=volume, created_by=user.username)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.created_by = user.username
    row.created_by_id = user.id
    row.created_by_version = user.auth_version
    row.last_error = None
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Backup schedule changed concurrently; refresh and retry") from None
    await log_activity(db, user.username, "backup.schedule.updated", volume)
    return backups.schedule_data(row)


@router.delete("/schedules/{volume}")
async def delete_schedule(volume: str, db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    user = await _administrator(Authorize, db)
    row = (await db.execute(select(BackupSchedule).where(BackupSchedule.volume == volume))).scalars().first()
    if row is None:
        raise HTTPException(404, "Backup schedule not found")
    await db.delete(row)
    await db.commit()
    await log_activity(db, user.username, "backup.schedule.deleted", volume)
    return {"deleted": True}


@router.get("")
async def list_backups(
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper),
):
    await _administrator(Authorize, db)
    await backups.recover_backups(db)
    total = (await db.execute(select(func.count()).select_from(VolumeBackup))).scalar_one()
    rows = (await db.execute(select(VolumeBackup).order_by(VolumeBackup.created_at.desc(), VolumeBackup.id).offset(offset).limit(limit))).scalars().all()
    return {"items": [backups.backup_data(row) for row in rows], "total": total}


@router.post("", status_code=202)
async def create_backup(payload: BackupRequest, db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    user = await _administrator(Authorize, db)
    await _validate_source(payload.volume, payload.confirm_live)
    row = await backups.queue_backup(db, volume=payload.volume, actor=user, confirm_live=payload.confirm_live)
    await log_activity(db, user.username, "backup.queued", payload.volume)
    return backups.backup_data(row)


@router.post("/{backup_id}/restore/preview")
async def preview_restore(backup_id: str, payload: RestoreRequest, db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    await _administrator(Authorize, db)
    row = await _completed_backup(db, backup_id)
    try:
        result = await asyncio.to_thread(backups.inspect_archive_sync, row.id, row.sha256, payload.target_volume)
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError):
        raise HTTPException(409, "Archive verification failed or destination volume already exists") from None
    except Exception:
        logger.exception("Restore preview failed: %s", backup_id)
        raise HTTPException(503, "Restore verification is unavailable") from None
    return {**result, "backup_id": row.id, "source_volume": row.volume, "size_bytes": row.size_bytes}


@router.post("/{backup_id}/restore", status_code=202)
async def restore_backup(backup_id: str, payload: RestoreRequest, db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    user = await _administrator(Authorize, db)
    if not payload.confirm_new_volume:
        raise HTTPException(422, "Confirm restoration into a new volume")
    backups.validate_volume_name(payload.target_volume)
    row = await _completed_backup(db, backup_id)
    await preview_restore(backup_id, payload, db, Authorize)
    from api.services.operations import submit_operation

    async def runner(report):
        await backups._assert_admin(user.username, user.auth_version)
        await report("Verifying archive and creating a new volume")
        try:
            await asyncio.to_thread(backups.restore_backup_sync, row.id, row.sha256, payload.target_volume)
        except Exception:
            logger.exception("Volume restoration failed: %s", backup_id)
            raise ValueError("Volume restoration failed; check server logs") from None
        await report("Archive restored into the new volume")
        return {"volume": payload.target_volume}

    operation = await submit_operation(db, kind="volume.restore", resource=payload.target_volume, actor=user,
                                       action=row.id.replace("-", ""), runner=runner)
    await log_activity(db, user.username, "backup.restore.queued", payload.target_volume)
    return {"operation_id": operation.id, "target_volume": payload.target_volume, "status": operation.status}


@router.delete("/{backup_id}")
async def delete_backup(backup_id: str, db: AsyncSession = Depends(get_db), Authorize=Depends(get_auth_wrapper)):
    user = await _administrator(Authorize, db)
    row = await db.get(VolumeBackup, backups.canonical_id(backup_id))
    if row is None:
        raise HTTPException(404, "Backup not found")
    if row.status in {"queued", "running"}:
        raise HTTPException(409, "A pending backup cannot be deleted")
    if await backups.restore_is_pending(db, row.id):
        raise HTTPException(409, "A backup with a pending restoration cannot be deleted")
    try:
        await asyncio.to_thread(backups.delete_archive, row.id)
    except Exception:
        logger.exception("Could not delete backup: %s", backup_id)
        raise HTTPException(503, "Backup storage is unavailable") from None
    await db.delete(row)
    await db.commit()
    await log_activity(db, user.username, "backup.deleted", row.volume)
    return {"deleted": True}
