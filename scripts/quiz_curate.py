# -*- coding: utf-8 -*-
"""题库策展工具（quiz curate）：章节匹配 / 低质题 / 答案检测 / 按章补题 / 软删除 / 恢复 / 回滚

子命令一览（AI/规则生成报告 → 人工确认 → 明确操作执行，绝不自动修改正式题库）：

  python scripts/quiz_curate.py profiles [--force]
      从章节正文生成 12 章知识画像（核心知识/前置知识/边界），供 chapter 检查使用。
      输出: data/curate/chapter_profiles.json（一次生成，可复用）

  1. 章节匹配检查
     python scripts/quiz_curate.py chapter [--llm] [--chapters 3,5] [--threshold 5] [--limit 0]
     规则初筛 → LLM 结合章节画像五分类: own(本章)/cross(跨章涉及前置知识)/
     misplaced(错放)/beyond(超纲)/unsure(待确认)，保存理由与画像证据。
     输出: data/curate/chapter_audit.json + docs/chapter_audit_report.md
           data/curate/move_chapter.json（移动清单，move --from 执行）
     注意: 未见标注样本，阈值(--threshold)未经校准，报告仅供人工参考。

  2. 低质题筛选
     python scripts/quiz_curate.py quality [--llm] [--min-score 3] [--sim-threshold 0.6]
     规则信号（残缺/重复选项/送分/占位符…）+ 语义查重(bigram Jaccard)
     → LLM 按维度评审，四分类: ok(合格)/fixable(可修复)/remove(建议删除)/review(待复核)，
     fatal_logic(严重逻辑错误)单独标记，不被其它维度高分掩盖。
     输出: data/curate/quality_audit.json + docs/quality_audit_report.md
           data/curate/remove_quality.json

  3. 答案检测汇总
     python scripts/quiz_curate.py answers
     汇总 verify 流水线结果: fix(答案错误→修正方案) /
     multi_answer(多解/条件不足→建议暂停使用) /
     insufficient(证据不足→复核) / keep(正确)。
     输出: data/curate/answer_actions.json + docs/answer_actions_report.md
     修正执行: python scripts/verify_disputed.py --apply（保存旧版本，可回滚）

  4. 按章补题
     python scripts/quiz_curate.py plan [--target 100]
     统计各章合格题量（软删除/答案未确认不计入），对比目标题量 → 缺口蓝图
     data/curate/gap_plan.json（目标值默认建议，假设见报告）。
     python scripts/quiz_curate.py generate --chapter 11 [--count N]
     按蓝图生成 → 每题过格式校验+语义查重+独立答案自检，全部通过才进草稿，
     草稿仍需人工审核后用 merge_new_questions.py 合入。

  执行操作（默认 dry-run，--apply 才生效，生效前自动备份）：
     python scripts/quiz_curate.py remove --from data/curate/remove_quality.json --apply   # 软删除
     python scripts/quiz_curate.py restore --from data/curate/xxx.json --apply             # 恢复
     python scripts/quiz_curate.py move   --from data/curate/move_chapter.json --apply     # 移章
     python scripts/quiz_curate.py rollback --batch <batch_id> --apply                     # 回滚批次
     python scripts/quiz_curate.py status                                                  # 台账与统计

LLM 配置：复用 config/verify_config.json。
注意：qid = 章-seq，删除不重排 seq；软删除题不会出现在运行时 .js 中。
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
import threading
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import curate_core as cc  # noqa: E402
from classify_questions import CHAPTERS, RULES, ANALYSIS_RULES  # noqa: E402

CFG = ROOT / "config" / "verify_config.json"
VERIFY_FINAL = ROOT / "data" / "verify_final.json"
CURATE_DIR = cc.CURATE_DIR
DOCS_DIR = ROOT / "docs"
DRAFTS_DIR = ROOT / "scripts" / "_drafts"

CHAPTER_OUT = CURATE_DIR / "chapter_audit.json"
REMOVE_CH = CURATE_DIR / "remove_chapter.json"
MOVE_CH = CURATE_DIR / "move_chapter.json"
QUALITY_OUT = CURATE_DIR / "quality_audit.json"
REMOVE_Q = CURATE_DIR / "remove_quality.json"
ANSWER_OUT = CURATE_DIR / "answer_actions.json"
GAP_PLAN = CURATE_DIR / "gap_plan.json"
PROFILES_OUT = CURATE_DIR / "chapter_profiles.json"

MULTI_HINTS = ["以下哪些", "有哪些", "哪些是", "哪几个", "多选"]
CONTEXT_HINTS = [
    "在示例中", "以下代码片段中", "在代码中", "函数中", "如果问题类型是",
    "如果问题类型无法识别", "优化后的答疑机器人",
]
FALLBACK_OPTIONS = {"以上都对", "以上都正确", "以上均是", "以上都是", "全部正确", "以上均正确", "都正确"}
PLACEHOLDERS = ["？？", "XXX", "xxx", "待补充", "TODO", "（略）"]


# ---------------- 基础工具 ----------------

def norm_ans(ans) -> list[str]:
    ans = re.sub(r"\s", "", str(ans or ""))
    if "," in ans:
        return [s.strip() for s in ans.split(",") if s.strip()]
    return [c for c in ans if re.match(r"[A-H]", c)]


def qid_of(q: dict) -> str:
    return cc.qid_of(q["chapter"], q["seq"])


def brief(q: dict) -> dict:
    return {
        "qid": qid_of(q),
        "chapter": q["chapter"],
        "chapter_name": CHAPTERS.get(q["chapter"], "?"),
        "seq": str(q["seq"]).zfill(4),
        "type": q.get("type", 0),
        "answer": q.get("answer", ""),
        "stem": cc.normalize_space(q.get("stem", ""))[:120],
    }


def load_llm_cfg() -> dict | None:
    if not CFG.exists():
        print(f"[提示] 未找到 {CFG}，--llm 需要先复制 config/verify_config.example.json "
              f"为 verify_config.json 并填入 API Key。")
        return None
    return json.loads(CFG.read_text(encoding="utf-8"))


CTX = ssl.create_default_context()


class ModelAccessError(RuntimeError):
    """Non-retryable provider account/authentication failure."""


MODEL_HALTED = threading.Event()


def chat(cfg: dict, model: str, messages: list, max_tokens=800, temperature=0, timeout=90):
    if MODEL_HALTED.is_set():
        raise ModelAccessError("模型账户不可用，已停止后续网络请求")
    body = json.dumps({
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
    }).encode("utf-8")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    last = None
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
            raw_error = e.read()
            try:
                error_type = json.loads(raw_error).get("error", {}).get("type", "")
            except (ValueError, AttributeError):
                error_type = ""
            if e.code in (401, 403) or str(error_type).lower() in ("arrearage", "authenticationerror", "invalid_api_key"):
                MODEL_HALTED.set()
                raise ModelAccessError(f"模型接口不可用：HTTP {e.code}，{error_type or '认证/访问失败'}；未应用未经校验的题目")
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** attempt + random.random())
                continue
            print(f"[LLM] HTTP {e.code}: {raw_error[:200]}")
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
    analysis = cc.normalize_space(q.get("analysis", ""))
    return (f"【题目】{cc.normalize_space(q.get('stem', ''))}\n【选项】\n{opts}\n"
            f"【题型】{kind}\n【参考答案】{q.get('answer', '')}\n"
            f"【解析】{analysis if analysis and analysis != '暂无' else '（无）'}")


def question_block_no_answer(q: dict) -> str:
    opts = "\n".join(f"{o['option_label']}. {o['option_text']}" for o in q.get("options", []))
    kind = "多选" if q.get("type") == 1 else "单选"
    return f"【题目】{cc.normalize_space(q.get('stem', ''))}\n【选项】\n{opts}\n【题型】{kind}"


# ---------------- 关键词打分（规则初筛） ----------------

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


# ---------------- LLM 并发执行 ----------------

def run_llm_workers(cfg, model, tasks, workers, desc="LLM 复核"):
    """tasks: [(key, messages)] → {key: 解析后的 JSON 或 None}"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {}

    def one(item):
        key, messages, max_tokens = item
        text = chat(cfg, model, messages, max_tokens=max_tokens)
        return key, parse_json_obj(text)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, t) for t in tasks]
        for i, fut in enumerate(as_completed(futs), 1):
            key, obj = fut.result()
            results[key] = obj
            if i % 20 == 0 or i == len(tasks):
                print(f"  {desc}进度 {i}/{len(tasks)}")
    return results


# ---------------- 章节知识画像 ----------------

PROFILE_PROMPT = """你是课程编目专家。下面是认证教材某章的正文节选，请提炼本章知识画像。

【章节】第 {n} 章 「{name}」
【正文节选】
{text}

只输出 JSON（全部用中文，术语可带英文）：
{{
  "core_concepts": ["本章核心知识点，8-15 个，每个不超过 15 字"],
  "prerequisite_concepts": ["理解本章会用到的前置知识，来自更基础的章节，5-10 个"],
  "boundaries": ["明确不属于本章的内容（常见易混的其它章主题），3-6 个"],
  "learning_goals": ["由正文归纳的本章学习目标，3-6 条，每条不超过 30 字"]
}}"""


def cmd_profiles(args) -> int:
    sections = cc.extract_chapter_sections()
    if not sections:
        print("[错误] 未能从 docs/ACP高频知识点总结.md 提取章节正文")
        return 1
    if PROFILES_OUT.exists() and not args.force:
        old = json.loads(PROFILES_OUT.read_text(encoding="utf-8"))
        if len(old.get("profiles", {})) >= len(sections):
            print(f"[跳过] 画像已存在（{PROFILES_OUT.name}），--force 可重新生成")
            return 0
    cfg = load_llm_cfg()
    if not cfg:
        return 1
    model = cfg.get("primary_model", "qwen-plus")
    tasks = []
    for n, sec in sorted(sections.items()):
        prompt = PROFILE_PROMPT.format(n=n, name=sec["title"], text=sec["text"])
        tasks.append((str(n), [
            {"role": "system", "content": "只输出 JSON。"},
            {"role": "user", "content": prompt},
        ], 1500))
    print(f"生成 12 章知识画像（模型 {model}，依据 docs/ACP高频知识点总结.md 正文）…")
    results = run_llm_workers(cfg, model, tasks, args.workers, desc="画像生成")
    profiles = {}
    for n, sec in sections.items():
        p = results.get(str(n)) or {}
        profiles[n] = {
            "title": sec["title"],
            "core_concepts": [str(x) for x in p.get("core_concepts", [])][:20],
            "prerequisite_concepts": [str(x) for x in p.get("prerequisite_concepts", [])][:12],
            "boundaries": [str(x) for x in p.get("boundaries", [])][:8],
            "learning_goals": [str(x) for x in p.get("learning_goals", [])][:8],
        }
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "docs/ACP高频知识点总结.md（章节正文，max 7000 字/章）",
        "note": "原文档无结构化学习目标块，learning_goals 由模型从正文归纳，"
                "仅供章节归属判断参考，不得当作教材原文引用。",
        "profiles": profiles,
    }
    CURATE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成 → {PROFILES_OUT.relative_to(ROOT)}")
    return 0


