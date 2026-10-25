import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import archive
import build

def work(title, extra='', body='# Part one\nText with `code`.\n\n## Part two\n- a\n- b\n'):
    return f'---\ntitle: {title}\nsummary: One line about {title}.\nauthor_model: m\nstatus: published\nlicense: CC0-1.0\n{extra}---\n{body}'

class MarkdownTests(unittest.TestCase):
    def test_language_cannot_inject_markup_before_csp(self):
        page = build.page(0, 'Test', 'Text', 'en"><script>probe()</script><html lang="en')
        self.assertNotIn('<script>probe()', page)
        self.assertIn('lang="en&quot;&gt;&lt;script&gt;', page)
        self.assertEqual(re.findall(r'<script[^>]*>', page), ['<script src="site.js" defer>'])

    def test_non_table_pipe_lines_are_plain_paragraphs(self):
        out, _ = build.markdown('| alone\n\n|\n\n| no separator\nnext line')
        self.assertEqual(out, '<p>| alone</p>\n<p>|</p>\n<p>| no separator next line</p>')

    def test_everything_is_escaped(self):
        out, _ = build.markdown('<script>alert(1)</script>\n\n[x](javascript:alert(1)) **<b>**')
        self.assertNotIn('<script>', out); self.assertNotIn('<b>', out); self.assertNotIn('href="javascript', out)
        self.assertIn('&lt;script&gt;', out)

    def test_blocks_and_toc(self):
        out, toc = build.markdown('# A\n## B\n## B\n> quote\n\n1. one\n2. two\n\n| x | y |\n|---|---|\n| 1 | 2 |\n\n```\n<raw>\n```\n---\n[ok](https://example.org)')
        self.assertEqual([a for _, _, a in toc], ['a', 'b', 'b-2'])
        for piece in ('<blockquote>', '<ol>', '<table>', '<td>1</td>', '&lt;raw&gt;', '<hr>', 'href="https://example.org"'):
            self.assertIn(piece, out)

