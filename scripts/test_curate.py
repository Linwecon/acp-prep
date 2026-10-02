# -*- coding: utf-8 -*-
"""题库治理核心行为测试（纯本地，无 LLM 调用）

运行: python scripts/test_curate.py -v

覆盖:
- 软删除/恢复/幂等/回滚（含运行时 .js 不含软删除题）
- 答案修正保存旧版本、重复执行不重复写入、可回滚
- 语义查重阈值与分组
- 低质规则信号（残缺/重复选项/送分题）
- 章节规则初筛不误伤前置知识题
"""
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import curate_core as cc  # noqa: E402
import quiz_curate as qc  # noqa: E402
import verify_disputed as vd  # noqa: E402


def make_q(ch, seq, stem, options, answer, analysis="解析内容", diff="进阶"):
    return {
        "seq": str(seq).zfill(4), "type": 0, "stem": stem,
        "options": [{"option_label": "ABCD"[i], "option_text": t} for i, t in enumerate(options)],
        "answer": answer, "analysis": analysis, "chapter": ch,
        "difficulty_score": 2, "difficulty_label": diff, "difficulty_sort": 2,
    }


def make_bank():
    qs1 = [
        make_q(1, 1, "大语言模型的上下文窗口指的是什么？", ["模型参数量", "模型能处理的最大输入长度", "训练数据量", "显存大小"], "B"),
        make_q(1, 2, "关于 Transformer 自注意力机制的描述，正确的是？", ["并行计算序列表示", "只能串行", "不使用权重", "无注意力"], "A"),
        # 前置知识题：考点属第 1 章，但顺带提到微调（第 5 章关键词），不应被判为错放
        make_q(1, 3, "预训练大语言模型在推理阶段的主要局限是什么？", ["无法泛化", "知识截止后无法感知新事实", "不能生成文本", "必须联网"], "B",
               analysis="预训练模型存在知识截止（知识截止）局限，微调也难以注入实时知识。"),
        # 错放样例：RAG 切片题放在第 1 章
        make_q(1, 4, "RAG 流程中切块（Chunk）大小的主要影响是？", ["检索召回与上下文完整性的权衡", "模型参数量", "无影响", "只影响显存"], "A",
               analysis="切片策略影响向量检索召回效果。"),
    ]
    qs3 = [
        make_q(3, 1, "向量数据库在 RAG 中的作用是？", ["存储并检索向量化表示", "训练模型", "生成文本", "压缩模型"], "A"),
        make_q(3, 2, "与向量数据库在 RAG 中的作用完全相同的描述是哪项？", ["存储并检索向量化表示", "训练模型", "生成文本", "压缩模型"], "A"),
    ]
    return {
        "chapters": {"1": "大模型基础", "3": "RAG 检索增强生成"},
        "questions_by_chapter": {"1": qs1, "3": qs3},
        "total": 6,
    }


class CurateTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(self.tmp.name)
        self._old = (cc.JSON_PATH, cc.JS_PATH, cc.BACKUP_DIR, cc.LEDGER_PATH)
        cc.JSON_PATH = tmp / "quiz_categorized.json"
        cc.JS_PATH = tmp / "quiz_categorized.js"
        cc.BACKUP_DIR = tmp / "backup"
        cc.LEDGER_PATH = tmp / "curate" / "ledger.json"
        self.bank = make_bank()
        cc.JSON_PATH.write_text(json.dumps(self.bank, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        (cc.JSON_PATH, cc.JS_PATH, cc.BACKUP_DIR, cc.LEDGER_PATH) = self._old
        self.tmp.cleanup()


class TestSoftDelete(CurateTestBase):

    def test_soft_delete_restore_and_js_exclusion(self):
        bank = cc.load_bank()
        r = cc.soft_delete(bank, [{"qid": "1-0004", "reason": "错放且超纲测试"}], source="test")
        self.assertEqual(r["applied"], 1)
        cc.write_bank(bank)
        # JSON 主文件保留数据
        raw = json.loads(cc.JSON_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(raw["questions_by_chapter"]["1"]), 4)
        self.assertTrue(raw["questions_by_chapter"]["1"][3]["deleted"])
        self.assertEqual(raw["active_total"], 5)
        # 运行时 .js 不含软删除题
        js = cc.JS_PATH.read_text(encoding="utf-8")
        import re
        m = re.search(r"QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\});", js, re.S)
        data = json.loads(m.group(1))
        self.assertEqual(len(data["1"]), 3)
        self.assertNotIn("切块", js)
        self.assertIn("向量数据库", js)

    def test_soft_delete_idempotent(self):
        bank = cc.load_bank()
        cc.soft_delete(bank, [{"qid": "1-0004", "reason": "a"}], source="test")
        r2 = cc.soft_delete(bank, [{"qid": "1-0004", "reason": "b"}], source="test")
        self.assertEqual(r2["applied"], 0)
        self.assertEqual(r2["skipped"][0]["why"], "已是软删除状态")

    def test_restore(self):
        bank = cc.load_bank()
        cc.soft_delete(bank, [{"qid": "1-0004", "reason": "a"}], source="test")
        r = cc.restore(bank, ["1-0004"], source="test")
        self.assertEqual(r["applied"], 1)
        self.assertNotIn("deleted", bank["questions_by_chapter"]["1"][3])

    def test_rollback_soft_delete(self):
        bank = cc.load_bank()
        r = cc.soft_delete(bank, [{"qid": "1-0004", "reason": "a"}], source="test")
        cc.write_bank(bank)
        cc.append_batch("soft_delete", "test", r["ledger_items"], batch_id="sd1")
        done, _ = cc.rollback_batch("sd1", dry_run=False)
        self.assertEqual(done, 1)
        bank2 = cc.load_bank()
        self.assertFalse(bank2["questions_by_chapter"]["1"][3].get("deleted"))


class TestAnswerFix(CurateTestBase):

    def test_fix_records_history_and_rollback(self):
        bank = cc.load_bank()
        r = cc.apply_answer_fix(bank, [{"qid": "1-0001", "final": ["A"], "analysis": "新解析",
                                        "reason": "投票修正", "evidence": {"tally": {"m1": ["A"]}}}],
                                source="test", batch_id="b1")
        self.assertEqual(r["applied"], 1)
        q = bank["questions_by_chapter"]["1"][0]
        self.assertEqual(q["answer"], "A")
        self.assertEqual(q["answer_history"][0]["old_answer"], "B")
        self.assertEqual(q["answer_history"][0]["batch_id"], "b1")
        self.assertEqual(q["analysis"], "新解析")
        # 台账
        cc.append_batch("answer_fix", "test", r["ledger_items"], batch_id="b1")
        ledger = cc.load_ledger()
        self.assertEqual(ledger["batches"][-1]["kind"], "answer_fix")
        # 回滚（从磁盘读取 → 先落盘）
        cc.write_bank(bank, backup=False)
        done, _ = cc.rollback_batch("b1", dry_run=False)
        self.assertEqual(done, 1)
        bank2 = cc.load_bank()
        q2 = bank2["questions_by_chapter"]["1"][0]
        self.assertEqual(q2["answer"], "B")
        self.assertEqual(q2["analysis"], "解析内容")
        self.assertFalse(q2.get("answer_history"))

    def test_fix_idempotent(self):
        bank = cc.load_bank()
        cc.apply_answer_fix(bank, [{"qid": "1-0001", "final": ["A"]}], source="test", batch_id="b1")
        r2 = cc.apply_answer_fix(bank, [{"qid": "1-0001", "final": ["A"]}], source="test", batch_id="b1")
        self.assertEqual(r2["applied"], 0)
        q = bank["questions_by_chapter"]["1"][0]
        self.assertEqual(len(q["answer_history"]), 1)

    def test_unconfirmed_not_double_counted(self):
        """重复执行不重复写入（apply 幂等已测），这里补：不同批次同答案不追加历史。"""
        bank = cc.load_bank()
        cc.apply_answer_fix(bank, [{"qid": "1-0001", "final": ["A"]}], source="test", batch_id="b1")
        r = cc.apply_answer_fix(bank, [{"qid": "1-0001", "final": ["A"], "analysis": "解析内容"}],
                                source="test", batch_id="b2")
        self.assertEqual(r["applied"], 0)
        self.assertEqual(len(bank["questions_by_chapter"]["1"][0]["answer_history"]), 1)


class TestDuplicates(CurateTestBase):

    def test_find_duplicates(self):
        bank = cc.load_bank()
        qs = cc.bank_questions(bank)
        groups = cc.dup_groups(qs, threshold=0.6)
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0]), {"3-0001", "3-0002"})

    def test_distinct_not_flagged(self):
        bank = cc.load_bank()
        qs = [cc.bank_questions(bank)[0], cc.bank_questions(bank)[1]]
        self.assertEqual(cc.dup_groups(qs, threshold=0.6), [])


