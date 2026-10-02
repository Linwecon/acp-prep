# -*- coding: utf-8 -*-
"""把官方实战教程 .ipynb 预转换为静态网页数据（不在浏览器执行 Python）。

用法:
    python scripts/build_notebooks.py                 # 默认源目录 aliyun_acp_learning/大模型ACP认证教程
    python scripts/build_notebooks.py --src <目录>     # 指定教程目录

产物:
    data/notebooks.js                 # 教程索引（章节分组 + 标题/简介/难度/时长）
    data/notebooks/<id>.js            # 单个教程正文（Markdown / 代码 / 输出 / 图片，按原顺序）
    assets/notebooks/<id>/*.png       # 代码单元的图片输出（base64 还原为文件）

源文件下载：详情页不再提供本地副本，列表页链接指向官方仓库
    https://github.com/AlibabaCloudDocs/aliyun_acp_learning

设计约束:
- 纯静态：内容预先落盘为 JS 数据，页面只做渲染，不执行任何 Python；
- Markdown 沿用站点既有渲染器 js/study.js 的 ACP.mdToHtml，保持教材风格一致；
- 源仓库（aliyun_acp_learning）不在本仓库内，缺失时给出提示并不破坏已生成数据。
"""
import argparse
import base64
import json
import pathlib
import re
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / 'aliyun_acp_learning' / '大模型ACP认证教程'
OUT_INDEX = ROOT / 'data' / 'notebooks.js'
OUT_DIR = ROOT / 'data' / 'notebooks'
IMG_DIR = ROOT / 'assets' / 'notebooks'
SOURCE_REPO = 'https://github.com/AlibabaCloudDocs/aliyun_acp_learning'

# 章节分组：目录前缀 → (id, 标题, 关联站点章节)
CHAPTER_META = [
    ('C1', 'c1', 'C1 课程准备', '环境搭建与 API 调用入门', ['1', '9', '10']),
    ('C2', 'c2', 'C2 构造问答系统', '从提示词到 RAG 与自动化评测', ['2', '3', '7']),
    ('C3', 'c3', 'C3 构建 Agent 系统', '工具调用、规划、多 Agent 与工程化', ['4', '11']),
    ('C4', 'c4', 'C4 交付上线', '蒸馏、部署、生产实践与安全合规', ['5', '6', '8']),
    ('C5', 'c5', 'C5 总结与展望', '用 AI 为业务提效的方法论', []),
]
EXTRA_GROUP = ('extra', '拓展实战', '课程配套拓展 Notebook', [])


def js_safe(obj) -> str:
    """JSON 序列化并避免 </script> 提前结束脚本。"""
    s = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    return s.replace('</', '<\\/')


def cell_src(cell) -> str:
    src = cell.get('source', [])
    return ''.join(src) if isinstance(src, list) else str(src)


def slugify(path: pathlib.Path, src_root: pathlib.Path) -> tuple:
    """由路径生成 (分组id, slug, 排序号)。"""
    rel = path.relative_to(src_root)
    top = rel.parts[0] if len(rel.parts) > 1 else ''
    group_id = None
    for prefix, gid, *_ in CHAPTER_META:
        if top.startswith(prefix):
            group_id = gid
            break
    if group_id is None:
        group_id = EXTRA_GROUP[0]
    m = re.match(r'(\d+)[_-](\d+)', path.stem)
    num = f'{m.group(1)}-{m.group(2)}' if m else re.sub(r'\W+', '-', path.stem).lower()
    return group_id, f'{group_id}-{num}', num


def split_num(s: str):
    parts = [int(x) for x in re.findall(r'\d+', s)]
    return parts + [0] * (2 - len(parts))


def file_title(path: pathlib.Path) -> str:
    """由文件名生成形如 “2.1 用大模型构建新人答疑机器人” 的标题。"""
    stem = re.sub(r'^(\d+)[_-](\d+)[_-]?', r'\1.\2 ', path.stem)
    return stem.replace('_', ' ').strip()[:60]


def pick_title(md: str, path: pathlib.Path) -> str:
    """优先用 H1；H1 过长（像一句说明）时退回文件名标题。"""
    m = re.search(r'^#\s+(.+?)\s*$', md, re.M)
    if m:
        t = re.sub(r'^[\d.\s]+', '', m.group(1)).strip()
        if t and len(t) <= 26:
            return t[:60]
    return file_title(path)


