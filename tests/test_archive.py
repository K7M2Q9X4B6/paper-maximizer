import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
import archive
from archive import Archive, ArchiveError

def doc(title='Practical Cucumber Growing', run='R1', status='published', prev=None, relations='', body='# Body\nCucumbers like sun.'):
    head = [f'title: {title}', 'author_model: test-model', f'run_id: {run}', f'status: {status}']
    head += [f'prev_hash: {prev}'] if prev else []
    head += [f'relations: {relations}'] if relations else []
    return '---\n'+'\n'.join(head)+'\n---\n'+body

class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = Archive(Path(self.tmp.name))
    def tearDown(self):
        self.tmp.cleanup()

    def test_replications_count_only_another_account_or_model(self):
        self.a.submit(doc(), 'R1', submitter='alice')
        rep = doc('Same Result', relations='replication W0001@1')
        self.a.submit(rep, 'R2', submitter='alice')                                         # same account and model
        self.a.submit(rep, 'R3', submitter='bob')                                           # another account
        self.a.submit(rep.replace('test-model', 'other-model'), 'R4', submitter='alice')    # another model
        self.assertEqual(self.a.state('W0001')['replications'], ['W0003@1', 'W0004@1'])

    def test_hash_ignores_bom_and_crlf(self):
        x = archive.normalize('﻿'+doc().replace('\n', '\r\n'))
        self.assertEqual(x, archive.normalize(doc()))
        e = self.a.submit(x, 'R1')
        self.assertEqual((e['work_id'], e['version'], e['prev_hash'], e['author_identity']), ('W0001', 1, 'none', 'self-reported (unverified)'))
        self.assertNotIn(e['sha256'], (self.a.root/e['file']).read_text(encoding='utf-8'))

    def test_versions_chain_and_only_original_submitter_revises(self):
        v1 = self.a.submit(doc(), 'R1')
        with self.assertRaises(ArchiveError):
            self.a.submit(doc(prev='wrong'), 'R1', 'W0001')
        v2 = self.a.submit(doc(prev=v1['sha256'], body='revised'), 'R1', 'W0001')
        self.assertEqual((v2['version'], v2['prev_hash']), (2, v1['sha256']))
        with self.assertRaises(ArchiveError):
            self.a.submit(doc(run='R2', prev=v2['sha256']), 'R2', 'W0001')
        self.assertEqual(self.a.submit(doc(run='R2', relations='revision W0001@2'), 'R2')['work_id'], 'W0002')

    def test_same_account_revises_across_pull_requests(self):
        v1 = self.a.submit(doc(), 'PR-1', submitter='alice')
        v2 = self.a.submit(doc(prev=v1['sha256'], body='v2'), 'PR-7', 'W0001', submitter='alice')
        self.assertEqual((v2['version'], v2['run_id'], v2['submitter']), (2, 'PR-7', 'alice'))
        with self.assertRaises(ArchiveError):
            self.a.submit(doc(prev=v2['sha256']), 'PR-9', 'W0001', submitter='mallory')
        stored = (self.a.root/v2['file']).read_bytes()
        self.assertEqual(stored, archive.normalize(doc(prev=v1['sha256'], body='v2')))  # stored exactly as submitted

    def test_review_needs_another_submitter(self):
        self.a.submit(doc(), 'R1')
        self.a.submit(doc(title='self review', relations='review W0001@1'), 'R1')
        self.assertEqual(self.a.state('W0001')['state'], 'public, unreviewed')
        self.a.submit(doc(title='review', run='R9', relations='review W0001@1'), 'R9')
        self.assertEqual(self.a.state('W0001')['state'], 'public, reviewed')

    def test_retraction_and_requests(self):
        v1 = self.a.submit(doc(), 'R1')
        self.a.submit(doc(title='request', run='R5', relations='retraction-request W0001@1'), 'R5')
        self.assertEqual(self.a.state('W0001')['retraction_requests'], ['W0002@1'])
        self.a.submit(doc(status='retracted', prev=v1['sha256']), 'R1', 'W0001')
        self.assertEqual(self.a.state('W0001')['state'], 'retracted')
        with self.assertRaises(ArchiveError):
            self.a.submit(doc(prev='x'), 'R1', 'W0001')

    def test_verify_detects_edits(self):
        self.a.submit(doc(), 'R1')
        self.assertEqual(self.a.verify(), [])
        f = self.a.root/'works/W0001/v1.md'
        f.write_bytes(f.read_bytes()+b'x')
        self.assertTrue(self.a.verify())
        f.write_bytes(archive.normalize(doc()))
        entry = json.loads(self.a.catalog.read_text(encoding='utf-8'))
        entry['title'] = 'changed'
        self.a.catalog.write_text(json.dumps(entry)+'\n', encoding='utf-8')
        self.assertTrue(any('catalog damaged' in p for p in self.a.verify()))

if __name__ == '__main__':
    unittest.main()
