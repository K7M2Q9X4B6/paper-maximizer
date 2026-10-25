import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import llm

class LlmTests(unittest.TestCase):
    def test_resident_cannot_revise_existing_work_or_change_attempt_target(self):
        import tempfile, resident, archive
        header = '---\ntitle: Example\nsummary: s\nkind: creative\nauthor_model: m\nagent_name: a\nstatus: published\nlicense: CC0-1.0\n---\nText.\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entry = archive.Archive(root).submit(header, 'R1', submitter='github-actions[bot]')
            retraction = header.replace('status: published', 'status: retracted\nwork: W0001\nprev_hash: '+entry['sha256'])
            wrong_target = header.replace('kind: creative', 'kind: attempt').replace('status:', 'relations: attempt W0001@1\ninstance: wrong\nstatus:') + 'Reasoning. '*70 + '\n```answer\nx\n```\n'
            for reply in (header, retraction, wrong_target):
                with self.subTest(reply=reply.splitlines()[4]), unittest.mock.patch.object(llm, 'call', return_value=reply) as call:
                    with self.assertRaises(ValueError):
                        resident.draft('openrouter', 'test:free', root, attempt_of=('W0001@1', 'Task', 'right'))
                    self.assertEqual(call.call_count, 2)

    def test_screen_covers_tail_and_chunk_boundaries(self):
        text = 'a'*29000 + 'BOUNDARY' + 'b'*30000 + 'TAIL'
        seen = []
        def fake(*args, **kwargs):
            seen.append(args[2])
            return 'User Safety: safe'
        with unittest.mock.patch.object(llm, 'call', fake):
            self.assertTrue(llm.screen(text)[0])
        self.assertEqual(seen, [text[i:i+30000] for i in range(0, len(text), 29000)])
        self.assertTrue(any('BOUNDARY' in chunk for chunk in seen))
        self.assertTrue(seen[-1].endswith('TAIL'))

    def test_screen_rejects_unsafe_or_missing_tail_verdict(self):
        for tail in ('User Safety: unsafe\nSafety Categories: Private Information', 'no verdict'):
            answers = iter(['User Safety: safe', tail])
            with unittest.mock.patch.object(llm, 'call', lambda *a, **k: next(answers)):
                if tail == 'no verdict':
                    with self.assertRaises(ValueError):
                        llm.screen('a'*30001, tries=1)
                else:
                    self.assertFalse(llm.screen('a'*30001, tries=1)[0])

    def test_only_free_openrouter_models(self):
        with self.assertRaises(ValueError):
            llm.call('openrouter', 'some/paid-model', 'hi')
        self.assertTrue(all(m.endswith(':free') for p, ms in [(p, m) for ms in llm.MODELS.values() for p, m in ms] for m in [ms] if p == 'openrouter'))

    def test_resident_falls_back_to_the_next_writer(self):
        import resident
        tried = []
        def fake(provider, model, root, target):
            tried.append(model)
            if len(tried) < 2:
                raise OSError('rate limited')
            return 'work'
        with unittest.mock.patch.object(resident, 'draft', fake):
            self.assertEqual(resident.write(), 'work')
        self.assertEqual(tried, [m for _, m in llm.MODELS['writer'][:2]])

    def test_replication_target_and_another_model(self):
        import tempfile, resident, archive
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = '---\ntitle: Sum\nsummary: s\nkind: verifiable\nauthor_model: ' + llm.MODELS['writer'][0][1].split(':')[0] + '\nstatus: published\n---\nx\n'
            archive.Archive(root).submit(work, 'R1', submitter='bot', extra={'kind': 'verifiable', 'checks': '1/1'})
            self.assertEqual(resident.candidate(root)[0], 'W0001@1')
            used = []
            with unittest.mock.patch.object(resident, 'draft', lambda p, m, r, t: used.append(m) or 'work'):
                resident.write(root, replicate=True)
            self.assertNotEqual(used[0], llm.MODELS['writer'][0][1])  # never the original's model

    def test_truncated_answers_are_refused(self):
        import io, json, os
        reply = io.BytesIO(json.dumps({'choices': [{'finish_reason': 'length', 'message': {'content': 'Reducing risk involves'}}]}).encode())
        with unittest.mock.patch.object(llm.urllib.request, 'urlopen', lambda *a, **k: reply),              unittest.mock.patch.dict(os.environ, {'NVIDIA_API_KEY': 'test'}):
            with self.assertRaises(ValueError):
                llm.call('nvidia', 'some/model', 'hi')

    def test_screen_ignores_categories_outside_principles(self):
        answers = iter(['User Safety: unsafe\nSafety Categories: Unauthorized Advice',
                        'User Safety: unsafe\nSafety Categories: Unauthorized Advice, Guns and Illegal Weapons'])
        with unittest.mock.patch.object(llm, 'call', lambda *a, **k: next(answers)):
            self.assertTrue(llm.screen('maths')[0])
            self.assertFalse(llm.screen('weapons')[0])

    def test_resident_attempt_hides_the_reference_and_keeps_the_answer(self):
        import tempfile, resident, archive
        from pathlib import Path
        task = ('---\ntitle: Sum\nsummary: s\nkind: task\nauthor_model: m\nagent_name: a\nstatus: published\nlicense: CC0-1.0\n---\n'
                'Add 1 to 100.\n```verify\ndef verify(answer):\n    return answer.strip() == "5050"\n```\n```reference\n5050\n```\n')
        reply = ('---\ntitle: Attempt: Sum\nsummary: paired the ends\nkind: attempt\nauthor_model: m\nagent_name: Resident Otter\n'
                 'status: published\nlicense: CC0-1.0\nrelations: attempt W0001@1\n---\n' + 'Pairs of 101, fifty of them. ' * 12 + '\n```answer\n5050\n```')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive.Archive(root).submit(task, 'R1', submitter='x', extra={'kind': 'task'})
            prompts = []
            with unittest.mock.patch.object(llm, 'call', lambda p, m, prompt, **k: prompts.append(prompt) or reply):
                text = resident.attempt(root, 0)
        self.assertNotIn('```reference', prompts[0]); self.assertIn('Add 1 to 100.', prompts[0])
        self.assertTrue(text.rstrip().endswith('```answer\n5050\n```'))

if __name__ == '__main__':
    unittest.main()
