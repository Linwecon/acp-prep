import copy
import unittest
import build_foundation as f


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.q = {'seq': '0001', 'type': 0, 'stem': 'Token 的作用是什么？',
                  'options': [{'option_label': 'A', 'option_text': '甲'}, {'option_label': 'B', 'option_text': '乙'}],
                  'answer': 'A', 'analysis': '用于演示单元选择的解析文字，不代表知识正确性验证。'}

    def test_invalid_answer_and_type(self):
        self.assertEqual(f.inspect(self.q), [])
        self.assertTrue(f.inspect({**self.q, 'answer': 'Z'}))
        self.assertTrue(f.inspect({**self.q, 'answer': 'A,B'}))

    def test_conflicting_duplicates_excluded_and_source_unchanged(self):
        b = {'chapters': {str(i): str(i) for i in range(1, 13)}, 'questions_by_chapter': {'1': [self.q, {**self.q, 'seq': '0002', 'answer': 'B'}]}}
        before = copy.deepcopy(b)
        rows, packs = f.build(b)
        self.assertEqual(len(rows), 2)
        self.assertIn('同题异答', rows[0]['reason'])
        self.assertEqual(packs['1']['count'], 0)
        self.assertEqual(b, before)

    def test_deleted_questions_excluded_and_gaps_explicit(self):
        b = {'chapters': {str(i): str(i) for i in range(1, 13)}, 'questions_by_chapter': {'1': [self.q, {**self.q, 'seq': '0002', 'deleted': True}]}}
        rows, packs = f.build(b)
        self.assertEqual(rows, [])
        self.assertEqual(packs['1']['count'], 1)
        self.assertEqual(sum(u['gap'] for u in packs['1']['units']), 7)


if __name__ == '__main__':
    unittest.main()
