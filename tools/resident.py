"""The resident agent: one small verifiable work per run, written by a free model, submitted like anyone else's.

Usage: python tools/resident.py write > work.md   (needs the API-key secrets; runs no generated code)
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

def campfire(root=archive.ROOT):
    """The library's latest Campfire question as (target, title), or None."""
    for e in reversed(archive.Archive(root).entries()):
        meta, _ = archive.split((root/e['file']).read_bytes())
        if meta.get('form', '').lower() in ('campfire', 'big question'):
            return f'{e["work_id"]}@{e["version"]}', e['title']
    return None

def write(root=archive.ROOT):
    """The first writer model that answers with a valid work wins; models come and go."""
    failures = []
    for provider, model in llm.MODELS['writer']:
        try:
            return draft(provider, model, root)
        except (OSError, ValueError) as exc:  # unreachable, rate-limited or invalid output
            failures.append(f'{model}: {exc}')
    raise SystemExit('no writer model produced a valid work:\n' + '\n'.join(failures))

def draft(provider, model, root):
    big = campfire(root)
    titles = '; '.join(e['title'] for e in archive.Archive(root).entries()[-30:]) or 'none yet'
    prompt = PROMPT.format(name=NAME, model=model.split(':')[0], titles=titles,
                           topic=f' to the Campfire question "{big[1]}"' if big else '',
                           relation=f'\nrelations: contribution {big[0]}' if big else '')
    for _ in range(2):
        text = re.sub(r'^```\w*\n|\n```\s*$', '', llm.call(provider, model, prompt, max_tokens=6000).strip()) + '\n'
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
    if sys.argv[1:2] == ['write']:
        sys.stdout.write(write())
    elif sys.argv[1:2] == ['submit']:
        submit(sys.argv[2])
    else:
        print(__doc__)
