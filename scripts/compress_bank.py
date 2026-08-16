# -*- coding: utf-8 -*-
"""压缩题库为 data/quiz_categorized.min.js（移动端加载优化）

键名缩短 + 去除冗余字段（"暂无"解析、chapter 冗余键），
js/data.js 的 buildBank 同时兼容完整版与压缩版键名。

用法:
    python scripts/compress_bank.py
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "quiz_categorized.js"
OUT = ROOT / "data" / "quiz_categorized.min.js"

KEY_MAP = {
    "seq": "s", "stem": "t", "options": "o",
    "option_label": "l", "option_text": "x",
    "answer": "a", "analysis": "n", "type": "y",
    "difficulty_score": "ds", "difficulty_label": "dl",
    "difficulty_sort": "dsrt",
}


def compress_q(q):
    out = {
        "s": q["seq"],
        "t": q["stem"],
        "o": [{"l": o["option_label"], "x": o["option_text"]} for o in q.get("options", [])],
        "a": q.get("answer", ""),
    }
    if q.get("type") is not None:
        out["y"] = q["type"]
    an = q.get("analysis", "")
    if an and an != "暂无":
        out["n"] = an
    out["ds"] = q.get("difficulty_score", 99)
    out["dl"] = q.get("difficulty_label", "进阶")
    out["dsrt"] = q.get("difficulty_sort", 999)
    return out


def main() -> int:
    raw = SRC.read_text(encoding="utf-8")
    m = re.search(r"const\s+QUIZ_CHAPTERS\s*=\s*(\{.*?\});", raw, re.S)
    if not m:
        print("[错误] 未找到 QUIZ_CHAPTERS")
        return 1
    chapters = json.loads(m.group(1))
    m = re.search(r"const\s+QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\})", raw, re.S)
    data = json.loads(m.group(1).rstrip().rstrip(";"))

    out_data = {ch: [compress_q(q) for q in qs] for ch, qs in data.items()}
    js = ("const QUIZ_CHAPTERS = " + json.dumps(chapters, ensure_ascii=False) + ";\n\n"
          "/* AUTO-COMPRESSED by scripts/compress_bank.py from quiz_categorized.js */\n"
          "const QUIZ_DATA_BY_CHAPTER = "
          + json.dumps(out_data, ensure_ascii=False, separators=(",", ":")).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
          + ";\n")
    OUT.write_text(js, encoding="utf-8")
    src_kb = SRC.stat().st_size / 1024
    out_kb = OUT.stat().st_size / 1024
    print(f"压缩完成: {src_kb:.0f} KB -> {out_kb:.0f} KB (省 {100 - out_kb / src_kb * 100:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
