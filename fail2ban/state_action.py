"""Fail2ban's application deny action; no firewall or Docker privileges."""

import ipaddress
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

STATE = Path(os.environ.get('YACHT_FAIL2BAN_STATE_DIR', '/run/yachtplus-security'))


def atomic_json(path: Path, value: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix='.state-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def ban_path(value: str) -> Path:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return STATE / 'bans' / (str(address).replace(':', '_') + '.json')


def action(arguments: list[str]) -> None:
    operation = arguments[0]
    if operation == 'start':
        bans = STATE / 'bans'
        bans.mkdir(mode=0o755, exist_ok=True)
        # Fail2ban starts actions with umask 077. Set the exact directory mode
        # after creation (and repair older volumes), so the separate UID 1000
        # application can traverse its read-only mount. Only UID 1001 writes.
        bans.chmod(0o755)
        atomic_json(STATE / 'action-ready.json', {'status': 'ready'})
    elif operation == 'stop':
        (STATE / 'action-ready.json').unlink(missing_ok=True)
    elif operation == 'check':
        if json.loads((STATE / 'action-ready.json').read_text()) != {'status': 'ready'}:
            raise ValueError('Fail2ban state action is not initialized')
        # Actually test the action's writable filesystem, not just permissions.
        descriptor, temporary = tempfile.mkstemp(prefix='.check-', dir=STATE / 'bans')
        os.close(descriptor)
        Path(temporary).unlink()
    elif operation == 'ban':
        duration = float(arguments[2])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Ban duration must be a finite positive number')
        started = float(arguments[3]) if len(arguments) > 3 else time.time()
        if not math.isfinite(started) or started < 0:
            raise ValueError('Ban timestamp must be a finite positive number')
        # Restored fail2ban tickets retain their original time, so a restart
        # cannot silently extend a ban beyond its configured expiration.
        atomic_json(ban_path(arguments[1]), {'expires_at': started + duration})
    elif operation == 'unban':
        ban_path(arguments[1]).unlink(missing_ok=True)
    else:
        raise ValueError('Unknown action')


if __name__ == '__main__':
    action(sys.argv[1:])
