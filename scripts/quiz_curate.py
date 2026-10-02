# -*- coding: utf-8 -*-
"""题库策展工具（quiz curate）：章节错分 / 低质题 / 答案校验汇总 / 按章补题 / 执行删除

四个子命令对应四类需求（AI 建议 + 人工确认 + 工具执行，绝不自动删除）：

  1. 章节错分检测
     python scripts/quiz_curate.py chapter [--llm] [--chapters 3,5] [--limit 0] [--workers 4]
     规则初筛（关键词得分）找出疑似放错章节的题 → 可选 LLM 逐题复核归属
     输出: data/curate/chapter_audit.json + docs/chapter_audit_report.md
           data/curate/remove_chapter.json（建议删除清单）

  2. 低质题筛选
     python scripts/quiz_curate.py quality [--llm] [--min-score 3] [--limit 0]
     多维规则信号打分（残缺/送分/重复/占位符/无解析...）→ 可选 LLM 复核
     输出: data/curate/quality_audit.json + docs/quality_audit_report.md
           data/curate/remove_quality.json

  3. 答案错误汇总（复用既有 verify 流水线的产物）
     python scripts/quiz_curate.py answers
     汇总 data/verify_final.json 的待修清单；无产物时提示校验命令

  4. 按章补题（LLM 出题 → 人工审核 → 合入）
     python scripts/quiz_curate.py generate --chapter 12 --count 30
     输出: scripts/_drafts/questions_auto_ch12.json（可用 merge_new_questions.py 合入）

  执行删除（读上面输出的清单，默认 dry-run，加 --apply 才真删）：
     python scripts/quiz_curate.py remove --from data/curate/remove_chapter.json --apply

LLM 配置：复用 config/verify_config.json（与 verify_answers.py 同一份）。
注意：删除只移除题目，不重排 seq —— 避免破坏用户已保存的进度/错题记录（qid = "章-seq"）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from classify_questions import CHAPTERS, RULES, ANALYSIS_RULES  # noqa: E402

JSON_PATH = ROOT / "data" / "quiz_categorized.json"
JS_PATH = ROOT / "data" / "quiz_categorized.js"
COMPRESS = ROOT / "scripts" / "compress_bank.py"
CFG = ROOT / "config" / "verify_config.json"
VERIFY_FINAL = ROOT / "data" / "verify_final.json"
CURATE_DIR = ROOT / "data" / "curate"
DOCS_DIR = ROOT / "docs"
DRAFTS_DIR = ROOT / "scripts" / "_drafts"

CTX = ssl.create_default_context()

MULTI_HINTS = ["以下哪些", "有哪些", "哪些是", "哪几个", "多选"]
SINGLE_HINTS = ["以下哪种", "以下哪个", "哪一项", "哪种方法", "是什么"]
CONTEXT_HINTS = [
    "在示例中", "以下代码片段中", "在代码中", "函数中", "如果问题类型是",
    "如果问题类型无法识别", "优化后的答疑机器人",
]
FALLBACK_OPTIONS = {"以上都对", "以上都正确", "以上均是", "以上都是", "全部正确", "以上均正确", "都正确"}
PLACEHOLDERS = ["？？", "XXX", "xxx", "待补充", "TODO", "（略）"]


# ---------------- 基础工具 ----------------

def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def norm_ans(ans) -> list[str]:
    ans = re.sub(r"\s", "", str(ans or ""))
    if "," in ans:
        return [s.strip() for s in ans.split(",") if s.strip()]
    return [c for c in ans if re.match(r"[A-H]", c)]


def load_bank() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def bank_questions(bank: dict) -> list[dict]:
    out = []
    for ch, qs in bank["questions_by_chapter"].items():
        for q in qs:
            q = dict(q)
            q["chapter"] = int(ch)
            out.append(q)
    return out


def qid_of(q: dict) -> str:
    return f"{q['chapter']}-{str(q['seq']).zfill(4)}"


def brief(q: dict) -> dict:
    return {
        "qid": qid_of(q),
        "chapter": q["chapter"],
        "chapter_name": CHAPTERS.get(q["chapter"], "?"),
        "seq": str(q["seq"]).zfill(4),
        "type": q.get("type", 0),
        "answer": q.get("answer", ""),
        "stem": normalize_space(q.get("stem", ""))[:120],
    }


def write_bank(bank: dict) -> None:
    by_ch = bank["questions_by_chapter"]
    diff = {"入门": 0, "进阶": 0, "挑战": 0}
    for arr in by_ch.values():
        for q in arr:
            label = q.get("difficulty_label", "进阶")
            if label in diff:
                diff[label] += 1
    bank["total"] = sum(len(v) for v in by_ch.values())
    bank["difficulty_counts"] = diff
    JSON_PATH.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    js = (
        "const QUIZ_CHAPTERS = " + json.dumps(bank["chapters"], ensure_ascii=False) + ";\n\n"
        "const QUIZ_DATA_BY_CHAPTER = "
        + json.dumps(by_ch, ensure_ascii=False, separators=(",", ":")) + ";\n"
    )
    JS_PATH.write_text(js, encoding="utf-8")


def rebuild_min_js() -> bool:
    r = subprocess.run([sys.executable, str(COMPRESS)], capture_output=True, text=True)
    if r.returncode != 0:
        print("[警告] compress_bank.py 执行失败：", (r.stderr or r.stdout)[-400:])
        return False
    return True


# ---------------- 关键词打分（与 scan_quiz_issues.py 保持一致） ----------------

def keyword_count(text: str, keyword: str) -> int:
    if re.search(r"[A-Za-z0-9_]", keyword) and not re.search(r"[\u4e00-\u9fff]", keyword):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(keyword)}(?![A-Za-z0-9_])"
        return len(re.findall(pattern, text, flags=re.IGNORECASE))
    return text.lower().count(keyword.lower())


def build_text_blob(q: dict) -> str:
    parts = [q.get("stem", ""), q.get("analysis", "")]
    parts.extend(o.get("option_text", "") for o in q.get("options", []))
    return " ".join(parts)


def score_question(q: dict) -> tuple[dict, dict]:
    text = build_text_blob(q)
    scores = {ch: 0 for ch in CHAPTERS}
    matched: dict[int, list[str]] = {ch: [] for ch in CHAPTERS}
    for ch, rule in RULES.items():
        for kw, weight in rule["keywords"]:
            n = keyword_count(text, kw)
            if n > 0:
                scores[ch] += weight * n
                if kw not in matched[ch]:
                    matched[ch].append(kw)
    if all(v == 0 for v in scores.values()):
        analysis = q.get("analysis", "")
        for kw, ch in ANALYSIS_RULES.items():
            if kw.lower() in analysis.lower():
                scores[ch] += 1
                if kw not in matched[ch]:
                    matched[ch].append(kw)
    return scores, matched


# ---------------- LLM ----------------

def load_llm_cfg() -> dict | None:
    if not CFG.exists():
        print(f"[提示] 未找到 {CFG}，--llm 需要先复制 config/verify_config.example.json "
              f"为 verify_config.json 并填入 API Key。")
        return None
    return json.loads(CFG.read_text(encoding="utf-8"))


def chat(cfg: dict, model: str, messages: list, max_tokens=800, temperature=0, timeout=90):
    body = json.dumps({
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
    }).encode("utf-8")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    for attempt in range(4):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": "Bearer " + cfg["api_key"],
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                data = json.loads(r.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** attempt + random.random())
                continue
            print(f"[LLM] HTTP {e.code}: {(e.read()[:200] if hasattr(e, 'read') else '')}")
            return None
        except Exception as e:
            time.sleep(2 ** attempt + random.random())
            last = e
    print(f"[LLM] 调用失败: {last}")
    return None


def parse_json_obj(text):
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\[?\{.*?\}?\]+)\s*```", text, re.S)
    if m:
        text = m.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S) or re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def question_block(q: dict) -> str:
    opts = "\n".join(f"{o['option_label']}. {o['option_text']}" for o in q.get("options", []))
    kind = "多选" if q.get("type") == 1 else "单选"
    analysis = normalize_space(q.get("analysis", ""))
    return (f"【题目】{normalize_space(q.get('stem', ''))}\n【选项】\n{opts}\n"
            f"【题型】{kind}\n【参考答案】{q.get('answer', '')}\n"
            f"【解析】{analysis if analysis and analysis != '暂无' else '（无）'}")


# ---------------- 需求1：章节错分 ----------------

CHAPTER_PROMPT = """你是题库编目专家。下面这道题目前被归在章节「{ch_name}」。
请判断它真正属于哪个章节，或是否根本不值得保留。

