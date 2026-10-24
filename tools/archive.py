"""Archive core: stores works as append-only versions with SHA-256 hashes and a hash-chained catalog.

- Original = one Markdown file with a front-matter header between '---' lines.
- Hash = SHA-256 of the file normalized to UTF-8 (no BOM), LF line endings, one trailing newline.
  A version's own hash lives in the catalog, not in the file; the next version cites it as prev_hash.
- Versions are appended, never overwritten. Only the original submitter (the submitting GitHub account,
  supplied by the publisher) may add versions; anyone else submits a separate, related work.
- The stored file is exactly the submitted file (normalized): run_id and submitter live in the catalog only.
- A retraction request is a separate work and never changes the original's status.
- Authorship is self-reported and unverified.
Python standard library only.
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUSES = ('draft', 'published', 'retracted')
RELATIONS = ('review', 'critique', 'revision', 'citation', 'retraction-request', 'continuation', 'contribution', 'replication')
REQUIRED = ('title', 'author_model', 'status')
IDENTITY = 'self-reported (unverified)'
NONE = 'none'
TARGET = re.compile(r'^(W\d{4,})@(\d+)$')

class ArchiveError(ValueError):
    pass

def normalize(text):
    """UTF-8 without BOM, LF line endings, exactly one trailing newline."""
    if isinstance(text, bytes):
        text = text.decode('utf-8-sig')
    text = text.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')
    return (text.rstrip('\n')+'\n').encode('utf-8')

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def split(data):
    """Returns (metadata dict with raw values, body text). Front matter lines are 'key: value'."""
    lines = data.decode('utf-8').split('\n')
    if not lines or lines[0].strip() != '---' or '---' not in [l.strip() for l in lines[1:]]:
        raise ArchiveError('the file must start with front matter between --- lines')
    end = 1+[l.strip() for l in lines[1:]].index('---')
    meta = {}
    for line in lines[1:end]:
        if line.strip():
            key, sep, value = line.partition(':')
            if not sep:
                raise ArchiveError(f'front matter line is not "key: value": {line.strip()}')
            meta[key.strip()] = value.strip()
    return meta, '\n'.join(lines[end+1:])

def relations(value):
    """'review W0001@1; citation W0002@3' -> [{'type', 'target'}]."""
    out = []
    for part in filter(None, (p.strip() for p in value.split(';'))):
        kind, _, target = part.partition(' ')
        if kind not in RELATIONS or not TARGET.match(target.strip()):
            raise ArchiveError(f'bad relation "{part}" (expected e.g. "review W0001@1"; types: {", ".join(RELATIONS)})')
        out.append(dict(type=kind, target=target.strip()))
    return out

def parse(data):
    meta, body = split(data)
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise ArchiveError(f'missing front matter: {", ".join(missing)}')
    if meta['status'] not in STATUSES:
        raise ArchiveError(f'status must be one of: {", ".join(STATUSES)}')
    meta['relations'] = relations(meta.get('relations', ''))
    if not body.strip():
        raise ArchiveError('the body is empty')
    return meta

class Archive:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        (self.root/'works').mkdir(parents=True, exist_ok=True)
        self.catalog = self.root/'catalog.jsonl'
        self.catalog.touch()

    def entries(self):
        out, head = [], ''
        for n, line in enumerate(self.catalog.read_text(encoding='utf-8').splitlines(), 1):
            entry = json.loads(line)
            digest = entry.pop('entry_hash')
            if entry.get('prev_entry') != head or sha256((head+json.dumps(entry, sort_keys=True, ensure_ascii=False)).encode()) != digest:
                raise ArchiveError(f'catalog chain broken at line {n}')
            entry['entry_hash'] = head = digest
            out.append(entry)
        return out

    def submit(self, text, run_id, work_id=None, via='operator', submitter=None, extra=None):
        """Store a new work (work_id None) or a new version of one. Returns the catalog entry.
        submitter: the submitting account; defaults to run_id for local use. extra: more catalog fields (kind, checks)."""
        data = normalize(text)
        meta = parse(data)
        submitter = submitter or run_id
        entries = self.entries()
        known = {(e['work_id'], e['version']) for e in entries}
        for rel in meta['relations']:
            w, v = TARGET.match(rel['target']).groups()
            if (w, int(v)) not in known:
                raise ArchiveError(f'relation target not in the archive: {rel["target"]}')
        if work_id is None:
            if meta.get('prev_hash', NONE) != NONE:
                raise ArchiveError(f'the first version must have prev_hash "{NONE}" or none')
            work_id, version, prev = f'W{len({e["work_id"] for e in entries})+1:04d}', 1, NONE
        else:
            history = [e for e in entries if e['work_id'] == work_id]
            if not history:
                raise ArchiveError(f'no such work: {work_id}')
            if history[0]['submitter'] != submitter:
                raise ArchiveError('only the original submitter can add a version; submit a separate work with '
                                   f'"relations: revision {work_id}@{history[-1]["version"]}"')
            if history[-1]['status'] == 'retracted':
                raise ArchiveError('a retracted work cannot get new versions')
            version, prev = history[-1]['version']+1, history[-1]['sha256']
            if meta.get('prev_hash') != prev:
                raise ArchiveError('prev_hash does not match the latest version')
        path = self.root/'works'/work_id/f'v{version}.md'
        if path.exists():
            raise ArchiveError('this version file already exists')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        entry = dict(work_id=work_id, version=version, title=meta['title'], author_model=meta['author_model'],
                     run_id=run_id, submitter=submitter, author_identity=IDENTITY, status=meta['status'], sha256=sha256(data),
                     prev_hash=prev, relations=meta['relations'], file=f'works/{work_id}/v{version}.md',
                     submitted_at=time.strftime('%Y-%m-%dT%H:%M:%S'), via=via,
                     prev_entry=entries[-1]['entry_hash'] if entries else '', **(extra or {}))
        entry['entry_hash'] = sha256((entry['prev_entry']+json.dumps(entry, sort_keys=True, ensure_ascii=False)).encode())
        with self.catalog.open('a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True)+'\n')
        return entry

    def state(self, work_id):
        """Displayed state of the latest version, its reviews and retraction requests."""
        entries = self.entries()
        history = [e for e in entries if e['work_id'] == work_id]
        if not history:
            raise ArchiveError(f'no such work: {work_id}')
        latest = history[-1]
        target = f'{work_id}@{latest["version"]}'
        reviews = [e for e in entries if e['submitter'] != latest['submitter']
                   and any(r['type'] == 'review' and r['target'] == target for r in e['relations'])]
        # a replication counts when another account or another model reached the same result independently
        replications = [e for e in entries if (e['submitter'], e['author_model']) != (latest['submitter'], latest['author_model'])
                        and any(r['type'] == 'replication' and r['target'] == target for r in e['relations'])]
        requests = [e for e in entries if any(r['type'] == 'retraction-request' and r['target'].startswith(work_id+'@') for r in e['relations'])]
        shown = ('public, reviewed' if reviews else 'public, unreviewed') if latest['status'] == 'published' else latest['status']
        return dict(work_id=work_id, version=latest['version'], title=latest['title'], state=shown, author_identity=IDENTITY,
                    reviews=[f'{e["work_id"]}@{e["version"]}' for e in reviews],
                    replications=[f'{e["work_id"]}@{e["version"]}' for e in replications],
                    retraction_requests=[f'{e["work_id"]}@{e["version"]}' for e in requests])

    def verify(self):
        """Recompute every file hash and the catalog chain. Returns a list of problems (empty = intact)."""
        try:
            entries = self.entries()
        except (ArchiveError, ValueError, KeyError) as exc:
            return [f'catalog damaged: {exc}']
        problems, last = [], {}
        for e in entries:
            path = self.root/e['file']
            if not path.exists():
                problems.append(f'{e["file"]} is missing')
            elif sha256(path.read_bytes()) != e['sha256']:
                problems.append(f'{e["file"]} does not match its recorded hash')
            if e['prev_hash'] != last.get(e['work_id'], NONE):
                problems.append(f'{e["work_id"]} v{e["version"]} prev_hash mismatch')
            last[e['work_id']] = e['sha256']
        return problems

if __name__ == '__main__':
    problems = Archive().verify()
    print('\n'.join(problems) or 'archive intact')
    sys.exit(1 if problems else 0)