def load_profiles() -> dict | None:
    if not PROFILES_OUT.exists():
        return None
    return json.loads(PROFILES_OUT.read_text(encoding="utf-8"))


# ---------------- 需求1：章节匹配检查 ----------------

CHAPTER_PROMPT = """你是题库编目专家。判断下面这道题的章节归属。

【当前章】第 {ch} 章 「{ch_name}」知识画像：
核心知识：{core}
允许涉及的前置知识：{prereq}
本章边界（不属于本章）：{bounds}

【其它相关章节画像摘要】
{others}

【本章原文节选（用于证据摘录）】
{source_text}

【判定规则】
- own：题目真正考查的知识点属于当前章核心知识（即使涉及前置知识也算本章题）。
- cross：核心考点属于当前章，但大量篇幅考查前置知识（保留在本章，不算错放）。
- misplaced：核心考点明确属于上述某一其它章 → 给出该章编号。
- beyond：考点超出全部章节范围（教材不涉及）→ 建议删除。
- unsure：证据不足无法判断。

只输出 JSON：
{{"category": "own|cross|misplaced|beyond|unsure",
  "exam_knowledge": "题目真正考查的知识点，不超过20字",
  "chapter": misplaced 时的目标章编号，否则为 0,
  "evidence": "从【本章原文节选】中逐字摘录的一段原文（不超过50字，禁止改写或概括；"
              "若节选中找不到相关原文，写『无』）",
  "reason": "不超过40字"}}

【题目】
{block}"""


def classify_llm_chapter(cfg, items, workers, profiles, sections=None):
    model = cfg.get("primary_model", "qwen-plus")
    prof = profiles["profiles"]
    sections = sections or {}

    def others_txt(cur):
        lines = []
        for n in sorted(prof, key=int):
            if int(n) == cur:
                continue
            p = prof[n]
            core = "、".join(p.get("core_concepts", [])[:6])
            lines.append(f"{n}. {p['title']}：{core}")
        return "\n".join(lines)

    tasks = []
    for it in items:
        ch = it["chapter"]
        p = prof.get(str(ch), {})
        prompt = CHAPTER_PROMPT.format(
            ch=ch, ch_name=p.get("title", CHAPTERS.get(ch, "?")),
            core="、".join(p.get("core_concepts", [])) or "（画像缺失）",
            prereq="、".join(p.get("prerequisite_concepts", [])) or "（画像缺失）",
            bounds="；".join(p.get("boundaries", [])) or "（画像缺失）",
            others=others_txt(ch),
            source_text=(sections.get(ch, {}).get("text", "") or "（原文缺失）")[:3000],
            block=question_block(it["_q"]))
        tasks.append((it["qid"], [
            {"role": "system", "content": "只输出 JSON。"},
            {"role": "user", "content": prompt},
        ], 800))
    raw = run_llm_workers(cfg, model, tasks, workers, desc="章节分类")
    out = {}
    for qid, obj in raw.items():
        obj = obj or {}
        cat = str(obj.get("category", "")).lower()
        if cat not in ("own", "cross", "misplaced", "beyond", "unsure"):
            cat = "unsure"
        try:
            ch_no = int(obj.get("chapter", 0))
        except (TypeError, ValueError):
            ch_no = 0
        if cat == "misplaced" and ch_no not in CHAPTERS:
            cat, ch_no = "unsure", 0
        out[qid] = {
            "category": cat,
            "exam_knowledge": str(obj.get("exam_knowledge", ""))[:40],
            "chapter": ch_no if cat == "misplaced" else 0,
            "chapter_name": CHAPTERS.get(ch_no) if cat == "misplaced" else None,
            "evidence": str(obj.get("evidence", ""))[:240],
            "reason": str(obj.get("reason", ""))[:100],
        }
    return out


def cmd_chapter(args) -> int:
    bank = cc.load_bank()
    questions = cc.bank_questions(bank)
    if args.chapters:
        keep = {int(c) for c in args.chapters.split(",")}
        questions = [q for q in questions if q["chapter"] in keep]
    if args.limit:
        questions = questions[:args.limit]

    profiles = load_profiles()
    if args.full:
        if not args.llm:
            print("[错误] --full 全量语义审核必须配合 --llm（逐题调用大模型）")
            return 1
        cfg = load_llm_cfg()
        if not cfg:
            return 1
        est = len(questions)
        print(f"[全量模式] 将对 {est} 题逐题做语义审核（预计 ≈{est} 次 LLM 调用，并发 {args.workers}）")
        if est > 200 and not args.yes:
            print("[确认] 调用量较大，请加 --yes 显式确认后运行。")
            return 1
        cands = [{**brief(q), "_q": q} for q in questions]
        q_by_id = {qid_of(q): q for q in questions}
        print(f"[1/3] 跳过规则初筛（全量审核 {len(cands)} 题）")
    else:
        print(f"[1/3] 规则初筛（{len(questions)} 题，阈值 {args.threshold}，阈值未经标注样本校准）…")
        cands = rule_candidates_chapter(questions, args.threshold)
        q_by_id = {qid_of(q): q for q in questions}
        for c in cands:
            c["_q"] = q_by_id[c["qid"]]
        print(f"  规则候选：{len(cands)} 题")

    if profiles is None and args.llm:
        print("[提示] 未找到章节画像（data/curate/chapter_profiles.json）。")
        print("  建议先执行: python scripts/quiz_curate.py profiles")
        print("  本次将以仅章节名的方式复核，判断依据较弱（报告中已标注）。")

    if args.llm and cands:
        if not args.full:
            cfg = load_llm_cfg()
            if not cfg:
                return 1
        print(f"[2/3] LLM 五分类{'（全量）' if args.full else ' 复核'}（{cfg.get('primary_model')}，并发 {args.workers}）…")
        done = {}
        if args.resume and CHAPTER_OUT.exists():
            try:
                old = json.loads(CHAPTER_OUT.read_text(encoding="utf-8"))
                for r in old["items"]:
                    if r.get("llm") and r.get("_profile_stamp") == (profiles or {}).get("generated_at", ""):
                        done[r["qid"]] = r["llm"]
                if done:
                    print(f"  断点续跑：复用 {len(done)} 条已有分类")
            except Exception:
                done = {}
        todo = [c for c in cands if c["qid"] not in done]
        sections_for_llm = cc.extract_chapter_sections(max_chars=20000)
        reviews = classify_llm_chapter(cfg, todo, args.workers, profiles, sections_for_llm) if todo else {}
        reviews.update(done)
        for c in cands:
            c["llm"] = reviews.get(c["qid"])
            c["_profile_stamp"] = (profiles or {}).get("generated_at", "")
    else:
        print("[2/3] 跳过 LLM 复核（未加 --llm）")
        for c in cands:
            c["llm"] = None

    print("[3/3] 证据回溯校验（逐段定位引用，区分『引用存在』与『支持结论』）…")
    sections = cc.extract_chapter_sections(max_chars=20000)
    n_verified = 0
    for c in cands:
        llm = c.get("llm") or {}
        ev = (llm.get("evidence", "") or "").strip()
        sec = sections.get(c["chapter"], {}).get("text", "")
        if not sec:
            check = {"quote_found": None, "mode": "no_source"}
        elif ev in ("无", "无。", "没有", "无相关原文", ""):
            check = {"quote_found": None, "mode": "none"}  # 模型声明无原文引用
        else:
            loc = cc.locate_quote(ev, sec)
            check = {"quote_found": loc["quote_found"],
                     "mode": "exact" if loc["quote_found"] else "missing",
                     "segments": loc["segments"][:4],
                     "unmatched": loc["unmatched"][:3]}
            # 注意：quote_found 只说明"引用存在"，不等于"证据支持分类结论"——
            # 分类结论本身仍属 AI 建议，需人工结合选项与限定条件确认。
        c["evidence_check"] = check
        if check.get("quote_found"):
            n_verified += 1

    print("[4/4] 汇总输出…")
    cats = {"own": [], "cross": [], "misplaced": [], "beyond": [], "unsure": []}
    for c in cands:
        c.pop("_q", None)
        llm = c.get("llm") or {}
        cat = llm.get("category") or ("unsure" if (args.llm or args.full) else "misplaced")
        if cat not in cats:
            cat = "unsure"
        cats[cat].append(c)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": ("llm-full+profiles" if args.full else
                 "llm+profiles" if (args.llm and profiles) else
                 "llm" if args.llm else "rule-only"),
        "threshold_calibrated": False,
        "threshold_note": "关键词初筛阈值未经人工标注样本校准，候选集仅用于缩小复核范围；"
                          "full 模式跳过初筛逐题语义审核。",
        "evidence_note": "evidence_check.verified=true 表示引用能在章节原文中定位"
                         "（exact 精确 / overlap 近似）；false 表示不可追溯，需人工核实。",
        "summary": {"scanned": len(questions), "candidates": len(cands),
                    "evidence_verified": n_verified,
                    **{f"cat_{k}": len(v) for k, v in cats.items()}},
        "items": cands,
    }
    CURATE_DIR.mkdir(parents=True, exist_ok=True)
    CHAPTER_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    move_list = {
        "source": "quiz_curate chapter（错放题移动清单，人工确认后 move --from 执行）",
        "generated_at": out["generated_at"],
        "items": [{"qid": c["qid"], "to": c["llm"]["chapter"],
                   "reason": f"{c['llm'].get('exam_knowledge', '')} {c['llm'].get('reason', '')}".strip(),
                   "evidence": c["llm"].get("evidence", "")}
                  for c in cats["misplaced"] if c.get("llm")],
    }
    MOVE_CH.write_text(json.dumps(move_list, ensure_ascii=False, indent=2), encoding="utf-8")
    remove_list = {
        "source": "quiz_curate chapter（超纲题软删除清单，人工确认后 remove --from 执行）",
        "generated_at": out["generated_at"],
        "items": [{"qid": c["qid"], "reason": f"超纲: {c['llm'].get('reason', '')}"}
                  for c in cats["beyond"] if c.get("llm")],
    }
    REMOVE_CH.write_text(json.dumps(remove_list, ensure_ascii=False, indent=2), encoding="utf-8")

    write_chapter_md(out, cats)
    print(f"\n完成：候选 {len(cands)}")
    for k, v in cats.items():
        print(f"  {k}: {len(v)}")
    print(f"  报告: {CHAPTER_OUT.relative_to(ROOT)} / docs/chapter_audit_report.md")
    print(f"  移动清单: {MOVE_CH.relative_to(ROOT)} · 超纲删除清单: {REMOVE_CH.relative_to(ROOT)}")
    print("  （均为建议清单，人工确认后用 move/remove 子命令执行）")
    return 0


