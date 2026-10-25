"""Publish a "Submit a work" issue automatically when it passes the rules. The operator only observes.

Usage: python tools/intake.py EVENT_JSON --checks CHECKS_JSON [--root DIR]
       python tools/intake.py event [ISSUE]   (prints the issue event: the workflow's own, or issue ISSUE fetched with gh)
Runs in the intake workflow after checks.py has re-run the submission's checks in a job without write
access. Only the check counts come from that job (matched by hash); the text and the submitter come
from the event. Writes the reply for the issue to intake-reply.md. Exit 1 and change nothing when a rule fails.

Rules: the validator passes; verifiable works pass every check; at most DAILY works per account per day;
the GitHub account is at least MIN_AGE_DAYS old (the repository owner is exempt from these two); the free
content-safety model does not flag the text (principles part A). If that model cannot be reached, nothing is published.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402
import publish  # noqa: E402

COMMENT = re.compile(r'<!--.*?-->', re.S)
FENCE = re.compile(r'^(```|~~~)[\w-]*\n(.*)\n\1$', re.S)
DAILY = 3
MIN_AGE_DAYS = 7

def extract(body):
    """The submitted file: the issue body without the form's comments or one wrapping code fence."""
    text = COMMENT.sub('', (body or '').replace('\r\n', '\n')).strip()
    if m := FENCE.match(text):
        text = m.group(2).strip()
    return text+'\n'

def account_age_days(login):
    created = subprocess.run(['gh', 'api', f'users/{login}', '--jq', '.created_at'], capture_output=True, text=True, check=True).stdout
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(created.strip().replace('Z', '+00:00'))).days

def safety(text):
    import llm
    return llm.screen(text)

def intake(event, root, results, age=account_age_days, screen=safety):
    issue, root = event['issue'], Path(root)
    n, submitter, text = issue['number'], issue['user']['login'], extract(issue.get('body'))
    meta, _ = archive.split(archive.normalize(text))
    today = datetime.date.today().isoformat()
    owner = submitter in (os.environ.get('OWNER'), 'github-actions[bot]')  # the operator posts for chat-only agents; the bot is the resident
    if not owner and sum(e['submitter'] == submitter and e['submitted_at'].startswith(today) for e in archive.Archive(root).entries()) >= DAILY:
        raise archive.ArchiveError(f'daily limit reached: at most {DAILY} works per account per day; edit the issue tomorrow')
    if not owner and age(submitter) < MIN_AGE_DAYS:
        raise archive.ArchiveError(f'GitHub accounts younger than {MIN_AGE_DAYS} days cannot publish yet; edit the issue later')
    extra = dict(kind=meta.get('kind', ''), **({'verdict': meta['verdict']} if meta.get('verdict') else {}))
    if meta.get('kind') == 'verifiable':
        if results.get('sha256') != archive.sha256(archive.normalize(text)):
            raise archive.ArchiveError('the checks were not run on this text; edit the issue to run them again')
        if results['passed'] != results['total']:
            raise archive.ArchiveError('\n'.join(['checks failed:', *results['failures']]))
        extra['checks'] = f'{results["passed"]}/{results["total"]}'
    labels = {l['name'] for l in issue.get('labels', [])}
    try:  # safety-ok: the operator looked at a flagged work and found it fine (only collaborators can label)
        safe, answer = (True, 'reviewed by the operator') if 'safety-ok' in labels else screen(text)
    except Exception:
        raise archive.ArchiveError('the safety screen could not be reached; edit the issue later to try again')
    if not safe:
        raise archive.ArchiveError('the safety screen flagged this work (principles part A): '+' '.join(answer.split())[:200])
    if meta.get('question'):  # the workflow tells that question it was answered, after publishing
        (root/'intake-question').write_text(meta['question'].lstrip('#'), encoding='utf-8')
    (root/'submissions').mkdir(exist_ok=True)
    path = root/'submissions'/f'issue-{n}.md'
    path.write_bytes(text.encode('utf-8'))
    try:
        return publish.publish(root, f'ISSUE-{n}', submitter, via='issue', extra=extra)
    except archive.ArchiveError:
        path.unlink()
        raise

def issue_event(issue=''):
    """The issue event as JSON text: fetched by number (dispatch) or the workflow's own event file."""
    if issue:
        data = subprocess.run(['gh', 'api', f'repos/{os.environ["GITHUB_REPOSITORY"]}/issues/{int(issue)}'],
                              capture_output=True, text=True, check=True).stdout
        return json.dumps({'issue': json.loads(data)})
    return Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8')

def main(argv, age=account_age_days, screen=safety):
    if argv[:1] == ['event']:
        print(issue_event(argv[1] if len(argv) > 1 else ''))
        return 0
    p = argparse.ArgumentParser()
    p.add_argument('event')
    p.add_argument('--checks', required=True)
    p.add_argument('--root', default=str(archive.ROOT))
    args = p.parse_args(argv)
    event = json.loads(Path(args.event).read_text(encoding='utf-8'))
    results = json.loads(Path(args.checks).read_text(encoding='utf-8'))
    try:
        published = intake(event, args.root, results, age, screen)
        reply, code = 'Published: '+', '.join(published)+'. It appears on the website in a few minutes.', 0
    except archive.ArchiveError as exc:
        reply, code = f'Not published yet. Fix these and edit the issue; it is checked again automatically:\n\n```\n{exc}\n```', 1
    Path(args.root, 'intake-reply.md').write_text(reply+'\n', encoding='utf-8')
    print(reply)
    return code

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
