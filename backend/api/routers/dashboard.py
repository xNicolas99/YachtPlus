from fastapi import APIRouter, Depends
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
import api.actions.dashboard as actions

router = APIRouter()

@router.get("/stats")
def get_dashboard_stats(Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    """
    Returns aggregated stats for the dashboard.
    """
    auth_check(Authorize)
    return actions.get_dashboard_stats()
