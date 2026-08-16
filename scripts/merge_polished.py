# -*- coding: utf-8 -*-
"""合并两份润色稿为最终知识点文档，并嵌入图表（chart 块）。

用法: python scripts/merge_polished.py
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "ACP高频知识点总结.md"
D16 = ROOT / "docs" / "_draft_1_6_polished.md"
D712 = ROOT / "docs" / "_draft_7_12_polished.md"

# (锚点, 插入内容) —— 锚点必须唯一
CHARTS = [
    # 3.1 RAG 流程动图
    ("ReRank重排 → LLM生成回答\n```",
     "```\n\n```chart flow\n用户提问\n文档解析\n文本切片\n向量化\n向量检索\nReRank 重排\nLLM 生成回答\n```"),
    # 1.5 temperature 对比条形图
    ("计算量大于贪婪解码。",
     "计算量大于贪婪解码。\n\n```chart bars\ntemperature = 0.2（聚焦头部候选） | 90\ntemperature = 1.0（原始分布） | 55\ntemperature = 1.8（分布趋于平坦） | 30\n```"),
    # 1.6 自注意力连线动画
    ("### 1.7 Token 与分词（Tokenization）",
     "```chart attn\n苹果\n很\n好吃\n而且\n便宜\n```\n\n---\n\n### 1.7 Token 与分词（Tokenization）"),
    # 5.7 LoRA 矩阵分解示意
    ("**① 低秩分解（数学原理）**：全参微调需要更新权重增量 ΔW（维度 d×d）；LoRA 把 ΔW 分解为两个小矩阵的乘积：**ΔW = B·A**，其中 A ∈ ℝ^(r×d)、B ∈ ℝ^(d×r)，秩 r（常取 8/16/64）远小于 d（如 4096）。",
     "**① 低秩分解（数学原理）**：全参微调需要更新权重增量 ΔW（维度 d×d）；LoRA 把 ΔW 分解为两个小矩阵的乘积：**ΔW = B·A**，其中 A ∈ ℝ^(r×d)、B ∈ ℝ^(d×r)，秩 r（常取 8/16/64）远小于 d（如 4096）。\n\n```chart matrix\nW₀ + ΔW（4096×4096） | B（4096×16） | A（16×4096）\n```"),
    # 6.2 量化位宽对比条形图
    ("→INT4 缩小 8 倍。",
     "→INT4 缩小 8 倍。\n\n```chart bars\nFP32 全精度（32 bit） | 32\nFP16 半精度（16 bit） | 16\nINT8 量化（8 bit） | 8\nINT4 量化（4 bit） | 4\n```"),
]


def main() -> int:
    original = DOC.read_text(encoding="utf-8")
    idx = original.find("## 1. 大模型基础")
    if idx < 0:
        print("[错误] 原文档中找不到 '## 1. 大模型基础'")
        return 1
    header = original[:idx].rstrip()

    if not D16.exists() or not D712.exists():
        print("[错误] 缺少润色稿文件")
        return 1
    merged = (header + "\n\n" + D16.read_text(encoding="utf-8").rstrip()
              + "\n\n" + D712.read_text(encoding="utf-8").rstrip() + "\n")

    for anchor, insert in CHARTS:
        if merged.count(anchor) != 1:
            print(f"[警告] 锚点出现 {merged.count(anchor)} 次，跳过: {anchor[:30]}...")
            continue
        merged = merged.replace(anchor, insert, 1)
        print(f"已插入图表 @ {anchor[:24]}...")

    DOC.write_text(merged, encoding="utf-8")
    print(f"\n合并完成: {merged.count(chr(10))} 行, {len(merged)} 字符 -> {DOC.name}")
    # 清理临时草稿
    for f in (D16, D712):
        f.unlink(missing_ok=True)
    print("临时草稿已清理")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
