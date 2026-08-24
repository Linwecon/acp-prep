# -*- coding: utf-8 -*-
"""清理历史重复题干与重复 ID。

- 重复题干：全局按去除空白后的题干分组，每组保留质量最优的一份，删除冗余副本。
- 重复 ID：同章同 seq 但题干不同的题目，保留两题内容，仅把后续题目重新编号，
  避免删除实质内容。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "quiz_categorized.json"
JS_PATH = ROOT / "data" / "quiz_categorized.js"

# 答案冲突的历史重复对：指定保留哪个 ID（避免按分析长度误删正确版本）。
KEEP_OVERRIDES = {
    "1-0432": "keep",
    "10-0820": "keep",
    "2-0830": "keep",
    "3-1412": "keep",
    "4-0443": "keep",
    "10-1302": "keep",
    "10-1301": "keep",
}


def norm(s: str) -> str:
    return re.sub(r"\s", "", s or "")


def score(q: dict) -> tuple:
    # 1) 有解析优于无解析；2) 解析更长；3) 章节/seq 作为稳定决胜
    has_analysis = 1 if (q.get("analysis") or "").strip() and q.get("analysis") != "暂无" else 0
    analysis_len = len(q.get("analysis") or "")
    return (has_analysis, analysis_len, -int(str(q.get("chapter", 0)) or 0), -int(str(q.get("seq", 0)) or 0))


def main() -> int:
    bank = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    by_ch = bank["questions_by_chapter"]

    # ---------- Step 1: 去重题干 ----------
    groups = {}
    for ch, arr in by_ch.items():
        for q in arr:
            key = norm(q.get("stem", ""))
            groups.setdefault(key, []).append((ch, q))

    removed_stem = []
    for key, items in groups.items():
        if len(items) < 2:
            continue
        # 若存在冲突且指定了保留 ID，优先保留该 ID
        keep_idx = None
        for i, (ch, q) in enumerate(items):
            qid = f"{ch}-{q.get('seq')}"
            if qid in KEEP_OVERRIDES:
                keep_idx = i
                break
        if keep_idx is None:
            # 否则保留评分最高者
            keep_idx = max(range(len(items)), key=lambda i: score(items[i][1]))
        for i, (ch, q) in enumerate(items):
            if i == keep_idx:
                continue
            removed_stem.append((f"{ch}-{q.get('seq')}", q.get("stem", "")))
            by_ch[ch].remove(q)

    # ---------- Step 2: 处理同章同 seq 的重复 ID ----------
    free_seq = 6001
    used_seqs = {str(q.get("seq")) for arr in by_ch.values() for q in arr}
    while str(free_seq) in used_seqs:
        free_seq += 1

    renumbered = []
    for ch, arr in by_ch.items():
        seen = {}
        for q in arr:
            seq = str(q.get("seq"))
            if seq in seen:
                new_seq = str(free_seq)
                while new_seq in used_seqs:
                    free_seq += 1
                    new_seq = str(free_seq)
                old_seq = q.get("seq")
                q["seq"] = new_seq
                used_seqs.add(new_seq)
                free_seq += 1
                renumbered.append((ch, old_seq, new_seq, q.get("stem", "")))
            seen[seq] = q

    # ---------- 更新统计 ----------
    total = sum(len(v) for v in by_ch.values())
    diff = {"入门": 0, "进阶": 0, "挑战": 0}
    for arr in by_ch.values():
        for q in arr:
            label = q.get("difficulty_label", "进阶")
            if label in diff:
                diff[label] += 1
    bank["questions_by_chapter"] = by_ch
    bank["total"] = total
    bank["difficulty_counts"] = diff

    JSON_PATH.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")

    chapters = bank["chapters"]
    js = (
        "const QUIZ_CHAPTERS = " + json.dumps(chapters, ensure_ascii=False) + ";\n\n"
        "const QUIZ_DATA_BY_CHAPTER = " + json.dumps(by_ch, ensure_ascii=False, separators=(",", ":")) + ";\n"
    )
    JS_PATH.write_text(js, encoding="utf-8")

    print(f"删除重复题干: {len(removed_stem)} 题")
    for qid, stem in removed_stem:
        print(f"  - {qid}: {stem[:60]}")
    print(f"重新编号重复 ID: {len(renumbered)} 题")
    for ch, old, new, stem in renumbered:
        print(f"  - {ch}-{old} -> {ch}-{new}: {stem[:60]}")
    print(f"总题数: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
