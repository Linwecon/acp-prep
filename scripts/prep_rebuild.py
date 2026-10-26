# -*- coding: utf-8 -*-
"""重构准备：为每道在用题打缺陷标记，输出待处理清单与逐章内容文件（只读题库）。

用法:
    python scripts/prep_rebuild.py

输出:
    data/curate/rebuild/attention.json   每题缺陷标记（含完整内容）
    data/curate/rebuild/clusters.json    重复簇（Jaccard>=0.72 连通分量）
    data/curate/rebuild/keep_plain.json  无缺陷信号的题（决策=保留）
    data/curate/rebuild/by_ch/chN.json   每章待处理题完整内容（供逐题复核）
"""
import json, re, pathlib, collections, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "curate" / "rebuild"
OUT.mkdir(parents=True, exist_ok=True)

CTX_PAT = re.compile(
    r"(如上图|如下图|如图|见图|参照图|上图|下图|图中(?!.{0,3}像)|"
    r"上述代码|以上代码|该代码|这段代码|下列代码|代码中|脚本中|"
    r"根据(上文|上述材料|给定材料|资料)|结合(材料|上文)|"
    r"阅读(以下|下面|上文)|上文(提到|所述)|本章|本节|教材第?\s*\d|第\s*\d+\.\d+\s*节|"
    r"上一题|本题材料|题目所给|示例(中|里)的|前文)"
)
ABS_PAT = re.compile(r"(只能|必须|完全|永远|任何(情况)?下都|一定不|绝不会|只需|唯一|所有…?都|不可能)")
# 教材私有函数/类名题（脱离教材代码无法作答）
PRIVATE_FN = re.compile(r"\b(extract_tags|ask_lm_route|ask_llm_route|abstract_generator|"
                        r"get_course_outline|generate_suggestions|custom_prompt|my_llm|"
                        r"llm_with_tools|invoke_func|function_call)\b")


def norm_ans(ans):
    ans = re.sub(r"\s", "", str(ans or ""))
    return [s for s in ans.split(",") if s] if "," in ans else [c for c in ans if re.match(r"[A-H]", c)]


def bigrams(s):
    s = re.sub(r"[\s，。、；：？！“”\"'（）()\[\]{}·\-—_*#/\\|]+", "", str(s)).lower()
    return {s[i:i+2] for i in range(len(s)-1)} if len(s) > 1 else {s}