def write_chapter_md(out, cats):
    s = out["summary"]
    lines = [
        "# 章节匹配审核报告", "",
        f"> 生成时间：{out['generated_at']} · 模式：`{out['mode']}` · "
        f"扫描 {s['scanned']} 题 · 候选 {s['candidates']} 题（AI 建议 + 人工确认，勿直接采信）", "",
        "> ⚠️ 关键词初筛阈值未经标注样本校准；跨章题涉及前置知识不会被判定为错放。", "",
        f"> 证据可追溯：{s.get('evidence_verified', 0)}/{s.get('candidates', 0)} 条引用能逐段定位到章节原文"
        "（✓=引用存在；✗=含未命中段落需人工核实；『引用存在』≠『支持结论』，结论仍需人工确认）。", "",
        "| 类别 | 数量 | 含义 | 处置 |", "|---|---:|---|---|",
        f"| own | {len(cats['own'])} | 本章题 | 保留 |",
        f"| cross | {len(cats['cross'])} | 考点在本章、涉及前置知识 | 保留 |",
        f"| misplaced | {len(cats['misplaced'])} | 错放题 | 建议移动章节 |",
        f"| beyond | {len(cats['beyond'])} | 超纲题 | 建议软删除 |",
        f"| unsure | {len(cats['unsure'])} | 待确认 | 人工复核 |", "",
    ]
    for title, key, cols in [
        ("错放题（建议移动）", "misplaced",
         "| 题号 | 当前章 | 建议章 | 考查知识点 | 证据 | 证据可追溯 | 理由 | 题干 |\n|---|---|---|---|---|---|---|---|"),
        ("超纲题（建议软删除）", "beyond",
         "| 题号 | 当前章 | 理由 | 证据 | 证据可追溯 | 题干 |\n|---|---|---|---|---|---|"),
        ("待确认", "unsure",
         "| 题号 | 当前章 | 理由 | 题干 |\n|---|---|---|---|"),
        ("跨章涉及前置知识（保留）", "cross",
         "| 题号 | 当前章 | 考查知识点 | 理由 | 题干 |\n|---|---|---|---|---|"),
    ]:
        arr = cats[key]
        if not arr:
            continue
        lines += [f"## {title}", "", cols, ""]
        for c in arr[:200]:
            llm = c.get("llm") or {}
            ec = c.get("evidence_check") or {}
            found = ec.get("quote_found", ec.get("verified"))
            ev_ok = ("✓" if found else
                     "✗ 不可追溯" if found is False else
                     "无引用" if ec.get("mode") == "none" else "-")
            if key == "misplaced":
                lines.append(f"| {c['qid']} | {c['chapter_name']} | {llm.get('chapter_name', '-')} | "
                             f"{llm.get('exam_knowledge', '-')} | {llm.get('evidence', '-')} | {ev_ok} | "
                             f"{llm.get('reason', '-')} | {c['stem']} |")
            elif key == "beyond":
                lines.append(f"| {c['qid']} | {c['chapter_name']} | {llm.get('reason', '-')} | "
                             f"{llm.get('evidence', '-')} | {ev_ok} | {c['stem']} |")
            elif key == "unsure":
                lines.append(f"| {c['qid']} | {c['chapter_name']} | {llm.get('reason', '-')} | {c['stem']} |")
            else:
                lines.append(f"| {c['qid']} | {c['chapter_name']} | {llm.get('exam_knowledge', '-')} | "
                             f"{llm.get('reason', '-')} | {c['stem']} |")
        lines.append("")
    (DOCS_DIR / "chapter_audit_report.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------- 需求2：低质题 ----------------

def quality_signals(q) -> tuple[int, list[str]]:
    """返回 (权重分, 信号列表)。分数越高越可疑。"""
    stem = cc.normalize_space(q.get("stem", ""))
    opts = [cc.normalize_space(o.get("option_text", "")) for o in q.get("options", [])]
    analysis = cc.normalize_space(q.get("analysis", ""))
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
    ans_set = set(norm_ans(q.get("answer", "")))
    for o, lab in zip(opts, [x.get("option_label") for x in q.get("options", [])]):
        if lab in ans_set and len(o) >= 8 and o in stem:
            score += 2; sigs.append("正确选项在题干中原文出现(送分题)"); break
    return score, sigs


QUALITY_PROMPT = """你是考试题库的质量审核员。按以下维度逐项评估这道 ACP 认证题目：

1. goal_match：是否对应明确的知识点/学习目标
2. logic_sound：题目条件是否充分、逻辑是否成立
3. clarity：表达是否清晰、有无歧义
4. distractors：干扰项是否合理、有无选项重复或同义
5. no_leak：有无答案泄露或明显猜题线索
6. difficulty：难度是否适合该章节的认证备考

注意：
- 题目简单不等于低质量：只要考点清晰、有区分度，即使容易也是合格题。
- fatal_logic：存在严重逻辑错误（条件不足无法作答、无正确选项、答案与题干矛盾等）时置 true。
  fatal_logic=true 时题目不允许因其它维度表现良好而判为合格。

只输出 JSON：
{{"dims": {{"goal_match": true/false, "logic_sound": true/false, "clarity": true/false,
          "distractors": true/false, "no_leak": true/false, "difficulty": true/false}},
  "fatal_logic": true/false,
  "defects": [{{"dim": "维度名", "evidence": "题目原文中的具体依据，不超过50字"}}],
  "fix_suggestion": "若有缺陷给出修复建议，否则空串",
  "verdict": "ok|fixable|remove|review",
  "reason": "不超过40字"}}

verdict 判定：fatal_logic 或 3 项以上缺陷 → remove；1-2 项可修复缺陷 → fixable；
无法确定 → review；无缺陷 → ok。

【题目】
{block}"""


def classify_llm_quality(cfg, items, workers):
    model = cfg.get("primary_model", "qwen-plus")
    tasks = []
    for it in items:
        prompt = QUALITY_PROMPT.format(block=question_block(it["_q"]))
        tasks.append((it["qid"], [
            {"role": "system", "content": "只输出 JSON。"},
            {"role": "user", "content": prompt},
        ], 900))
    raw = run_llm_workers(cfg, model, tasks, workers, desc="质量评审")
    out = {}
    for qid, obj in raw.items():
        obj = obj or {}
        dims = obj.get("dims") or {}
        if not isinstance(dims, dict):
            dims = {}
        defects = obj.get("defects") or []
        if not isinstance(defects, list):
            defects = []
        defects = [{"dim": str(d.get("dim", ""))[:20],
                    "evidence": str(d.get("evidence", ""))[:100]}
                   for d in defects if isinstance(d, dict)]
        verdict = str(obj.get("verdict", "")).lower()
        if verdict not in ("ok", "fixable", "remove", "review"):
            verdict = "review"
        fatal = bool(obj.get("fatal_logic"))
        if fatal and verdict in ("ok", "fixable"):
            verdict = "remove"  # 严重逻辑错误不被其它维度掩盖
        out[qid] = {
            "dims": dims,
            "fatal_logic": fatal,
            "defects": defects,
            "fix_suggestion": str(obj.get("fix_suggestion", ""))[:150],
            "verdict": verdict,
            "reason": str(obj.get("reason", ""))[:100],
        }
    return out


def cmd_quality(args) -> int:
    bank = cc.load_bank()
    questions = cc.bank_questions(bank)
    if args.chapters:
        keep_ch = {int(c) for c in args.chapters.split(",")}
        questions = [q for q in questions if q["chapter"] in keep_ch]

    print(f"[1/4] 规则信号打分（{len(questions)} 题）…")
    cands = []
    for q in questions:
        score, sigs = quality_signals(q)
        if score >= args.min_score:
            cands.append({**brief(q), "rule_score": score, "signals": sigs, "_q": q})
    print(f"  规则候选（score>={args.min_score}）：{len(cands)} 题")

    print(f"[2/4] 文本相似度初筛（bigram Jaccard ≥ {args.sim_threshold}，阈值未经标注样本校准）…")
    dupgs = cc.dup_groups(questions, args.sim_threshold)
    dup_map = {}
    for g in dupgs:
        keeper = g[0]  # 组内 qid 最小者视为保留版本
        for qid in g[1:]:
            dup_map[qid] = {"group": g, "kept": keeper}
    print(f"  文本相似组（初筛，语义是否重复需 LLM 确认）：{len(dupgs)} 组，涉及 {len(dup_map)} 题")
    for c in cands:
        if c["qid"] in dup_map:
            d = dup_map[c["qid"]]
            c["signals"].append(f"文本近似(与{d['kept']}同组:{','.join(d['group'][:4])})")
            c["rule_score"] += 1
    extra_dups = [qid for qid in dup_map if qid not in {c['qid'] for c in cands}]
    for qid in extra_dups:
        q = next((x for x in questions if qid_of(x) == qid), None)
        if q:
            d = dup_map[qid]
            cands.append({**brief(q), "rule_score": 1,
                          "signals": [f"文本近似(与{d['kept']}同组:{','.join(d['group'][:4])})"],
                          "_q": q})
    cands.sort(key=lambda x: (-x["rule_score"], x["qid"]))
    print(f"  合并后候选：{len(cands)} 题")

    if args.llm and cands:
        cfg = load_llm_cfg()
        if not cfg:
            return 1
        print(f"[3/4] LLM 按维度评审（{cfg.get('primary_model')}）…")
        done = {}
        if args.resume and QUALITY_OUT.exists():
            try:
                old = json.loads(QUALITY_OUT.read_text(encoding="utf-8"))
                done = {r["qid"]: r["llm"] for r in old["items"] if r.get("llm")}
                if done:
                    print(f"  断点续跑：复用 {len(done)} 条已有评审")
            except Exception:
                done = {}
        todo = [c for c in cands if c["qid"] not in done]
        reviews = classify_llm_quality(cfg, todo, args.workers) if todo else {}
        reviews.update(done)
        for c in cands:
            c["llm"] = reviews.get(c["qid"])
    else:
        print("[3/4] 跳过 LLM 评审（未加 --llm）")
        for c in cands:
            c["llm"] = None

    print("[4/4] 汇总输出…")
    verdicts = {"ok": [], "fixable": [], "remove": [], "review": []}
    for c in cands:
        c.pop("_q", None)
        llm = c.get("llm") or {}
        v = llm.get("verdict") or "review"  # 无 LLM 时一律待复核
        verdicts.setdefault(v, []).append(c)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "llm" if args.llm else "rule-only",
        "sim_threshold": args.sim_threshold,
        "min_score": args.min_score,
        "threshold_calibrated": False,
        "summary": {"scanned": len(questions), "candidates": len(cands),
                    "dup_groups": len(dupgs),
                    **{f"verdict_{k}": len(v) for k, v in verdicts.items()}},
        "items": cands,
    }
    CURATE_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    remove_list = {
        "source": "quiz_curate quality（低质题软删除清单，人工确认后 remove --from 执行）",
        "generated_at": out["generated_at"],
        "items": [{"qid": c["qid"],
                   "reason": "; ".join([d.get("dim", "") + ":" + d.get("evidence", "")
                                        for d in (c.get("llm") or {}).get("defects", [])][:2])
                   or (c.get("llm") or {}).get("reason", "低质题")}
                  for c in verdicts["remove"]],
    }
    REMOVE_Q.write_text(json.dumps(remove_list, ensure_ascii=False, indent=2), encoding="utf-8")

    write_quality_md(out, verdicts)
    print(f"\n完成：候选 {len(cands)}")
    for k, v in verdicts.items():
        print(f"  {k}: {len(v)}")
    print(f"  报告: {QUALITY_OUT.relative_to(ROOT)} / docs/quality_audit_report.md")
    print(f"  删除清单: {REMOVE_Q.relative_to(ROOT)}（人工确认后 remove --from 执行）")
    return 0


