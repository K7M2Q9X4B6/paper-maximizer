"""Machine verification: re-run a work's checks, validate a task's verifier, score an attempt. A check is a ```check block of Python (standard
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
FENCED = lambda name: re.compile(rf'^```{name}[ \t]*\n(.*?)^```[ \t]*$', re.S | re.M)
VERIFY, REFERENCE, ANSWER = FENCED('verify'), FENCED('reference'), FENCED('answer')
TRIVIAL = ('', '0')  # a task's verifier must reject these
SECONDS = 10
IMAGE = 'python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704'

def blocks(text):
    return BLOCK.findall(text)

def run(code):
    status, message = _execute(code)
    return status == 0, message

def _execute(code):
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
        return r.returncode, '' if r.returncode == 0 else f'check container exited with code {r.returncode}'
    except subprocess.TimeoutExpired:
        return None, f'took longer than {SECONDS} seconds'
    except OSError:
        return None, 'Docker unavailable; install/start Docker and run tools/checks.py --pull'
    finally:
        try:
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass

MAX_INSTANCES = 20

def instances(text):
    """A task template's parameter values ('instances: 3x10; 3x12'), or [None] for a single problem."""
    meta = archive.split(archive.normalize(text))[0]
    return [i.strip() for i in meta.get('instances', '').split(';') if i.strip()] or [None]

def references(text):
    """{instance: reference answer}. A template's reference block has one 'instance: answer' line per instance."""
    ref = REFERENCE.findall(text)[0].strip()
    if instances(text) == [None]:
        return {None: ref}
    return {k.strip(): v.strip() for k, _, v in (line.partition(':') for line in ref.splitlines()) if v}

def judge(verify_code, answer, instance=None):
    """True or False from the task's verify(answer[, instance]), or None if it errors or runs too long."""
    args = repr(answer) if instance is None else f'{answer!r}, {instance!r}'
    code = verify_code + f'\nimport sys\nsys.exit(0 if verify({args}) else 3)'
    status, _ = _execute(code)
    return {0: True, 3: False}.get(status)

def task_problems(text):
    """Why a task is not yet usable: its reference must pass, trivial answers fail, reruns agree."""
    verify, reference = VERIFY.findall(text), REFERENCE.findall(text)
    if len(verify) != 1 or len(reference) != 1:
        return ['a task needs exactly one verify block and one reference block']
    names, refs, problems = instances(text), references(text), []
    if len(names) > MAX_INSTANCES:
        return [f'at most {MAX_INSTANCES} instances per task']
    for name in names:  # each instance is its own problem: same checks for every one
        at = '' if name is None else f' (instance {name})'
        if name not in refs:
            problems.append(f'no reference answer for instance {name}')
            continue
        first, second = judge(verify[0], refs[name], name), judge(verify[0], refs[name], name)
        if first is not True:
            problems.append(f'the reference answer does not pass verify{at}')
        if first != second:
            problems.append(f'verify gives different results on reruns{at}')
        problems += [f'verify does not reject the trivial answer {t!r}{at}' for t in TRIVIAL if judge(verify[0], t, name) is not False]
    return problems

def attempt_result(text, root=archive.ROOT):
    """pass, fail or error: the target task's verifier run on the attempt's answer."""
    meta, _ = archive.split(archive.normalize(text))
    targets = [r['target'] for r in archive.relations(meta.get('relations', '')) if r['type'] == 'attempt']
    answers = ANSWER.findall(text)
    files = {f'{e["work_id"]}@{e["version"]}': e['file'] for e in archive.Archive(root).entries()}
    if len(targets) != 1 or len(answers) != 1 or targets[0] not in files:
        return 'error'
    task = (Path(root)/files[targets[0]]).read_text(encoding='utf-8')
    verify, instance = VERIFY.findall(task), meta.get('instance') or None
    if instance not in instances(task):  # a template needs one of its instances; a single problem needs none
        return 'error'
    verdict = judge(verify[0], answers[0].strip(), instance) if len(verify) == 1 else None
    return {True: 'pass', False: 'fail'}.get(verdict, 'error')

def check(text, root=archive.ROOT):
    results = [run(code) for code in blocks(text)]
    kind = archive.split(archive.normalize(text))[0].get('kind') if text.startswith('---') else ''
    return dict(sha256=archive.sha256(archive.normalize(text)), passed=sum(ok for ok, _ in results), total=len(results),
                failures=[f'check {i}: {msg}' for i, (ok, msg) in enumerate(results, 1) if not ok],
                **({'task_problems': task_problems(text)} if kind == 'task' else {}),
                **({'result': attempt_result(text, root)} if kind == 'attempt' else {}))

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
