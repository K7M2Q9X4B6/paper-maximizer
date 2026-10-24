import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import archive
import publish

def work(title, extra=''):
    return f'---\ntitle: {title}\nsummary: One line about {title}.\nauthor_model: m\nagent_name: Tester\nstatus: published\nlicense: CC0-1.0\n{extra}---\n# {title}\nText.\n'

class PublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'submissions').mkdir()
    def tearDown(self):
        self.tmp.cleanup()
    def add(self, name, text):
        (self.root/'submissions'/name).write_text(text, encoding='utf-8')

    def test_new_work_then_revision_by_same_account(self):
        self.add('a.md', work('First'))
        self.assertEqual(publish.publish(self.root, 'PR-3', 'alice'), ['W0001@1 First'])
        self.assertEqual(list((self.root/'submissions').glob('*.md')), [])
        sha = archive.Archive(self.root).entries()[0]['sha256']
        self.add('a2.md', work('First', f'work: W0001\nprev_hash: {sha}\n'))
        self.assertEqual(publish.publish(self.root, 'PR-8', 'alice'), ['W0001@2 First'])
        self.assertEqual(archive.Archive(self.root).verify(), [])

    def test_revision_by_other_account_rejected_and_nothing_changes(self):
        self.add('a.md', work('First'))
        publish.publish(self.root, 'PR-3', 'alice')
        sha = archive.Archive(self.root).entries()[0]['sha256']
        self.add('b.md', work('Hijack', f'work: W0001\nprev_hash: {sha}\n'))
        with self.assertRaises(archive.ArchiveError):
            publish.publish(self.root, 'PR-4', 'mallory')
        self.assertTrue((self.root/'submissions/b.md').exists())

    def test_invalid_file_blocks_the_whole_batch(self):
        self.add('good.md', work('Good'))
        self.add('bad.md', work('Bad').replace('license: CC0-1.0\n', ''))
        self.assertEqual(publish.main(['--run-id', 'PR-5', '--submitter', 'bob', '--root', str(self.root)]), 1)
        self.assertEqual(archive.Archive(self.root).entries(), [])
        self.assertEqual(len(list((self.root/'submissions').glob('*.md'))), 2)

if __name__ == '__main__':
    unittest.main()
