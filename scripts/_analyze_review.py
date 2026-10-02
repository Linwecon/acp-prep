# -*- coding: utf-8 -*-
"""临时分析：待复核项分类（可确认 / 答案存疑 / 需逐题审查），导出工作清单。"""
import json
import pathlib
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
a = json.load(open(ROOT / 'data/curate/governance/audit.json', encoding='utf-8'))
bank = json.load(open(ROOT / 'data/quiz_categorized.json', encoding='utf-8'))
idx = {}
for ch, qs in bank['questions_by_chapter'].items():
    for q in qs:
        idx[f'{ch}-{str(q["seq"]).zfill(4)}'] = q


def norm(x):
    return sorted(set(str(i).strip() for i in (x or [])))


chs = {4, 6, 7, 10, 11, 12}
rev = [r for r in a['rows'] if r['action'] == 'review']
conf, diff_ans, manual = Counter(), Counter(), Counter()
manual_ids = []
for r in rev:
    ch = r['chapter']
    f = r.get('first') or {}
    s = r.get('second') or {}
    bank_ans = norm(idx.get(r['qid'], {}).get('answer'))
    fa, sa = norm(f.get('answer')), norm(s.get('answer'))
    ok_cls = f.get('classification') in ('own', 'cross') and s.get('classification') in ('own', 'cross')
    ok_q = f.get('quality') == 'ok' and s.get('quality') == 'ok'
    if ch not in chs:
        continue
    if ok_q and ok_cls and fa and fa == sa == bank_ans:
        conf[ch] += 1
    elif ok_q and ok_cls and fa and fa == sa:
        diff_ans[ch] += 1
    else:
        manual[ch] += 1
        manual_ids.append(r['qid'])

print('可确认(双模型一致=题库):', dict(sorted(conf.items())), sum(conf.values()))
print('双模型一致但≠题库:', dict(sorted(diff_ans.items())), sum(diff_ans.values()))
print('需逐题审查:', dict(sorted(manual.items())), sum(manual.values()))
print('manual ids:', manual_ids)

# 导出六章节需逐题审查的紧凑工作清单
out = []
for r in rev:
    if r['qid'] not in manual_ids:
        continue
    q = idx.get(r['qid'], {})
    f = r.get('first') or {}
    s = r.get('second') or {}
    out.append({
        'qid': r['qid'], 'ch': r['chapter'],
        'type': q.get('type'), 'stem': q.get('stem', '')[:150],
        'options': [(o['option_label'], o['option_text'][:60]) for o in q.get('options', [])],
        'bank': q.get('answer'), 'first_answer': f.get('answer'), 'second_answer': s.get('answer'),
        'f_quality': f.get('quality'), 's_quality': s.get('quality'),
        'f_cls': f.get('classification'), 's_cls': s.get('classification'),
        'f_chapter': f.get('chapter'), 's_chapter': s.get('chapter'),
        'f_reason': (f.get('reason') or '')[:100], 's_reason': (s.get('reason') or '')[:100],
    })
p = ROOT / 'data/curate/governance/_manual_worklist.json'
p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
print('written', p, len(out))
