# -*- coding: utf-8 -*-
"""批次D-2：教材引用题干改写落库。
将 cite_final.txt 的 141 条改写（正则清洗+人工OVERRIDE，全部通过破损检测）应用到题干。
题意未实质变化（仅去除对内部教材的引用定位语），保留原 qid；设 revised_at；台账 rebuild20261027_D2_cite。
"""
import pathlib, sys, re, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core as cc
from datetime import datetime

NOW = datetime.now().isoformat(timespec="seconds")
ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = cc.load_bank()
BY = BANK["questions_by_chapter"]
BID = "rebuild20261027_D2_cite"

if cc.batch_exists(BID):
    print("批次D-2 已执行，跳过")
    sys.exit(0)

txt = (ROOT / "data" / "curate" / "rebuild" / "cite_final.txt").read_text(encoding="utf-8")
pairs = re.findall(r"=== (\S+) \[(\w+)\]\nOLD: (.*)\nNEW: (.*)\n", txt)
print("提案:", len(pairs))

items, missing, mismatch = [], [], []
for qid, kind, old, new in pairs:
    ch, seq = qid.split("-")
    q = next((x for x in BY.get(ch, []) if str(x["seq"]).zfill(4) == seq and not x.get("deleted")), None)
    if q is None:
        missing.append(qid); continue
    if q["stem"] != old:
        mismatch.append(qid); continue
    before = q["stem"]
    q["stem"] = new
    q["revised_at"] = NOW
    items.append({"qid": qid, "before": before, "after": new, "reason": f"去除教材引用定位语（{kind}）"})

print("应用:", len(items), "缺失:", missing, "题干不匹配(跳过):", mismatch)
cc.append_batch("stem_rewrite", "rebuild_batch_D2.py", items,
                reason="批次D-2：141题去除教材/原文/本章引用定位语，改写结果逐条人工审查通过",
                batch_id=BID)
cc.write_bank(BANK)
print("批次D-2 完成")
