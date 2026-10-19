import tempfile
import shutil
import unittest
from pathlib import Path
import build_foundation_lessons as f


class AuthoredLessons(unittest.TestCase):
    def test_complete_course_and_evidence_mapping(self):
        d = f.compile_lessons()
        self.assertEqual(len(d['chapters']), 12)
        ids = set()
        for ch, p in d['chapters'].items():
            self.assertEqual(len(p['items']), 30)
            self.assertEqual([q['number'] for q in p['items']], list(range(1, 31)))
            self.assertEqual([q['stage'] for q in p['items']], [0]*10+[1]*10+[2]*10)
            for q in p['items']:
                self.assertEqual(len(q['options']), 4)
                self.assertEqual([o['label'] for o in q['options']], list('ABCD'))
                self.assertEqual(sum(o['correct'] for o in q['options']), 1)
                self.assertEqual(next(o['label'] for o in q['options'] if o['correct']), q['answer'])
                self.assertEqual(len({o['text'] for o in q['options']}), 4)
                self.assertTrue(all(len(o['explanation']) >= 10 for o in q['options']))
                ids.add(q['id'])
                self.assertTrue(q['sources'])
                self.assertTrue(all(s['section'].startswith(ch+'.') for s in q['sources']))
            for label in 'ABCD':
                self.assertIn(sum(q['answer'] == label for q in p['items']), (7, 8))
        self.assertEqual(len(ids), 360)

    def test_truncated_chapter_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'authoring'
            shutil.copytree(f.AUTHORING, folder)
            path = folder / '01.txt'
            path.write_text('\n'.join(path.read_text(encoding='utf-8').splitlines()[:-1]), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '需要30题'):
                f.compile_lessons(folder)

    def test_nonexistent_or_wrong_chapter_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'authoring'
            shutil.copytree(f.AUTHORING, folder)
            path = folder / '01.txt'
            path.write_text(path.read_text(encoding='utf-8').replace('1.1|', '2.1|', 1), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '无效或跨章来源'):
                f.compile_lessons(folder)


if __name__ == '__main__':
    unittest.main()
