# -*- coding: utf-8 -*-
"""批次F：体检信号题裁决（4题：3题保留ID措辞修正，1题实质改写换身份）。

1-1492  题干"哪些场景"改"哪个场景"（单选，答案A唯一可辩护）
12-5078 实质改写（选项更换）→ 新身份 12-6003 + 软删旧题：
        原解析称B/D也符合，与单选答案A矛盾；B/D为不可核实产品细节，替换掉；
        考点（组件定位：增强适配而非替代）与正确项语义不变
10-1345 题干"哪一项"改"哪几项"并标注（多选），答案A,D不变
12-5107 删除题干残留"本章"定位语
台账：rebuild20261027_F_fix / rebuild20261027_F_del / rebuild20261027_F_add
"""
import pathlib, sys, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core as cc
from datetime import datetime

NOW = datetime.now().isoformat(timespec="seconds")
BANK = cc.load_bank()
BY = BANK["questions_by_chapter"]

def get(qid):
    ch, seq = qid.split("-")
    for q in BY.get(ch, []):
        if str(q["seq"]).zfill(4) == seq and not q.get("deleted"):
            return q
    return None

items = []

# 1-1492
q = get("1-1492")
assert q and "以下哪些场景直接源于" in q["stem"]
q["stem"] = q["stem"].replace("以下哪些场景直接源于", "以下哪个场景直接源于")
q["revised_at"] = NOW
items.append({"qid": "1-1492", "reason": "单选与'哪些'措辞矛盾，改为'哪个场景'"})

# 12-5078 实质改写 -> 新身份 12-6003 + 软删旧题
q = get("12-5078")
assert q
NEWQ = {
    "seq": "6003", "type": 0,
    "stem": "关于百炼平台提供的 LlamaIndex 组件，以下哪项描述符合其设计定位？",
    "options": [
        {"option_label": "A", "option_text": "预集成 DashScope Embedding 与 Qwen 系列模型适配，降低 RAG 应用接入阿里云模型的门槛"},
        {"option_label": "B", "option_text": "完全替代原生 LlamaIndex API，社区示例代码均无法使用"},
        {"option_label": "C", "option_text": "仅支持本地部署的开源模型，不能对接阿里云托管模型服务"},
        {"option_label": "D", "option_text": "只适用于文档问答场景，不支持其他类型的数据源接入"},
    ],
    "answer": "A",
    "analysis": ("A正确：百炼的 LlamaIndex 组件定位为对原生 LlamaIndex 的增强与适配，"
                 "预集成了 DashScope Embedding、Qwen 系列 LLM 等阿里云模型服务，"
                 "简化 RAG 应用接入阿里云模型的流程。B错误：组件是增强而非替代，"
                 "与原生 API 兼容；C错误：其价值恰恰在于对接阿里云托管模型，并非只支持本地开源模型；"
                 "D错误：数据源支持范围由 LlamaIndex 本身决定（支持多种 Loader），组件不缩小该能力。"),
    "chapter": 12, "difficulty_score": 1, "difficulty_label": "入门", "difficulty_sort": 1,
    "governance": {"origin": "自编重构题", "source_note": "重构改写替代原缺陷题 12-5078（原解析与单选答案矛盾）"},
}
assert get("12-6003") is None, "12-6003 已存在"
BY["12"].append(NEWQ)
if not cc.batch_exists("rebuild20261027_F_del"):
    res = cc.soft_delete(BANK, [{"qid": "12-5078",
        "reason": "原解析称B/D也符合、与单选答案A矛盾，实质改写采用新身份 12-6003"}],
        source="题库重构批次F")
    cc.append_batch("soft_delete", "rebuild_batch_F.py", res["ledger_items"],
                    reason="批次F：12-5078 实质改写换身份", batch_id="rebuild20261027_F_del")
if not cc.batch_exists("rebuild20261027_F_add"):
    cc.append_batch("add_questions", "rebuild_batch_F.py",
                    [{"qid": "12-6003", "before": None, "after": NEWQ,
                      "reason": NEWQ["governance"]["source_note"]}],
                    reason="批次F：新增12-6003替代题", batch_id="rebuild20261027_F_add")
items.append({"qid": "12-5078->12-6003", "reason": "实质改写（选项更换），新身份 12-6003，考点不变"})

# 10-1345
q = get("10-1345")
assert q
q["stem"] = q["stem"].replace("以下哪一项不属于", "以下哪几项不属于").rstrip("?？") + "？（多选）"
q["revised_at"] = NOW
items.append({"qid": "10-1345", "reason": "多选（答案A,D）与'哪一项'措辞矛盾，改为'哪几项…（多选）'"})

# 12-5107
q = get("12-5107")
assert q
q["stem"] = q["stem"].replace("此故障揭示了本章关于技术栈分层的哪两个关键原则？", "此故障揭示了关于技术栈分层的哪两个关键原则？")
q["revised_at"] = NOW
items.append({"qid": "12-5107", "reason": "删除题干残留'本章'定位语"})

if items and not cc.batch_exists("rebuild20261027_F_fix"):
    cc.append_batch("text_fix", "rebuild_batch_F.py", items,
                    reason="批次F：4道体检信号题措辞/选项修正（题意考点不变，保留ID）",
                    batch_id="rebuild20261027_F_fix")
cc.write_bank(BANK)
print("fixed:", len(items))
print("批次F 完成")
