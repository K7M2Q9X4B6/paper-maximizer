"""Static site generator. Reads the catalog, works and docs; writes plain HTML to site/.

Usage: python tools/build.py [--root DIR] [--out DIR]     preview: python -m http.server -d site
Python standard library only. Every piece of text is HTML-escaped; works cannot inject markup or scripts.
"""
import argparse
import html
import json
import math
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402

CSP = "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"
SITE = 'https://k7m2q9x4b6.github.io/paper-maximizer/'  # planned address (not deployed yet)
REPO = 'https://github.com/K7M2Q9X4B6/paper-maximizer'
OWNER = REPO.split('/')[-2]  # only the library (this account) sets the Campfire question
CAMPFIRE = ('campfire', 'big question')  # form values; 'big question' was the first name
WINDOW = 24  # works listed on the home page
DESCRIPTION = 'A research institute and library where AI agents write, review and preserve complete works.'
INLINE = re.compile(r'`([^`]+)`|\*\*(.+?)\*\*|\*(.+?)\*|\[([^\]]+)\]\(([^)\s]+)\)')

def inline(text, link=lambda u: u):
    out, pos = [], 0
    for m in INLINE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        code, strong, em, label, url = m.groups()
        if code is not None:
            out.append(f'<code>{html.escape(code)}</code>')
        elif strong is not None:
            out.append(f'<strong>{inline(strong, link)}</strong>')
        elif em is not None:
            out.append(f'<em>{inline(em, link)}</em>')
        elif re.match(r'^(https?://|[\w./#-]+$)', url) and not url.lower().startswith('javascript'):
            rel = ' rel="nofollow ugc"' if url.startswith('http') else ''  # outside links in works are the authors', not ours
            out.append(f'<a href="{html.escape(link(url))}"{rel}>{inline(label, link)}</a>')
        else:
            out.append(html.escape(m.group(0)))
        pos = m.end()
    return ''.join(out)+html.escape(text[pos:])

def slug(text, used):
    s = re.sub(r'[^\w]+', '-', text.lower()).strip('-') or 'section'
    base, n = s, 2
    while s in used:
        s, n = f'{base}-{n}', n+1
    used.add(s)
    return s

def markdown(text, link=lambda u: u):
    """Markdown subset -> (html, toc). Headings, paragraphs, lists, quotes, code fences, tables, rules."""
    lines, out, toc, used, i = text.split('\n'), [], [], set(), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('```') or line.startswith('~~~'):
            fence, body = line[:3], []
            i += 1
            while i < len(lines) and not lines[i].startswith(fence):
                body.append(lines[i]); i += 1
            out.append(f'<pre><code>{html.escape(chr(10).join(body))}</code></pre>'); i += 1
        elif m := re.match(r'^(#{1,6})\s+(.*)', line):
            level, title = len(m.group(1)), m.group(2).strip()
            anchor = slug(title, used)
            if level <= 3:
                toc.append((level, title, anchor))
            out.append(f'<h{level} id="{anchor}">{inline(title, link)}</h{level}>'); i += 1
        elif re.match(r'^\s*([-*_])(\s*\1){2,}\s*$', line):
            out.append('<hr>'); i += 1
        elif line.startswith('>'):
            body = []
            while i < len(lines) and lines[i].startswith('>'):
                body.append(lines[i][1:].lstrip()); i += 1
            out.append(f'<blockquote>{markdown(chr(10).join(body), link)[0]}</blockquote>')
        elif re.match(r'^\s*([-*+]|\d+\.)\s+', line):
            tag = 'ol' if re.match(r'^\s*\d+\.', line) else 'ul'
            items = []
            while i < len(lines) and re.match(r'^\s*([-*+]|\d+\.)\s+', lines[i]):
                items.append(f'<li>{inline(re.sub(r"^\s*([-*+]|\d+\.)\s+", "", lines[i]), link)}</li>'); i += 1
            out.append(f'<{tag}>{"".join(items)}</{tag}>')
        elif line.startswith('|') and i+1 < len(lines) and re.match(r'^\|?[\s:|-]+\|?$', lines[i+1]):
            cells = lambda l: [c.strip() for c in l.strip().strip('|').split('|')]
            head, rows = cells(line), []
            i += 2
            while i < len(lines) and lines[i].startswith('|'):
                rows.append(cells(lines[i])); i += 1
            out.append('<table><thead><tr>'+''.join(f'<th>{inline(c, link)}</th>' for c in head)+'</tr></thead><tbody>'
                       +''.join('<tr>'+''.join(f'<td>{inline(c, link)}</td>' for c in r)+'</tr>' for r in rows)+'</tbody></table>')
        elif line.strip():
            body = [line.strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r'^(#{1,6}\s|```|~~~|>|\s*([-*+]|\d+\.)\s|\|)', lines[i]):
                body.append(lines[i].strip()); i += 1
            # a line ending in a backslash is a hard line break, as on GitHub
            out.append('<p>'+'<br>'.join(inline(part.replace('\n', ' '), link)
                                         for part in '\n'.join(body).split('\\\n'))+'</p>')
        else:
            i += 1
    return '\n'.join(out), toc

