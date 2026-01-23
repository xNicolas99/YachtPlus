from fastapi import APIRouter, Depends
from api.auth.auth import get_auth_wrapper
import psutil
import shutil

router = APIRouter()

@router.get("/stats")
async def get_dashboard_stats(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    Authorize.jwt_required()

    cpu_percent = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage("/")

    return {
        "resources": {
            "cpu": cpu_percent,
            "ram": mem.percent,
            "ram_total": mem.total,
            "ram_used": mem.used,
            "disk": round((disk.used / disk.total) * 100, 1),
            "disk_total": disk.total,
            "disk_used": disk.used
        },
        "info": {"status": "active"}
    }
