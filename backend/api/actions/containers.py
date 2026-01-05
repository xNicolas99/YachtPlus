import aiodocker
import json
import asyncio
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def calculate_container_stats(stats, container_name="Unknown"):
    """
    Pure function to calculate CPU and Memory percentages from Docker stats payload.
    """
    cpu_percent = 0.0
    mem_percent = 0.0
    mem_current = 0
    mem_limit = 0

    try:
        # Calculate Memory
        try:
            mem_stats = stats.get("memory_stats", {})
            mem_current = mem_stats.get("usage", 0)
            mem_limit = mem_stats.get("limit", 0)
            if mem_limit > 0:
                mem_percent = (mem_current / mem_limit) * 100.0
        except Exception:
            pass

        # Calculate CPU
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
        except Exception:
            pass

        return {
            "name": container_name,
            "cpu_percent": round(cpu_percent, 2),
            "memory_percent": round(mem_percent, 2),
            "memory_usage_mb": round(mem_current / 1024 / 1024, 2),
            "memory_limit_mb": round(mem_limit / 1024 / 1024, 2),
            "status": "running"
        }
    except Exception as e:
        logger.error(f"Error calculating stats for {container_name}: {e}")
        return None

async def get_containers():
    async with aiodocker.Docker() as docker:
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

async def get_logs_generator(container_id: str, tail: int = 100, follow: bool = True, timestamps: bool = False):
    docker = aiodocker.Docker()
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
    except Exception as e:
        yield {"event": "error", "data": str(e)}
    finally:
        await docker.close()

async def get_stats(container_id: str):
    async with aiodocker.Docker() as docker:
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

        # Reuse calculation logic
        container_name = c_inspect.get("Name", "/Unknown")[1:]
        result = calculate_container_stats(stats, container_name)
        if result:
            # The API expected specific keys slightly different or subset, but let's see.
            # Original return was: cpu_percent, memory_usage_mb, memory_limit_mb, memory_percent
            # calculate_container_stats returns these plus 'name', 'id', 'status'.
            # It matches.
            return result
        else:
             raise HTTPException(status_code=500, detail="Calculation Error")
