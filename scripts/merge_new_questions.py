# -*- coding: utf-8 -*-
"""合并新增题目到题库 JSON/JS 并做基础校验。

用法:
    python scripts/merge_new_questions.py
输入:
    data/quiz_categorized.json
    scripts/_drafts/questions_a.json (可选)
    scripts/_drafts/questions_b.json (可选)
输出:
    data/quiz_categorized.json
    data/quiz_categorized.js   (与 JSON 同步)
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "quiz_categorized.json"
JS_PATH = ROOT / "data" / "quiz_categorized.js"
DRAFTS = [
    ROOT / "scripts" / "_drafts" / "questions_a.json",
    ROOT / "scripts" / "_drafts" / "questions_b.json",
]

VALID_CHAPTERS = {str(i) for i in range(1, 13)}
DIFF_LABELS = {"入门": 1, "进阶": 2, "挑战": 3}


def norm_ans(ans):
    ans = re.sub(r"\s", "", str(ans or ""))
    if "," in ans:
        return [s.strip() for s in ans.split(",") if s.strip()]
    return [c for c in ans if re.match(r"[A-H]", c)]


def validate(q):
    errs = []
    if not isinstance(q, dict):
        return ["题目不是对象"]
    for key in ["seq", "type", "stem", "options", "answer", "analysis", "chapter", "difficulty_score", "difficulty_label", "difficulty_sort"]:
        if key not in q:
            errs.append(f"缺少字段 {key}")
    if "seq" in q and not re.fullmatch(r"\d{4,6}", str(q["seq"])):
        errs.append(f"seq 格式异常: {q.get('seq')}")
    if "type" in q and q["type"] not in (0, 1):
        errs.append(f"type 必须为 0/1: {q.get('type')}")
    if "chapter" in q:
        ch = str(q["chapter"])
        if ch not in VALID_CHAPTERS:
            errs.append(f"chapter 非法: {q.get('chapter')}")
        q["chapter"] = int(ch)
    if "options" in q:
        opts = q["options"]
        if not isinstance(opts, list) or len(opts) < 2:
            errs.append("选项数量不足")
        else:
            labels = [o.get("option_label") for o in opts]
            if len(labels) != len(set(labels)):
                errs.append(f"选项标签重复: {labels}")
            if any(not re.fullmatch(r"[A-H]", str(l)) for l in labels):
                errs.append(f"选项标签非法: {labels}")
    if "answer" in q and "options" in q:
        ans = norm_ans(q["answer"])
        labels = [o.get("option_label") for o in q.get("options", [])]
        if not ans:
            errs.append("答案为空")
        missing = [a for a in ans if a not in labels]
        if missing:
            errs.append(f"答案不在选项中: {missing}")
        if q.get("type") == 0 and len(ans) != 1:
            errs.append(f"单选答案数量异常: {ans}")
        if q.get("type") == 1 and len(ans) < 2:
            errs.append(f"多选答案数量异常: {ans}")
        q["answer"] = ",".join(ans)
    if "difficulty_label" in q and q["difficulty_label"] not in DIFF_LABELS:
        errs.append(f"难度标签非法: {q.get('difficulty_label')}")
    if "difficulty_score" in q:
        q["difficulty_score"] = int(q["difficulty_score"])
    if "difficulty_sort" in q:
        q["difficulty_sort"] = int(q["difficulty_sort"])
    return errs


def load_drafts():
    new_qs = []
    errors = []
    for path in DRAFTS:
        if not path.exists():
            print(f"[跳过] 未找到草稿: {path.name}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            errors.append(f"{path.name}: 顶层不是数组")
            continue
        for q in data:
            errs = validate(q)
            if errs:
                errors.append(f"{path.name} seq={q.get('seq')}: {'; '.join(errs)}")
            else:
                new_qs.append(q)
        print(f"[读取] {path.name}: {len(data)} 题")
    return new_qs, errors


def main():
    bank = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    by_ch = bank["questions_by_chapter"]
    old_total = sum(len(v) for v in by_ch.values())

    # 现有 seq 与 stem 归一化用于查重
    seen_seq = {str(q["seq"]) for arr in by_ch.values() for q in arr}
    seen_stem = {re.sub(r"\s", "", q["stem"]) for arr in by_ch.values() for q in arr}

    new_qs, errors = load_drafts()
    if errors:
        print("\n[校验错误]")
        for e in errors:
            print(" -", e)
        return 1

    added = 0
    dup = 0
    for q in new_qs:
        if q["seq"] in seen_seq:
            print(f"[跳过重复 seq] {q['seq']}")
            dup += 1
            continue
        stem = re.sub(r"\s", "", q["stem"])
        if stem in seen_stem:
            print(f"[警告-题干疑似重复] seq={q['seq']}: {q['stem'][:50]}")
        ch = str(q["chapter"])
        by_ch.setdefault(ch, []).append(q)
        seen_seq.add(q["seq"])
        seen_stem.add(stem)
        added += 1

    # 更新统计
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

    # 生成 quiz_categorized.js（与线上压缩版保持同一数据源）
    chapters = bank["chapters"]
    js = (
        "const QUIZ_CHAPTERS = " + json.dumps(chapters, ensure_ascii=False) + ";\n\n"
        "const QUIZ_DATA_BY_CHAPTER = " + json.dumps(by_ch, ensure_ascii=False, separators=(",", ":")) + ";\n"
    )
    JS_PATH.write_text(js, encoding="utf-8")

    print(f"\n合并完成: 原 {old_total} 题 -> 新增 {added} 题 -> 总 {total} 题")
    print(f"难度分布: {diff}")
    print(f"已写入: {JSON_PATH.name}, {JS_PATH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
