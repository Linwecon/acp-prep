# -*- coding: utf-8 -*-
"""合并四份扩充草稿为最终知识点文档。

草稿文件（由并行写作任务产出）：
    docs/_draft_1_3.md   第 1-3 章
    docs/_draft_4_6.md   第 4-6 章
    docs/_draft_7_9.md   第 7-9 章
    docs/_draft_10_12.md 第 10-12 章 + 附录

合并结果覆盖 docs/ACP高频知识点总结.md。
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "ACP高频知识点总结.md"
DRAFTS = [
    ROOT / "docs" / "_draft_1_3.md",
    ROOT / "docs" / "_draft_4_6.md",
    ROOT / "docs" / "_draft_7_9.md",
    ROOT / "docs" / "_draft_10_12.md",
]

HEADER_END = "## 1. 大模型基础"


def main() -> int:
    original = DOC.read_text(encoding="utf-8")
    idx = original.find(HEADER_END)
    if idx < 0:
        print("[错误] 原文档中找不到", HEADER_END)
        return 1
    header = original[:idx]

    parts = [header.rstrip()]
    for d in DRAFTS:
        if not d.exists():
            print(f"[警告] 缺少草稿 {d.name}，跳过")
            continue
        parts.append(d.read_text(encoding="utf-8").rstrip())
    merged = "\n\n".join(parts) + "\n"

    DOC.write_text(merged, encoding="utf-8")
    n_lines = merged.count("\n")
    n_chars = len(merged)
    print(f"合并完成: {n_lines} 行, {n_chars} 字符 -> {DOC.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