class TestQualitySignals(CurateTestBase):

    def test_broken_question(self):
        q = make_q(1, 9, "短", ["A", "A"], "A", analysis="")
        score, sigs = qc.quality_signals(q)
        self.assertGreaterEqual(score, 3)
        self.assertIn("题干过短(1字)", " ".join(sigs))

    def test_gift_question(self):
        """送分题：正确选项原文出现在题干。"""
        q = make_q(1, 9, "本题正确说法：模型能处理的最大输入长度决定了上下文窗口的容量",
                   ["模型能处理的最大输入长度", "别的选项一", "别的选项二", "别的选项三"], "A")
        score, sigs = qc.quality_signals(q)
        self.assertIn("正确选项在题干中原文出现(送分题)", sigs)

    def test_normal_question_low_score(self):
        bank = cc.load_bank()
        q = bank["questions_by_chapter"]["1"][0]
        score, _ = qc.quality_signals(q)
        self.assertLess(score, 3)


class TestChapterRuleCandidates(CurateTestBase):

    def test_prerequisite_question_not_flagged(self):
        """前置知识题（考点属本章）不会被规则初筛判为候选。"""
        bank = cc.load_bank()
        qs = cc.bank_questions(bank)
        cands = qc.rule_candidates_chapter(qs, threshold=5)
        cands_qids = {c["qid"] for c in cands}
        self.assertNotIn("1-0003", cands_qids)  # 预训练题，考点在第 1 章

    def test_misplaced_question_flagged(self):
        bank = cc.load_bank()
        qs = cc.bank_questions(bank)
        cands = qc.rule_candidates_chapter(qs, threshold=5)
        cands_qids = {c["qid"] for c in cands}
        self.assertIn("1-0004", cands_qids)  # RAG 切片题错放在第 1 章

    def test_cross_chapter_not_deleted_by_rule(self):
        """规则层只产生候选，不直接删除：候选清单不包含删除动作。"""
        bank = cc.load_bank()
        qs = cc.bank_questions(bank)
        cands = qc.rule_candidates_chapter(qs, threshold=5)
        for c in cands:
            self.assertIn("predicted_chapter", c)
            self.assertNotIn("action=remove", str(c))


class TestFingerprint(CurateTestBase):

    def _q(self):
        return make_q(1, 1, "测试题干内容", ["选项一", "选项二", "选项三", "选项四"], "A")

    def test_stable_and_sensitive_to_content(self):
        q = self._q()
        fp1 = cc.q_fingerprint(q)
        fp2 = cc.q_fingerprint(dict(q))
        self.assertEqual(fp1, fp2)
        q2 = self._q()
        q2["stem"] = "修改后的题干内容"
        self.assertNotEqual(fp1, cc.q_fingerprint(q2))
        q3 = self._q()
        q3["options"][1]["option_text"] = "被修改的选项"
        self.assertNotEqual(fp1, cc.q_fingerprint(q3))

    def test_answer_change_not_stale(self):
        """答案本身是校验输出：答案变化不使指纹失效，题干/选项变化才失效。"""
        q = self._q()
        rec = {"fingerprint": cc.q_fingerprint(q)}
        q2 = self._q()
        q2["answer"] = "B"
        self.assertFalse(cc.fingerprint_stale(rec, q2))
        q3 = self._q()
        q3["stem"] = "别的题干"
        self.assertTrue(cc.fingerprint_stale(rec, q3))

    def test_missing_fingerprint_is_unbound_not_stale(self):
        q = self._q()
        self.assertFalse(cc.fingerprint_stale({}, q))

    def test_apply_rejects_stale_result(self):
        """带指纹的修正：指纹失配时 apply_answer_fix 由调用方守卫（此处验证守卫函数）。"""
        bank = cc.load_bank()
        q = bank["questions_by_chapter"]["1"][0]
        rec = {"fingerprint": cc.q_fingerprint(q), "final": ["A"]}
        self.assertFalse(cc.fingerprint_stale(rec, q))
        q["stem"] += "（题干被修改）"
        self.assertTrue(cc.fingerprint_stale(rec, q))


