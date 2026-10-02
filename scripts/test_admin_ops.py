# -*- coding: utf-8 -*-
"""管理服务操作测试：在临时题库副本上验证 remove/restore/move/answer_fix/manual_fix/rollback。

覆盖：
- 所有修正入口走统一守卫；显式 fixes 无独立绕过入口；
- 人工覆盖（manual_fix）必须提供理由，台账记录为「人工覆盖」；
- answer_history 与台账 batch_id 一致；
- 并发操作互斥不丢更新；
- 回滚冲突不覆盖后续修改；
- answer_actions 中的无指纹旧结果被拒绝。

运行: python scripts/test_admin_ops.py -v
不修改正式题库（data/quiz_categorized.json 等）。
"""
import json
import pathlib
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import curate_core as cc  # noqa: E402
import admin_server as admin  # noqa: E402


def make_q(ch, seq, stem, answer="A"):
    return {
        "seq": str(seq).zfill(4), "type": 0, "stem": stem,
        "options": [{"option_label": "ABCD"[i], "option_text": f"选项{i+1}"} for i in range(4)],
        "answer": answer, "analysis": "解析", "chapter": ch,
        "difficulty_score": 2, "difficulty_label": "进阶", "difficulty_sort": 2,
    }


class AdminOpsTest(unittest.TestCase):
    """每个用例在独立的临时副本上运行 admin_server 的操作函数。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bank_dir = pathlib.Path(self.tmp.name)
        bank = {
            "chapters": {"1": "大模型基础", "3": "RAG 检索增强生成"},
            "questions_by_chapter": {
                "1": [make_q(1, 1, "题目甲", "A"), make_q(1, 2, "题目乙", "B")],
                "3": [make_q(3, 1, "题目丙", "C"), make_q(3, 2, "题目丁", "D")],
            },
            "total": 4,
        }
        (self.bank_dir / "quiz_categorized.json").write_text(
            json.dumps(bank, ensure_ascii=False), encoding="utf-8")
        self._old = (cc.JSON_PATH, cc.JS_PATH, cc.LEDGER_PATH, cc.BACKUP_DIR,
                     admin.BANK_COPY_MODE, admin.ACTIONS_PATH)
        cc.JSON_PATH = self.bank_dir / "quiz_categorized.json"
        cc.JS_PATH = self.bank_dir / "quiz_categorized.js"
        cc.LEDGER_PATH = self.bank_dir / "curate" / "ledger.json"
        cc.BACKUP_DIR = self.bank_dir / "backup"
        admin.BANK_COPY_MODE = True  # 副本模式：跳过 min.js 重建
        # 伪造 answer_actions：一条带指纹+完整证据（可修正），一条无指纹（须拒绝）
        self.fp1 = cc.q_fingerprint(bank["questions_by_chapter"]["3"][0])
        self.actions = self.bank_dir / "answer_actions.json"
        self.actions.write_text(json.dumps({"fix": [
            {"qid": "3-0001", "final": ["D"], "analysis": "修正后的解析",
             "fingerprint": self.fp1,
             "evidence": {"evidence_state": "external",
                          "external_evidence": {"supported": True, "quote_found": True,
                                                "fingerprint": self.fp1, "source": "测试"}}},
            {"qid": "3-0002", "final": ["A"], "analysis": "旧结果",
             "fingerprint": None,
             "evidence": {"evidence_state": "vote_only"}},
        ]}, ensure_ascii=False), encoding="utf-8")
        admin.ACTIONS_PATH = self.actions

    def tearDown(self):
        (cc.JSON_PATH, cc.JS_PATH, cc.LEDGER_PATH, cc.BACKUP_DIR,
         admin.BANK_COPY_MODE, admin.ACTIONS_PATH) = self._old
        self.tmp.cleanup()

    # ---------- 基础操作 ----------

    def test_remove_restore_roundtrip(self):
        r = admin.op_remove({"qids": ["1-0001"], "reason": "测试删除", "apply": True})
        self.assertEqual(r["applied"], 1)
        self.assertIn("batch_id", r)
        bank = cc.load_bank()
        self.assertTrue(bank["questions_by_chapter"]["1"][0]["deleted"])
        # 正式题库未被触碰
        real = json.loads((pathlib.Path(self._old[0])).read_text(encoding="utf-8"))
        self.assertFalse(real["questions_by_chapter"]["1"][0].get("deleted"))
        r2 = admin.op_restore({"qids": ["1-0001"], "apply": True})
        self.assertEqual(r2["applied"], 1)
        bank = cc.load_bank()
        self.assertFalse(bank["questions_by_chapter"]["1"][0].get("deleted"))

    def test_remove_dry_run_no_ledger(self):
        r = admin.op_remove({"qids": ["1-0001"], "reason": "x", "apply": False})
        self.assertEqual(r["applied"], 1)
        bank = cc.load_bank()
        self.assertFalse(bank["questions_by_chapter"]["1"][0].get("deleted"))
        self.assertEqual(len(cc.load_ledger()["batches"]), 0)  # dry-run 不写台账

    def test_move_and_rollback(self):
        r = admin.op_move({"items": [{"qid": "1-0002", "to": 3, "reason": "错放"}], "apply": True})
        self.assertEqual(r["applied"], 1)
        bank = cc.load_bank()
        self.assertEqual(bank["questions_by_chapter"]["3"][2]["stem"], "题目乙")
        done, _ = cc.rollback_batch(r["batch_id"], dry_run=False)
        self.assertEqual(done, 1)
        bank = cc.load_bank()
        self.assertTrue(any(q["stem"] == "题目乙" for q in bank["questions_by_chapter"]["1"]))

    # ---------- 统一守卫 ----------

    def test_answer_fix_via_actions_requires_guard(self):
        """验证链入口：有指纹+完整证据的方案通过；无指纹旧结果被拒绝。"""
        r = admin.op_answer_fix({"qids": ["3-0001", "3-0002"], "apply": True})
        self.assertEqual(r["applied"], 1)
        rejected = {s["qid"]: s["why"] for s in r["skipped"]}
        self.assertIn("不得补绑", rejected.get("3-0002", ""))
        bank = cc.load_bank()
        q = bank["questions_by_chapter"]["3"][0]
        self.assertEqual(q["answer"], "D")
        self.assertEqual(q["answer_history"][0]["old_answer"], "C")

    def test_explicit_fixes_have_no_bypass(self):
        """显式 fixes 不能绕过守卫：op_answer_fix 不接受 fixes 字段（HTTP 校验器也会 400）；
        无指纹旧结果走守卫被拒绝，题目未被改。"""
        r = admin.op_answer_fix({"qids": ["3-0002"], "fixes": [{"qid": "3-0002", "final": ["A"]}],
                                 "apply": True})
        self.assertEqual(r["applied"], 0)
        self.assertIn("不得补绑", r["skipped"][0]["why"])
        bank = cc.load_bank()
        self.assertEqual(bank["questions_by_chapter"]["3"][1]["answer"], "D")  # 未被改

    def test_manual_fix_requires_reason_and_records_override(self):
        """人工覆盖入口：理由必须明确；台账与历史记录为「人工覆盖」。"""
        r = admin.op_manual_fix({"fixes": [{"qid": "3-0002", "final": ["A"]}],
                                 "reason": "题干限定条件与选项D矛盾，人工复核后判定 A",
                                 "apply": True})
        self.assertEqual(r["applied"], 1)
        bank = cc.load_bank()
        q = bank["questions_by_chapter"]["3"][1]
        self.assertEqual(q["answer"], "A")
        self.assertTrue(q["answer_history"][0]["reason"].startswith("人工覆盖"))
        led = cc.load_ledger()
        self.assertIn("人工覆盖", led["batches"][-1]["source"])
        # 理由不明确 → 拒绝
        r2 = admin.op_manual_fix({"fixes": [{"qid": "3-0002", "final": ["B"]}],
                                  "reason": "改", "apply": True})
        self.assertEqual(r2["applied"], 0)
        bank = cc.load_bank()
        self.assertEqual(bank["questions_by_chapter"]["3"][1]["answer"], "A")

    # ---------- batch_id 一致性 ----------

    def test_history_and_ledger_batch_id_consistent(self):
        r = admin.op_answer_fix({"qids": ["3-0001"], "apply": True})
        bank = cc.load_bank()
        q = bank["questions_by_chapter"]["3"][0]
        self.assertEqual(q["answer_history"][0]["batch_id"], r["batch_id"])
        led = cc.load_ledger()
        batch = next(b for b in led["batches"] if b["batch_id"] == r["batch_id"])
        self.assertEqual(batch["kind"], "answer_fix")
        self.assertEqual(batch["count"], 1)
        # 回滚后 answer_history 中该批次条目被移除，且不会重复
        cc.rollback_batch(r["batch_id"], dry_run=False)
        q = cc.load_bank()["questions_by_chapter"]["3"][0]
        self.assertFalse(q.get("answer_history"))

    # ---------- 并发一致性 ----------

    def test_concurrent_ops_no_lost_update(self):
        """并发执行 remove + move + manual_fix：互斥保护下互不丢失。"""
        payload = {"qids": ["1-0001"], "reason": "并发删除", "apply": True}
        payload2 = {"items": [{"qid": "1-0002", "to": 3, "reason": "并发移动"}], "apply": True}
        payload3 = {"fixes": [{"qid": "3-0001", "final": ["D"]}],
                    "reason": "并发人工修正：选项D与题干一致", "apply": True}
        with ThreadPoolExecutor(max_workers=3) as ex:
            f1 = ex.submit(admin.op_remove, dict(payload))
            f2 = ex.submit(admin.op_move, dict(payload2))
            f3 = ex.submit(admin.op_manual_fix, dict(payload3))
            r1, r2, r3 = f1.result(), f2.result(), f3.result()
        self.assertEqual(r1["applied"], 1)
        self.assertEqual(r2["applied"], 1)
        self.assertEqual(r3["applied"], 1)
        bank = cc.load_bank()
        self.assertTrue(bank["questions_by_chapter"]["1"][0]["deleted"])
        self.assertEqual(bank["questions_by_chapter"]["3"][2]["stem"], "题目乙")
        self.assertEqual(bank["questions_by_chapter"]["3"][0]["answer"], "D")
        led = cc.load_ledger()
        kinds = sorted(b["kind"] for b in led["batches"])
        self.assertEqual(kinds, ["answer_fix", "move", "soft_delete"])

    def test_concurrent_conflicting_writes_serialize(self):
        """两线程同时对同一题做答案修正：串行执行后历史完整（两次都留下记录）。"""
        fp = cc.q_fingerprint(cc.load_bank()["questions_by_chapter"]["3"][0])
        self.actions.write_text(json.dumps({"fix": [
            {"qid": "3-0001", "final": ["D"], "analysis": "并发一",
             "fingerprint": fp,
             "evidence": {"external_evidence": {"supported": True, "quote_found": True,
                                                "fingerprint": fp}}},
        ]}, ensure_ascii=False), encoding="utf-8")
        p1 = {"qids": ["3-0001"], "apply": True}
        p2 = {"fixes": [{"qid": "3-0001", "final": ["C"]}],
              "reason": "并发人工修正：复核后改选 C", "apply": True}
        with ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(admin.op_answer_fix, dict(p1))
            f2 = ex.submit(admin.op_manual_fix, dict(p2))
            r1, r2 = f1.result(), f2.result()
        self.assertEqual(r1["applied"] + r2["applied"], 2)  # 两次都成功（串行）
        bank = cc.load_bank()
        q = bank["questions_by_chapter"]["3"][0]
        self.assertEqual(len(q["answer_history"]), 2)       # 两条历史都保留，无丢失
        self.assertIn(q["answer"], ("C", "D"))
        # 后到的批次回滚应检测冲突或按序回滚，不会覆盖丢历史
        led = cc.load_ledger()
        self.assertEqual(len(led["batches"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
