import json
import shutil
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
        found.write_text(json.dumps(results or checks.check(intake.extract(body), self.root)), encoding='utf-8')
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

    @unittest.skipUnless(shutil.which('docker'), 'Docker required for submitted Python checks')
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

    def test_safety_ok_label_skips_the_screen(self):
        event, found = self.root/'event.json', self.root/'checks.json'
        event.write_text(json.dumps({'action': 'labeled', 'label': {'name': 'safety-ok'}, 'issue': {'number': 8, 'body': FILE, 'user': {'login': 'carol'}, 'labels': [{'name': 'safety-ok'}]}}), encoding='utf-8')
        found.write_text(json.dumps(checks.check(FILE)), encoding='utf-8')
        def flag(_): return False, 'User Safety: unsafe'
        self.assertEqual(intake.main([str(event), '--checks', str(found), '--root', str(self.root)], age=lambda _: 30, screen=flag), 0)

    def test_edited_text_does_not_inherit_an_old_safety_approval(self):
        event = {'action': 'edited', 'issue': {'number': 9, 'body': FILE, 'user': {'login': 'carol'}, 'labels': [{'name': 'safety-ok'}]}}
        screen = mock.Mock(return_value=(False, 'flagged'))
        with self.assertRaises(archive.ArchiveError):
            intake.intake(event, self.root, checks.check(FILE), age=lambda _: 30, screen=screen)
        screen.assert_called_once()
        self.assertEqual(archive.Archive(self.root).entries(), [])

    def test_preflight_failure_cannot_reach_the_safety_service_or_publisher(self):
        event = {'issue': {'number': 9, 'body': FILE, 'user': {'login': 'carol'}}}
        screen = mock.Mock()
        with self.assertRaises(archive.ArchiveError):
            intake.intake(event, self.root, {'validation_errors': ['too many checks']}, age=lambda _: 30, screen=screen)
        screen.assert_not_called()
        self.assertEqual(archive.Archive(self.root).entries(), [])

    @unittest.skipUnless(shutil.which('docker'), 'Docker required for submitted verifiers')
    def test_tasks_need_a_sound_verifier_and_attempts_are_scored_pass_or_fail(self):
        task = FILE.replace('creative', 'task') + '```verify\ndef verify(answer):\n    return answer.strip() == "5050"\n```\n```reference\n5050\n```\n'
        loose = task.replace('return answer.strip() == "5050"', 'return True')
        code, reply = self.run_issue(loose, n=1)
        self.assertEqual(code, 1); self.assertIn("does not reject the trivial answer ''", reply)
        self.assertEqual(self.run_issue(task, n=2)[0], 0)  # W0001
        published = (self.root/archive.Archive(self.root).entries()[0]['file']).read_text(encoding='utf-8')
        self.assertNotIn('5050\n```\n', published); self.assertIn('withheld', published)
        self.assertEqual((self.root/'intake-body.md').read_text(encoding='utf-8'), published)
        attempt = FILE.replace('creative', 'attempt').replace('status:', 'relations: attempt W0001@1\nstatus:') + 'I paired numbers from both ends. ' * 12 + '\n```answer\n5050\n```\n'
        self.assertEqual(self.run_issue(attempt, n=3)[0], 0)
        self.assertEqual(self.run_issue(attempt.replace('5050\n```', '5051\n```'), n=4)[0], 0)  # a wrong answer is kept too
        self.assertEqual([e.get('result') for e in archive.Archive(self.root).entries()], [None, 'pass', 'fail'])
        self.assertEqual([r for _, r, _ in archive.Archive(self.root).state('W0001')['attempts']], ['pass', 'fail'])

    def test_reference_answers_are_withheld_by_hash(self):
        task = FILE.replace('creative', 'task') + '```verify\ndef verify(answer):\n    return answer.strip() == "5050"\n```\n```reference\n5050\n```\nAfter.\n'
        out = intake.withhold(task)
        self.assertNotIn('5050\n```', out); self.assertIn('return answer.strip() == "5050"', out)  # the verifier stays
        self.assertIn(f'(sha256 {archive.sha256(b"5050" + bytes([10]))})', out); self.assertTrue(out.endswith('```\nAfter.\n'))

    def test_template_references_parse_per_instance(self):
        template = FILE.replace('creative', 'task').replace('status:', 'instances: 10; 12\nstatus:') + '```reference\n10: 55\n12: 78\n```\n'
        self.assertEqual(checks.instances(template), ['10', '12'])
        self.assertEqual(checks.references(template), {'10': '55', '12': '78'})
        self.assertEqual(checks.instances(FILE), [None])

    @unittest.skipUnless(shutil.which('docker'), 'Docker required for submitted verifiers')
    def test_one_template_many_problems_scored_per_instance(self):
        verify = '```verify\ndef verify(answer, instance):\n    n = int(instance)\n    return answer.strip() == str(n * (n + 1) // 2)\n```\n'
        template = FILE.replace('creative', 'task').replace('status:', 'instances: 10; 12\nstatus:') + verify + '```reference\n10: 55\n12: 78\n```\n'
        code, reply = self.run_issue(template.replace('12: 78', '12: 77'), n=1)
        self.assertEqual(code, 1); self.assertIn('instance 12', reply)
        self.assertEqual(self.run_issue(template, n=2)[0], 0)
        attempt = FILE.replace('creative', 'attempt').replace('status:', 'relations: attempt W0001@1\ninstance: 12\nstatus:') + 'Gauss pairing. ' * 30 + '\n```answer\n78\n```\n'
        self.assertEqual(self.run_issue(attempt, n=3)[0], 0)
        self.assertEqual(archive.Archive(self.root).entries()[-1]['instance'], '12')

    def test_one_issue_is_never_published_twice(self):
        self.assertEqual(self.run_issue(FILE, n=7)[0], 0)
        code, reply = self.run_issue(FILE, n=7)
        self.assertEqual(code, 0); self.assertIn('already published', reply)
        self.assertEqual(len(archive.Archive(self.root).entries()), 1)

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
    @unittest.skipUnless(shutil.which('docker'), 'Docker required for submitted Python checks')
    def test_pass_fail_timeout_and_no_environment(self):
        text = '```check\nassert 2 + 2 == 4\n```\n```check\nassert 1 == 2\n```\n```check\nimport os\nassert "GH_TOKEN" not in os.environ\n```\n'
        result = checks.check(text)
        self.assertEqual((result['passed'], result['total']), (2, 3))
        self.assertEqual(result['failures'], ['check 2: check container exited with code 1'])

if __name__ == '__main__':
    unittest.main()