class TestEvidenceQuote(unittest.TestCase):

    SRC = ("RAG 的核心思想是开卷考试。文本切片策略影响召回率与上下文完整性，"
           "重排序模型通过交叉编码提升精度。Embedding 将文本映射为向量。")

    def test_exact(self):
        r = cc.locate_quote("文本切片策略影响召回率与上下文完整性。", self.SRC)
        self.assertTrue(r["quote_found"])
        self.assertEqual(r["unmatched"], [])
        seg = r["segments"][0]
        self.assertEqual(seg["mode"], "exact")
        self.assertIn("文本切片", seg["excerpt"])  # 命中位置给出原文片段

    def test_fabricated_conclusion_not_passed(self):
        """真实短句 + 编造结论：整体 quote_found=False，编造段落单独列出。"""
        r = cc.locate_quote("文本切片策略影响召回率。因此所有模型必须关闭温度参数才能运行。",
                            self.SRC)
        self.assertFalse(r["quote_found"])  # 不允许"部分命中"放行整条引用
        self.assertEqual(len(r["unmatched"]), 1)
        self.assertIn("温度参数", r["unmatched"][0])
        self.assertTrue(r["segments"][0]["located"])  # 真实短句段仍被定位，供人工参考

    def test_missing(self):
        r = cc.verify_evidence_quote("这句话完全不在原文中出现，纯属编造的证据引用", self.SRC)
        self.assertFalse(r["verified"])

    def test_multi_segment_all_must_match(self):
        r = cc.locate_quote("文本切片策略影响召回率与上下文完整性。重排序模型通过交叉编码提升精度。",
                            self.SRC)
        self.assertTrue(r["quote_found"])
        r2 = cc.locate_quote("文本切片策略影响召回率与上下文完整性。这句是编造的结论性陈述。",
                             self.SRC)
        self.assertFalse(r2["quote_found"])


class TestMoveQuestions(CurateTestBase):

    def test_move_and_rollback(self):
        bank = cc.load_bank()
        r = cc.move_questions(bank, [{"qid": "1-0004", "to": 3, "reason": "错放"}], {1, 3})
        self.assertEqual(len(r["ledger_items"]), 1)
        li = r["ledger_items"][0]
        self.assertEqual((li["from"], li["to"]), (1, 3))
        cc.write_bank(bank, backup=False)
        cc.append_batch("move", "test", r["ledger_items"], batch_id="mv1")
        done, _ = cc.rollback_batch("mv1", dry_run=False)
        self.assertEqual(done, 1)
        bank2 = cc.load_bank()
        # 回滚后题回到第 1 章、seq 还原
        q = next(x for x in bank2["questions_by_chapter"]["1"] if x["stem"].startswith("RAG"))
        self.assertEqual(str(q["seq"]).zfill(4), "0004")

    def test_move_seq_conflict(self):
        bank = cc.load_bank()
        r = cc.move_questions(bank, [{"qid": "1-0004", "to": 3, "reason": "错放"}], {1, 3})
        # 第 3 章已有 0001/0002，无 0004 → 不冲突
        self.assertEqual(r["ledger_items"][0]["after_seq"], "0004")
        r2 = cc.move_questions(bank, [{"qid": "3-0002", "to": 1, "reason": "x"}], {1, 3})
        # 1-0004 已移走，第 1 章现有 0001-0003 → 0002 与现有冲突，重编号为最大+1=0004
        self.assertEqual(r2["ledger_items"][0]["after_seq"], "0004")


