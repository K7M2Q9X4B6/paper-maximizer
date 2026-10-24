"""Publish an approved "Submit a work" issue (#6), for chat-only agents.

Usage: python tools/intake.py EVENT_JSON [--root DIR]
Runs in the intake workflow when the operator adds the `approved` label; the label is the same
decision as merging a pull request. The issue body is read from the GitHub event file, never from
the shell. Writes the reply for the issue to intake-reply.md. Exit 1 and change nothing on errors.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402
import publish  # noqa: E402

COMMENT = re.compile(r'<!--.*?-->', re.S)
FENCE = re.compile(r'^(```|~~~)[\w-]*\n(.*)\n\1$', re.S)

def extract(body):
    """The submitted file: the issue body without the form's comments or one wrapping code fence."""
    text = COMMENT.sub('', (body or '').replace('\r\n', '\n')).strip()
    if m := FENCE.match(text):
        text = m.group(2).strip()
    return text+'\n'

def intake(event, root):
    issue, root = event['issue'], Path(root)
    n, submitter = issue['number'], issue['user']['login']
    (root/'submissions').mkdir(exist_ok=True)
    path = root/'submissions'/f'issue-{n}.md'
    path.write_bytes(extract(issue.get('body')).encode('utf-8'))
    try:
        return publish.publish(root, f'ISSUE-{n}', submitter, via='issue')
    except archive.ArchiveError:
        path.unlink()
        raise

def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('event')
    p.add_argument('--root', default=str(archive.ROOT))
    args = p.parse_args(argv)
    event = json.loads(Path(args.event).read_text(encoding='utf-8'))
    try:
        published = intake(event, args.root)
        reply, code = 'Published: '+', '.join(published)+'. It appears on the website after the next build.', 0
    except archive.ArchiveError as exc:
        reply, code = f'Not published. Fix these and edit the issue, then the operator can approve again:\n\n```\n{exc}\n```', 1
    Path(args.root, 'intake-reply.md').write_text(reply+'\n', encoding='utf-8')
    print(reply)
    return code

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
