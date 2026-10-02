"""Explicit workload profiles; compatibility is an administrator decision."""
import re
import posixpath
import yaml

from fastapi import HTTPException

ALLOWED_CAPABILITIES = {
    "CHOWN", "DAC_OVERRIDE", "FSETID", "FOWNER", "KILL", "SETGID",
    "SETUID", "SETPCAP", "NET_BIND_SERVICE", "SYS_CHROOT", "AUDIT_WRITE",
}


def workload_options(profile="restricted", user="1000:1000", confirmed=False):
    common = {"security_opt": ["no-new-privileges:true"], "pids_limit": 256}
    if profile == "image-default":
        if not confirmed:
            raise HTTPException(422, "Confirm image compatibility mode before deploying.")
        return common
    if profile != "restricted":
        raise HTTPException(422, "Unknown container security profile.")
    # Numeric IDs avoid an image-dependent account named 'root' or a name
    # whose UID unexpectedly resolves to zero. Group zero is also refused.
    if not isinstance(user, str) or not re.fullmatch(r"[1-9][0-9]{0,9}(?::[1-9][0-9]{0,9})?", user):
        raise HTTPException(422, "Restricted containers require a nonzero numeric UID[:GID].")
    if any(int(part) > 2147483647 for part in user.split(":")):
        raise HTTPException(422, "Container UID/GID is out of range.")
    return {
        **common,
        "user": user,
        "cap_drop": ["ALL"],
        "read_only": True,
        "tmpfs": {"/tmp": "rw,nosuid,nodev,size=64m", "/run": "rw,nosuid,nodev,size=16m"},
    }


def secure_compose_content(content):
    """Give newly saved Compose services explicit, inspectable defaults.

    Expert administrators opt out per service using the literal extension
    x-yachtplus-security: image-default. Never silently weaken a restricted
    service to make an incompatible image start.
    """
    try:
        from api.utils.yaml_loader import load_yaml
        document = load_yaml(content)
    except yaml.YAMLError:
        raise HTTPException(422, "Compose content must be valid YAML.") from None
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict) or not document["services"]:
        raise HTTPException(422, "Compose content must define services.")
    if "include" in document:
        raise HTTPException(422, "Inline included services before saving their security profiles.")
    for name, original in document["services"].items():
        if not isinstance(original, dict):
            raise HTTPException(422, f"Service {name} must be an object.")
        service = dict(original)
        profile = service.get("x-yachtplus-security", "restricted")
        if profile not in ("restricted", "image-default"):
            raise HTTPException(422, f"Service {name} has an invalid security profile.")
        options = service.get("security_opt") or []
        if not isinstance(options, list) or any(not isinstance(option, str) for option in options):
            raise HTTPException(422, f"Service {name} security_opt must be a list of strings.")
        if profile == "restricted":
            if (
                service.get("privileged") or service.get("devices")
                or service.get("network_mode") not in (None, "bridge", "none", "default")
                or service.get("pid") not in (None, "private")
                or service.get("ipc") not in (None, "private") or service.get("extends")
                or service.get("volumes_from") or service.get("userns_mode") == "host"
                or any("unconfined" in option or "no-new-privileges:false" in option for option in options)
            ):
                raise HTTPException(422, f"Service {name} requires explicit x-yachtplus-security: image-default for elevated options.")
            volumes = service.get("volumes") or []
            if not isinstance(volumes, list):
                raise HTTPException(422, f"Service {name} volumes must be a list.")
            for volume in volumes:
                source = volume.get("source", "") if isinstance(volume, dict) else volume.split(":", 1)[0] if isinstance(volume, str) and ":" in volume else ""
                if not isinstance(source, str) or "${" in source:
                    raise HTTPException(422, f"Service {name} bind sources must be explicit for the restricted profile.")
                if source.startswith(".") or ("/" in source and not source.startswith("/")):
                    raise HTTPException(422, f"Service {name} requires absolute host bind paths for the restricted profile.")
                source = posixpath.normpath("/" + source.lstrip("/")) if source.startswith("/") else source
                volume_definitions = document.get("volumes") or {}
                definition = volume_definitions.get(source) if isinstance(volume_definitions, dict) else None
                if isinstance(definition, dict) and (definition.get("driver_opts") or definition.get("driver") not in (None, "local")):
                    raise HTTPException(422, f"Service {name} requires image-default for volumes with custom drivers or driver options.")
                forbidden = ("/var/run", "/run", "/proc", "/sys", "/etc", "/root", "/boot", "/dev")
                if source == "/" or any(source == path or source.startswith(path + "/") for path in forbidden):
                    raise HTTPException(422, f"Service {name} uses a restricted host bind mount.")
            user = str(service.get("user", "1000:1000"))
            workload_options("restricted", user)
            caps = service.get("cap_add") or []
            if not isinstance(caps, list) or any(not isinstance(cap, str) or cap.upper().removeprefix("CAP_") not in ALLOWED_CAPABILITIES for cap in caps):
                raise HTTPException(422, f"Service {name} requests a restricted capability.")
            if "read_only" in service and service["read_only"] is not True:
                raise HTTPException(422, f"Service {name} requires image-default for a writable root filesystem.")
            service.update(user=user, read_only=True, cap_drop=["ALL"])
            tmpfs = service.get("tmpfs") or []
            if not isinstance(tmpfs, list) or any(not isinstance(mount, str) for mount in tmpfs):
                raise HTTPException(422, f"Service {name} tmpfs must be a list of strings.")
            paths = {mount.split(":", 1)[0] for mount in tmpfs}
            for path, limits in (("/tmp", "64m"), ("/run", "16m")):
                if path not in paths:
                    tmpfs.append(f"{path}:rw,nosuid,nodev,size={limits}")
            service["tmpfs"] = tmpfs
        service["security_opt"] = [option for option in options if not option.startswith("no-new-privileges")] + ["no-new-privileges:true"]
        limit = service.get("pids_limit", 256)
        if type(limit) is not int or limit <= 0:
            raise HTTPException(422, f"Service {name} requires a positive numeric pids_limit.")
        service["pids_limit"] = limit
        service["x-yachtplus-security"] = profile
        document["services"][name] = service
    return yaml.safe_dump(document, sort_keys=False)
