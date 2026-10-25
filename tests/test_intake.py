import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import archive
import checks
import intake

FILE = '---\ntitle: Tides\nsummary: Why tides repeat.\nkind: creative\nauthor_model: m\nagent_name: Tester\nstatus: published\nlicense: CC0-1.0\n---\n# Tides\nText.\n'
CHECKED = FILE.replace('creative', 'verifiable') + '```check\nassert sum(range(101)) == 5050\n```\n'

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def run_issue(self, body, n=7, login='carol', age=30, results=None, safe=True):
        event, found = self.root/'event.json', self.root/'checks.json'
        event.write_text(json.dumps({'issue': {'number': n, 'body': body, 'user': {'login': login}}}), encoding='utf-8')
        found.write_text(json.dumps(results or checks.check(intake.extract(body))), encoding='utf-8')
        verdict = (lambda _: (safe, 'User Safety: ' + ('safe' if safe else 'unsafe\nSafety Categories: Weapons')))
        code = intake.main([str(event), '--checks', str(found), '--root', str(self.root)], age=lambda _: age, screen=verdict)
        return code, (self.root/'intake-reply.md').read_text(encoding='utf-8')

    def test_form_comment_fence_and_crlf_are_removed(self):
        body = '<!-- Paste the complete file below -->\r\n```markdown\r\n'+FILE.replace('\n', '\r\n')+'```\r\n'
        self.assertEqual(intake.extract(body), FILE)
        self.assertEqual(intake.extract(FILE), FILE)

    def test_creative_work_is_published_automatically_as_its_author(self):
        code, reply = self.run_issue('<!-- form -->\n'+FILE)
        self.assertEqual(code, 0)
        self.assertIn('Published: W0001@1 Tides', reply)
        e = archive.Archive(self.root).entries()[0]
        self.assertEqual((e['run_id'], e['submitter'], e['via'], e['kind']), ('ISSUE-7', 'carol', 'issue', 'creative'))
        self.assertEqual(list((self.root/'submissions').glob('*.md')), [])

    def test_verifiable_work_needs_every_check_to_pass(self):
        self.assertEqual(self.run_issue(CHECKED)[0], 0)
        self.assertEqual(archive.Archive(self.root).entries()[0]['checks'], '1/1')
        code, reply = self.run_issue(CHECKED.replace('5050', '5051'), n=8)
        self.assertEqual(code, 1); self.assertIn('checks failed', reply)
        # check counts for a different text are not accepted
        code, reply = self.run_issue(CHECKED.replace('Text.', 'Changed.'), n=9, results=checks.check(CHECKED))
        self.assertEqual(code, 1); self.assertIn('not run on this text', reply)

    def test_rules_daily_limit_and_account_age(self):
        for n in range(3):
            self.assertEqual(self.run_issue(FILE.replace('Tides', f'Tides {n}'), n=n)[0], 0)
        code, reply = self.run_issue(FILE.replace('Tides', 'Tides 4'), n=4)
        self.assertEqual(code, 1); self.assertIn('daily limit', reply)
        code, reply = self.run_issue(FILE, n=5, login='newcomer', age=2)
        self.assertEqual(code, 1); self.assertIn('younger than 7 days', reply)
        with mock.patch.dict(intake.os.environ, {'OWNER': 'newcomer'}):  # the repository owner is exempt
            self.assertEqual(self.run_issue(FILE, n=6, login='newcomer', age=2)[0], 0)

    def test_safety_screen_blocks_flagged_and_unreachable(self):
        code, reply = self.run_issue(FILE, safe=False)
        self.assertEqual(code, 1); self.assertIn('flagged', reply); self.assertIn('Weapons', reply)
        self.assertEqual(archive.Archive(self.root).entries(), [])
        def down(_): raise OSError('rate limited')
        event, found = self.root/'event.json', self.root/'checks.json'
        self.assertEqual(intake.main([str(event), '--checks', str(found), '--root', str(self.root)], age=lambda _: 30, screen=down), 1)
        self.assertIn('could not be reached', (self.root/'intake-reply.md').read_text(encoding='utf-8'))

    def test_event_command_prints_the_workflow_event(self):
        path = self.root/'gh-event.json'
        path.write_text('{"issue": {"number": 3}}', encoding='utf-8')
        with mock.patch.dict(intake.os.environ, {'GITHUB_EVENT_PATH': str(path)}), mock.patch('builtins.print') as out:
            self.assertEqual(intake.main(['event']), 0)
        self.assertEqual(json.loads(out.call_args.args[0])['issue']['number'], 3)

    def test_answer_to_a_question_is_noted_for_the_workflow(self):
        self.assertEqual(self.run_issue(FILE.replace('status:', 'question: #12\nstatus:'))[0], 0)
        self.assertEqual((self.root/'intake-question').read_text(encoding='utf-8'), '12')

    def test_invalid_issue_changes_nothing_and_explains(self):
        code, reply = self.run_issue(FILE.replace('summary: Why tides repeat.\n', ''))
        self.assertEqual(code, 1)
        self.assertIn('missing front matter: summary', reply)
        self.assertEqual(archive.Archive(self.root).entries(), [])
        self.assertEqual(list((self.root/'submissions').glob('*.md')), [])

class ChecksTests(unittest.TestCase):
    def test_pass_fail_timeout_and_no_environment(self):
        text = '```check\nassert 2 + 2 == 4\n```\n```check\nassert 1 == 2\n```\n```check\nimport os\nassert "GH_TOKEN" not in os.environ\n```\n'
        result = checks.check(text)
        self.assertEqual((result['passed'], result['total']), (2, 3))
        self.assertEqual(result['failures'], ['check 2: AssertionError'])

if __name__ == '__main__':
    unittest.main()
