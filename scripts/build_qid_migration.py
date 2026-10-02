# -*- coding: utf-8 -*-
"""从台账 move 批次生成 qid 迁移映射 data/quiz_qid_migration.js。

客户端（store.js / sync.js）据此把旧 `章-seq` 学习记录迁移到新编号，
保留原有进度/错题/收藏，不清空任何记录。
"""
import json
import pathlib
import hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
led = json.loads((ROOT / 'data' / 'curate' / 'ledger.json').read_text(encoding='utf-8'))

mapping = {}
for b in led['batches']:
    if b.get('kind') != 'move':
        continue
    for it in b.get('items', []):
        old_qid = it.get('qid')
        to = it.get('to')
        after = it.get('after_seq')
        if not (old_qid and to is not None and after):
            continue
        new_qid = f'{to}-{str(after).zfill(4)}'
        if old_qid != new_qid:
            mapping[old_qid] = new_qid

# 传递链收敛：a->b 且 b->c 时直接映射到 c
changed = True
while changed:
    changed = False
    for k, v in list(mapping.items()):
        if v in mapping:
            mapping[k] = mapping[v]
            changed = True

h = hashlib.md5(json.dumps(mapping, sort_keys=True).encode()).hexdigest()[:10]
lines = [f'/* 自动生成：scripts/build_qid_migration.py（hash {h}）。移章批次旧题号→新题号映射，'
         '用于客户端学习记录迁移，请勿手工编辑。 */',
         'window.ACP_QID_MIGRATION = ' + json.dumps(mapping, ensure_ascii=False, indent=0,
                                                   sort_keys=True) + ';']
out = ROOT / 'data' / 'quiz_qid_migration.js'
out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'映射 {len(mapping)} 条 -> {out.name}')
sample = list(mapping.items())[:3]
for k, v in sample:
    print(' ', k, '->', v)
