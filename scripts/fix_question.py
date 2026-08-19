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
    # 1-0080：原为"答案直接复述题干"的弱智题，改写为场景化提示工程题（答案分散到 B）
    "1-0080": {
        "stem": "开发者需要让大模型对一段产品介绍进行扩写和润色，使其更吸引消费者。以下哪种提示词设计最能达成目标？",
        "options": [
            {"option_label": "A", "option_text": "要求模型“增加训练数据、提升模型效果”"},
            {"option_label": "B", "option_text": "提供原文，并提示“在保持事实准确的前提下扩写润色，语言更生动，控制在 300 字以内”"},
            {"option_label": "C", "option_text": "只输入“帮我写一段吸引人的产品介绍”，不提供原文"},
            {"option_label": "D", "option_text": "要求模型“提高推理速度、减少生成时间”"},
        ],
        "answer": "B",
        "analysis": "扩写/润色类提示词应包含三要素：提供原文（上下文）、明确任务（扩写润色）、设定约束（事实准确、风格、字数）。正确做法完整覆盖三要素，最能稳定达成目标；“只输入一句话且不提供原文”会让模型凭空发挥；“增加训练数据”“提高推理速度”把训练与性能话题混入提示词设计，与本题无关。",
    },
    # 1-0086：原为"依赖缺失材料的材料题"，不可独立作答，改写为自包含的分隔符考点题（答案分散到 C）
    "1-0086": {
        "stem": "在编写提示词时，为了让大模型准确区分“系统指令”与“用户输入”的边界，最合适的做法是？",
        "options": [
            {"option_label": "A", "option_text": "把用户输入与指令混在一起连续书写，不做任何区分"},
            {"option_label": "B", "option_text": "增加模型的训练数据量，让模型自行理解边界"},
            {"option_label": "C", "option_text": "使用明确的标记或分隔符（如【输入如下】）标出用户输入的范围"},
            {"option_label": "D", "option_text": "调高 temperature 参数，让模型更灵活地推断边界"},
        ],
        "answer": "C",
        "analysis": "提示词分隔符是提示工程的核心技巧：用固定标记（如【输入如下】、XML 标签、三引号等）明确圈出用户输入，帮助模型区分“指令”与“数据”，减少误读。把指令与输入混写会让模型难以判断边界、容易出错；增加训练数据不改变提示词结构；调高 temperature 只影响输出随机性，与输入边界无关。",
    },
    # 1-0178：原为"引用不存在材料 ask_lm_route 的输入格式题"，改写为自包含的 API 消息角色考点题（答案分散到 D）
    "1-0178": {
        "stem": "在调用大模型 API 时，需要区分系统指令、用户输入与模型历史回复。下列哪种做法符合 API 调用的消息规范？",
        "options": [
            {"option_label": "A", "option_text": "用 temperature 参数的高低来区分不同角色"},
            {"option_label": "B", "option_text": "把所有内容拼接成一段连续文本，不做角色区分"},
            {"option_label": "C", "option_text": "用 max_tokens 参数分别限定各角色的长度"},
            {"option_label": "D", "option_text": "将消息放入 messages 数组，并用 role 字段区分（system / user / assistant）"},
        ],
        "answer": "D",
        "analysis": "OpenAI 兼容 / DashScope 的大模型 API 中，messages 数组的 role 字段用于标识每条消息的角色：system（系统提示词）、user（用户输入）、assistant（模型回复），模型据此理解对话结构。把内容拼接成一段文本会令模型无法分辨指令与输入；temperature 只控制随机性、max_tokens 只限制生成长度，均与消息角色无关。",
    },
    # 1-0294：原题 A/B 均为正确效果（presence_penalty 既减少重复又增加多样性），单选题不唯一，改写干扰项使答案唯一
    "1-0294": {
        "options": [
            {"option_label": "A", "option_text": "减少输出的重复性"},
            {"option_label": "B", "option_text": "增加输出中已出现过的词被再次选中的概率"},
            {"option_label": "C", "option_text": "使输出更具确定性"},
            {"option_label": "D", "option_text": "控制输出长度"},
        ],
        "answer": "A",
        "analysis": "presence_penalty 对已经出现过的 token 施加惩罚：取正值（如 0.6）时，模型会倾向于不再重复使用已出现的词，直接作用是减少输出的重复性（A 正确），并由此带来更多样的话题。B 方向相反——正惩罚是降低而非提高已出现词被再次选中的概率；C 也相反——正惩罚提高随机性、降低确定性；D 是 max_tokens 的作用，与 presence_penalty 无关。",
    },
    # 以下三题题干为"哪些"、答案为多字母，却被标成单选 type=0，修正为多选 type=1
    "3-0192": {"type": 1},
    "3-0215": {"type": 1},
    "7-0160": {"type": 1},
    # 1-0457：题目本身合格，仅补充缺失的解析
    "1-0457": {
        "analysis": "微调（Fine-tuning）是在预训练模型基础上继续训练：预训练阶段模型已习得通用语言规律与知识，微调只需在少量领域数据上做增量学习，因此相比从零训练，计算资源与时间成本都大幅降低（C 正确）。A 把方向说反——微调是更省而非更费；B 的“时间相对较长”也错误，微调训练时间通常远短于全量训练；D 的“完成所有任务”过于绝对——微调只适配特定任务，且可能引入过拟合，不可能在所有任务上全面超越。",
    },
}

# 删除依赖缺失材料、无法独立作答的劣质题（ask_llm_route 函数题 + 缺失的"答疑机器人提示词"材料题）
DELETE_IDS = [
    "2-0127", "2-0141", "2-0163", "2-0207", "2-0210",
    "2-0469", "2-0479", "2-0484", "2-0486", "2-0504",
    "2-0522", "2-0524", "2-0541", "2-0546", "2-1437",
]


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
        found.update(new)  # 仅覆盖给出的字段，其余保留
        print(f"已改写 {qid}: {new.get('stem', new.get('analysis', '')[:36])[:36]}...")

    for qid in DELETE_IDS:
        ch, seq = qid.split("-")
        before = len(data.get(ch, []))
        data[ch] = [q for q in data.get(ch, []) if str(q.get("seq")) != seq]
        if len(data[ch]) < before:
            print(f"已删除 {qid}")
        else:
            print(f"[警告] 未找到待删除 {qid}")

    SRC.write_text(raw[: m.start(1)] + json.dumps(data, ensure_ascii=False) + raw[m.end(1):], encoding="utf-8")

    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "compress_bank.py")], cwd=ROOT)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
