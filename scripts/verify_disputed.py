# -*- coding: utf-8 -*-
"""争议题多方验证 + 解析生成 + 题库修正

针对 verify_answers.py 判定的争议题（两模型冲突 / 无法作答），
用更多模型独立投票得出最终答案，并为每道题生成解析。

子命令:
    python scripts/verify_disputed.py --vote      # 多模型投票 → data/verify_final.json
    python scripts/verify_disputed.py --apply     # 按投票结果修正 data/quiz_categorized.js
    python scripts/verify_disputed.py --report    # 生成修正报告 docs/verify_final_report.md

投票规则（6 模型：qwen-plus、deepseek-v3.2 + 4 个新增模型）:
    - 最多票答案 ≠ 题库答案 且 票数 ≥ 3  → fix（修正答案 + 写入解析）
    - 最多票答案 == 题库答案             → keep（保留答案 + 补充解析）
    - 平票 / 票数 < 3                   → undecided（保留题库答案，解析标注争议）
"""
import argparse
import json
import pathlib
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from verify_answers import chat, parse_json, PROMPT  # noqa: E402

CFG_FILE = ROOT / "config" / "verify_config.json"
SRC = ROOT / "data" / "quiz_categorized.js"
VERIFY_RESULTS = ROOT / "data" / "verify_results.json"
VOTES = ROOT / "data" / "verify_votes.json"
FINAL = ROOT / "data" / "verify_final.json"
REPORT = ROOT / "docs" / "verify_final_report.md"

# 追加投票模型（不同厂商，避免单一训练数据偏差）
EXTRA_MODELS = ["qwen3.7-max", "kimi-k2.6", "glm-5.2", "MiniMax-M2.5"]
MAJORITY = 3  # 修正所需最少票数
ANALYSIS_MODEL = "qwen-plus"  # 解析生成模型（需响应快）

ANALYSIS_PROMPT = """你是阿里云大模型高级工程师认证（ACP）的解析撰写专家。请为下面这道{kind}题撰写答案解析。

【题目】
{stem}

【选项】
{options}

【标准答案】
{ans}

【要求】
1. 只输出 JSON：{{"analysis": "解析文本"}}
2. 解析 100~180 字：先说明正确答案为什么对（可引用阿里云官方概念/API/平台能力），再点出错误选项的关键问题
3. 不要提及"模型投票"等外部过程，直接写面向考生的解析"""


def load_bank():
    raw = SRC.read_text(encoding="utf-8")
    m = re.search(r"const\s+QUIZ_CHAPTERS\s*=\s*(\{.*?\});", raw, re.S)
    chapters = json.loads(m.group(1)) if m else {}
    m = re.search(r"const\s+QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\})", raw, re.S)
    data = json.loads(m.group(1).rstrip().rstrip(";"))
    return data, chapters


def ask(cfg, model, q):
    kind = "多选" if q["multi"] else "单选"
    options = "\n".join(f"{label}. {text}" for label, text in q["options"]) or "（无选项）"
    prompt = PROMPT.format(kind=kind, stem=q["stem"], options=options)
    text = chat(cfg, model, [
        {"role": "system", "content": "你是严谨的考试题目审校专家，答案必须基于阿里云官方文档与公开知识。"},
        {"role": "user", "content": prompt},
    ])
    obj = parse_json(text)
    if not obj:
        return []
    ans = obj.get("answer") or []
    return sorted({re.sub(r"[^A-G]", "", str(a)).upper() for a in ans if re.match(r"[A-G]", str(a))})


def gen_analysis(cfg, model, q, final_ans, disputed=False):
    kind = "多选" if q["multi"] else "单选"
    options = "\n".join(f"{label}. {text}" for label, text in q["options"]) or "（无选项）"
    ans = ",".join(final_ans) if final_ans else "（争议未决，请以官方文档为准）"
    prompt = ANALYSIS_PROMPT.format(kind=kind, stem=q["stem"], options=options, ans=ans)
    if disputed:
        prompt += "\n4. 本题存在不同意见，解析需客观说明争议点，提醒考生查阅官方文档核实"
    text = chat(cfg, model, [
        {"role": "system", "content": "你是严谨的考试解析撰写专家。"},
        {"role": "user", "content": prompt},
    ], timeout=150)
    obj = parse_json(text)
    return (obj or {}).get("analysis", "").strip() or "（解析生成失败）"


