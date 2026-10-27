import atexit
import os
try:
    import fcntl
except ImportError:  # Windows development and test runs
    fcntl = None
    import msvcrt
from apscheduler.schedulers.background import BackgroundScheduler
# Watchtower runs inside the *sync* BackgroundScheduler thread, so it
# must call the sync implementation directly. Previously this file
# imported `compose_action` (the `async def` wrapper) and invoked it
# without await — every call produced a "RuntimeWarning: coroutine
# never awaited" and silently did nothing. Auto-update was broken.
from api.actions.compose import _compose_action_sync
from api.settings import get_settings
settings = get_settings()
from api.utils.compose import find_yml_files
import logging

logger = logging.getLogger("yachtplus.watchtower")

scheduler = BackgroundScheduler()

# Guard to avoid starting the scheduler more than once per process. This is
# important when running under gunicorn with multiple workers; without the
# guard each worker would start its own scheduler and run the same update
# job concurrently.
_scheduler_started = False


def update_compose_project(project_name):
    """
    Pulls images and updates the stack for a given compose project.
    """
    logger.info(f"Auto-updating project: {project_name}")
    try:
        # Pull is implicitly handled if we do 'pull' action or if 'up' pulls?
        # docker-compose up -d usually pulls if missing, but to force update we need pull first.
        # api.actions.compose.compose_action handles basic actions.
        # We need to extend it or call it twice.

        # 1. Pull
        logger.info(f"Pulling images for {project_name}...")
        # compose_action doesn't support "pull" explicitly yet in the original code unless updated.
        # But 'docker-compose pull' is a valid command.
        # api.actions.compose.compose_action calls docker_compose(action, ...)
        # So it should work if we pass "pull" as action.
        _compose_action_sync(project_name, "pull")

        # 2. Up -d
        logger.info(f"Recreating containers for {project_name}...")
        _compose_action_sync(project_name, "up")

        logger.info(f"Successfully updated {project_name}")
    except Exception as e:
        logger.error(f"Failed to update {project_name}: {e}")
        raise

def update_all_projects():
    """
    Iterates through all compose projects and updates them.
    """
    if not get_settings().COMPOSE_AUTO_UPDATE:
        return
    # A saved per-project policy overrides the global legacy opt-in,
    # including disabled schedules and explicit exclusions. Failure to read
    # those policies must never silently bypass a maintenance window.
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from api.db.database import sync_migration_url
    from api.db.models.update_plans import UpdatePlan
    plan_engine = create_engine(sync_migration_url(get_settings().DATABASE_URL))

    def uses_global_policy(project_name):
        try:
            with Session(plan_engine) as db:
                return db.scalar(select(UpdatePlan.project_name).where(
                    UpdatePlan.project_name == project_name
                )) is None
        except Exception:
            logger.exception("Automatic updates stopped because project update policies are unavailable")
            return False

    try:
        files = find_yml_files(get_settings().COMPOSE_DIR)
        for project_name in files:
            if not get_settings().COMPOSE_AUTO_UPDATE or not uses_global_policy(project_name):
                continue
            _compose_action_sync(project_name, "pull")
            # A plan or exclusion may be saved while another project's pull
            # is running. Check again immediately before service recreation.
            if get_settings().COMPOSE_AUTO_UPDATE and uses_global_policy(project_name):
                _compose_action_sync(project_name, "up")
    finally:
        plan_engine.dispose()

def _acquire_leader_lock() -> bool:
    """Try to acquire a filesystem lock so only one worker becomes leader.

    gunicorn runs multiple worker processes. APScheduler's BackgroundScheduler
    would start in every worker, causing the same compose auto-update to run
    N times simultaneously. A non-blocking flock on a shared file elects
    exactly one leader per container; other workers skip scheduling silently.
    The lock is released automatically when the process exits.
    """
    lock_dir = os.path.dirname(settings.COMPOSE_DIR) or "."
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, ".watchtower_leader.lock")
    fd = None
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        if fcntl is None:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_NB | fcntl.LOCK_EX)
        # Keep fd open for the process lifetime; register a cleanup.
        def release_lock():
            try:
                if fcntl is None:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

        atexit.register(release_lock)
        return True
    except (OSError, BlockingIOError):
        if fd is not None:
            os.close(fd)
        return False


def start_scheduler():
    global _scheduler_started
    if _scheduler_started:
        logger.debug("Watchtower scheduler already started in this process; skipping.")
        return

    if not _acquire_leader_lock():
        logger.info("Another worker already leads the watchtower scheduler; skipping.")
        return

    # Schedule update every 24 hours (example)
    # Ideally this should be configurable via DB settings
    if get_settings().COMPOSE_AUTO_UPDATE:
        scheduler.add_job(update_all_projects, 'interval', hours=24, id='auto_update_all')
    scheduler.add_job(cleanup_security_records, 'interval', hours=1, id='security_cleanup')
    scheduler.add_job(run_scheduled_policies, 'interval', seconds=60,
                      id='scheduled_policies', max_instances=1, coalesce=True)
    scheduler.start()
    _scheduler_started = True
    logger.info("Watchtower scheduler started.")

def stop_scheduler():
    global _scheduler_started
    if not _scheduler_started:
        return
    scheduler.shutdown(wait=False)
    _scheduler_started = False


def run_scheduled_policies():
    """Enqueue opt-in policies on the API loop from the scheduler thread."""
    import asyncio
    from concurrent.futures import TimeoutError
    from api.services.operations import get_operation_loop
    loop = get_operation_loop()
    if loop is None or not loop.is_running():
        return

    async def enqueue():
        from api.services.backups import run_due_backups
        from api.services.update_plans import run_due_update_plans
        for callback in (run_due_update_plans, run_due_backups):
            try:
                await callback()
            except Exception:
                logger.exception("Scheduled policy scan failed: %s", callback.__name__)

    future = asyncio.run_coroutine_threadsafe(enqueue(), loop)
    try:
        future.result(timeout=45)
    except TimeoutError:
        future.cancel()
        logger.error("Scheduled policy scan exceeded its time limit")

def cleanup_security_records():
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import delete
    from api.db.database import sync_migration_url
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from api.db.models.audit import AuditLog
    from api.db.models.users import LoginAttempt
    from api.db.models.settings import TokenBlacklist
    now = datetime.now(timezone.utc)
    cleanup_engine = create_engine(sync_migration_url(settings.DATABASE_URL))
    try:
        with Session(cleanup_engine) as db:
            db.execute(delete(AuditLog).where(AuditLog.timestamp < now - timedelta(days=settings.AUDIT_RETENTION_DAYS)))
            db.execute(delete(LoginAttempt).where(LoginAttempt.timestamp < now - timedelta(days=settings.LOGIN_RETENTION_DAYS)))
            db.execute(delete(TokenBlacklist).where(TokenBlacklist.expires < now))
            db.commit()
    finally:
        cleanup_engine.dispose()
# updated
