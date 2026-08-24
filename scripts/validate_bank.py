# -*- coding: utf-8 -*-
"""题库结构与覆盖校验。

用法:
    python scripts/validate_bank.py
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "quiz_categorized.json"

DOMAIN_CHS = {
    "大模型应用开发": ["1", "9", "10", "12"],
    "大模型提示词工程": ["2"],
    "大模型检索增强": ["3"],
    "大模型微调": ["5"],
    "多Agent及多模态应用": ["4", "11"],
    "生产环境应用实践": ["6", "7", "8"],
}

KEYWORDS = {
    "批量生成/BatchAPI": ["批量", "BatchAPI", "batch"],
    "提示词分隔符": ["分隔符"],
    "意图分类": ["意图"],
    "文档审阅": ["审阅"],
    "文档修订": ["修订"],
    "句子窗口检索": ["句子窗口"],
    "自动合并检索": ["自动合并"],
    "标题改写": ["标题改写"],
    "表格内容增强": ["表格"],
    "文本分割方法对比": ["分割方法", "切片方法", "分割策略"],
    "RAGAS": ["RAGAS", "Ragas", "Faithfulness", "Context Recall", "Context Precision", "Answer Relevancy"],
    "Assistant API": ["Assistant API"],
    "个性化语音助手/多模态交互": ["语音助手", "TTS", "ASR", "CosyVoice", "多模态交互"],
    "医疗/教育/娱乐应用": ["医疗", "教育", "娱乐"],
    "安全组/WAF/DDoS": ["安全组", "WAF", "DDoS"],
    "云上身份与网络隔离": ["RAM", "最小权限", "网络隔离", "私网"],
    "ECS/FC/FC发布AI助手": ["ECS", "函数计算", "FC", "AI 助手", "AI助手"],
    "Dify": ["Dify"],
}


def norm_ans(ans):
    ans = re.sub(r"\s", "", str(ans or ""))
    if "," in ans:
        return [s.strip() for s in ans.split(",") if s.strip()]
    return [c for c in ans if re.match(r"[A-H]", c)]


def is_multi(q, ans):
    return len(ans) > 1 or q.get("type") == 2


def main():
    bank = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    by_ch = bank["questions_by_chapter"]
    errors = []
    ids = set()
    dup_ids = []
    ch_seq = {}
    stem_norm = {}
    total = 0
    single = multi = 0
    ch_counts = {}
    for ch, arr in by_ch.items():
        if ch not in bank["chapters"]:
            errors.append(f"章节 {ch} 不在 chapters 中")
        ch_counts[ch] = len(arr)
        ch_seq.setdefault(ch, set())
        for q in arr:
            total += 1
            seq = str(q.get("seq", ""))
            qid = f"{ch}-{seq}"
            if qid in ids:
                dup_ids.append(qid)
                # 前端 js/data.js 会对同章同 seq 的题追加 'b' 后缀保留两题；
                # 仅当新增题(seq>=5000)发生同章撞号时才算阻断错误。
                if seq.isdigit() and int(seq) >= 5000:
                    errors.append(f"新增题重复 id: {qid}")
            ids.add(qid)
            ch_seq[ch].add(seq)
            ans = norm_ans(q.get("answer"))
            labels = [o.get("option_label") for o in q.get("options", [])]
            missing = [a for a in ans if a not in labels]
            if missing:
                errors.append(f"{qid} 答案不在选项: {missing}")
            multi_flag = is_multi(q, ans)
            if not multi_flag and len(ans) != 1:
                errors.append(f"{qid} 单选答案数量异常: {ans}")
            if multi_flag and len(ans) < 1:
                errors.append(f"{qid} 多选答案为空")
            if multi_flag:
                multi += 1
            else:
                single += 1
            stem = re.sub(r"\s", "", q.get("stem", ""))
            stem_norm.setdefault(stem, []).append(qid)
    dup_stems = {k: v for k, v in stem_norm.items() if len(v) > 1}

    unmapped = [ch for ch in ch_counts if ch not in {c for v in DOMAIN_CHS.values() for c in v}]
    if unmapped:
        errors.append(f"存在无法映射到知识域的章节: {unmapped}")

    new_qs = [q for arr in by_ch.values() for q in arr if str(q.get("seq", "")).isdigit() and 5000 <= int(q["seq"]) < 6000]
    new_by_ch = {}
    for q in new_qs:
        new_by_ch[q["chapter"]] = new_by_ch.get(q["chapter"], 0) + 1
    keyword_counts = {}
    for name, kws in KEYWORDS.items():
        c = 0
        for q in new_qs:
            text = (q.get("stem", "") + " " + " ".join(o.get("option_text", "") for o in q.get("options", [])))
            if any(kw.lower() in text.lower() for kw in kws):
                c += 1
        keyword_counts[name] = c

    print("=== 题库校验 ===")
    print(f"总题数: {total}")
    print(f"单选: {single}  多选: {multi}")
    print(f"章节题量: {ch_counts}")
    print(f"新增题量(seq>=5000): {len(new_qs)}  分布: {new_by_ch}")
    print(f"重复 id(原始数据，运行时由 js/data.js 追加b后缀): {len(dup_ids)}")
    print(f"答案不在选项: {len([e for e in errors if '答案不在选项' in e])}")
    print(f"答案数量异常: {len([e for e in errors if '答案数量异常' in e])}")
    print(f"无法映射章节: {len([e for e in errors if '无法映射' in e])}")
    print(f"重复题干组: {len(dup_stems)}")
    if dup_stems:
        print("\n重复题干样例(已有题库历史重复):")
        for stem, qids in list(dup_stems.items())[:20]:
            print("  ", qids, stem[:80])
    print("\n=== 新增题覆盖关键词 ===")
    for name, c in keyword_counts.items():
        print(f"  {name}: {c}")
    if errors:
        print("\n=== 错误列表 ===")
        for e in errors[:100]:
            print(" -", e)
        return 1
    print("\n校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
