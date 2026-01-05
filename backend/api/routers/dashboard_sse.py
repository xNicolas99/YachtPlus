from fastapi import APIRouter, Depends, status, Request
from sse_starlette.sse import EventSourceResponse
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
import api.actions.dashboard as dashboard_actions
import api.actions.containers as container_actions
import aiodocker
import asyncio
import logging
from api.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

router = APIRouter()

# Global stream control
STREAM_DELAY = 2  # seconds

async def stats_generator(request: Request):
    """
    Generator for dashboard stats + container stats
    """
    # Instantiate Docker client once outside the loop
    docker = aiodocker.Docker()

    try:
        while True:
            if await request.is_disconnected():
                break

            try:
                # 1. Overview
                overview_task = dashboard_actions.get_dashboard_stats()

                # 2. Container Stats (Bulk)
                # Use shared logic and persistent docker client
                container_stats = {}

                try:
                    # Note: actions.get_containers() creates its own docker client.
                    # We should probably use our local 'docker' instance if possible,
                    # but aiodocker.Docker() is lightweight if we don't open/close it repeatedly.
                    # Wait, 'docker' here is open.

                    # We can't easily pass 'docker' to actions unless we refactor actions to accept it.
                    # But for now, let's use the local docker instance to list and stat.

                    containers = await docker.containers.list()

                    async def fetch_single_stats(container):
                        try:
                            # We use stream=False for snapshot
                            stats = await container.stats(stream=False)
                            name = container._container.get("Names", ["/Unknown"])[0][1:]

                            # Use shared calculation logic
                            res = container_actions.calculate_container_stats(stats, name)
                            if res:
                                res['id'] = container.id
                            return res
                        except Exception:
                            return None

                    tasks = [fetch_single_stats(c) for c in containers]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for res in results:
                        if res and isinstance(res, dict):
                            container_stats[res['name']] = res

                except Exception as e:
                    logger.error(f"Error fetching container stats for SSE: {e}")

                # Wait for overview
                overview = await overview_task

                # Merge
                payload = overview
                payload["container_stats"] = container_stats

                yield {
                    "event": "message",
                    "id": "message_id",
                    "retry": 2000,
                    "data": payload
                }
            except Exception as e:
                logger.error(f"Error generating dashboard stats stream: {e}")
                yield {
                    "event": "error",
                    "data": str(e)
                }

            await asyncio.sleep(STREAM_DELAY)
    finally:
        # Ensure we close the client when the client disconnects or error occurs
        await docker.close()

@router.get("/stream")
async def stream_dashboard_stats(
    request: Request,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    Streams dashboard stats via SSE (Overview + Container CPU/RAM)
    """
    auth_check(Authorize)
    return EventSourceResponse(stats_generator(request))
