import aiodocker
import json
import asyncio
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

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

        if container._container["State"]["Status"] != "running":
            raise HTTPException(status_code=409, detail="Container is not running")

        try:
            # Use stream=False as requested by user to fix stats issue
            stats = await container.stats(stream=False)
        except aiodocker.exceptions.DockerError as e:
             raise HTTPException(status_code=500, detail=str(e))

        # Calculate Memory
        mem_current = 0
        mem_total = 0
        mem_percent = 0

        if "memory_stats" in stats:
             mem_current = stats["memory_stats"].get("usage", 0)
             mem_total = stats["memory_stats"].get("limit", 0)
             if mem_total > 0:
                 mem_percent = (mem_current / mem_total) * 100.0

        # Calculate CPU
        cpu_percent = 0.0
        try:
            cpu_stats = stats.get("cpu_stats", {})
            # With stream=False, precpu_stats should be present in the response
            precpu_stats = stats.get("precpu_stats", {})

            cpu_usage = cpu_stats.get("cpu_usage", {})
            pre_cpu_usage = precpu_stats.get("cpu_usage", {})

            total_usage = cpu_usage.get("total_usage", 0)
            pre_total_usage = pre_cpu_usage.get("total_usage", 0)

            system_cpu_usage = cpu_stats.get("system_cpu_usage", 0)
            pre_system_cpu_usage = precpu_stats.get("system_cpu_usage", 0)

            cpu_delta = total_usage - pre_total_usage
            system_delta = system_cpu_usage - pre_system_cpu_usage

            percpu_usage = cpu_usage.get("percpu_usage", [])
            num_cpus = len(percpu_usage) if percpu_usage else 1
            if num_cpus == 0:
                 # Fallback if percpu_usage is empty
                 online_cpus = cpu_stats.get("online_cpus", 1)
                 num_cpus = online_cpus

            if system_delta > 0 and cpu_delta > 0:
                 cpu_percent = (cpu_delta / system_delta) * num_cpus * 100.0
        except Exception as e:
            logger.error(f"Error calculating CPU stats for {container_id}: {e}")
            pass

        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(mem_current / 1024 / 1024, 2),
            "memory_limit_mb": round(mem_total / 1024 / 1024, 2),
            "memory_percent": round(mem_percent, 2)
        }
