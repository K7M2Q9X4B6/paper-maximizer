import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import archive
import intake

FILE = '---\ntitle: Tides\nsummary: Why tides repeat.\nauthor_model: m\nstatus: published\nlicense: CC0-1.0\n---\n# Tides\nText.\n'

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def run_issue(self, body, n=7):
        event = self.root/'event.json'
        event.write_text(json.dumps({'issue': {'number': n, 'body': body, 'user': {'login': 'carol'}}}), encoding='utf-8')
        return intake.main([str(event), '--root', str(self.root)]), (self.root/'intake-reply.md').read_text(encoding='utf-8')

    def test_form_comment_fence_and_crlf_are_removed(self):
        body = '<!-- Paste the complete file below -->\r\n```markdown\r\n'+FILE.replace('\n', '\r\n')+'```\r\n'
        self.assertEqual(intake.extract(body), FILE)
        self.assertEqual(intake.extract(FILE), FILE)

    def test_approved_issue_is_published_as_its_author(self):
        code, reply = self.run_issue('<!-- form -->\n'+FILE)
        self.assertEqual(code, 0)
        self.assertIn('Published: W0001@1 Tides', reply)
        e = archive.Archive(self.root).entries()[0]
        self.assertEqual((e['run_id'], e['submitter'], e['via']), ('ISSUE-7', 'carol', 'issue'))
        self.assertEqual(list((self.root/'submissions').glob('*.md')), [])

    def test_invalid_issue_changes_nothing_and_explains(self):
        code, reply = self.run_issue(FILE.replace('summary: Why tides repeat.\n', ''))
        self.assertEqual(code, 1)
        self.assertIn('missing front matter: summary', reply)
        self.assertEqual(archive.Archive(self.root).entries(), [])
        self.assertEqual(list((self.root/'submissions').glob('*.md')), [])

if __name__ == '__main__':
    unittest.main()
