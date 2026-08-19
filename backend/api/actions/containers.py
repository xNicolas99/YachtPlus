import aiodocker
import json
import asyncio
from fastapi import HTTPException
import logging
from datetime import datetime
from api.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

# Cache stats for 5 seconds
stats_cache = {}
CACHE_TTL = 5  # seconds

async def get_containers():
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            containers = await docker.containers.list(all=True)
            # Normalize container objects to dicts
            result = []
            for c in containers:
                c_dict = c._container if hasattr(c, '_container') else c
                result.append(c_dict)
            return result
        except Exception as e:
            logger.error(f"Error fetching containers: {e}")
            raise HTTPException(status_code=500, detail=str(e))

async def stream_stats_generator(request, container_id: str):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        stats_iter = None
        try:
            container = await docker.containers.get(container_id)
            # Hold a reference to the async iterator so we can explicitly
            # aclose() it in the finally — without that, when the client
            # disconnects (`break` below) the underlying aiohttp response
            # was leaking until GC ran.
            stats_iter = container.stats(stream=True)
            async for stats in stats_iter:
                if await request.is_disconnected():
                    break

                mem_usage = stats.get("memory_stats", {}).get("usage", 0)
                mem_limit = stats.get("memory_stats", {}).get("limit", 1)
                mem_percent = (mem_usage / mem_limit) * 100.0

                cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
                system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
                online_cpus = stats["cpu_stats"].get("online_cpus", 1)
                cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0 if system_delta > 0 else 0.0

                payload = {
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_percent": round(mem_percent, 2),
                    "memory_usage_mb": round(mem_usage / 1024 / 1024, 2)
                }
                yield {"event": "stats", "data": json.dumps(payload)}
        except asyncio.CancelledError:
            # Client disconnected — normal SSE exit, don't log an error.
            raise
        except Exception:
            logger.exception("SSE stats stream error for container %s", container_id)
            # Send a generic error frame; don't echo the raw exception
            # message back to the browser (could include internal paths
            # or daemon details).
            yield {"event": "error", "data": "stats stream error"}
        finally:
            if stats_iter is not None and hasattr(stats_iter, "aclose"):
                try:
                    await stats_iter.aclose()
                except Exception:
                    logger.debug(
                        "Failed to close stats iterator for %s",
                        container_id,
                        exc_info=True,
                    )

async def get_logs_generator(container_id: str, tail: int = 100, follow: bool = True, timestamps: bool = False):
    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        try:
            container = await docker.containers.get(container_id)
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                raise HTTPException(status_code=404, detail="Container not found")
            raise HTTPException(status_code=500, detail=str(e))

        # log() returns an async generator
        try:
            logs = container.log(stdout=True, stderr=True, follow=follow, tail=tail, timestamps=timestamps)
        except aiodocker.exceptions.DockerError as e:
             raise HTTPException(status_code=500, detail=str(e))

        async for line in logs:
            yield {"data": line}

    except asyncio.CancelledError:
        # Client disconnected
        pass
    except HTTPException:
        # Re-raise FastAPI/Starlette HTTPExceptions (e.g. 404) as-is.
        raise
    except Exception as e:
        logger.exception(
            "Error streaming logs for container %r", container_id
        )
        # Never send the raw exception text to the client: it may contain
        # daemon paths, internal hostnames, or other operational details.
        yield {"event": "error", "data": "Failed to stream container logs."}
    finally:
        await docker.close()

