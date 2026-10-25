"""Machine verification: re-run a work's checks. A check is a ```check block of Python (standard
library only) that must exit without error within 10 seconds. Verified = every check passes.

Usage: python tools/checks.py FILE.md        (anyone can re-run a published work's checks)
       python tools/checks.py --event EVENT  (intake workflow: checks of a submission issue, as JSON)
Checks require Docker with Linux containers. Prepare the pinned image with --pull.
Submitted code has no network, host mounts, credentials, or access to the result artifact.
"""
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402

BLOCK = re.compile(r'^```check[ \t]*\n(.*?)^```[ \t]*$', re.S | re.M)
SECONDS = 10
IMAGE = 'python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704'

def blocks(text):
    return BLOCK.findall(text)

def run(code):
    """A disposable, resource-limited container; never fall back to host execution."""
    name = 'paper-check-' + uuid.uuid4().hex
    command = ['docker', 'run', '--rm', '-i', '--pull=never', '--name', name,
               '--network=none', '--read-only', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--user=65534:65534',
               '--pids-limit=32', '--memory=128m', '--memory-swap=128m', '--cpus=1',
               '--log-driver=none', '--tmpfs=/tmp:rw,noexec,nosuid,size=16m', '--workdir=/tmp',
               IMAGE, 'python', '-I', '-']
    try:
        r = subprocess.run(command, input=code, text=True, encoding='utf-8',
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=SECONDS)
        return r.returncode == 0, '' if r.returncode == 0 else f'check container exited with code {r.returncode}'
    except subprocess.TimeoutExpired:
        return False, f'took longer than {SECONDS} seconds'
    except OSError:
        return False, 'Docker unavailable; install/start Docker and run tools/checks.py --pull'
    finally:
        try:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass

def check(text):
    results = [run(code) for code in blocks(text)]
    return dict(sha256=archive.sha256(archive.normalize(text)), passed=sum(ok for ok, _ in results), total=len(results),
                failures=[f'check {i}: {msg}' for i, (ok, msg) in enumerate(results, 1) if not ok])

def main(argv):
    if argv == ['--pull']:
        subprocess.run(['docker', 'pull', IMAGE], check=True)
        return 0
    if argv[:1] == ['--event']:
        import intake
        event = json.loads(Path(argv[1]).read_text(encoding='utf-8'))
        print(json.dumps(check(intake.extract(event['issue'].get('body')))))
        return 0
    result = check(Path(argv[0]).read_text(encoding='utf-8'))
    print(f'{result["passed"]} of {result["total"]} checks passed', *result['failures'], sep='\n')
    return 0 if result['passed'] == result['total'] else 1

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