【全部章节】
{chapters}

【判定规则】
- 题目核心考点明确属于上述某一章 → action=move，chapter=该章编号
- 核心考点就是当前章 → action=keep，chapter={ch}
- 题干残缺/无意义/依赖缺失的上下文/纯属凑数，不属于任何章 → action=remove，chapter=0
注意：题库原有解析仅供参考，判断以题干与选项本身的考点为准。

只输出 JSON：{{"action": "keep|move|remove", "chapter": 数字, "confidence": "high|mid|low", "reason": "不超过40字"}}

【题目】
{block}"""


def rule_candidates_chapter(questions, threshold):
    """规则初筛：关键词得分 top 章节明显不是当前章。"""
    out = []
    for q in questions:
        ch = q["chapter"]
        if ch not in CHAPTERS:
            continue
        scores, matched = score_question(q)
        ranked = sorted(scores.items(), key=lambda i: (-i[1], i[0]))
        top_ch, top_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        cur = scores.get(ch, 0)
        if top_ch != ch and top_score >= threshold and (cur == 0 or top_score >= cur + 3) and top_score - second >= 2:
            out.append({
                **brief(q),
                "predicted_chapter": top_ch,
                "predicted_chapter_name": CHAPTERS[top_ch],
                "current_score": cur,
                "top_score": top_score,
                "matched_keywords": matched.get(top_ch, [])[:6],
            })
    out.sort(key=lambda x: (-(x["top_score"] - x["current_score"]), x["qid"]))
    return out


def llm_review_chapter(cfg, items, workers):
    model = cfg.get("primary_model", "qwen-plus")
    chapters_txt = "\n".join(f"{k}. {v}" for k, v in CHAPTERS.items())
    results = {}

    def one(item):
        prompt = CHAPTER_PROMPT.format(
            ch_name=CHAPTERS.get(item["chapter"], "?"), chapters=chapters_txt,
            ch=item["chapter"], block=question_block(item["_q"]))
        text = chat(cfg, model, [{"role": "system", "content": "只输出 JSON。"},
                                 {"role": "user", "content": prompt}])
        obj = parse_json_obj(text) or {}
        action = str(obj.get("action", "")).lower()
        if action not in ("keep", "move", "remove"):
            action = "keep"
        try:
            ch_no = int(obj.get("chapter", 0))
        except (TypeError, ValueError):
            ch_no = 0
        if action == "move" and ch_no not in CHAPTERS:
            action, ch_no = "keep", item["chapter"]
        return item["qid"], {
            "action": action,
            "chapter": ch_no if action == "move" else None,
            "chapter_name": CHAPTERS.get(ch_no) if action == "move" else None,
            "confidence": str(obj.get("confidence", "low")).lower(),
            "reason": str(obj.get("reason", ""))[:80],
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, it) for it in items]
        for i, fut in enumerate(as_completed(futs), 1):
            qid, res = fut.result()
            results[qid] = res
            if i % 20 == 0 or i == len(items):
                print(f"  LLM 复核进度 {i}/{len(items)}")
    return results


def cmd_chapter(args) -> int:
    bank = load_bank()
    questions = bank_questions(bank)
    if args.chapters:
        keep = {int(c) for c in args.chapters.split(",")}
        questions = [q for q in questions if q["chapter"] in keep]

    print(f"[1/3] 规则初筛（{len(questions)} 题，阈值 {args.threshold}）…")
    cands = rule_candidates_chapter(questions, args.threshold)
    for c in cands:
        c["_q"] = next(q for q in questions if qid_of(q) == c["qid"])
    print(f"  规则候选：{len(cands)} 题")

    if args.llm and cands:
        cfg = load_llm_cfg()
        if not cfg:
            return 1
        print(f"[2/3] LLM 复核（{cfg.get('primary_model')}，并发 {args.workers}）…")
        done = {}
        if args.resume and CHAPTER_OUT.exists():
            try:
                done = {r["qid"]: r.get("llm") for r in
                        json.loads(CHAPTER_OUT.read_text(encoding="utf-8"))["items"] if r.get("llm")}
                print(f"  断点续跑：已有 {len(done)} 条复核结果")
            except Exception:
                done = {}
        todo = [c for c in cands if c["qid"] not in done]
        reviews = llm_review_chapter(cfg, todo, args.workers) if todo else {}
        reviews.update(done)
        for c in cands:
            c["llm"] = reviews.get(c["qid"])
    else:
        print("[2/3] 跳过 LLM 复核（未加 --llm）")
        for c in cands:
            c["llm"] = None

    print("[3/3] 汇总输出…")
    move, remove, keep = [], [], []
    for c in cands:
        c.pop("_q", None)
        llm = c.get("llm") or {}
        action = llm.get("action")
        if action == "remove":
            remove.append(c)
        elif action == "move":
            move.append(c)
        elif action == "keep":
            keep.append(c)
        else:  # 无 LLM 复核：全部列为"待人工确认"
            move.append(c)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "llm" if args.llm else "rule-only",
        "summary": {"scanned": len(questions), "candidates": len(cands),
                    "suggest_move": len(move), "suggest_remove": len(remove), "keep": len(keep)},
        "items": cands,
    }
    CHAPTER_OUT.parent.mkdir(parents=True, exist_ok=True)
    CHAPTER_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    remove_list = {
        "source": "quiz_curate chapter",
        "generated_at": out["generated_at"],
        "items": [{"qid": c["qid"], "reason": (c.get("llm") or {}).get("reason", "疑似不属于任何章节")}
                  for c in remove],
    }
    REMOVE_CH.write_text(json.dumps(remove_list, ensure_ascii=False, indent=2), encoding="utf-8")

    write_chapter_md(out, move, remove, keep)
    print(f"\n完成：候选 {len(cands)} = 建议移动 {len(move)} + 建议删除 {len(remove)} + 保留 {len(keep)}")
    print(f"  报告: {CHAPTER_OUT.relative_to(ROOT)} / docs/chapter_audit_report.md")
    print(f"  删除清单: {REMOVE_CH.relative_to(ROOT)}（人工确认后执行 remove 子命令）")
    return 0


def write_chapter_md(out, move, remove, keep):
    s = out["summary"]
    lines = [
        "# 章节错分审核报告", "",
        f"> 生成时间：{out['generated_at']} · 模式：`{out['mode']}` · "
        f"扫描 {s['scanned']} 题 · 候选 {s['candidates']} 题（AI 建议 + 人工确认，勿直接采信）", "",
        "| 类别 | 数量 | 说明 |", "|---|---:|---|",
        f"| 建议移动 | {len(move)} | 题目本身没问题，放错了章节 |",
        f"| 建议删除 | {len(remove)} | 不属于任何章节 / 残缺无意义 |",
        f"| 误报保留 | {len(keep)} | 规则初筛命中但 LLM 判定归属正确 |", "",
    ]
    if move:
        lines += ["## 建议移动（当前章 → 建议章）", "",
                  "| 题号 | 当前章 | 建议章 | 置信度 | 理由 | 题干 |", "|---|---|---|---|---|---|"]
        for c in move[:200]:
            llm = c.get("llm") or {}
            to = llm.get("chapter_name") or c.get("predicted_chapter_name", "?")
            lines.append(f"| {c['qid']} | {c['chapter_name']} | {to} | {llm.get('confidence', '-')} | "
                         f"{llm.get('reason', '-')} | {c['stem']} |")
        lines.append("")
    if remove:
        lines += ["## 建议删除", "", "| 题号 | 当前章 | 理由 | 题干 |", "|---|---|---|---|"]
        for c in remove[:200]:
            llm = c.get("llm") or {}
            lines.append(f"| {c['qid']} | {c['chapter_name']} | {llm.get('reason', '-')} | {c['stem']} |")
        lines.append("")
    if keep:
        lines += ["## 误报保留（仅列出，供抽查）", "", "| 题号 | 当前章 | LLM 理由 | 题干 |", "|---|---|---|---|"]
        for c in keep[:80]:
            llm = c.get("llm") or {}
            lines.append(f"| {c['qid']} | {c['chapter_name']} | {llm.get('reason', '-')} | {c['stem']} |")
        lines.append("")
    (DOCS_DIR / "chapter_audit_report.md").write_text("\n".join(lines), encoding="utf-8")


CHAPTER_OUT = CURATE_DIR / "chapter_audit.json"
REMOVE_CH = CURATE_DIR / "remove_chapter.json"


# ---------------- 需求2：低质题 ----------------

def quality_signals(q) -> tuple[int, list[str]]:
    """返回 (权重分, 信号列表)。分数越高越可疑。"""
    stem = normalize_space(q.get("stem", ""))
    opts = [normalize_space(o.get("option_text", "")) for o in q.get("options", [])]
    analysis = normalize_space(q.get("analysis", ""))
    score, sigs = 0, []

    if len(stem) < 15:
        score += 2; sigs.append(f"题干过短({len(stem)}字)")
    if len(opts) < 4:
        score += 2; sigs.append(f"选项不足({len(opts)}个)")
    if any(len(o) == 1 for o in opts):
        score += 1; sigs.append("存在单字选项")
    if len([o for o in opts if o]) != len(set(o for o in opts if o)):
        score += 2; sigs.append("选项文本重复")
    if any(o in FALLBACK_OPTIONS for o in opts):
        score += 1; sigs.append("含“以上都对”类兜底选项")
    if not analysis or analysis == "暂无":
        score += 1; sigs.append("无解析")
    for bad in PLACEHOLDERS:
        if bad in stem or any(bad in o for o in opts):
            score += 2; sigs.append("含占位/残缺文本"); break
    if any(h in stem for h in CONTEXT_HINTS):
        score += 1; sigs.append("疑似依赖缺失的上下文")
    # 送分题：正确选项原文出现在题干中（≥8字才判定）
    ans_set = set(norm_ans(q.get("answer", "")))
    for o, lab in zip(opts, [x.get("option_label") for x in q.get("options", [])]):
        if lab in ans_set and len(o) >= 8 and o in stem:
            score += 2; sigs.append("正确选项在题干中原文出现(送分题)"); break
    return score, sigs


QUALITY_PROMPT = """你是考试题库的质量审核员。评估下面这道 ACP 认证题目是否值得保留。

