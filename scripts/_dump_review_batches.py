# -*- coding: utf-8 -*-
"""导出人工复核工作清单：A=可确认抽查样张；B=双模型一致但异于题库；C=需逐题审查。"""
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
A, B, C = [], [], []
for r in rev:
    if r['chapter'] not in chs:
        continue
    q = idx.get(r['qid'])
    if not q:
        continue
    f = r.get('first') or {}
    s = r.get('second') or {}
    fa, sa = norm(f.get('answer')), norm(s.get('answer'))
    bank_ans = norm(q.get('answer'))
    ok_cls = f.get('classification') in ('own', 'cross') and s.get('classification') in ('own', 'cross')
    ok_q = f.get('quality') == 'ok' and s.get('quality') == 'ok'
    base = {
        'qid': r['qid'], 'ch': r['chapter'], 'type': q.get('type'),
        'stem': q.get('stem', ''),
        'options': [(o['option_label'], o['option_text']) for o in q.get('options', [])],
        'bank': q.get('answer'),
        'f_reason': (f.get('reason') or '')[:80], 's_reason': (s.get('reason') or '')[:80],
    }
    if ok_q and ok_cls and fa and fa == sa == bank_ans:
        A.append(base)
    elif ok_q and ok_cls and fa and fa == sa:
        base['model_ans'] = fa
        base['f_why'] = '; '.join((d.get('why') or '')[:30] for d in (f.get('per_option') or []) if isinstance(d, dict))
        B.append(base)
    else:
        base.update({'f_answer': f.get('answer'), 's_answer': s.get('answer'),
                     'f_quality': f.get('quality'), 's_quality': s.get('quality'),
                     'f_cls': f.get('classification'), 's_cls': s.get('classification'),
                     'f_chapter': f.get('chapter'), 's_chapter': s.get('chapter')})
        C.append(base)

out = ROOT / 'data/curate/governance'
out.mkdir(parents=True, exist_ok=True)
(out / '_review_A_confirm.json').write_text(json.dumps(A, ensure_ascii=False, indent=1), encoding='utf-8')
(out / '_review_B_ansdiff.json').write_text(json.dumps(B, ensure_ascii=False, indent=1), encoding='utf-8')
(out / '_review_C_manual.json').write_text(json.dumps(C, ensure_ascii=False, indent=1), encoding='utf-8')
print('A(可确认候选)', len(A), dict(Counter(x['ch'] for x in A)))
print('B(答案存疑)', len(B), dict(Counter(x['ch'] for x in B)))
print('C(需逐题审查)', len(C), dict(Counter(x['ch'] for x in C)))