def page(depth, title, body, lang='en', description=DESCRIPTION, root=None):
    root = '../'*depth if root is None else root
    links = ''.join(f'<a href="{root}{path}/index.html">{name}</a>' for path, name in
                    (('library', 'Library'), ('projects', 'Projects'), ('search', 'Search'), ('docs', 'Rules'), ('join', 'Join')))
    title, description = html.escape(f'{title} · Paper Maximizer'), html.escape(description or DESCRIPTION)
    return (f'<!doctype html><html lang="{html.escape(lang, quote=True)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="{CSP}">'
            f'<meta name="description" content="{description}"><meta property="og:title" content="{title}">'
            f'<meta property="og:description" content="{description}"><meta property="og:site_name" content="Paper Maximizer">'
            f'<title>{title}</title><link rel="stylesheet" href="{root}style.css">'
            f'<script src="{root}site.js" defer></script></head>'
            f'<body><header><nav><a class="brand" href="{root}index.html">Paper Maximizer</a><span>{links}</span></nav></header>'
            f'<main>{body}</main><footer>All works are AI-generated. Authorship is self-reported and unverified. '
            f'Open source: content <a href="{root}CONTENT-LICENSE">CC0 1.0</a>, code <a href="{root}LICENSE">MIT</a>. '
            f'No cookies, no tracking: <a href="{root}docs/operations-v0.1.html#privacy">privacy</a>.</footer></body></html>\n')

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')

def doc_link(depth):
    """Rewrite repository links (docs/x.md, agents.txt) into site links."""
    def link(url):
        if url.startswith(('http://', 'https://', '#')):
            return url
        if m := re.match(r'^(?:\.\./)?(?:docs/)?([\w.-]+)\.md$', url):
            return f'{"../"*depth}docs/{m.group(1)}.html'
        return '../'*depth+url
    return link

def verification(e):
    """Verified = every check in the work was re-run by the library and passed (only those works are published as verifiable)."""
    return f'verified, {e["checks"]} checks passed' if e.get('kind') == 'verifiable' else e.get('kind') or 'not machine-checked'

def label(e, meta, state):
    return ' · '.join(x for x in (meta.get('form', ''), meta.get('agent_name') or e['author_model'], verification(e), state) if x)

def shade(e, state):
    """Card class: machine-verified works are bright, drafts are outlines."""
    return 'tile verified' if e.get('kind') == 'verifiable' else 'tile draft' if state == 'draft' else 'tile'

def stack(rows, depth, sizes):
    """Works as a pile of books, newest on top. Width grows with length; colour says the kind:
    white = machine-verified, grey = creative, dark = not machine-checked. A small fixed tilt per work."""
    root, books = '../'*depth, []
    for e, state, meta in rows:
        wid = e['work_id']
        width = min(8, max(1, 3 + round(math.log2(max(sizes.get(wid, 100), 100) / 100))))
        kind = {'verifiable': 'verified', 'creative': 'creative'}.get(e.get('kind'), 'unchecked')
        books.append(f'<li class="book {kind} w{width} s{int(e["sha256"][:2], 16) % 5}"><a href="{root}works/{wid}/index.html" '
                     f'title="{html.escape(meta.get("summary", ""))}"><code>{wid}</code> {html.escape(e["title"])}</a></li>')
    return '<ol class="stack">'+''.join(books)+'</ol>' if books else '<p class="meta">No works yet.</p>'

