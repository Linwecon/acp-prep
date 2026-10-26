# -*- coding: utf-8 -*-
"""批次E：近重复裁决 + 笔误修正（验收第3项复核产物）。

删除（镜像换皮题，各对保留解析更好的一题）：
  3-0567（与3-0494镜像：切片过短/过大）
  9-0554（与9-0543镜像：temperature高/低）
  9-0531（与9-0510镜像：top_p高/低）
修正（题干/选项文字，题意不变，保留ID，设 revised_at）：
  2-1137  Output Fomat -> Output Format
  2-0581  Rol/Audienc/Object -> Role/Audience/Objective
  2-0337  少样本本 -> 少样本提示（Few-shot Prompting）
  5-0829  选项D 尾部杂字"试题" -> 调整梯度数值的大小
  5-0985  编码策略 -> 解码策略
  5-1000  qwen2.5.1b -> Qwen2.5-1.5B
  7-0290  ground_trut -> ground_truth
  4-5175  背景去重（与4-5169同背景换皮）：报销查询助手 -> IT权限工单助手，考点(ReAct失败出口)不变
台账：rebuild20261027_E_del / rebuild20261027_E_fix
"""
import pathlib, sys
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

# ---- 删除镜像换皮题 ----
DEL = [
    {"qid": "3-0567", "reason": "与3-0494构成镜像换皮题（仅过短/过长一词之差、选项完全对称），保留3-0494"},
    {"qid": "9-0554", "reason": "与9-0543构成镜像换皮题（temperature高/低对调），保留9-0543"},
    {"qid": "9-0531", "reason": "与9-0510构成镜像换皮题（top_p高/低对调），保留9-0510"},
]
if not cc.batch_exists("rebuild20261027_E_del"):
    res = cc.soft_delete(BANK, DEL, source="题库重构批次E")
    cc.append_batch("soft_delete", "rebuild_batch_E.py", res["ledger_items"],
                    reason="批次E：删除3道镜像换皮题", batch_id="rebuild20261027_E_del")
    print("deleted:", res.get("applied"))

# ---- 文字修正 ----
FIXES = {
    "2-1137": lambda q: _rep(q, "Output Fomat", "Output Format"),
    "2-0581": lambda q: [_rep(q, "角色（Rol）", "角色（Role）"),
                          _rep(q, "受众（Audienc）", "受众（Audience）"),
                          _rep(q, "任务目标（Object）", "任务目标（Objective）")],
    "2-0337": lambda q: _rep(q, "少样本本", "少样本提示（Few-shot Prompting）"),
    "5-0829": lambda q: _rep(q, "调整梯度大小 试题", "调整梯度数值的大小"),
    "5-0985": lambda q: _rep(q, "编码策略", "解码策略"),
    "5-1000": lambda q: _rep(q, "qwen2.5.1b模型", "Qwen2.5-1.5B 模型"),
    "7-0290": lambda q: _rep(q, "ground_trut分解", "ground_truth 分解"),
}

def _rep(q, old, new):
    n = 0
    if old in q.get("stem", ""):
        q["stem"] = q["stem"].replace(old, new); n += 1
    for o in q.get("options", []):
        if old in o.get("option_text", ""):
            o["option_text"] = o["option_text"].replace(old, new); n += 1
    an = q.get("analysis") or ""
    if old in an:
        q["analysis"] = an.replace(old, new); n += 1
    return n

n_fixed = 0
ledger_items = []
for qid, fn in FIXES.items():
    q = get(qid)
    if not q:
        print("missing:", qid); continue
    hits = fn(q)
    if hits:
        q["revised_at"] = NOW
        n_fixed += 1
        ledger_items.append({"qid": qid, "reason": f"批次E文字修正（{hits}处）", "hits": hits})
    else:
        print("no match:", qid)

# 4-5175 背景去重改写（题意不变）
q = get("4-5175")
if q:
    q["stem"] = ("某企业内部 IT 服务助手采用 ReAct 架构处理权限申请查询。"
                 "用户问'帮我查一下我上个月提交的 VPN 权限申请审批到哪一步了'，"
                 "模型返回 tool_calls=[{'name':'get_access_request','args':{'user_id':'U456','month':'2024-07'}}]。"
                 "此时若工具执行超时返回空结果，Agent 下一步最应采取的行动是？")
    q["analysis"] = (q.get("analysis") or "").replace("报销单", "工单").replace("报销查询", "权限申请查询")
    q["revised_at"] = NOW
    n_fixed += 1
    ledger_items.append({"qid": "4-5175", "reason": "批次E：与4-5169同背景换皮，改写背景消除重复（考点ReAct失败出口不变）", "hits": 1})

if ledger_items and not cc.batch_exists("rebuild20261027_E_fix"):
    cc.append_batch("text_fix", "rebuild_batch_E.py", ledger_items,
                    reason="批次E：8题文字修正/背景去重（题意不变，保留ID）", batch_id="rebuild20261027_E_fix")
cc.write_bank(BANK)
print("fixed:", n_fixed)
print("批次E 完成")