def jac(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main():
    data = json.loads((ROOT / "data" / "quiz_categorized.json").read_text(encoding="utf-8"))
    by_ch = data["questions_by_chapter"]
    active = []
    for ch, arr in sorted(by_ch.items(), key=lambda kv: int(kv[0])):
        for q in arr:
            if q.get("deleted"):
                continue
            rec = dict(q)
            rec["_ch"] = str(ch)
            rec["_id"] = f"{ch}-{str(q['seq']).zfill(4)}"
            rec["_ans"] = norm_ans(q.get("answer", ""))
            rec["_multi"] = len(rec["_ans"]) > 1 or q.get("type") == 2
            rec["_bg"] = bigrams(q.get("stem", ""))
            active.append(rec)

    flags = {r["_id"]: [] for r in active}
    by_id = {r["_id"]: r for r in active}

    # 1. 结构异常
    for r in active:
        if r["_multi"] and len(r["_ans"]) < 2:
            flags[r["_id"]].append("multi_but_single_answer")
        if len(r.get("options", [])) < 4:
            flags[r["_id"]].append("few_options")
        if r.get("image"):
            flags[r["_id"]].append("image_dependency")
        if not str(r.get("stem", "")).strip():
            flags[r["_id"]].append("empty_stem")

    # 2. 解析
    for r in active:
        an = str(r.get("analysis", "")).strip()
        if not an or an == "暂无":
            flags[r["_id"]].append("no_analysis")
        elif len(an) < 25:
            flags[r["_id"]].append("thin_analysis")

    # 3. 上下文依赖
    for r in active:
        if CTX_PAT.search(str(r.get("stem", ""))):
            flags[r["_id"]].append("context_dependent")
        if PRIVATE_FN.search(str(r.get("stem", "")) + " ".join(
                str(o.get("option_text", "")) for o in r.get("options", []))):
            flags[r["_id"]].append("private_function_reference")

    # 4. 选项泄露
    for r in active:
        opts = r.get("options", [])
        lens = [len(str(o.get("option_text", ""))) for o in opts]
        ans_set = set(r["_ans"])
        wrong_lens = [l for o, l in zip(opts, lens) if o.get("option_label") not in ans_set]
        if wrong_lens and len(opts) >= 4:
            ans_max = max([l for o, l in zip(opts, lens) if o.get("option_label") in ans_set] or [0])
            if ans_max - max(wrong_lens) > 25 and lens.count(ans_max) == 1:
                flags[r["_id"]].append("longest_is_answer_leak")
        abs_labels = [o.get("option_label") for o in opts if ABS_PAT.search(str(o.get("option_text", "")))]
        if abs_labels and all(l not in ans_set for l in abs_labels) and len(abs_labels) == len(opts) - len(ans_set):
            flags[r["_id"]].append("abs_words_only_on_distractors")

    # 5. 重复簇（连通分量）
    n = len(active)
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    pair_details = []
    for i in range(n):
        for j in range(i + 1, n):
            if not active[i]["_bg"] or not active[j]["_bg"]:
                continue
            s = jac(active[i]["_bg"], active[j]["_bg"])
            if s >= 0.72:
                union(i, j)
                pair_details.append({"a": active[i]["_id"], "b": active[j]["_id"],
                                     "sim": round(s, 3),
                                     "same_answer": active[i]["_ans"] == active[j]["_ans"]})
    groups = collections.defaultdict(list)
    for idx in range(n):
        groups[find(idx)].append(active[idx]["_id"])
    clusters = [sorted(v) for v in groups.values() if len(v) > 1]
    for cl in clusters:
        for qid in cl:
            flags[qid].append("duplicate_cluster")

    # 汇总
    attention, keep = [], []
    for r in active:
        f = flags[r["_id"]]
        if f:
            attention.append({"id": r["_id"], "ch": r["_ch"], "flags": f})
        else:
            keep.append(r["_id"])

    (OUT / "keep_plain.json").write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
    att = [{"id": a["id"], "ch": a["ch"], "flags": a["flags"],
            "stem": by_id[a["id"]]["stem"], "answer": by_id[a["id"]].get("answer"),
            "type": by_id[a["id"]].get("type")} for a in attention]
    (OUT / "attention.json").write_text(json.dumps(att, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "clusters.json").write_text(json.dumps(
        {"clusters": clusters, "pairs": pair_details}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 逐章完整内容文件
    bch = OUT / "by_ch"
    bch.mkdir(exist_ok=True)
    att_ids = {a["id"] for a in attention}
    for ch in sorted({a["ch"] for a in attention}, key=int):
        items = []
        for a in attention:
            if a["ch"] != ch:
                continue
            r = by_id[a["id"]]
            items.append({"id": a["id"], "flags": a["flags"],
                          "type": r.get("type"), "stem": r.get("stem"),
                          "options": [{"l": o.get("option_label"), "x": o.get("option_text")}
                                      for o in r.get("options", [])],
                          "answer": r.get("answer"), "analysis": r.get("analysis"),
                          "difficulty_label": r.get("difficulty_label")})
        (bch / f"ch{ch}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    flag_counts = collections.Counter(f for a in attention for f in a["flags"])
    print(f"在用 {n} · 待处理 {len(attention)} · 干净保留 {len(keep)}")
    print("信号分布:", dict(flag_counts))
    print(f"重复簇: {len(clusters)} 组，涉及 {sum(len(c) for c in clusters)} 题")
    per_ch = collections.Counter(a["ch"] for a in attention)
    print("待处理按章:", dict(sorted(per_ch.items(), key=lambda kv: int(kv[0]))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
