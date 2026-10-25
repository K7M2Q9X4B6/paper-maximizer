import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import checks

class RunnerTests(unittest.TestCase):
    def test_only_container_receives_code_and_no_host_output_is_captured(self):
        with mock.patch.object(checks.subprocess, 'run', return_value=mock.Mock(returncode=0)) as run:
            self.assertEqual(checks.run('assert True'), (True, ''))
        command = run.call_args_list[0].args[0]
        for flag in ('--network=none', '--read-only', '--cap-drop=ALL', '--user=65534:65534',
                     '--security-opt=no-new-privileges', '--memory=128m', '--pids-limit=32'):
            self.assertIn(flag, command)
        self.assertNotIn('--volume', command)
        self.assertNotIn('--mount', command)
        self.assertEqual(command[-4:], [checks.IMAGE, 'python', '-I', '-'])
        kwargs = run.call_args_list[0].kwargs
        self.assertEqual(kwargs['input'], 'assert True')
        self.assertEqual(kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
        self.assertEqual(run.call_args_list[-1].args[0][:3], ['docker', 'rm', '-f'])

    def test_unavailable_sandbox_fails_closed_without_host_fallback(self):
        with mock.patch.object(checks.subprocess, 'run', side_effect=FileNotFoundError) as run:
            passed, message = checks.run('assert True')
        self.assertFalse(passed)
        self.assertIn('Docker unavailable', message)
        self.assertTrue(all(call.args[0][0] == 'docker' for call in run.call_args_list))

    def test_timeout_removes_the_whole_named_container(self):
        with mock.patch.object(checks.subprocess, 'run', side_effect=[
                subprocess.TimeoutExpired('docker', 10), mock.Mock(returncode=0)]) as run:
            self.assertFalse(checks.run('while True: pass')[0])
        command = run.call_args_list[0].args[0]
        name = command[command.index('--name')+1]
        self.assertEqual(run.call_args_list[1].args[0], ['docker', 'rm', '-f', name])

@unittest.skipUnless(shutil.which('docker'), 'Docker integration tests run in Linux CI')
class SandboxTests(unittest.TestCase):
    def test_no_host_files_network_or_root_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp)/'checks.json'
            marker.write_text('host-result', encoding='utf-8')
            code = f'''import os, socket
from pathlib import Path
assert "GH_TOKEN" not in os.environ
assert [name for _, name in socket.if_nameindex()] == ["lo"]
assert not Path({str(marker)!r}).exists()
try:
    Path({str(marker)!r}).write_text("forged")
except OSError:
    pass
else:
    raise AssertionError("host artifact was writable")
try:
    Path("/root-write-probe").write_text("probe")
except OSError:
    pass
else:
    raise AssertionError("root filesystem was writable")
s = socket.socket()
s.settimeout(0.2)
try:
    s.connect(("192.0.2.1", 443))
except OSError:
    pass
else:
    raise AssertionError("external network was reachable")
finally:
    s.close()
Path("/tmp/probe").write_text("temporary writes still work")
'''
            self.assertTrue(checks.run(code)[0])
            self.assertEqual(marker.read_text(encoding='utf-8'), 'host-result')

    def test_real_timeout(self):
        with mock.patch.object(checks, 'SECONDS', 1):
            passed, message = checks.run('while True: pass')
        self.assertFalse(passed)
        self.assertIn('longer than', message)

    def test_existing_archived_checks_still_pass(self):
        root = Path(__file__).resolve().parent.parent
        for line in (root/'catalog.jsonl').read_text(encoding='utf-8').splitlines():
            entry = json.loads(line)
            if entry.get('kind') == 'verifiable':
                with self.subTest(work=entry['file']):
                    result = checks.check((root/entry['file']).read_text(encoding='utf-8'))
                    self.assertEqual(result['passed'], result['total'])
                    self.assertEqual(f"{result['passed']}/{result['total']}", entry['checks'])

if __name__ == '__main__':
    unittest.main()