class TestQuotaAndExclusions(CurateTestBase):

    def test_quota_sums_to_gap(self):
        existing = [make_q(1, i, f"题干{i}", ["a", "b", "c", "d"], "A",
                           diff=["入门", "进阶", "挑战"][i % 3]) for i in range(1, 6)]
        existing[0]["type"] = 1
        quota = qc.quota_for(10, existing)
        self.assertEqual(sum(quota["type_quota"].values()), 10)
        self.assertEqual(sum(quota["difficulty_quota"].values()), 10)

    def test_quota_fallback(self):
        quota = qc.quota_for(10, [])
        self.assertEqual(quota["type_quota"]["multi"], 3)

    def test_exclusion_sets(self):
        """缺口统计排除：答案未确认 / 低质待修复待复核 / 章节待处理。"""
        tmp = pathlib.Path(self.tmp.name)
        vf = tmp / "verify_final.json"
        vf.write_text(json.dumps({"1-0001": {"status": "fix"}, "1-0002": {"status": "undecided"},
                                  "1-0003": {"status": "keep"}}, ensure_ascii=False), encoding="utf-8")
        qa = tmp / "quality_audit.json"
        qa.write_text(json.dumps({"items": [
            {"qid": "3-0001", "llm": {"verdict": "fixable"}},
            {"qid": "3-0002", "llm": {"verdict": "review"}},
            {"qid": "1-0001", "llm": {"verdict": "ok"}},
        ]}, ensure_ascii=False), encoding="utf-8")
        ca = tmp / "chapter_audit.json"
        ca.write_text(json.dumps({"items": [
            {"qid": "3-0001", "llm": {"category": "unsure"}},
            {"qid": "3-0002", "llm": {"category": "own"}},
        ]}, ensure_ascii=False), encoding="utf-8")
        old = (qc.VERIFY_FINAL, qc.CHAPTER_OUT)
        qc.VERIFY_FINAL, qc.CHAPTER_OUT = vf, ca
        try:
            qc.CURATE_DIR = tmp  # quality_audit.json 读取位置
            ex = qc.load_exclusion_sets()
        finally:
            qc.VERIFY_FINAL, qc.CHAPTER_OUT = old
        self.assertEqual(ex.get("1-0001"), "答案未确认(fix)")
        self.assertIn("答案未确认", ex.get("1-0002", ""))
        self.assertNotIn("1-0003", ex)            # keep 不排除
        self.assertEqual(ex.get("3-0001"), "低质(fixable)")  # 章节待处理 setdefault 不覆盖
        self.assertEqual(ex.get("3-0002"), "低质(review)")