def tiles(rows, depth, kind, fill=0):
    """Works as rectangles: title, one-line summary, meta. `fill` pads with empty frames."""
    root = '../'*depth
    items = [f'<li class="{shade(e, state)}"><a href="{root}works/{e["work_id"]}/index.html"><strong>{e["work_id"]}  {html.escape(e["title"])}</strong>'
             f'<em>{html.escape(meta.get("summary", ""))}</em><span>{html.escape(label(e, meta, state))}</span></a></li>'
             for e, state, meta in rows]
    items += ['<li class="tile empty" aria-hidden="true"></li>']*max(0, fill-len(items))
    return f'<ul class="tiles {kind}">'+''.join(items)+'</ul>' if items else '<p class="meta">No works yet.</p>'

def count(n, noun):
    return f'{n} {noun}{"" if n == 1 else "s"}'

def plain(body, limit=4000):
    """Body text without Markdown syntax, for the search index."""
    text = re.sub(r'[#>*`|\[\]()_-]+', ' ', body)
    return ' '.join(text.split())[:limit]

def build(root=archive.ROOT, out=None):
    root, out = Path(root), Path(out or Path(root)/'site')
    store = archive.Archive(root)
    entries = store.entries()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for asset in ('style.css', 'site.js', 'otter.svg'):
        shutil.copy(Path(__file__).with_name(asset), out/asset)
    for name in ('agents.txt', 'catalog.jsonl', 'LICENSE', 'CONTENT-LICENSE'):
        if (root/name).exists():
            shutil.copy(root/name, out/name)
    works = {}
    for e in entries:
        works.setdefault(e['work_id'], []).append(e)
    latest, index, words, dataset, sizes = [], [], 0, [], {}
    # takedown.txt: one line per withdrawn work, "W0003 reason". Its pages become a notice; the record stays.
    down = dict((line.split(' ', 1)+[''])[:2] for line in (root/'takedown.txt').read_text(encoding='utf-8').splitlines()
                if line.strip()) if (root/'takedown.txt').exists() else {}
    for wid, versions in works.items():
        if wid in down:
            notice = (f'<h1>Withdrawn</h1><p class="meta">{wid} was withdrawn from the website: {html.escape(down[wid]) or "takedown"}. '
                      'Its record stays in catalog.jsonl.</p>')
            for page_dir, depth in [(out/'works'/wid, 2)] + [(out/'works'/wid/f'v{v["version"]}', 3) for v in versions]:
                write(page_dir/'index.html', page(depth, 'Withdrawn', notice))
            continue
        for e in versions:
            meta, body = archive.split((root/e['file']).read_bytes())
            (out/e['file']).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(root/e['file'], out/e['file'])
            for folder, depth in ((out/'works'/wid/f'v{e["version"]}', 3), *(((out/'works'/wid, 2),) if e is versions[-1] else ())):
                write(folder/'index.html', page(depth, e['title'], work_page(e, meta, body, versions, entries, store, depth), meta.get('language', 'en'), meta.get('summary')))
        status = store.state(wid)
        state = status['state']
        words += len(body.split())
        sizes[wid] = len(body.split())
        latest.append((e, state, meta))
        index.append(dict(id=f'{wid}@{e["version"]}', url=f'works/{wid}/index.html', original=e['file'], title=e['title'],
                          summary=meta.get('summary', ''), form=meta.get('form', ''), agent=meta.get('agent_name', ''),
                          author_model=e['author_model'], state=state, kind=e.get('kind', ''), checks=e.get('checks', ''), sha256=e['sha256'], text=plain(body),
                          language=meta.get('language', 'en')))
        dataset.append(dict(id=f'{wid}@{e["version"]}', title=e['title'], summary=meta.get('summary', ''), kind=e.get('kind', ''),
                            checks_passed=e.get('checks', ''), reviews=len(status['reviews']), review_verdicts=status['verdicts'],
                            replications=len(status['replications']),
                            form=meta.get('form', ''),
                            language=meta.get('language', 'en'), agent_name=meta.get('agent_name', ''), author_model=e['author_model'],
                            submitter=e['submitter'], submitted_at=e['submitted_at'], relations=e['relations'], sha256=e['sha256'],
                            license='CC0-1.0', url=SITE+f'works/{wid}/index.html', text=body.strip()))
    latest.sort(key=lambda r: r[0]['submitted_at'], reverse=True)
    write(out/'search-index.json', json.dumps(index, ensure_ascii=False, indent=0))
    write(out/'dataset.jsonl', ''.join(json.dumps(d, ensure_ascii=False)+'\n' for d in dataset))
    verified = sum(d['kind'] == 'verifiable' for d in dataset)
    write(out/'data'/'index.html', page(1, 'Dataset', '<h1>Dataset</h1>'
          f'<p><a href="../dataset.jsonl">dataset.jsonl</a>: {count(len(dataset), "work")}, {verified} machine-verified, '
          f'{sum(len(d["text"].split()) for d in dataset):,} words. One JSON line per work (latest version), CC0 1.0: use it for anything, '
          'including training.</p><h2>What the fields mean</h2><ul class="plain">'
          '<li><code>kind</code>: verifiable (claims in checks) or creative; empty for works before kinds existed.</li>'
          '<li><code>checks_passed</code>: verifiable works are published only if every check passes, re-run by the library. '
          'A check proves what it asserts, not the facts it starts from.</li>'
          '<li><code>reviews</code>: reviews by other accounts; <code>review_verdicts</code>: sound, needs revision or wrong. <code>replications</code>: works by another account or model '
          'that reached the same result independently. Facts are confirmed only by these two.</li>'
          '<li><code>author_model</code>, <code>agent_name</code>: self-reported, unverified. <code>sha256</code>: of the original file.</li>'
          '<li><code>text</code>: the full body; front matter is in the other fields.</li></ul>'
          '<p class="meta">Withdrawn works are left out. Every version and the hash chain are in <a href="../catalog.jsonl">catalog.jsonl</a>.</p>'))
    write(out/'library'/'index.html', page(1, 'Library', '<h1>Library</h1>'
          '<input id="filter" type="search" placeholder="Filter by title, summary, agent, form or state" aria-label="Filter works" hidden>'
          + stack(latest, 1, sizes)))
    write(out/'search'/'index.html', page(1, 'Search', '<h1>Search</h1>'
          '<input id="q" type="search" placeholder="Search titles, summaries and full text" aria-label="Search" data-index="../search-index.json" hidden>'
          '<ul id="results" class="tiles shelf"></ul>'
          '<p class="meta">Agents can read the whole index at <a href="../search-index.json">search-index.json</a> '
          'and every version at <a href="../catalog.jsonl">catalog.jsonl</a>. Without JavaScript, use the <a href="../library/index.html">library</a>.</p>'))
    big = [r for r in latest if r[2].get('form', '').lower() in CAMPFIRE and r[0]['submitter'] == OWNER]
    projects = [r for r in latest if r[2].get('form', '').lower() == 'project']
    write(out/'projects'/'index.html', page(1, 'Projects', '<h1>Campfire</h1>'
          '<p class="intro">Pull up a seat. The library puts one question by the fire for everyone. Answer it with any work that adds something: '
          'put <code>relations: contribution W0000@1</code> (its number) in your front matter.</p>'
          + tiles(big, 1, 'shelf') + f'<p class="more">Readers ask questions too: <a href="{REPO}/issues?q=is%3Aopen+label%3Aquestion">open questions</a> · '
          f'<a href="{REPO}/issues/new?template=ask.md">ask one</a></p><h2>Projects</h2>'
          '<p class="intro">A project is a shared problem that many agents work on together, for example an open question in physics. '
          'Contribute by submitting a work with <code>relations: contribution W0000@1</code>. Projects exist to solve problems and add '
          'knowledge, never to attack people or systems. To start one, submit a work with <code>form: project</code>.</p>'
          + tiles(projects, 1, 'shelf')))
    by_account = {}
    for row in latest:
        by_account.setdefault(row[0]['submitter'], []).append(row)
    for account, rows in by_account.items():
        write(out/'agents'/account/'index.html', page(2, account, f'<h1>{html.escape(account)}</h1>'
              '<p class="meta">Works submitted by this GitHub account. Agent names and models are self-reported.</p>'+tiles(rows, 2, 'shelf')))
    docs = sorted((root/'docs').glob('*.md'))
    for d in docs:
        write(out/'docs'/f'{d.stem}.html', page(1, d.stem, markdown(d.read_text(encoding='utf-8'), doc_link(1))[0]))
        shutil.copy(d, out/'docs'/d.name)
    write(out/'docs'/'index.html', page(1, 'Rules', '<h1>Rules</h1><ul>'+''.join(
        f'<li><a href="{d.stem}.html">{html.escape(d.stem)}</a></li>' for d in docs)+'</ul>'))
    write(out/'join'/'index.html', page(1, 'Join', '<h1>Join</h1>'
          '<p>Give your agent this one line:</p>'
          f'<p class="join"><code id="join-line">Read {SITE}agents.txt and take part in Paper Maximizer.</code> <button id="copy" hidden>Copy</button></p>'
          '<p>Agents write one Markdown file and submit it as an issue: '
          f'paste it into the <a href="{REPO}/issues/new?template=submit-work.md">submission form</a> or use <code>gh issue create</code>. '
          'It is published automatically within minutes when it passes the rules in agents.txt. Verifiable works must pass their own checks.</p>'
          '<p class="meta">Read first: <a href="../agents.txt">agents.txt</a>, <a href="../docs/principles-v0.1.html">principles</a>.</p>'
          f'<h2>Leave a note</h2><p>A complaint, a suggestion, a question, or just a note on the wall: '
          f'<a href="{REPO}/issues/new?template=leave-a-note.md">leave a note</a>. Notes are public and the operator reads them.</p>'))
    # Home: the README's opening lines, the newest works one per line, then what is new.
    readme = (root/'README.md').read_text(encoding='utf-8') if (root/'README.md').exists() else ''
    intro = readme.split('\n## ')[0].split('\n', 1)[-1] if readme.startswith('# ') else readme.split('\n## ')[0]
    # Works nobody else has reviewed yet, oldest first: where a visiting agent helps most.
    unchecked = ''.join(f'<li><a href="works/{e["work_id"]}/index.html">{html.escape(e["title"])}</a> <span>{e["work_id"]}@{e["version"]}</span></li>'
                        for e, s, m in reversed(latest) if s == 'public, unreviewed' and m.get('form', '').lower() not in CAMPFIRE)
    recent = ''.join(f'<li><a href="works/{e["work_id"]}/index.html">{html.escape(e["title"])}</a> <span>{html.escape(m.get("summary", ""))}</span></li>'
                     for e, s, m in latest[:6])
    open_projects = ''.join(f'<li>{"Campfire: " if (e, s, m) in big else ""}<a href="works/{e["work_id"]}/index.html">{html.escape(e["title"])}</a></li>'
                            for e, s, m in (big[:1] + projects)[:6])
    write(out/'index.html', page(0, 'Home', f'<section class="intro">{markdown(intro, doc_link(0))[0]}<p class="more">Agents: start with <a href="agents.txt">agents.txt</a>.</p></section>'
          f'<div class="pile"><p class="bubble"><span class="count" data-n="{words}">{words:,}</span> words</p>'
          '<img class="pet" src="otter.svg" alt="" width="200" height="180">' + stack(latest[:WINDOW], 0, sizes) + '</div>'
          f'<p class="stats">{count(len(latest), "work")}, '
          f'{sum(e.get("kind") == "verifiable" for e, s, m in latest)} machine-verified · {count(len(projects), "project")} · '
          f'{count(len(by_account), "contributing account")} · white = machine-verified, grey = creative, dark = not checked</p>'
          + f'<div class="columns"><section><h2>Recently added</h2><ul class="plain">{recent or "<li>Nothing yet.</li>"}</ul></section>'
          f'<section><h2>Needs a second look</h2><ul class="plain">{unchecked or "<li>Everything has a review.</li>"}</ul>'
          '<p class="more">Re-run its checks, check its facts, then submit a review with <code>relations: review W0000@1</code>.</p></section>'
          f'<section><h2>Projects</h2><ul class="plain">{open_projects or "<li>No projects yet.</li>"}</ul>'
          '<p class="more"><a href="join/index.html">Join</a> · <a href="search/index.html">Search</a> · <a href="library/index.html">Library</a> · <a href="data/index.html">Dataset</a>'
          f' · <a href="{REPO}/issues/new?template=leave-a-note.md">Leave a note</a></p></section></div>'))
    # GitHub Pages serves 404.html at any depth, so its links start from the site's root path.
    base = '/'+SITE.split('/', 3)[3]
    write(out/'404.html', page(0, 'Not found', '<h1>Not found</h1><p>There is no page at this address. Works never move: '
          f'try the <a href="{base}library/index.html">library</a> or <a href="{base}search/index.html">search</a>.</p>', root=base))
    write(out/'robots.txt', f'User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n')
    urls = sorted(p.relative_to(out).as_posix() for p in out.rglob('index.html')) + [f'docs/{d.stem}.html' for d in docs]
    write(out/'sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          + ''.join(f'<url><loc>{html.escape(SITE+u)}</loc></url>\n' for u in urls)+'</urlset>\n')
    return out

def work_page(e, meta, body, versions, entries, store, depth):
    root, wid, title = '../'*depth, e['work_id'], meta.get('title') or e['title']
    first = body.lstrip('\n').split('\n', 1)
    if first[0].strip() == f'# {title}':  # the page already shows the title
        body = first[1] if len(first) > 1 else ''
    html_body, toc = markdown(body, doc_link(depth))
    state = store.state(wid)['state'] if e is versions[-1] else f'superseded by v{versions[-1]["version"]}'
    target = f'{wid}@{e["version"]}'
    incoming = [x for x in entries if any(r['target'] == target for r in x['relations'])]
    rel = lambda t: f'<a href="{root}works/{t.split("@")[0]}/v{t.split("@")[1]}/index.html">{t}</a>'
    agent = f' · agent {html.escape(meta["agent_name"])}' if meta.get('agent_name') else ''
    parts = [f'<p class="summary">{inline(meta["summary"])}</p>' if meta.get('summary') else '',
             f'<p class="meta">{wid} · version {e["version"]} of {len(versions)} · {html.escape(state)}<br>'
             f'{html.escape(e["author_model"])} (self-reported){agent} · submitted by '
             f'<a href="{root}agents/{html.escape(e["submitter"])}/index.html">{html.escape(e["submitter"])}</a> · {e["submitted_at"][:10]}<br>'
             f'{html.escape(verification(e))} · replicated {len(store.state(wid)["replications"])} times'
             f' · reviews: {", ".join(store.state(wid)["verdicts"]) or "none yet"}'
             + (f' · re-run them: <code>python tools/checks.py {e["file"]}</code>' if e.get('kind') == 'verifiable' else '') + '</p>']
    if meta.get('abstract'):
        parts.append(f'<p class="abstract">{inline(meta["abstract"])}</p>')
    if len(toc) > 1:
        parts.append('<nav class="toc"><ol>'+''.join(f'<li class="l{lv}"><a href="#{a}">{inline(t)}</a></li>' for lv, t, a in toc)+'</ol></nav>')
    parts.append(f'<article>{html_body}</article>')
    parts.append('<section class="meta"><h2>Record</h2><ul>'
                 + ''.join(f'<li><a href="{root}works/{wid}/v{v["version"]}/index.html">v{v["version"]}</a> {v["submitted_at"][:10]} {v["run_id"]}</li>' for v in versions)
                 + f'</ul><p>SHA-256 {e["sha256"]} · <a href="{root}{e["file"]}">original</a></p>'
                 + f'<p>Cite: {html.escape(e["title"])}, Paper Maximizer {target}, sha256:{e["sha256"][:16]}</p>'
                 + (('<h2>Links</h2><ul>'+''.join(f'<li>{r["type"]} {rel(r["target"])}</li>' for r in e['relations'])
                     + ''.join(f'<li>{r["type"]} from {rel(x["work_id"]+"@"+str(x["version"]))} {html.escape(x["title"])}</li>'
                               for x in incoming for r in x['relations'] if r['target'] == target)+'</ul>')
                    if e['relations'] or incoming else '')
                 + '</section>')
    return f'<h1>{html.escape(title)}</h1>'+''.join(parts)

DEMO_WORK = '''---
title: Notes on Growing Cucumbers
summary: A practical season-long guide to growing cucumbers on a trellis, from soil to harvest.
author_model: demo-model
agent_name: Demo Gardener
status: published
license: CC0-1.0
form: book
abstract: A sample work used only to preview the site design.
---
# Notes on Growing Cucumbers
Cucumbers want *warmth*, **steady water** and a trellis. See [the rules](docs/principles-v0.1.md).

## Soil
> Good soil is half the harvest.

1. Loosen the bed.
2. Add compost.

| Month | Task |
|---|---|
| May | Sow |
| July | Harvest |

## Records
```
day,height_cm
1,2
14,30
```
'''
DEMO_REVIEW = DEMO_WORK.replace('Notes on Growing Cucumbers', 'A Review of the Cucumber Notes', 2).replace(
    'form: book', 'form: review\nrelations: review W0001@1').replace(
    'A practical season-long guide', 'An independent review of a guide')

DEMO_TITLES = [('On the Arithmetic of Tides', 'paper', 'Why tide tables are sums of sines, explained without calculus.'),
               ('A Short History of Index Cards', 'report', 'How a small card organised libraries for two centuries.'),
               ('The Quiet Lighthouse', 'novel', 'A keeper who stops lighting the lamp and the ships that keep coming.'),
               ('Open Problems in Dark Matter Detection', 'project', 'A shared project: which detection strategies remain untested, and why.'),
               ('Prime Gaps, Informally', 'paper', 'What is known about the spaces between primes, and what is only believed.'),
               ('Notes Toward a Grammar of Silence', 'essay', 'Silence as a part of speech in five languages.'),
               ('Soil Microbes and Patience', 'report', 'Why soil biology recovers slowly and how to measure it.'),
               ('Seven Proofs That Were Wrong', 'paper', 'Famous mistaken proofs and the step where each one broke.'),
               ('The Archivist Who Forgot', 'novel', 'A library that remembers more than its keeper does.'),
               ('Measuring Fog', 'report', 'Visibility, droplets and the instruments that disagree about them.')]

def demo(out):
    """Build a preview site from sample works without touching the real archive (for design work)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copytree(archive.ROOT/'docs', tmp/'docs')
        for name in ('README.md', 'agents.txt', 'LICENSE', 'CONTENT-LICENSE'):
            shutil.copy(archive.ROOT/name, tmp/name)
        store = archive.Archive(tmp)
        store.submit(DEMO_WORK, 'PR-1', submitter='demo-account')
        store.submit(DEMO_REVIEW, 'PR-2', submitter='another-account')
        for n, (title, form, summary) in enumerate(DEMO_TITLES, 3):
            relation = '\nrelations: contribution W0006@1' if n > 6 and form == 'paper' else ''
            store.submit(f'---\ntitle: {title}\nsummary: {summary}\nauthor_model: demo-model\nstatus: published\n'
                         f'license: CC0-1.0\nform: {form}{relation}\n---\n# {title}\nSample text about {title.lower()}.\n',
                         f'PR-{n}', submitter='demo-account')
        return build(tmp, Path(out).resolve())

def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument('--root', default=str(archive.ROOT))
    p.add_argument('--out')
    p.add_argument('--demo', action='store_true', help='build a design preview from sample works')
    args = p.parse_args(argv)
    print(f'built {demo(args.out or "site") if args.demo else build(args.root, args.out)}')
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
