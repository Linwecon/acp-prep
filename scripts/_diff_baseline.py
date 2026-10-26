# -*- coding: utf-8 -*-
"""对比重构前基线（data/backup 最早快照）与当前题库的各章题量/单多选。"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

def stats(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    by = d["questions_by_chapter"]
    rows = {}
    for ch in sorted(by, key=int):
        live = [q for q in by[ch] if not q.get("deleted")]
        s = sum(1 for q in live if q.get("type") == 0)
        m = sum(1 for q in live if q.get("type") == 1)
        rows[ch] = (len(live), s, m)
    tot = sum(v[0] for v in rows.values())
    return rows, tot, d.get("total"), d.get("active_total")

base = ROOT / "data/backup/quiz_categorized_20261027_004951.json"
if not base.exists():
    import glob
    cands = sorted(glob.glob(str(ROOT / "data/backup/quiz_categorized_*.json")))
    base = pathlib.Path(cands[0])
print("基线:", base.name)
b_rows, b_tot, b_total, b_active = stats(base)
c_rows, c_tot, c_total, c_active = stats(ROOT / "data/quiz_categorized.json")
print(f"{'章':<4}{'前(在用/单/多)':<20}{'后(在用/单/多)':<20}{'变化':<8}")
for ch in sorted(set(b_rows) | set(c_rows), key=int):
    b = b_rows.get(ch, (0, 0, 0)); c = c_rows.get(ch, (0, 0, 0))
    print(f"{ch:<4}{str(b):<20}{str(c):<20}{c[0]-b[0]:+d}")
print(f"合计 前 {b_tot} (total={b_total} active={b_active})  后 {c_tot} (total={c_total} active={c_active})")
