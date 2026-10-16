"""Guard chapter integrity, reviewed corrections, and safe legacy enrichment."""
import contextlib
import io
import pathlib
import re
import tempfile
import unittest

from enhance_learning_doc import insert_intro_and_summary

ROOT = pathlib.Path(__file__).resolve().parent.parent


class KnowledgeContentTests(unittest.TestCase):
    def test_chapter_structure_and_self_tests(self):
        text = (ROOT / 'docs/ACP高频知识点总结.md').read_text(encoding='utf-8')
        chapters = re.split(r'^## (?=\d+\.)', text, flags=re.M)
        self.assertEqual(len(chapters), 13)
        self.assertNotIn('本章总结与自测', chapters[0])
        self.assertIn('第 5 章按需微调，第 6 章部署上线', chapters[0])
        counts = [12, 11, 10, 12, 10, 12, 9, 10, 11, 9, 10, 8]
        for n, (chapter, expected) in enumerate(zip(chapters[1:], counts), 1):
            with self.subTest(chapter=n):
                headings = re.findall(r'^### (\d+)\.(\d+) ', chapter, re.M)
                self.assertEqual(headings, [(str(n), str(i)) for i in range(1, expected + 1)])
                self.assertEqual(chapter.count(':::qa'), 1)
                self.assertIn('**解析', chapter)
        self.assertIn('Precision@k × v_k', text)
        self.assertIn('0.833', text)
        self.assertNotIn('各片段 precision 分之和 / 相关片段总数', text)
        self.assertNotIn('微调不更新模型的知识截止时间', text)
        self.assertNotIn('共用一套 API Key', text)

    def test_enrichment_stays_in_its_chapter_and_is_idempotent(self):
        source = ('# Demo\n\n## 如何使用本手册\n\n既有前言。\n\n'
                  '## 1. 大模型基础\n\n**本章要解决的问题**：测试。\n\n'
                  '### 1.1 内容\n\n第一章结尾。\n\n---\n\n'
                  '## 2. 提示工程\n\n**本章要解决的问题**：测试。\n\n'
                  '### 2.1 内容\n\n第二章结尾。\n\n---\n\n'
                  '## 附录\n\n附录内容。\n')
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / 'sample.md'
            target.write_text(source, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                insert_intro_and_summary(target)
                first = target.read_text(encoding='utf-8')
                insert_intro_and_summary(target)
            self.assertEqual(target.read_text(encoding='utf-8'), first)
            self.assertLess(first.index('第一章结尾'), first.index('#### 大模型基础：'))
            self.assertLess(first.index('#### 大模型基础：'), first.index('## 2. 提示工程'))
            self.assertLess(first.index('第二章结尾'), first.index('#### 提示工程：'))
            self.assertLess(first.index('#### 提示工程：'), first.index('## 附录'))
            self.assertEqual(re.findall(r'^### .*', first, re.M), re.findall(r'^### .*', source, re.M))

    def test_current_document_does_not_get_duplicate_summaries(self):
        source = (ROOT / 'docs/ACP高频知识点总结.md').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / 'copy.md'
            target.write_text(source, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                insert_intro_and_summary(target)
            self.assertEqual(target.read_text(encoding='utf-8'), source)


if __name__ == '__main__':
    unittest.main()
