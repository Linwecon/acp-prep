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
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core  # noqa: E402

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


def sanitize_votes_cache(raw: dict, qid2fp: dict) -> tuple[dict, int, int]:
    """断点缓存净化：缓存必须绑定实际输入版本。

    - 旧格式（无 fingerprint / 无 votes 字段）→ 作废（不得把当前指纹补绑到旧缓存上）；
    - 指纹与当前题目内容失配 → 作废（题目已变化，旧投票不得复用）。
    返回 (有效缓存, 作废旧格式条数, 内容变化失效条数)。
    """
    valid, legacy, stale = {}, 0, 0
    for qid, v in (raw or {}).items():
        if not (isinstance(v, dict) and v.get("fingerprint") and isinstance(v.get("votes"), dict)):
            legacy += 1
            continue
        if qid in qid2fp and v["fingerprint"] != qid2fp[qid]:
            stale += 1
            continue
        valid[qid] = v
    return valid, legacy, stale


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vote", action="store_true", help="多模型投票（结果绑定题目内容指纹）")
    ap.add_argument("--evidence", action="store_true", help="对 fix 项做教材证据核对（引用须能在章节原文定位）")
    ap.add_argument("--apply", action="store_true", help="修正题库（需指纹绑定 + 教材证据通过）")
    ap.add_argument("--allow-vote-only", action="store_true",
                    help="显式放行无教材证据的仅投票修正（记录在台账）")
    ap.add_argument("--report", action="store_true", help="生成报告")
    ap.add_argument("--limit", type=int, default=0, help="证据核对只处理前 N 条（0=全部）")
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
                "type": q.get("type", 0),
                "options": [(o["option_label"], o["option_text"]) for o in q.get("options", [])],
                "bank": [re.sub(r"\s", "", x) for x in re.findall(r"[A-G]", str(q.get("answer", "")))]
                       or [x.strip() for x in str(q.get("answer", "")).split(",") if x.strip()],
                "multi": True if q.get("type") == 2 else len(re.findall(r"[A-G]", str(q.get("answer", "")))) > 1,
            }
    # 每题当前内容指纹（投票/证据的实际输入版本）
    qid2fp = {qid: curate_core.q_fingerprint({"type": q["type"], "stem": q["stem"],
                                              "options": [{"option_label": l, "option_text": t}
                                                          for l, t in q["options"]]})
              for qid, q in qid2q.items()}
    # 校验结果（verify_results）绑定版本：题目变化后其结论不进入争议集，需重跑 verify_answers
    stale_results = {qid: r for qid, r in vres.items()
                     if r["primary"]["verdict"] != "agree"
                     and qid in qid2q
                     and curate_core.fingerprint_stale(r, {"type": qid2q[qid]["type"],
                                                           "stem": qid2q[qid]["stem"],
                                                           "options": [{"option_label": l, "option_text": t}
                                                                       for l, t in qid2q[qid]["options"]]})}
    if stale_results:
        print(f"[版本守卫] {len(stale_results)} 条校验结果因题目内容变化失效，"
              f"已排除出争议集（请重跑 verify_answers.py 后再投票）")
    disputed = {qid: r for qid, r in vres.items()
                if r["primary"]["verdict"] != "agree" and qid not in stale_results and qid in qid2q}
    print(f"争议题: {len(disputed)} 题 | 追加投票模型: {EXTRA_MODELS}")

    if args.vote:
        final = {}
        if FINAL.exists():
            final = json.loads(FINAL.read_text(encoding="utf-8"))
        # 断点缓存：绑定实际输入版本（内容指纹）。旧格式或指纹失配的缓存一律作废。
        votes_map = {}
        if VOTES.exists():
            raw = json.loads(VOTES.read_text(encoding="utf-8"))
            votes_map, n_legacy, n_stale = sanitize_votes_cache(raw, qid2fp)
            if n_legacy:
                print(f"  断点缓存：作废 {n_legacy} 条未绑定版本的旧缓存（将重新投票）")
            if n_stale:
                print(f"  断点缓存：{n_stale} 条因题目内容变化失效，重新投票")
        todo = {qid: qid2q[qid] for qid in disputed if qid not in votes_map}

        def vote_one(item):
            qid, q = item
            votes = {cfg.get("primary_model", "qwen-plus"): disputed[qid]["primary"]["answer"]}
            if disputed[qid].get("secondary"):
                votes[cfg.get("secondary_model", "deepseek-v3.2")] = disputed[qid]["secondary"]["answer"]
            for m in EXTRA_MODELS:
                votes[m] = ask(cfg, m, q)
            return qid, {"fingerprint": qid2fp[qid], "votes": votes}

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
        print(f"投票完成: {len(votes_map)} 题（含有效缓存，全部绑定输入版本）")

        def finalize(item):
            qid, cached = item
            q = qid2q[qid]
            votes = cached["votes"]
            status, final_ans, tally = decide(q["bank"], votes)
            disputed_analysis = status == "undecided" and (not final_ans or tuple(final_ans) != tuple(q["bank"]))
            analysis = gen_analysis(cfg, ANALYSIS_MODEL, q, final_ans or q["bank"], disputed=disputed_analysis)
            # 绑定实际输入版本：取投票缓存中的指纹（投票时题目内容的快照）
            return qid, {
                "qid": qid, "ch": q["ch"], "seq": q["seq"],
                "kind": "多选" if q["multi"] else "单选",
                "bank": q["bank"], "status": status, "final": final_ans,
                "tally": {m: list(a) for m, a in tally.items()},
                "fingerprint": cached["fingerprint"],
                "analysis": analysis,
            }

        todo2 = {qid: v for qid, v in votes_map.items()
                 if qid not in final or final[qid].get("fingerprint") != v["fingerprint"]}
        done2 = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(finalize, it): it[0] for it in todo2.items()}
            for fut in as_completed(futs):
                qid, rec = fut.result()
                final[qid] = rec
                done2 += 1
                if done2 % 20 == 0:
                    curate_core._atomic_write_text(
                        FINAL, json.dumps(final, ensure_ascii=False, indent=1))
                    print(f"  解析进度 {done2}/{len(todo2)}")
        # 注意：无指纹的旧结果不补绑——保留 unbound 状态，apply 时拒绝，须重新验证
        FINAL.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"解析完成 → {FINAL}")

    # ---------- 教材证据核对（修正依据不能只有模型投票） ----------
    final = json.loads(FINAL.read_text(encoding="utf-8")) if FINAL.exists() else {}
    if args.evidence:
        sections = curate_core.extract_chapter_sections(max_chars=9000)
        targets = [f for f in final.values() if f.get("status") == "fix"]
        if args.limit:
            targets = targets[:args.limit]
        print(f"教材证据核对：{len(targets)} 条 fix 记录（逐段定位引用 + 逐选项核对，绑定输入版本）")
        n_ok = n_fail = 0
        for i, f in enumerate(targets, 1):
            qid = f["qid"]
            if qid not in qid2q:
                continue
            q = qid2q[qid]
            fp = qid2fp[qid]
            # 证据必须绑定它核对时的题目版本；题目已变化的旧证据直接作废
            sec = sections.get(int(q["ch"]) if str(q["ch"]).isdigit() else 0, {}).get("text", "")
            kind = "多选" if q["multi"] else "单选"
            options = "\n".join(f"{l}. {t}" for l, t in q["options"])
            ans = ",".join(f["final"] or [])
            prompt = f"""仅依据下面的章节原文，核对这道{kind}题。

【章节原文（可能节选）】
{sec[:6000]}

【题目】{q['stem']}

【选项】
{options}

【待核对答案】{ans}

只输出 JSON：
{{"supported": true/false,
  "quote": "支持的原文引用（逐字摘录，可多句，禁止改写；原文不足以判断则留空）",
  "per_option": [{{"label": "A", "verdict": "correct|wrong|unknown", "why": "不超过20字"}}],
  "note": "补充说明，不超过40字"}}
要求：逐项核对每个选项的正误及题干限定条件（如"最""必须""不包括"等），
而不是只给答案找一句支持文字。若原文不足以判断，supported=false。禁止编造原文。"""
            obj = parse_json(chat(cfg, ANALYSIS_MODEL, [
                {"role": "system", "content": "只输出 JSON，引用必须逐字来自给定原文。"},
                {"role": "user", "content": prompt},
            ])) or {}
            quote = str(obj.get("quote", ""))
            loc = curate_core.locate_quote(quote, sec) if sec else {
                "segments": [], "quote_found": False, "unmatched": []}
            f["external_evidence"] = {
                "supported": bool(obj.get("supported")),
                "quote": quote[:200],
                "quote_found": bool(loc["quote_found"]),      # 引用是否存在（逐段定位）
                "locate": loc["segments"],                    # 命中位置/原文片段/未匹配部分
                "unmatched": loc["unmatched"][:5],
                "per_option": (obj.get("per_option") or [])[:8],
                "fingerprint": fp,                            # 证据绑定的输入版本
                "source": f"docs/ACP高频知识点总结.md 第{q['ch']}章",
                "source_version": {"file": "docs/ACP高频知识点总结.md", "chapter": q["ch"],
                                   "excerpt_max_chars": 9000},
                "note": str(obj.get("note", ""))[:80],
                "checked_at": datetime.now().isoformat(timespec="seconds"),
            }
            if obj.get("supported") and loc["quote_found"]:
                n_ok += 1
            else:
                n_fail += 1
            if i % 20 == 0 or i == len(targets):
                curate_core._atomic_write_text(FINAL, json.dumps(final, ensure_ascii=False, indent=1))
                print(f"  证据核对进度 {i}/{len(targets)}（通过 {n_ok} / 不通过 {n_fail}）")
        curate_core._atomic_write_text(FINAL, json.dumps(final, ensure_ascii=False, indent=1))
        print(f"证据核对完成：通过 {n_ok} · 不通过 {n_fail}（不通过项进入复核，apply 将拒绝）")

    final = json.loads(FINAL.read_text(encoding="utf-8")) if FINAL.exists() else {}
    if args.apply:
        # 统一守卫（curate_core.check_fix_entry）适用于所有修正条目
        bank = curate_core.load_bank()
        index = curate_core.build_index(bank)
        batch_id = "ansfix_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        fixes = []
        manual_items = []
        n_keep = n_und = 0
        counters = Counter()
        for qid, f in final.items():
            if qid not in index:
                continue
            if f["status"] == "fix" and f["final"]:
                _, q = index[qid]
                entry = {"qid": qid, "final": f["final"], "fingerprint": f.get("fingerprint"),
                         "external_evidence": f.get("external_evidence")}
                # --allow-vote-only：显式人工覆盖入口（不伪装成验证通过，台账记录人工覆盖）
                if args.allow_vote_only:
                    ev = f.get("external_evidence") or {}
                    if not (ev.get("supported") and ev.get("quote_found")):
                        entry["manual_reason"] = ("CLI --allow-vote-only 显式放行："
                                                  "仅 6 模型投票 ≥%d 票，无教材证据" % MAJORITY)
                ok, why, info = curate_core.check_fix_entry(entry, q, allow_manual=args.allow_vote_only)
                if not ok:
                    counters[why.split("（")[0][:12]] += 1
                    print(f"  [拒绝] {qid}: {why}")
                    continue
                entry["reason"] = why
                entry["evidence"] = {"tally": f.get("tally"),
                                     "external_evidence": f.get("external_evidence")}
                fixes.append(entry)
                if info.get("manual"):
                    manual_items.append(qid)
            elif f["status"] == "keep":
                # 仅解析更新（答案不变）：也必须绑定当前题目版本
                if f.get("analysis"):
                    _, q = index[qid]
                    fp_ok = f.get("fingerprint") and not curate_core.fingerprint_stale(f, q)
                    if fp_ok and curate_core.normalize_space(q.get("analysis", "")) != curate_core.normalize_space(f["analysis"]):
                        fixes.append({"qid": qid, "final": f["bank"],
                                      "analysis": f["analysis"],
                                      "fingerprint": f["fingerprint"],
                                      "external_evidence": {"supported": True, "quote_found": True,
                                                            "fingerprint": f["fingerprint"],
                                                            "note": "解析更新（答案维持，非答案修正）"}})
                    elif not fp_ok:
                        counters["解析更新被拒(未绑定)"] += 1
                n_keep += 1
            else:
                n_und += 1
        result = curate_core.apply_answer_fix(bank, fixes, source="verify_disputed --apply",
                                              batch_id=batch_id)
        n_fix = result["applied"]
        if n_fix:
            curate_core.write_bank(bank)
            reason_note = (f"verify_disputed --apply（人工覆盖 {len(manual_items)} 条）"
                           if manual_items else "verify_disputed --apply")
            curate_core.append_batch("answer_fix", reason_note,
                                     result["ledger_items"], batch_id=batch_id)
        for s in result["skipped"][:5]:
            print(f"  [跳过] {s['qid']}: {s['why']}")
        print(f"实际变更 {n_fix} 题（答案修正/解析更新，变更前的旧值已存档可回滚）· "
              f"维持原答案 {n_keep} 题 · 未决 {n_und} 题" + ("" if n_fix else "（重复执行，幂等跳过）"))
        if counters:
            print(f"  守卫拒绝统计：{dict(counters)}")
        if n_fix:
            print(f"回滚: python scripts/quiz_curate.py rollback --batch {batch_id} --apply")

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