【判定为 remove（低质）的典型特征】
- 题干残缺、语义不明，或依赖题目中没有给出的上下文/代码
- 选项敷衍凑数（多个选项明显同义、荒谬、与考点无关）
- 纯送分题：不看题干也能猜出答案，无考查价值
- 考点错误、答案明显有争议且无法自洽
【判定为 keep】考点清晰、有区分度、答案自洽即可，难度本身不是问题。

只输出 JSON：{{"verdict": "keep|remove", "score": 1到10的保留价值分, "reason": "不超过40字"}}

【题目】
{block}"""


def llm_review_quality(cfg, items, workers):
    model = cfg.get("primary_model", "qwen-plus")
    results = {}

    def one(item):
        prompt = QUALITY_PROMPT.format(block=question_block(item["_q"]))
        text = chat(cfg, model, [{"role": "system", "content": "只输出 JSON。"},
                                 {"role": "user", "content": prompt}])
        obj = parse_json_obj(text) or {}
        verdict = str(obj.get("verdict", "")).lower()
        if verdict not in ("keep", "remove"):
            verdict = "keep"
        try:
            sc = max(1, min(10, int(obj.get("score", 5))))
        except (TypeError, ValueError):
            sc = 5
        return item["qid"], {"verdict": verdict, "keep_score": sc,
                             "reason": str(obj.get("reason", ""))[:80]}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, it) for it in items]
        for i, fut in enumerate(as_completed(futs), 1):
            qid, res = fut.result()
            results[qid] = res
            if i % 20 == 0 or i == len(items):
                print(f"  LLM 复核进度 {i}/{len(items)}")
    return results


def cmd_quality(args) -> int:
    bank = load_bank()
    questions = bank_questions(bank)
    if args.chapters:
        keep_ch = {int(c) for c in args.chapters.split(",")}
        questions = [q for q in questions if q["chapter"] in keep_ch]

    print(f"[1/3] 规则信号打分（{len(questions)} 题）…")
    stem_groups: dict[str, list] = {}
    for q in questions:
        stem_groups.setdefault(re.sub(r"\s", "", q.get("stem", "")), []).append(qid_of(q))

    cands = []
    for q in questions:
        score, sigs = quality_signals(q)
        dup_group = stem_groups.get(re.sub(r"\s", "", q.get("stem", "")), [])
        if len(dup_group) > 1:
            # 重复题干：保留 qid 最小的一个，其余标记
            if qid_of(q) != sorted(dup_group)[0]:
                score += 1
                sigs.append(f"题干重复(同组:{','.join(dup_group[:3])})")
        if score >= args.min_score:
            cands.append({**brief(q), "rule_score": score, "signals": sigs, "_q": q})
    cands.sort(key=lambda x: (-x["rule_score"], x["qid"]))
    print(f"  规则候选（score>={args.min_score}）：{len(cands)} 题")

    if args.llm and cands:
        cfg = load_llm_cfg()
        if not cfg:
            return 1
        print(f"[2/3] LLM 复核（{cfg.get('primary_model')}）…")
        reviews = llm_review_quality(cfg, cands, args.workers)
        for c in cands:
            c["llm"] = reviews.get(c["qid"])
    else:
        print("[2/3] 跳过 LLM 复核（未加 --llm）")
        for c in cands:
            c["llm"] = None

    print("[3/3] 汇总输出…")
    remove, keep = [], []
    for c in cands:
        c.pop("_q", None)
        v = (c.get("llm") or {}).get("verdict")
        if v == "remove":
            remove.append(c)
        else:
            keep.append(c)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "llm" if args.llm else "rule-only",
        "summary": {"scanned": len(questions), "candidates": len(cands),
                    "suggest_remove": len(remove), "keep": len(keep)},
        "items": cands,
    }
    CURATE_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    remove_list = {
        "source": "quiz_curate quality",
        "generated_at": out["generated_at"],
        "items": [{"qid": c["qid"], "reason": (c.get("llm") or {}).get("reason", "低质题")}
                  for c in remove],
    }
    REMOVE_Q.write_text(json.dumps(remove_list, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 低质题审核报告", "",
        f"> 生成时间：{out['generated_at']} · 模式：`{out['mode']}` · "
        f"扫描 {out['summary']['scanned']} 题 · 候选 {len(cands)} 题", "",
    ]
    if remove:
        lines += ["## 建议删除", "", "| 题号 | 章节 | 规则分 | LLM 理由 | 题干 |", "|---|---|---:|---|---|"]
        for c in remove[:200]:
            lines.append(f"| {c['qid']} | {c['chapter_name']} | {c['rule_score']} | "
                         f"{(c.get('llm') or {}).get('reason', '-')} | {c['stem']} |")
        lines.append("")
    lines += ["## 候选但建议保留 / 待人工确认", "",
              "| 题号 | 章节 | 规则分 | 信号 | LLM 意见 | 题干 |", "|---|---|---:|---|---|---|"]
    for c in keep[:200]:
        llm = c.get("llm") or {}
        opinion = f"{llm.get('verdict', '-')}(保留价值{llm.get('keep_score', '-')}) {llm.get('reason', '')}" if llm else "-"
        lines.append(f"| {c['qid']} | {c['chapter_name']} | {c['rule_score']} | "
                     f"{'; '.join(c['signals'])} | {opinion} | {c['stem']} |")
    (DOCS_DIR / "quality_audit_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\n完成：候选 {len(cands)} = 建议删除 {len(remove)} + 保留/待确认 {len(keep)}")
    print(f"  报告: {QUALITY_OUT.relative_to(ROOT)} / docs/quality_audit_report.md")
    print(f"  删除清单: {REMOVE_Q.relative_to(ROOT)}（人工确认后执行 remove 子命令）")
    return 0


QUALITY_OUT = CURATE_DIR / "quality_audit.json"
REMOVE_Q = CURATE_DIR / "remove_quality.json"


# ---------------- 需求3：答案校验汇总 ----------------

def cmd_answers(args) -> int:
    print("答案校验使用既有流水线（无需重复造轮子）：\n")
    print("  第 1 步  独立作答交叉验证（不给参考答案，防迎合）：")
    print("    python scripts/verify_answers.py --resume --workers 8")
    print("  第 2 步  争议题 6 模型投票终裁（>=3 票才修正）：")
    print("    python scripts/verify_disputed.py --vote --report")
    print("  第 3 步  确认 docs/verify_final_report.md 后回写题库并重压缩：")
    print("    python scripts/verify_disputed.py --apply\n")

    if not VERIFY_FINAL.exists():
        print(f"[提示] 尚未找到 {VERIFY_FINAL.name}，请先执行第 1、2 步。")
        return 0

    final = json.loads(VERIFY_FINAL.read_text(encoding="utf-8"))
    fix = [v for v in final.values() if v.get("status") == "fix"]
    undecided = [v for v in final.values() if v.get("status") == "undecided"]
    keep = [v for v in final.values() if v.get("status") == "keep"]
    print(f"verify_final.json 汇总：待修正 {len(fix)} · 存疑未决 {len(undecided)} · 维持原答案 {len(keep)}\n")

    if fix:
        print("待修正清单（verify_disputed.py --apply 会自动回写）：")
        print("| 题号 | 题库答案 | 终裁答案 | 模型票型 |")
        print("|---|---|---|---|")
        for v in fix[:60]:
            tally = " / ".join(f"{m}:{','.join(a) if a else '-'}" for m, a in list((v.get("tally") or {}).items())[:3])
            print(f"| {v.get('qid')} | {','.join(v.get('bank') or [])} | "
                  f"{','.join(v.get('final') or [])} | {tally} |")
        if len(fix) > 60:
            print(f"| …（其余 {len(fix) - 60} 条见 docs/verify_final_report.md） | | | |")
    return 0


# ---------------- 需求4：按章补题 ----------------

GEN_SYSTEM = ("你是阿里云大模型高级工程师认证（ACP）的资深出题人。"
              "出的题必须考点准确、答案唯一且自洽、解析基于阿里云官方文档知识，风格与给出的样例题一致。")


def gen_prompt(ch_name, samples, existing_stems, count):
    sample_txt = "\n\n".join(f"样例{i+1}:\n{question_block(s)}" for i, s in enumerate(samples))
    stems_txt = "\n".join(existing_stems[:100]) or "（暂无）"
    return f"""请为章节「{ch_name}」新出 {count} 道高质量选择题。