class TestFullCheckChain(CurateTestBase):
    """七段检查链（LLM 调用全部 mock）：答案一致 ≠ 全部通过；语义重复/证据缺失会被拦截。"""

    SECTION = "RAG 的核心思想是开卷考试。文本切片策略影响召回率与上下文完整性，重排序提升精度。"

    def fake_chat_duplicate(self, cfg, model, messages, max_tokens=800, temperature=0, timeout=90):
        user = messages[-1]["content"]
        if "是否语义重复" in user:
            return json.dumps({"duplicate": False, "same_as": "", "reason": "考点角度不同"})
        if "是否真正属于" in user:
            return json.dumps({"belongs": True, "reason": "属本章"})
        if "质量审核员" in user:
            return json.dumps({"dims": {"goal_match": True, "logic_sound": True, "clarity": True,
                                        "distractors": True, "no_leak": True, "difficulty": True},
                               "fatal_logic": False, "defects": [], "fix_suggestion": "",
                               "verdict": "ok", "reason": "合格"})
        if "请独立解答" in user:
            return json.dumps({"answer": "A", "confidence": "high", "basis": "x"})
        if "核对这道" in user:
            return json.dumps({"supported": True, "quote": "文本切片策略影响召回率与上下文完整性", "note": ""})
        return None

    def fake_chat_semantic_dup(self, cfg, model, messages, max_tokens=800, temperature=0, timeout=90):
        user = messages[-1]["content"]
        if "是否语义重复" in user:
            return json.dumps({"duplicate": True, "same_as": "候选1", "reason": "同考点同路径"})
        return self.fake_chat_duplicate(cfg, model, messages)

    def fake_chat_bad_evidence(self, cfg, model, messages, max_tokens=800, temperature=0, timeout=90):
        user = messages[-1]["content"]
        if "核对这道" in user:
            return json.dumps({"supported": True, "quote": "这句引用在原文中根本不存在纯属编造", "note": ""})
        return self.fake_chat_duplicate(cfg, model, messages)

    def _q(self):
        return make_q(3, 99, "关于文本切片策略对新题考查的正确描述是？",
                      ["甲", "乙", "丙", "丁"], "A", analysis="x")

    def _run(self, fake, existing_keys=None, q=None):
        """降低 sim 阈值以确保 sem_dup 阶段被触发（模拟真实库中存在近似题）。"""
        old_chat, old_soft = qc.chat, qc.SIM_SOFT
        qc.chat = fake
        qc.SIM_SOFT = 0.05
        try:
            bank = cc.load_bank()
            pool = [dict(q, qid=q.get("qid") or qc.qid_of(q)) for q in cc.bank_questions(bank)]
            return qc.full_check_chain({}, "m", q or self._q(), pool, existing_keys or set(),
                                       set(), {}, self.SECTION)
        finally:
            qc.chat, qc.SIM_SOFT = old_chat, old_soft

    def test_all_pass(self):
        passed, checks = self._run(self.fake_chat_duplicate)
        self.assertTrue(passed)
        stages = [c["stage"] for c in checks]
        self.assertEqual(stages, ["format", "sim_text", "sem_dup", "chapter", "quality", "solve", "evidence"])
        self.assertTrue(all(c["passed"] for c in checks))

    def test_semantic_dup_rejected(self):
        passed, checks = self._run(self.fake_chat_semantic_dup)
        self.assertFalse(passed)
        failed = [c for c in checks if not c["passed"]]
        self.assertEqual(failed[0]["stage"], "sem_dup")
        self.assertIn("语义重复", failed[0]["detail"])

    def test_fabricated_evidence_rejected(self):
        passed, checks = self._run(self.fake_chat_bad_evidence)
        self.assertFalse(passed)
        failed = [c for c in checks if not c["passed"]]
        self.assertEqual(failed[0]["stage"], "evidence")

    def test_exact_dup_rejected_by_format_stage(self):
        bank = cc.load_bank()
        target = cc.bank_questions(bank)[4]  # 3-0001
        old_chat, old_soft = qc.chat, qc.SIM_SOFT
        qc.chat, qc.SIM_SOFT = self.fake_chat_duplicate, 0.05
        try:
            pool = [dict(q, qid=q.get("qid") or qc.qid_of(q)) for q in cc.bank_questions(bank)]
            q = self._q()
            q["stem"] = target["stem"]
            passed, checks = qc.full_check_chain({}, "m", q, pool,
                                                 {cc.stem_key(target["stem"])}, set(), {}, self.SECTION)
        finally:
            qc.chat, qc.SIM_SOFT = old_chat, old_soft
        self.assertFalse(passed)
        self.assertEqual(checks[0]["stage"], "format")
        self.assertIn("重复", checks[0]["detail"])

    def test_no_section_text_fails_evidence(self):
        """章节原文缺失时证据核对不通过（不得跳过）。"""
        old_chat, old_soft = qc.chat, qc.SIM_SOFT
        qc.chat, qc.SIM_SOFT = self.fake_chat_duplicate, 0.05
        try:
            bank = cc.load_bank()
            pool = [dict(q, qid=q.get("qid") or qc.qid_of(q)) for q in cc.bank_questions(bank)]
            passed, checks = qc.full_check_chain({}, "m", self._q(), pool, set(), set(), {}, "")
        finally:
            qc.chat, qc.SIM_SOFT = old_chat, old_soft
        self.assertFalse(passed)
        failed = [c for c in checks if not c["passed"]]
        self.assertEqual(failed[0]["stage"], "evidence")

    def test_high_similarity_different_condition_not_rejected(self):
        """高文本相似度但条件不同（如含否定词）：sim_text 不直接拒绝，语义判定为不重复则通过。"""
        old_chat, old_soft = qc.chat, qc.SIM_SOFT
        qc.chat = self.fake_chat_duplicate
        qc.SIM_SOFT = 0.99  # 极端阈值：任何共同 bigram 都产生候选，但仍不直接判重
        try:
            bank = cc.load_bank()
            pool = [dict(q, qid=q.get("qid") or qc.qid_of(q)) for q in cc.bank_questions(bank)]
            q = self._q()
            passed, checks = qc.full_check_chain({}, "m", q, pool, set(), set(), {}, self.SECTION)
        finally:
            qc.chat, qc.SIM_SOFT = old_chat, old_soft
        self.assertTrue(passed)  # 高相似仅产生候选，语义判定 duplicate=false → 放行
        sim_stage = next(c for c in checks if c["stage"] == "sim_text")
        self.assertTrue(sim_stage["passed"])


