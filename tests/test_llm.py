import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import llm

class LlmTests(unittest.TestCase):
    def test_only_free_openrouter_models(self):
        with self.assertRaises(ValueError):
            llm.call('openrouter', 'some/paid-model', 'hi')
        self.assertTrue(all(m.endswith(':free') for p, ms in [(p, m) for ms in llm.MODELS.values() for p, m in ms] for m in [ms] if p == 'openrouter'))

if __name__ == '__main__':
    unittest.main()
