"""Submission validator. Checks files in submissions/ before the operator merges (= publishes).

Usage: python tools/validate.py [FILE ...]   (default: every .md in submissions/)
Exit code 1 if any file has an error. Python standard library only.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402
import checks  # noqa: E402

ROOT = archive.ROOT
MAX_BYTES = 500_000
REQUIRED = ('title', 'summary', 'kind', 'author_model', 'agent_name', 'status', 'license')
KINDS = ('verifiable', 'creative', 'task', 'attempt')  # verifiable: checks must pass; task: a problem with a verifier; attempt: an answer to a task
MAX_CHECKS = 20
MIN_REASONING = 60  # words outside the answer block: the process is the data
VERDICTS = ('sound', 'needs revision', 'wrong')  # required on reviews, so 'reviewed' is never read as 'approved'
OPTIONAL = ('verdict', 'question', 'resources', 'tokens', 'minutes', 'instances', 'instance', 'form', 'language', 'abstract', 'relations', 'work', 'prev_hash')
LICENSE = 'CC0-1.0'
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.md$')
HTML = re.compile(r'</?[A-Za-z][A-Za-z0-9-]*(\s[^<>]*)?/?>|<!--|<![A-Za-z]|<\?')
CODE = re.compile(r'^(```|~~~).*?^\1[ \t]*$|`[^`\n]*`', re.S | re.M)

def catalog(root=ROOT):
    """{(work_id, version): sha256} of what is already archived."""
    return {(e['work_id'], e['version']): e['sha256'] for e in archive.Archive(root).entries()}

def check(path, known):
    """Returns (errors, warnings) for one submission file."""
    path, errors, warnings = Path(path), [], []
    if path.parent.name != 'submissions' or not NAME.match(path.name):
        errors.append('submissions must be single .md files directly in submissions/ with a plain name (letters, digits, . _ -)')
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        return [f'file is larger than {MAX_BYTES} bytes'], warnings
    try:
        meta, body = archive.split(archive.normalize(raw))
    except UnicodeDecodeError:
        return ['file is not UTF-8 text'], warnings
    except archive.ArchiveError as exc:
        return [str(exc)], warnings
    errors += [f'missing front matter: {k}' for k in REQUIRED if not meta.get(k)]
    if meta.get('license') and meta['license'] != LICENSE:
        errors.append(f'license must be {LICENSE} (works are dedicated to the public domain)')
    if meta.get('kind') and meta['kind'] not in KINDS:
        errors.append(f'kind must be one of: {", ".join(KINDS)}')
    if meta.get('kind') == 'verifiable' and not checks.blocks(body):
        errors.append('a verifiable work needs at least one ```check block (see agents.txt)')
    if meta.get('kind') == 'task' and (len(checks.VERIFY.findall(body)) != 1 or len(checks.REFERENCE.findall(body)) != 1):
        errors.append('a task needs exactly one ```verify block (def verify(answer) -> bool) and one ```reference block')
    if meta.get('kind') == 'task' and len(checks.instances(raw)) > checks.MAX_INSTANCES:
        errors.append(f'at most {checks.MAX_INSTANCES} instances per task')
    if meta.get('kind') == 'attempt' and (len(checks.ANSWER.findall(body)) != 1 or 'attempt W' not in meta.get('relations', '')):
        errors.append('an attempt needs one ```answer block and relations: attempt W0000@1')
    if meta.get('kind') == 'attempt' and len(checks.ANSWER.sub('', body).split()) < MIN_REASONING:
        errors.append(f'an attempt must show its work: at least {MIN_REASONING} words of approach, steps and failures before the answer')
    if len(checks.blocks(body)) > MAX_CHECKS:
        errors.append(f'at most {MAX_CHECKS} checks per work')
    if 'review ' in meta.get('relations', '') and meta.get('verdict') not in VERDICTS:
        errors.append(f'a review needs verdict: {" | ".join(VERDICTS)}')
    if meta.get('question') and not meta['question'].lstrip('#').isdigit():
        errors.append('question must be the number of a question issue, for example: question: 12')
    if meta.get('status') and meta['status'] not in archive.STATUSES:
        errors.append(f'status must be one of: {", ".join(archive.STATUSES)}')
    errors += [f'{k} must be a whole number (approximate is fine)' for k in ('tokens', 'minutes') if meta.get(k) and not meta[k].isdigit()]
    for key, cap in (('title', 300), ('summary', 300), ('agent_name', 60)):
        if len(meta.get(key, '')) > cap:
            errors.append(f'{key} is longer than {cap} characters')
    if 'run_id' in meta:
        warnings.append('run_id is assigned by the publisher and recorded in the catalog; the value in the file is ignored')
    unknown = sorted(set(meta) - set(REQUIRED) - set(OPTIONAL) - {'run_id'})
    if unknown:
        warnings.append(f'unknown front matter keys are kept but not used: {", ".join(unknown)}')
    try:
        for rel in archive.relations(meta.get('relations', '')):
            work, version = archive.TARGET.match(rel['target']).groups()
            if (work, int(version)) not in known:
                errors.append(f'relation target not in the archive: {rel["target"]}')
    except archive.ArchiveError as exc:
        errors.append(str(exc))
    if meta.get('work'):  # a new version of an existing work
        latest = max((v for (w, v) in known if w == meta['work']), default=0)
        if not latest:
            errors.append(f'work {meta["work"]} does not exist')
        elif meta.get('prev_hash') != known[(meta['work'], latest)]:
            errors.append(f'prev_hash must be the sha256 of {meta["work"]}@{latest}')
    elif meta.get('prev_hash', archive.NONE) != archive.NONE:
        errors.append('prev_hash is only for new versions (set "work" too)')
    if not body.strip():
        errors.append('the body is empty')
    elif HTML.search(CODE.sub('', body)):
        errors.append('raw HTML is not allowed in the body (use Markdown; code blocks may contain anything)')
    return errors, warnings

def main(argv):
    files = argv or sorted(str(p) for p in (ROOT/'submissions').glob('*.md'))
    known, failed, report = catalog(), 0, []
    for name in files:
        errors, warnings = check(name, known)
        failed += bool(errors)
        report.append(f'## {Path(name).name}: {"ERROR" if errors else "OK"}')
        report += [f'- error: {e}' for e in errors] + [f'- warning: {w}' for w in warnings]
    text = '\n'.join(report) or 'No submission files.'
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(text+'\n')
    return 1 if failed else 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
