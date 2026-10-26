# -*- coding: utf-8 -*-
"""从台账导出重构批次可追溯处理清单 CSV（原ID/新ID/处理方式/理由/批次）。"""
import csv, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
led = json.loads((ROOT / "data/curate/ledger.json").read_text(encoding="utf-8"))

# 实质改写换身份映射（del reason 中含"新身份"，add 批次给出新题）
newid_by_reason = {}
for b in led["batches"]:
    if b["kind"] == "add_questions" and b["batch_id"].startswith("rebuild20261027"):
        for it in b["items"]:
            note = (it.get("after") or {}).get("governance", {}).get("source_note", "")
            import re
            m = re.search(r"替代原缺陷题 (\d+-\d+)", note)
            if m:
                newid_by_reason[m.group(1)] = it["qid"]

rows = []
for b in led["batches"]:
    bid = b["batch_id"]
    if not bid.startswith("rebuild20261027"):
        continue
    kind = b["kind"]
    for it in b.get("items", []):
        qid = it.get("qid", "")
        reason = it.get("reason", b.get("reason", ""))
        if kind == "soft_delete":
            action = "删除(软删)"
            new = newid_by_reason.get(qid, "")
            if "新身份" in reason or new:
                action = "实质改写(换身份)"
        elif kind == "restore":
            action = "恢复"
        elif kind == "answer_fix":
            action = "修正答案"
            before = it.get("before") or {}
            after = it.get("after") or {}
            reason += f"｜{before.get('answer','')}→{after.get('answer','')}"
        elif kind == "add_questions":
            action = "新增"
        elif kind == "move":
            action = "移章"
            reason += f"｜{qid}→{it.get('to')}-{str(it.get('after_seq') or '').zfill(4)}"
        elif kind in ("stem_rewrite", "text_fix"):
            action = "题干改写(保留ID)" if kind == "stem_rewrite" else "文字修正(保留ID)"
        elif kind == "analysis_fill":
            action = "补写解析(保留ID)"
        else:
            action = kind
        rows.append({
            "批次": bid, "原ID": qid, "新ID": newid_by_reason.get(qid, ""),
            "处理方式": action, "理由": reason,
        })

out = ROOT / "docs" / "题库重构处理清单.csv"
with out.open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["批次", "原ID", "新ID", "处理方式", "理由"])
    w.writeheader()
    w.writerows(rows)
print(f"{len(rows)} 条 -> {out}")
from collections import Counter
print(Counter(r["处理方式"] for r in rows))
