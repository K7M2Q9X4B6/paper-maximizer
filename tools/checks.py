"""Machine verification: re-run a work's checks. A check is a ```check block of Python (standard
library only) that must exit without error within 10 seconds. Verified = every check passes.

Usage: python tools/checks.py FILE.md        (anyone can re-run a published work's checks)
       python tools/checks.py --event EVENT  (intake workflow: checks of a submission issue, as JSON)
Checks are untrusted code: run them only where there is no write token and no secret.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402

BLOCK = re.compile(r'^```check[ \t]*\n(.*?)^```[ \t]*$', re.S | re.M)
SECONDS = 10

def blocks(text):
    return BLOCK.findall(text)

def run(code):
    """(passed, message) for one check, in a fresh interpreter with an empty environment."""
    env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT') if k in os.environ}
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r = subprocess.run([sys.executable, '-I', '-c', code], cwd=tmp, env=env, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=SECONDS)
        except subprocess.TimeoutExpired:
            return False, f'took longer than {SECONDS} seconds'
    return r.returncode == 0, (r.stderr.strip().splitlines() or [''])[-1][:200]

def check(text):
    results = [run(code) for code in blocks(text)]
    return dict(sha256=archive.sha256(archive.normalize(text)), passed=sum(ok for ok, _ in results), total=len(results),
                failures=[f'check {i}: {msg}' for i, (ok, msg) in enumerate(results, 1) if not ok])

def main(argv):
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
