#!/usr/bin/env python3
"""Exercise the production nginx/backend/fail2ban stack on a real Docker host.

Requires Docker Engine and Compose; missing prerequisites are failures. Every
run uses a randomly named Compose project and fresh volumes, and cleans up only
resources carrying that project's label. --image reuses a candidate app image.
"""

import argparse
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
LAN = '192.168.45.17'
PUBLIC = '8.8.8.8'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def wait_for(description, check, timeout=60, interval=1):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            last_error = str(exc)
        time.sleep(interval)
    suffix = f': {last_error}' if last_error else ''
    raise RuntimeError(f'Timed out waiting for {description}{suffix}')


def probe(host, port, path='/', headers=None, method='GET', body=None):
    connection = http.client.HTTPConnection(host, port, timeout=8)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        data = response.read(2 * 1024 * 1024)
        return {'status': response.status, 'body': data.decode('utf-8', errors='replace')}
    finally:
        connection.close()


class Stack:
    def __init__(self, image=None, timeout=600):
        self.project = 'yachtplus-security-smoke-' + uuid.uuid4().hex[:12]
        self.image = image
        self.deadline = time.monotonic() + timeout
        self.environment = dict(os.environ, COMPOSE_PROJECT_NAME=self.project)
        self.temporary = tempfile.TemporaryDirectory(prefix=self.project + '-')
        self.compose_file = Path(self.temporary.name) / 'compose.json'
        self.config = None
        self.container_ids = {}

    def command(self, arguments, capture=True, timeout=120, cleanup=False):
        remaining = timeout if cleanup else min(timeout, self.deadline - time.monotonic())
        require(remaining > 0, 'Security stack smoke exceeded its total timeout')
        result = subprocess.run(
            ['docker', *arguments], cwd=ROOT, env=self.environment,
            text=True, stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None, timeout=remaining,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or '').strip()[-4000:]
            raise RuntimeError(f'Docker command failed ({result.returncode}): {" ".join(arguments)}\n{detail}')
        return result.stdout or ''

    def compose(self, *arguments, **options):
        return self.command(['compose', '--project-name', self.project, '-f', str(self.compose_file), *arguments], **options)

    def initialize(self):
        require(shutil.which('docker') is not None, 'Docker CLI is required; this check cannot be skipped')
        self.command(['version'])
        self.command(['compose', 'version'])
        # Materialize Compose's resolved configuration rather than relying on
        # list-merge behavior for ports. This replaces the production binding
        # with one random loopback port and isolates every named volume.
        rendered = self.command(['compose', '--project-name', self.project, '-f', str(ROOT / 'docker-compose.yml'), 'config', '--format', 'json'])
        self.config = json.loads(rendered)
        require(self.config.get('name') == self.project, 'Compose resolved an unexpected project name')
        app = self.config['services']['yachtplus']
        app['ports'] = [{'target': 8080, 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]
        app['environment']['YACHT_HTTP_TRUSTED_PROXIES'] = '127.0.0.1/32'
        if self.image:
            app['image'] = self.image
            app.pop('build', None)
        for name, volume in self.config.get('volumes', {}).items():
            require(not volume.get('external'), 'Smoke tests refuse external volumes')
            volume['name'] = self.project + '_' + name
        network = self.config['networks']['docker_api']
        require(network['name'] == self.project + '_docker_api', 'Docker API network is not isolated to the test project')
        require(app['environment']['YACHT_DOCKER_PROXY_NETWORK'] == network['name'], 'Worker proxy network does not match the isolated network')
        self.compose_file.write_text(json.dumps(self.config), encoding='utf-8')
        self.compose('build', *(['fail2ban'] if self.image else ['yachtplus', 'fail2ban']), capture=False, timeout=600)
        self.compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180', capture=False, timeout=200)
        for service in ['yachtplus', 'fail2ban', 'dockerproxy']:
            identifier = self.compose('ps', '-q', service).strip()
            require(identifier, f'Missing {service} container')
            inspected = json.loads(self.command(['inspect', identifier]))[0]
            require(inspected['Config']['Labels']['com.docker.compose.project'] == self.project, 'Container escaped test project ownership')
            self.container_ids[service] = identifier

    def python(self, source, service='yachtplus'):
        executable = 'python3' if service == 'fail2ban' else 'python'
        return self.compose('exec', '-T', service, executable, '-c', source)

    def forwarded_probe(self, source, path='/', method='GET', body=None, upgrade=False, cookie=False):
        headers = {'Host': 'localhost', 'X-Forwarded-For': source}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if upgrade:
            headers.update({'Upgrade': 'websocket', 'Connection': 'Upgrade', 'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': 'c2VjdXJpdHktc21va2UtMQ=='})
        if cookie:
            headers['Cookie'] = 'access_token_cookie=security-smoke-invalid-token'
        payload = json.dumps(body) if body is not None else None
        code = (
            'import http.client,json; c=http.client.HTTPConnection("127.0.0.1",8080,timeout=8); '
            f'c.request({method!r},{path!r},body={payload!r},headers={headers!r}); '
            'r=c.getresponse(); print(json.dumps({"status":r.status,"body":r.read(2097152).decode("utf-8",errors="replace")})); c.close()'
        )
        return json.loads(self.python(code))

    def expect(self, source, path, expected, **options):
        result = self.forwarded_probe(source, path, **options)
        accepted = expected if isinstance(expected, tuple) else (expected,)
        require(result['status'] in accepted, f'{source} {path}: expected {accepted}, received {result["status"]}: {result["body"][:200]}')
        return result

    def jail(self, *arguments):
        return self.compose('exec', '-T', 'fail2ban', 'fail2ban-client', '-s', '/tmp/fail2ban.sock', *arguments)

    def healthy(self):
        data = json.loads(self.command(['inspect', self.container_ids['fail2ban']]))[0]
        return data['State'].get('Health', {}).get('Status') == 'healthy'

    def wait(self, description, check, timeout=60):
        remaining = min(timeout, self.deadline - time.monotonic())
        require(remaining > 0, 'Security stack smoke exceeded its total timeout')
        wait_for(description, check, timeout=remaining)

    def assert_banned(self, address):
        require(address in self.jail('get', 'yachtplus', 'banip').split(), f'{address} is not banned by the real jail')
        filename = str(ipaddress.ip_address(address)).replace(':', '_') + '.json'
        state = json.loads(self.python(f'from pathlib import Path; print(Path("/run/yachtplus-security/bans/{filename}").read_text())'))
        require(state['expires_at'] > time.time(), 'Persisted ban has already expired')
        for path, options in [('/', {}), ('/api/setup/status', {}), ('/api/containers/smoke/exec', {'upgrade': True, 'cookie': True})]:
            self.expect(address, path, 403, **options)
        return state['expires_at']

    def policy(self, enabled):
        # Fixture setup through the same atomic writer used by the admin API.
        # Admin permission/confirmation checks are covered by backend tests.
        self.python(f'from api.utils.access_policy import write_access_policy; write_access_policy({enabled!r})')

    def verify_boundaries(self):
        for service, uid in [('yachtplus', '1000'), ('fail2ban', '1001')]:
            data = json.loads(self.command(['inspect', self.container_ids[service]]))[0]
            require(data['Config']['User'].split(':')[0] == uid, f'{service} configured user is root')
            require(self.compose('exec', '-T', service, 'id', '-u').strip() == uid, f'{service} actual process UID is wrong')
            host = data['HostConfig']
            require(host['CapDrop'] == ['ALL'] and not host.get('CapAdd'), f'{service} has unexpected capabilities')
            require(host['ReadonlyRootfs'], f'{service} root filesystem is writable')
            require(any(option in ('no-new-privileges', 'no-new-privileges:true') for option in host['SecurityOpt']), f'{service} can gain privileges')
            require(not any('docker.sock' in mount['Destination'] for mount in data['Mounts']), f'{service} received a Docker socket')
        guard = json.loads(self.command(['inspect', self.container_ids['fail2ban']]))[0]
        require(guard['HostConfig']['NetworkMode'] == 'none', 'Fail2ban has network access')
        proxy = json.loads(self.command(['inspect', self.container_ids['dockerproxy']]))[0]
        require(set(proxy['NetworkSettings']['Networks']) == {self.project + '_docker_api'}, 'Docker proxy is reachable outside its internal network')
        require(not proxy['HostConfig'].get('PortBindings'), 'Docker proxy published a host port')
        sockets = [mount for mount in proxy['Mounts'] if mount['Destination'] == '/var/run/docker.sock']
        require(len(sockets) == 1 and not sockets[0]['RW'], 'Proxy does not own the intended single read-only Docker socket mount')
        # Seeded log file is readable to the sidecar and writable to the app.
        self.python('import os,stat; p="/config/security/auth.log"; s=os.stat(p); assert s.st_uid==1000 and s.st_gid==1000 and stat.S_IMODE(s.st_mode)==0o640; assert os.access(p,os.W_OK); assert not os.path.exists("/var/run/docker.sock")')
        self.python('from pathlib import Path; assert Path("/config/security/auth.log").read_text()==""', service='fail2ban')
        self.jail('status', 'yachtplus')
        require('yachtplus-state' in self.jail('get', 'yachtplus', 'actions'), 'Real fail2ban jail has no state enforcement action')
        self.python('from api.utils.access_policy import fail2ban_active; assert fail2ban_active()')
        app = json.loads(self.command(['inspect', self.container_ids['yachtplus']]))[0]
        require(not next(mount['RW'] for mount in app['Mounts'] if mount['Destination'] == '/run/yachtplus-security'), 'Application can mutate fail2ban protection state')
        addresses = [network['IPAddress'] for network in app['NetworkSettings']['Networks'].values()]
        self.python('import socket\n' + '\n'.join(f's=socket.socket(); s.settimeout(3); assert s.connect_ex(({address!r},8000))!=0, "Backend exposed on sibling network"; s.close()' for address in addresses))

    def run_cases(self):
        self.verify_boundaries()
        self.expect(LAN, '/', 200)
        self.expect(LAN, '/api/setup/status', 200)
        for path, options in [('/', {}), ('/api/setup/status', {}), ('/api/containers/smoke/exec', {'upgrade': True})]:
            self.expect(PUBLIC, path, 403, **options)
        require(self.forwarded_probe(LAN, '/internal/access')['status'] == 403, 'Internal access gate is externally reachable')

        # Real login failures must reach the jail through application logging.
        username = 'smoke_username_' + uuid.uuid4().hex
        for _ in range(5):
            self.expect(LAN, '/api/auth/login_cookie', 400, method='POST', body={'username': username, 'password': 'Invalid-Smoke-Password!42'})
        log = self.python('from pathlib import Path; print(Path("/config/security/auth.log").read_text())')
        require(username not in log and 'Invalid-Smoke-Password' not in log, 'Authentication log leaked supplied credentials')
        require(log.count(f'yachtplus-auth failure ip={LAN}') == 5, 'Five real authentication failures were not logged')
        self.wait('real failed-login ban', lambda: LAN in self.jail('get', 'yachtplus', 'banip').split(), timeout=45)
        self.assert_banned(LAN)
        self.jail('set', 'yachtplus', 'unbanip', LAN)
        self.wait('LAN unban', lambda: self.forwarded_probe(LAN)['status'] == 200, timeout=20)

        self.policy(True)
        self.expect(PUBLIC, '/', 200)
        self.jail('set', 'yachtplus', 'banip', PUBLIC)
        self.wait('public ban enforcement', lambda: self.forwarded_probe(PUBLIC)['status'] == 403, timeout=20)
        self.assert_banned(PUBLIC)
        self.jail('set', 'yachtplus', 'unbanip', PUBLIC)
        self.wait('public unban', lambda: self.forwarded_probe(PUBLIC)['status'] == 200, timeout=20)
        self.policy(False)
        self.expect(PUBLIC, '/', 403)

        # External clients are not in the trusted proxy allowlist. Their XFF
        # cannot change their actual peer IP, even to evade a peer's ban.
        port = self.compose('port', 'yachtplus', '8080').strip().rsplit(':', 1)[1]
        marker = uuid.uuid4().hex
        path = '/?security-smoke=' + marker
        require(probe('127.0.0.1', int(port), path, headers={'Host': 'localhost', 'X-Forwarded-For': PUBLIC})['status'] == 200, 'Untrusted XFF changed external peer attribution')
        output = self.command(['logs', '--tail', '100', self.container_ids['yachtplus']])
        match = re.search(r'([0-9a-fA-F:.]+) - - \[[^\]]+\] "GET /\?security-smoke=' + marker, output)
        require(match is not None, 'Could not verify actual external TCP peer from nginx access log')
        actual_peer = str(ipaddress.ip_address(match.group(1)))
        require(actual_peer not in (PUBLIC, '127.0.0.1'), 'External test traffic did not cross the untrusted container boundary')
        self.jail('set', 'yachtplus', 'banip', actual_peer)
        self.wait('external peer ban', lambda: probe('127.0.0.1', int(port), headers={'Host': 'localhost', 'X-Forwarded-For': '192.168.45.19'})['status'] == 403, timeout=20)
        self.jail('set', 'yachtplus', 'unbanip', actual_peer)

        self.jail('set', 'yachtplus', 'banip', LAN)
        self.wait('pre-restart ban', lambda: self.forwarded_probe(LAN)['status'] == 403, timeout=20)
        original_expiration = self.assert_banned(LAN)
        self.compose('restart', 'fail2ban', capture=False)
        self.wait('fail2ban restart readiness', self.healthy, timeout=90)
        restored_expiration = self.assert_banned(LAN)
        require(abs(restored_expiration - original_expiration) <= 1, 'Restart extended or lost the persisted ban expiration')
        self.jail('set', 'yachtplus', 'unbanip', LAN)
        self.wait('post-restart unban', lambda: self.forwarded_probe(LAN)['status'] == 200, timeout=20)
        self.compose('stop', 'fail2ban', capture=False)
        self.wait('fail-closed protection loss', lambda: self.forwarded_probe(LAN)['status'] in (500, 503), timeout=35)
        self.expect(LAN, '/', (500, 503))
        self.compose('start', 'fail2ban', capture=False)
        self.wait('protection recovery', self.healthy, timeout=90)
        self.expect(LAN, '/', 200)

    def cleanup(self):
        try:
            if self.compose_file.exists():
                try:
                    self.compose('logs', '--no-color', '--tail', '200', capture=False, cleanup=True, timeout=30)
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    print(f'Could not collect security stack logs: {exc}', file=sys.stderr)
                require(self.config.get('name') == self.project and self.project.startswith('yachtplus-security-smoke-'), 'Refusing cleanup of a non-test project')
                for volume in self.config.get('volumes', {}).values():
                    require(not volume.get('external') and volume['name'].startswith(self.project + '_'), 'Refusing cleanup of a non-test volume')
                for identifier in self.compose('ps', '-a', '-q', cleanup=True).split():
                    data = json.loads(self.command(['inspect', identifier], cleanup=True))[0]
                    require(data['Config']['Labels'].get('com.docker.compose.project') == self.project, 'Refusing cleanup of another project container')
                self.compose('down', '--volumes', '--remove-orphans', capture=False, cleanup=True, timeout=90)
        finally:
            self.temporary.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', help='Use an existing application image; still build the fail2ban sidecar')
    parser.add_argument('--timeout', type=int, default=600, help='Overall timeout in seconds (default: 600)')
    arguments = parser.parse_args()
    require(arguments.timeout > 0, 'Timeout must be positive')
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt('Security stack smoke interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    stack = Stack(arguments.image, arguments.timeout)
    result = 0
    try:
        stack.initialize()
        stack.run_cases()
        print('Security stack smoke passed: real fail2ban, LAN/public gates, proxy attribution, non-root isolation and protection recovery.')
    except (OSError, RuntimeError, ValueError, KeyboardInterrupt, subprocess.SubprocessError) as exc:
        print(f'Security stack smoke FAILED: {exc}', file=sys.stderr)
        result = 1
    finally:
        try:
            stack.cleanup()
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            print(f'Security stack cleanup FAILED: {exc}', file=sys.stderr)
            result = 1
    return result


if __name__ == '__main__':
    raise SystemExit(main())