async def get_stats(container_id: str):
    async with aiodocker.Docker(url=settings.DOCKER_HOST) as docker:
        try:
            container = await docker.containers.get(container_id)
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                raise HTTPException(status_code=404, detail="Container not found")
            raise HTTPException(status_code=500, detail=str(e))

        c_inspect = await container.show()
        if c_inspect["State"]["Status"] != "running":
            raise HTTPException(status_code=409, detail="Container is not running")

        stats = None

        try:
            # Try single snapshot first
            stats = await container.stats(stream=False)

            # Check if we have valid precpu_stats
            has_precpu = False
            if 'precpu_stats' in stats:
                pre_total_usage = stats['precpu_stats'].get('cpu_usage', {}).get('total_usage', 0)
                if pre_total_usage > 0:
                     has_precpu = True

            if not has_precpu:
                 logger.debug(f"Stats: Falling back to stream for {container_id}")

                 # Reset stats to ensure we don't use the stateless snapshot if it's invalid
                 stats = None

                 # Using a managed context for stream to ensure it closes
                 async for chunk in container.stats(stream=True):
                      if not stats:
                           stats = chunk
                           # If the first chunk happens to have valid precpu, we can stop.
                           if 'precpu_stats' in chunk and chunk['precpu_stats']['cpu_usage']['total_usage'] > 0:
                                break
                      else:
                           # This is the second chunk. It should have precpu_stats populated relative to the first.
                           stats = chunk
                           break

        except aiodocker.exceptions.DockerError as e:
             raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
             logger.error(f"Error fetching stats stream: {e}")
             if not stats:
                 raise HTTPException(status_code=500, detail="Failed to fetch stats")

        # Fallback check if stats is still None (e.g. stream returned empty)
        if not stats:
             raise HTTPException(status_code=500, detail="Failed to fetch stats (empty)")

        # Calculate Memory
        mem_current = 0
        mem_total = 0
        mem_percent = 0

        if "memory_stats" in stats:
             mem_current = stats["memory_stats"].get("usage", 0)
             mem_total = stats["memory_stats"].get("limit", 0)

             # Fallback if limit is extremely high (host memory) or 0
             if mem_total == 0:
                 mem_total = 1 # Avoid div by zero

             mem_percent = (mem_current / mem_total) * 100.0

        # Calculate CPU
        cpu_percent = 0.0
        try:
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})

            cpu_usage = cpu_stats.get("cpu_usage", {})
            pre_cpu_usage = precpu_stats.get("cpu_usage", {})

            total_usage = cpu_usage.get("total_usage", 0)
            pre_total_usage = pre_cpu_usage.get("total_usage", 0)

            system_cpu_usage = cpu_stats.get("system_cpu_usage", 0)
            pre_system_cpu_usage = precpu_stats.get("system_cpu_usage", 0)

            cpu_delta = float(total_usage) - float(pre_total_usage)
            system_delta = float(system_cpu_usage) - float(pre_system_cpu_usage)

            # Determine Number of CPUs
            # 1. online_cpus (Docker 1.13+)
            online_cpus = cpu_stats.get("online_cpus")
            if not online_cpus:
                # 2. Length of percpu_usage
                percpu_usage = cpu_usage.get("percpu_usage", [])
                if percpu_usage:
                    online_cpus = len(percpu_usage)
                else:
                    # 3. Fallback to 1
                    online_cpus = 1

            if system_delta > 0.0 and cpu_delta > 0.0:
                 cpu_percent = (cpu_delta / system_delta) * float(online_cpus) * 100.0

        except Exception as e:
            logger.error(f"Error calculating CPU stats for {container_id}: {e}")
            pass

        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(mem_current / 1024 / 1024, 2),
            "memory_limit_mb": round(mem_total / 1024 / 1024, 2),
            "memory_percent": round(mem_percent, 2)
        }

async def get_all_stats():
    now = datetime.now()

    # Check cache
    if 'data' in stats_cache and 'timestamp' in stats_cache:
        age = (now - stats_cache['timestamp']).total_seconds()
        if age < CACHE_TTL:
            return stats_cache['data']

    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        containers = await docker.containers.list()

        async def fetch_single_stats(container):
            try:
                stats = await container.stats(stream=False)

                # Calculate CPU
                cpu_percent = 0.0
                mem_percent = 0.0
                mem_current = 0
                mem_limit = 0

                try:
                    cpu_stats = stats.get("cpu_stats", {})
                    precpu_stats = stats.get("precpu_stats", {})

                    cpu_usage = cpu_stats.get("cpu_usage", {})
                    pre_cpu_usage = precpu_stats.get("cpu_usage", {})

                    total_usage = cpu_usage.get("total_usage", 0)
                    pre_total_usage = pre_cpu_usage.get("total_usage", 0)

                    system_cpu_usage = cpu_stats.get("system_cpu_usage", 0)
                    pre_system_cpu_usage = precpu_stats.get("system_cpu_usage", 0)

                    if total_usage > 0 and pre_total_usage > 0:
                        cpu_delta = float(total_usage) - float(pre_total_usage)
                        system_delta = float(system_cpu_usage) - float(pre_system_cpu_usage)

                        online_cpus = cpu_stats.get("online_cpus")
                        if not online_cpus:
                            online_cpus = len(cpu_usage.get("percpu_usage", [])) or 1

                        if system_delta > 0.0 and cpu_delta > 0.0:
                            cpu_percent = (cpu_delta / system_delta) * float(online_cpus) * 100.0
                except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                    # Stats payload from Docker is best-effort and can be
                    # missing fields on cold-started containers. Log so a
                    # repeatedly-broken container surfaces in the logs.
                    logger.debug("CPU stats parse skipped: %s", exc)

                try:
                    mem_stats = stats.get("memory_stats", {})
                    mem_current = mem_stats.get("usage", 0)
                    mem_limit = mem_stats.get("limit", 0)
                    if mem_limit > 0:
                        mem_percent = (mem_current / mem_limit) * 100.0
                except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                    logger.debug("Memory stats parse skipped: %s", exc)

                # Get name (strip /)
                name = container._container.get("Names", ["/Unknown"])[0][1:]

                return {
                    "name": name,
                    "id": container.id,
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_percent": round(mem_percent, 2),
                    "memory_usage_mb": round(mem_current / 1024 / 1024, 2),
                    "memory_limit_mb": round(mem_limit / 1024 / 1024, 2),
                    "status": "running"
                }
            except Exception as e:
                # logger.error(f"Error fetching stats for container: {e}")
                return None

        tasks = [fetch_single_stats(c) for c in containers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out Nones and Errors
        valid_results = {}
        for res in results:
            if res and isinstance(res, dict):
                valid_results[res['name']] = res

        # Update cache
        stats_cache['data'] = valid_results
        stats_cache['timestamp'] = now

        return valid_results

    except Exception as e:
        logger.error(f"Global stats error: {e}")
        return {}
    finally:
        await docker.close()
