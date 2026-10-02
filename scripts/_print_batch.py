# -*- coding: utf-8 -*-
"""按章打印待复核题与双模型判定，供人工裁决。用法: python _print_batch.py 6 [start] [end]"""
import json
import sys
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent
gov = root / 'data' / 'curate' / 'governance'
data = json.loads((gov / '_adjudicate_gapch.json').read_text(encoding='utf-8'))

ch = sys.argv[1]
start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
end = int(sys.argv[3]) if len(sys.argv) > 3 else 10 ** 9
items = [o for o in data if str(o['ch']) == ch][start:end]
for i, o in enumerate(items):
    print(f"### [{start+i}] {o['qid']} type={o['type']} bank={o['bank']}")
    print('T:', o['stem'])
    for l, t in o['options']:
        print(f'  {l}. {t}')
    for tag in ('first', 'second'):
        m = o.get(tag)
        if not m:
            continue
        print(f"  {tag}: ans={m.get('answer')} q={m.get('quality')} cls={m.get('classification')} ch={m.get('chapter')} sup={m.get('supported')}")
        r = (m.get('reason') or '')[:150]
        if r:
            print(f'    why: {r}')
    print()
