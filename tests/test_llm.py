import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import llm

class LlmTests(unittest.TestCase):
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

if __name__ == '__main__':
    unittest.main()
