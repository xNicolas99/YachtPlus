import atexit
import fcntl
import os
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

def update_all_projects():
    """
    Iterates through all compose projects and updates them.
    """
    files = find_yml_files(get_settings().COMPOSE_DIR)
    for project_name in files.keys():
        update_compose_project(project_name)

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
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_NB | fcntl.LOCK_EX)
        # Keep fd open for the process lifetime; register a cleanup.
        atexit.register(lambda: (fcntl.flock(fd, fcntl.LOCK_UN), os.close(fd)))
        return True
    except (OSError, BlockingIOError):
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
    scheduler.add_job(update_all_projects, 'interval', hours=24, id='auto_update_all')
    scheduler.start()
    _scheduler_started = True
    logger.info("Watchtower scheduler started.")

def stop_scheduler():
    global _scheduler_started
    scheduler.shutdown()
    _scheduler_started = False
# updated