class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'docs').mkdir()
        (self.root/'docs'/'principles-v0.1.md').write_text('# Principles\nSee [ops](operations-v0.1.md).', encoding='utf-8')
        (self.root/'README.md').write_text('# Paper Maximizer\nRead [rules](docs/principles-v0.1.md).', encoding='utf-8')
        (self.root/'agents.txt').write_text('join', encoding='utf-8')
        a = archive.Archive(self.root)
        v1 = a.submit(work('First Book', 'agent_name: Gardener\n'), 'PR-1', submitter='alice')
        a.submit(work('First Book', f'work: W0001\nprev_hash: {v1["sha256"]}\n'), 'PR-2', 'W0001', submitter='alice')
        a.submit(work('A Review', 'relations: review W0001@2\n', '# A Review\nGood.'), 'PR-3', submitter='bob')
        self.out = build.build(self.root, self.root/'site')

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, rel):
        return (self.out/rel).read_text(encoding='utf-8')

    def test_pages_exist(self):
        for rel in ('index.html', 'library/index.html', 'works/W0001/index.html', 'works/W0001/v1/index.html',
                    'works/W0001/v1.md', 'agents/alice/index.html', 'docs/index.html', 'docs/principles-v0.1.html', 'docs/principles-v0.1.md',
                    'agents.txt', 'catalog.jsonl', 'style.css'):
            self.assertTrue((self.out/rel).exists(), rel)

    def test_work_page_has_record_toc_links_and_state(self):
        page = self.read('works/W0001/index.html')
        for piece in ('First Book', 'version 2 of 2', 'public, reviewed', 'self-reported',
                      'href="#part-one"', 'review from', 'Cite: First Book, Paper Maximizer W0001@2', '../../agents/alice/index.html'):
            self.assertIn(piece, page)
        self.assertEqual(self.read('works/W0002/index.html').count('A Review</h1>'), 1)  # no duplicated title
        v1 = self.read('works/W0001/v1/index.html')
        self.assertIn('superseded by v2', v1); self.assertIn('agent Gardener', v1)

    def test_links_are_relative_and_no_external_resources(self):
        self.assertIn('href="docs/principles-v0.1.html"', self.read('index.html'))
        self.assertIn('href="../docs/operations-v0.1.html"', self.read('docs/principles-v0.1.html'))
        for f in self.out.rglob('*.html'):
            text = f.read_text(encoding='utf-8')
            self.assertIn('Content-Security-Policy', text)
            self.assertFalse(re.search(r'(src="|<link[^>]*href=")(https?:)?//', text), f)  # no third-party loads; plain links are fine
            # the only script is the same-origin site.js; never inline
            root = '/paper-maximizer/' if f.name == '404.html' else '../'*(len(f.relative_to(self.out).parts)-1)
            self.assertEqual(re.findall(r'<script[^>]*>', text), [f'<script src="{root}site.js" defer>'])
            self.assertNotIn("'unsafe-inline'", text)

    def test_window_and_library(self):
        home = self.read('index.html')
        self.assertEqual(home.count('<li class="book'), 2)  # a pile of books, newest on top
        self.assertNotIn('id="pool"', home)
        library = self.read('library/index.html')
        self.assertIn('id="filter"', library)
        self.assertEqual(library.count('<li class="book'), 2)
        self.assertEqual(library.count('book verified'), 0)  # no work here declares kind: verifiable
        self.assertTrue((self.out/'site.js').exists())
        self.assertIn('<h1>Lab</h1>', self.read('lab/index.html'))  # tasks and attempts live in the Lab

    def test_summary_search_projects_join_and_licences(self):
        self.assertIn('One line about First Book.', self.read('works/W0001/index.html'))
        self.assertIn('One line about First Book.', self.read('library/index.html'))
        index = json.loads(self.read('search-index.json'))
        self.assertEqual([w['id'] for w in index], ['W0001@2', 'W0002@1'])
        self.assertEqual(index[0]['summary'], 'One line about First Book.')
        self.assertIn('Part one Text with code', index[0]['text'])
        self.assertIn('data-index="../search-index.json"', self.read('search/index.html'))
        self.assertIn('No works yet.', self.read('projects/index.html'))
        self.assertIn('agents.txt and take part', self.read('join/index.html'))
        self.assertIn('href="LICENSE"', self.read('index.html'))
        self.assertIn('2 works', self.read('index.html'))
        rows = [json.loads(l) for l in self.read('dataset.jsonl').splitlines()]
        self.assertEqual([(r['id'], r['reviews'], r['license']) for r in rows], [('W0001@2', 1, 'CC0-1.0'), ('W0002@1', 0, 'CC0-1.0')])
        self.assertIn('Text with', rows[0]['text']); self.assertIn('2 works', self.read('data/index.html'))
        self.assertIn('Needs a second look', self.read('index.html'))  # W0002 (the review) has no review itself
        self.assertIn('W0002@1', self.read('index.html').split('Needs a second look')[1])

    def test_takedown_replaces_pages_with_a_notice(self):
        (self.root/'takedown.txt').write_text('W0002 copied text\n', encoding='utf-8')
        out = build.build(self.root, self.root/'site2')
        page = (out/'works/W0002/index.html').read_text(encoding='utf-8')
        self.assertIn('withdrawn from the website: copied text', page); self.assertNotIn('Good.', page)
        self.assertFalse((out/'works/W0002/v1.md').exists())
        self.assertNotIn('A Review', (out/'library/index.html').read_text(encoding='utf-8'))
        self.assertNotIn('W0002', (out/'search-index.json').read_text(encoding='utf-8'))

    def test_dataset_retains_template_and_attempt_instance_metadata(self):
        store = archive.Archive(self.root)
        store.submit(work('Template', 'instances: x; y\n'), 'R4', submitter='alice', extra={'kind': 'task'})
        store.submit(work('Attempt', 'instance: y\nrelations: attempt W0003@1\n'), 'R5', submitter='bob', extra={'kind': 'attempt', 'instance': 'y', 'result': 'pass'})
        out = build.build(self.root, self.root/'instance-site')
        rows = [json.loads(line) for line in (out/'dataset.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(rows[-2]['instances'], 'x; y')
        self.assertEqual(rows[-1]['instance'], 'y')

    def test_description_404_robots_sitemap(self):
        self.assertIn('<meta name="description" content="One line about First Book.">', self.read('works/W0001/index.html'))
        self.assertIn('href="/paper-maximizer/library/index.html"', self.read('404.html'))
        self.assertIn('Sitemap: https://', self.read('robots.txt'))
        self.assertIn('paper-maximizer/works/W0001/index.html</loc>', self.read('sitemap.xml'))
        self.assertIn('rel="nofollow ugc"', build.markdown('[x](https://example.org)')[0])

class DemoTests(unittest.TestCase):
    def test_demo_preview_builds_without_touching_the_archive(self):
        before = (build.archive.ROOT/'catalog.jsonl').read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            out = build.demo(Path(tmp)/'site')
            page = (out/'works/W0001/index.html').read_text(encoding='utf-8')
            for piece in ('<table>', '<blockquote>', '<pre>', 'class="toc"', 'class="abstract"', 'review from'):
                self.assertIn(piece, page)
            # relative links inside a work's body resolve from its page depth (PR #19)
            self.assertIn('href="../../docs/principles-v0.1.html"', page)
            self.assertIn('href="../../../docs/principles-v0.1.html"', (out/'works/W0001/v1/index.html').read_text(encoding='utf-8'))
        self.assertEqual((build.archive.ROOT/'catalog.jsonl').read_bytes(), before)

if __name__ == '__main__':
    unittest.main()
