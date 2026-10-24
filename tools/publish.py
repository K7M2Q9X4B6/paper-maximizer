"""Publish merged submissions: each submissions/*.md becomes works/Wxxxx/vN.md with a catalog entry.

Usage: python tools/publish.py --run-id PR-12 --submitter <github-login> [--root DIR]
Runs in the publish workflow after a merge to main. Validates again (direct pushes skip the PR check),
then archives every file and removes it from submissions/. Exit 1 and change nothing if any file fails.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402
import validate  # noqa: E402

def publish(root, run_id, submitter, via='pull-request'):
    root = Path(root)
    store = archive.Archive(root)
    files = sorted((root/'submissions').glob('*.md'))
    known = validate.catalog(root)
    problems = [f'{f.name}: {e}' for f in files for e in validate.check(f, known)[0]]
    if problems:
        raise archive.ArchiveError('\n'.join(problems))
    published = []
    for f in files:
        meta, _ = archive.split(archive.normalize(f.read_bytes()))
        entry = store.submit(f.read_bytes(), run_id, meta.get('work') or None, via=via, submitter=submitter)
        f.unlink()
        published.append(f'{entry["work_id"]}@{entry["version"]} {entry["title"]}')
    return published

def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('--run-id', required=True)
    p.add_argument('--submitter', required=True)
    p.add_argument('--root', default=str(archive.ROOT))
    args = p.parse_args(argv)
    try:
        published = publish(args.root, args.run_id, args.submitter)
    except archive.ArchiveError as exc:
        print(f'not published:\n{exc}')
        return 1
    print('\n'.join(f'published {w}' for w in published) or 'nothing to publish')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
