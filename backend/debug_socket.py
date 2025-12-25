import aiodocker
import asyncio
import sys
import subprocess
import os

async def check_docker():
    try:
        print("Checking Docker connection...")
        async with aiodocker.Docker() as docker:
            print("Connecting to Docker API...")
            containers = await docker.containers.list()
            print(f"Success! Found {len(containers)} containers.")
            for c in containers:
                name = c._container.get("Names", ["/Unknown"])[0]
                print(f" - {name}")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        # Check if it's a permission error
        if "Permission denied" in str(e) or "EACCES" in str(e):
            print("\n!!! PERMISSION DENIED !!!")
            print("The 'appuser' cannot access /var/run/docker.sock.")
            try:
                print("Current User ID: " + str(subprocess.check_output(["id", "-u"]).decode().strip()))
                print("Docker Socket GID: " + str(os.stat("/var/run/docker.sock").st_gid))
            except Exception as inner_e:
                print(f"Error getting debug info: {inner_e}")
            sys.exit(1)
        sys.exit(1)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(check_docker())
