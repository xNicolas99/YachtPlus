from fastapi import APIRouter, Depends
from api.auth.auth import get_auth_wrapper
from api.actions import dashboard as dashboard_actions
import shutil

router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    """The Home page KPI strip reads .containers / .projects / .images /
    .volumes / .networks off this response. The router used to return
    only {resources, info} (a stub from an earlier iteration), so the
    Vue layer crashed with `TypeError: can't access property "total",
    overview.containers is undefined` every time the dashboard polled.
    Wire the proper aggregating action that returns the full shape, and
    layer disk_usage on top (the action only computes CPU + RAM).
    """
    Authorize.jwt_required()
    stats = await dashboard_actions.get_dashboard_stats()

    # Enrich `resources` with disk info; never let a stat failure break
    # the KPI strip.
    try:
        disk = shutil.disk_usage("/")
        resources = dict(stats.get("resources") or {})
        resources.update({
            "disk": round((disk.used / disk.total) * 100, 1) if disk.total else 0,
            "disk_total": disk.total,
            "disk_used": disk.used,
        })
        stats["resources"] = resources
    except Exception:
        pass

    stats.setdefault("info", {"status": "active"})
    return stats