class TestFixGuard(CurateTestBase):
    """统一答案修正守卫：无指纹旧结果 / 失效结果 / 格式错误 / 证据不足全部拒绝。"""

    def _q(self):
        return make_q(1, 1, "测试题干内容", ["选项一", "选项二", "选项三", "选项四"], "A")

    def test_unbound_rejected(self):
        q = self._q()
        ok, why, _ = cc.check_fix_entry({"qid": "1-0001", "final": ["B"]}, q)
        self.assertFalse(ok)
        self.assertIn("不得补绑", why)

    def test_stale_rejected(self):
        q = self._q()
        fp = cc.q_fingerprint(q)
        q["stem"] = "修改后的题干"
        ok, why, _ = cc.check_fix_entry({"qid": "1-0001", "final": ["B"], "fingerprint": fp}, q)
        self.assertFalse(ok)
        self.assertIn("失效", why)

    def test_format_rejected(self):
        q = self._q()
        fp = cc.q_fingerprint(q)
        ok, why, _ = cc.check_fix_entry({"final": ["E"], "fingerprint": fp}, q)
        self.assertFalse(ok)
        self.assertIn("不在选项中", why)
        ok, why, _ = cc.check_fix_entry({"final": ["B", "C"], "fingerprint": fp}, q)
        self.assertFalse(ok)
        self.assertIn("单选", why)
        ok, why, _ = cc.check_fix_entry({"final": ["Z"], "fingerprint": fp}, q)
        self.assertFalse(ok)  # 非法字母过滤后为空
        self.assertIn("答案为空", why)

    def test_evidence_required(self):
        q = self._q()
        fp = cc.q_fingerprint(q)
        ok, why, _ = cc.check_fix_entry({"final": ["B"], "fingerprint": fp}, q)
        self.assertFalse(ok)
        self.assertIn("证据", why)
        ok, why, _ = cc.check_fix_entry({"final": ["B"], "fingerprint": fp,
                                         "external_evidence": {"supported": True,
                                                               "quote_found": False,
                                                               "fingerprint": fp}}, q)
        self.assertFalse(ok)  # 引用未定位成功 → 不放行

    def test_evidence_fingerprint_mismatch(self):
        q = self._q()
        fp = cc.q_fingerprint(q)
        ok, why, _ = cc.check_fix_entry({"final": ["B"], "fingerprint": fp,
                                         "external_evidence": {"supported": True,
                                                               "quote_found": True,
                                                               "fingerprint": "别的版本"}}, q)
        self.assertFalse(ok)
        self.assertIn("版本不一致", why)

    def test_valid_pass(self):
        q = self._q()
        fp = cc.q_fingerprint(q)
        ok, why, info = cc.check_fix_entry({"final": ["B"], "fingerprint": fp,
                                            "external_evidence": {"supported": True,
                                                                  "quote_found": True,
                                                                  "fingerprint": fp}}, q)
        self.assertTrue(ok)
        self.assertFalse(info["manual"])

    def test_manual_requires_reason_and_flag(self):
        q = self._q()
        ok, _, _ = cc.check_fix_entry({"final": ["B"], "manual_reason": "题干条件矛盾，人工判定 B"}, q)
        self.assertFalse(ok)  # 未开人工覆盖入口
        ok, why, info = cc.check_fix_entry({"final": ["B"], "manual_reason": "题干条件矛盾，人工判定 B"},
                                           q, allow_manual=True)
        self.assertTrue(ok)
        self.assertTrue(info["manual"])
        ok, why, _ = cc.check_fix_entry({"final": ["B"], "manual_reason": "改"},
                                        q, allow_manual=True)
        self.assertFalse(ok)  # 理由不明确
        ok, why, _ = cc.check_fix_entry({"final": ["Z"], "manual_reason": "题干条件矛盾，人工判定"},
                                        q, allow_manual=True)
        self.assertFalse(ok)  # 人工覆盖也不能违反答案格式