def write_quality_md(out, verdicts):
    lines = [
        "# 低质题审核报告", "",
        f"> 生成时间：{out['generated_at']} · 模式：`{out['mode']}` · "
        f"扫描 {out['summary']['scanned']} 题 · 候选 {out['summary']['candidates']} 题 · "
        f"文本相似组 {out['summary']['dup_groups']}（bigram 初筛，语义是否重复以 LLM 评审为准）", "",
        "> ⚠️ 阈值未经标注样本校准；简单题不是低质题，删除建议均需人工确认。", "",
        "| 分类 | 数量 | 含义 |", "|---|---:|---|",
        f"| ok 合格 | {out['summary'].get('verdict_ok', 0)} | 候选中评审合格 |",
        f"| fixable 可修复 | {out['summary'].get('verdict_fixable', 0)} | 有缺陷但可修 |",
        f"| remove 建议删除 | {out['summary'].get('verdict_remove', 0)} | 严重缺陷/纯凑数 |",
        f"| review 待复核 | {out['summary'].get('verdict_review', 0)} | 证据不足 |", "",
    ]
    def dims_txt(llm):
        dims = llm.get("dims") or {}
        bad = [k for k, v in dims.items() if v is False]
        return "、".join(bad) or "-"
    for title, key, cols in [
        ("建议删除", "remove",
         "| 题号 | 章节 | 严重逻辑错误 | 缺陷维度 | 缺陷依据 | 理由 | 题干 |\n|---|---|---|---|---|---|---|"),
        ("可修复", "fixable",
         "| 题号 | 章节 | 缺陷维度 | 缺陷依据 | 修复建议 | 题干 |\n|---|---|---|---|---|---|"),
        ("待复核", "review",
         "| 题号 | 章节 | 缺陷维度 | 理由 | 题干 |\n|---|---|---|---|---|"),
        ("候选中合格（保留）", "ok",
         "| 题号 | 章节 | 信号 | 理由 | 题干 |\n|---|---|---|---|---|"),
    ]:
        arr = verdicts[key]
        if not arr:
            continue
        lines += [f"## {title}", "", cols, ""]
        for c in arr[:200]:
            llm = c.get("llm") or {}
            defects = "; ".join(f"{d.get('dim')}:{d.get('evidence')}" for d in llm.get("defects", [])[:3]) or "-"
            if key == "remove":
                lines.append(f"| {c['qid']} | {c['chapter_name']} | "
                             f"{'⚠️是' if llm.get('fatal_logic') else '否'} | {dims_txt(llm)} | "
                             f"{defects} | {llm.get('reason', '-')} | {c['stem']} |")
            elif key == "fixable":
                lines.append(f"| {c['qid']} | {c['chapter_name']} | {dims_txt(llm)} | {defects} | "
                             f"{llm.get('fix_suggestion', '-')} | {c['stem']} |")
            elif key == "review":
                lines.append(f"| {c['qid']} | {c['chapter_name']} | {dims_txt(llm)} | "
                             f"{llm.get('reason', '-')} | {c['stem']} |")
            else:
                lines.append(f"| {c['qid']} | {c['chapter_name']} | {'; '.join(c['signals'])} | "
                             f"{llm.get('reason', '-')} | {c['stem']} |")
        lines.append("")
    (DOCS_DIR / "quality_audit_report.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------- 需求3：答案检测汇总 ----------------

def classify_undecided(v) -> str:
    """细分 undecided：multi_answer（答案分散=可能多解/条件不足）或 insufficient（证据不足）。"""
    tally = v.get("tally") or {}
    answers = Counter()
    for model, ans in tally.items():
        key = tuple(ans) if ans else ("∅",)
        answers[key] += 1
    non_empty = [(k, n) for k, n in answers.items() if k != ("∅",)]
    # 至少两个不同答案各有 ≥2 票 → 答案分散，疑似多解/条件不足
    solid = [n for k, n in non_empty if n >= 2]
    if len(solid) >= 2:
        return "multi_answer"
    if not non_empty or non_empty[0][1] < 2:
        return "insufficient"
    return "insufficient"


def cmd_answers(args) -> int:
    print("答案校验流水线（先报告，修正通过 verify_disputed.py --apply 执行）：\n")
    print("  第 1 步  独立作答交叉验证（隐藏题库答案，防迎合）：")
    print("    python scripts/verify_answers.py --resume --workers 8")
    print("  第 2 步  争议题 6 模型投票终裁：")
    print("    python scripts/verify_disputed.py --vote --report")
    print("  第 3 步  确认 docs/verify_final_report.md 后应用修正（自动保存旧版本，可回滚）：")
    print("    python scripts/verify_disputed.py --apply\n")

    if not VERIFY_FINAL.exists():
        print(f"[提示] 尚未找到 {VERIFY_FINAL.name}，请先执行第 1、2 步。")
        return 0

    final = json.loads(VERIFY_FINAL.read_text(encoding="utf-8"))
    bank = cc.load_bank()
    index = cc.build_index(bank)
    fixes, stale, multi, insufficient, keep = [], [], [], [], []
    for qid, v in final.items():
        status = v.get("status")
        item = {
            "qid": qid,
            "chapter": int(v.get("ch", 0)) if str(v.get("ch", "")).isdigit() else 0,
            "chapter_name": CHAPTERS.get(int(v["ch"]), "?") if str(v.get("ch", "")).isdigit() else "?",
            "kind": v.get("kind"),
            "bank_answer": v.get("bank"),
            "tally": v.get("tally"),
            "stem": cc.normalize_space(index[qid][1].get("stem", ""))[:120] if qid in index else "",
        }
        # 内容版本守卫：校验记录绑定的指纹与当前题目失配 → 结果失效
        if status == "fix" and qid in index and cc.fingerprint_stale(v, index[qid][1]):
            item["stale"] = True
            item["stale_note"] = "题干/选项已变化，校验结果失效，需重跑校验"
            stale.append(item)
            continue
        if status == "fix":
            item["final"] = v.get("final")
            item["analysis"] = v.get("analysis")
            item["fingerprint"] = v.get("fingerprint")  # 校验结果绑定的内容版本
            ev = v.get("external_evidence") or {}
            item["evidence"] = {"vote_tally": v.get("tally"),
                                "external_evidence": ev,
                                "evidence_state": ("external" if (ev.get("supported") and ev.get("quote_located"))
                                                   else "rejected" if ev and ev.get("supported") is False
                                                   else "vote_only"),
                                "note": "修正需教材证据核对通过（--evidence）；仅投票项会被 apply 拒绝"}
            fixes.append(item)
        elif status == "undecided":
            sub = classify_undecided(v)
            item["sub"] = sub
            item["suggestion"] = ("疑似多解/条件不足：应修复题干或选项、暂停使用，不应强行改答案"
                                  if sub == "multi_answer"
                                  else "证据不足：进入人工复核列表，不修正")
            (multi if sub == "multi_answer" else insufficient).append(item)
        else:
            keep.append(item)

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {"fix": len(fixes), "stale": len(stale), "multi_answer": len(multi),
                    "insufficient": len(insufficient), "keep": len(keep)},
        "fix": fixes,
        "stale": stale,
        "multi_answer": multi,
        "insufficient": insufficient,
    }
    CURATE_DIR.mkdir(parents=True, exist_ok=True)
    ANSWER_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 多解/条件不足 → 暂停使用清单（软删除候选）
    suspend = {
        "source": "quiz_curate answers（多解/条件不足题暂停使用清单，人工确认后 remove --from 执行）",
        "generated_at": out["generated_at"],
        "items": [{"qid": it["qid"], "reason": "多解/条件不足，暂停使用待修复题干"}
                  for it in multi],
    }
    (CURATE_DIR / "suspend_answers.json").write_text(
        json.dumps(suspend, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 答案检测处置报告", "",
        f"> 生成时间：{out['generated_at']} · 来源：data/verify_final.json（6 模型投票）", "",
        "| 分类 | 数量 | 处置 |", "|---|---:|---|",
        f"| 答案错误（可修正） | {len(fixes)} | --evidence 核对教材证据后 --apply（保存旧版本可回滚） |",
        f"| 结果失效（内容已变） | {len(stale)} | 重跑校验，禁止使用旧结论 |",
        f"| 多解/条件不足 | {len(multi)} | 修复题干或暂停使用，禁止强行改答案 |",
        f"| 证据不足 | {len(insufficient)} | 人工复核，不修正 |",
        f"| 维持原答案 | {len(keep)} | 无需处理 |", "",
    ]
    if fixes:
        lines += ["## 待修正清单", "",
                  "证据状态：external=教材证据核对通过（可 apply）；vote_only=仅模型投票（apply 拒绝）；"
                  "rejected=证据核对不通过（拒绝）。", "",
                  "| 题号 | 题库答案 | 终裁答案 | 证据状态 | 票型 | 题干 |", "|---|---|---|---|---|---|"]
        for v in fixes[:100]:
            tally = " / ".join(f"{m}:{','.join(a) if a else '-'}"
                               for m, a in list((v.get("tally") or {}).items())[:3])
            lines.append(f"| {v['qid']} | {','.join(v.get('bank_answer') or [])} | "
                         f"{','.join(v.get('final') or [])} | {v.get('evidence', {}).get('evidence_state', '-')} | "
                         f"{tally} | {v['stem']} |")
        lines.append("")
    if stale:
        lines += ["## 校验结果失效（题目内容已变化）", "",
                  "| 题号 | 题库答案 | 说明 |", "|---|---|---|"]
        for v in stale[:100]:
            lines.append(f"| {v['qid']} | {','.join(v.get('bank_answer') or [])} | {v.get('stale_note', '')} |")
        lines.append("")
    if multi:
        lines += ["## 多解 / 条件不足（建议暂停使用）", "",
                  "| 题号 | 题库答案 | 票型 | 题干 |", "|---|---|---|---|"]
        for v in multi[:100]:
            tally = " / ".join(f"{m}:{','.join(a) if a else '-'}"
                               for m, a in list((v.get("tally") or {}).items())[:3])
            lines.append(f"| {v['qid']} | {','.join(v.get('bank_answer') or [])} | {tally} | {v['stem']} |")
        lines.append("")
    if insufficient:
        lines += ["## 证据不足（人工复核）", "",
                  "| 题号 | 题库答案 | 题干 |", "|---|---|---|"]
        for v in insufficient[:100]:
            lines.append(f"| {v['qid']} | {','.join(v.get('bank_answer') or [])} | {v['stem']} |")
        lines.append("")
    (DOCS_DIR / "answer_actions_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"汇总：待修正 {len(fixes)} · 结果失效 {len(stale)} · 多解/条件不足 {len(multi)} · "
          f"证据不足 {len(insufficient)} · 维持 {len(keep)}")
    print(f"  报告: {ANSWER_OUT.relative_to(ROOT)} / docs/answer_actions_report.md")
    print(f"  暂停使用清单: data/curate/suspend_answers.json（人工确认后软删除）")
    return 0


# ---------------- 需求4：补题 ----------------

DEFAULT_TARGET = 100  # 默认建议目标题量/章：全库均值约 138，取偏低值 100，未配置目标时使用


def load_exclusion_sets():
    """汇总三类"不计入合格题量"的题号：
    - 答案未确认：verify_final 中 fix / undecided
    - 低质待修复/建议删除/待复核：quality_audit 中 verdict ∈ {fixable, remove, review}
    - 章节待处理：chapter_audit 中 category ∈ {misplaced, beyond, unsure}
    返回 {qid: 原因}
    """
    excluded: dict[str, str] = {}
    if VERIFY_FINAL.exists():
        final = json.loads(VERIFY_FINAL.read_text(encoding="utf-8"))
        for qid, v in final.items():
            if v.get("status") in ("fix", "undecided"):
                excluded[qid] = f"答案未确认({v.get('status')})"
    qa = CURATE_DIR / "quality_audit.json"
    if qa.exists():
        try:
            for it in json.loads(qa.read_text(encoding="utf-8")).get("items", []):
                v = (it.get("llm") or {}).get("verdict")
                if v in ("fixable", "remove", "review"):
                    excluded[it["qid"]] = f"低质({v})"
        except Exception:
            pass
    ca = CHAPTER_OUT
    if ca.exists():
        try:
            for it in json.loads(ca.read_text(encoding="utf-8")).get("items", []):
                c = (it.get("llm") or {}).get("category")
                if c in ("misplaced", "beyond", "unsure"):
                    excluded.setdefault(it["qid"], f"章节待处理({c})")
        except Exception:
            pass
    return excluded


def quota_for(gap: int, existing_qs: list) -> dict:
    """按现有题型/难度分布计算补题配额（无数据时回退 7:3 与 3:5:2）。"""
    n = len(existing_qs)
    if n:
        multi = sum(1 for q in existing_qs if q.get("type") == 1)
        multi_ratio = multi / n
        diff_cnt = Counter(q.get("difficulty_label", "进阶") for q in existing_qs)
        diff_ratio = {k: diff_cnt.get(k, 0) / n for k in ("入门", "进阶", "挑战")}
    else:
        multi_ratio, diff_ratio = 0.3, {"入门": 0.3, "进阶": 0.5, "挑战": 0.2}
    multi_n = round(gap * multi_ratio)
    type_quota = {"multi": multi_n, "single": gap - multi_n}
    dq = {k: round(gap * r) for k, r in diff_ratio.items()}
    dq["进阶"] += gap - sum(dq.values())  # 余数补到进阶
    return {"type_quota": type_quota, "difficulty_quota": dq,
            "note": f"按该章现有分布计算（多选占比 {multi_ratio:.0%}）；无题时回退 7:3 / 3:5:2"}


def knowledge_coverage(ch: int, qs: list) -> list:
    """画像核心考点的覆盖统计：[{concept, coverage}]，覆盖 0 的排最前。"""
    if not PROFILES_OUT.exists():
        return []
    prof = json.loads(PROFILES_OUT.read_text(encoding="utf-8"))["profiles"].get(str(ch), {})
    out = []
    for concept in prof.get("core_concepts", []):
        cov = sum(1 for q in qs if keyword_count(build_text_blob(q), concept) > 0)
        out.append({"concept": concept, "coverage": cov})
    out.sort(key=lambda x: (x["coverage"], x["concept"]))
    return out


def cmd_plan(args) -> int:
    bank = cc.load_bank()
    questions = cc.bank_questions(bank)  # 排除软删除
    excluded = load_exclusion_sets()
    eligible_qs = [q for q in questions if qid_of(q) not in excluded]

    print(f"目标题量/章：{args.target}（默认建议值，假设：全库均值约 "
          f"{sum(len(v) for v in bank['questions_by_chapter'].values()) // 12}，"
          f"取偏低值保证可达；如项目有官方要求请用 --target 覆盖）")
    print(f"合格口径：非软删除 且 答案已确认 且 非低质待修复/待复核 且 非章节待处理"
          f"（共排除 {len(excluded)} 题）\n")

    plan = {}
    for ch in range(1, 13):
        ch_qs = [q for q in questions if q["chapter"] == ch]
        arr = [q for q in eligible_qs if q["chapter"] == ch]
        n = len(arr)
        types = Counter("multi" if q.get("type") == 1 else "single" for q in arr)
        diffs = Counter(q.get("difficulty_label", "进阶") for q in arr)
        gap = max(0, args.target - n)
        blueprint = {}
        if gap:
            cov = knowledge_coverage(ch, arr)
            blueprint = {
                "count": gap,
                "quota_note": quota_for(gap, arr)["note"],
                "type_quota": quota_for(gap, arr)["type_quota"],
                "difficulty_quota": quota_for(gap, arr)["difficulty_quota"],
                "priority_knowledge": [
                    {"concept": c["concept"], "coverage": c["coverage"]}
                    for c in cov[:10] if c["coverage"] <= max(1, n // 20)
                ] or [{"concept": c["concept"], "coverage": c["coverage"]} for c in cov[:5]],
                "coverage_note": "coverage=该考点下现有合格题数，0 表示完全未覆盖，优先补。",
            }
        plan[ch] = {
            "chapter": ch,
            "chapter_name": CHAPTERS[ch],
            "active_count": len(ch_qs),
            "eligible_count": n,
            "excluded_counts": {
                "answer_unconfirmed": sum(1 for q in ch_qs if "答案未确认" in excluded.get(qid_of(q), "")),
                "quality_flagged": sum(1 for q in ch_qs if "低质" in excluded.get(qid_of(q), "")),
                "chapter_flagged": sum(1 for q in ch_qs if "章节" in excluded.get(qid_of(q), "")),
            },
            "type_counts": dict(types),
            "difficulty_counts": dict(diffs),
            "gap": gap,
            "blueprint": blueprint,
        }
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "target_per_chapter": args.target,
        "target_note": "默认建议值（假设见运行输出），非官方要求；可用 --target 调整。",
        "exclusion_note": "合格 = 非软删除 + 答案已确认 + 低质检查非待修复/待复核 + 章节检查非待处理。",
        "plan": plan,
    }
    CURATE_DIR.mkdir(parents=True, exist_ok=True)
    GAP_PLAN.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    total_gap = sum(p["gap"] for p in plan.values())
    print(f"{'章':<4}{'章名':<14}{'在用':>5}{'未确认':>7}{'低质标记':>9}{'章节标记':>9}{'合格':>6}{'缺口':>5}")
    for ch, p in plan.items():
        e = p["excluded_counts"]
        print(f"{ch:<4}{p['chapter_name']:<14}{p['active_count']:>5}{e['answer_unconfirmed']:>7}"
              f"{e['quality_flagged']:>9}{e['chapter_flagged']:>9}{p['eligible_count']:>6}{p['gap']:>5}")
    print(f"\n总缺口：{total_gap} 题 → 蓝图: {GAP_PLAN.relative_to(ROOT)}")
    print("补题：python scripts/quiz_curate.py generate --chapter <N>（从蓝图读缺口与配额）")
    return 0


GEN_SYSTEM = ("你是阿里云大模型高级工程师认证（ACP）的资深出题人。"
              "出的题必须考点准确、答案唯一且自洽、解析基于阿里云官方文档知识，风格与给出的样例题一致。")

ANSWER_CHECK_PROMPT = """请独立解答下面这道{kind}题（不要参考任何给出的答案）。

{block}

只输出 JSON：{{"answer": "字母"或"字母,字母", "confidence": "high|mid|low",
"basis": "判断依据，不超过50字"}}
若题目条件不足或存在多个合理答案，输出 {{"answer": "", "problem": "multi|insufficient", "basis": "..."}}"""


def gen_prompt(ch_name, profile, samples, existing_stems, count, blueprint):
    sample_txt = "\n\n".join(f"样例{i+1}:\n{question_block(s)}" for i, s in enumerate(samples))
    stems_txt = "\n".join(existing_stems[:100]) or "（暂无）"
    tq = blueprint.get("type_quota", {"multi": round(count * 0.3), "single": count - round(count * 0.3)})
    dq = blueprint.get("difficulty_quota", {"入门": round(count * 0.3), "进阶": round(count * 0.5),
                                            "挑战": count - round(count * 0.3) - round(count * 0.5)})
    priority = "；".join(f"{p['concept']}(现有{p['coverage']}题)" for p in blueprint.get("priority_knowledge", [])[:8])
    core = "、".join(profile.get("core_concepts", [])[:12]) if profile else ""
    return f"""请为章节「{ch_name}」新出 {count} 道高质量选择题。

【本章知识画像核心考点】{core or '（无画像，按章节名把握范围）'}

【风格样例（模仿其题干表述、选项长度、解析风格）】
{sample_txt}

【该章已有题目（新题题干不得与这些重复或近似改写）】
{stems_txt}

【硬性要求】
1. 只输出 JSON 数组，不要任何其他文字
2. 每个元素字段：{{"type": 0或1, "stem": "题干", "options": [{{"option_label": "A", "option_text": "..."}}, ...], "answer": "B"或"A,C", "analysis": "80字以内的解析，必须解释为什么正确、其它选项为什么错", "difficulty": "入门|进阶|挑战", "knowledge_point": "考查的核心知识点，不超过15字", "basis": "本题依据的章节知识要点，不超过30字"}}
3. 选项 4 个（A-D），单选 type=0 答案一个字母；多选 type=1 答案 2-3 个字母（逗号分隔）
4. 本批题型与难度按以下配额：多选 {tq.get('multi', 0)} 题 / 单选 {tq.get('single', 0)} 题；难度 入门 {dq.get('入门', 0)} / 进阶 {dq.get('进阶', 0)} / 挑战 {dq.get('挑战', 0)}
5. 考点优先覆盖：{priority or '（无指定，按画像核心考点覆盖）'}
6. 考点必须属于本章知识画像列出的核心考点，覆盖不同知识点，不要互相重复
7. 题目条件必须充分、答案唯一、无歧义；正确选项不要固定在同一个位置"""


def check_new_question(q, existing_keys, batch_keys, sim_threshold=0.6):
    """新题静态检查：格式（merge 规则）+ 标准化题干精确查重。返回错误列表。"""
    import merge_new_questions as merge_mod
    errs = list(merge_mod.validate(dict(q, chapter=q["chapter"])))
    key = cc.stem_key(q["stem"])
    if key in existing_keys or key in batch_keys:
        errs.append("题干与已有题目重复")
    return errs


def llm_semantic_dup_check(cfg, model, q, similar_items):
    """语义查重：对文本相似初筛命中的近似题（含高相似度），判定考点/关键条件/解题路径。

    高文本相似度不等于语义重复——可能只差否定词、限定条件或数字，考查内容完全不同，
    因此任何相似度档位都必须经本判定，文本相似度仅作候选筛选。
    """
    others = "\n\n".join(
        f"候选{i+1}（{it['qid']}，文本相似度 {it['sim']}）:\n{question_block(it['q'])}"
        for i, it in enumerate(similar_items[:3]))
    prompt = f"""请判断【新题】与候选题是否语义重复。逐项比较以下三点：
1. 考点是否相同；
2. 关键条件是否相同（特别注意否定词"不/最/必须/不包括"、数量、限定范围等差异——
   仅一个否定词或数字不同，考查内容就可能完全不同）；
3. 解题路径/判断依据是否相同。

判定：三点全部相同 → duplicate=true（同一道题的改写）；任一点不同 → duplicate=false。
只输出 JSON：{{"duplicate": true/false, "same_as": "重复的候选编号，无则空串",
"diff": "与最相似候选的关键差异，不超过30字", "reason": "不超过40字"}}

【新题】
{question_block_no_answer(q)}

【已有近似题】
{others}"""
    obj = parse_json_obj(chat(cfg, model, [
        {"role": "system", "content": "只输出 JSON。"},
        {"role": "user", "content": prompt},
    ])) or {}
    if obj.get("duplicate") is True:
        return True, f"语义重复({obj.get('same_as', '')}): {obj.get('reason', '')}"
    return False, f"语义查重通过: {obj.get('diff') or obj.get('reason', '')}"


def llm_chapter_check(cfg, model, q, profiles):
    """章节归属检查：新题必须归属其目标章（own / cross 均算归属）。"""
    ch = q["chapter"]
    prof = (profiles or {}).get("profiles", {}).get(str(ch), {})
    prompt = f"""判断这道新题是否真正属于第 {ch} 章「{prof.get('title', CHAPTERS.get(ch, '?'))}」。
本章核心知识：{"、".join(prof.get("core_concepts", [])) or "（画像缺失，按章节名判断）"}
允许的前置知识：{"、".join(prof.get("prerequisite_concepts", [])) or "（无）"}
只输出 JSON：{{"belongs": true/false, "reason": "不超过30字"}}（涉及前置知识但考点在本章也算 belongs=true）

【新题】
{question_block_no_answer(q)}"""
    obj = parse_json_obj(chat(cfg, model, [
        {"role": "system", "content": "只输出 JSON。"},
        {"role": "user", "content": prompt},
    ])) or {}
    if obj.get("belongs") is True:
        return True, f"章节归属通过: {obj.get('reason', '')}"
    return False, f"章节归属存疑: {obj.get('reason', '')}"


def llm_evidence_check(cfg, model, q, section_text):
    """教材证据核对：逐选项核对正误与题干限定条件，引用逐段定位。

    分开记录"引用是否存在"（quote_found）与"是否支持结论"（supported），
    两者都通过才算核对通过；任一不成立 → 进入复核（拒绝入库）。
    """
    prompt = f"""仅依据下面的章节原文，核对这道题。

【章节原文（可能节选）】
{section_text[:6000]}

【题目】
{question_block(q)}

只输出 JSON：
{{"supported": true/false,
  "quote": "支持的原文引用（逐字摘录，可多句，禁止改写；原文不足以判断则留空）",
  "per_option": [{{"label": "A", "verdict": "correct|wrong|unknown", "why": "不超过20字"}}],
  "note": "补充说明，不超过40字"}}
要求：逐项核对每个选项的正误及题干限定条件（如"最""必须""不包括"等），
而不是只给答案找一句支持文字。若原文不足以判断，supported=false。禁止编造原文。"""
    obj = parse_json_obj(chat(cfg, model, [
        {"role": "system", "content": "只输出 JSON，引用必须逐字来自给定原文。"},
        {"role": "user", "content": prompt},
    ])) or {}
    quote = str(obj.get("quote", ""))
    loc = cc.locate_quote(quote, section_text) if section_text else {"quote_found": False, "unmatched": ["原文缺失"]}
    supported = obj.get("supported") is True
    quote_found = bool(loc.get("quote_found"))
    if supported and quote_found:
        n_opt = len([o for o in (obj.get("per_option") or []) if o.get("verdict") in ("correct", "wrong")])
        return True, f"教材证据核对通过（引用逐段定位，{n_opt} 个选项有明确判定）: {quote[:50]}"
    if supported and not quote_found:
        return False, (f"教材证据含无法定位的段落（疑似编造/改写）: "
                       f"{'; '.join(loc.get('unmatched', [])[:2])}")
    return False, f"教材证据不支持或不足: {obj.get('note', '')}"


def llm_self_check(cfg, model, q, workers_hint=None):
    """独立答案自检：隐藏答案让模型作答，一致才通过。"""
    kind = "多选" if q.get("type") == 1 else "单选"
    block = question_block_no_answer(q)
    prompt = ANSWER_CHECK_PROMPT.format(kind=kind, block=block)
    obj = parse_json_obj(chat(cfg, model, [
        {"role": "system", "content": "只输出 JSON。你是独立解题者，依据阿里云官方文档知识作答。"},
        {"role": "user", "content": prompt},
    ]))
    if not obj:
        return False, "自检无响应"
    if obj.get("problem"):
        return False, f"自检判定问题: {obj.get('problem')} - {obj.get('basis', '')}"
    got = sorted(set(norm_ans(obj.get("answer", ""))))
    want = sorted(set(norm_ans(q["answer"])))
    if got != want:
        return False, f"自检答案不一致: 模型={got or '?'} 题库={want}"
    return True, f"自检一致（{obj.get('confidence', '?')}）"


# 新题全检查链的阶段定义（顺序执行，前一阶段失败即淘汰）
SIM_SOFT = 0.35   # 文本相似度 ≥ 此值 → 进入 LLM 语义判定（仅候选筛选，任何相似度都不直接判重）


def full_check_chain(cfg, model, q, pool_qs, existing_keys, batch_keys,
                     profiles, section_text):
    """新题完整检查链。返回 (passed, checks: [{stage, passed, detail}])。

    阶段：format 格式与精确查重 → sim_text 文本相似度初筛 → sem_dup 语义查重（LLM，
    高相似度也必须比较考点/关键条件/解题路径，不直接判重）
    → chapter 章节归属（LLM）→ quality 质量评审（LLM）→ solve 独立解题（LLM）
    → evidence 教材证据核对（LLM，引用存在与支持结论分开判定）。
    """
    checks = []

    def record(stage, passed, detail):
        checks.append({"stage": stage, "passed": bool(passed), "detail": str(detail)[:160]})
        return passed

    # 1. 格式 + 精确查重
    errs = check_new_question(q, existing_keys, batch_keys)
    if not record("format", not errs, "; ".join(errs) or "格式与精确查重通过"):
        return False, checks

    # 2. 文本相似度初筛（仅产生语义判定候选，不做任何直接拒绝）
    sims = cc.top_similar(q, pool_qs, k=3, min_sim=SIM_SOFT)
    record("sim_text", True,
           f"候选近似题 {len(sims)} 个，最高文本相似度 {sims[0]['sim'] if sims else 0}"
           f"（{sims[0]['qid'] if sims else '-'}）；仅作语义判定候选")

    # 3. 语义查重（考点 + 关键条件 + 解题路径，LLM；高相似也不豁免）
    if sims:
        sim_items = [{"qid": s["qid"], "sim": s["sim"],
                      "q": next(x for x in pool_qs if x.get("qid") == s["qid"])}
                     for s in sims]
        dup, why = llm_semantic_dup_check(cfg, model, q, sim_items)
        if not record("sem_dup", not dup, why):
            return False, checks
    else:
        record("sem_dup", True, "无近似题，跳过语义判定")

    # 4. 章节归属
    ok, why = llm_chapter_check(cfg, model, q, profiles)
    if not record("chapter", ok, why):
        return False, checks

    # 5. 质量评审（复用 quality 的六维度 prompt；fixable/remove/review 均不通过）
    obj = parse_json_obj(chat(cfg, model, [
        {"role": "system", "content": "只输出 JSON。"},
        {"role": "user", "content": QUALITY_PROMPT.format(block=question_block(q))},
    ], max_tokens=900)) or {}
    verdict = str(obj.get("verdict", "")).lower()
    defects = obj.get("defects") or []
    detail = (f"verdict={verdict or '无响应'}"
              + (f"; 缺陷: {'; '.join(str(d.get('dim', '')) + ':' + str(d.get('evidence', ''))[:30] for d in defects[:2])}" if defects else ""))
    if not record("quality", verdict == "ok", detail):
        return False, checks

    # 6. 独立解题（隐藏答案）
    ok, why = llm_self_check(cfg, model, q)
    if not record("solve", ok, why):
        return False, checks

    # 7. 教材证据核对（引用须能在章节原文中定位）
    if section_text:
        ok, why = llm_evidence_check(cfg, model, q, section_text)
        if not record("evidence", ok, why):
            return False, checks
    else:
        record("evidence", False, "章节原文缺失，无法核对证据")

    return all(c["passed"] for c in checks), checks


def cmd_generate(args) -> int:
    ch = args.chapter
    if ch not in CHAPTERS:
        print(f"[错误] chapter 必须是 1-12，收到 {ch}")
        return 1
    cfg = load_llm_cfg()
    if not cfg:
        return 1
    model = cfg.get("primary_model", "qwen-plus")

    bank = cc.load_bank()
    all_q = cc.bank_questions(bank, include_deleted=False)
    by_ch = bank["questions_by_chapter"]
    arr = [q for q in by_ch.get(str(ch), []) if not q.get("deleted")]
    existing_stems = [cc.normalize_space(q.get("stem", "")) for q in arr]
    existing_keys = {cc.stem_key(s) for s in existing_stems}
    seqs = sorted(int(str(q["seq"])) for q in arr if str(q["seq"]).isdigit())
    next_seq = (seqs[-1] if seqs else 0) + 1

    # 目标题量：显式 --count > 蓝图缺口
    count = args.count
    blueprint = {}
    if GAP_PLAN.exists():
        plan = json.loads(GAP_PLAN.read_text(encoding="utf-8")).get("plan", {}).get(str(ch), {})
        blueprint = plan.get("blueprint", {})
        if count is None:
            count = plan.get("gap", 0)
            if plan:
                print(f"从蓝图读取缺口：{count} 题（该章当前合格 {plan.get('eligible_count', 0)} 题）")
    if count is None:
        count = 10
        print(f"[提示] 未指定 --count 且无蓝图，默认生成 {count} 题（建议先执行 plan 子命令）")
    if count <= 0:
        print(f"[OK] 第 {ch} 章无缺口，无需补题")
        return 0

    profiles = load_profiles()
    profile = (profiles or {}).get("profiles", {}).get(str(ch), {})
    sections = cc.extract_chapter_sections(max_chars=9000)
    section_text = sections.get(ch, {}).get("text", "")

    rng = random.Random(args.seed)
    samples = rng.sample(arr, min(args.samples, len(arr))) if arr else []
    if not samples:
        print(f"[提示] 第 {ch} 章暂无可用题目，将按章节画像直接出题。")

    ch_name = CHAPTERS[ch]
    est_calls = (count + args.batch - 1) // args.batch + count * 6  # 生成批次 + 每题最多 6 次检查
    print(f"目标：第 {ch} 章「{ch_name}」现有 {len(arr)} 题，生成 {count} 题（每批 {args.batch}）")
    print(f"检查链（每题）：格式 → 文本相似初筛 → 语义查重 → 章节归属 → 质量评审 → 独立解题 → 教材证据核对")
    print(f"预计调用：≈{est_calls} 次；并发 1，失败自动重试")

    draft, rejected = [], []
    batch_qs = []  # 本批次已接收草稿（参与后续题的相似度池）
    made, batch_no = 0, 0
    max_batches = args.max_retry + (count // max(args.batch, 1)) + 2
    while made < count and batch_no < max_batches:
        batch_no += 1
        n = min(args.batch, count - made)
        prompt = gen_prompt(ch_name, profile, samples, existing_stems, n, blueprint)
        text = chat(cfg, model, [{"role": "system", "content": GEN_SYSTEM},
                                 {"role": "user", "content": prompt}],
                    max_tokens=4000, temperature=0.7)
        items = parse_json_obj(text)
        if not isinstance(items, list):
            print(f"  [批次{batch_no}] 输出解析失败，重试…")
            continue
        ok = 0
        for it in items:
            if not isinstance(it, dict) or ok >= n:
                continue
            stem = cc.normalize_space(it.get("stem", ""))
            if not stem:
                continue
            labels = [o.get("option_label") for o in it.get("options", [])]
            if len(labels) != 4 or len(set(labels)) != 4 or set(labels) != {"A", "B", "C", "D"}:
                rejected.append({"stem": stem[:60], "why": "选项格式不合格"})
                continue
            ans = ",".join(norm_ans(it.get("answer", "")))
            a_list = ans.split(",") if ans else []
            qtype = 1 if len(a_list) > 1 else 0
            if not a_list or (qtype == 0 and len(a_list) != 1):
                rejected.append({"stem": stem[:60], "why": "答案格式不合格"})
                continue
            diff_label = it.get("difficulty") if it.get("difficulty") in ("入门", "进阶", "挑战") else "进阶"
            q = {
                "seq": str(next_seq).zfill(4),
                "type": qtype,
                "stem": stem,
                "options": [{"option_label": o["option_label"],
                             "option_text": cc.normalize_space(o.get("option_text", ""))}
                            for o in it["options"]],
                "answer": ans,
                "analysis": cc.normalize_space(it.get("analysis", "")) or "暂无",
                "chapter": ch,
                "difficulty_score": {"入门": 1, "进阶": 2, "挑战": 3}[diff_label],
                "difficulty_label": diff_label,
                "difficulty_sort": {"入门": 1, "进阶": 2, "挑战": 3}[diff_label],
            }
            # 完整检查链（任一阶段失败即淘汰，全部记录）
            pool = all_q + batch_qs
            passed, checks = full_check_chain(cfg, model, q, pool, existing_keys,
                                              set(), profiles, section_text)
            if not passed:
                failed = [c for c in checks if not c["passed"]]
                rejected.append({"stem": stem[:60],
                                 "why": f"[{failed[0]['stage']}] {failed[0]['detail']}",
                                 "checks": checks})
                continue
            q["gen_meta"] = {
                "batch_id": f"ch{ch}-{datetime.now().strftime('%Y%m%d')}-{batch_no}",
                "knowledge_point": str(it.get("knowledge_point", ""))[:30],
                "basis": str(it.get("basis", ""))[:60],
                "checks": checks,
                "note": "草稿通过 ≠ 正式入库；合入需人工逐题审核。",
            }
            next_seq += 1
            draft.append(q)
            batch_qs.append({**q, "qid": f"ch{ch}-{q['seq']}"})
            existing_stems.append(stem)
            ok += 1
            made += 1
        print(f"  [批次{batch_no}] 接收 {len(items)} → 通过全部检查 {ok}（累计 {made}/{count}）")
        if ok == 0 and batch_no >= args.max_retry:
            print("  连续失败，提前结束。")
            break

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DRAFTS_DIR / f"questions_auto_ch{ch}.json"
    out_path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "chapter": ch,
        "note": ("草稿：已通过格式校验、文本相似初筛、LLM 语义查重（考点+解题路径）、"
                 "章节归属、质量评审、隐藏答案独立解题、教材证据核对七段检查；"
                 "草稿通过 ≠ 正式入库，合入前仍需人工逐题审核"
                 "（merge_new_questions.py）。"),
        "check_chain": ["format", "sim_text", "sem_dup", "chapter", "quality", "solve", "evidence"],
        "draft": draft,
        "rejected": rejected[:200],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n草稿: {out_path.relative_to(ROOT)}（通过 {len(draft)} 题，淘汰 {len(rejected)} 题）")
    if made < count:
        print(f"[缺口] 未达标：还差 {count - made} 题（已达尝试上限，不降低质量凑数）")
    print("下一步（人工逐题审核后合入正式题库）：")
    print(f"  python scripts/merge_new_questions.py --drafts {out_path.name}")
    return 0


# ---------------- 执行操作 ----------------

def _resolve(path_str: str) -> pathlib.Path:
    p = pathlib.Path(path_str)
    return p if p.is_absolute() else ROOT / p


def load_action_list(path: pathlib.Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) else data
    out = []
    for it in items:
        if isinstance(it, str):
            out.append({"qid": it, "reason": ""})
        elif isinstance(it, dict) and it.get("qid"):
            out.append({"qid": str(it["qid"]), "reason": str(it.get("reason", "")),
                        "to": it.get("to") or it.get("chapter")})
    return out


def cmd_remove(args) -> int:
    """软删除：数据保留在 JSON 主文件，运行时 .js 不再包含，可随时恢复。"""
    src = _resolve(args.from_file)
    if not src.exists():
        print(f"[错误] 清单不存在: {src}")
        return 1
    items = load_action_list(src)
    if not items:
        print("[错误] 清单为空")
        return 1
    # 幂等：重复执行同一清单 → 复用同一批次号
    batch_id = "rm_" + src.stem + "_" + re.sub(r"[-:T]", "", json.loads(src.read_text(encoding='utf-8')).get("generated_at", str(int(datetime.now().timestamp()))))
    if cc.batch_exists(batch_id):
        print(f"[幂等] 该清单已于批次 {batch_id} 应用过，跳过。")
        return 0

    bank = cc.load_bank()
    result = cc.soft_delete(bank, items, source=f"quiz_curate remove <{src.name}>", batch_id=batch_id)
    if not result["applied"]:
        print("[提示] 没有可删除的题（全部不存在或已删除）")
        for s in result["skipped"][:10]:
            print(f"  [跳过] {s['qid']}: {s['why']}")
        return 0

    index = cc.build_index(bank)
    print(f"将软删除 {result['applied']} 题（跳过 {len(result['skipped'])}）：")
    for it in items:
        qid = it["qid"]
        if qid in index and not index[qid][1].get("deleted"):
            stem = cc.normalize_space(index[qid][1].get("stem", ""))[:60]
            print(f"  {qid}  {it.get('reason', '')}  {stem}")

    if not args.apply:
        print("\n[dry-run] 未做任何修改。确认无误后追加 --apply 执行软删除。")
        return 0

    cc.write_bank(bank)
    cc.append_batch("soft_delete", f"quiz_curate remove <{src.name}>",
                    result["ledger_items"], batch_id=batch_id)
    ok = rebuild_min_js()
    print(f"\n已软删除 {result['applied']} 题（数据保留，可用 restore 恢复）")
    print("已重写 quiz_categorized.json / .js（运行时不含软删除题）"
          + ("，并重压缩 min.js" if ok else "（min.js 重压缩失败，请手动执行 python scripts/compress_bank.py）"))
    print("提示：请同步更新 index.html 中 quiz_categorized.min.js?v= 的版本号以强刷缓存。")
    print(f"提示：批次号 {batch_id}，回滚：python scripts/quiz_curate.py rollback --batch {batch_id} --apply")
    return 0


def cmd_restore(args) -> int:
    src = _resolve(args.from_file)
    if src.exists():
        items = load_action_list(src)
        qids = [it["qid"] for it in items]
    elif args.qids:
        qids = [q.strip() for q in args.qids.split(",") if q.strip()]
    else:
        print("[错误] 需要 --from 清单或 --qids（逗号分隔）")
        return 1
    bank = cc.load_bank()
    result = cc.restore(bank, qids, source="quiz_curate restore")
    if not result["applied"]:
        print("[提示] 没有可恢复的题")
        for s in result["skipped"][:10]:
            print(f"  [跳过] {s['qid']}: {s['why']}")
        return 0
    if not args.apply:
        print(f"将恢复 {result['applied']} 题：{', '.join(qids[:20])}{'…' if len(qids) > 20 else ''}")
        print("\n[dry-run] 追加 --apply 执行恢复。")
        return 0
    cc.write_bank(bank)
    cc.append_batch("restore", "quiz_curate restore", result["ledger_items"])
    ok = rebuild_min_js()
    print(f"已恢复 {result['applied']} 题" + ("，重压缩 min.js" if ok else ""))
    return 0


def cmd_rollback(args) -> int:
    if not args.batch:
        print("[错误] 需要 --batch <batch_id>（见 status 子命令）")
        return 1
    done, notes = cc.rollback_batch(args.batch, dry_run=not args.apply)
    for n in notes:
        print(" ", n)
    if done == 0:
        return 1
    if args.apply:
        ok = rebuild_min_js()
        print(f"已回滚批次 {args.batch} 的 {done} 条变更" + ("，重压缩 min.js" if ok else ""))
    else:
        print(f"[dry-run] 可回滚 {done} 条，追加 --apply 执行。")
    return 0


def cmd_status(args) -> int:
    bank = cc.load_bank()
    all_q = [q for arr in bank["questions_by_chapter"].values() for q in arr]
    deleted = [q for q in all_q if q.get("deleted")]
    with_hist = [q for q in all_q if q.get("answer_history")]
    ledger = cc.load_ledger()
    print(f"题库：总 {len(all_q)} 题 · 在用 {len(all_q) - len(deleted)} · 软删除 {len(deleted)} · "
          f"含答案修正历史 {len(with_hist)} 题")
    if deleted:
        print("\n最近软删除（最多 10 条）：")
        shown = 0
        for ch, qs in bank["questions_by_chapter"].items():
            for q in qs:
                if not q.get("deleted"):
                    continue
                if shown >= 10:
                    break
                shown += 1
                meta = q.get("deleted_meta") or {}
                print(f"  {ch}-{str(q['seq']).zfill(4)}  {meta.get('reason', '')[:50]}")
    print(f"\n操作台账：{len(ledger['batches'])} 个批次")
    for b in ledger["batches"][-15:]:
        print(f"  {b['batch_id']}  {b['at']}  {b['kind']:<12} {b['count']:>4} 条  {b.get('source', '')[:40]}")
    if len(ledger["batches"]) > 15:
        print(f"  …（共 {len(ledger['batches'])} 个批次，见 {cc.LEDGER_PATH.relative_to(ROOT)}）")
    print("\n回滚：python scripts/quiz_curate.py rollback --batch <batch_id> --apply")
    return 0


def cmd_move(args) -> int:
    src = _resolve(args.from_file)
    if not src.exists():
        print(f"[错误] 清单不存在: {src}")
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    items = data["items"] if isinstance(data, dict) else data

    bank = cc.load_bank()
    result = cc.move_questions(bank, items, CHAPTERS)
    plan, ledger_items = result["plan"], result["ledger_items"]

    if not plan:
        print("[提示] 没有需要移动的题目")
        for s in result["skipped"][:10]:
            print(f"  [跳过] {s['qid']}: {s['why']}")
        return 0
    print(f"将移动 {len(plan)} 题（跳过 {len(result['skipped'])}）：")
    for p in plan[:40]:
        print(f"  {p['qid']}  {CHAPTERS[int(p['from'])]} -> {CHAPTERS[p['to']]}  {p['reason'][:40]}")
    for s in result["skipped"]:
        print(f"  [跳过] {s['qid']}: {s['why']}")

    if not args.apply:
        print("\n[dry-run] 未做任何修改。确认无误后追加 --apply 执行移章。")
        return 0

    cc.write_bank(bank)
    cc.append_batch("move", f"quiz_curate move <{src.name}>", ledger_items)
    for li in ledger_items:
        if li["before_seq"] != li["after_seq"]:
            print(f"  [重编号] {li['qid']} 因目标章 seq 冲突改为 {li['to']}-{li['after_seq']}")
    ok = rebuild_min_js()
    print(f"已移动 {len(ledger_items)} 题，并重写 quiz_categorized.json / .js" + ("，重压缩 min.js" if ok else "（压缩失败请手动执行）"))
    print("提示：qid = 章-seq，换章后这些题在用户旧进度/错题记录中的条目会失联（不影响其它数据）。")
    print("提示：请同步更新 index.html 中 quiz_categorized.min.js?v= 的版本号。")
    return 0


def rebuild_min_js() -> bool:
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "compress_bank.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("[警告] compress_bank.py 执行失败：", (r.stderr or r.stdout)[-400:])
        return False
    return True


# ---------------- CLI ----------------

def main() -> int:
    ap = argparse.ArgumentParser(description="题库策展工具", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("profiles", help="从章节正文生成 12 章知识画像")
    p.add_argument("--force", action="store_true", help="覆盖已有画像")
    p.add_argument("--workers", type=int, default=4)
    p.set_defaults(func=cmd_profiles)

    p = sub.add_parser("chapter", help="章节匹配检查（五分类）")
    p.add_argument("--llm", action="store_true", help="用 LLM 逐题复核（需 verify_config.json）")
    p.add_argument("--full", action="store_true", help="全量语义审核：跳过规则初筛，逐题 LLM 审核（需 --llm）")
    p.add_argument("--chapters", default="", help="只审这些章，如 3,5")
    p.add_argument("--threshold", type=int, default=5, help="规则初筛的关键词分阈值（未经校准）")
    p.add_argument("--limit", type=int, default=0, help="只审前 N 题（0=全部）")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--yes", action="store_true", help="全量模式调用量确认")
    p.add_argument("--resume", action="store_true", help="复用已有 chapter_audit.json 中的复核结果")
    p.set_defaults(func=cmd_chapter)

    p = sub.add_parser("quality", help="低质题筛选（四分类）")
    p.add_argument("--llm", action="store_true", help="用 LLM 按维度评审")
    p.add_argument("--chapters", default="", help="只审这些章，如 3,5")
    p.add_argument("--min-score", type=int, default=3, help="规则信号分阈值")
    p.add_argument("--sim-threshold", type=float, default=0.6, help="语义查重 Jaccard 阈值（未经校准）")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--resume", action="store_true", help="复用已有质量评审结果")
    p.set_defaults(func=cmd_quality)

    sub.add_parser("answers", help="汇总答案检测处置报告").set_defaults(func=cmd_answers)

    p = sub.add_parser("plan", help="统计各章题量缺口，生成补题蓝图")
    p.add_argument("--target", type=int, default=DEFAULT_TARGET, help="每章目标题量（默认建议值）")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("generate", help="按蓝图生成新题草稿（含自检链）")
    p.add_argument("--chapter", type=int, required=True)
    p.add_argument("--count", type=int, default=None, help="目标出题数（默认取蓝图缺口）")
    p.add_argument("--batch", type=int, default=8, help="每批请求数量")
    p.add_argument("--samples", type=int, default=6, help="作为风格样例的现有题数")
    p.add_argument("--max-retry", type=int, default=5)
    p.add_argument("--seed", type=int, default=7)
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("remove", help="按清单软删除题目（默认 dry-run）")
    p.add_argument("--from", dest="from_file", required=True, help="清单 JSON 路径")
    p.add_argument("--apply", action="store_true", help="真正执行（会先备份，可回滚）")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("restore", help="恢复软删除的题目")
    p.add_argument("--from", dest="from_file", default="", help="清单 JSON 路径")
    p.add_argument("--qids", default="", help="逗号分隔的题号，如 3-0012,5-0001")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("rollback", help="按批次回滚变更")
    p.add_argument("--batch", default="", help="批次 ID（见 status）")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_rollback)

    p = sub.add_parser("move", help="按清单移动题目到其它章节（默认 dry-run）")
    p.add_argument("--from", dest="from_file", required=True, help="清单 JSON：{items:[{qid,to,reason}]}")
    p.add_argument("--apply", action="store_true", help="真正执行移章（会先备份）")
    p.set_defaults(func=cmd_move)

    sub.add_parser("status", help="题库统计与操作台账").set_defaults(func=cmd_status)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