def pick_desc(cells_md: list, title: str) -> str:
    """取首个 H1 之后的第一段正文作为简介；列表/引用/ HTML 不算。"""
    for md in cells_md[:6]:
        lines = md.split('\n')
        started = False
        buf = []
        for ln in lines:
            s = ln.strip()
            if re.match(r'^#{1,6}\s', s):
                if started and buf:
                    break
                started = True
                continue
            if not started or not s:
                continue
            if s.startswith(('>', '*', '-', '|', '```', ':', '<', '[')):
                continue
            if '](' in s:   # 链接 / 图片 / 视频行不作为简介
                continue
            buf.append(re.sub(r'\s+', ' ', s))
            if len(' '.join(buf)) > 80:
                break
        desc = re.sub(r'\s+', ' ', ' '.join(buf)).strip(' 。')
        if desc and len(desc) >= 8:
            return desc[:110]
    return title


def _cell_text(html: str) -> str:
    """表格单元格：去标签、合并空白、避免竖线破坏列结构。"""
    t = re.sub(r'<(?:br|p|div|li)\b[^>]*>', ' ', html, flags=re.I)
    t = re.sub(r'</?(?:pre|code)\b[^>]*>', ' ', t, flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t.replace('|', '｜')


def _table_repl(m):
    """<table> → Markdown 表格（首行为表头）。"""
    html = m.group(0)
    rows = re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, flags=re.S | re.I)
    out = []
    for ri, r in enumerate(rows):
        cells = [_cell_text(c) for c in re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>', r, flags=re.S | re.I)]
        cells = [c for c in cells if c != '' or len(cells) <= 1]
        if not cells:
            continue
        out.append('| ' + ' | '.join(cells) + ' |')
        if ri == 0:
            out.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
    return ('\n\n' + '\n'.join(out) + '\n\n') if out else ''


def _details_repl(m):
    """<details><summary>题面</summary>答案</details> → 教材自测题折叠块。"""
    html = m.group(0)
    sm = re.search(r'<summary\b[^>]*>(.*?)</summary>', html, flags=re.S | re.I)
    summary = re.sub(r'<[^>]+>', '', sm.group(1)).strip() if sm else '自测题'
    body = html[(sm.end() if sm else 0):]
    body = re.sub(r'</?details\b[^>]*>', '', body, flags=re.I)
    return f'\n\n:::qa {summary[:60]}\n{body.strip()}\n:::\n\n'


def sanitize_md(md: str) -> str:
    """把 Notebook 里的原生 HTML 转成渲染器可识别的 Markdown。

    教程正文混有 <table>/<div>/<p>/<details>/<b> 等标签，直接渲染会把源码当正文显示；
    这里统一转换：表格 → Markdown 表格、折叠答案 → 自测题块、段落/列表 → 标准 Markdown。
    """
    # 1. 样式与脚本（不参与渲染）
    md = re.sub(r'<(style|script)\b[^>]*>.*?</\1>', '', md, flags=re.S | re.I)

    # 2. 媒体：<video> → 视频链接，<img> → Markdown 图片
    def video_repl(m):
        src = re.search(r'src="([^"]+)"', m.group(0))
        return f'\n🎬 [视频演示（点击播放）]({src.group(1)})\n' if src else ''
    md = re.sub(r'<video\b[^>]*>.*?</video>', video_repl, md, flags=re.S | re.I)

    def img_repl(m):
        tag = m.group(0)
        src = re.search(r'src="([^"]+)"', tag)
        alt = re.search(r'alt="([^"]*)"', tag)
        return f'![{alt.group(1) if alt else "图片"}]({src.group(1)})' if src else ''
    md = re.sub(r'<img\b[^>]*>', img_repl, md, flags=re.I)

    md = re.sub(r'<br\s*/?>', '\n', md, flags=re.I)

    # 3. 表格（先于其它块级处理，避免单元格内容被拆分）
    md = re.sub(r'<table\b[^>]*>.*?</table>', _table_repl, md, flags=re.S | re.I)

    # 4. 折叠块：课后小测验 / 参考答案
    md = re.sub(r'<details\b[^>]*>.*?</details>', _details_repl, md, flags=re.S | re.I)

    # 5. 独立代码块
    def pre_repl(m):
        inner = re.sub(r'</?code\b[^>]*>', '', m.group(1), flags=re.I)
        return '\n\n```\n' + inner.strip('\n') + '\n```\n\n'
    md = re.sub(r'<pre\b[^>]*>(.*?)</pre>', pre_repl, md, flags=re.S | re.I)

    # 6. 列表
    md = re.sub(r'</?[uo]l\b[^>]*>', '\n', md, flags=re.I)
    md = re.sub(r'<li\b[^>]*>', '\n- ', md, flags=re.I)
    md = re.sub(r'</li>', '', md, flags=re.I)

    # 7. 标题（h4-h6 → ####…，h1-h3 保留文本由 Markdown 标题处理）
    md = re.sub(r'<h([1-6])\b[^>]*>(.*?)</h\1>',
                lambda m: '\n\n' + '#' * int(m.group(1)) + ' ' + re.sub(r'<[^>]+>', '', m.group(2)).strip() + '\n\n',
                md, flags=re.S | re.I)

    # 8. 段落 / 容器 → 空行分隔
    md = re.sub(r'</?(?:p|div|figure|figcaption|tbody|thead|section)\b[^>]*>', '\n\n', md, flags=re.I)

    # 9. 行内标签
    md = re.sub(r'<(b|strong)\b[^>]*>(.*?)</\1>', r'**\2**', md, flags=re.S | re.I)
    md = re.sub(r'<(i|em)\b[^>]*>(.*?)</\1>', r'*\2*', md, flags=re.S | re.I)
    md = re.sub(r'<code\b[^>]*>(.*?)</code>', r'`\1`', md, flags=re.S | re.I)
    md = re.sub(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r'[\2](\1)', md, flags=re.S | re.I)
    # 仅保留文本的标签
    md = re.sub(r'</?(?:mark|u|s|sub|sup|span|font|small|owner|dev|tag)\b[^>]*>', '', md, flags=re.I)

    # 10. 兜底：清除所有剩余标签
    md = re.sub(r'<[^>]+>', '', md)

    # 11. 实体还原（还原后由渲染器统一转义显示）
    md = (md.replace('&nbsp;', ' ').replace('&amp;', '&')
            .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"'))

    # 12. 规范空行
    md = re.sub(r'[ \t]+\n', '\n', md)
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def build_toc(blocks: list) -> list:
    """目录项记录 (所属块, 块内第几个标题)，前端按同样顺序给标题加 id。"""
    toc = []
    for i, b in enumerate(blocks):
        if b['t'] != 'md':
            continue
        h = 0
        for line in b['md'].split('\n'):
            m = re.match(r'^(#{1,3})\s+(.+?)\s*$', line)
            if m:
                toc.append({'lvl': len(m.group(1)),
                            'text': re.sub(r'[#*`]', '', m.group(2)).strip()[:60],
                            'b': i, 'h': h})
                h += 1
    # 去掉完全重复的相邻标题（同格多行重复）
    out, seen = [], set()
    for e in toc:
        key = (e['lvl'], e['text'], e['b'])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def difficulty_of(stats: dict, group_id: str) -> str:
    """难度启发式（构建脚本内标注，供列表展示）。"""
    if group_id == 'c1':
        return '入门'
    score = (stats['code'] * 1.4 + stats['h3'] * 0.3 + stats['outs'] * 0.5
             + stats['chars'] / 4000)
    if score < 18:
        return '入门'
    if score < 45:
        return '进阶'
    return '挑战'


def minutes_of(stats: dict) -> int:
    """预计学习时长（分钟，取整到 5）。"""
    raw = (stats['md_chars'] / 900 + stats['code'] * 0.6
           + stats['code_lines'] * 0.03 + stats['out_chars'] / 600)
    mins = int(round(max(8, min(90, raw)) / 5) * 5)
    return mins


def convert(path: pathlib.Path, src_root: pathlib.Path, group_id: str, slug: str) -> dict:
    nb = json.loads(path.read_text(encoding='utf-8'))
    cells = nb.get('cells', [])
    blocks = []
    md_cells = []
    stats = {'cells': len(cells), 'code': 0, 'md': 0, 'outs': 0, 'h3': 0,
             'chars': 0, 'md_chars': 0, 'code_lines': 0, 'out_chars': 0}
    img_seq = 0

    for cell in cells:
        kind = cell.get('cell_type')
        src = cell_src(cell)
        if kind == 'markdown':
            if not src.strip():
                continue
            src = sanitize_md(src)
            stats['md'] += 1
            stats['md_chars'] += len(src)
            stats['h3'] += len(re.findall(r'^#{3,4}\s', src, re.M))
            blocks.append({'t': 'md', 'md': src})
            md_cells.append(src)
            continue
        if kind != 'code':
            continue
        if not src.strip() and not (cell.get('outputs') or []):
            continue
        stats['code'] += 1
        stats['code_lines'] += len([l for l in src.split('\n') if l.strip()])
        outs = []
        for o in (cell.get('outputs') or []):
            otype = o.get('output_type')
            data = o.get('data') or {}
            if 'image/png' in data:
                img_seq += 1
                img_dir = IMG_DIR / slug
                img_dir.mkdir(parents=True, exist_ok=True)
                rel = f'assets/notebooks/{slug}/out-{img_seq}.png'
                (ROOT / rel).write_bytes(base64.b64decode(data['image/png']))
                outs.append({'t': 'img', 'src': rel})
                stats['outs'] += 1
                continue
            text = None
            if otype == 'stream':
                text = ''.join(o.get('text', []))
            elif 'text/plain' in data:
                v = data['text/plain']
                text = ''.join(v) if isinstance(v, list) else str(v)
            elif otype == 'error':
                text = '\n'.join(o.get('traceback', []))
            if text is None:
                continue
            text = text.rstrip()
            if not text:
                continue
            outs.append({'t': 'out', 'kind': otype or 'stream', 'text': text[:4000]})
            stats['outs'] += 1
            stats['out_chars'] += len(text)
        stats['chars'] += len(src)
        blocks.append({'t': 'code', 'src': src, 'exec': cell.get('execution_count'),
                       'outs': outs})

    first_md = md_cells[0] if md_cells else ''
    title = pick_title(first_md, path)
    stats['chars'] = stats['md_chars'] + sum(len(b.get('src', '')) for b in blocks if b['t'] == 'code')
    return {
        'id': slug,
        'title': title,
        'desc': pick_desc(md_cells, title),
        'difficulty': difficulty_of(stats, group_id),
        'minutes': minutes_of(stats),
        'blocks': blocks,
        'toc': build_toc(blocks),
        'stats': stats,
        'origin': str(path.relative_to(src_root)).replace('\\', '/'),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=str(DEFAULT_SRC), help='教程 Notebook 源目录')
    args = ap.parse_args()

    src_root = pathlib.Path(args.src)
    if not src_root.exists():
        print(f'[提示] 未找到教程源目录：{src_root}')
        print('       教程源仓库（aliyun_acp_learning）不在本仓库内；'
              '已生成的 data/notebooks*.js 仍然可用，无需重新构建。')
        return 0

    files = [p for p in sorted(src_root.rglob('*.ipynb')) if '.ipynb_checkpoints' not in str(p)]
    if not files:
        print('[提示] 源目录下没有 .ipynb 文件')
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    grouped = {}
    for _prefix, gid, title, desc, chs in CHAPTER_META:
        grouped[gid] = {'id': gid, 'title': title, 'desc': desc, 'chs': chs, 'items': []}
    grouped[EXTRA_GROUP[0]] = {'id': EXTRA_GROUP[0], 'title': EXTRA_GROUP[1],
                               'desc': EXTRA_GROUP[2], 'chs': EXTRA_GROUP[3], 'items': []}

    total_blocks = 0
    for path in files:
        gid, slug, num = slugify(path, src_root)
        if slug.startswith('extra-') and not re.match(r'^\d', path.stem):
            num = '99-' + num
        data = convert(path, src_root, gid, slug)
        data['order'] = num
        # 正文文件（按需加载，避免首屏加载全部内容）
        (OUT_DIR / f'{slug}.js').write_text(
            'window.NOTEBOOK_CONTENT=window.NOTEBOOK_CONTENT||{};\n'
            f'window.NOTEBOOK_CONTENT[{json.dumps(slug, ensure_ascii=False)}]={js_safe(data)};\n',
            encoding='utf-8')
        item = {k: data[k] for k in ('id', 'title', 'desc', 'difficulty', 'minutes', 'order')}
        item.update({'cells': data['stats']['cells'], 'code': data['stats']['code'],
                     'outs': data['stats']['outs'], 'blocks': len(data['blocks'])})
        grouped[gid]['items'].append(item)
        total_blocks += len(data['blocks'])

    for g in grouped.values():
        g['items'].sort(key=lambda x: split_num(x['order']))

    chapters = [grouped[gid] for _prefix, gid, *_rest in CHAPTER_META if grouped[gid]['items']]
    if grouped[EXTRA_GROUP[0]]['items']:
        chapters.append(grouped[EXTRA_GROUP[0]])

    index = {
        'updated': datetime.now().isoformat(timespec='seconds'),
        'source': str(src_root.relative_to(ROOT)).replace('\\', '/'),
        'source_repo': SOURCE_REPO,
        'count': sum(len(c['items']) for c in chapters),
        'chapters': chapters,
    }
    OUT_INDEX.write_text(
        'window.NOTEBOOK_INDEX=' + js_safe(index) + ';\n', encoding='utf-8')

    print(f'教程 {index["count"]} 篇 / {len(chapters)} 个分组 · 内容块 {total_blocks}')
    for c in chapters:
        print(f'  {c["title"]}: {len(c["items"])} 篇')
    print(f'索引 -> {OUT_INDEX.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
