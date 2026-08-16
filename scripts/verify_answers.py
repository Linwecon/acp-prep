# -*- coding: utf-8 -*-
"""题库答案批量校验脚本（多模型交叉验证）

工作流：
  1. 读取题库 data/quiz_categorized.js
  2. 对每题构造"独立作答"提示词（不透露参考答案，避免模型迎合）
  3. 主模型（默认 qwen-plus）作答 → 与题库答案比对
  4. 分歧/无法作答的题，再用第二模型（默认 deepseek-v3.2）交叉作答
  5. 输出报告 docs/answer_verify_report.md + 结果缓存 data/verify_results.json

用法:
    python scripts/verify_answers.py --limit 50            # 只校验前 50 题
    python scripts/verify_answers.py --chapters 3,5        # 只校验第 3、5 章
    python scripts/verify_answers.py --sample 0.3          # 随机抽 30%
    python scripts/verify_answers.py --single              # 只用主模型（省钱）
    python scripts/verify_answers.py --resume              # 断点续跑
    python scripts/verify_answers.py --workers 8           # 并发数

配置: config/verify_config.json（见 verify_config.example.json）
"""
import argparse
import json
import pathlib
import random
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "quiz_categorized.js"
CFG = ROOT / "config" / "verify_config.json"
RESULT = ROOT / "data" / "verify_results.json"
REPORT = ROOT / "docs" / "answer_verify_report.md"

CTX = ssl.create_default_context()

# ---------- 题库加载（与 buildBank 相同判定） ----------

def norm_ans(ans):
    ans = re.sub(r"\s", "", str(ans or ""))
    if "," in ans:
        return [s.strip() for s in ans.split(",") if s.strip()]
    return [c for c in ans if re.match(r"[A-G]", c)]


def load_bank():
    raw = SRC.read_text(encoding="utf-8")
    m = re.search(r"const\s+QUIZ_CHAPTERS\s*=\s*(\{.*?\});", raw, re.S)
    chapters = json.loads(m.group(1)) if m else {}
    m = re.search(r"const\s+QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\})", raw, re.S)
    data = json.loads(m.group(1).rstrip().rstrip(";"))
    bank = []
    for ch, qs in data.items():
        seen = set()
        for q in qs:
            ans_arr = norm_ans(q.get("answer"))
            qid = f"{ch}-{q['seq']}"
            if qid in seen:
                qid += "b"  # 与 js/data.js 的撞号唯一化保持一致
            seen.add(qid)
            bank.append({
                "id": qid, "ch": ch, "seq": q["seq"],
                "stem": q.get("stem", ""),
                "options": [(o["option_label"], o["option_text"]) for o in q.get("options", [])],
                "ans": ans_arr,
                "multi": len(ans_arr) > 1 or q.get("type") == 2,
            })
    return bank, chapters

# ---------- LLM 调用 ----------

def chat(cfg, model, messages, max_tokens=800, temperature=0, timeout=60):
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
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
            return None
        except Exception:
            time.sleep(2 ** attempt + random.random())
    return None


def parse_json(text):
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


PROMPT = """你是阿里云大模型高级工程师认证（ACP）的出题专家。请独立解答下面这道{kind}题。

【要求】
1. 只输出 JSON，不要输出任何其他文字
2. JSON 格式：{{"answer": ["A"], "confidence": "high|mid|low", "reason": "不超过60字的理由"}}
3. 单选题 answer 为单元素数组；多选题 answer 为多元素数组，按字母排序
4. 若不确信，confidence 填 "low"，但仍给出你认为最可能的答案
5. 若题目信息不完整或无法作答，输出 {{"answer": [], "confidence": "low", "reason": "原因"}}

【题目】
{stem}

【选项】
{options}"""


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
        return {"answer": [], "confidence": "low", "reason": f"解析失败: {(text or '')[:80]}"}
    ans = obj.get("answer") or []
    ans = sorted({re.sub(r"[^A-G]", "", str(a)).upper() for a in ans if re.match(r"[A-G]", str(a))})
    return {"answer": ans, "confidence": str(obj.get("confidence", "low")).lower(), "reason": str(obj.get("reason", ""))[:120]}


