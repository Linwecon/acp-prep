# -*- coding: utf-8 -*-
"""一次性脚本：重新分配单选题的答案字母，降低 A/B 过度集中、提升 C/D 占比。

做法：只处理 type==0、恰好 4 个选项、解析不含字母引用、且无"以上/交叉引用/有序数值"的题。
把正确选项移动到目标位置并重新编号（A/B/C/D），选项文字内容完全不变，解析无需改动。

用法: python scripts/rebalance_answers.py
注意: 脚本运行一次后，被处理的题答案会变为 C/D，重复运行会挑选下一批 A/B 题，请勿重复运行。
"""
import collections
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "quiz_categorized.js"

LETTER_REF = re.compile(r"[ABCD]\s*(正确|错误|选项|项|答案|对|错|：|、|和|与|及|或|表示|指|对应|是)")
CROSS_REF = re.compile(r"[ABCD]\s*(和|与|及|、|或)\s*[ABCD]")


def is_safe(q):
    """仅允许：单选、4 选项、解析无字母引用、无以上/交叉引用/有序数值。"""
    if q.get("type") != 0:
        return False
    if len(q.get("options", [])) != 4:
        return False
    if LETTER_REF.search(q.get("analysis") or ""):
        return False
    ts = [(o.get("option_text") or "").strip() for o in q.get("options", [])]
    if any("以上" in t for t in ts):
        return False
    if any(CROSS_REF.search(t) for t in ts):
        return False
    if all(re.match(r"^\d+(\.\d+)?$", t) for t in ts):
        return False
    if all(re.match(r"^[一二三四五六七八九十]+[、.．\s]", t) for t in ts):
        return False
    if all(re.match(r"^\d+[、.．\s]", t) for t in ts):
        return False
    return True


def apply_move(q, new_idx):
    """把正确选项移动到 new_idx（0-based），其余选项保持相对顺序，重新编号。"""
    old_idx = ord(q["answer"]) - ord("A")
    opts = list(q["options"])
    item = opts.pop(old_idx)
    opts.insert(new_idx, item)
    for i, o in enumerate(opts):
        o["option_label"] = chr(ord("A") + i)
    q["options"] = opts
    q["answer"] = chr(ord("A") + new_idx)


def largest_remainder(weights, n):
    """按权重分配 n 个名额（最大余数法）。weights: {key: float}"""
    total = sum(weights.values())
    if total <= 0:
        return {}
    quota = {k: w / total * n for k, w in weights.items()}
    alloc = {k: int(v) for k, v in quota.items()}
    rem = n - sum(alloc.values())
    for k, _ in sorted(quota.items(), key=lambda kv: -(quota[kv[0]] - alloc[kv[0]])):
        if rem <= 0:
            break
        alloc[k] += 1
        rem -= 1
    return alloc


def pick_spread(items, n):
    """从按 seq 排序的列表里均匀抽取 n 个（避免产生新的连续段）。"""
    if n <= 0:
        return []
    if n >= len(items):
        return items
    step = len(items) / n
    out = []
    for i in range(n):
        out.append(items[int(i * step)])
    return out


def main() -> int:
    raw = SRC.read_text(encoding="utf-8")
    m = re.search(r"const\s+QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\})", raw, re.S)
    data = json.loads(m.group(1).rstrip().rstrip(";"))

    # 按章收集：单选总数 / A 数 / B 数
    chapters = sorted(data, key=lambda c: int(c))
    sc_count, a_count, b_count = {}, {}, {}
    for ch in chapters:
        qs = [q for q in data[ch] if q.get("type") == 0]
        sc_count[ch] = len(qs)
        a_count[ch] = sum(1 for q in qs if q.get("answer") == "A")
        b_count[ch] = sum(1 for q in qs if q.get("answer") == "B")

    # 超额量 = max(0, 实际数 - 均衡数)，作为分配权重
    def excess(count):
        return {ch: max(0, count[ch] - round(sc_count[ch] / 4)) for ch in chapters}

    N_A, N_B = 60, 30
    alloc_a = largest_remainder(excess(a_count), N_A)
    alloc_b = largest_remainder(excess(b_count), N_B)

    # 收集安全候选（按 seq 排序）
    safe_a, safe_b = {}, {}
    for ch in chapters:
        qs = sorted(
            (q for q in data[ch] if q.get("answer") == "A" and is_safe(q)),
            key=lambda q: int(q.get("seq", 0)),
        )
        safe_a[ch] = qs
        qs = sorted(
            (q for q in data[ch] if q.get("answer") == "B" and is_safe(q)),
            key=lambda q: int(q.get("seq", 0)),
        )
        safe_b[ch] = qs

    selected = []  # (ch, q, from_letter)
    for ch in chapters:
        for q in pick_spread(safe_a[ch], alloc_a.get(ch, 0)):
            selected.append((ch, q, "A"))
        for q in pick_spread(safe_b[ch], alloc_b.get(ch, 0)):
            selected.append((ch, q, "B"))

    # 按 (章, seq) 排序后，用 D,D,C 循环分配目标字母 → 合计 60 D + 30 C
    selected.sort(key=lambda x: (int(x[0]), int(x[1].get("seq", 0))))
    target_cycle = ["D", "D", "C"]
    log = []
    for i, (ch, q, src) in enumerate(selected):
        tgt = target_cycle[i % len(target_cycle)]
        new_idx = ord(tgt) - ord("A")
        old_ans = q["answer"]
        apply_move(q, new_idx)
        log.append(f"{ch}-{q['seq']}: {old_ans}->{q['answer']}  {q['stem'][:26]}")

    SRC.write_text(raw[: m.start(1)] + json.dumps(data, ensure_ascii=False) + raw[m.end(1):], encoding="utf-8")

    print(f"共改写 {len(selected)} 题：")
    for line in log:
        print(" ", line)

    print("\n—— 改写后单选题答案分布 ——")
    cnt = collections.Counter()
    for ch in chapters:
        for q in data[ch]:
            if q.get("type") == 0:
                cnt[q.get("answer")] += 1
    total = sum(cnt.values())
    for k in "ABCD":
        print(f"  {k}: {cnt.get(k, 0):>4} ({cnt.get(k, 0) / total * 100:.0f}%)")

    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "compress_bank.py")], cwd=ROOT)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
