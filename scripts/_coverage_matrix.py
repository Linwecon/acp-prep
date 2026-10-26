# -*- coding: utf-8 -*-
"""输出知识域覆盖矩阵（域—章节—题量—单选/多选—难度分布）。"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
bank = json.loads((ROOT / "data/quiz_categorized.json").read_text(encoding="utf-8"))
DOM = {
    "开发多模型应用(dev)": [1, 9, 10, 12],
    "提示工程(prompt)": [2],
    "检索增强(rag)": [3],
    "微调(ft)": [5],
    "Agent/多模态(agent)": [4, 11],
    "生产实践(prod)": [6, 7, 8],
}
Q = {"1": "大模型基础", "9": "API调用", "10": "阿里云AI平台", "12": "框架与工具",
     "2": "提示工程", "3": "RAG", "5": "微调", "4": "Agent", "11": "多模态",
     "6": "部署", "7": "评估", "8": "安全合规"}
print(f"{'域':<22}{'章节':<16}{'在用':>5}{'单选':>5}{'多选':>5}{'入门':>5}{'进阶':>5}{'挑战':>5}")
tot = 0
for name, chs in DOM.items():
    s = m = e = a = c = 0
    for ch in chs:
        live = [q for q in bank["questions_by_chapter"].get(str(ch), []) if not q.get("deleted")]
        s += sum(1 for q in live if q.get("type") == 0)
        m += sum(1 for q in live if q.get("type") == 1)
        e += sum(1 for q in live if q.get("difficulty_label") == "入门")
        a += sum(1 for q in live if q.get("difficulty_label") == "进阶")
        c += sum(1 for q in live if q.get("difficulty_label") == "挑战")
    tot += s + m
    print(f"{name:<22}{','.join(Q[str(x)] for x in chs)[:15]:<16}{s+m:>5}{s:>5}{m:>5}{e:>5}{a:>5}{c:>5}")
print("合计在用:", tot)

# 自编题统计
n_self = sum(1 for ch, qs in bank["questions_by_chapter"].items() for q in qs
             if not q.get("deleted") and (q.get("governance") or {}).get("origin") == "自编重构题")
n_rev = sum(1 for ch, qs in bank["questions_by_chapter"].items() for q in qs
            if not q.get("deleted") and q.get("revised_at"))
print("自编重构题(在用):", n_self, "| 修订题(在用):", n_rev)
