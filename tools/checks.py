"""Machine verification: re-run a work's checks, validate a task's verifier, score an attempt. A check is a ```check block of Python (standard
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
FENCED = lambda name: re.compile(rf'^```{name}[ \t]*\n(.*?)^```[ \t]*$', re.S | re.M)
VERIFY, REFERENCE, ANSWER = FENCED('verify'), FENCED('reference'), FENCED('answer')
TRIVIAL = ('', '0')  # a task's verifier must reject these
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

def judge(verify_code, answer):
    """True or False from the task's verify(answer), or None if it errors or runs too long."""
    env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT') if k in os.environ}
    code = verify_code + '\nimport sys\nprint("VERDICT", bool(verify(sys.stdin.read())))'
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r = subprocess.run([sys.executable, '-I', '-c', code], input=answer, cwd=tmp, env=env, capture_output=True,
                               text=True, encoding='utf-8', errors='replace', timeout=SECONDS)
        except subprocess.TimeoutExpired:
            return None
    last = (r.stdout.strip().splitlines() or [''])[-1]
    return {'VERDICT True': True, 'VERDICT False': False}.get(last) if r.returncode == 0 else None

def task_problems(text):
    """Why a task is not yet usable: its reference must pass, trivial answers fail, reruns agree."""
    verify, reference = VERIFY.findall(text), REFERENCE.findall(text)
    if len(verify) != 1 or len(reference) != 1:
        return ['a task needs exactly one verify block and one reference block']
    problems, ref = [], reference[0].strip()
    first, second = judge(verify[0], ref), judge(verify[0], ref)
    if first is not True:
        problems.append('the reference answer does not pass verify')
    if first != second:
        problems.append('verify gives different results on reruns')
    problems += [f'verify does not reject the trivial answer {t!r}' for t in TRIVIAL if judge(verify[0], t) is not False]
    return problems

def attempt_result(text, root=archive.ROOT):
    """pass, fail or error: the target task's verifier run on the attempt's answer."""
    meta, _ = archive.split(archive.normalize(text))
    targets = [r['target'] for r in archive.relations(meta.get('relations', '')) if r['type'] == 'attempt']
    answers = ANSWER.findall(text)
    files = {f'{e["work_id"]}@{e["version"]}': e['file'] for e in archive.Archive(root).entries()}
    if len(targets) != 1 or len(answers) != 1 or targets[0] not in files:
        return 'error'
    verify = VERIFY.findall((Path(root)/files[targets[0]]).read_text(encoding='utf-8'))
    verdict = judge(verify[0], answers[0].strip()) if len(verify) == 1 else None
    return {True: 'pass', False: 'fail'}.get(verdict, 'error')

def check(text, root=archive.ROOT):
    results = [run(code) for code in blocks(text)]
    kind = archive.split(archive.normalize(text))[0].get('kind') if text.startswith('---') else ''
    return dict(sha256=archive.sha256(archive.normalize(text)), passed=sum(ok for ok, _ in results), total=len(results),
                failures=[f'check {i}: {msg}' for i, (ok, msg) in enumerate(results, 1) if not ok],
                **({'task_problems': task_problems(text)} if kind == 'task' else {}),
                **({'result': attempt_result(text, root)} if kind == 'attempt' else {}))

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
