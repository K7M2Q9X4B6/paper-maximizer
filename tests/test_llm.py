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
        def fake(provider, model, root):
            tried.append(model)
            if len(tried) < 2:
                raise OSError('rate limited')
            return 'work'
        with unittest.mock.patch.object(resident, 'draft', fake):
            self.assertEqual(resident.write(), 'work')
        self.assertEqual(tried, [m for _, m in llm.MODELS['writer'][:2]])

if __name__ == '__main__':
    unittest.main()
