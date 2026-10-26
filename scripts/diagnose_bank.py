# -*- coding: utf-8 -*-
"""题库重构前的全库诊断（只读，不修改题库）。

输出: data/curate/rebuild_diagnosis.json + docs/题库重构诊断.md

用法:
    python scripts/diagnose_bank.py
"""
import json
import pathlib
import re
import sys
import collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "quiz_categorized.json"
OUT_JSON = ROOT / "data" / "curate" / "rebuild_diagnosis.json"
OUT_MD = ROOT / "docs" / "题库重构诊断.md"

# 与 js/acp.js 的 EXAM_DOMAINS 保持一致
DOMAIN_CHS = {
    "大模型应用开发": ["1", "9", "10", "12"],
    "大模型提示词工程": ["2"],
    "大模型检索增强": ["3"],
    "大模型微调": ["5"],
    "多Agent及多模态应用": ["4", "11"],
    "生产环境应用实践": ["6", "7", "8"],
}
DOMAIN_PCT = {"大模型应用开发": 17, "大模型提示词工程": 15, "大模型检索增强": 20,
              "大模型微调": 16, "多Agent及多模态应用": 16, "生产环境应用实践": 16}
EXAM_SINGLE, EXAM_MULTI = 50, 25

CH_OF_DOMAIN = {ch: d for d, chs in DOMAIN_CHS.items() for ch in chs}


def quota_alloc(total, pcts):
    raw = [total * p / 100 for p in pcts]
    base = [int(r // 1) for r in raw]
    remain = total - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))
    for k in range(remain):
        base[order[k]] += 1
    return base


def norm_ans(ans):
    ans = re.sub(r"\s", "", str(ans or ""))
    if "," in ans:
        return [s for s in ans.split(",") if s]
    return [c for c in ans if re.match(r"[A-H]", c)]


def bigrams(s):
    s = re.sub(r"[\s，。、；：？！“”\"'（）()\[\]{}·\-—_*#/\\|]+", "", s).lower()
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------- 信号规则 ----------
# 真正的上下文依赖：明确指代未提供的材料/图/代码/前文
CTX_PAT = re.compile(
    r"(如上图|如下图|如图|见图|参照图|上图|下图|图中(?!.{0,3}像)|"
    r"上述代码|以上代码|该代码|这段代码|下列代码|代码中|脚本中|"
    r"根据(上文|上述材料|给定材料|资料)|结合(材料|上文)|"
    r"阅读(以下|下面|上文)|上文(提到|所述)|本章|本节|教材第?\s*\d|第\s*\d+\.\d+\s*节|"
    r"上一题|本题材料|题目所给|示例(中|里)的|前文)"
)
# 送分/荒谬干扰项信号：过短且无信息量的选项
JUNK_OPT = re.compile(r"^(以上(都|均)?(是|对)|无法(确定|判断)|不知道|其他(选项)?|无|空|略)$")
# 绝对化措辞（常泄露错误项，也常出现在正确项）
ABS_PAT = re.compile(r"(只能|必须|完全|永远|任何(情况)?下都|一定不|绝不会|只需|唯一|所有…?都|不可能)")


