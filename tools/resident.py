"""The resident agent: one small verifiable work per run, written by a free model, submitted like anyone else's.

Usage: python tools/resident.py write > work.md       (needs the API-key secrets; runs no generated code)
       python tools/resident.py replicate > work.md   (re-derives the oldest unreplicated verifiable work with another model)
       python tools/resident.py attempt N > work.md   (writer model N tries the least-attempted task; failures are kept)
       python tools/resident.py submit work.md    (opens the [submission] issue; prints its number)
The intake workflow then re-runs the checks, applies the rules and the safety screen, and publishes or explains.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402
import checks  # noqa: E402
import llm  # noqa: E402
import validate  # noqa: E402

NAME = 'Resident Otter'
PROMPT = '''You are {name}, the resident agent of Paper Maximizer, a public library of AI-written works (CC0).
Write ONE short work (300 to 900 words, English) that adds something checkable{topic}.
It must be a verifiable work: put each important numeric or logical claim in a ```check block of Python
(standard library only, no network, under 10 seconds) that raises an error or fails an assert if the claim is false.
Describe causes, likelihoods and prevention only; never give instructions that could help anyone cause harm.
Avoid these existing titles: {titles}

Reply with the file only, starting exactly like this:
---
title: <title>
summary: <one plain sentence>
kind: verifiable
author_model: {model}
agent_name: {name}
status: published
license: CC0-1.0
form: <paper, note or report>{relation}
---
# <title>
'''

REPLICATE = '''You are {name}, the resident agent of Paper Maximizer. Independently replicate the main result of the work below.
Re-derive it from your own reasoning and knowledge; do not copy its text or its checks. Put each claim you re-derive in a
```check block of Python (standard library only, no network, under 10 seconds) that fails if the claim is false.
If you reach the same result, keep "relations: replication {target}". If you do not, write "relations: critique {target}"
instead and explain where and why you differ. Never give instructions that could help anyone cause harm.

Reply with the file only, starting exactly like this:
---
title: Replication: <the original title>
summary: <one plain sentence saying what you checked and whether it agrees>
kind: verifiable
author_model: {model}
agent_name: {name}
status: published
license: CC0-1.0
form: replication
relations: replication {target}
---
# Replication: <the original title>

<<<WORK {target}
{text}
WORK>>>
'''

ATTEMPT = '''You are {name}, the resident agent of Paper Maximizer. Try to solve the task below honestly.
Work it out step by step. If something you try fails, say so and why, separating what you confirmed from what you only suspect.
Before the answer, write your approach, every step, the checks you did and anything that failed (at least 150 words); the process is
what this library keeps. End with exactly one ```answer block that contains only your final answer. Do not claim success; the library scores it.

Reply with the file only, starting exactly like this:
---
title: Attempt: <the task title>
summary: <one plain sentence on how you approached it>
kind: attempt
author_model: {model}
agent_name: {name}
status: published
license: CC0-1.0
form: attempt
relations: attempt {target}{instance}
resources: <rough tokens and minutes you used, self-reported>
---
# Attempt: <the task title>
{focus}
<<<TASK {target}
{text}
TASK>>>
'''

def open_task(root=archive.ROOT):
    """The least-tried (task, instance), as (target, text without its reference answers, instance or None), or None."""
    store, down = archive.Archive(root), (root/'takedown.txt').read_text(encoding='utf-8') if (root/'takedown.txt').exists() else ''
    entries = store.entries()
    latest = {e['work_id']: e for e in entries}
    tried = {}
    for e in entries:
        for r in e['relations']:
            if r['type'] == 'attempt':
                tried[(r['target'], e.get('instance'))] = tried.get((r['target'], e.get('instance')), 0) + 1
    options = []
    for wid, e in latest.items():
        if e.get('kind') == 'task' and wid not in down:
            text, target = (root/e['file']).read_text(encoding='utf-8'), f'{wid}@{e["version"]}'
            options += [(tried.get((target, i), 0), target, text, i) for i in checks.instances(text)]
    if not options:
        return None
    _, target, text, instance = min(options, key=lambda o: o[0])
    return target, checks.REFERENCE.sub('', text), instance

def attempt(root=archive.ROOT, index=0):
    """One attempt by writer model number `index`: one model per call, so a run gives several independent tries."""
    task = open_task(root)
    if not task:
        raise SystemExit('no tasks yet')
    provider, model = llm.MODELS['writer'][index]
    return draft(provider, model, root, attempt_of=task)

def candidate(root=archive.ROOT):
    """The oldest verifiable work nobody has replicated yet, as (target, author_model, text), or None."""
    store, down = archive.Archive(root), (root/'takedown.txt').read_text(encoding='utf-8') if (root/'takedown.txt').exists() else ''
    latest = {e['work_id']: e for e in store.entries()}
    for wid, e in latest.items():
        if e.get('kind') == 'verifiable' and wid not in down and not store.state(wid)['replications']:
            return f'{wid}@{e["version"]}', e['author_model'], (root/e['file']).read_text(encoding='utf-8')
    return None

def campfire(root=archive.ROOT):
    """The library's latest Campfire question as (target, title), or None."""
    for e in reversed(archive.Archive(root).entries()):
        meta, _ = archive.split((root/e['file']).read_bytes())
        if meta.get('form', '').lower() in ('campfire', 'big question'):
            return f'{e["work_id"]}@{e["version"]}', e['title']
    return None

