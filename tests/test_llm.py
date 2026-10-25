import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import llm

class LlmTests(unittest.TestCase):
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

if __name__ == '__main__':
    unittest.main()