def verdict(model_ans, bank_ans):
    """模型作答 vs 题库答案：agree / disagree / unsure"""
    if not model_ans:
        return "unsure"
    return "agree" if model_ans == sorted(bank_ans) else "disagree"

# ---------- 主流程 ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="题库答案批量校验")
    ap.add_argument("--limit", type=int, default=0, help="最多校验题数（0=全部）")
    ap.add_argument("--chapters", default="", help="仅校验章节，逗号分隔，如 3,5")
    ap.add_argument("--sample", type=float, default=0, help="随机抽样比例 0~1")
    ap.add_argument("--workers", type=int, default=4, help="并发数")
    ap.add_argument("--single", action="store_true", help="只用主模型")
    ap.add_argument("--resume", action="store_true", help="断点续跑")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not CFG.exists():
        print(f"[错误] 缺少配置文件 {CFG}\n请复制 config/verify_config.example.json 为 "
              f"verify_config.json 并填入你的 API Key。")
        return 1
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    primary = cfg.get("primary_model", "qwen-plus")
    secondary = cfg.get("secondary_model", "deepseek-v3.2")

    bank, chapters = load_bank()
    if args.chapters:
        chs = [c.strip() for c in args.chapters.split(",") if c.strip()]
        bank = [q for q in bank if q["ch"] in chs]
    if args.sample:
        rng = random.Random(args.seed)
        bank = rng.sample(bank, max(1, int(len(bank) * args.sample)))
    if args.limit:
        bank = bank[: args.limit]

    results = {}
    if args.resume and RESULT.exists():
        results = json.loads(RESULT.read_text(encoding="utf-8"))
        todo = [q for q in bank if q["id"] not in results]
        print(f"断点续跑：已有 {len(results)} 条结果，待校验 {len(todo)} 题")
    else:
        todo = bank

    print(f"待校验: {len(todo)} 题 | 主模型: {primary}" +
          ("" if args.single else f" + 第二模型: {secondary}") +
          f" | 并发: {args.workers}")

    calls = {"primary": 0, "secondary": 0}

    def verify(q):
        r1 = ask(cfg, primary, q)
        calls["primary"] += 1
        v1 = verdict(r1["answer"], q["ans"])
        r2 = None
        v2 = None
        if not args.single and v1 != "agree":
            r2 = ask(cfg, secondary, q)
            calls["secondary"] += 1
            v2 = verdict(r2["answer"], q["ans"])
        return q["id"], {
            "ch": q["ch"], "seq": q["seq"], "multi": q["multi"],
            "bank": q["ans"], "kind": "多选" if q["multi"] else "单选",
            "primary": {**r1, "verdict": v1},
            "secondary": None if r2 is None else {**r2, "verdict": v2},
        }

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(verify, q): q for q in todo}
        for fut in as_completed(futs):
            qid, res = fut.result()
            results[qid] = res
            done += 1
            if done % 20 == 0 or done == len(todo):
                RESULT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"  进度 {done}/{len(todo)} | 主模型调用 {calls['primary']} | 第二模型 {calls['secondary']}")

    RESULT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- 汇总 ----------
    stat = {"agree": 0, "disagree": 0, "unsure": 0, "conflict": 0, "second_disagree": 0}
    by_ch = {}
    issues = []
    for q in bank:
        r = results[q["id"]]
        v1, v2 = r["primary"]["verdict"], (r["secondary"] or {}).get("verdict")
        s = by_ch.setdefault(r["ch"], {"agree": 0, "disagree": 0, "unsure": 0, "conflict": 0})
        if v1 == "agree":
            stat["agree"] += 1; s["agree"] += 1
        elif v1 == "unsure":
            stat["unsure"] += 1; s["unsure"] += 1
        elif v2 == "agree":
            stat["agree"] += 1; s["agree"] += 1
        elif v2 == "disagree":
            stat["conflict"] += 1; s["conflict"] += 1
            issues.append((r, q["stem"], "两模型均反对题库答案"))
        elif v2 == "unsure":
            stat["unsure"] += 1; s["unsure"] += 1
        else:
            stat["disagree"] += 1; s["disagree"] += 1
            issues.append((r, q["stem"], "主模型反对，第二模型未交叉"))

    n = len(bank)
    print(f"\n===== 校验完成: {n} 题 =====")
    print(f"  一致通过   : {stat['agree']:>4}  ({stat['agree']/n*100:.1f}%)")
    print(f"  主模型反对 : {stat['disagree']:>4}  ({stat['disagree']/n*100:.1f}%)")
    print(f"  两模型冲突 : {stat['conflict']:>4}  ({stat['conflict']/n*100:.1f}%)  ← 题库答案可能错误")
    print(f"  无法作答   : {stat['unsure']:>4}  ({stat['unsure']/n*100:.1f}%)")
    print(f"  LLM 调用   : 主模型 {calls['primary']} 次 + 第二模型 {calls['secondary']} 次")

    # ---------- 报告 ----------
    lines = [
        "# 题库答案校验报告",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 主模型 `{primary}` · "
        f"第二模型 `{'无' if args.single else secondary}` · 校验 {n} 题",
        "",
        "## 一、总体结论",
        "",
        f"| 类别 | 题数 | 占比 | 含义 |",
        f"|------|-----:|-----:|------|",
        f"| ✅ 一致通过 | {stat['agree']} | {stat['agree']/n*100:.1f}% | 模型答案与题库答案一致，可信度高 |",
        f"| ⚠️ 主模型反对 | {stat['disagree']} | {stat['disagree']/n*100:.1f}% | 主模型认为题库答案有误（未交叉验证） |",
        f"| ❌ 两模型冲突 | {stat['conflict']} | {stat['conflict']/n*100:.1f}% | 两个模型均反对题库答案，**题库答案很可能错误** |",
        f"| ❓ 无法作答 | {stat['unsure']} | {stat['unsure']/n*100:.1f}% | 模型认为题目信息不完整或无法作答 |",
        "",
        "## 二、分章节分布",
        "",
        "| 章节 | 一致 | 主模型反对 | 两模型冲突 | 无法作答 |",
        "|------|-----:|----------:|----------:|--------:|",
    ]
    for ch in sorted(by_ch, key=int):
        s = by_ch[ch]
        name = chapters.get(ch, f"第{ch}章")
        t = sum(s.values()) or 1
        lines.append(
            f"| {ch} {name} | {s['agree']} | {s['disagree']} | {s['conflict']} | {s['unsure']} |")
    lines += ["", "## 三、待人工复核清单（两模型冲突 / 无法作答）", ""]
    if issues:
        lines.append("| 题号 | 类型 | 题库答案 | 主模型 | 第二模型 | 判定 |")
        lines.append("|------|------|---------|--------|---------|------|")
        for r, stem, tag in issues:
            p, s2 = r["primary"], r["secondary"]
            lines.append(
                f"| {r['ch']}-{r['seq']} | {r['kind']} | {','.join(r['bank']) or '空'} | "
                f"{','.join(p['answer']) or '空'}（{p['confidence']}） | "
                f"{','.join(s2['answer']) if s2 else '—'} | {tag} |")
        lines.append("")
        lines.append("### 冲突题理由摘录")
        lines.append("")
        for r, stem, tag in issues:
            p, s2 = r["primary"], r["secondary"]
            lines.append(f"**{r['ch']}-{r['seq']}**：{stem[:90]}…")
            lines.append(f"- 题库答案 {','.join(r['bank'])}｜主模型：{p['reason'] or '无'}")
            if s2:
                lines.append(f"- 第二模型：{s2['reason'] or '无'}")
            lines.append("")
    else:
        lines.append("本次校验未发现冲突题，全部一致通过。")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