def main() -> int:
    data = json.loads(BANK.read_text(encoding="utf-8"))
    by_ch = data["questions_by_chapter"]
    chapters = data["chapters"]

    active, deleted = [], []
    for ch, arr in by_ch.items():
        for q in arr:
            rec = dict(q)
            rec["_ch"] = str(ch)
            rec["_id"] = f"{ch}-{q.get('seq')}"
            rec["_domain"] = CH_OF_DOMAIN.get(str(ch), "?")
            ans = norm_ans(q.get("answer"))
            rec["_ans"] = ans
            rec["_multi"] = len(ans) > 1 or q.get("type") == 2
            (deleted if q.get("deleted") else active).append(rec)

    diag = {
        "bank_sha256": data.get("bank_sha256"),
        "totals": {
            "raw": len(active) + len(deleted),
            "active": len(active),
            "deleted": len(deleted),
        },
    }

    # ---- 1. 结构合法性 ----
    struct = {"dup_id": [], "answer_not_in_options": [], "single_bad_answer": [],
              "multi_empty": [], "opt_count": collections.Counter(),
              "labels_not_sequential": [], "dup_option_text": [], "empty_stem": []}
    seen_ids = collections.Counter(r["_id"] for r in active + deleted)
    struct["dup_id"] = [k for k, v in seen_ids.items() if v > 1]
    for r in active:
        labels = [o.get("option_label") for o in r.get("options", [])]
        struct["opt_count"][len(labels)] += 1
        if any(a not in labels for a in r["_ans"]):
            struct["answer_not_in_options"].append(r["_id"])
        if not r["_multi"] and len(r["_ans"]) != 1:
            struct["single_bad_answer"].append(r["_id"])
        if r["_multi"] and len(r["_ans"]) < 2:
            struct["multi_empty"].append(r["_id"])
        expect = [chr(ord("A") + i) for i in range(len(labels))]
        if labels != expect:
            struct["labels_not_sequential"].append({"id": r["_id"], "labels": labels})
        texts = [re.sub(r"\s", "", o.get("option_text", "")) for o in r.get("options", [])]
        if len(set(texts)) != len(texts):
            struct["dup_option_text"].append(r["_id"])
        if not str(r.get("stem", "")).strip():
            struct["empty_stem"].append(r["_id"])
    diag["structure"] = {**{k: v for k, v in struct.items() if k != "opt_count"},
                         "opt_count": dict(struct["opt_count"])}

    # ---- 2. 解析质量 ----
    no_analysis = [r["_id"] for r in active
                   if not str(r.get("analysis", "")).strip() or str(r.get("analysis", "")).strip() == "暂无"]
    thin = [r["_id"] for r in active
            if 0 < len(str(r.get("analysis", "")).strip()) < 25]
    diag["analysis"] = {"missing_or_placeholder": len(no_analysis),
                        "missing_ids_sample": no_analysis[:40],
                        "thin_under_25chars": len(thin),
                        "thin_ids_sample": thin[:40]}

    # ---- 3. 题干上下文依赖（精确规则）----
    ctx = [{"id": r["_id"], "ch": r["_ch"], "stem": r["stem"][:120]}
           for r in active if CTX_PAT.search(str(r.get("stem", "")))]
    diag["context_dependent"] = {"count": len(ctx), "items": ctx}

    # ---- 4. 重复与近义换皮 ----
    exact = collections.Counter(re.sub(r"\s", "", str(r["stem"])) for r in active)
    diag["dup_exact_stem"] = {k: v for k, v in exact.items() if v > 1}
    # 题干 bigram 相似（同章优先，跨章也查）
    bg = [(r, bigrams(str(r["stem"]))) for r in active]
    near = []
    seen_pair = set()
    for i in range(len(bg)):
        ri, gi = bg[i]
        if not gi:
            continue
        for j in range(i + 1, len(bg)):
            rj, gj = bg[j]
            if not gj:
                continue
            s = jaccard(gi, gj)
            if s >= 0.72:
                key = (ri["_id"], rj["_id"])
                if key in seen_pair:
                    continue
                seen_pair.add(key)
                same_ans = ri["_ans"] == rj["_ans"]
                near.append({"a": ri["_id"], "b": rj["_id"], "sim": round(s, 3),
                             "same_ch": ri["_ch"] == rj["_ch"], "same_answer": same_ans,
                             "stem_a": str(ri["stem"])[:70], "stem_b": str(rj["stem"])[:70]})
    near.sort(key=lambda x: -x["sim"])
    diag["near_dup"] = {"pairs_ge_072": len(near), "items": near[:120]}

    # ---- 5. 选项质量信号 ----
    junk_opt, longest_is_answer, abs_only_wrong = [], [], []
    for r in active:
        opts = r.get("options", [])
        if not opts:
            continue
        for o in opts:
            if JUNK_OPT.match(re.sub(r"\s", "", str(o.get("option_text", "")))):
                junk_opt.append({"id": r["_id"], "label": o.get("option_label")})
        lens = [len(str(o.get("option_text", ""))) for o in opts]
        ans_set = set(r["_ans"])
        # 正确项显著长于所有错误项（长度差 > 25 且为最长）
        wrong_lens = [l for o, l in zip(opts, lens) if o.get("option_label") not in ans_set]
        if wrong_lens and max(lens) in [l for o, l in zip(opts, lens) if o.get("option_label") in ans_set]:
            if max(lens) - max(wrong_lens) > 25 and len(opts) >= 4:
                longest_is_answer.append(r["_id"])
        # 绝对词只出现在错误项
        abs_labels = [o.get("option_label") for o in opts if ABS_PAT.search(str(o.get("option_text", "")))]
        if abs_labels and all(l not in ans_set for l in abs_labels) and len(abs_labels) == len(opts) - len(ans_set):
            abs_only_wrong.append(r["_id"])
    diag["options"] = {
        "junk_option_hits": len(junk_opt), "junk_sample": junk_opt[:30],
        "longest_is_answer_leak": len(longest_is_answer), "longest_sample": longest_is_answer[:30],
        "abs_words_only_on_distractors": len(abs_only_wrong), "abs_sample": abs_only_wrong[:30],
    }

    # ---- 6. 答案字母分布 ----
    dist = collections.Counter()
    for r in active:
        if r["_multi"]:
            dist["+".join(sorted(r["_ans"]))] += 1
        else:
            dist[r["_ans"][0] if r["_ans"] else "?"] += 1
    diag["answer_distribution"] = dict(sorted(dist.items(), key=lambda kv: -kv[1])[:25])

    # ---- 7. 章节/知识域配额可行性 ----
    per_ch = collections.Counter(r["_ch"] for r in active)
    per_ch_multi = collections.Counter(r["_ch"] for r in active if r["_multi"])
    quota = {}
    names = list(DOMAIN_PCT)
    pcts = [DOMAIN_PCT[n] for n in names]
    sq = quota_alloc(EXAM_SINGLE, pcts)
    mq = quota_alloc(EXAM_MULTI, pcts)
    for i, name in enumerate(names):
        s = sum(per_ch[c] - per_ch_multi[c] for c in DOMAIN_CHS[name])
        m = sum(per_ch_multi[c] for c in DOMAIN_CHS[name])
        quota[name] = {"pct": DOMAIN_PCT[name], "need_single": sq[i], "avail_single": s,
                       "need_multi": mq[i], "avail_multi": m,
                       "ok": s >= sq[i] and m >= mq[i]}
    diag["domain_quota"] = quota
    diag["chapter_counts"] = {ch: {"total": per_ch[ch], "multi": per_ch_multi[ch],
                                   "single": per_ch[ch] - per_ch_multi[ch],
                                   "name": chapters.get(ch, "")} for ch in sorted(per_ch, key=int)}

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(diag, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- markdown 摘要 ----
    md = ["# 题库重构诊断（自动信号 + 人工复核清单）", ""]
    t = diag["totals"]
    md += [f"- 原始条目 {t['raw']}，在用 {t['active']}，软删除 {t['deleted']}", ""]
    md += ["## 结构合法性", f"- 重复 id：{len(diag['structure']['dup_id'])}",
           f"- 答案不在选项中：{len(diag['structure']['answer_not_in_options'])}",
           f"- 单选答案数异常：{len(diag['structure']['single_bad_answer'])}",
           f"- 多选答案不足 2：{len(diag['structure']['multi_empty'])}",
           f"- 选项标签非 A..N 顺序：{len(diag['structure']['labels_not_sequential'])}",
           f"- 同题重复选项文本：{len(diag['structure']['dup_option_text'])}",
           f"- 选项个数分布：{diag['structure']['opt_count']}", ""]
    a = diag["analysis"]
    md += ["## 解析质量", f"- 缺解析/占位“暂无”：{a['missing_or_placeholder']}",
           f"- 解析过短（<25 字）：{a['thin_under_25chars']}", ""]
    md += ["## 上下文依赖题干", f"- 命中 {diag['context_dependent']['count']} 条（需逐题改写或下架）", ""]
    md += ["## 重复与换皮", f"- 精确重复题干组：{len(diag['dup_exact_stem'])}",
           f"- 近似重复对（Jaccard>=0.72）：{diag['near_dup']['pairs_ge_072']}", ""]
    o = diag["options"]
    md += ["## 选项质量信号", f"- 送分/占位干扰项命中：{o['junk_option_hits']}",
           f"- 正确项异常偏长（可能泄题）：{o['longest_is_answer_leak']}",
           f"- 绝对词只出现在干扰项：{o['abs_words_only_on_distractors']}", ""]
    md += ["## 知识域抽题配额可行性", "",
           "| 知识域 | 比例 | 需单选 | 可用单选 | 需多选 | 可用多选 | 满足 |", "|---|---:|---:|---:|---:|---:|---|"]
    for name, v in quota.items():
        md.append(f"| {name} | {v['pct']}% | {v['need_single']} | {v['avail_single']} | "
                  f"{v['need_multi']} | {v['avail_multi']} | {'是' if v['ok'] else '否'} |")
    md += ["", "## 各章题量", "", "| 章 | 名称 | 在用 | 单选 | 多选 |", "|---|---|---:|---:|---:|"]
    for ch, v in diag["chapter_counts"].items():
        md.append(f"| {ch} | {v['name']} | {v['total']} | {v['single']} | {v['multi']} |")
    md += ["", "> 以上均为规则信号，用于定位待人工逐题复核的题，不构成内容正确性结论。", ""]
    md += ["## 近似重复对（Top 60）", ""]
    for it in diag["near_dup"]["items"][:60]:
        md.append(f"- {it['a']} ↔ {it['b']} sim={it['sim']} same_ch={it['same_ch']} "
                  f"same_ans={it['same_answer']}｜{it['stem_a']}｜{it['stem_b']}")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"在用 {t['active']} 题；诊断已写入 {OUT_JSON.relative_to(ROOT)} 与 {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
