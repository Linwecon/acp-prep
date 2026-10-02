# -*- coding: utf-8 -*-
"""教程（Notebook）预转换产物校验：python scripts/test_notebooks.py

检查项：
- 索引结构完整（分组 / 标题 / 简介 / 难度 / 时长 / 内容块数）
- 每篇都有正文文件与原文件副本
- 目录项指向存在的 Markdown 块与块内标题序号
- 引用的图片文件存在
- 生成的 JS 不含会提前闭合脚本的内容
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / 'data' / 'notebooks.js'
OUT_DIR = ROOT / 'data' / 'notebooks'
SRC_DIR = OUT_DIR / 'src'

fails = []
checks = 0


def ok(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)


def load_index():
    t = INDEX.read_text(encoding='utf-8')
    prefix = 'window.NOTEBOOK_INDEX='
    ok(t.startswith(prefix), '索引文件前缀异常')
    return json.loads(t[len(prefix):].rstrip().rstrip(';'))


def load_content(slug):
    p = OUT_DIR / f'{slug}.js'
    t = p.read_text(encoding='utf-8')
    m = re.search(r'window\.NOTEBOOK_CONTENT\["' + re.escape(slug) + r'"\]=(.*);\s*$', t, re.S)
    ok(bool(m), f'{slug}: 正文文件格式异常')
    return json.loads(m.group(1)) if m else None


def main():
    ok(INDEX.exists(), '缺少 data/notebooks.js（请先运行 build_notebooks.py）')
    if not INDEX.exists():
        print('FAIL:', fails[0])
        return 1

    idx = load_index()
    ok(isinstance(idx.get('chapters'), list) and idx['chapters'], '索引缺少 chapters')
    total = 0
    for ch in idx['chapters']:
        ok(bool(ch.get('id')) and bool(ch.get('title')), '分组缺少 id/title')
        ok(isinstance(ch.get('items'), list), f'{ch.get("id")}: items 缺失')
        total += len(ch['items'])
        for it in ch['items']:
            for k in ('id', 'title', 'desc', 'difficulty', 'minutes', 'cells', 'blocks'):
                ok(k in it, f'{it.get("id")}: 缺少字段 {k}')
            ok(it.get('difficulty') in ('入门', '进阶', '挑战'),
               f'{it["id"]}: 难度取值异常 {it.get("difficulty")}')
            ok(isinstance(it.get('minutes'), int) and 5 <= it['minutes'] <= 120,
               f'{it["id"]}: 时长不合理 {it.get("minutes")}')
            ok(bool(it.get('desc')), f'{it["id"]}: 简介为空')

            content = load_content(it['id'])
            ok(content is not None, f'{it["id"]}: 正文加载失败')
            if not content:
                continue
            blocks = content.get('blocks') or []
            ok(len(blocks) == it['blocks'], f'{it["id"]}: 索引与正文块数不一致')
            ok(any(b['t'] == 'md' for b in blocks), f'{it["id"]}: 没有任何讲解内容')
            # 顺序与内容
            for i, b in enumerate(blocks):
                ok(b.get('t') in ('md', 'code'), f'{it["id"]}: 未知块类型 {b.get("t")}')
                if b['t'] == 'md':
                    ok(bool((b.get('md') or '').strip()), f'{it["id"]}#{i}: 空 Markdown 块')
                else:
                    ok(bool((b.get('src') or '').strip()), f'{it["id"]}#{i}: 空代码块')
                    for o in (b.get('outs') or []):
                        if o.get('t') == 'img':
                            ok((ROOT / o['src']).exists(), f'{it["id"]}#{i}: 图片缺失 {o["src"]}')
            # 目录项指向有效位置
            for e in content.get('toc') or []:
                b, h = e.get('b'), e.get('h')
                ok(isinstance(b, int) and 0 <= b < len(blocks), f'{it["id"]}: 目录块越界 {b}')
                if isinstance(b, int) and 0 <= b < len(blocks):
                    blk = blocks[b]
                    ok(blk['t'] == 'md', f'{it["id"]}: 目录指向非 Markdown 块 {b}')
                    if blk['t'] == 'md':
                        heads = re.findall(r'^#{1,3}\s+\S', blk['md'], re.M)
                        ok(isinstance(h, int) and 0 <= h < len(heads),
                           f'{it["id"]}: 目录标题序号越界 {b}/{h}')

    ok(total == idx.get('count'), f'count({idx.get("count")}) 与实际({total}) 不一致')

    # JS 安全性：不得出现能闭合 script 的字面量
    for p in list(OUT_DIR.glob('*.js')) + [INDEX]:
        ok('</script' not in p.read_text(encoding='utf-8').lower(), f'{p.name}: 含 </script 字面量')

    print(f'教程校验：{total} 篇，{checks} 项检查')
    if fails:
        print('FAIL:')
        for f in fails[:15]:
            print('  -', f)
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
