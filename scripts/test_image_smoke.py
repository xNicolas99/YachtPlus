"""Execute the production secret-file guard with success and failure find results."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELL = shutil.which('sh') or shutil.which('bash')
if not SHELL and Path('C:/Program Files/Git/bin/bash.exe').is_file():
    SHELL = 'C:/Program Files/Git/bin/bash.exe'


@unittest.skipUnless(SHELL, 'POSIX shell required for release smoke tests')
class ImageSecretGuardTests(unittest.TestCase):
    def run_guard(self, output='', status=0):
        source = (ROOT / 'scripts/image-smoke-test.sh').read_text(encoding='utf-8')
        guard = source.split('echo "=== No packaged credentials or runtime databases ==="', 1)[1]
        guard = guard.split('echo "=== Backend import ==="', 1)[0]
        # Simulate find outcomes, including a filesystem error with no stdout.
        # The real guard must reject such errors instead of accepting an empty
        # failed command substitution as evidence of a clean image.
        command = 'find() { printf "%s" "$SMOKE_FIND_OUTPUT"; return "$SMOKE_FIND_STATUS"; };\n' + guard
        env = {**os.environ, 'SMOKE_FIND_OUTPUT': output, 'SMOKE_FIND_STATUS': str(status)}
        return subprocess.run([SHELL, '-eu', '-c', command], env=env, capture_output=True, timeout=10).returncode

    def test_clean_image_passes(self):
        self.assertEqual(self.run_guard(), 0)

    def test_packaged_signing_key_rejects_image(self):
        self.assertNotEqual(self.run_guard('/api/.secret_key'), 0)

    def test_packaged_encryption_salt_rejects_image(self):
        self.assertNotEqual(self.run_guard('/config/.fernet_salt'), 0)

    def test_packaged_credentials_reject_image(self):
        for filename in ['.env', '.env.local', '.env.production']:
            with self.subTest(filename=filename):
                self.assertNotEqual(self.run_guard('/api/nested/' + filename), 0)

    def test_packaged_database_rejects_image(self):
        for filename in ['yacht.db', 'yacht.db-wal', 'yacht.db-shm']:
            with self.subTest(filename=filename):
                self.assertNotEqual(self.run_guard('/api/' + filename), 0)

    def test_filesystem_error_without_output_rejects_image(self):
        self.assertNotEqual(self.run_guard(status=2), 0)


if __name__ == '__main__':
    unittest.main()