def decide(bank_ans, votes):
    """votes: {model: [A,B]} → (status, final_ans, details)
    details: {model: [答案]}，用于报告展示"""
    counted = Counter()
    details = {}
    for model, ans in votes.items():
        key = tuple(ans) if ans else ("∅",)
        counted[key] += 1
        details[model] = ans
    if not counted:
        return "undecided", bank_ans, details
    top_key, top_n = counted.most_common(1)[0]
    # 多数模型无法作答 → 未决，不修正
    if top_key == ("∅",):
        return "undecided", bank_ans, details
    # 平票（最高票不唯一）→ 保守处理为未决
    if len(counted) > 1 and counted.most_common(2)[1][1] == top_n:
        return "undecided", bank_ans, details
    final_ans = list(top_key)
    if top_n >= MAJORITY:
        if tuple(bank_ans) == top_key:
            return "keep", bank_ans, details
        return "fix", final_ans, details
    return "undecided", bank_ans, details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vote", action="store_true", help="多模型投票")
    ap.add_argument("--apply", action="store_true", help="修正题库")
    ap.add_argument("--report", action="store_true", help="生成报告")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    cfg = json.loads(CFG_FILE.read_text(encoding="utf-8"))
    data, chapters = load_bank()
    vres = json.loads(VERIFY_RESULTS.read_text(encoding="utf-8"))

    # 争议题 = 主模型非 agree
    qid2q = {}
    for ch, qs in data.items():
        seen = set()
        for q in qs:
            qid = f"{ch}-{q['seq']}"
            if qid in seen:
                qid += "b"
            seen.add(qid)
            qid2q[qid] = {
                "ch": ch, "seq": q["seq"], "stem": q.get("stem", ""),
                "options": [(o["option_label"], o["option_text"]) for o in q.get("options", [])],
                "bank": [re.sub(r"\s", "", x) for x in re.findall(r"[A-G]", str(q.get("answer", "")))]
                       or [x.strip() for x in str(q.get("answer", "")).split(",") if x.strip()],
                "multi": True if q.get("type") == 2 else len(re.findall(r"[A-G]", str(q.get("answer", "")))) > 1,
            }
    disputed = {qid: r for qid, r in vres.items() if r["primary"]["verdict"] != "agree"}
    print(f"争议题: {len(disputed)} 题 | 追加投票模型: {EXTRA_MODELS}")

    if args.vote:
        final = {}
        if FINAL.exists():
            final = json.loads(FINAL.read_text(encoding="utf-8"))
        # 投票结果缓存：已存在则直接复用（断点续跑）
        votes_map = {}
        if VOTES.exists():
            votes_map = json.loads(VOTES.read_text(encoding="utf-8"))
        todo = {qid: qid2q[qid] for qid in disputed if qid not in votes_map}

        def vote_one(item):
            qid, q = item
            votes = {cfg.get("primary_model", "qwen-plus"): disputed[qid]["primary"]["answer"]}
            if disputed[qid].get("secondary"):
                votes[cfg.get("secondary_model", "deepseek-v3.2")] = disputed[qid]["secondary"]["answer"]
            for m in EXTRA_MODELS:
                votes[m] = ask(cfg, m, q)
            return qid, votes

        if todo:
            done = 0
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(vote_one, it): it[0] for it in todo.items()}
                for fut in as_completed(futs):
                    qid, votes = fut.result()
                    votes_map[qid] = votes
                    done += 1
                    if done % 40 == 0:
                        VOTES.write_text(json.dumps(votes_map, ensure_ascii=False), encoding="utf-8")
                        print(f"  投票进度 {done}/{len(todo)}")
            VOTES.write_text(json.dumps(votes_map, ensure_ascii=False), encoding="utf-8")
        print(f"投票完成: {len(votes_map)} 题（含缓存）")

        def finalize(item):
            qid, votes = item
            q = qid2q[qid]
            status, final_ans, tally = decide(q["bank"], votes)
            disputed_analysis = status == "undecided" and (not final_ans or tuple(final_ans) != tuple(q["bank"]))
            analysis = gen_analysis(cfg, ANALYSIS_MODEL, q, final_ans or q["bank"], disputed=disputed_analysis)
            return qid, {
                "qid": qid, "ch": q["ch"], "seq": q["seq"],
                "kind": "多选" if q["multi"] else "单选",
                "bank": q["bank"], "status": status, "final": final_ans,
                "tally": {m: list(a) for m, a in tally.items()},
                "analysis": analysis,
            }

        todo2 = {qid: v for qid, v in votes_map.items() if qid not in final}
        done2 = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(finalize, it): it[0] for it in todo2.items()}
            for fut in as_completed(futs):
                qid, rec = fut.result()
                final[qid] = rec
                done2 += 1
                if done2 % 20 == 0:
                    FINAL.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
                    print(f"  解析进度 {done2}/{len(todo2)}")
        FINAL.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"解析完成 → {FINAL}")

    final = json.loads(FINAL.read_text(encoding="utf-8")) if FINAL.exists() else {}
    if args.apply:
        n_fix = n_keep = n_und = 0
        for qid, f in final.items():
            ch = f["ch"]
            # 按出现顺序精确匹配（同章同 seq 的撞号题第二个为 qid+b 后缀）
            seen = set()
            target = None
            for x in data.get(ch, []):
                s = str(x.get("seq"))
                key = s if s not in seen else s + "b"
                seen.add(s)
                if f"{ch}-{key}" == qid:
                    target = x
                    break
            if target is None:
                continue
            # 只修正有明确唯一票源的题（fix）
            if f["status"] == "fix" and f["final"]:
                target["answer"] = ",".join(f["final"])
                n_fix += 1
            elif f["status"] == "keep":
                n_keep += 1
            else:
                n_und += 1
            if f.get("analysis"):
                target["analysis"] = f["analysis"]
        js = "const QUIZ_CHAPTERS = " + json.dumps(chapters, ensure_ascii=False) + ";\n\n" \
             "const QUIZ_DATA_BY_CHAPTER = " + json.dumps(data, ensure_ascii=False) + ";\n"
        SRC.write_text(js, encoding="utf-8")
        print(f"已写入 {SRC}：修正 {n_fix} 题答案，补充解析 {n_keep + n_fix + n_und} 题，未决 {n_und} 题")

    if args.report:
        lines = [
            "# 争议题多方验证与修正报告",
            "",
            f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')} · "
            f"投票模型：qwen-plus、deepseek-v3.2、{'、'.join(EXTRA_MODELS)} · 修正阈值：≥{MAJORITY} 票",
            "",
            "## 一、结论",
            "",
            "| 状态 | 数量 | 说明 |",
            "|------|-----:|------|",
        ]
        cnt = Counter(f["status"] for f in final.values())
        lines += [
            f"| ✏️ 修正 (fix) | {cnt.get('fix', 0)} | 多数模型（≥{MAJORITY}票）认为题库答案有误，已修正 |",
            f"| ✅ 保留 (keep) | {cnt.get('keep', 0)} | 多数模型支持题库答案，已补充解析 |",
            f"| ⚠️ 未决 (undecided) | {cnt.get('undecided', 0)} | 模型意见分歧，保留原答案，解析标注争议 |",
            "",
            "## 二、修正明细（fix）",
            "",
        ]
        fixes = [f for f in final.values() if f["status"] == "fix"]
        if fixes:
            lines.append("| 题号 | 类型 | 原答案 | 新答案 | 票数分布 |")
            lines.append("|------|------|--------|--------|---------|")
            for f in fixes:
                tally = "、".join(f"{m}:{','.join(a) or '∅'}" for m, a in f["tally"].items())
                qid = f.get("qid", f"{f['ch']}-{f['seq']}")
                lines.append(f"| {qid} | {f['kind']} | {','.join(f['bank']) or '空'} | "
                             f"{','.join(f['final']) or '空'} | {tally} |")
            lines += ["", "### 修正题解析", ""]
            for f in fixes:
                qid = f.get("qid", f"{f['ch']}-{f['seq']}")
                lines.append(f"**{qid}**（原答案 {','.join(f['bank']) or '空'} → 新答案 {','.join(f['final'])}）")
                lines.append(f"> {f.get('analysis', '')}")
                lines.append("")
        else:
            lines.append("无修正题。")
        lines += ["", "## 三、未决题（undecided）", ""]
        unds = [f for f in final.values() if f["status"] == "undecided"]
        if unds:
            lines.append("| 题号 | 题库答案 | 模型票数分布 |")
            lines.append("|------|---------|-------------|")
            for f in unds:
                tally = "、".join(f"{m}:{','.join(a) or '∅'}" for m, a in f["tally"].items())
                qid = f.get("qid", f"{f['ch']}-{f['seq']}")
                lines.append(f"| {qid} | {','.join(f['bank']) or '空'} | {tally} |")
        else:
            lines.append("无未决题。")
        REPORT.write_text("\n".join(lines), encoding="utf-8")
        print(f"报告已写入: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
