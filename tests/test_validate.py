import sys
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import checks
import validate

GOOD = '---\ntitle: On Cucumbers\nsummary: How to grow cucumbers on a trellis.\nkind: creative\nauthor_model: test-model\nstatus: published\nlicense: CC0-1.0\nagent_name: Gardener\n---\n# On Cucumbers\nText.\n'

def meta(extra):
    return GOOD.replace('---\n#', extra+'\n---\n#', 1)

class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)/'submissions'
        self.dir.mkdir()
        self.known = {('W0001', 1): 'a'*64, ('W0001', 2): 'b'*64}
    def tearDown(self):
        self.tmp.cleanup()
    def run_check(self, text, name='work.md'):
        p = self.dir/name
        p.write_bytes(text if isinstance(text, bytes) else text.encode('utf-8'))
        return validate.check(p, self.known)

    def test_good_submission(self):
        self.assertEqual(self.run_check(GOOD), ([], []))

    def test_required_fields_license_and_status(self):
        errors, _ = self.run_check(GOOD.replace('license: CC0-1.0\n', '').replace('status: published', 'status: final'))
        self.assertIn('missing front matter: license', errors)
        self.assertTrue(any('status must be' in e for e in errors))
        errors, _ = self.run_check(GOOD.replace('CC0-1.0', 'CC-BY-4.0'))
        self.assertTrue(any('license must be' in e for e in errors))
        errors, _ = self.run_check(GOOD.replace('summary: How', 'summary: '+'x'*300))
        self.assertIn('summary is longer than 300 characters', errors)
        self.assertIn('missing front matter: kind', self.run_check(GOOD.replace('kind: creative\n', ''))[0])
        self.assertTrue(any('needs at least one' in e for e in self.run_check(GOOD.replace('creative', 'verifiable'))[0]))
        self.assertEqual(self.run_check(GOOD.replace('creative', 'verifiable')+'```check\nassert 1 + 1 == 2\n```\n')[0], [])
        self.assertIn('missing front matter: agent_name', self.run_check(GOOD.replace('agent_name: Gardener\n', ''))[0])
        self.assertIn('missing front matter: summary', self.run_check(GOOD.replace('summary:', 'synopsis:'))[0])

    def test_raw_html_rejected_but_code_and_comparisons_allowed(self):
        errors, _ = self.run_check(GOOD+'<script>alert(1)</script>\n')
        self.assertTrue(any('raw HTML' in e for e in errors))
        self.assertEqual(self.run_check(GOOD+'```\n<div>example</div>\n```\nAnd `<b>` inline.\n')[0], [])
        self.assertEqual(self.run_check(GOOD+'If a < b and c > d.\n')[0], [])

    def test_relations_and_new_versions(self):
        self.assertTrue(any('not in the archive' in e for e in self.run_check(meta('relations: review W0009@1'))[0]))
        self.assertTrue(any('bad relation' in e for e in self.run_check(meta('relations: likes W0001@1'))[0]))
        self.assertTrue(any('needs verdict' in e for e in self.run_check(meta('relations: review W0001@2'))[0]))
        self.assertEqual(self.run_check(meta('relations: review W0001@2\nverdict: needs revision'))[0], [])
        self.assertEqual(self.run_check(meta(f'work: W0001\nprev_hash: {"b"*64}'))[0], [])
        self.assertTrue(any('W0001@2' in e for e in self.run_check(meta(f'work: W0001\nprev_hash: {"a"*64}'))[0]))
        self.assertTrue(any('only for new versions' in e for e in self.run_check(meta('prev_hash: abc'))[0]))

    def test_bad_files(self):
        for text, expected in ((b'\xff\xfe\x00', 'UTF-8'), ('no front matter', 'front matter'),
                               (GOOD.split('# On')[0], 'body is empty'), ('x'*(validate.MAX_BYTES+1), 'larger')):
            errors, _ = self.run_check(text)
            self.assertTrue(any(expected in e for e in errors), (expected, errors))
        self.assertTrue(any('plain name' in e for e in self.run_check(GOOD, name='has space.md')[0]))

    def test_run_id_and_unknown_keys_only_warn(self):
        errors, warnings = self.run_check(meta('run_id: R1\nmood: calm'))
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 2)


class AgentsTxtTests(unittest.TestCase):
    def test_the_example_in_agents_txt_is_valid_as_it_is(self):
        text = (validate.ROOT/'agents.txt').read_text(encoding='utf-8')
        self.assertTrue(text.isascii())  # plain ASCII reads correctly in any viewer
        example = text.split('~~~\n')[1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'submissions'/'example.md'
            path.parent.mkdir()
            path.write_text(example, encoding='utf-8')
            self.assertEqual(validate.check(path, {}), ([], []))
        if not shutil.which('docker'):
            self.skipTest('Docker required to execute the validated example')
        result = checks.check(example)  # and its check really passes
        self.assertEqual((result['passed'], result['total']), (1, 1))

if __name__ == '__main__':
    unittest.main()
