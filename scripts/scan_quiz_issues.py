"""
ACP 题库全库体检脚本

输出：
1. 题库全库问题清单.json
2. 题库全库体检.md
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from classify_questions import (
    ANALYSIS_RULES,
    CHAPTERS,
    RULES,
    apply_manual_fixes,
    normalize_answer_labels,
    normalize_chapter,
)


QUIZ_FILE = PROJECT_ROOT / "data" / "quiz_data.json"
JSON_REPORT = PROJECT_ROOT / "题库全库问题清单.json"
MD_REPORT = PROJECT_ROOT / "题库全库体检.md"


MULTI_HINTS = [
    "以下哪些",
    "有哪些",
    "哪些是",
    "哪几个",
    "多选",
]

SINGLE_HINTS = [
    "以下哪种",
    "以下哪个",
    "哪一项",
    "哪种方法",
    "主要作用是什么",
    "用于评估什么",
    "会使用哪个方法",
    "有什么特点",
    "是什么",
]

CONTEXT_HINTS = [
    "在示例中",
    "以下代码片段中",
    "在代码中",
    "函数中",
    "优化后的答疑机器人",
    "如果问题类型是",
    "如果问题类型无法识别",
]


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def build_text_blob(q: dict) -> str:
    parts = [q.get("stem", ""), q.get("analysis", "")]
    parts.extend(opt.get("option_text", "") for opt in q.get("options", []))
    return " ".join(parts)


def keyword_count(text: str, keyword: str) -> int:
    """与分类脚本保持一致，英文词按边界匹配，避免 Token/tokenize 误报。"""
    if re.search(r"[A-Za-z0-9_]", keyword) and not re.search(r"[\u4e00-\u9fff]", keyword):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(keyword)}(?![A-Za-z0-9_])"
        return len(re.findall(pattern, text, flags=re.IGNORECASE))
    return text.lower().count(keyword.lower())


def score_question(q: dict) -> tuple[dict[int, int], dict[int, list[str]]]:
    text = build_text_blob(q)
    scores = {ch: 0 for ch in CHAPTERS}
    matched = defaultdict(list)

    for ch, rule in RULES.items():
        for keyword, weight in rule["keywords"]:
            count = keyword_count(text, keyword)
            if count > 0:
                scores[ch] += weight * count
                if keyword not in matched[ch]:
                    matched[ch].append(keyword)

    if all(v == 0 for v in scores.values()):
        analysis = q.get("analysis", "")
        for kw, ch in ANALYSIS_RULES.items():
            if kw.lower() in analysis.lower():
                scores[ch] += 1
                if kw not in matched[ch]:
                    matched[ch].append(kw)

    return scores, matched


def top_chapters(scores: dict[int, int], n: int = 3) -> list[tuple[int, int]]:
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:n]


def issue_brief(q: dict) -> dict:
    return {
        "seq": str(q.get("seq", "")).zfill(4),
        "chapter": normalize_chapter(q.get("chapter")),
        "stem": q.get("stem", ""),
        "answer": q.get("answer", ""),
        "type": q.get("type"),
    }


def main() -> None:
    raw_questions = json.loads(QUIZ_FILE.read_text(encoding="utf-8"))
    questions = [apply_manual_fixes(q) for q in raw_questions]

    duplicate_option_texts = []
    duplicate_option_labels = []
    answer_label_mismatches = []
    multi_hint_single_answer = []
    single_hint_multi_answer = []
    context_dependent = []
    high_confidence_chapter_mismatches = []
    duplicate_stems = []

    stem_groups = defaultdict(list)
    mismatch_by_current_chapter = Counter()
    context_by_chapter = Counter()

    for q in questions:
        seq = str(q.get("seq", "")).zfill(4)
        current_ch = normalize_chapter(q.get("chapter"))
        option_labels = [normalize_space(opt.get("option_label", "")).upper() for opt in q.get("options", [])]
        option_texts = [normalize_space(opt.get("option_text", "")) for opt in q.get("options", [])]
        answer_labels = normalize_answer_labels(q.get("answer", ""))

        text_counter = Counter(opt.lower() for opt in option_texts if opt)
        repeated_texts = [text for text, count in text_counter.items() if count > 1]
        if repeated_texts:
            duplicate_option_texts.append(
                {
                    **issue_brief(q),
                    "repeated_option_texts": repeated_texts,
                }
            )

        label_counter = Counter(label for label in option_labels if label)
        repeated_labels = [label for label, count in label_counter.items() if count > 1]
        if repeated_labels:
            duplicate_option_labels.append(
                {
                    **issue_brief(q),
                    "repeated_option_labels": repeated_labels,
                }
            )

        missing_labels = [label for label in answer_labels if label not in option_labels]
        if missing_labels:
            answer_label_mismatches.append(
                {
                    **issue_brief(q),
                    "missing_answer_labels": missing_labels,
                    "option_labels": option_labels,
                }
            )

        stem = normalize_space(q.get("stem", ""))
        has_multi_hint = any(hint in stem for hint in MULTI_HINTS)

        if has_multi_hint and len(answer_labels) == 1:
            multi_hint_single_answer.append(issue_brief(q))

        if any(hint in stem for hint in SINGLE_HINTS) and not has_multi_hint and len(answer_labels) > 1:
            single_hint_multi_answer.append(issue_brief(q))

        if any(hint in stem for hint in CONTEXT_HINTS):
            context_dependent.append(issue_brief(q))
            context_by_chapter[current_ch] += 1

        scores, matched = score_question(q)
        ranked = top_chapters(scores, 3)
        top_ch, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0
        current_score = scores.get(current_ch, 0)

        if (
            current_ch in CHAPTERS
            and top_ch != current_ch
            and top_score >= 5
            and (current_score == 0 or top_score >= current_score + 4)
            and (top_score - second_score >= 2)
        ):
            high_confidence_chapter_mismatches.append(
                {
                    **issue_brief(q),
                    "predicted_chapter": top_ch,
                    "predicted_chapter_name": CHAPTERS[top_ch],
                    "current_chapter_name": CHAPTERS.get(current_ch),
                    "current_score": current_score,
                    "predicted_score": top_score,
                    "matched_keywords": matched.get(top_ch, [])[:8],
                }
            )
            mismatch_by_current_chapter[current_ch] += 1

        stem_groups[stem].append(
            {
                "seq": seq,
                "chapter": current_ch,
                "answer": q.get("answer", ""),
            }
        )

    for stem, items in stem_groups.items():
        if len(items) < 2:
            continue
        answers = sorted({item["answer"] for item in items})
        chapters = sorted({item["chapter"] for item in items})
        duplicate_stems.append(
            {
                "stem": stem,
                "count": len(items),
                "seqs": [item["seq"] for item in items],
                "answers": answers,
                "chapters": chapters,
                "inconsistent_answers": len(answers) > 1,
                "inconsistent_chapters": len(chapters) > 1,
            }
        )

    duplicate_stems.sort(
        key=lambda item: (
            not item["inconsistent_answers"],
            not item["inconsistent_chapters"],
            -item["count"],
            item["seqs"][0],
        )
    )
    high_confidence_chapter_mismatches.sort(
        key=lambda item: (
            -(item["predicted_score"] - item["current_score"]),
            -item["predicted_score"],
            item["seq"],
        )
    )

    report = {
        "summary": {
            "total_questions": len(questions),
            "duplicate_option_texts": len(duplicate_option_texts),
            "duplicate_option_labels": len(duplicate_option_labels),
            "answer_label_mismatches": len(answer_label_mismatches),
            "multi_hint_single_answer": len(multi_hint_single_answer),
            "single_hint_multi_answer": len(single_hint_multi_answer),
            "context_dependent_questions": len(context_dependent),
            "high_confidence_chapter_mismatches": len(high_confidence_chapter_mismatches),
            "duplicate_stems": len(duplicate_stems),
        },
        "mismatch_by_current_chapter": {str(k): v for k, v in sorted(mismatch_by_current_chapter.items())},
        "context_by_chapter": {str(k): v for k, v in sorted(context_by_chapter.items())},
        "duplicate_option_texts": duplicate_option_texts,
        "duplicate_option_labels": duplicate_option_labels,
        "answer_label_mismatches": answer_label_mismatches,
        "multi_hint_single_answer": multi_hint_single_answer,
        "single_hint_multi_answer": single_hint_multi_answer,
        "context_dependent_questions": context_dependent,
        "high_confidence_chapter_mismatches": high_confidence_chapter_mismatches,
        "duplicate_stems": duplicate_stems,
    }

    JSON_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = []
    lines.append("# 题库全库体检")
    lines.append("")
    lines.append("> 说明：这是程序化筛查结果，用于定位高风险题目，不等于全部都已人工确认。")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 总题量：`{len(questions)}`")
    lines.append(f"- 重复选项文本：`{len(duplicate_option_texts)}`")
    lines.append(f"- 重复选项标签：`{len(duplicate_option_labels)}`")
    lines.append(f"- 答案标签对不上选项：`{len(answer_label_mismatches)}`")
    lines.append(f"- 题干像多选但当前只有单答案：`{len(multi_hint_single_answer)}`")
    lines.append(f"- 题干像单选但当前是多答案：`{len(single_hint_multi_answer)}`")
    lines.append(f"- 明显依赖外部上下文/代码片段的题：`{len(context_dependent)}`")
    lines.append(f"- 高置信度章节错配候选：`{len(high_confidence_chapter_mismatches)}`")
    lines.append(f"- 重复题干：`{len(duplicate_stems)}`")
    lines.append("")

    lines.append("## 高置信度章节错配")
    lines.append("")
    lines.append("| 题号 | 当前章节 | 建议章节 | 分差 | 命中关键词 | 题干 |")
    lines.append("|---|---|---|---:|---|---|")
    for item in high_confidence_chapter_mismatches[:80]:
        diff = item["predicted_score"] - item["current_score"]
        lines.append(
            f"| {item['seq']} | {item['current_chapter_name']} | {item['predicted_chapter_name']} | {diff} | "
            f"{' / '.join(item['matched_keywords'][:4])} | {item['stem']} |"
        )
    lines.append("")

    lines.append("## 重复选项文本")
    lines.append("")
    lines.append("| 题号 | 章节 | 重复项 | 题干 |")
    lines.append("|---|---|---|---|")
    for item in duplicate_option_texts[:80]:
        lines.append(
            f"| {item['seq']} | {CHAPTERS.get(item['chapter'])} | {' / '.join(item['repeated_option_texts'])} | {item['stem']} |"
        )
    lines.append("")

    lines.append("## 答案标签对不上选项")
    lines.append("")
    lines.append("| 题号 | 章节 | 缺失答案标签 | 当前答案 | 题干 |")
    lines.append("|---|---|---|---|---|")
    for item in answer_label_mismatches[:80]:
        lines.append(
            f"| {item['seq']} | {CHAPTERS.get(item['chapter'])} | {' / '.join(item['missing_answer_labels'])} | "
            f"{item['answer']} | {item['stem']} |"
        )
    lines.append("")

    lines.append("## 多选提示但单答案")
    lines.append("")
    lines.append("| 题号 | 章节 | 当前答案 | 题干 |")
    lines.append("|---|---|---|---|")
    for item in multi_hint_single_answer[:80]:
        lines.append(f"| {item['seq']} | {CHAPTERS.get(item['chapter'])} | {item['answer']} | {item['stem']} |")
    lines.append("")

    lines.append("## 依赖上下文的题")
    lines.append("")
    lines.append("| 题号 | 章节 | 当前答案 | 题干 |")
    lines.append("|---|---|---|---|")
    for item in context_dependent[:100]:
        lines.append(f"| {item['seq']} | {CHAPTERS.get(item['chapter'])} | {item['answer']} | {item['stem']} |")
    lines.append("")

    lines.append("## 重复题干")
    lines.append("")
    lines.append("| 次数 | 题号 | 答案是否不一致 | 章节是否不一致 | 题干 |")
    lines.append("|---:|---|---|---|---|")
    for item in duplicate_stems[:80]:
        lines.append(
            f"| {item['count']} | {', '.join(item['seqs'])} | "
            f"{'是' if item['inconsistent_answers'] else '否'} | "
            f"{'是' if item['inconsistent_chapters'] else '否'} | {item['stem']} |"
        )
    lines.append("")

    lines.append("## 文件输出")
    lines.append("")
    lines.append(f"- 详细 JSON：`{JSON_REPORT.name}`")
    lines.append(f"- Markdown 摘要：`{MD_REPORT.name}`")
    lines.append("")

    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")

    print(f"已输出 {JSON_REPORT.name}")
    print(f"已输出 {MD_REPORT.name}")


if __name__ == "__main__":
    main()
