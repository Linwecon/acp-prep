# -*- coding: utf-8 -*-
"""改写低质量题目 data/quiz_categorized.js 中的 1-0080，并重新生成压缩版。
用法: python scripts/fix_question.py
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "quiz_categorized.js"

NEW_Q = {
    "stem": "开发者需要让大模型对一段产品介绍进行扩写和润色，使其更吸引消费者。以下哪种提示词设计最能达成目标？",
    "options": [
        {"option_label": "A", "option_text": "提供原文，并提示“在保持事实准确的前提下扩写润色，语言更生动，控制在 300 字以内”"},
        {"option_label": "B", "option_text": "只输入“帮我写一段吸引人的产品介绍”，不提供原文"},
        {"option_label": "C", "option_text": "要求模型“增加训练数据、提升模型效果”"},
        {"option_label": "D", "option_text": "要求模型“提高推理速度、减少生成时间”"},
    ],
    "answer": "A",
    "analysis": "扩写/润色类提示词应包含三要素：提供原文（上下文）、明确任务（扩写润色）、设定约束（事实准确、风格、字数）。A 完整覆盖三要素，最能稳定达成目标；B 未提供原文且任务表述泛化，模型只能凭空发挥；C 将“训练/数据”话题混入提示词设计，与本题无关；D 将“推理性能”话题混入，同样与提示词设计无关。",
}


def main() -> int:
    raw = SRC.read_text(encoding="utf-8")
    m = re.search(r"const\s+QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\})", raw, re.S)
    data = json.loads(m.group(1).rstrip().rstrip(";"))

    found = None
    for q in data["1"]:
        if str(q.get("seq")) == "0080":
            found = q
            break
    if found is None:
        print("[错误] 未找到 1-0080")
        return 1

    found.update(NEW_Q)
    new_raw = raw[: m.start(1)] + json.dumps(data, ensure_ascii=False) + raw[m.end(1):]
    SRC.write_text(new_raw, encoding="utf-8")
    print("已改写 1-0080 ->", found["stem"][:40], "...")

    # 重新生成压缩版
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "compress_bank.py")], cwd=ROOT)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