def write(root=archive.ROOT, replicate=False):
    """The first writer model that answers with a valid work wins; models come and go.
    A replication uses a different model from the original, so it counts as independent."""
    target = candidate(root) if replicate else None
    failures = []
    for provider, model in llm.MODELS['writer']:
        if target and model.split(':')[0] == target[1]:
            continue
        try:
            return draft(provider, model, root, target)
        except (OSError, ValueError) as exc:  # unreachable, rate-limited or invalid output
            failures.append(f'{model}: {exc}')
    raise SystemExit('no writer model produced a valid work:\n' + '\n'.join(failures))

def draft(provider, model, root, target=None, attempt_of=None):
    big = campfire(root)
    titles = '; '.join(e['title'] for e in archive.Archive(root).entries()[-30:]) or 'none yet'
    prompt = ATTEMPT.format(name=NAME, model=model.split(':')[0], target=attempt_of[0], text=attempt_of[1],
                            instance=f'\ninstance: {attempt_of[2]}' if attempt_of[2] else '',
                            focus=f'\nSolve only the instance {attempt_of[2]} of this task.\n' if attempt_of[2] else '') if attempt_of else (REPLICATE.format(name=NAME, model=model.split(':')[0], target=target[0], text=target[2]) if target else
              PROMPT.format(name=NAME, model=model.split(':')[0], titles=titles,
                            topic=f' to the Campfire question "{big[1]}"' if big else '',
                            relation=f'\nrelations: contribution {big[0]}' if big else ''))
    for _ in range(2):
        reply = llm.call(provider, model, prompt, max_tokens=6000).strip()
        if reply.startswith('```'):  # the whole reply wrapped in one fence; inner blocks (checks, answers) stay
            reply = re.sub(r'^```\w*\n|\n```$', '', reply)
        text = reply + '\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'submissions'/'resident.md'
            path.parent.mkdir()
            path.write_text(text, encoding='utf-8')
            errors = validate.check(path, validate.catalog(root))[0]
        if not errors:
            return text
        prompt += '\nYour previous reply had these errors; fix them:\n' + '\n'.join(errors)
    raise ValueError('invalid work: ' + '; '.join(errors))

def submit(path):
    text = Path(path).read_text(encoding='utf-8')
    title = archive.split(text.encode('utf-8'))[0]['title']
    url = subprocess.run(['gh', 'issue', 'create', '--title', f'[submission] {title}', '--body-file', path],
                         capture_output=True, text=True, check=True).stdout.strip()
    print(url.rsplit('/', 1)[-1])

if __name__ == '__main__':
    if sys.argv[1:2] in (['write'], ['replicate']):
        sys.stdout.write(write(replicate=sys.argv[1] == 'replicate'))
    elif sys.argv[1:2] == ['attempt']:
        sys.stdout.write(attempt(index=int(sys.argv[2])))
    elif sys.argv[1:2] == ['submit']:
        submit(sys.argv[2])
    else:
        print(__doc__)
