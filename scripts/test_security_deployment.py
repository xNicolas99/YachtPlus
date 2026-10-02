"""Deployment privilege boundaries and fail2ban action/readiness regressions."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(loaded)
    return loaded


state_action = module('state_action', ROOT / 'fail2ban/state_action.py')
sys.modules['state_action'] = state_action
supervise = module('fail2ban_supervise', ROOT / 'fail2ban/supervise.py')
nginx_configuration = module('nginx_configuration', ROOT / 'backend/configure_nginx.py')
security_smoke = module('security_stack_smoke', ROOT / 'scripts/security-stack-smoke.py')


class DeploymentTests(unittest.TestCase):
    def test_both_deployments_require_unprivileged_healthy_fail2ban(self):
        for filename in ['docker-compose.yml', 'docker-compose.example.yml']:
            with self.subTest(filename=filename):
                deployment = yaml.safe_load((ROOT / filename).read_text(encoding='utf-8'))
                services = deployment['services']
                app = services['yachtplus']
                guard = services['fail2ban']
                for name, role in [('yachtplus', 'application'), ('dockerproxy', 'docker-proxy'), ('fail2ban', 'fail2ban')]:
                    self.assertEqual(services[name]['labels']['local.yachtplus.infrastructure'], role)
                self.assertEqual(app['user'], '1000:1000')
                self.assertEqual(guard['user'], '1001:1000')
                self.assertEqual(app['environment']['YACHT_FAIL2BAN_REQUIRED'], 'true')
                self.assertEqual(app['depends_on']['fail2ban']['condition'], 'service_healthy')
                for service in [app, guard]:
                    self.assertEqual(service['cap_drop'], ['ALL'])
                    self.assertNotIn('cap_add', service)
                    self.assertTrue(service['read_only'])
                    self.assertIn('no-new-privileges:true', service['security_opt'])
                    self.assertFalse(any('docker.sock' in mount for mount in service['volumes']))
                self.assertEqual(guard['network_mode'], 'none')
                self.assertNotIn('ports', guard)
                self.assertIn('yacht_security_logs:/config/security:ro', guard['volumes'])
                self.assertIn('yacht_security_state:/run/yachtplus-security:ro', app['volumes'])
                self.assertTrue(deployment['networks']['docker_api']['internal'])
                self.assertEqual(services['dockerproxy']['networks'], ['docker_api'])
                self.assertEqual(set(app['networks']), {'docker_api', 'app_egress'})
                proxy = services['dockerproxy']
                self.assertTrue(proxy['read_only'])
                self.assertIn('/run:noexec,nosuid,nodev,size=1m,mode=0755', proxy['tmpfs'])

    def test_final_image_user_and_forwarding_cannot_bypass_peer_checks(self):
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertEqual([line for line in dockerfile.splitlines() if line.startswith('USER ')][-1], 'USER 1000:1000')
        self.assertIn('ENV YACHT_FAIL2BAN_REQUIRED="true"', dockerfile)
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertIn('python scripts/security-stack-smoke.py --image "$candidate" --timeout 600', workflow)
        entrypoint = (ROOT / 'backend/start.sh').read_text(encoding='utf-8')
        for script in ['backend/start.sh', 'scripts/image-smoke-test.sh']:
            self.assertNotIn(b'\r', (ROOT / script).read_bytes())
        self.assertNotIn('chown ', entrypoint)
        self.assertNotIn('gosu ', entrypoint)
        self.assertIn('--bind 127.0.0.1:8000', entrypoint)
        self.assertIn("--forwarded-allow-ips=''", entrypoint)
        nginx = (ROOT / 'nginx.conf').read_text(encoding='utf-8')
        self.assertIn('auth_request /_yacht_access;', nginx)
        self.assertIn('location = /internal/access { deny all; }', nginx)
        self.assertIn('proxy_set_header X-Real-IP $remote_addr;', nginx)
        self.assertNotIn('$proxy_add_x_forwarded_for', nginx)
        self.assertIn('geo $realip_remote_addr $trusted_http_proxy', nginx)


class Fail2banStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name)
        self.patchers = [patch.object(state_action, 'STATE', self.state), patch.object(supervise, 'STATE', self.state)]
        for patcher in self.patchers:
            patcher.start()
        state_action.action(['start'])

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()
        self.temporary.cleanup()

    def test_real_action_canonicalizes_ipv4_mapped_and_ipv6_and_unbans(self):
        for address, filename in [('::ffff:192.168.1.10', '192.168.1.10.json'), ('2001:0db8::10', '2001_db8__10.json')]:
            with self.subTest(address=address):
                with patch.object(state_action.time, 'time', return_value=1000):
                    state_action.action(['ban', address, '3600'])
                destination = self.state / 'bans' / filename
                self.assertEqual(json.loads(destination.read_text(encoding='utf-8')), {'expires_at': 4600})
                state_action.action(['unban', address])
                self.assertFalse(destination.exists())
        self.assertEqual(list(self.state.glob('bans/.state-*')), [])

    def test_rejects_path_shell_ip_and_nonfinite_duration(self):
        for address in ['../ready', '1.2.3.4; touch /tmp/evil', '192.168.1.1\nfake']:
            with self.assertRaises(ValueError):
                state_action.action(['ban', address, '3600'])
        for duration in ['nan', 'inf', '-1', '0']:
            with self.assertRaises(ValueError):
                state_action.action(['ban', '192.168.1.1', duration])
        self.assertEqual(list((self.state / 'bans').iterdir()), [])

    def test_restored_ticket_preserves_original_expiration(self):
        state_action.action(['ban', '192.168.1.1', '3600', '1000'])
        self.assertEqual(json.loads((self.state / 'bans/192.168.1.1.json').read_text(encoding='utf-8')), {'expires_at': 4600})

    @unittest.skipIf(os.name == 'nt', 'POSIX ownership and umask are exercised on Linux')
    def test_start_repairs_private_ban_directory_under_fail2ban_umask(self):
        bans = self.state / 'bans'
        bans.rmdir()
        previous = os.umask(0o077)
        try:
            # A fresh volume must allow another UID to search ban filenames.
            state_action.action(['start'])
            self.assertEqual(stat.S_IMODE(bans.stat().st_mode), 0o755)
            # Existing private state from an older image is repaired as well.
            for mode in (0o700, 0o770):
                bans.chmod(mode)
                state_action.action(['start'])
                self.assertEqual(stat.S_IMODE(bans.stat().st_mode), 0o755)
            state_action.action(['ban', '192.168.1.10', '3600'])
            self.assertEqual(stat.S_IMODE(state_action.ban_path('192.168.1.10').stat().st_mode), 0o644)
            # Fail2ban's private database keeps its restrictive mode.
            private = self.state / 'fail2ban.sqlite3'
            private.write_bytes(b'private database fixture')
            state_action.action(['start'])
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
        finally:
            os.umask(previous)

    def test_health_requires_fresh_state_real_jail_and_expected_action(self):
        def client(*arguments):
            if arguments == ('get', 'yachtplus', 'banip'):
                return ''
            if arguments == ('get', 'yachtplus', 'actions'):
                return 'yachtplus-state'
            if arguments == ('get', 'yachtplus', 'action', 'yachtplus-state', 'actionban'):
                return 'python3 /opt/yachtplus/state_action.py ban <ip> <bantime>'
            return 'Status for the jail: yachtplus'

        state_action.atomic_json(self.state / 'ready.json', {'timestamp': time.time(), 'status': 'ready'})
        with patch.object(supervise, 'client', side_effect=client):
            supervise.healthcheck()
        def missing_ban_client(*arguments):
            if arguments == ('get', 'yachtplus', 'banip'):
                return '192.168.1.19'
            return client(*arguments)
        with patch.object(supervise, 'client', side_effect=missing_ban_client):
            with self.assertRaises(OSError):
                supervise.healthcheck()
        with patch.object(supervise, 'client', side_effect=subprocess.CalledProcessError(1, 'fail2ban-client')):
            with self.assertRaises(subprocess.SubprocessError):
                supervise.healthcheck()
        with patch.object(supervise, 'client', return_value='iptables-allports'):
            with self.assertRaises(RuntimeError):
                supervise.healthcheck()
        for timestamp in [time.time() - 31, time.time() + 10]:
            state_action.atomic_json(self.state / 'ready.json', {'timestamp': timestamp, 'status': 'ready'})
            with self.assertRaises(RuntimeError):
                supervise.healthcheck()

    def test_failed_action_check_and_missing_state_never_healthy(self):
        (self.state / 'action-ready.json').unlink()
        with self.assertRaises(OSError):
            state_action.action(['check'])
        with self.assertRaises(OSError):
            supervise.healthcheck()


class ProxyConfigurationTests(unittest.TestCase):
    def test_only_ip_networks_can_become_nginx_directives(self):
        real_ip, geo = nginx_configuration.proxy_configuration('10.1.2.3,2001:db8::/32')
        self.assertIn('set_real_ip_from 10.1.2.3/32;', real_ip)
        self.assertIn('2001:db8::/32 1;', geo)
        self.assertEqual(nginx_configuration.proxy_configuration(''), ('', ''))
        for value in ['proxy.example.org', '10.0.0.0/8; allow all;', '10.0.0.1\ninclude evil;']:
            with self.assertRaises(ValueError):
                nginx_configuration.proxy_configuration(value)


class SecuritySmokeTests(unittest.TestCase):
    def test_startup_diagnostics_reports_reader_modes_without_container_environment(self):
        stack = security_smoke.Stack()
        inspected = [{
            'Config': {'Labels': {'com.docker.compose.project': stack.project,
                                  'com.docker.compose.service': 'yachtplus'},
                       'Env': ['SECRET_KEY=must-never-print']},
            'State': {'Status': 'running', 'ExitCode': 0,
                      'Health': {'Status': 'unhealthy', 'Log': [{'Output': 'HTTP 503'}]}},
        }]
        def compose(*arguments, **options):
            return 'test-container' if arguments[0] == 'ps' else '{"uid":1000,"paths":{"bans":{"mode":"0o700"}}}'
        with patch.object(stack, 'compose', side_effect=compose), \
                patch.object(stack, 'command', return_value=json.dumps(inspected)), \
                patch.object(security_smoke, 'print') as output:
            stack.startup_diagnostics()
        messages = '\n'.join(str(call.args[0]) for call in output.call_args_list)
        self.assertIn('unhealthy', messages)
        self.assertIn('HTTP 503', messages)
        self.assertIn('0o700', messages)
        self.assertNotIn('must-never-print', messages)
        stack.temporary.cleanup()

    def test_http_failure_is_preserved_and_connection_closes_on_timeout(self):
        connection = unittest.mock.Mock()
        response = connection.getresponse.return_value
        response.status = 503
        response.read.return_value = b'Protection unavailable'
        with patch.object(security_smoke.http.client, 'HTTPConnection', return_value=connection):
            self.assertEqual(security_smoke.probe('localhost', 8080)['status'], 503)
            connection.close.assert_called_once()
            connection.reset_mock()
            connection.getresponse.side_effect = TimeoutError('No response')
            with self.assertRaises(TimeoutError):
                security_smoke.probe('localhost', 8080)
            connection.close.assert_called_once()

    def test_poll_timeout_fails_instead_of_treating_failure_as_success(self):
        with patch.object(security_smoke.time, 'monotonic', side_effect=[0, 0, 2]), patch.object(security_smoke.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Timed out waiting for real jail'):
                security_smoke.wait_for('real jail', lambda: False, timeout=1)

    def test_cleanup_refuses_other_project_and_still_runs_after_log_failure(self):
        stack = security_smoke.Stack()
        stack.config = {'name': stack.project, 'volumes': {'config': {'name': stack.project + '_config'}}}
        stack.compose_file.write_text('{}', encoding='utf-8')
        calls = []

        def compose(*arguments, **options):
            calls.append(arguments)
            if arguments[0] == 'logs':
                raise RuntimeError('Logs unavailable')
            return ''

        with patch.object(stack, 'compose', side_effect=compose):
            stack.cleanup()
        self.assertTrue(any(arguments[0] == 'down' for arguments in calls))
        other = security_smoke.Stack()
        other.config = {'name': 'production'}
        other.compose_file.write_text('{}', encoding='utf-8')
        with patch.object(other, 'compose', return_value='') as mocked:
            with self.assertRaisesRegex(RuntimeError, 'non-test project'):
                other.cleanup()
        self.assertFalse(any(call.args[0] == 'down' for call in mocked.call_args_list))


if __name__ == '__main__':
    unittest.main()
