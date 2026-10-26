# -*- coding: utf-8 -*-
"""批次D-3：缺解析题处理落库（289 题）。
- keep(273)：补写解析，保留 ID
- fix_answer(1)：1-1322 答案 A,B,C->A,B（走 apply_answer_fix，旧答案入 answer_history）
- rewrite 保留ID(7)：仅错字/歧义/表述修正且题意不变（1-0318/1-0823/1-0450/1-0428/10-0769/11-0388/11-0709）
- rewrite 新身份(6)：选项实质更换 -> 新题 6xxx + 软删旧题
  1-0362->1-6002, 1-0397->1-6003, 12-0229->12-6002, 7-0090->7-6003, 7-0186->7-6004, 8-0245->8-6001
- delete(2)：1-0178（虚构API ask_lm_route）、2-0080（同义反复无区分度）
台账：rebuild20261027_D3_analysis / _D3_fix / _D3_del / _D3_add
"""
import pathlib, sys, json, glob, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core as cc
from datetime import datetime

NOW = datetime.now().isoformat(timespec="seconds")
ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = cc.load_bank()
BY = BANK["questions_by_chapter"]

def get(qid):
    ch, seq = qid.split("-")
    for q in BY.get(ch, []):
        if str(q["seq"]).zfill(4) == seq and not q.get("deleted"):
            return q
    return None

results = []
for f in glob.glob(str(ROOT / "data" / "curate" / "rebuild" / "noanalysis" / "result_*.json")):
    results.extend(json.load(open(f, encoding="utf-8")))
print("结果条数:", len(results))

# 题意实质更换 -> 新身份映射
NEWID = {"1-0362": "1-6002", "1-0397": "1-6003", "12-0229": "12-6002",
         "7-0090": "7-6003", "7-0186": "7-6004", "8-0245": "8-6001"}

def norm_opts(opts):
    out = []
    for i, o in enumerate(opts):
        if isinstance(o, dict):
            out.append({"option_label": o["option_label"], "option_text": o["option_text"]})
        else:
            m = re.match(r"^([A-Z])[\.、．]\s*(.*)$", o.strip(), re.S)
            if m:
                out.append({"option_label": m.group(1), "option_text": m.group(2).strip()})
            else:
                out.append({"option_label": chr(ord("A") + i), "option_text": o.strip()})
    return out

n_keep = n_rw = 0
for it in results:
    qid, act = it["qid"], it["action"]
    if act == "keep":
        q = get(qid)
        if not q:
            print("missing keep:", qid); continue
        q["analysis"] = it["analysis"].strip()
        q["revised_at"] = NOW
        n_keep += 1
    elif act == "rewrite" and qid not in NEWID:
        q = get(qid)
        if not q:
            print("missing rw:", qid); continue
        q["stem"] = it["new_stem"]
        q["options"] = norm_opts(it["new_options"])
        q["answer"] = it["new_answer"]
        q["analysis"] = it["analysis"].strip()
        q["revised_at"] = NOW
        n_rw += 1

BID = "rebuild20261027_D3"
if not cc.batch_exists(BID + "_analysis"):
    cc.append_batch("analysis_fill", "rebuild_batch_D3.py",
                    [{"qid": x["qid"], "reason": "补写解析"} for x in results if x["action"] == "keep"],
                    reason=f"批次D-3：{n_keep}题补写解析+{n_rw}题保题意改写", batch_id=BID + "_analysis")
print("keep:", n_keep, "rewrite保留ID:", n_rw)

# fix_answer
fa = [x for x in results if x["action"] == "fix_answer"]
if fa and not cc.batch_exists(BID + "_fix"):
    res = cc.apply_answer_fix(BANK, [
        {"qid": "1-1322", "final": ["A", "B"],
         "analysis": next(x["analysis"] for x in fa if x["qid"] == "1-1322"),
         "reason": "语义切片不适用于严格控制Token数量场景（那是Token切片用途），原答案含C错误",
         "evidence": "课程材料：语义切片按语义相关性切分，不保证长度精确可控"}],
        source="题库重构批次D-3", batch_id=BID + "_fix")
    print("fix_answer:", res.get("applied"))

# delete + 新身份替换
DEL = [{"qid": "1-0178", "reason": "ask_lm_route 为虚构API，无法核实，选项与'输入格式'无关、无区分度"},
       {"qid": "2-0080", "reason": "题干与正确项同义反复，干扰项为模板化无关填充，无考查价值"}]
for qid, newid in NEWID.items():
    src = next(x for x in results if x["qid"] == qid)
    DEL.append({"qid": qid, "reason": f"实质改写题，采用新身份 {newid}（{src['reason'][:60]}）"})
if not cc.batch_exists(BID + "_del"):
    res = cc.soft_delete(BANK, DEL, source="题库重构批次D-3", batch_id=BID + "_del")
    cc.append_batch("soft_delete", "rebuild_batch_D3.py", res["ledger_items"],
                    reason="批次D-3删除2缺陷题+6实质改写旧题", batch_id=BID + "_del")
    print("deleted:", res.get("applied"))

ADDS = []
for qid, newid in NEWID.items():
    src = next(x for x in results if x["qid"] == qid)
    ch = qid.split("-")[0]
    ADDS.append({
        "seq": newid.split("-")[1], "type": 0 if "," not in src["new_answer"] else 1,
        "stem": src["new_stem"], "options": norm_opts(src["new_options"]),
        "answer": src["new_answer"], "analysis": src["analysis"].strip(),
        "chapter": int(ch), "difficulty_score": 1, "difficulty_label": "入门", "difficulty_sort": 1,
        "governance": {"origin": "自编重构题", "source_note": f"重构改写替代原缺陷题 {qid}"},
    })
if not cc.batch_exists(BID + "_add"):
    for a in ADDS:
        BY.setdefault(str(a["chapter"]), []).append(a)
    cc.append_batch("add_questions", "rebuild_batch_D3.py",
                    [{"qid": f"{a['chapter']}-{a['seq']}", "before": None, "after": a,
                      "reason": a["governance"]["source_note"]} for a in ADDS],
                    reason="批次D-3新增6道改写替代题", batch_id=BID + "_add")
    print("added:", len(ADDS))

cc.write_bank(BANK)
print("批次D-3 完成")