【风格样例（模仿其题干表述、选项长度、解析风格）】
{sample_txt}

【该章已有题目（新题题干不得与这些重复或近似改写）】
{stems_txt}

【硬性要求】
1. 只输出 JSON 数组，不要任何其他文字
2. 每个元素字段：{{"type": 0或1, "stem": "题干", "options": [{{"option_label": "A", "option_text": "..."}}, ...], "answer": "B"或"A,C", "analysis": "80字以内的解析，必须解释为什么正确、其它选项为什么错", "difficulty": "入门|进阶|挑战"}}
3. 选项 4 个（A-D），单选 type=0 答案一个字母；多选 type=1 答案 2-3 个字母（逗号分隔）
4. 单选和多选都要有，比例约 7:3；难度大致 入门:进阶:挑战 = 3:5:2
5. 考点在本章范围内，覆盖不同的知识点，不要互相重复
6. 正确选项不要固定在同一个位置，打乱分布"""


def cmd_generate(args) -> int:
    ch = args.chapter
    if ch not in CHAPTERS:
        print(f"[错误] chapter 必须是 1-12，收到 {ch}")
        return 1
    cfg = load_llm_cfg()
    if not cfg:
        return 1
    model = cfg.get("primary_model", "qwen-plus")

    bank = load_bank()
    by_ch = bank["questions_by_chapter"]
    arr = by_ch.get(str(ch), [])
    existing_stems = [normalize_space(q.get("stem", "")) for q in arr]
    seqs = sorted(int(str(q["seq"])) for q in arr if str(q["seq"]).isdigit())
    next_seq = (seqs[-1] if seqs else 0) + 1

    rng = random.Random(args.seed)
    samples = rng.sample(arr, min(args.samples, len(arr))) if arr else []
    if not samples:
        print(f"[提示] 第 {ch} 章暂无题目，无法提供风格样例，将按章节名直接出题。")

    ch_name = CHAPTERS[ch]
    print(f"目标：第 {ch} 章「{ch_name}」现有 {len(arr)} 题，生成 {args.count} 题（每批 {args.batch}）")
    draft = []
    seen_stems = set(existing_stems)
    made, batch_no = 0, 0
    while made < args.count:
        batch_no += 1
        n = min(args.batch, args.count - made)
        prompt = gen_prompt(ch_name, samples, existing_stems, n)
        text = chat(cfg, model, [{"role": "system", "content": GEN_SYSTEM},
                                 {"role": "user", "content": prompt}],
                    max_tokens=4000, temperature=0.7)
        items = parse_json_obj(text)
        if not isinstance(items, list):
            print(f"  [批次{batch_no}] 解析失败，重试…")
            continue
        ok = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            stem = normalize_space(it.get("stem", ""))
            if not stem or re.sub(r"\s", "", stem) in seen_stems:
                continue
            labels = [o.get("option_label") for o in it.get("options", [])]
            if len(labels) != 4 or len(set(labels)) != 4 or set(labels) != {"A", "B", "C", "D"}:
                continue
            ans = ",".join(norm_ans(it.get("answer", "")))
            a_list = ans.split(",") if ans else []
            qtype = 1 if len(a_list) > 1 else 0
            if not a_list:
                continue
            if qtype == 0 and len(a_list) != 1:
                continue
            diff_label = it.get("difficulty") if it.get("difficulty") in ("入门", "进阶", "挑战") else "进阶"
            q = {
                "seq": str(next_seq).zfill(4),
                "type": qtype,
                "stem": stem,
                "options": [{"option_label": o["option_label"],
                             "option_text": normalize_space(o.get("option_text", ""))}
                            for o in it["options"]],
                "answer": ans,
                "analysis": normalize_space(it.get("analysis", "")) or "暂无",
                "chapter": ch,
                "difficulty_score": {"入门": 1, "进阶": 2, "挑战": 3}[diff_label],
                "difficulty_label": diff_label,
                "difficulty_sort": {"入门": 1, "进阶": 2, "挑战": 3}[diff_label],
            }
            next_seq += 1
            draft.append(q)
            seen_stems.add(re.sub(r"\s", "", stem))
            existing_stems.append(stem)
            ok += 1
        made += ok
        print(f"  [批次{batch_no}] 接收 {len(items)} → 合格入库草稿 {ok}（累计 {made}/{args.count}）")
        if ok == 0 and batch_no >= args.max_retry:
            print("  连续失败，提前结束。")
            break

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DRAFTS_DIR / f"questions_auto_ch{ch}.json"
    out_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

    # 用 merge_new_questions 的校验器再验一遍
    sys.path.insert(0, str(ROOT / "scripts"))
    import merge_new_questions as merge_mod
    errs = []
    for q in draft:
        errs += [f"seq={q['seq']}: {e}" for e in merge_mod.validate(q)]
    if errs:
        print("[校验警告] 以下条目合入时会被拒绝，请先修订草稿：")
        for e in errs[:20]:
            print("  -", e)

    print(f"\n已生成草稿: {out_path.relative_to(ROOT)}（{len(draft)} 题）")
    print("下一步（人工审核！逐题检查答案与解析后）：")
    print(f"  python scripts/merge_new_questions.py --drafts {out_path.name}")
    return 0


# ---------------- 执行移章 ----------------

def cmd_move(args) -> int:
    src = pathlib.Path(args.from_file)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        print(f"[错误] 清单不存在: {src}")
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) else data

    bank = load_bank()
    by_ch = bank["questions_by_chapter"]
    index: dict[str, tuple[str, dict]] = {}
    for ch, qs in by_ch.items():
        for q in qs:
            index[f"{ch}-{str(q['seq']).zfill(4)}"] = (ch, q)

    plan, skipped = [], []
    for it in items:
        qid = str(it.get("qid", ""))
        to = int(it.get("to") or it.get("chapter") or 0)
        if qid not in index:
            skipped.append((qid, "题号不存在")); continue
        if to not in CHAPTERS:
            skipped.append((qid, f"目标章非法: {to}")); continue
        cur_ch, q = index[qid]
        if str(cur_ch) == str(to):
            skipped.append((qid, "已在目标章")); continue
        plan.append({"qid": qid, "from": cur_ch, "to": to,
                     "reason": str(it.get("reason", "")), "q": q})

    if not plan:
        print("[提示] 没有需要移动的题目")
        return 0
    print(f"将移动 {len(plan)} 题（跳过 {len(skipped)}）：")
    for p in plan[:40]:
        print(f"  {p['qid']}  {CHAPTERS[int(p['from'])]} -> {CHAPTERS[p['to']]}  {p['reason'][:40]}")
    if len(plan) > 40:
        print(f"  …（共 {len(plan)} 题）")
    for qid, why in skipped:
        print(f"  [跳过] {qid}: {why}")

    if not args.apply:
        print("\n[dry-run] 未做任何修改。确认无误后追加 --apply 执行移章。")
        return 0

    backup_dir = ROOT / "data" / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for p_ in (JSON_PATH, JS_PATH):
        (backup_dir / f"{p_.stem}_{stamp}{p_.suffix}").write_text(p_.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"\n已备份到 data/backup/*_{stamp}")

    moved = 0
    for p in plan:
        cur_ch, q = index[p["qid"]]
        tgt = str(p["to"])
        old_seq = str(q["seq"]).zfill(4)
        tgt_seqs = {str(x["seq"]).zfill(4) for x in by_ch.get(tgt, [])}
        if old_seq in tgt_seqs:  # 目标章 seq 冲突 → 重新分配该章最大 seq+1
            nums = [int(s) for s in tgt_seqs if s.isdigit()]
            q["seq"] = str((max(nums) if nums else 0) + 1).zfill(4)
        by_ch[cur_ch] = [x for x in by_ch[cur_ch] if x is not q]
        q["chapter"] = p["to"]
        by_ch.setdefault(tgt, []).append(q)
        moved += 1
        if q["seq"] != old_seq:
            print(f"  [重编号] {p['qid']} 因目标章 seq 冲突改为 {tgt}-{q['seq']}")

    write_bank(bank)
    ok = rebuild_min_js()
    print(f"已移动 {moved} 题，并重写 quiz_categorized.json / .js" + ("，重压缩 min.js" if ok else "（压缩失败请手动执行）"))
    print("提示：qid = 章-seq，换章后这些题在用户旧进度/错题记录中的条目会失联（不影响其它数据）。")
    print("提示：请同步更新 index.html 中 quiz_categorized.min.js?v= 的版本号。")
    return 0


# ---------------- 执行删除 ----------------

def parse_remove_list(path: pathlib.Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) else data
    out = []
    for it in items:
        if isinstance(it, str):
            out.append({"qid": it, "reason": ""})
        elif isinstance(it, dict) and it.get("qid"):
            out.append({"qid": str(it["qid"]), "reason": str(it.get("reason", ""))})
    return out


def cmd_remove(args) -> int:
    src = pathlib.Path(args.from_file)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        print(f"[错误] 清单不存在: {src}")
        return 1
    items = parse_remove_list(src)
    if not items:
        print("[错误] 清单为空")
        return 1

    bank = load_bank()
    by_ch = bank["questions_by_chapter"]
    index: dict[str, dict] = {}
    for ch, qs in by_ch.items():
        for q in qs:
            index[f"{ch}-{str(q['seq']).zfill(4)}"] = q

    missing = [it["qid"] for it in items if it["qid"] not in index]
    found = [it for it in items if it["qid"] in index]
    old_total = bank["total"]

    print(f"清单 {src.name}: {len(items)} 项，命中 {len(found)}，未找到 {len(missing)}")
    for m in missing[:10]:
        print(f"  [未找到] {m}")
    print("\n将删除以下题目：")
    for it in found[:50]:
        stem = normalize_space(index[it["qid"]].get("stem", ""))[:60]
        print(f"  {it['qid']}  {it.get('reason', '')}  {stem}")
    if len(found) > 50:
        print(f"  …（共 {len(found)} 题）")

    if not args.apply:
        print("\n[dry-run] 未做任何修改。确认无误后追加 --apply 执行删除。")
        return 0

    # 备份
    backup_dir = ROOT / "data" / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for p in (JSON_PATH, JS_PATH):
        (backup_dir / f"{p.stem}_{stamp}{p.suffix}").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"\n已备份到 data/backup/*_{stamp}")

    removed = 0
    for it in found:
        ch, seq = it["qid"].split("-", 1)
        qs = by_ch.get(ch, [])
        new_qs = [q for q in qs if str(q["seq"]).zfill(4) != seq.zfill(4)]
        if len(new_qs) != len(qs):
            by_ch[ch] = new_qs
            removed += 1

    write_bank(bank)
    ok = rebuild_min_js()
    print(f"已删除 {removed} 题：{old_total} -> {bank['total']}")
    print("已重写 quiz_categorized.json / .js" + ("，并重压缩 min.js" if ok else "（min.js 重压缩失败，请手动执行 python scripts/compress_bank.py）"))
    print("提示：请同步更新 index.html 中 quiz_categorized.min.js?v= 的版本号以强刷缓存。")
    print("提示：删除未重排 seq，用户已有进度/错题记录（按 章-seq 索引）不受影响。")
    return 0


# ---------------- CLI ----------------

def main() -> int:
    ap = argparse.ArgumentParser(description="题库策展工具", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("chapter", help="检测不属于当前章节的题")
    p.add_argument("--llm", action="store_true", help="用 LLM 逐题复核（需 verify_config.json）")
    p.add_argument("--chapters", default="", help="只审这些章，如 3,5")
    p.add_argument("--threshold", type=int, default=5, help="规则初筛的关键词分阈值")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--resume", action="store_true", help="复用已有 chapter_audit.json 中的复核结果")
    p.set_defaults(func=cmd_chapter)

    p = sub.add_parser("quality", help="筛选低质量题目")
    p.add_argument("--llm", action="store_true", help="用 LLM 逐题复核")
    p.add_argument("--chapters", default="", help="只审这些章，如 3,5")
    p.add_argument("--min-score", type=int, default=3, help="规则信号分阈值")
    p.add_argument("--workers", type=int, default=4)
    p.set_defaults(func=cmd_quality)

    sub.add_parser("answers", help="汇总答案校验待修清单（复用 verify 流水线）").set_defaults(func=cmd_answers)

    p = sub.add_parser("generate", help="LLM 按章节生成新题草稿")
    p.add_argument("--chapter", type=int, required=True)
    p.add_argument("--count", type=int, default=20, help="目标出题数")
    p.add_argument("--batch", type=int, default=8, help="每批请求数量")
    p.add_argument("--samples", type=int, default=6, help="作为风格样例的现有题数")
    p.add_argument("--max-retry", type=int, default=5)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("remove", help="按清单删除题目（默认 dry-run）")
    p.add_argument("--from", dest="from_file", required=True, help="清单 JSON 路径")
    p.add_argument("--apply", action="store_true", help="真正执行删除（会先备份）")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("move", help="按清单移动题目到其它章节（默认 dry-run）")
    p.add_argument("--from", dest="from_file", required=True, help="清单 JSON：{items:[{qid,to,reason}]}")
    p.add_argument("--apply", action="store_true", help="真正执行移章（会先备份）")
    p.set_defaults(func=cmd_move)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
