"""Fail closed readiness heartbeat for the real fail2ban yachtplus jail."""

import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

from state_action import STATE, action, atomic_json, ban_path


def client(*arguments: str) -> str:
    return subprocess.check_output(
        ['fail2ban-client', '-s', '/tmp/fail2ban.sock', *arguments],
        timeout=4, text=True, stderr=subprocess.STDOUT,
    )


def verify_jail() -> None:
    client('status', 'yachtplus')
    actions = client('get', 'yachtplus', 'actions')
    if 'yachtplus-state' not in actions:
        raise RuntimeError('Required yachtplus-state action is not installed')
    configured = client('get', 'yachtplus', 'action', 'yachtplus-state', 'actionban')
    if '/opt/yachtplus/state_action.py ban' not in configured:
        raise RuntimeError('Unexpected fail2ban ban action')
    action(['check'])
    for address in client('get', 'yachtplus', 'banip').split():
        expires = json.loads(ban_path(address).read_text())['expires_at']
        if not isinstance(expires, (float, int)) or not math.isfinite(expires) or expires <= time.time():
            raise RuntimeError('A fail2ban ban is not enforced by the application state')


def healthcheck() -> None:
    ready = json.loads((STATE / 'ready.json').read_text())
    timestamp = ready['timestamp']
    age = time.time() - timestamp
    if ready.get('status') != 'ready' or not 0 <= age <= 30:
        raise RuntimeError('Fail2ban readiness is missing or stale')
    verify_jail()


def run() -> None:
    ready = STATE / 'ready.json'
    ready.unlink(missing_ok=True)
    (STATE / 'action-ready.json').unlink(missing_ok=True)
    daemon = subprocess.Popen([
        'fail2ban-server', '-f', '-s', '/tmp/fail2ban.sock',
        '-p', '/tmp/fail2ban.pid', '-c', '/etc/fail2ban',
    ])
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True
        try:
            ready.unlink(missing_ok=True)
        finally:
            if daemon.poll() is None:
                daemon.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    deadline = time.monotonic() + 30
    try:
        while daemon.poll() is None and not stopping:
            try:
                verify_jail()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                ready.unlink(missing_ok=True)
                if time.monotonic() >= deadline:
                    raise RuntimeError('Fail2ban jail/action failed readiness validation')
                time.sleep(1)
                continue
            atomic_json(ready, {'timestamp': time.time(), 'status': 'ready'})
            deadline = time.monotonic() + 10
            time.sleep(5)
        if not stopping:
            raise RuntimeError(f'Fail2ban exited with status {daemon.returncode}')
    finally:
        try:
            ready.unlink(missing_ok=True)
        finally:
            if daemon.poll() is None:
                daemon.terminate()
            try:
                daemon.wait(timeout=10)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait()


if __name__ == '__main__':
    if '--healthcheck' in sys.argv:
        healthcheck()
    else:
        run()
