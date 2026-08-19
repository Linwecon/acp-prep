# -*- coding: utf-8 -*-
"""生成可分享的部署包 dist/acp_share.zip

只包含运行必需文件，自动排除：
  - config/（含 API Key 的 verify_config.json）
  - data/ 下的校验缓存（verify_*.json、*.log）
  - 源数据 JSON（quiz_data.json、quiz_categorized.json）
  - scripts/、docs/、.gitignore

用法:
    python scripts/build_share.py
输出:
    dist/acp_share.zip
"""
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "dist"
OUT = OUT_DIR / "acp_share.zip"

INCLUDE = [
    "index.html",
    "style.css",
    "js/acp.js",
    "js/utils.js",
    "js/store.js",
    "js/data.js",
    "js/sidebar.js",
    "js/dashboard.js",
    "js/chapter.js",
    "js/study.js",
    "js/exam.js",
    "js/search.js",
    "js/ai.js",
    "js/app.js",
    "data/quiz_categorized.min.js",
    "data/knowledge.js",
    "README.md",
]


def main() -> int:
    missing = [f for f in INCLUDE if not (ROOT / f).exists()]
    if missing:
        print("[错误] 缺少文件:", ", ".join(missing))
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    total = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            zf.write(ROOT / rel, arcname=rel)
            size = (ROOT / rel).stat().st_size
            total += size
            print(f"  + {rel}  ({size/1024:.0f} KB)")
    print(f"\n已生成 {OUT}  ({OUT.stat().st_size/1024/1024:.2f} MB, 含 {len(INCLUDE)} 个文件)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
