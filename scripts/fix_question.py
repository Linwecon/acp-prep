# -*- coding: utf-8 -*-
"""改写低质量题目 data/quiz_categorized.js，并重新生成压缩版。

REPLACEMENTS: { "章-seq": { 新题干/选项/答案/解析 } }
用法: python scripts/fix_question.py
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "quiz_categorized.js"

REPLACEMENTS = {
    # 1-0080：原为"答案直接复述题干"的弱智题，改写为场景化提示工程题
    "1-0080": {
        "stem": "开发者需要让大模型对一段产品介绍进行扩写和润色，使其更吸引消费者。以下哪种提示词设计最能达成目标？",
        "options": [
            {"option_label": "A", "option_text": "提供原文，并提示“在保持事实准确的前提下扩写润色，语言更生动，控制在 300 字以内”"},
            {"option_label": "B", "option_text": "只输入“帮我写一段吸引人的产品介绍”，不提供原文"},
            {"option_label": "C", "option_text": "要求模型“增加训练数据、提升模型效果”"},
            {"option_label": "D", "option_text": "要求模型“提高推理速度、减少生成时间”"},
        ],
        "answer": "A",
        "analysis": "扩写/润色类提示词应包含三要素：提供原文（上下文）、明确任务（扩写润色）、设定约束（事实准确、风格、字数）。A 完整覆盖三要素，最能稳定达成目标；B 未提供原文且任务表述泛化，模型只能凭空发挥；C 将“训练/数据”话题混入提示词设计，与本题无关；D 将“推理性能”话题混入，同样与提示词设计无关。",
    },
    # 1-0086：原为"依赖缺失材料的材料题"，不可独立作答，改写为自包含的分隔符考点题
    "1-0086": {
        "stem": "在编写提示词时，为了让大模型准确区分“系统指令”与“用户输入”的边界，最合适的做法是？",
        "options": [
            {"option_label": "A", "option_text": "使用明确的标记或分隔符（如【输入如下】）标出用户输入的范围"},
            {"option_label": "B", "option_text": "把用户输入与指令混在一起连续书写，不做任何区分"},
            {"option_label": "C", "option_text": "增加模型的训练数据量，让模型自行理解边界"},
            {"option_label": "D", "option_text": "调高 temperature 参数，让模型更灵活地推断边界"},
        ],
        "answer": "A",
        "analysis": "提示词分隔符是提示工程的核心技巧：用固定标记（如【输入如下】、XML 标签、三引号等）明确圈出用户输入，帮助模型区分“指令”与“数据”，减少误读。B 不做区分会让模型难以判断哪里是指令、哪里是输入，容易出错；C 混淆了提示词设计与模型训练——训练数据不改变提示词结构；D 混淆了采样参数的作用——temperature 只控制输出随机性，与输入边界无关。",
    },
}


def main() -> int:
    raw = SRC.read_text(encoding="utf-8")
    m = re.search(r"const\s+QUIZ_DATA_BY_CHAPTER\s*=\s*(\{.*\})", raw, re.S)
    data = json.loads(m.group(1).rstrip().rstrip(";"))

    for qid, new in REPLACEMENTS.items():
        ch, seq = qid.split("-")
        found = next((q for q in data.get(ch, []) if str(q.get("seq")) == seq), None)
        if found is None:
            print(f"[警告] 未找到 {qid}，跳过")
            continue
        found.update(new)
        print(f"已改写 {qid}: {new['stem'][:36]}...")

    SRC.write_text(raw[: m.start(1)] + json.dumps(data, ensure_ascii=False) + raw[m.end(1):], encoding="utf-8")

    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "compress_bank.py")], cwd=ROOT)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