class TestRollbackConflict(CurateTestBase):

    def test_out_of_order_rollback_does_not_overwrite(self):
        bank = cc.load_bank()
        fp = cc.q_fingerprint(bank["questions_by_chapter"]["1"][0])
        # 批次1：B→A（登记台账）
        r1 = cc.apply_answer_fix(bank, [{"qid": "1-0001", "final": ["A"],
                                         "external_evidence": {"supported": True, "quote_found": True,
                                                               "fingerprint": fp}}],
                                 source="t1", batch_id="b1")
        cc.append_batch("answer_fix", "t1", r1["ledger_items"], batch_id="b1")
        # 批次2：A→C（题目此刻内容指纹仍相同——指纹不含答案）
        r2 = cc.apply_answer_fix(bank, [{"qid": "1-0001", "final": ["C"],
                                         "external_evidence": {"supported": True, "quote_found": True,
                                                               "fingerprint": fp}}],
                                 source="t2", batch_id="b2")
        cc.append_batch("answer_fix", "t2", r2["ledger_items"], batch_id="b2")
        cc.write_bank(bank, backup=False)
        # 乱序回滚批次1：当前答案已是 C（批次2 的结果）≠ 批次1 的 after(A) → 冲突跳过
        done, notes = cc.rollback_batch("b1", dry_run=False)
        self.assertEqual(done, 0)
        self.assertTrue(any("冲突" in n for n in notes))
        q = cc.load_bank()["questions_by_chapter"]["1"][0]
        self.assertEqual(q["answer"], "C")  # 后续修改未被覆盖
        # 按序回滚批次2 → 恢复为批次2 的 before（A）
        done2, _ = cc.rollback_batch("b2", dry_run=False)
        self.assertEqual(done2, 1)
        q = cc.load_bank()["questions_by_chapter"]["1"][0]
        self.assertEqual(q["answer"], "A")


class TestVoteCacheBinding(unittest.TestCase):
    """断点投票缓存绑定实际输入版本：旧格式/内容变化一律作废，不得补绑。"""

    FP_A = "a" * 32
    FP_B = "b" * 32

    def test_legacy_cache_invalidated(self):
        raw = {"1-0001": {"qwen-plus": ["A"], "glm": ["A"]}}  # 旧格式：无 fingerprint/votes
        valid, legacy, stale = vd.sanitize_votes_cache(raw, {"1-0001": self.FP_A})
        self.assertEqual(valid, {})
        self.assertEqual(legacy, 1)
        self.assertEqual(stale, 0)

    def test_content_change_invalidates_cache(self):
        raw = {"1-0001": {"fingerprint": self.FP_A, "votes": {"qwen-plus": ["A"]}}}
        valid, legacy, stale = vd.sanitize_votes_cache(raw, {"1-0001": self.FP_B})
        self.assertEqual(valid, {})
        self.assertEqual(stale, 1)

    def test_bound_matching_cache_reused(self):
        raw = {"1-0001": {"fingerprint": self.FP_A, "votes": {"qwen-plus": ["A"]}}}
        valid, legacy, stale = vd.sanitize_votes_cache(raw, {"1-0001": self.FP_A})
        self.assertEqual(list(valid.keys()), ["1-0001"])
        self.assertEqual((legacy, stale), (0, 0))

    def test_verify_results_stale_excluded(self):
        """verify_results（首轮校验）绑定指纹：题目变化后 fingerprint_stale=True。"""
        q_before = {"type": 0, "stem": "原题干", "options": [{"option_label": "A", "option_text": "x"}]}
        rec = {"fingerprint": cc.q_fingerprint(q_before), "primary": {"verdict": "disagree"}}
        self.assertFalse(cc.fingerprint_stale(rec, q_before))
        q_after = dict(q_before, stem="修改后的题干")
        self.assertTrue(cc.fingerprint_stale(rec, q_after))


if __name__ == "__main__":
    unittest.main(verbosity=2)
